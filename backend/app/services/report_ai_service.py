"""
Report AI Service

Generates AI-powered summaries for performance reports using
the user's own AI provider credentials.

Returns two tiers (simple, detailed) in a single AI call.
"""

import logging
import re
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_AI_TRANSFER_LABELS = {
    "cardspend": "Card Spend",
    "fiat_deposit": "Bank Deposit",
    "fiat_withdrawal": "Bank Withdrawal",
    "send": "Crypto Transfer",
    "exchange_deposit": "Exchange Transfer",
    "exchange_withdrawal": "Exchange Transfer",
}


def _ai_transfer_label(rec: dict) -> str:
    """Map original_type to a descriptive label for AI prompts."""
    ot = rec.get("original_type")
    if ot and ot in _AI_TRANSFER_LABELS:
        label = _AI_TRANSFER_LABELS[ot]
        if ot == "cardspend":
            label += f" ({rec.get('currency', 'USD')})"
        return label
    return rec.get("type", "").capitalize()


def _summarize_conditions(conditions_obj: Optional[dict]) -> str:
    """Summarize indicator conditions into a concise human-readable string."""
    if not conditions_obj or not isinstance(conditions_obj, dict):
        return ""
    groups = conditions_obj.get("groups", [])
    if not groups:
        return ""
    group_strs = []
    for grp in groups:
        conds = grp.get("conditions", [])
        parts = []
        for c in conds:
            ind = c.get("type", c.get("indicator", "?"))
            op = c.get("operator", "")
            val = c.get("value", "")
            tf = c.get("timeframe", "")
            parts.append(f"{ind} {op} {val} ({tf})")
        if parts:
            logic = grp.get("logic", "and").upper()
            group_strs.append(f" {logic} ".join(parts))
    if not group_strs:
        return ""
    group_logic = conditions_obj.get("groupLogic", "and").upper()
    return f" {group_logic} ".join(f"({g})" if len(group_strs) > 1 else g for g in group_strs)


def _fmt_ai_coverage_pct(pct: float) -> str:
    """Format coverage percentage with adaptive precision for AI prompts."""
    if pct < 1:
        return f"{pct:.2f}%"
    elif pct < 10:
        return f"{pct:.1f}%"
    else:
        return f"{pct:.0f}%"


# Max tokens for summary generation (2 tiers with structured markdown sections)
MAX_SUMMARY_TOKENS = 4096

# System message for all AI providers — sets the role and output format
_SYSTEM_MESSAGE = (
    "You are a trading performance analyst writing structured report summaries. "
    "Format your output using markdown: ### for section headers, **bold** for key "
    "figures, - for bullet lists. Be factual — never invent data not provided."
)

# Delimiters used to split the AI response into tiers
_DELIM_SIMPLE = "---SUMMARY---"
_DELIM_DETAILED = "---DETAILED---"
# Regex to strip stray delimiter-like artifacts the AI sometimes adds
_STRAY_DELIM_RE = re.compile(r'---[A-Z_]+---')


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
        tiered_summary_dict has keys: simple, detailed
    """
    all_providers = ["claude", "openai", "gemini"]
    if provider:
        # Try preferred provider first, then fall back to others
        providers_to_try = [provider] + [p for p in all_providers if p != provider]
    else:
        providers_to_try = all_providers

    any_client_obtained = False
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

        any_client_obtained = True
        prompt = _build_summary_prompt(report_data, period_label)

        try:
            raw_text = await _call_ai(client, prov, prompt)
            if raw_text:
                tiered = _parse_tiered_summary(raw_text)
                return tiered, prov
        except Exception as e:
            logger.warning(f"AI summary generation failed with {prov}: {e}")
            continue

    if any_client_obtained:
        logger.warning(
            f"All AI providers failed for user {user_id} "
            "(credentials found but calls errored)"
        )
        return {"_error": "all_providers_failed"}, None
    logger.info(f"No AI provider available for user {user_id}, skipping summary")
    return None, None


def _parse_tiered_summary(text: str) -> dict:
    """
    Parse a delimited AI response into two tiers.

    Expected format:
        ---SUMMARY---
        ... simple text ...
        ---DETAILED---
        ... detailed text ...

    Fallback: if delimiters are not found, the entire response is
    assigned to the 'simple' tier.
    """
    has_delimiters = (
        _DELIM_SIMPLE in text
        and _DELIM_DETAILED in text
    )

    if not has_delimiters:
        return {
            "simple": text.strip(),
            "detailed": None,
        }

    after_simple = text.split(_DELIM_SIMPLE, 1)[1]
    simple_text, detailed_text = after_simple.split(_DELIM_DETAILED, 1)

    # Strip stray delimiter artifacts the AI may include (e.g. "---DELIMITER---")
    simple_clean = _STRAY_DELIM_RE.sub('', simple_text).strip() or None
    detailed_clean = _STRAY_DELIM_RE.sub('', detailed_text).strip() or None

    return {
        "simple": simple_clean,
        "detailed": detailed_clean,
    }


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
                    f"Coverage: {_fmt_ai_coverage_pct(cov_pct)} ({covered_n}/{total_n} items covered), "
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

    # Always compute the account value change vs profit discrepancy
    start_val = data.get("period_start_value_usd", 0)
    end_val = data.get("account_value_usd", 0)
    account_change = round(end_val - start_val, 2)
    period_profit = data.get("period_profit_usd", 0)
    net_deposits = data.get("net_deposits_usd", 0)
    total_dep = data.get("total_deposits_usd", 0)
    total_wth = data.get("total_withdrawals_usd", 0)
    adj_growth = data.get("adjusted_account_growth_usd", 0)

    deposits_source = data.get("deposits_source", "transfers")
    source_note = ""
    if deposits_source == "implied":
        source_note = (
            "\n  NOTE: No individual deposit/withdrawal records are available. "
            "The net deposits figure above is computed from the accounting identity: "
            "net deposits = account value change - trading profit. "
            "Do NOT say 'no deposits were made' — the math proves deposits/withdrawals "
            "occurred. Present the implied net figure accurately."
        )

    # Trading summary line
    trade_summary = data.get("trade_summary")
    trade_line = ""
    if trade_summary and trade_summary.get("total_trades", 0) > 0:
        ts = trade_summary
        ts_sign = "+" if ts["net_profit_usd"] >= 0 else ""
        trade_line = (
            f"\n  - Trading activity: {ts['total_trades']} trades "
            f"({ts['winning_trades']}W/{ts['losing_trades']}L), "
            f"net P&L: {ts_sign}${abs(ts['net_profit_usd']):,.2f}"
        )

    capital_section = (
        f"\nCapital Movements & Account Reconciliation:"
        f"{trade_line}"
        f"\n  - Account value change in period: ${account_change:,.2f}"
        f"\n    (from ${start_val:,.2f} to ${end_val:,.2f})"
        f"\n  - Trading profit in period: ${period_profit:,.2f}"
        f"\n  - Net deposits/withdrawals: ${net_deposits:,.2f}"
        f"\n    (Deposits: ${total_dep:,.2f} / Withdrawals: ${total_wth:,.2f})"
        f"\n  - Adjusted growth (excluding deposits): ${adj_growth:,.2f}"
        f"{source_note}"
    )

    # Append transfer records — aggregate staking rewards, list others individually
    transfer_records = data.get("transfer_records", [])
    if transfer_records:
        staking = [
            tr for tr in transfer_records
            if tr.get("original_type") == "send" and tr.get("type") == "deposit"
        ]
        other = [tr for tr in transfer_records if tr not in staking]
        lines = []
        if staking:
            stk_total = sum(abs(tr.get("amount_usd", 0)) for tr in staking)
            lines.append(
                f"\n  - Staking rewards: {len(staking)} deposits, "
                f"total +${stk_total:,.2f}"
            )
        if other:
            lines.append("\n  Individual transfers (most recent first):")
            for tr in other:
                tr_type = _ai_transfer_label(tr)
                tr_amt = abs(tr.get("amount_usd", 0))
                tr_sign = "+" if tr.get("type") == "deposit" else "-"
                lines.append(
                    f"  - {tr.get('date', '')}: {tr_type} {tr_sign}${tr_amt:,.2f}"
                )
        capital_section += "\n".join(lines)

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

    # Bot strategy context — helps the AI interpret win rates and trade patterns
    strategy_section = ""
    bot_strategies = data.get("bot_strategies", [])
    if bot_strategies:
        strat_lines = ["\nTrading Strategy Context:"]
        for bs in bot_strategies:
            cfg = bs.get("config", {})
            st = bs.get("strategy_type", "unknown")
            pairs = ", ".join(bs.get("pairs", []))
            trades = bs.get("trades_in_period", 0)
            wins = bs.get("wins_in_period", 0)
            strat_lines.append(
                f"  Bot: {bs['name']} ({st}, {pairs}) — "
                f"{trades} trades ({wins}W/{trades - wins}L)"
            )
            # Core DCA parameters
            params = []
            tp = cfg.get("take_profit_percentage")
            if tp is not None:
                params.append(f"take_profit={tp}%")
            mso = cfg.get("max_safety_orders")
            if mso is not None:
                params.append(f"max_safety_orders={mso}")
            so_pct = cfg.get("safety_order_percentage")
            if so_pct is not None:
                params.append(f"safety_order_size={so_pct}%")
            pd = cfg.get("price_deviation")
            if pd is not None:
                params.append(f"price_deviation={pd}%")
            mcd = cfg.get("max_concurrent_deals")
            if mcd is not None:
                params.append(f"max_concurrent_deals={mcd}")
            soss = cfg.get("safety_order_step_scale")
            if soss is not None:
                params.append(f"safety_order_step_scale={soss}")
            sovs = cfg.get("safety_order_volume_scale")
            if sovs is not None:
                params.append(f"safety_order_volume_scale={sovs}")
            if cfg.get("trailing_take_profit"):
                params.append(f"trailing_tp={cfg.get('trailing_deviation', 0)}%")
            if cfg.get("stop_loss_enabled"):
                params.append("stop_loss=enabled")
            if params:
                strat_lines.append(f"    Config: {', '.join(params)}")
            # Summarize indicator conditions
            for phase, label in [
                ("base_order_conditions", "Entry signals"),
                ("take_profit_conditions", "Take profit signals"),
                ("safety_order_conditions", "Safety order signals"),
            ]:
                conds = _summarize_conditions(cfg.get(phase))
                if conds:
                    strat_lines.append(f"    {label}: {conds}")
        strat_lines.append(
            "  STRATEGY NOTES (use these to inform your analysis):"
        )
        strat_lines.append(
            "  - DCA Mechanics: These bots enter on momentum/indicator signals "
            "and take small profits. Safety orders require BOTH a minimum price "
            "drop from entry (price_deviation, multiplied by "
            "safety_order_step_scale for each subsequent order — e.g. 2% for "
            "SO1, 4% for SO2, 8% for SO3) AND the momentum indicator "
            "conditions to be met. This prevents premature averaging down. "
            "High win rates are expected — positions close only when profitable."
        )
        # Detect BTC-pair bots and add crypto-maximalist context
        has_btc_pairs = any(
            any(p.endswith("-BTC") for p in bs.get("pairs", []))
            for bs in bot_strategies
        )
        if has_btc_pairs:
            strat_lines.append(
                "  - BTC Accumulation Strategy: Bots trading alt/BTC pairs "
                "are denominated in BTC — profits and losses are in BTC, not "
                "USD. The goal is to accumulate more BTC by trading more "
                "volatile altcoins against it. Since crypto assets tend to "
                "move together as a risk class, alt volatility relative to "
                "BTC creates opportunities to 'mine' BTC through trading. "
                "Open positions holding top-tier altcoins are not considered "
                "dead capital — the user is a crypto maximalist who accepts "
                "alt exposure, knowing that quality crypto assets tend to "
                "appreciate against fiat long-term even if BTC outpaces them. "
                "Do NOT frame BTC-pair positions as 'capital lockup' or "
                "'opportunity cost' — the user is intentionally holding crypto."
            )
        strategy_section = "\n".join(strat_lines)

    total_trades = data.get('total_trades', 0)
    if total_trades > 0:
        trade_stats = (
            f"- Total Trades: {total_trades}\n"
            f"- Win/Loss: {data.get('winning_trades', 0)}W / {data.get('losing_trades', 0)}L\n"
            f"- Win Rate: {data.get('win_rate', 0):.1f}%"
        )
    else:
        trade_stats = "- Total Trades: 0 (no trades closed in this period)"

    return f"""Analyze this trading report for the period: {period_label}.

Report Data:
- Account Value: ${data.get('account_value_usd', 0):,.2f} ({data.get('account_value_btc', 0):.6f} BTC)
- Period Start Value: ${data.get('period_start_value_usd', 0):,.2f}
- Period Profit: ${data.get('period_profit_usd', 0):,.2f} ({data.get('period_profit_btc', 0):.8f} BTC)
{trade_stats}
{goals_section}{capital_section}{prior_section}{strategy_section}

IMPORTANT: If there were zero trades in the period, do NOT mention win rate, \
win/loss ratios, or imply poor performance. Simply note that no trades closed \
during this period. Focus on account value changes, capital movements, and goals instead.

Write TWO versions separated by the exact delimiters below.

{_DELIM_SIMPLE}
(Summary version: plain language, explain jargon, encouraging tone. Focus on \
"what does this mean for me?" Use a few approachable symbols at section headers \
for visual warmth — not childish or overloaded, just welcoming.)

Required sections in order:
### Performance Overview, ### Goal Progress (if goal data present), \
### Capital Movements, ### Outlook & Action Items.
Keep each section concise: 2-4 sentences or a short bullet list.

Formatting: ### for headers, **bold** for key figures, - for bullet lists.

{_DELIM_DETAILED}
(Detailed version: expert-level depth, technical, opinionated. Analyze alpha, \
risk metrics, win rate trends, period-over-period delta. Skip basic explanations. \
Professional — use financial symbols (%, +/-, currency) but minimal decorative symbols. \
You MAY add extra sections beyond the required ones if the data warrants it — e.g. \
### Risk Assessment, ### Strategy Notes, ### Optimization Ideas. Offer your \
analytical opinion and suggest specific, actionable improvements.)

Required sections in order:
### Performance Overview, ### Goal Progress (if goal data present), \
### Capital Movements, ### Outlook & Action Items.
Additional sections are encouraged after the required ones.

Formatting: ### for headers, **bold** for key figures, - for bullet lists.

Guidelines for BOTH versions:
- Be factual — do not hallucinate data not provided above
- CRITICAL: NEVER imply that account value change equals trading profit. The \
account value change includes deposits and withdrawals. Always break down the \
account value change: how much came from trading profit vs. deposits/withdrawals. \
If account value change is significantly different from trading profit, explicitly \
state that the difference is from deposits or withdrawals — do NOT present the \
value change as if it resulted from trading.
- CRITICAL: When both deposits AND withdrawals occurred, you MUST mention BOTH. \
The math must add up: account_change = trading_profit + deposits - withdrawals. \
Never cite only deposits and omit withdrawals (or vice versa) — the reader will \
notice the numbers don't add up.
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
