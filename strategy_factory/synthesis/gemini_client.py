"""
Gemini synthesis client backed by OpenRouter.

Routes Gemini chat completion calls through OpenRouter's OpenAI-compatible API
while preserving the SynthesisResult interface used by the synthesis pipeline.
"""

import os
import time
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass

import httpx

from ..config import (
    GEMINI_MODEL,
    GEMINI_REQUEST_DELAY,
    RETRY_CONFIG,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_APP_TITLE,
)


@dataclass
class SynthesisResult:
    """Result of a synthesis request."""
    content: str
    model_used: str
    timestamp: datetime
    prompt_tokens: int
    completion_tokens: int
    cost_estimate: float
    error: Optional[str] = None


class GeminiClient:
    """
    OpenRouter-backed wrapper for Google Gemini models.

    Features:
    - Automatic retry with exponential backoff
    - Cost estimation and tracking
    - Rate limiting
    - Token counting (from OpenRouter usage where available)
    """

    # Gemini 2.5 Flash pricing on OpenRouter (per 1M tokens, USD)
    COST_PER_1M_INPUT = 0.075
    COST_PER_1M_OUTPUT = 0.30

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = GEMINI_MODEL,
    ):
        """
        Initialize the Gemini client.

        Args:
            api_key: OpenRouter API key. If not provided, uses OPENROUTER_API_KEY env var.
            model_name: OpenRouter model ID (e.g. "google/gemini-2.5-flash").
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment variables")

        self.base_url = OPENROUTER_BASE_URL
        self.model_name = model_name
        self.http = httpx.Client(timeout=300.0)

        # Cost tracking
        self.total_cost = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.request_count = 0

        # Rate limiting
        self.last_request_time = 0.0
        self.min_request_interval = GEMINI_REQUEST_DELAY

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate the cost of a request."""
        input_cost = (input_tokens / 1_000_000) * self.COST_PER_1M_INPUT
        output_cost = (output_tokens / 1_000_000) * self.COST_PER_1M_OUTPUT
        return input_cost + output_cost

    def _count_tokens(self, text: str) -> int:
        """Rough token estimate (~4 chars/token)."""
        return len(text) // 4

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
    ) -> SynthesisResult:
        """
        Generate content using Gemini via OpenRouter.
        """
        max_retries = RETRY_CONFIG["max_retries"]
        delay = RETRY_CONFIG["initial_delay"]
        max_delay = RETRY_CONFIG["max_delay"]
        backoff = RETRY_CONFIG["backoff_multiplier"]

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
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

                try:
                    content = data["choices"][0]["message"].get("content") or ""
                except (KeyError, IndexError, TypeError) as e:
                    raise RuntimeError(f"Malformed OpenRouter response: {data}") from e

                usage = data.get("usage") or {}
                input_tokens = int(usage.get("prompt_tokens") or 0)
                output_tokens = int(usage.get("completion_tokens") or 0)
                if not input_tokens:
                    input_tokens = self._count_tokens(prompt)
                    if system_instruction:
                        input_tokens += self._count_tokens(system_instruction)
                if not output_tokens:
                    output_tokens = self._count_tokens(content)

                cost = self._estimate_cost(input_tokens, output_tokens)

                self.total_cost += cost
                self.total_input_tokens += input_tokens
                self.total_output_tokens += output_tokens
                self.request_count += 1

                return SynthesisResult(
                    content=content,
                    model_used=self.model_name,
                    timestamp=datetime.now(),
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    cost_estimate=cost,
                )

            except Exception as e:  # noqa: BLE001 - retried below
                last_error = e
                if attempt < max_retries - 1:
                    print(f"Retry {attempt + 1}/{max_retries} after error: {e}")
                    time.sleep(delay)
                    delay = min(delay * backoff, max_delay)

        return SynthesisResult(
            content="",
            model_used=self.model_name,
            timestamp=datetime.now(),
            prompt_tokens=0,
            completion_tokens=0,
            cost_estimate=0.0,
            error=str(last_error) if last_error else "Unknown error",
        )

    def generate_with_context(
        self,
        prompt: str,
        context: Dict[str, Any],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
    ) -> SynthesisResult:
        """
        Generate content with structured context substituted into the prompt.
        """
        formatted_prompt = prompt
        for key, value in context.items():
            placeholder = f"{{{key}}}"
            if placeholder in formatted_prompt:
                formatted_prompt = formatted_prompt.replace(placeholder, str(value))

        return self.generate(
            prompt=formatted_prompt,
            system_instruction=system_instruction,
            temperature=temperature,
        )

    def _fix_malformed_tables(self, content: str) -> str:
        """Fix malformed markdown tables with overly long separator rows."""
        import re
        lines = content.split('\n')
        fixed_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            if line.count('|') >= 2 and not re.match(r'^\s*\|[\s\-:]+\|', line):
                cols = [c.strip() for c in line.split('|')]
                cols = [c for c in cols if c]
                num_cols = len(cols)

                if num_cols >= 2:
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        if len(next_line) > 200 and '-' in next_line:
                            separator = '|' + '|'.join([' --- ' for _ in range(num_cols)]) + '|'
                            fixed_lines.append(line)
                            fixed_lines.append(separator)
                            i += 2
                            continue

            if len(line) > 500:
                i += 1
                continue

            fixed_lines.append(line)
            i += 1

        return '\n'.join(fixed_lines)

    def generate_markdown(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> SynthesisResult:
        """Generate markdown content with consistent formatting guidance."""
        markdown_instruction = """
You are generating professional consulting documentation in Markdown format.
Follow these formatting guidelines:
- Use proper heading hierarchy (# for title, ## for sections, ### for subsections)
- Use bullet points and numbered lists for clarity
- Include tables where appropriate using markdown syntax
- CRITICAL: For markdown tables, each row must be on a single line. Table separator row must only have dashes like |---|---|---|
- Use **bold** for emphasis and `code` for technical terms
- Keep paragraphs concise and actionable
- Do not include ```markdown``` code fences around the output
"""

        full_instruction = markdown_instruction
        if system_instruction:
            full_instruction = f"{markdown_instruction}\n\n{system_instruction}"

        result = self.generate(
            prompt=prompt,
            system_instruction=full_instruction,
            temperature=0.5,
        )

        if result.content:
            result.content = self._fix_malformed_tables(result.content)

        return result

    def get_cost_summary(self) -> Dict[str, Any]:
        """Get a summary of API usage and costs."""
        return {
            "total_cost": round(self.total_cost, 4),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "request_count": self.request_count,
            "avg_cost_per_request": round(
                self.total_cost / max(1, self.request_count), 4
            ),
        }
