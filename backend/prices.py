"""Model pricing via the official ``genai-prices`` package.

We previously fetched and parsed the raw genai-prices YAML ourselves, which broke
on tiered/constraint-based price schemas and made a network call on every task.
The package ships auto-updated price data bundled for fully offline use, so cost
calculation is a single in-process lookup with no network dependency.
"""

import logfire
from genai_prices import Usage, calc_price

# Fallback rate (USD per 1M tokens) used only when genai-prices cannot price a
# model id — e.g. a brand-new model not yet in the bundled data. Keeps cost
# tracking from ever crashing a pipeline stage.
_FALLBACK_INPUT_PER_M = 3.0
_FALLBACK_OUTPUT_PER_M = 15.0


def model_cost(input_tokens: int, output_tokens: int, model: str, provider_id: str) -> float:
    """USD cost for a call, via genai-prices bundled data (offline, no network)."""
    try:
        price = calc_price(
            Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            model_ref=model,
            provider_id=provider_id,
        )
        return float(price.total_price)
    except Exception as exc:
        logfire.warning(
            "genai-prices lookup failed; using fallback rate",
            model=model,
            provider_id=provider_id,
            error=str(exc),
        )
        return (input_tokens / 1_000_000) * _FALLBACK_INPUT_PER_M + (
            output_tokens / 1_000_000
        ) * _FALLBACK_OUTPUT_PER_M
