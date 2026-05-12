"""
Gemini API client wrapper (via OpenRouter) with retry logic.

Routes Gemini calls through OpenRouter's OpenAI-compatible endpoint so the
project only needs a single OPENROUTER_API_KEY. Preserves the SynthesisResult
contract so the rest of the synthesis pipeline is unchanged.
"""

import os
import time
from datetime import datetime
from typing import Any, Dict, Optional
from dataclasses import dataclass

from openai import OpenAI

from ..config import GEMINI_MODEL, GEMINI_REQUEST_DELAY, RETRY_CONFIG


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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
    Wrapper for Gemini (via OpenRouter) with retry logic.

    Features:
    - OpenAI-compatible chat completions through OpenRouter
    - Automatic retry with exponential backoff
    - Cost estimation and tracking
    - Rate limiting
    - Token counting
    """

    # Gemini 2.5 Flash pricing through OpenRouter (per 1M tokens, USD).
    # OpenRouter passes through provider pricing with no markup for direct routes.
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
            model_name: Model to use for synthesis (config GEMINI_MODEL is the bare
                model id; we prefix with the OpenRouter provider slug here).
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment variables")

        self.client = OpenAI(api_key=self.api_key, base_url=OPENROUTER_BASE_URL)
        self.model_name = self._to_openrouter_model_id(model_name)

        # Cost tracking
        self.total_cost = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.request_count = 0

        # Rate limiting
        self.last_request_time = 0.0
        self.min_request_interval = GEMINI_REQUEST_DELAY

    @staticmethod
    def _to_openrouter_model_id(model_name: str) -> str:
        """Map bare Gemini ids (e.g. 'gemini-2.5-flash') to OpenRouter ids ('google/gemini-2.5-flash')."""
        if "/" in model_name:
            return model_name
        return f"google/{model_name}"

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
        """Rough token estimate when the API does not return usage."""
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

        Args:
            prompt: The prompt to send.
            system_instruction: Optional system instruction.
            temperature: Sampling temperature (0-1).
            max_output_tokens: Maximum tokens in response.

        Returns:
            SynthesisResult with generated content.
        """
        max_retries = RETRY_CONFIG["max_retries"]
        delay = RETRY_CONFIG["initial_delay"]
        max_delay = RETRY_CONFIG["max_delay"]
        backoff = RETRY_CONFIG["backoff_multiplier"]

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        last_error = None

        for attempt in range(max_retries):
            try:
                self._rate_limit()

                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_output_tokens,
                )

                content = response.choices[0].message.content or ""

                # Prefer real token usage from the API; fall back to estimate.
                usage = getattr(response, "usage", None)
                if usage and getattr(usage, "prompt_tokens", None):
                    input_tokens = usage.prompt_tokens
                    output_tokens = usage.completion_tokens or self._count_tokens(content)
                else:
                    input_tokens = self._count_tokens(prompt)
                    if system_instruction:
                        input_tokens += self._count_tokens(system_instruction)
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

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    print(f"Retry {attempt + 1}/{max_retries} after error: {e}")
                    time.sleep(delay)
                    delay = min(delay * backoff, max_delay)

        # All retries failed
        return SynthesisResult(
            content="",
            model_used=self.model_name,
            timestamp=datetime.now(),
            prompt_tokens=0,
            completion_tokens=0,
            cost_estimate=0.0,
            error=str(last_error),
        )

    def generate_with_context(
        self,
        prompt: str,
        context: dict,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
    ) -> SynthesisResult:
        """Generate content with a context dict formatted into the prompt template."""
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

                if num_cols >= 2 and i + 1 < len(lines):
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
        """
        Generate markdown content, with formatting guidance and table post-processing.
        """
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
        """Summary of API usage and costs."""
        return {
            "total_cost": round(self.total_cost, 4),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "request_count": self.request_count,
            "avg_cost_per_request": round(
                self.total_cost / max(1, self.request_count), 4
            ),
        }
