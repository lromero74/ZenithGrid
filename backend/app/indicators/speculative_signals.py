"""
Speculative Setup Scorer.

Quantitative scoring of catalyst-hunt setups for the high-risk-doubling
preset. Runs BEFORE the LLM call and is injected into the prompt as
pre-computed context — the AI reasons over this audited scaffold rather
than freelancing the full analysis.

Each weight component fires (yes/no) based on thresholds against inputs
from AISpotOpinionEvaluator._calculate_metrics and BTC reference metrics.
Fired components contribute their full weight; unfired contribute 0.
The sum of WEIGHTS is exactly 100, so the returned score is bounded [0, 100].

Design intent (per PRPs/high-risk-doubling-preset.md §Recommended Design §4):
- Calibratable: each component's contribution is logged separately to
  ai_opinion_log so speculative_calibration_monitor can later compare
  per-component win rates and propose weight adjustments.
- Deterministic / testable: given the same inputs the score is identical.
- Not a gate: a high score does not auto-trigger a buy. It is a hint
  to the LLM, which still makes the final call.

Initial weights are educated guesses. They are expected to change after
enough ai_opinion_log outcomes accumulate — see Phase F for the alert
loop that notifies the owner when it is time to recalibrate.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Default component weights. Used when a user has never applied a
# calibration proposal. Once a user applies a proposal via the auto-tuner
# (speculative_weights_auto_calibration feature), their effective weights
# come from that row via app.services.speculative_weights_cache.
#
# Sum MUST equal 100 so the returned score is a clean percentage.
DEFAULT_WEIGHTS: Dict[str, int] = {
    "volume_surge":          25,   # abnormal volume vs 30d baseline
    "compression_breakout":  20,   # range expansion after tight coil
    "momentum_accelerating": 20,   # positive hourly momentum accelerating
    "micro_mid_cap":         10,   # favors smaller / newer listings
    "correlation_break":     10,   # coin moves idiosyncratically vs BTC
    "volume_vs_mcap":        15,   # high turnover = "in play"
}

assert sum(DEFAULT_WEIGHTS.values()) == 100, "DEFAULT_WEIGHTS must sum to 100"

# Back-compat alias for code that imports WEIGHTS directly. Safe because
# it's a reference to the same dict; no callers mutate it.
WEIGHTS = DEFAULT_WEIGHTS


# Thresholds per component. Kept at the top of the file so a future
# calibration session (Phase F) only has to tune these numbers.
_VOLUME_SURGE_RATIO_MIN = 3.0
_COMPRESSION_RATIO_MIN = 3.0
_COMPRESSION_REQUIRES_POSITIVE_MOMENTUM = True
_MOMENTUM_ACCELERATION_MIN = 0.0      # must be > 0
_MOMENTUM_1H_MIN_PCT = 2.0
_CORRELATION_BREAK_DELTA_MIN_PCT = 3.0
_VOLUME_VS_MCAP_TURNOVER_MIN = 0.05   # 5% of market cap traded in 24h
_MICRO_MID_CAP_LISTING_AGE_DAYS_MAX = 90


def _fires_volume_surge(metrics: Dict[str, Any]) -> bool:
    ratio = metrics.get("volume_30d_ratio")
    return ratio is not None and ratio >= _VOLUME_SURGE_RATIO_MIN


def _fires_compression_breakout(metrics: Dict[str, Any]) -> bool:
    ratio = metrics.get("compression_ratio")
    mom1h = metrics.get("momentum_1h")
    if ratio is None or ratio < _COMPRESSION_RATIO_MIN:
        return False
    if _COMPRESSION_REQUIRES_POSITIVE_MOMENTUM and (mom1h is None or mom1h <= 0):
        return False
    return True


def _fires_momentum_accelerating(metrics: Dict[str, Any]) -> bool:
    accel = metrics.get("momentum_acceleration")
    mom1h = metrics.get("momentum_1h")
    if accel is None or accel <= _MOMENTUM_ACCELERATION_MIN:
        return False
    if mom1h is None or mom1h < _MOMENTUM_1H_MIN_PCT:
        return False
    return True


def _fires_micro_mid_cap(metrics: Dict[str, Any]) -> bool:
    """Proxy for small cap: either listed recently, or base currency is
    not in a user-supplied 'major cap' set. We don't have authoritative
    market-cap data, so both are best-effort heuristics.
    """
    age_days = metrics.get("listing_age_days")
    if age_days is not None and age_days <= _MICRO_MID_CAP_LISTING_AGE_DAYS_MAX:
        return True
    is_major = metrics.get("is_major_cap")
    if is_major is False:
        return True
    return False


def _fires_correlation_break(metrics: Dict[str, Any],
                             btc_metrics: Optional[Dict[str, Any]]) -> bool:
    if not btc_metrics:
        return False
    mom = metrics.get("momentum_1h")
    btc_mom = btc_metrics.get("momentum_1h")
    if mom is None or btc_mom is None:
        return False
    return abs(mom - btc_mom) >= _CORRELATION_BREAK_DELTA_MIN_PCT


def _fires_volume_vs_mcap(metrics: Dict[str, Any]) -> bool:
    turnover = metrics.get("turnover_ratio_24h")
    if turnover is None:
        return False
    return turnover >= _VOLUME_VS_MCAP_TURNOVER_MIN


_COMPONENT_EVALUATORS = (
    ("volume_surge",          _fires_volume_surge),
    ("compression_breakout",  _fires_compression_breakout),
    ("momentum_accelerating", _fires_momentum_accelerating),
    ("micro_mid_cap",         _fires_micro_mid_cap),
    ("correlation_break",     _fires_correlation_break),
    ("volume_vs_mcap",        _fires_volume_vs_mcap),
)


def score_speculative_setup(
    metrics: Dict[str, Any],
    btc_metrics: Optional[Dict[str, Any]] = None,
    product_id: str = "",
    weights: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Score a catalyst-hunt setup on a 0-100 scale.

    Args:
        metrics: Output of AISpotOpinionEvaluator._calculate_metrics plus
            optional micro-cap hints (listing_age_days, is_major_cap) and
            turnover_ratio_24h. Missing keys cause the corresponding
            component not to fire (contribution=0).
        btc_metrics: Optional BTC reference metrics with at minimum
            {'momentum_1h': float}. Used by correlation_break only.
        product_id: Trading pair — passed through for logging.
        weights: Override component weights. When None, DEFAULT_WEIGHTS
            applies. Used by the auto-calibration pipeline to pass a
            user's calibrated weights in place of the defaults.

    Returns:
        {
            "score": int 0-100,
            "components": {
                "volume_surge":          {"fired": bool, "contribution": int},
                ... one per DEFAULT_WEIGHTS key ...
            },
        }

    Safe to call with empty metrics — returns score=0 and all components
    not-fired without raising.
    """
    if not isinstance(metrics, dict):
        metrics = {}

    effective_weights = weights if weights is not None else DEFAULT_WEIGHTS
    components: Dict[str, Dict[str, Any]] = {}
    total = 0

    for name, evaluator in _COMPONENT_EVALUATORS:
        weight = effective_weights.get(name, DEFAULT_WEIGHTS[name])
        try:
            if name == "correlation_break":
                fired = evaluator(metrics, btc_metrics)
            else:
                fired = evaluator(metrics)
        except Exception:
            logger.exception(
                "speculative_signals: component %s raised on %s — treating as not fired",
                name, product_id,
            )
            fired = False
        contribution = weight if fired else 0
        components[name] = {"fired": bool(fired), "contribution": contribution}
        total += contribution

    # Defensive clamp — the invariant sum(WEIGHTS)==100 should make this
    # unreachable, but return type contract is stricter than code intent.
    total = max(0, min(100, total))

    return {"score": total, "components": components}


def summarize_components_for_prompt(result: Dict[str, Any]) -> str:
    """Render a scorer result as a short block suitable for the AI prompt.

    Returns a multi-line string (no trailing newline). Non-fired components
    are omitted to keep prompts tight.
    """
    score = result.get("score", 0)
    components = result.get("components", {})
    fired = [(name, c["contribution"]) for name, c in components.items()
             if c.get("fired")]
    if not fired:
        return f"Speculative setup score: {score}/100 — no components fired."
    fired.sort(key=lambda x: -x[1])
    lines = [f"Speculative setup score: {score}/100"]
    lines.append("Components fired:")
    for name, contribution in fired:
        lines.append(f"  - {name} (+{contribution})")
    return "\n".join(lines)


def components_for_log(result: Dict[str, Any]) -> list:
    """Compact list form for ai_opinion_log persistence.

    [(name, fired, contribution), ...] — deterministic order so later
    calibration queries can GROUP BY name consistently.
    """
    components = result.get("components", {})
    return [(name, components[name]["fired"], components[name]["contribution"])
            for name, _ in _COMPONENT_EVALUATORS
            if name in components]
