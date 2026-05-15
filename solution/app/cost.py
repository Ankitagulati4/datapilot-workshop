"""Token + USD cost estimation (Module 10).

We don't have an exact billing API. We use Groq's published pricing for
gpt-oss-20b and approximate token counts via the LangChain message metadata.
Result is a low-precision but real cost signal in the UI.
"""
from __future__ import annotations

# Groq gpt-oss-20b pricing per 1M tokens (USD), as of early 2026.
PRICE_INPUT_PER_M = 0.10
PRICE_OUTPUT_PER_M = 0.50


def estimate_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * PRICE_INPUT_PER_M
        + output_tokens / 1_000_000 * PRICE_OUTPUT_PER_M
    )


def crude_token_count(text: str) -> int:
    """Rough heuristic: ~4 characters per token. Good enough for a badge."""
    return max(1, len(text) // 4)
