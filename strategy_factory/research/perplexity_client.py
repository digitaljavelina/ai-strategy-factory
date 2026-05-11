"""
Perplexity search client backed by OpenRouter.

Routes Perplexity Sonar model calls through OpenRouter's OpenAI-compatible
chat completions API, while preserving the QueryResult/SearchResult interface
expected by the rest of the pipeline. Citations returned by Perplexity (via
`annotations` and the top-level `citations` field) are mapped back into
`SearchResult` records so downstream synthesis works unchanged.
"""

import os
import time
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass

import httpx

from ..config import (
    RETRY_CONFIG,
    PERPLEXITY_COSTS,
    PerplexityModel,
    QUALITY_DOMAINS,
    OPENROUTER_BASE_URL,
    OPENROUTER_PERPLEXITY_PREFIX,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_APP_TITLE,
)
from ..models import SearchResult, QueryResult


@dataclass
class CacheEntry:
    """Represents a cached query result."""
    query_hash: str
    query: str
    result: QueryResult
    timestamp: datetime
    ttl_hours: int = 24


class PerplexityClient:
    """
    OpenRouter-backed wrapper for Perplexity Sonar models.

    Features:
    - Automatic retry with exponential backoff
    - Query result caching
    - Cost estimation and tracking
    - Rate limiting
    - Multi-query support
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        enable_cache: bool = True,
    ):
        """
        Initialize the client.

        Args:
            api_key: OpenRouter API key. If not provided, uses OPENROUTER_API_KEY env var.
            cache_dir: Directory for caching query results.
            enable_cache: Whether to enable result caching.
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment variables")

        self.base_url = OPENROUTER_BASE_URL
        self.http = httpx.Client(timeout=180.0)
        self.enable_cache = enable_cache
        self.cache_dir = cache_dir
        self.cache: Dict[str, CacheEntry] = {}

        # Cost tracking
        self.total_cost = 0.0
        self.query_count = 0

        # Rate limiting
        self.last_request_time = 0.0
        self.min_request_interval = 1.0  # seconds between requests

        # Load cache from disk if available
        if self.cache_dir and self.enable_cache:
            self._load_cache()

    def _get_cache_key(self, query: str, **params) -> str:
        """Generate a cache key from query and parameters."""
        cache_data = {"query": query, **params}
        cache_str = json.dumps(cache_data, sort_keys=True, default=str)
        return hashlib.md5(cache_str.encode()).hexdigest()

    def _load_cache(self) -> None:
        """Load cache from disk."""
        if not self.cache_dir:
            return

        cache_file = self.cache_dir / "research_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    for key, entry in data.items():
                        result_dict = entry["result"]
                        result_dict["timestamp"] = datetime.fromisoformat(result_dict["timestamp"])
                        results = [SearchResult(**r) for r in result_dict["results"]]
                        result_dict["results"] = results

                        self.cache[key] = CacheEntry(
                            query_hash=key,
                            query=entry["query"],
                            result=QueryResult(**result_dict),
                            timestamp=datetime.fromisoformat(entry["timestamp"]),
                            ttl_hours=entry.get("ttl_hours", 24),
                        )
            except Exception as e:
                print(f"Warning: Could not load cache: {e}")

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if not self.cache_dir:
            return

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self.cache_dir / "research_cache.json"

        try:
            data = {}
            for key, entry in self.cache.items():
                result_dict = entry.result.model_dump()
                result_dict["timestamp"] = result_dict["timestamp"].isoformat()
                result_dict["results"] = [r.model_dump() for r in entry.result.results]

                data[key] = {
                    "query": entry.query,
                    "result": result_dict,
                    "timestamp": entry.timestamp.isoformat(),
                    "ttl_hours": entry.ttl_hours,
                }

            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"Warning: Could not save cache: {e}")

    def _is_cache_valid(self, entry: CacheEntry) -> bool:
        """Check if a cache entry is still valid."""
        age_hours = (datetime.now() - entry.timestamp).total_seconds() / 3600
        return age_hours < entry.ttl_hours

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _estimate_cost(
        self,
        model: PerplexityModel,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate the cost of a query using per-1K token rates."""
        input_cost, output_cost = PERPLEXITY_COSTS.get(model, (0.001, 0.001))
        return (input_tokens / 1000 * input_cost) + (output_tokens / 1000 * output_cost)

    def _openrouter_model_id(self, model: PerplexityModel) -> str:
        """Map an internal PerplexityModel enum to the OpenRouter model ID."""
        return f"{OPENROUTER_PERPLEXITY_PREFIX}{model.value}"

    def _build_extra_body(
        self,
        max_results: int,
        country: Optional[str],
        search_recency_filter: Optional[str],
        search_after_date: Optional[str],
        search_before_date: Optional[str],
        search_domain_filter: Optional[List[str]],
        use_quality_domains: bool,
    ) -> Dict[str, Any]:
        """
        Build Perplexity-specific search options forwarded via OpenRouter.

        OpenRouter passes unknown body fields through to the underlying provider,
        which allows Perplexity's search controls (recency, domain filter, etc.)
        to keep working.
        """
        extra: Dict[str, Any] = {}

        if search_recency_filter:
            extra["search_recency_filter"] = search_recency_filter
        if search_after_date:
            extra["search_after_date"] = search_after_date
        if search_before_date:
            extra["search_before_date"] = search_before_date
        if country:
            extra["search_country"] = country

        if use_quality_domains and not search_domain_filter:
            extra["search_domain_filter"] = QUALITY_DOMAINS[:20]
        elif search_domain_filter:
            extra["search_domain_filter"] = search_domain_filter[:20]

        # Hint Perplexity on how many sources to surface
        extra["web_search_options"] = {"search_context_size": "medium"}
        extra["max_search_results"] = max(1, min(max_results, 20))

        return extra

    def search(
        self,
        query: Union[str, List[str]],
        max_results: int = 10,
        max_tokens_per_page: int = 1024,
        country: Optional[str] = None,
        search_recency_filter: Optional[str] = None,
        search_after_date: Optional[str] = None,
        search_before_date: Optional[str] = None,
        search_domain_filter: Optional[List[str]] = None,
        use_quality_domains: bool = False,
        model: PerplexityModel = PerplexityModel.SONAR,
        cache_ttl_hours: int = 24,
    ) -> QueryResult:
        """
        Execute a Perplexity search through OpenRouter.

        The `max_tokens_per_page` argument is preserved for backward
        compatibility but is not used by OpenRouter — the model decides
        how much page content to surface.
        """
        # Normalize queries (OpenRouter only takes one prompt; join multi-query)
        if isinstance(query, list):
            query_str = " ".join(query)
        else:
            query_str = query

        cache_params = {
            "max_results": max_results,
            "country": country,
            "recency": search_recency_filter,
            "after": search_after_date,
            "before": search_before_date,
            "domains": search_domain_filter,
            "model": model.value,
        }
        cache_key = self._get_cache_key(query_str, **cache_params)

        if self.enable_cache and cache_key in self.cache:
            entry = self.cache[cache_key]
            if self._is_cache_valid(entry):
                return entry.result

        extra_body = self._build_extra_body(
            max_results=max_results,
            country=country,
            search_recency_filter=search_recency_filter,
            search_after_date=search_after_date,
            search_before_date=search_before_date,
            search_domain_filter=search_domain_filter,
            use_quality_domains=use_quality_domains,
        )

        result = self._execute_with_retry(query_str, model, extra_body)

        if self.enable_cache:
            self.cache[cache_key] = CacheEntry(
                query_hash=cache_key,
                query=query_str,
                result=result,
                timestamp=datetime.now(),
                ttl_hours=cache_ttl_hours,
            )
            self._save_cache()

        return result

    def _execute_with_retry(
        self,
        query: str,
        model: PerplexityModel,
        extra_body: Dict[str, Any],
    ) -> QueryResult:
        """Execute a single OpenRouter request with retry logic."""
        max_retries = RETRY_CONFIG["max_retries"]
        delay = RETRY_CONFIG["initial_delay"]
        max_delay = RETRY_CONFIG["max_delay"]
        backoff = RETRY_CONFIG["backoff_multiplier"]

        payload: Dict[str, Any] = {
            "model": self._openrouter_model_id(model),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a research assistant. Answer the user's query "
                        "concisely using current web information and cite every "
                        "factual claim with a source URL."
                    ),
                },
                {"role": "user", "content": query},
            ],
            "temperature": 0.2,
            **extra_body,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": OPENROUTER_HTTP_REFERER,
            "X-Title": OPENROUTER_APP_TITLE,
        }

        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                self._rate_limit()

                response = self.http.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                results = self._parse_search_results(data)

                usage = data.get("usage") or {}
                input_tokens = int(usage.get("prompt_tokens") or 0)
                output_tokens = int(usage.get("completion_tokens") or 0)
                if not input_tokens and not output_tokens:
                    # Fall back to a rough estimate if OpenRouter omits usage
                    input_tokens = max(1, len(query) // 4)
                    content = self._get_message_content(data)
                    output_tokens = max(1, len(content) // 4)

                cost = self._estimate_cost(model, input_tokens, output_tokens)
                self.total_cost += cost
                self.query_count += 1

                return QueryResult(
                    query=query,
                    model_used=model.value,
                    results=results,
                    result_count=len(results),
                    timestamp=datetime.now(),
                    cost_estimate=cost,
                )

            except Exception as e:  # noqa: BLE001 - retried below
                last_error = e
                if attempt < max_retries - 1:
                    print(f"Retry {attempt + 1}/{max_retries} after error: {e}")
                    time.sleep(delay)
                    delay = min(delay * backoff, max_delay)

        return QueryResult(
            query=query,
            model_used=model.value,
            results=[],
            result_count=0,
            timestamp=datetime.now(),
            cost_estimate=0.0,
            error=str(last_error) if last_error else "Unknown error",
        )

    @staticmethod
    def _get_message_content(data: Dict[str, Any]) -> str:
        """Extract the assistant content from an OpenRouter chat response."""
        try:
            return data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            return ""

    def _parse_search_results(self, data: Dict[str, Any]) -> List[SearchResult]:
        """
        Convert OpenRouter/Perplexity citations into SearchResult records.

        Perplexity surfaces sources in two ways:
        - `choices[0].message.annotations` with type `url_citation` containing
          title, url, and start/end indices into the answer content.
        - A top-level `citations` list of bare URLs.

        We prefer annotations (richer metadata) and fall back to citations.
        """
        content = self._get_message_content(data)
        results: List[SearchResult] = []
        seen_urls: set[str] = set()

        try:
            annotations = data["choices"][0]["message"].get("annotations") or []
        except (KeyError, IndexError, TypeError):
            annotations = []

        for ann in annotations:
            if ann.get("type") != "url_citation":
                continue
            cite = ann.get("url_citation") or {}
            url = cite.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            title = cite.get("title") or url
            start = cite.get("start_index")
            end = cite.get("end_index")
            snippet = ""
            if isinstance(start, int) and isinstance(end, int) and content:
                snippet = content[max(0, start) : min(len(content), end)].strip()
            if not snippet:
                snippet = content[:500].strip()

            results.append(SearchResult(
                title=title,
                url=url,
                snippet=snippet,
                date=cite.get("date"),
                last_updated=cite.get("last_updated"),
            ))

        # Fall back to / supplement with the top-level citations list
        for url in data.get("citations") or []:
            if not isinstance(url, str) or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(SearchResult(
                title=url,
                url=url,
                snippet=content[:500].strip(),
            ))

        # If we still have no citations but do have content, surface the answer
        # itself as a single synthetic "result" so downstream synthesis isn't
        # starved.
        if not results and content:
            results.append(SearchResult(
                title="Perplexity answer",
                url="",
                snippet=content.strip()[:2000],
            ))

        return results

    def search_multi(
        self,
        queries: List[str],
        **kwargs,
    ) -> List[QueryResult]:
        """Execute multiple independent searches sequentially."""
        return [self.search(q, **kwargs) for q in queries]

    def get_cost_summary(self) -> Dict[str, Any]:
        """Get a summary of API usage and costs."""
        return {
            "total_cost": round(self.total_cost, 4),
            "query_count": self.query_count,
            "avg_cost_per_query": round(self.total_cost / max(1, self.query_count), 4),
            "cache_hits": len([e for e in self.cache.values() if self._is_cache_valid(e)]),
        }

    def clear_cache(self) -> None:
        """Clear the query cache."""
        self.cache = {}
        if self.cache_dir:
            cache_file = self.cache_dir / "research_cache.json"
            if cache_file.exists():
                cache_file.unlink()
