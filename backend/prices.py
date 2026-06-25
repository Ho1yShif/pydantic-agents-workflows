"""Dynamic model pricing from pydantic/genai-prices."""

from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml
import logfire


@dataclass
class ModelPrices:
    input_cost_per_m: float   # USD per 1M input tokens
    output_cost_per_m: float  # USD per 1M output tokens


# Global price cache: model_id -> ModelPrices
_prices: dict[str, ModelPrices] = {}

_GITHUB_BASE = (
    "https://raw.githubusercontent.com/pydantic/genai-prices/main/prices/providers"
)
_BUNDLED_DIR = Path(__file__).parent / "prices"

_PROVIDERS = ["openai", "anthropic"]


def _parse_yaml(content: str) -> dict[str, ModelPrices]:
    data = yaml.safe_load(content)
    result: dict[str, ModelPrices] = {}
    for model in data.get("models", []):
        model_id = model.get("id", "")
        p = model.get("prices", {})
        if model_id and "input_mtok" in p:
            result[model_id] = ModelPrices(
                input_cost_per_m=float(p["input_mtok"]),
                output_cost_per_m=float(p.get("output_mtok", 0.0)),
            )
    return result


async def load_prices() -> None:
    """Load prices from GitHub; fall back to bundled YAML files on failure."""
    global _prices

    async with httpx.AsyncClient(timeout=5.0) as client:
        for provider in _PROVIDERS:
            loaded = False

            # Attempt live fetch (both .yml and .yaml extensions)
            for ext in ("yml", "yaml"):
                url = f"{_GITHUB_BASE}/{provider}.{ext}"
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    new = _parse_yaml(resp.text)
                    _prices.update(new)
                    logfire.info(
                        "Loaded model prices from GitHub",
                        provider=provider,
                        count=len(new),
                        source=url,
                    )
                    loaded = True
                    break
                except Exception as exc:
                    logfire.debug(
                        "GitHub price fetch failed",
                        provider=provider,
                        url=url,
                        error=str(exc),
                    )

            # Fall back to bundled files if live fetch failed
            if not loaded:
                for bundled in sorted(_BUNDLED_DIR.glob(f"{provider}_*.yml")):
                    try:
                        new = _parse_yaml(bundled.read_text())
                        _prices.update(new)
                        logfire.info(
                            "Loaded model prices from bundled file",
                            provider=provider,
                            count=len(new),
                            source=bundled.name,
                        )
                        loaded = True
                        break
                    except Exception as exc:
                        logfire.warning(
                            "Failed to load bundled price file",
                            file=str(bundled),
                            error=str(exc),
                        )

            if not loaded:
                logfire.warning("No price data loaded for provider", provider=provider)


def get_price(model_id: str) -> ModelPrices:
    """Return pricing for *model_id*, using fuzzy matching as a fallback."""
    # 1. Exact match
    if model_id in _prices:
        return _prices[model_id]

    # 2. model_id is a prefix of a stored ID (e.g. "claude-sonnet-4-6" matches
    #    "claude-sonnet-4-6-20251114")
    for stored_id, price in _prices.items():
        if stored_id.startswith(model_id) or model_id.startswith(stored_id):
            return price

    # 3. Substring containment
    for stored_id, price in _prices.items():
        if stored_id in model_id or model_id in stored_id:
            return price

    # 4. Hard-coded sensible defaults so cost calculations never crash
    logfire.warning("No price data found for model, using defaults", model_id=model_id)
    return ModelPrices(input_cost_per_m=3.0, output_cost_per_m=15.0)
