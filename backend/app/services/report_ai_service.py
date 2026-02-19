"""
Report AI Service

Generates AI-powered summaries for performance reports using
the user's own AI provider credentials.

Returns three experience-level tiers (beginner, comfortable, experienced)
in a single AI call.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Max tokens for summary generation (3 tiers @ ~300 words each)
MAX_SUMMARY_TOKENS = 2048

# Delimiters used to split the AI response into tiers
_DELIM_BEGINNER = "---BEGINNER---"
_DELIM_COMFORTABLE = "---COMFORTABLE---"
_DELIM_EXPERIENCED = "---EXPERIENCED---"


async def generate_report_summary(
    db: AsyncSession,
    user_id: int,
    report_data: Dict[str, Any],
    period_label: str,
    provider: Optional[str] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Generate an AI summary of the report data.

    Args:
        db: Database session
        user_id: User ID for credential lookup
        report_data: The report metrics dict
        period_label: Human-readable period (e.g. "Jan 1 - Jan 7, 2026")
        provider: Preferred AI provider (claude/openai/gemini), or None for first available

    Returns:
        Tuple of (tiered_summary_dict, provider_used) or (None, None) if no AI available.
        tiered_summary_dict has keys: beginner, comfortable, experienced
    """
    providers_to_try = (
        [provider] if provider else ["claude", "openai", "gemini"]
    )

    for prov in providers_to_try:
        try:
            from app.ai_service import get_ai_client
            client = await get_ai_client(
                provider=prov if prov != "claude" else "anthropic",
                user_id=user_id,
                db=db,
            )
        except (ValueError, Exception) as e:
            logger.warning(f"AI provider {prov} not available: {e}")
            continue

        prompt = _build_summary_prompt(report_data, period_label)

        try:
            raw_text = await _call_ai(client, prov, prompt)
            if raw_text:
                tiered = _parse_tiered_summary(raw_text)
                return tiered, prov
        except Exception as e:
            logger.warning(f"AI summary generation failed with {prov}: {e}")
            continue

    logger.info(f"No AI provider available for user {user_id}, skipping summary")
    return None, None


def _parse_tiered_summary(text: str) -> dict:
    """
    Parse a delimited AI response into three tiers.

    Expected format:
        ---BEGINNER---
        ... beginner text ...
        ---COMFORTABLE---
        ... comfortable text ...
        ---EXPERIENCED---
        ... experienced text ...

    Fallback: if delimiters are not found, the entire response is
    assigned to the 'comfortable' tier.
    """
    has_delimiters = (
        _DELIM_BEGINNER in text
        and _DELIM_COMFORTABLE in text
        and _DELIM_EXPERIENCED in text
    )

    if not has_delimiters:
        return {
            "beginner": None,
            "comfortable": text.strip(),
            "experienced": None,
        }

    parts = {}

    # Split on the three delimiters in order
    after_beginner = text.split(_DELIM_BEGINNER, 1)[1]
    beginner_text, rest = after_beginner.split(_DELIM_COMFORTABLE, 1)
    comfortable_text, experienced_text = rest.split(_DELIM_EXPERIENCED, 1)

    parts["beginner"] = beginner_text.strip() or None
    parts["comfortable"] = comfortable_text.strip() or None
    parts["experienced"] = experienced_text.strip() or None

    return parts


def _build_summary_prompt(data: Dict[str, Any], period_label: str) -> str:
    """Build the prompt for the AI summary."""
    goals_section = ""
    if data.get("goals"):
        goals_lines = []
        for g in data["goals"]:
            status = "on track" if g.get("on_track") else "behind target"
            if g.get("target_type") == "income":
                period = g.get("income_period", "monthly")
                goals_lines.append(
                    f"  - {g['name']} (Income Goal): "
                    f"Target {g['target_value']} {g['target_currency']}/{period}, "
                    f"Linear projection: {g.get('projected_income_linear', 0)}, "
                    f"Compound projection: {g.get('projected_income_compound', 0)}, "
                    f"Daily avg income: {g.get('current_daily_income', 0)}, "
                    f"Based on {g.get('sample_trades', 0)} trades over "
                    f"{g.get('lookback_days_used', 0)} days, "
                    f"{status}"
                )
                dep_lin = g.get("deposit_needed_linear")
                dep_cmp = g.get("deposit_needed_compound")
                if dep_lin is not None or dep_cmp is not None:
                    goals_lines.append(
                        f"    Deposit needed: "
                        f"~{dep_lin} (linear) / ~{dep_cmp} (compound) "
                        f"{g['target_currency']} to reach target"
                    )
            else:
                goals_lines.append(
                    f"  - {g['name']}: {g['progress_pct']}% complete "
                    f"({g['current_value']} / {g['target_value']} "
                    f"{g['target_currency']}), "
                    f"{status}, time elapsed: {g['time_elapsed_pct']}%"
                )
        goals_section = "\nGoal Progress:\n" + "\n".join(goals_lines)

    prior_section = ""
    prior = data.get("prior_period")
    if prior:
        prior_profit = prior.get("period_profit_usd", 0)
        current_profit = data.get("period_profit_usd", 0)
        change = current_profit - prior_profit
        direction = "up" if change >= 0 else "down"
        prior_section = (
            f"\nPrior Period Comparison:"
            f"\n  - Prior period profit: ${prior_profit:,.2f}"
            f"\n  - Current period profit: ${current_profit:,.2f}"
            f"\n  - Change: ${abs(change):,.2f} ({direction})"
            f"\n  - Prior account value: ${prior.get('account_value_usd', 0):,.2f}"
        )

    return f"""You are a trading performance analyst. Analyze this trading report for \
the period: {period_label}.

Report Data:
- Account Value: ${data.get('account_value_usd', 0):,.2f} ({data.get('account_value_btc', 0):.6f} BTC)
- Period Start Value: ${data.get('period_start_value_usd', 0):,.2f}
- Period Profit: ${data.get('period_profit_usd', 0):,.2f} ({data.get('period_profit_btc', 0):.8f} BTC)
- Total Trades: {data.get('total_trades', 0)}
- Win/Loss: {data.get('winning_trades', 0)}W / {data.get('losing_trades', 0)}L
- Win Rate: {data.get('win_rate', 0):.1f}%
{goals_section}{prior_section}

Write THREE versions of a concise 3-5 paragraph summary, separated by the exact \
delimiters shown below. Each version targets a different audience:

{_DELIM_BEGINNER}
(For beginners: use plain language, explain any financial jargon, keep an encouraging \
tone, avoid complex metrics. Focus on "what does this mean for me?")

{_DELIM_COMFORTABLE}
(For comfortable users: data-driven but approachable, highlight key trends, note goal \
progress, suggest 1-2 actionable items. Professional but friendly tone.)

{_DELIM_EXPERIENCED}
(For experienced traders: technical, concise, focus on alpha/risk metrics, win rate \
analysis, period-over-period delta. Skip basic explanations.)

Guidelines for ALL tiers:
- Be factual — do not hallucinate data not provided above
- If income projections or forward-looking estimates are present, include a brief \
disclaimer: past performance does not guarantee future results, projections are \
estimates based on historical data, and actual results may vary
- If there's prior period data, compare and note changes
- Note goal progress and whether the user is on track"""


async def _call_ai(client, provider: str, prompt: str) -> Optional[str]:
    """Call the appropriate AI provider and return the response text."""
    if provider in ("claude", "anthropic"):
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=MAX_SUMMARY_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else None

    elif provider == "openai":
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=MAX_SUMMARY_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content if response.choices else None

    elif provider == "gemini":
        model_instance = client.GenerativeModel("gemini-2.0-flash")
        response = await model_instance.generate_content_async(prompt)
        return response.text if response else None

    return None
