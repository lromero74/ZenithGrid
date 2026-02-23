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

# Max tokens for summary generation (3 tiers with structured markdown sections)
MAX_SUMMARY_TOKENS = 4096

# System message for all AI providers — sets the role and output format
_SYSTEM_MESSAGE = (
    "You are a trading performance analyst writing structured report summaries. "
    "Format your output using markdown: ### for section headers, **bold** for key "
    "figures, - for bullet lists. Every summary MUST include these sections in order: "
    "### Performance Overview, ### Goal Progress (if goal data is present), "
    "### Capital Movements (if deposit/withdrawal data is present), "
    "### Outlook & Action Items. Keep each section concise (2-4 sentences or a short "
    "bullet list). Be factual — never invent data not provided."
)

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
            elif g.get("target_type") == "expenses":
                coverage = g.get("expense_coverage", {})
                exp_period = g.get("expense_period", "monthly")
                cov_pct = coverage.get("coverage_pct", 0)
                total_exp = coverage.get("total_expenses", 0)
                income_at = coverage.get("income_after_tax", 0)
                covered_n = coverage.get("covered_count", 0)
                total_n = coverage.get("total_count", 0)
                goals_lines.append(
                    f"  - {g['name']} (Expenses Goal): "
                    f"Total expenses: {total_exp} {g['target_currency']}/{exp_period}, "
                    f"Income after tax: {income_at}, "
                    f"Coverage: {cov_pct:.0f}% ({covered_n}/{total_n} items covered), "
                    f"Based on {g.get('sample_trades', 0)} trades over "
                    f"{g.get('lookback_days_used', 0)} days"
                )
                partial_name = coverage.get("partial_item_name")
                partial_short = coverage.get("partial_item_shortfall")
                next_name = coverage.get("next_uncovered_name")
                next_amt = coverage.get("next_uncovered_amount")
                if partial_name and partial_short:
                    goals_lines.append(
                        f"    Partially covered: {partial_name} "
                        f"(needs ~{partial_short} more {g['target_currency']})"
                    )
                if next_name and next_amt:
                    goals_lines.append(
                        f"    Next uncovered: {next_name} "
                        f"(~{next_amt} {g['target_currency']})"
                    )
                dep = g.get("deposit_needed")
                if dep is not None:
                    goals_lines.append(
                        f"    Total deposit needed: "
                        f"~{dep} {g['target_currency']}"
                    )
            else:
                goals_lines.append(
                    f"  - {g['name']}: {g['progress_pct']}% complete "
                    f"({g['current_value']} / {g['target_value']} "
                    f"{g['target_currency']}), "
                    f"{status}, time elapsed: {g['time_elapsed_pct']}%"
                )
        goals_section = "\nGoal Progress:\n" + "\n".join(goals_lines)

    capital_section = ""
    net_deposits = data.get("net_deposits_usd", 0)
    if net_deposits != 0:
        total_dep = data.get("total_deposits_usd", 0)
        total_wth = data.get("total_withdrawals_usd", 0)
        adj_growth = data.get("adjusted_account_growth_usd", 0)
        capital_section = (
            f"\nCapital Movements:"
            f"\n  - Net deposits in period: ${net_deposits:,.2f}"
            f"\n  - Adjusted account growth (excluding deposits): "
            f"${adj_growth:,.2f}"
            f"\n  - Total deposits: ${total_dep:,.2f} / "
            f"Total withdrawals: ${total_wth:,.2f}"
        )

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

    return f"""Analyze this trading report for the period: {period_label}.

Report Data:
- Account Value: ${data.get('account_value_usd', 0):,.2f} ({data.get('account_value_btc', 0):.6f} BTC)
- Period Start Value: ${data.get('period_start_value_usd', 0):,.2f}
- Period Profit: ${data.get('period_profit_usd', 0):,.2f} ({data.get('period_profit_btc', 0):.8f} BTC)
- Total Trades: {data.get('total_trades', 0)}
- Win/Loss: {data.get('winning_trades', 0)}W / {data.get('losing_trades', 0)}L
- Win Rate: {data.get('win_rate', 0):.1f}%
{goals_section}{capital_section}{prior_section}

Write THREE versions separated by the exact delimiters below. All versions MUST use \
the same section structure (### headers in order), but pitched for different audiences.

Formatting rules (apply to ALL tiers):
- Use ### for section headers (### Performance Overview, ### Goal Progress, etc.)
- Use **bold** for key figures and important numbers
- Use - bullet lists for action items in the Outlook section
- Keep each section concise: 2-4 sentences or a short bullet list
- Only include ### Goal Progress if goal data is present above
- Only include ### Capital Movements if deposit/withdrawal data is present above

{_DELIM_BEGINNER}
(For beginners: plain language, explain jargon, encouraging tone. Focus on \
"what does this mean for me?" Use a few approachable symbols at section headers \
for visual warmth — not childish or overloaded, just welcoming.)

{_DELIM_COMFORTABLE}
(For comfortable users: data-driven but approachable, highlight key trends, note \
goal progress, suggest 1-2 actionable items. Professional but friendly. Light use \
of symbols at section headers only.)

{_DELIM_EXPERIENCED}
(For experienced traders: technical, concise, focus on alpha/risk metrics, win rate \
analysis, period-over-period delta. Skip basic explanations. Professional — use \
financial symbols (%, +/-, currency) but minimal decorative symbols.)

Guidelines for ALL tiers:
- Be factual — do not hallucinate data not provided above
- If income projections or forward-looking estimates are present, include a brief \
disclaimer: past performance does not guarantee future results, projections are \
estimates based on historical data, and actual results may vary
- If there's prior period data, compare and note changes
- Note goal progress and whether the user is on track
- If deposits or withdrawals occurred, explicitly mention them and clarify the \
difference between account value growth and actual trading performance"""


async def _call_ai(client, provider: str, prompt: str) -> Optional[str]:
    """Call the appropriate AI provider and return the response text."""
    if provider in ("claude", "anthropic"):
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=MAX_SUMMARY_TOKENS,
            system=_SYSTEM_MESSAGE,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else None

    elif provider == "openai":
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=MAX_SUMMARY_TOKENS,
            messages=[
                {"role": "system", "content": _SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content if response.choices else None

    elif provider == "gemini":
        model_instance = client.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=_SYSTEM_MESSAGE,
        )
        response = await model_instance.generate_content_async(prompt)
        return response.text if response else None

    return None
