"""
Perplexity API client wrapper (via OpenRouter) with retry logic and rate limiting.

Routes Perplexity sonar models through OpenRouter's OpenAI-compatible chat
completions endpoint. The native Perplexity Search API returns structured
per-result objects; OpenRouter returns one synthesized answer plus citations,
so this client adapts that response into the project's existing
QueryResult / SearchResult schema.
"""

import os
import time
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from urllib.parse import urlparse

from openai import OpenAI

from ..config import (
    RETRY_CONFIG,
    PERPLEXITY_COSTS,
    PerplexityModel,
    QUALITY_DOMAINS,
)
from ..models import SearchResult, QueryResult


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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
    Wrapper for Perplexity sonar models via OpenRouter.

    Features:
    - OpenAI-compatible chat completions through OpenRouter
    - Automatic retry with exponential backoff
    - Query result caching
    - Cost estimation and tracking
    - Rate limiting
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        enable_cache: bool = True,
    ):
        """
        Initialize the Perplexity client.

        Args:
            api_key: OpenRouter API key. If not provided, uses OPENROUTER_API_KEY env var.
            cache_dir: Directory for caching query results.
            enable_cache: Whether to enable result caching.
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment variables")

        self.client = OpenAI(api_key=self.api_key, base_url=OPENROUTER_BASE_URL)
        self.enable_cache = enable_cache
        self.cache_dir = cache_dir
        self.cache: Dict[str, CacheEntry] = {}

        # Cost tracking
        self.total_cost = 0.0
        self.query_count = 0

        # Rate limiting
        self.last_request_time = 0.0
        self.min_request_interval = 1.0  # seconds between requests

        if self.cache_dir and self.enable_cache:
            self._load_cache()

    # ------------------------------------------------------------------ cache

    def _get_cache_key(self, query: str, **params) -> str:
        cache_data = {"query": query, **params}
        cache_str = json.dumps(cache_data, sort_keys=True, default=str)
        return hashlib.md5(cache_str.encode()).hexdigest()

    def _load_cache(self) -> None:
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
        age_hours = (datetime.now() - entry.timestamp).total_seconds() / 3600
        return age_hours < entry.ttl_hours

    # --------------------------------------------------------- rate / cost

    def _rate_limit(self) -> None:
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _estimate_cost(
        self,
        model: PerplexityModel,
        input_tokens: int = 500,
        output_tokens: int = 1000,
    ) -> float:
        """Fallback token-based cost estimate. Does not include search-request
        fees or reasoning tokens — use _cost_from_response to read the real
        billed cost from OpenRouter when available."""
        input_cost, output_cost = PERPLEXITY_COSTS.get(model, (0.001, 0.001))
        return (input_tokens / 1000 * input_cost) + (output_tokens / 1000 * output_cost)

    def _cost_from_response(self, response: Any, model: PerplexityModel) -> float:
        """
        Read the real billed cost from an OpenRouter response.

        With `extra_body={"usage": {"include": True}}`, OpenRouter returns a
        `cost` field on the usage object (USD). That number includes every
        surcharge OpenRouter passes through — input/output tokens, reasoning
        tokens for reasoning models, and per-request search fees for sonar
        models — so it matches the dashboard.

        Falls back to the token-based estimate if the field is absent.
        """
        usage = getattr(response, "usage", None)
        if usage is not None:
            real_cost = getattr(usage, "cost", None)
            if real_cost is None and hasattr(usage, "model_dump"):
                real_cost = usage.model_dump().get("cost")
            if isinstance(real_cost, (int, float)) and real_cost > 0:
                return float(real_cost)

            # Estimate fallback using whatever token counts we have.
            prompt_tokens = getattr(usage, "prompt_tokens", None) or 500
            completion_tokens = getattr(usage, "completion_tokens", None) or 1000
            return self._estimate_cost(model, prompt_tokens, completion_tokens)

        return self._estimate_cost(model)

    @staticmethod
    def _to_openrouter_model_id(model: PerplexityModel) -> str:
        """Map PerplexityModel enum to OpenRouter model id ('perplexity/sonar' etc.)."""
        return f"perplexity/{model.value}"

    # ------------------------------------------------ response → SearchResult

    def _parse_response_to_results(
        self,
        response: Any,
        max_results: int,
    ) -> List[SearchResult]:
        """
        Convert an OpenRouter Perplexity chat-completion response into a list
        of SearchResult objects compatible with the rest of the pipeline.

        The OpenRouter response shape (for Perplexity sonar models):
          - response.choices[0].message.content          # synthesized answer text
          - response.choices[0].message.annotations      # optional, list of
              { "type": "url_citation",
                "url_citation": {"url": ..., "title": ..., "content": ...} }
          - response.citations                           # optional, list of URL strings

        Downstream code (result_processor.py) does substring matching on
        `result.snippet.lower()` to pull facts (location, funding, etc.) out of
        the research, and aggregates `result.url` into source lists. So
        EVERY returned SearchResult must have:
          - a non-empty `url`
          - a `snippet` rich enough that keyword matching can find facts
          - a `title` (URL host is an acceptable fallback)

        Strategy: annotations-first, with citation fallback.
        """
        message = response.choices[0].message
        answer = message.content or ""

        annotations = getattr(message, "annotations", None) or []
        out: List[SearchResult] = []

        for a in annotations[:max_results]:
            # SDK may return either a dict or a Pydantic-like object
            citation = a.get("url_citation") if isinstance(a, dict) else getattr(a, "url_citation", None)
            if citation is None:
                continue
            if not isinstance(citation, dict):
                citation = citation.model_dump() if hasattr(citation, "model_dump") else dict(citation)

            url = citation.get("url")
            if not url:
                continue
            out.append(SearchResult(
                title=citation.get("title") or url,
                url=url,
                snippet=citation.get("content") or answer,
            ))

        if not out:
            citations = getattr(response, "citations", None) or []
            for url in citations[:max_results]:
                if not url:
                    continue
                out.append(SearchResult(
                    title=urlparse(url).netloc or url,
                    url=url,
                    snippet=answer,
                ))

        return out

    # --------------------------------------------------------------- search

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
        Execute a Perplexity search query (via OpenRouter chat completion) with retries.
        """
        # Coerce list-of-queries into a single combined query for OpenRouter
        # (the native Perplexity SDK supported up to 5 parallel queries; OpenRouter
        # chat completions expect one prompt, so we join them).
        if isinstance(query, list):
            query_str = "\n".join(f"- {q}" for q in query)
            user_prompt = "Please research the following topics and answer each:\n" + query_str
        else:
            query_str = query
            user_prompt = query

        # Build cache key (same shape as before so existing caches load cleanly)
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

        # Build web_search_options for Perplexity-on-OpenRouter
        web_search_options: Dict[str, Any] = {}
        if search_recency_filter:
            web_search_options["search_recency_filter"] = search_recency_filter
        if search_after_date:
            web_search_options["search_after_date_filter"] = search_after_date
        if search_before_date:
            web_search_options["search_before_date_filter"] = search_before_date
        if country:
            web_search_options["user_location"] = {"country": country}

        if use_quality_domains and not search_domain_filter:
            web_search_options["search_domain_filter"] = QUALITY_DOMAINS[:20]
        elif search_domain_filter:
            web_search_options["search_domain_filter"] = search_domain_filter[:20]

        # Always ask OpenRouter to include real cost in the response.
        extra_body: Dict[str, Any] = {"usage": {"include": True}}
        if web_search_options:
            extra_body["web_search_options"] = web_search_options

        result = self._execute_with_retry(
            user_prompt=user_prompt,
            query_str=query_str,
            model=model,
            max_results=max_results,
            extra_body=extra_body,
        )

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
        user_prompt: str,
        query_str: str,
        model: PerplexityModel,
        max_results: int,
        extra_body: Dict[str, Any],
    ) -> QueryResult:
        max_retries = RETRY_CONFIG["max_retries"]
        delay = RETRY_CONFIG["initial_delay"]
        max_delay = RETRY_CONFIG["max_delay"]
        backoff = RETRY_CONFIG["backoff_multiplier"]

        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                self._rate_limit()

                response = self.client.chat.completions.create(
                    model=self._to_openrouter_model_id(model),
                    messages=[{"role": "user", "content": user_prompt}],
                    extra_body=extra_body or None,
                )

                results = self._parse_response_to_results(response, max_results)

                # Prefer OpenRouter's actual cost (includes search fees and
                # reasoning tokens). Fall back to token-based estimate if the
                # cost field is missing.
                cost = self._cost_from_response(response, model)

                self.total_cost += cost
                self.query_count += 1

                return QueryResult(
                    query=query_str,
                    model_used=model.value,
                    results=results,
                    result_count=len(results),
                    timestamp=datetime.now(),
                    cost_estimate=cost,
                )

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    print(f"Retry {attempt + 1}/{max_retries} after error: {e}")
                    time.sleep(delay)
                    delay = min(delay * backoff, max_delay)

        return QueryResult(
            query=query_str,
            model_used=model.value,
            results=[],
            result_count=0,
            timestamp=datetime.now(),
            cost_estimate=0.0,
            error=str(last_error),
        )

    def search_multi(
        self,
        queries: List[str],
        **kwargs,
    ) -> List[QueryResult]:
        """Execute multiple independent searches sequentially."""
        return [self.search(q, **kwargs) for q in queries]

    def get_cost_summary(self) -> Dict[str, Any]:
        """Summary of API usage and costs."""
        return {
            "total_cost": round(self.total_cost, 4),
            "query_count": self.query_count,
            "avg_cost_per_query": round(
                self.total_cost / max(1, self.query_count), 4
            ),
        }
