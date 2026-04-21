"""Pricing table + cost estimator for per-call AI cost tracking (Phase F).

Prices are USD per 1,000,000 tokens and are matched against a provider's
SDK model string (e.g. "claude-sonnet-4-20250514"). The matcher is prefix-
based — versioned model IDs from providers change often, and we'd rather
group price points per family than ship a new migration every time a new
dated snapshot drops.

Keep this table loudly explicit (one entry per publicly priced model).
Unknown models fall through to zero cost — better to under-report than to
surface a fabricated number on the dashboard.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# Prices in USD per 1,000,000 tokens: (input, output).
# Source: provider pricing pages as of April 2026. Update alongside any
# default-model change in the adapters.
MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    # Anthropic Claude
    "claude-opus-4-7": (15.00, 75.00),
    "claude-opus-4-5": (15.00, 75.00),
    "claude-opus-4-1": (15.00, 75.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-opus": (15.00, 75.00),
    "claude-3-haiku": (0.25, 1.25),
    # OpenAI GPT
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o1-preview": (15.00, 60.00),
    # Google Gemini
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}

_PRICE_PER_M_TOKENS = 1_000_000.0


def _match_pricing(model: str) -> Optional[Tuple[float, float]]:
    """Look up pricing for a model string.

    Exact match wins. Otherwise pick the longest matching prefix so
    versioned IDs like "claude-sonnet-4-20250514" resolve to the base
    "claude-sonnet-4" row when the dated entry isn't listed.
    """
    if not model:
        return None
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    best_key = None
    for key in MODEL_PRICING:
        if model.startswith(key) and (best_key is None or len(key) > len(best_key)):
            best_key = key
    return MODEL_PRICING[best_key] if best_key else None


def estimate_cost_usd(
    *,
    model: Optional[str],
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Compute USD cost for one call. Returns 0.0 for unknown models.

    Rounded to 6 decimals — more precision than the dashboard needs, fewer
    floating-point drift artefacts when aggregating thousands of rows.
    """
    if not model:
        return 0.0
    pricing = _match_pricing(model)
    if pricing is None:
        return 0.0
    input_rate, output_rate = pricing
    cost = (
        (int(input_tokens or 0) / _PRICE_PER_M_TOKENS) * input_rate
        + (int(output_tokens or 0) / _PRICE_PER_M_TOKENS) * output_rate
    )
    return round(cost, 6)


def provider_for_model(model: Optional[str]) -> Optional[str]:
    """Infer provider slug from a model string.

    Used by the cost-summary endpoint to group rows by provider when the
    ai_model column is missing (legacy rows from before Phase F).
    """
    if not model:
        return None
    m = model.lower()
    if m.startswith("claude"):
        return "claude"
    if m.startswith(("gpt-", "o1")):
        return "gpt"
    if m.startswith("gemini"):
        return "gemini"
    return None
