"""
HTML Builder — HTML report generation, charts, AI summaries, metrics, goals.

Part of the report_generator_service package.
"""

import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import markdown as _md
from PIL import Image, ImageDraw, ImageFont

from app.services.brand_service import get_brand
from app.services.report_generator_service.expense_builder import (
    _build_expenses_goal_card,
)


# Tier display labels
_TIER_LABELS = {
    "simple": "Summary",
    "detailed": "Detailed Analysis",
}


def _md_to_styled_html(text: str, brand_color: str) -> str:
    """Convert markdown text to dark-theme styled HTML for report display.

    Converts markdown → HTML via the markdown library, then applies
    inline styles for the dark theme (slate backgrounds, light text).
    Old plain-text summaries pass through fine — plain text gets <p> wrapped.
    """
    raw_html = _md.markdown(text.strip(), extensions=["extra"])

    # Apply inline styles via string replacement
    styled = raw_html
    # h3 headers → brand color, bold
    styled = styled.replace(
        "<h3>",
        f'<h3 style="color: {brand_color}; font-size: 15px; font-weight: 700; '
        f'margin: 18px 0 8px 0;">',
    )
    # Paragraphs → slate text
    styled = styled.replace(
        "<p>",
        '<p style="color: #cbd5e1; line-height: 1.7; '
        'margin: 0 0 10px 0; font-size: 14px;">',
    )
    # Unordered lists
    styled = styled.replace(
        "<ul>",
        '<ul style="color: #cbd5e1; font-size: 14px; line-height: 1.7; '
        'margin: 4px 0 10px 0; padding-left: 20px;">',
    )
    # List items
    styled = styled.replace(
        "<li>",
        '<li style="margin: 2px 0;">',
    )
    # Bold → bright white
    styled = styled.replace(
        "<strong>",
        '<strong style="color: #f1f5f9;">',
    )
    # Italic → muted
    styled = styled.replace(
        "<em>",
        '<em style="color: #94a3b8;">',
    )
    return styled


def _normalize_ai_summary(
    ai_summary: Union[None, str, dict],
) -> Optional[dict]:
    """
    Normalize ai_summary to a tiered dict with keys: simple, detailed.

    Handles:
      - None → None
      - str → {"simple": str, "detailed": None}
      - dict → pass through (with legacy 3-tier migration)
      - JSON string of a dict → parsed dict
    """
    if ai_summary is None:
        return None

    if isinstance(ai_summary, dict):
        return _migrate_legacy_tiers(ai_summary)

    if isinstance(ai_summary, str):
        # Try to parse as JSON dict (stored in DB as json.dumps)
        try:
            parsed = json.loads(ai_summary)
            if isinstance(parsed, dict):
                return _migrate_legacy_tiers(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
        # Plain text — wrap as simple tier
        return {
            "simple": ai_summary,
            "detailed": None,
        }

    return None


def _migrate_legacy_tiers(d: dict) -> dict:
    """Convert old 3-tier (beginner/comfortable/experienced) to 2-tier (simple/detailed)."""
    if "simple" in d or "detailed" in d:
        return d
    # Legacy format — map comfortable→simple, experienced→detailed
    return {
        "simple": d.get("comfortable") or d.get("beginner"),
        "detailed": d.get("experienced"),
    }


def build_report_html(
    report_data: Dict[str, Any],
    ai_summary: Union[None, str, dict],
    user_name: str,
    period_label: str,
    default_level: str = "simple",
    schedule_name: Optional[str] = None,
    email_mode: bool = False,
    account_name: Optional[str] = None,
    inline_images: Optional[List[Tuple[str, bytes]]] = None,
) -> str:
    """
    Build the full HTML report.

    Args:
        report_data: Metrics dictionary
        ai_summary: AI-generated summary — dict of tiers, plain string, or None
        user_name: User's display name or email
        period_label: e.g. "January 1 - January 7, 2026"
        default_level: Which tier tab is active by default
        schedule_name: Optional report schedule name (shown as title)
        email_mode: If True, show only the default tier (email clients strip JS)
        inline_images: Mutable list; PNG chart images are appended as (cid, bytes)
            tuples for CID embedding in email. Only used when email_mode=True.

    Returns:
        Complete HTML string
    """
    b = get_brand()
    brand_color = b["colors"]["primary"]

    metrics_html = _build_metrics_section(report_data)
    transfers_html = _build_transfers_section(report_data)

    # Split goals: expenses goals go right after Capital Movements
    all_goals = report_data.get("goals", [])
    expense_goals = [g for g in all_goals if g.get("target_type") == "expenses"]
    other_goals = [g for g in all_goals if g.get("target_type") != "expenses"]
    schedule_meta = report_data.get("_schedule_meta")
    expense_goals_html = _build_goals_section(
        expense_goals, brand_color, email_mode=email_mode,
        section_title="Expense Coverage",
        schedule_meta=schedule_meta,
        inline_images=inline_images,
    )
    goals_html = _build_goals_section(
        other_goals, brand_color, email_mode=email_mode,
        inline_images=inline_images,
    )
    comparison_html = _build_comparison_section(report_data)

    tiered = _normalize_ai_summary(ai_summary)
    ai_html = ""
    if tiered:
        if email_mode:
            ai_html = _build_email_ai_section(tiered, default_level, brand_color)
        else:
            ai_html = _build_tabbed_ai_section(tiered, default_level, brand_color)
    elif isinstance(ai_summary, dict) and "_error" in ai_summary:
        ai_html = """
        <div style="margin: 25px 0; padding: 15px; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155; text-align: center;">
            <p style="color: #94a3b8; margin: 0; font-size: 13px;">
                AI insights temporarily unavailable — provider rate-limited or credits exhausted.
                Check your AI provider dashboard.</p>
        </div>"""
    elif ai_summary is None:
        ai_html = """
        <div style="margin: 25px 0; padding: 15px; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155; text-align: center;">
            <p style="color: #94a3b8; margin: 0; font-size: 13px;">
                Add AI provider credentials in Settings to enable AI-powered insights.</p>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{b['shortName']} Performance Report</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0f172a; color: #e2e8f0;
             font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
<div style="max-width: 700px; margin: 0 auto; padding: 20px;">
    {_report_header(b, user_name, period_label, brand_color, schedule_name, account_name)}
    {metrics_html}
    {goals_html}
    {expense_goals_html}
    {transfers_html}
    {comparison_html}
    {ai_html}
    {_report_footer(b)}
</div>
</body>
</html>"""


def _build_tabbed_ai_section(
    ai_summary: dict,
    default_level: str,
    brand_color: str,
) -> str:
    """
    Render AI tiers as CSS-only tabbed interface (no JavaScript).

    Uses hidden radio buttons + :checked pseudo-class for tab switching,
    which works under strict CSP without 'unsafe-inline' in script-src.
    """
    tier_order = ["simple", "detailed"]
    available = [(t, ai_summary.get(t)) for t in tier_order if ai_summary.get(t)]

    if not available:
        return ""

    if len(available) == 1:
        # Only one tier — no tabs needed
        tier, text = available[0]
        label = _TIER_LABELS.get(tier, tier.capitalize())
        return _render_single_ai_section(text, label, brand_color)

    # CSS rules for tab states (checked radio → show panel + highlight label)
    # !important is required to override the inline style="display:none" on panels
    css_rules = []
    for tier, _ in available:
        css_rules.append(
            f'#ai-tab-{tier}:checked ~ .ai-tab-bar label[for="ai-tab-{tier}"] '
            f'{{ background-color: #1e293b; color: {brand_color}; '
            f'border-bottom-color: {brand_color}; }}'
        )
        css_rules.append(
            f'#ai-tab-{tier}:checked ~ #ai-panel-{tier} '
            f'{{ display: block !important; }}'
        )

    # Hidden radio inputs (must precede tab-bar and panels as siblings)
    radios = []
    for tier, _ in available:
        checked = " checked" if tier == default_level else ""
        radios.append(
            f'<input type="radio" name="ai-tab" id="ai-tab-{tier}" '
            f'style="display:none"{checked}>'
        )

    # Tab labels
    labels = []
    for tier, _ in available:
        label = _TIER_LABELS.get(tier, tier.capitalize())
        labels.append(
            f'<label for="ai-tab-{tier}" style="padding: 10px 18px; '
            f'cursor: pointer; font-size: 13px; font-weight: 600; '
            f'font-family: inherit; border-bottom: 2px solid transparent; '
            f'color: #64748b; transition: all 0.2s;">{label}</label>'
        )

    # Content panels (hidden by default, shown via CSS when radio checked)
    panels = []
    for tier, text in available:
        rendered = _md_to_styled_html(text, brand_color)
        panels.append(
            f'<div id="ai-panel-{tier}" style="display: none; '
            f'padding: 20px;">{rendered}</div>'
        )

    return f"""
        <style>
        {chr(10).join(css_rules)}
        </style>
        <div style="margin: 25px 0; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155; overflow: hidden;">
            {chr(10).join(radios)}
            <div class="ai-tab-bar" style="display: flex; border-bottom: 1px solid #334155;
                        background-color: #162032;">
                {chr(10).join(labels)}
            </div>
            {chr(10).join(panels)}
        </div>"""


def _build_email_ai_section(
    ai_summary: dict,
    default_level: str,
    brand_color: str,
) -> str:
    """
    Render only the recipient's tier for email delivery.

    Email clients strip JS, so no tabs. Shows one tier with a note
    about other perspectives being available in the web report.
    """
    text = ai_summary.get(default_level)
    if not text:
        # Fallback: try any available tier
        for tier in ["simple", "detailed"]:
            text = ai_summary.get(tier)
            if text:
                default_level = tier
                break
    if not text:
        return ""

    label = _TIER_LABELS.get(default_level, default_level.capitalize())
    return _render_single_ai_section(text, label, brand_color)


def _render_single_ai_section(text: str, label: str, brand_color: str) -> str:
    """Render a single AI summary section (used by both email and single-tier)."""
    rendered = _md_to_styled_html(text, brand_color)
    return f"""
        <div style="margin: 25px 0; padding: 20px; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155;
                    border-left: 4px solid {brand_color};">
            <h3 style="color: {brand_color}; margin: 0 0 15px 0; font-size: 16px;">
                {label}</h3>
            {rendered}
        </div>"""


def _report_header(
    brand: dict, user_name: str, period_label: str, brand_color: str,
    schedule_name: Optional[str] = None, account_name: Optional[str] = None,
) -> str:
    """Report header with brand name, report title, account, and period."""
    title = schedule_name or "Performance Report"
    prepared_for = user_name
    if account_name:
        prepared_for += f" &mdash; {account_name}"
    return f"""
    <div style="text-align: center; padding: 25px 0; border-bottom: 1px solid #334155;">
        <h1 style="color: {brand_color}; margin: 0; font-size: 26px;">{brand['shortName']}</h1>
        <p style="color: #94a3b8; margin: 5px 0 0 0; font-size: 14px;">
            {brand['tagline']}</p>
    </div>
    <div style="padding: 20px 0 10px 0;">
        <h2 style="color: #f1f5f9; margin: 0 0 5px 0; font-size: 20px;">
            {title}</h2>
        <p style="color: #94a3b8; margin: 0; font-size: 14px;">
            {period_label} &mdash; Prepared for {prepared_for}</p>
    </div>"""


def _report_footer(brand: dict) -> str:
    """Report footer with copyright."""
    return f"""
    <div style="border-top: 1px solid #334155; padding: 20px 0; text-align: center;
                margin-top: 30px;">
        <p style="color: #64748b; font-size: 12px; margin: 0;">
            &copy; {brand['copyright']}</p>
        <p style="color: #475569; font-size: 11px; margin: 5px 0 0 0;">
            Generated on {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')}</p>
    </div>"""


_TRANSFER_LABELS = {
    "cardspend": "Card Spend",
    "fiat_deposit": "Bank Deposit",
    "fiat_withdrawal": "Bank Withdrawal",
    "send": "Crypto Transfer",
    "exchange_deposit": "Exchange Transfer",
    "exchange_withdrawal": "Exchange Transfer",
}


def _transfer_label(rec: Dict[str, Any]) -> str:
    """Map original_type to a human-readable label for reports."""
    ot = rec.get("original_type")
    if ot and ot in _TRANSFER_LABELS:
        label = _TRANSFER_LABELS[ot]
        if ot == "cardspend":
            label += f" ({rec.get('currency', 'USD')})"
        return label
    return rec.get("type", "").capitalize()


def _build_transfers_section(data: Dict[str, Any]) -> str:
    """Render a Capital Movements table with optional trading summary and transfers."""
    trade_summary = data.get("trade_summary")
    records = data.get("transfer_records", [])
    has_trades = trade_summary and trade_summary.get("total_trades", 0) > 0

    if not records and not has_trades:
        return ""

    # Trading summary row
    trade_row = ""
    if has_trades:
        ts = trade_summary
        net = ts["net_profit_usd"]
        color = "#10b981" if net >= 0 else "#ef4444"
        sign = "+" if net >= 0 else ""
        w = ts["winning_trades"]
        lo = ts["losing_trades"]
        trade_row = f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 2px solid #475569;
                               color: #e2e8f0; font-size: 12px; font-weight: 600;"
                        colspan="2">Trading Activity &mdash; {ts['total_trades']} trades ({w}W/{lo}L)</td>
                    <td style="padding: 8px; border-bottom: 2px solid #475569;
                               color: {color}; font-size: 12px; text-align: right;
                               font-weight: 700;">{sign}${abs(net):,.2f}</td>
                </tr>"""

    # Separate staking rewards from other transfers for aggregation
    staking = [r for r in records if r.get("original_type") == "send" and r.get("type") == "deposit"]
    other_transfers = [r for r in records if r not in staking]

    # Staking rewards summary row (aggregated like trading activity)
    staking_row = ""
    if staking:
        total_staking = sum(abs(r.get("amount_usd", 0)) for r in staking)
        staking_row = f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 2px solid #475569;
                               color: #e2e8f0; font-size: 12px; font-weight: 600;"
                        colspan="2">Staking Rewards &mdash; {len(staking)} deposits</td>
                    <td style="padding: 8px; border-bottom: 2px solid #475569;
                               color: #10b981; font-size: 12px; text-align: right;
                               font-weight: 700;">+${total_staking:,.2f}</td>
                </tr>"""

    # Individual transfer rows (non-staking)
    transfer_rows = ""
    for rec in other_transfers:
        is_deposit = rec.get("type") == "deposit"
        color = "#10b981" if is_deposit else "#ef4444"
        sign = "+" if is_deposit else "-"
        amt = abs(rec.get("amount_usd", 0))
        label = _transfer_label(rec)
        date_str = rec.get("date", "")
        transfer_rows += f"""
                <tr>
                    <td style="padding: 6px 8px; border-bottom: 1px solid #334155;
                               color: #94a3b8; font-size: 12px;">{date_str}</td>
                    <td style="padding: 6px 8px; border-bottom: 1px solid #334155;
                               color: {color}; font-size: 12px;">{label}</td>
                    <td style="padding: 6px 8px; border-bottom: 1px solid #334155;
                               color: {color}; font-size: 12px; text-align: right;
                               font-weight: 600;">{sign}${amt:,.2f}</td>
                </tr>"""

    return f"""
    <div style="margin: 20px 0;">
        <h3 style="color: #94a3b8; font-size: 13px; text-transform: uppercase;
                   letter-spacing: 1px; margin: 0 0 15px 0;">Capital Movements</h3>
        <table style="width: 100%; border-collapse: collapse; background-color: #1e293b;
                      border-radius: 8px; border: 1px solid #334155;">
            <thead>
                <tr>
                    <th style="padding: 8px; text-align: left; color: #64748b;
                               font-size: 11px; border-bottom: 1px solid #334155;">Date</th>
                    <th style="padding: 8px; text-align: left; color: #64748b;
                               font-size: 11px; border-bottom: 1px solid #334155;">Type</th>
                    <th style="padding: 8px; text-align: right; color: #64748b;
                               font-size: 11px; border-bottom: 1px solid #334155;">Amount</th>
                </tr>
            </thead>
            <tbody>
                {trade_row}{staking_row}{transfer_rows}
            </tbody>
        </table>
    </div>"""


def _build_metrics_section(data: Dict[str, Any]) -> str:
    """Key metrics cards grid."""
    value_usd = data.get("account_value_usd", 0)
    value_btc = data.get("account_value_btc", 0)
    profit_usd = data.get("period_profit_usd", 0)
    profit_btc = data.get("period_profit_btc", 0)
    total_trades = data.get("total_trades", 0)
    win_rate = data.get("win_rate", 0)
    winning = data.get("winning_trades", 0)
    losing = data.get("losing_trades", 0)
    period_days = data.get("period_days")
    trades_label = "Total Trades"
    if period_days:
        trades_label += f" (last {period_days}d)"

    profit_color = "#10b981" if profit_usd >= 0 else "#ef4444"
    profit_sign = "+" if profit_usd >= 0 else ""

    # Build deposit/withdrawal row if applicable
    net_deposits = data.get("net_deposits_usd", 0)
    adjusted_growth = data.get("adjusted_account_growth_usd")
    deposit_row = ""
    if adjusted_growth is not None:
        dep_sign = "+" if net_deposits >= 0 else ""
        dep_color = "#3b82f6" if net_deposits >= 0 else "#f59e0b"
        adj_sign = "+" if adjusted_growth >= 0 else ""
        adj_color = "#10b981" if adjusted_growth >= 0 else "#ef4444"
        deposit_row = f"""
            <tr>
                <td style="width: 50%; padding: 12px; background-color: #1e293b;
                           border: 1px solid #334155;">
                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">Net Deposits</p>
                    <p style="color: {dep_color}; font-size: 20px; font-weight: 700;
                             margin: 5px 0 0 0;">{dep_sign}${abs(net_deposits):,.2f}</p>
                    <p style="color: #94a3b8; font-size: 12px; margin: 3px 0 0 0;">
                        capital movement</p>
                </td>
                <td style="width: 50%; padding: 12px; background-color: #1e293b;
                           border: 1px solid #334155;">
                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">Adjusted Growth</p>
                    <p style="color: {adj_color}; font-size: 20px; font-weight: 700;
                             margin: 5px 0 0 0;">{adj_sign}${abs(adjusted_growth):,.2f}</p>
                    <p style="color: #94a3b8; font-size: 12px; margin: 3px 0 0 0;">
                        excl. deposits</p>
                </td>
            </tr>"""

    html = f"""
    <div style="margin: 20px 0;">
        <h3 style="color: #94a3b8; font-size: 13px; text-transform: uppercase;
                   letter-spacing: 1px; margin: 0 0 15px 0;">Key Metrics</h3>
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="width: 50%; padding: 12px; background-color: #1e293b;
                           border-radius: 8px 0 0 0; border: 1px solid #334155;">
                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">Account Value</p>
                    <p style="color: #f1f5f9; font-size: 20px; font-weight: 700;
                             margin: 5px 0 0 0;">${value_usd:,.2f}</p>
                    <p style="color: #94a3b8; font-size: 12px; margin: 3px 0 0 0;">
                        {value_btc:.6f} BTC</p>
                </td>
                <td style="width: 50%; padding: 12px; background-color: #1e293b;
                           border-radius: 0 8px 0 0; border: 1px solid #334155;">
                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">Period Profit</p>
                    <p style="color: {profit_color}; font-size: 20px; font-weight: 700;
                             margin: 5px 0 0 0;">{profit_sign}${abs(profit_usd):,.2f}</p>
                    <p style="color: #94a3b8; font-size: 12px; margin: 3px 0 0 0;">
                        {profit_sign}{profit_btc:.8f} BTC</p>
                </td>
            </tr>
            <tr>
                <td style="width: 50%; padding: 12px; background-color: #1e293b;
                           border-radius: 0 0 0 8px; border: 1px solid #334155;">
                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">{trades_label}</p>
                    <p style="color: #f1f5f9; font-size: 20px; font-weight: 700;
                             margin: 5px 0 0 0;">{total_trades}</p>
                    <p style="color: #94a3b8; font-size: 12px; margin: 3px 0 0 0;">
                        {winning}W / {losing}L</p>
                </td>
                <td style="width: 50%; padding: 12px; background-color: #1e293b;
                           border-radius: 0 0 8px 0; border: 1px solid #334155;">
                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">Win Rate</p>
                    <p style="color: {'#10b981' if win_rate >= 50 else '#ef4444'};
                             font-size: 20px; font-weight: 700;
                             margin: 5px 0 0 0;">{win_rate:.1f}%</p>
                    <p style="color: #94a3b8; font-size: 12px; margin: 3px 0 0 0;">
                        of closed trades</p>
                </td>
            </tr>{deposit_row}
        </table>
    </div>"""

    # Market Value Effect row (appended after the table if available)
    mve = data.get("market_value_effect_usd")
    if mve is not None:
        mve_sign = "+" if mve >= 0 else ""
        mve_color = "#a78bfa" if mve >= 0 else "#f59e0b"
        html += f"""
    <div style="margin: -10px 0 20px 0;">
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="width: 100%; padding: 12px; background-color: #1e293b;
                           border: 1px solid #334155; border-radius: 0 0 8px 8px;">
                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">
                        Market Value Effect (BTC price change)</p>
                    <p style="color: {mve_color}; font-size: 20px; font-weight: 700;
                             margin: 5px 0 0 0;">{mve_sign}${abs(mve):,.2f}</p>
                    <p style="color: #94a3b8; font-size: 12px; margin: 3px 0 0 0;">
                        USD value change from BTC price movement alone</p>
                </td>
            </tr>
        </table>
    </div>"""

    return html


def _build_goals_section(
    goals: List[Dict[str, Any]], brand_color: str = "#3b82f6",
    email_mode: bool = False,
    section_title: str = "Goal Progress",
    schedule_meta: Optional[Dict[str, Any]] = None,
    inline_images: Optional[List[Tuple[str, bytes]]] = None,
) -> str:
    """Goal progress bars with optional trend charts."""
    if not goals:
        return ""

    goal_rows = ""
    for g in goals:
        if g.get("target_type") == "income":
            goal_rows += _build_income_goal_card(g)
        elif g.get("target_type") == "expenses":
            goal_rows += _build_expenses_goal_card(
                g, email_mode=email_mode, schedule_meta=schedule_meta,
                brand_color=brand_color, inline_images=inline_images,
            )
        else:
            goal_rows += _build_standard_goal_card(
                g, brand_color, email_mode=email_mode,
                inline_images=inline_images,
            )

    return f"""
    <div style="margin: 25px 0;">
        <h3 style="color: #94a3b8; font-size: 13px; text-transform: uppercase;
                   letter-spacing: 1px; margin: 0 0 15px 0;">{section_title}</h3>
        {goal_rows}
    </div>"""


def _build_standard_goal_card(
    g: Dict[str, Any],
    brand_color: str = "#3b82f6",
    email_mode: bool = False,
    inline_images: Optional[List[Tuple[str, bytes]]] = None,
) -> str:
    """Standard balance/profit/both goal card with progress bar and trend chart."""
    pct = g.get("progress_pct", 0)
    bar_color = "#10b981" if g.get("on_track") else "#f59e0b"
    bar_width = min(pct, 100)
    currency = g.get("target_currency", "USD")
    fmt = ".8f" if currency == "BTC" else ",.2f"
    current = f"{g.get('current_value', 0):{fmt}}"
    target = f"{g.get('target_value', 0):{fmt}}"
    prefix = "" if currency == "BTC" else "$"
    track_label = "On Track" if g.get("on_track") else "Behind"
    track_color = "#10b981" if g.get("on_track") else "#f59e0b"

    # Trend chart (SVG for web, PNG for email)
    trend_html = ""
    trend_data = g.get("trend_data")
    if trend_data:
        if email_mode and inline_images is not None:
            png_bytes = _render_trend_chart_png(trend_data, brand_color, currency)
            if png_bytes:
                goal_id = g.get("id", id(g))
                cid = f"goal-chart-{goal_id}"
                inline_images.append((cid, png_bytes))
                trend_html = (
                    '<div style="margin-top: 10px;">'
                    f'<img src="cid:{cid}" width="660"'
                    ' style="width:100%;height:auto;display:block;'
                    'border-radius:6px;" alt="Goal trend chart"/>'
                    '</div>'
                )
        else:
            trend_html = _build_trend_chart_svg(trend_data, brand_color, currency)

    return f"""
        <div style="margin: 0 0 15px 0; padding: 12px; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155;">
            <div style="display: flex; justify-content: space-between; align-items: center;
                        margin: 0 0 8px 0;">
                <span style="color: #f1f5f9; font-weight: 600; font-size: 14px;">
                    {g.get('name', '')}</span>
                <span style="color: {track_color}; font-size: 12px; font-weight: 600;">
                    {track_label}</span>
            </div>
            <div style="background-color: #334155; border-radius: 4px; height: 8px;
                        overflow: hidden;">
                <div style="background-color: {bar_color}; width: {bar_width}%;
                            height: 100%; border-radius: 4px;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; margin-top: 6px;">
                <span style="color: #94a3b8; font-size: 12px;">
                    {prefix}{current} / {prefix}{target} {currency}</span>
                <span style="color: #94a3b8; font-size: 12px;">{pct:.1f}%</span>
            </div>
            {trend_html}
        </div>"""


def _build_income_goal_card(g: Dict[str, Any]) -> str:
    """Income goal card with projection table and deposit advice."""
    pct = g.get("progress_pct", 0)
    bar_color = "#10b981" if g.get("on_track") else "#f59e0b"
    bar_width = min(pct, 100)
    currency = g.get("target_currency", "USD")
    fmt = ".8f" if currency == "BTC" else ",.2f"
    prefix = "" if currency == "BTC" else "$"
    period = g.get("income_period", "monthly")
    track_label = "On Track" if g.get("on_track") else "Behind"
    track_color = "#10b981" if g.get("on_track") else "#f59e0b"

    target = f"{g.get('target_value', 0):{fmt}}"
    daily = f"{g.get('current_daily_income', 0):{fmt}}"
    linear = f"{g.get('projected_income_linear', 0):{fmt}}"
    compound = f"{g.get('projected_income_compound', 0):{fmt}}"

    dep_lin = g.get("deposit_needed_linear")
    dep_cmp = g.get("deposit_needed_compound")
    dep_lin_str = f"{prefix}{dep_lin:{fmt}}" if dep_lin is not None else "N/A"
    dep_cmp_str = f"{prefix}{dep_cmp:{fmt}}" if dep_cmp is not None else "N/A"

    sample = g.get("sample_trades", 0)
    lookback = g.get("lookback_days_used", 0)

    return f"""
        <div style="margin: 0 0 15px 0; padding: 12px; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155;">
            <div style="display: flex; justify-content: space-between; align-items: center;
                        margin: 0 0 8px 0;">
                <span style="color: #f1f5f9; font-weight: 600; font-size: 14px;">
                    {g.get('name', '')}
                    <span style="color: #94a3b8; font-weight: 400; font-size: 12px;
                                 margin-left: 6px;">Income / {period.capitalize()}</span>
                </span>
                <span style="color: {track_color}; font-size: 12px; font-weight: 600;">
                    {track_label}</span>
            </div>
            <div style="background-color: #334155; border-radius: 4px; height: 8px;
                        overflow: hidden; margin-bottom: 10px;">
                <div style="background-color: {bar_color}; width: {bar_width}%;
                            height: 100%; border-radius: 4px;"></div>
            </div>
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Target</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {prefix}{target} {currency}/{period}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Daily Avg Income</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {prefix}{daily} {currency}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Linear Projection</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {prefix}{linear} {currency}/{period}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Compound Projection</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {prefix}{compound} {currency}/{period}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Deposit Needed (Linear)</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {dep_lin_str}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Deposit Needed (Compound)</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {dep_cmp_str}</td>
                </tr>
            </table>
            <p style="color: #64748b; font-size: 11px; margin: 8px 0 0 0;">
                Based on {sample} trades over {lookback} days</p>
            <p style="color: #475569; font-size: 10px; font-style: italic; margin: 6px 0 0 0;">
                Past performance does not guarantee future results. Projections are
                estimates based on historical data and actual results may vary.</p>
        </div>"""


def _format_chart_value(val: float, currency: str) -> str:
    """Format a value for chart axis labels."""
    if currency == "BTC":
        if abs(val) >= 1:
            return f"{val:.2f}"
        return f"{val:.4f}"
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if abs(val) >= 10_000:
        return f"${val / 1_000:.0f}K"
    if abs(val) >= 1_000:
        return f"${val / 1_000:.1f}K"
    return f"${val:,.0f}"


def _build_trend_chart_svg(
    trend_data: Dict[str, Any],
    brand_color: str,
    currency: str = "USD",
) -> str:
    """
    Build an inline SVG trend chart showing actual vs ideal goal progress.

    Returns HTML containing the SVG, or empty string if insufficient data.
    """
    data_points = trend_data.get("data_points", [])
    if len(data_points) < 2:
        return ""

    # Chart dimensions
    width, height = 660, 200
    ml, mr, mt, mb = 65, 15, 20, 35
    cw = width - ml - mr
    ch = height - mt - mb

    # Extract values
    actual = [p["current_value"] for p in data_points]
    ideal = [p["ideal_value"] for p in data_points]
    all_vals = actual + ideal

    min_val = min(all_vals)
    max_val = max(all_vals)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = max_val * 0.1 or 1.0
    # Add 5% padding
    min_val -= val_range * 0.05
    max_val += val_range * 0.05
    val_range = max_val - min_val

    n = len(data_points)

    def sx(i):
        return ml + (i / (n - 1)) * cw

    def sy(v):
        return mt + (1 - (v - min_val) / val_range) * ch

    # Build polyline points
    actual_pts = " ".join(
        f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(actual)
    )
    ideal_pts = " ".join(
        f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(ideal)
    )

    # Area fill under actual line
    area_pts = (
        actual_pts
        + f" {sx(n - 1):.1f},{mt + ch:.1f} {sx(0):.1f},{mt + ch:.1f}"
    )

    is_on_track = data_points[-1].get("on_track", False)
    actual_color = "#10b981" if is_on_track else "#f59e0b"

    # Grid lines + Y-axis labels
    grid_svg = ""
    n_grids = 4
    for i in range(n_grids + 1):
        gy = mt + (i / n_grids) * ch
        grid_svg += (
            f'<line x1="{ml}" y1="{gy:.1f}" '
            f'x2="{width - mr}" y2="{gy:.1f}" '
            f'stroke="#334155" stroke-width="0.5"/>\n'
        )
        val = max_val - (i / n_grids) * val_range
        label = _format_chart_value(val, currency)
        grid_svg += (
            f'<text x="{ml - 5}" y="{gy + 3:.1f}" text-anchor="end" '
            f'fill="#64748b" font-size="9" '
            f'font-family="sans-serif">{label}</text>\n'
        )

    # X-axis date labels
    first_date = data_points[0]["date"]
    last_date = data_points[-1]["date"]

    # Legend positions
    leg_x = ml
    leg_y = height - 20

    return f"""
            <div style="margin-top: 10px;">
                <svg xmlns="http://www.w3.org/2000/svg"
                     viewBox="0 0 {width} {height}"
                     style="width:100%;height:auto;display:block;">
                    <rect width="{width}" height="{height}"
                          rx="6" fill="#1a2332"/>
                    {grid_svg}
                    <polygon points="{area_pts}"
                             fill="{actual_color}" opacity="0.08"/>
                    <polyline points="{ideal_pts}" fill="none"
                        stroke="{brand_color}" stroke-width="1.5"
                        stroke-dasharray="6,4" opacity="0.7"/>
                    <polyline points="{actual_pts}" fill="none"
                        stroke="{actual_color}" stroke-width="2"/>
                    <text x="{ml}" y="{height - 5}" fill="#64748b"
                        font-size="9"
                        font-family="sans-serif">{first_date}</text>
                    <text x="{width - mr}" y="{height - 5}"
                        text-anchor="end" fill="#64748b"
                        font-size="9"
                        font-family="sans-serif">{last_date}</text>
                    <line x1="{leg_x}" y1="{leg_y}"
                        x2="{leg_x + 20}" y2="{leg_y}"
                        stroke="{actual_color}" stroke-width="2"/>
                    <text x="{leg_x + 25}" y="{leg_y + 4}"
                        fill="#94a3b8" font-size="9"
                        font-family="sans-serif">Actual</text>
                    <line x1="{leg_x + 80}" y1="{leg_y}"
                        x2="{leg_x + 100}" y2="{leg_y}"
                        stroke="{brand_color}" stroke-width="1.5"
                        stroke-dasharray="6,4" opacity="0.7"/>
                    <text x="{leg_x + 105}" y="{leg_y + 4}"
                        fill="#94a3b8" font-size="9"
                        font-family="sans-serif">Ideal</text>
                </svg>
            </div>"""


def _load_chart_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a sans-serif font for chart rendering, with fallback."""
    for path in [
        "/usr/share/fonts/google-noto-vf/NotoSans[wght].ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _render_trend_chart_png(
    trend_data: Dict[str, Any],
    brand_color: str,
    currency: str = "USD",
) -> bytes:
    """
    Render a goal trend chart as a PNG image using Pillow.

    Mirrors _build_trend_chart_svg() visuals: dark background, grid lines,
    y-axis labels, dashed ideal line, solid actual line, area fill, legend.

    Rendered at 2x resolution (1320x400) for retina displays.
    Returns PNG bytes.
    """
    data_points = trend_data.get("data_points", [])
    if len(data_points) < 2:
        return b""

    # 2x resolution for retina — displayed at 660x200 via HTML width
    scale = 2
    width, height = 660 * scale, 200 * scale
    ml, mr, mt, mb = 65 * scale, 15 * scale, 20 * scale, 35 * scale
    cw = width - ml - mr
    ch = height - mt - mb

    # Extract values
    actual = [p["current_value"] for p in data_points]
    ideal = [p["ideal_value"] for p in data_points]
    all_vals = actual + ideal

    min_val = min(all_vals)
    max_val = max(all_vals)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = max_val * 0.1 or 1.0
    min_val -= val_range * 0.05
    max_val += val_range * 0.05
    val_range = max_val - min_val

    n = len(data_points)

    def sx(i):
        return ml + (i / (n - 1)) * cw

    def sy(v):
        return mt + (1 - (v - min_val) / val_range) * ch

    is_on_track = data_points[-1].get("on_track", False)
    actual_color = "#10b981" if is_on_track else "#f59e0b"

    # Parse hex colors to RGB tuples
    def hex_to_rgb(h: str) -> tuple:
        h = h.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    bg_rgb = hex_to_rgb("#1a2332")
    grid_rgb = hex_to_rgb("#334155")
    label_rgb = hex_to_rgb("#64748b")
    legend_text_rgb = hex_to_rgb("#94a3b8")
    actual_rgb = hex_to_rgb(actual_color)
    brand_rgb = hex_to_rgb(brand_color)

    # Create image
    img = Image.new("RGB", (width, height), bg_rgb)
    draw = ImageDraw.Draw(img, "RGBA")

    # Fonts (scaled)
    font_label = _load_chart_font(9 * scale)
    font_legend = _load_chart_font(9 * scale)

    # Grid lines + Y-axis labels
    n_grids = 4
    for i in range(n_grids + 1):
        gy = int(mt + (i / n_grids) * ch)
        draw.line([(ml, gy), (width - mr, gy)], fill=grid_rgb, width=1)
        val = max_val - (i / n_grids) * val_range
        label = _format_chart_value(val, currency)
        bbox = draw.textbbox((0, 0), label, font=font_label)
        tw = bbox[2] - bbox[0]
        draw.text((ml - 5 * scale - tw, gy - (bbox[3] - bbox[1]) // 2),
                  label, fill=label_rgb, font=font_label)

    # Build coordinate lists
    actual_coords = [(int(sx(i)), int(sy(v))) for i, v in enumerate(actual)]
    ideal_coords = [(int(sx(i)), int(sy(v))) for i, v in enumerate(ideal)]

    # Area fill under actual line (semi-transparent)
    area_fill_color = actual_rgb + (20,)  # ~8% opacity
    area_polygon = actual_coords + [
        (int(sx(n - 1)), int(mt + ch)),
        (int(sx(0)), int(mt + ch)),
    ]
    draw.polygon(area_polygon, fill=area_fill_color)

    # Ideal line (dashed)
    dash_len = 6 * scale
    gap_len = 4 * scale
    brand_rgba = brand_rgb + (179,)  # ~70% opacity
    for i in range(len(ideal_coords) - 1):
        x0, y0 = ideal_coords[i]
        x1, y1 = ideal_coords[i + 1]
        dx = x1 - x0
        dy = y1 - y0
        seg_len = (dx ** 2 + dy ** 2) ** 0.5
        if seg_len == 0:
            continue
        ux, uy = dx / seg_len, dy / seg_len
        pos = 0.0
        drawing = True
        while pos < seg_len:
            step = dash_len if drawing else gap_len
            end = min(pos + step, seg_len)
            if drawing:
                draw.line(
                    [(int(x0 + ux * pos), int(y0 + uy * pos)),
                     (int(x0 + ux * end), int(y0 + uy * end))],
                    fill=brand_rgba, width=max(1, int(1.5 * scale)),
                )
            pos = end
            drawing = not drawing

    # Actual line (solid)
    draw.line(actual_coords, fill=actual_rgb, width=2 * scale)

    # X-axis date labels
    first_date = data_points[0]["date"]
    last_date = data_points[-1]["date"]
    date_y = height - 5 * scale
    draw.text((ml, date_y - font_label.size), first_date,
              fill=label_rgb, font=font_label)
    last_bbox = draw.textbbox((0, 0), last_date, font=font_label)
    last_tw = last_bbox[2] - last_bbox[0]
    draw.text((width - mr - last_tw, date_y - font_label.size),
              last_date, fill=label_rgb, font=font_label)

    # Legend
    leg_x = ml
    leg_y = height - 20 * scale
    # Actual line sample
    draw.line([(leg_x, leg_y), (leg_x + 20 * scale, leg_y)],
              fill=actual_rgb, width=2 * scale)
    draw.text((leg_x + 25 * scale, leg_y - font_legend.size // 2),
              "Actual", fill=legend_text_rgb, font=font_legend)
    # Ideal line sample (dashed approximation — short solid segment)
    ideal_leg_x = leg_x + 80 * scale
    for dx in range(0, 20 * scale, (dash_len + gap_len)):
        end = min(dx + dash_len, 20 * scale)
        draw.line(
            [(ideal_leg_x + dx, leg_y), (ideal_leg_x + end, leg_y)],
            fill=brand_rgba, width=max(1, int(1.5 * scale)),
        )
    draw.text((ideal_leg_x + 25 * scale, leg_y - font_legend.size // 2),
              "Ideal", fill=legend_text_rgb, font=font_legend)

    # Export as PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _build_comparison_section(data: Dict[str, Any]) -> str:
    """Period-on-period comparison table."""
    prior = data.get("prior_period")
    if not prior:
        return ""

    period_days = data.get("period_days")
    trades_label = "Total Trades"
    if period_days:
        trades_label += f" (last {period_days}d)"

    rows = [
        ("Account Value", data.get("account_value_usd", 0),
         prior.get("account_value_usd", 0), "usd"),
        ("Period Profit", data.get("period_profit_usd", 0),
         prior.get("period_profit_usd", 0), "usd"),
        (trades_label, data.get("total_trades", 0),
         prior.get("total_trades", 0), "int"),
        ("Win Rate", data.get("win_rate", 0),
         prior.get("win_rate", 0), "pct"),
    ]

    table_rows = ""
    for label, current, previous, fmt in rows:
        if fmt == "usd":
            cur_str = f"${current:,.2f}"
            prev_str = f"${previous:,.2f}"
            change = current - previous
            change_str = f"{'+'if change >= 0 else ''}{change:,.2f}"
        elif fmt == "int":
            cur_str = str(int(current))
            prev_str = str(int(previous))
            change = current - previous
            change_str = f"{'+'if change >= 0 else ''}{int(change)}"
        else:
            cur_str = f"{current:.1f}%"
            prev_str = f"{previous:.1f}%"
            change = current - previous
            change_str = f"{'+'if change >= 0 else ''}{change:.1f}%"

        change_color = "#10b981" if change >= 0 else "#ef4444"

        table_rows += f"""
            <tr>
                <td style="padding: 8px 12px; border-bottom: 1px solid #334155;
                           color: #94a3b8; font-size: 13px;">{label}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #334155;
                           color: #f1f5f9; font-size: 13px; text-align: right;">
                    {cur_str}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #334155;
                           color: #94a3b8; font-size: 13px; text-align: right;">
                    {prev_str}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #334155;
                           color: {change_color}; font-size: 13px; text-align: right;
                           font-weight: 600;">{change_str}</td>
            </tr>"""

    return f"""
    <div style="margin: 25px 0;">
        <h3 style="color: #94a3b8; font-size: 13px; text-transform: uppercase;
                   letter-spacing: 1px; margin: 0 0 15px 0;">
            Period Comparison</h3>
        <table style="width: 100%; border-collapse: collapse; background-color: #1e293b;
                      border-radius: 8px; border: 1px solid #334155;">
            <thead>
                <tr>
                    <th style="padding: 10px 12px; text-align: left; color: #64748b;
                               font-size: 12px; border-bottom: 1px solid #334155;">
                        Metric</th>
                    <th style="padding: 10px 12px; text-align: right; color: #64748b;
                               font-size: 12px; border-bottom: 1px solid #334155;">
                        Current</th>
                    <th style="padding: 10px 12px; text-align: right; color: #64748b;
                               font-size: 12px; border-bottom: 1px solid #334155;">
                        Previous</th>
                    <th style="padding: 10px 12px; text-align: right; color: #64748b;
                               font-size: 12px; border-bottom: 1px solid #334155;">
                        Change</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>"""
