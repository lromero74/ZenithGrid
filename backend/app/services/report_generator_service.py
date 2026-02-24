"""
Report Generator Service

Builds HTML report content and generates PDF from it.
Reuses brand styling from email_service (dark theme).

Supports tiered AI summaries (beginner/comfortable/experienced) and
uses the brand's primary accent color instead of hardcoded blue.
"""

import json
import logging
import re as _re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import markdown as _md

from app.services.brand_service import get_brand

logger = logging.getLogger(__name__)


def _fmt_coverage_pct(pct: float) -> str:
    """Format expense coverage percentage with adaptive precision.

    Small values get more decimals so they don't misleadingly round to 0%.
    - < 1%  → 2 decimals (e.g. "0.31%")
    - 1-10% → 1 decimal  (e.g. "3.2%")
    - >= 10% → 0 decimals (e.g. "67%")
    """
    if pct < 1:
        return f"{pct:.2f}%"
    elif pct < 10:
        return f"{pct:.1f}%"
    else:
        return f"{pct:.0f}%"


# Tier display labels
_TIER_LABELS = {
    "beginner": "Summary (Simplified)",
    "comfortable": "AI Performance Analysis",
    "experienced": "Technical Analysis",
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
    Normalize ai_summary to a tiered dict.

    Handles:
      - None → None
      - str → {"comfortable": str, "beginner": None, "experienced": None}
      - dict → pass through
      - JSON string of a dict → parsed dict
    """
    if ai_summary is None:
        return None

    if isinstance(ai_summary, dict):
        return ai_summary

    if isinstance(ai_summary, str):
        # Try to parse as JSON dict (stored in DB as json.dumps)
        try:
            parsed = json.loads(ai_summary)
            if isinstance(parsed, dict) and "comfortable" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        # Plain text — wrap as comfortable tier
        return {
            "beginner": None,
            "comfortable": ai_summary,
            "experienced": None,
        }

    return None


def build_report_html(
    report_data: Dict[str, Any],
    ai_summary: Union[None, str, dict],
    user_name: str,
    period_label: str,
    default_level: str = "comfortable",
    schedule_name: Optional[str] = None,
    email_mode: bool = False,
) -> str:
    """
    Build the full HTML report.

    Args:
        report_data: Metrics dictionary
        ai_summary: AI-generated summary — dict of tiers, plain string, or None
        user_name: User's display name or email
        period_label: e.g. "January 1 - January 7, 2026"
        default_level: Which tier gets visual prominence
        schedule_name: Optional report schedule name (shown as title)
        email_mode: If True, show only the default tier (email clients strip JS)

    Returns:
        Complete HTML string
    """
    b = get_brand()
    brand_color = b["colors"]["primary"]

    metrics_html = _build_metrics_section(report_data)
    transfers_html = _build_transfers_section(report_data)
    goals_html = _build_goals_section(
        report_data.get("goals", []), brand_color, email_mode=email_mode,
    )
    comparison_html = _build_comparison_section(report_data)

    tiered = _normalize_ai_summary(ai_summary)
    ai_html = ""
    if tiered:
        if email_mode:
            ai_html = _build_email_ai_section(tiered, default_level, brand_color)
        else:
            ai_html = _build_tabbed_ai_section(tiered, default_level, brand_color)
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
    {_report_header(b, user_name, period_label, brand_color, schedule_name)}
    {metrics_html}
    {transfers_html}
    {goals_html}
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
    tier_order = ["beginner", "comfortable", "experienced"]
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
        for tier in ["comfortable", "beginner", "experienced"]:
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
    schedule_name: Optional[str] = None,
) -> str:
    """Report header with brand name, report title, and period."""
    title = schedule_name or "Performance Report"
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
            {period_label} &mdash; Prepared for {user_name}</p>
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

    # Individual transfer rows
    transfer_rows = ""
    for rec in records:
        is_deposit = rec.get("type") == "deposit"
        color = "#10b981" if is_deposit else "#ef4444"
        sign = "+" if is_deposit else "-"
        amt = abs(rec.get("amount_usd", 0))
        label = rec.get("type", "").capitalize()
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
                {trade_row}{transfer_rows}
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

    return f"""
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


def _build_goals_section(
    goals: List[Dict[str, Any]], brand_color: str = "#3b82f6",
    email_mode: bool = False,
) -> str:
    """Goal progress bars with optional trend charts."""
    if not goals:
        return ""

    goal_rows = ""
    for g in goals:
        if g.get("target_type") == "income":
            goal_rows += _build_income_goal_card(g)
        elif g.get("target_type") == "expenses":
            goal_rows += _build_expenses_goal_card(g, email_mode=email_mode)
        else:
            goal_rows += _build_standard_goal_card(g, brand_color)

    return f"""
    <div style="margin: 25px 0;">
        <h3 style="color: #94a3b8; font-size: 13px; text-transform: uppercase;
                   letter-spacing: 1px; margin: 0 0 15px 0;">Goal Progress</h3>
        {goal_rows}
    </div>"""


def _build_standard_goal_card(
    g: Dict[str, Any], brand_color: str = "#3b82f6",
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

    # Trend chart SVG (if trend data is available)
    trend_svg = ""
    trend_data = g.get("trend_data")
    if trend_data:
        trend_svg = _build_trend_chart_svg(trend_data, brand_color, currency)

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
            {trend_svg}
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


_DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTH_ABBREVS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _ordinal_day(day: int) -> str:
    """Render a due day as ordinal ('1st', '15th') or 'Last' for -1."""
    if day == -1:
        return "Last"
    if 11 <= (day % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _next_biweekly_date(anchor_str: str, dow: int, today: datetime) -> datetime:
    """Find the next biweekly occurrence of `dow` based on anchor date.

    Args:
        anchor_str: ISO date string (YYYY-MM-DD) for the anchor/start date.
        dow: Day of week (0=Mon..6=Sun).
        today: Current datetime (only date part used).
    """
    anchor = datetime.strptime(anchor_str, "%Y-%m-%d")
    # If anchor hasn't started yet, return it
    if today.replace(hour=0, minute=0, second=0, microsecond=0) < anchor:
        return anchor
    # Find next occurrence of dow from today
    days_until = (dow - today.weekday()) % 7
    candidate = today.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_until)
    # Check week parity relative to anchor
    weeks_diff = (candidate - anchor).days // 7
    if weeks_diff % 2 != 0:
        # Off-week — push 7 days forward
        candidate += timedelta(days=7)
    return candidate


def _next_every_n_days_date(anchor_str: str, n: int, today: datetime) -> datetime:
    """Find the next every-N-days occurrence based on anchor date.

    Args:
        anchor_str: ISO date string (YYYY-MM-DD) for the anchor/start date.
        n: Number of days between occurrences.
        today: Current datetime (only date part used).
    """
    import math
    anchor = datetime.strptime(anchor_str, "%Y-%m-%d")
    today_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
    # If anchor hasn't started yet, return it
    if today_date < anchor:
        return anchor
    days_elapsed = (today_date - anchor).days
    # ceil to find next multiple of n that's >= days_elapsed
    cycles = math.ceil(days_elapsed / n)
    return anchor + timedelta(days=cycles * n)


def _get_upcoming_items(items: list, now: datetime) -> List:
    """Return upcoming expense items sorted by days until due, scoped to current month.

    Returns list of (sort_key, item) tuples.
    """
    import calendar

    today_day = now.day
    current_month = now.month
    today_dow = now.weekday()
    last_day_of_month = calendar.monthrange(now.year, now.month)[1]
    today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    _MULTI_MONTH_FREQS = {"quarterly", "semi_annual", "yearly"}
    _WEEKLY_FREQS = {"weekly", "biweekly"}

    upcoming = []
    for item in items:
        dd = item.get("due_day")
        freq = item.get("frequency", "monthly")
        anchor = item.get("frequency_anchor")

        # every_n_days: compute from anchor, no due_day needed
        if freq == "every_n_days" and anchor and item.get("frequency_n"):
            next_dt = _next_every_n_days_date(anchor, item["frequency_n"], now)
            if next_dt.month == now.month and next_dt.year == now.year:
                days_until = (next_dt - today_date).days
                upcoming.append((days_until, item))
            continue

        if dd is None:
            continue

        dm = item.get("due_month")

        if freq in _WEEKLY_FREQS:
            if freq == "biweekly" and anchor:
                next_dt = _next_biweekly_date(anchor, dd, now)
                days_until = (next_dt - today_date).days
            else:
                days_until = (dd - today_dow) % 7
                next_dt = now + timedelta(days=days_until)
            if next_dt.month == now.month and next_dt.year == now.year:
                upcoming.append((days_until, item))
            continue

        # For multi-month frequencies, check if this item is due this month
        if freq in _MULTI_MONTH_FREQS and dm is not None:
            if freq == "yearly" and current_month != dm:
                continue
            elif freq == "semi_annual":
                if current_month not in (dm, ((dm + 5) % 12) + 1):
                    continue
            elif freq == "quarterly":
                quarter_months = {((dm - 1 + 3 * i) % 12) + 1 for i in range(4)}
                if current_month not in quarter_months:
                    continue

        resolved = last_day_of_month if dd == -1 else min(dd, last_day_of_month)
        if resolved >= today_day:
            upcoming.append((resolved, item))

    upcoming.sort(key=lambda x: x[0])
    return upcoming


def _format_due_label(item: dict, now: Optional[datetime] = None) -> str:
    """Format a human-readable due label for an expense item."""
    freq = item.get("frequency", "monthly")
    dd = item.get("due_day")
    anchor = item.get("frequency_anchor")

    # every_n_days: compute from anchor, no due_day needed
    if freq == "every_n_days" and anchor and item.get("frequency_n"):
        if not now:
            return ""
        next_dt = _next_every_n_days_date(anchor, item["frequency_n"], now)
        return f"{_MONTH_ABBREVS[next_dt.month - 1]} {_ordinal_day(next_dt.day)}"

    if dd is None:
        return ""

    if freq in ("weekly", "biweekly"):
        dow_name = _DOW_NAMES[dd] if 0 <= dd <= 6 else str(dd)
        if now and 0 <= dd <= 6:
            # Use anchor-aware calc for biweekly if anchor is set
            if freq == "biweekly" and anchor:
                next_date = _next_biweekly_date(anchor, dd, now)
            else:
                days_until = (dd - now.weekday()) % 7
                next_date = now + timedelta(days=days_until)
            mon = _MONTH_ABBREVS[next_date.month - 1]
            return f"{dow_name} {mon} {_ordinal_day(next_date.day)}"
        return dow_name

    dm = item.get("due_month")
    day_str = _ordinal_day(dd)
    if freq in ("quarterly", "semi_annual", "yearly") and dm and 1 <= dm <= 12:
        return f"{_MONTH_ABBREVS[dm - 1]} {day_str}"
    # monthly/semi_monthly: show current month
    if now:
        return f"{_MONTH_ABBREVS[now.month - 1]} {day_str}"
    return day_str


def _build_expense_status_badge(item: dict) -> str:
    """Return an HTML badge span for an expense item's coverage status."""
    status = item.get("status", "uncovered")
    if status == "covered":
        badge_bg, badge_color, badge_text = "#065f46", "#6ee7b7", "Covered"
    elif status == "partial":
        cp = item.get("coverage_pct", 0)
        badge_bg, badge_color, badge_text = "#78350f", "#fcd34d", _fmt_coverage_pct(cp)
    else:
        badge_bg, badge_color, badge_text = "#7f1d1d", "#fca5a5", "Uncovered"
    return (
        f'<span style="background: {badge_bg}; color: {badge_color};'
        f' padding: 1px 6px; border-radius: 4px; font-size: 10px;'
        f' font-weight: 600;">{badge_text}</span>'
    )


def _expense_name_html(item: dict, color: str = "#f1f5f9") -> str:
    """Render expense name, linked to login_url if set."""
    name = item.get("name", "")
    url = item.get("login_url")
    if url:
        return (
            f'<a href="{url}" target="_blank" rel="noopener noreferrer"'
            f' style="color: {color}; text-decoration: underline;'
            f' text-decoration-color: #475569;">{name}</a>'
        )
    return name


def _build_expenses_goal_card(g: Dict[str, Any], email_mode: bool = False) -> str:
    """Expenses goal card with Coverage + Upcoming tabs."""
    from datetime import datetime as _dt

    coverage = g.get("expense_coverage", {})
    pct = coverage.get("coverage_pct", 0)
    bar_color = "#10b981" if pct >= 100 else "#f59e0b" if pct >= 50 else "#ef4444"
    bar_width = min(pct, 100)
    currency = g.get("target_currency", "USD")
    fmt = ".8f" if currency == "BTC" else ",.2f"
    prefix = "" if currency == "BTC" else "$"
    period = g.get("expense_period", "monthly")
    tax_pct = g.get("tax_withholding_pct", 0)
    goal_id = g.get("id", 0)

    total_exp = coverage.get("total_expenses", 0)
    income_at = coverage.get("income_after_tax", 0)
    covered = coverage.get("covered_count", 0)
    total = coverage.get("total_count", 0)
    items = coverage.get("items", [])

    # ---- Coverage tab content (existing) ----
    item_rows = ""
    for item in items:
        norm = item.get("normalized_amount", 0)
        item_rows += f"""
            <tr>
                <td style="padding: 4px 0; color: #94a3b8; font-size: 11px;">
                    {item.get('category', '')}</td>
                <td style="padding: 4px 0; color: #f1f5f9; font-size: 12px;">
                    {_expense_name_html(item)}</td>
                <td style="padding: 4px 0; color: #f1f5f9; text-align: right; font-size: 12px;">
                    {prefix}{norm:{fmt}}</td>
                <td style="padding: 4px 6px; text-align: center;">
                    {_build_expense_status_badge(item)}</td>
            </tr>"""

    dep = g.get("deposit_needed")
    dep_partial = g.get("deposit_partial")
    dep_next = g.get("deposit_next")
    dep_line = ""
    if dep is not None or coverage.get("partial_item_name") or coverage.get("next_uncovered_name"):
        dep_parts = []
        partial_name = coverage.get("partial_item_name")
        next_name = coverage.get("next_uncovered_name")

        if partial_name and dep_partial is not None:
            dep_parts.append(
                f"Finish covering <strong>{partial_name}</strong>: "
                f"deposit ~{prefix}{dep_partial:{fmt}} {currency}"
            )
            if next_name and dep_next is not None:
                dep_parts.append(
                    f"Then cover <strong>{next_name}</strong>: "
                    f"deposit ~{prefix}{dep_next:{fmt}} {currency} more"
                )
        elif next_name and dep_next is not None:
            dep_parts.append(
                f"Cover <strong>{next_name}</strong>: "
                f"deposit ~{prefix}{dep_next:{fmt}} {currency}"
            )

        if dep is not None:
            already_mentioned = (dep_partial or 0) + (dep_next or 0)
            additional = dep - already_mentioned
            if additional > 0 and already_mentioned > 0:
                dep_parts.append(
                    f"Cover all listed expenses: ~{prefix}{dep:{fmt}} {currency} total"
                    f" (+{prefix}{additional:{fmt}} {currency})"
                )
            else:
                dep_parts.append(
                    f"Cover all listed expenses: deposit ~{prefix}{dep:{fmt}} {currency} total"
                )

        dep_line = "".join(
            f'<p style="color: #94a3b8; font-size: 11px; margin: {4 if i else 8}px 0 0 0;">'
            f'{part}</p>'
            for i, part in enumerate(dep_parts)
        )

    tax_line = ""
    if tax_pct > 0:
        tax_line = f"""
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Tax Withholding</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {tax_pct:.1f}%</td>
                </tr>"""

    coverage_content = f"""
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;
                          margin-bottom: 10px;">
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Total Expenses</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {prefix}{total_exp:{fmt}} {currency}/{period}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Income After Tax</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {prefix}{income_at:{fmt}} {currency}/{period}</td>
                </tr>{tax_line}
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Items Covered</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {covered} / {total}</td>
                </tr>
            </table>
            <table style="width: 100%; border-collapse: collapse; border-top: 1px solid #334155;
                          padding-top: 8px;">
                <tr>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: left;
                               font-weight: 600;">Category</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: left;
                               font-weight: 600;">Name</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: right;
                               font-weight: 600;">Amount</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: center;
                               font-weight: 600;">Status</th>
                </tr>
                {item_rows}
            </table>
            {dep_line}"""

    # ---- Upcoming tab content ----
    now = _dt.utcnow()
    upcoming_raw = _get_upcoming_items(items, now)
    # Re-wrap tuples to include dd for template compatibility
    upcoming_items = [(sort_key, item.get("due_day"), item) for sort_key, item in upcoming_raw]

    has_any_due_day = any(
        item.get("due_day") is not None
        or (item.get("frequency") == "every_n_days" and item.get("frequency_anchor"))
        for item in items
    )
    if not upcoming_items and not has_any_due_day:
        upcoming_content = (
            '<p style="color: #64748b; font-size: 12px; text-align: center; padding: 16px 0;">'
            'Set due dates on your expenses to see upcoming bills</p>'
        )
    elif not upcoming_items:
        upcoming_content = (
            '<p style="color: #64748b; font-size: 12px; text-align: center; padding: 16px 0;">'
            'No upcoming expenses due this month</p>'
        )
    else:
        upcoming_rows = ""
        for _, dd, item in upcoming_items:
            bill_amount = item.get("amount", 0)
            due_label = _format_due_label(item, now=now)
            upcoming_rows += f"""
                <tr>
                    <td style="padding: 4px 0; color: #e2e8f0; font-size: 12px;
                               font-weight: 600;">{due_label}</td>
                    <td style="padding: 4px 0; color: #94a3b8; font-size: 11px;">
                        {item.get('category', '')}</td>
                    <td style="padding: 4px 0; color: #f1f5f9; font-size: 12px;">
                        {_expense_name_html(item)}</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right; font-size: 12px;">
                        {prefix}{bill_amount:{fmt}}</td>
                    <td style="padding: 4px 6px; text-align: center;">
                        {_build_expense_status_badge(item)}</td>
                </tr>"""
        upcoming_content = f"""
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: left;
                               font-weight: 600;">Due</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: left;
                               font-weight: 600;">Category</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: left;
                               font-weight: 600;">Name</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: right;
                               font-weight: 600;">Amount</th>
                    <th style="padding: 4px 0; color: #64748b; font-size: 10px; text-align: center;
                               font-weight: 600;">Status</th>
                </tr>
                {upcoming_rows}
            </table>"""

    # ---- Projection section (parallels income goal projections) ----
    projection_content = ""
    daily_inc = g.get("current_daily_income", 0)
    proj_linear = g.get("projected_income")
    proj_compound = g.get("projected_income_compound")
    sample = g.get("sample_trades", 0)
    lookback = g.get("lookback_days_used", 0)
    dep_compound = g.get("deposit_needed_compound")

    if daily_inc or proj_linear or proj_compound:
        after_tax_factor = (1 - tax_pct / 100) if tax_pct < 100 else 0
        linear_at = (proj_linear or 0) * after_tax_factor
        compound_at = (proj_compound or 0) * after_tax_factor

        dep_lin_str = f"{prefix}{dep:{fmt}}" if dep is not None else "N/A"
        dep_cmp_str = f"{prefix}{dep_compound:{fmt}}" if dep_compound is not None else "N/A"

        projection_content = f"""
            <div style="border-top: 1px solid #334155; margin-top: 10px; padding-top: 10px;">
                <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                    <tr>
                        <td style="padding: 4px 0; color: #94a3b8;">Target</td>
                        <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                            {prefix}{total_exp:{fmt}} {currency}/{period}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #94a3b8;">Daily Avg Income</td>
                        <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                            {prefix}{daily_inc:{fmt}} {currency}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #94a3b8;">Linear Projection</td>
                        <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                            {prefix}{linear_at:{fmt}} {currency}/{period} (after tax)</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #94a3b8;">Compound Projection</td>
                        <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                            {prefix}{compound_at:{fmt}} {currency}/{period} (after tax)</td>
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

    # ---- Card header (shared) ----
    header_html = f"""
        <div style="margin: 0 0 15px 0; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155; overflow: hidden;">
            <div style="padding: 12px 12px 0 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;
                            margin: 0 0 8px 0;">
                    <span style="color: #f1f5f9; font-weight: 600; font-size: 14px;">
                        {g.get('name', '')}
                        <span style="color: #94a3b8; font-weight: 400; font-size: 12px;
                                     margin-left: 6px;">Expenses / {period.capitalize()}</span>
                    </span>
                    <span style="color: {bar_color}; font-size: 12px; font-weight: 600;">
                        {_fmt_coverage_pct(pct)} Covered</span>
                </div>
                <div style="background-color: #334155; border-radius: 4px; height: 8px;
                            overflow: hidden; margin-bottom: 10px;">
                    <div style="background-color: {bar_color}; width: {bar_width}%;
                                height: 100%; border-radius: 4px;"></div>
                </div>
            </div>"""

    if email_mode:
        # ---- Email: stacked sections (no CSS tabs) ----
        section_hdr = (
            'style="color: #3b82f6; font-size: 12px; font-weight: 600;'
            ' padding: 8px 12px; margin: 0; border-bottom: 1px solid #334155;'
            ' background-color: #162032;"'
        )
        proj_block = ""
        if projection_content:
            proj_block = (
                f'<p {section_hdr}>Projections</p>'
                f'<div style="padding: 12px;">{projection_content}</div>'
            )
        return (
            f"{header_html}"
            f'<p {section_hdr}>Coverage</p>'
            f'<div style="padding: 12px;">{coverage_content}</div>'
            f'<p {section_hdr}>Upcoming</p>'
            f'<div style="padding: 12px;">{upcoming_content}</div>'
            f'{proj_block}'
            f'</div>'
        )

    # ---- In-app: CSS-only tabs ----
    tab_name = f"exp-tab-{goal_id}"
    cov_id = f"exp-tab-coverage-{goal_id}"
    upc_id = f"exp-tab-upcoming-{goal_id}"
    proj_id = f"exp-tab-proj-{goal_id}"
    cov_panel = f"exp-panel-coverage-{goal_id}"
    upc_panel = f"exp-panel-upcoming-{goal_id}"
    proj_panel = f"exp-panel-proj-{goal_id}"

    proj_css = ""
    if projection_content:
        proj_css = f"""
        #{proj_id}:checked ~ .exp-tab-bar-{goal_id} label[for="{proj_id}"]
            {{ background-color: #1e293b; color: #3b82f6; border-bottom-color: #3b82f6; }}
        #{proj_id}:checked ~ #{proj_panel}
            {{ display: block !important; }}"""

    css_rules = f"""
        #{cov_id}:checked ~ .exp-tab-bar-{goal_id} label[for="{cov_id}"]
            {{ background-color: #1e293b; color: #3b82f6; border-bottom-color: #3b82f6; }}
        #{cov_id}:checked ~ #{cov_panel}
            {{ display: block !important; }}
        #{upc_id}:checked ~ .exp-tab-bar-{goal_id} label[for="{upc_id}"]
            {{ background-color: #1e293b; color: #3b82f6; border-bottom-color: #3b82f6; }}
        #{upc_id}:checked ~ #{upc_panel}
            {{ display: block !important; }}{proj_css}
    """

    tab_label_style = (
        'padding: 8px 14px; cursor: pointer; font-size: 12px; font-weight: 600;'
        ' font-family: inherit; border-bottom: 2px solid transparent;'
        ' color: #64748b; transition: all 0.2s;'
    )

    proj_radio = ""
    proj_label = ""
    proj_panel_html = ""
    if projection_content:
        proj_radio = (
            f'<input type="radio" name="{tab_name}" id="{proj_id}" style="display:none">'
        )
        proj_label = f'<label for="{proj_id}" style="{tab_label_style}">Projections</label>'
        proj_panel_html = (
            f'<div id="{proj_panel}" style="display: none; padding: 12px;">'
            f'{projection_content}</div>'
        )

    return f"""
        <style>{css_rules}</style>
        {header_html}
            <input type="radio" name="{tab_name}" id="{cov_id}" style="display:none" checked>
            <input type="radio" name="{tab_name}" id="{upc_id}" style="display:none">
            {proj_radio}
            <div class="exp-tab-bar-{goal_id}" style="display: flex;
                        border-bottom: 1px solid #334155; background-color: #162032;">
                <label for="{cov_id}" style="{tab_label_style}">Coverage</label>
                <label for="{upc_id}" style="{tab_label_style}">Upcoming</label>
                {proj_label}
            </div>
            <div id="{cov_panel}" style="display: none; padding: 12px;">
                {coverage_content}
            </div>
            <div id="{upc_panel}" style="display: none; padding: 12px;">
                {upcoming_content}
            </div>
            {proj_panel_html}
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


# Regex to strip emoji characters (Helvetica lacks emoji glyphs)
_EMOJI_RE = _re.compile(
    "["
    "\U0001F300-\U0001F9FF"  # Misc Symbols, Emoticons, Supplemental Symbols
    "\U00002702-\U000027B0"  # Dingbats
    "\U0000FE00-\U0000FE0F"  # Variation Selectors
    "\U0000200D"             # Zero Width Joiner
    "\U000024C2-\U0001F251"  # Enclosed chars
    "]+",
)


def _sanitize_for_pdf(text: str) -> str:
    """Replace Unicode characters unsupported by Helvetica (Latin-1) with ASCII equivalents."""
    # Strip emoji first (they render in HTML but Helvetica lacks the glyphs)
    text = _EMOJI_RE.sub("", text)
    replacements = {
        "\u2013": "-",    # en-dash
        "\u2014": "--",   # em-dash
        "\u2018": "'",    # left single quote
        "\u2019": "'",    # right single quote
        "\u201c": '"',    # left double quote
        "\u201d": '"',    # right double quote
        "\u2026": "...",  # ellipsis
        "\u2022": "*",    # bullet
        "\u00a0": " ",    # non-breaking space
        "\u2032": "'",    # prime
        "\u2033": '"',    # double prime
        "\u2212": "-",    # minus sign
        "\u00b7": "*",    # middle dot
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Fallback: replace any remaining non-Latin-1 chars
    return text.encode("latin-1", errors="replace").decode("latin-1")


def generate_pdf(
    html_content: str,
    report_data: Optional[Dict] = None,
    schedule_name: Optional[str] = None,
) -> Optional[bytes]:
    """
    Generate a PDF report using fpdf2.

    Supports tiered AI summaries passed via report_data["_ai_summary"]
    (dict with beginner/comfortable/experienced keys, or plain string).

    Returns PDF bytes, or None on failure.
    """
    if not report_data:
        logger.warning("No report_data provided for PDF generation")
        return None

    try:
        from io import BytesIO

        from fpdf import FPDF

        b = get_brand()
        # Parse brand color hex to RGB for fpdf
        brand_hex = b["colors"]["primary"]
        br, bg, bb = _hex_to_rgb(brand_hex)

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Header
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(br, bg, bb)
        pdf.cell(0, 12, b["shortName"], new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(148, 163, 184)  # slate-400
        pdf.cell(0, 6, b["tagline"], new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(5)

        # Title
        title = _sanitize_for_pdf(schedule_name) if schedule_name else "Performance Report"
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(100, 100, 100)
        now_str = datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC")
        pdf.cell(0, 6, f"Generated on {now_str}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(8)

        # Key Metrics
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 8, "Key Metrics", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        value_usd = report_data.get("account_value_usd", 0)
        value_btc = report_data.get("account_value_btc", 0)
        profit_usd = report_data.get("period_profit_usd", 0)
        total_trades = report_data.get("total_trades", 0)
        win_rate = report_data.get("win_rate", 0)

        pdf_period_days = report_data.get("period_days")
        pdf_trades_label = "Total Trades"
        if pdf_period_days:
            pdf_trades_label += f" (last {pdf_period_days}d)"

        metrics = [
            ("Account Value", f"${value_usd:,.2f} ({value_btc:.6f} BTC)"),
            ("Period Profit", f"${profit_usd:,.2f}"),
            (pdf_trades_label, str(total_trades)),
            ("Win Rate", f"{win_rate:.1f}%"),
            ("Winning Trades", str(report_data.get("winning_trades", 0))),
            ("Losing Trades", str(report_data.get("losing_trades", 0))),
        ]

        # Always show capital movement metrics for full transparency
        pdf_start_val = report_data.get("period_start_value_usd", 0)
        pdf_net_deposits = report_data.get("net_deposits_usd", 0)
        pdf_total_dep = report_data.get("total_deposits_usd", 0)
        pdf_total_wth = report_data.get("total_withdrawals_usd", 0)
        pdf_adj_growth = report_data.get("adjusted_account_growth_usd", 0)
        metrics.append(("Period Start Value", f"${pdf_start_val:,.2f}"))
        dep_sign = "+" if pdf_net_deposits >= 0 else "-"
        metrics.append(
            ("Net Deposits", f"{dep_sign}${abs(pdf_net_deposits):,.2f}")
        )
        if pdf_total_dep or pdf_total_wth:
            metrics.append(
                ("  Deposits / Withdrawals",
                 f"${pdf_total_dep:,.2f} / ${pdf_total_wth:,.2f}")
            )
        adj_sign = "+" if pdf_adj_growth >= 0 else "-"
        metrics.append(
            ("Adjusted Growth", f"{adj_sign}${abs(pdf_adj_growth):,.2f}")
        )

        pdf.set_font("Helvetica", "", 10)
        for label, value in metrics:
            pdf.set_text_color(100, 100, 100)
            pdf.cell(60, 7, label + ":", new_x="RIGHT")
            pdf.set_text_color(30, 30, 30)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)

        # Capital Movements (trading summary + individual transfers)
        pdf_trade_summary = report_data.get("trade_summary")
        pdf_transfers = report_data.get("transfer_records", [])
        pdf_has_trades = (
            pdf_trade_summary
            and pdf_trade_summary.get("total_trades", 0) > 0
        )

        if pdf_has_trades or pdf_transfers:
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(
                0, 8, "Capital Movements",
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.ln(2)

            # Trading summary row
            if pdf_has_trades:
                ts = pdf_trade_summary
                net = ts["net_profit_usd"]
                t_sign = "+" if net >= 0 else ""
                w = ts["winning_trades"]
                lo = ts["losing_trades"]
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(30, 30, 30)
                pdf.cell(
                    80, 7,
                    f"Trading: {ts['total_trades']} trades ({w}W/{lo}L)",
                    new_x="RIGHT",
                )
                pdf.cell(
                    0, 7, f"{t_sign}${abs(net):,.2f}",
                    new_x="LMARGIN", new_y="NEXT", align="R",
                )
                pdf.set_font("Helvetica", "", 10)
                pdf.ln(2)

            # Column headers for transfers
            if pdf_transfers:
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(100, 100, 100)
                pdf.cell(40, 6, "Date", new_x="RIGHT")
                pdf.cell(40, 6, "Type", new_x="RIGHT")
                pdf.cell(0, 6, "Amount", new_x="LMARGIN", new_y="NEXT", align="R")
                for trec in pdf_transfers:
                    t_date = trec.get("date", "")
                    t_type = trec.get("type", "").capitalize()
                    t_amt = abs(trec.get("amount_usd", 0))
                    t_sign = "+" if trec.get("type") == "deposit" else "-"
                    pdf.set_text_color(100, 100, 100)
                    pdf.cell(40, 6, t_date, new_x="RIGHT")
                    pdf.cell(40, 6, t_type, new_x="RIGHT")
                    pdf.set_text_color(30, 30, 30)
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.cell(
                        0, 6, f"{t_sign}${t_amt:,.2f}",
                        new_x="LMARGIN", new_y="NEXT", align="R",
                    )
                    pdf.set_font("Helvetica", "", 10)

        # Goals
        goals = report_data.get("goals", [])
        if goals:
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 8, "Goal Progress", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 10)

            for g in goals:
                pct = g.get("progress_pct", 0)
                status = "On Track" if g.get("on_track") else "Behind"
                curr = g.get("target_currency", "USD")
                pfx = "$" if curr == "USD" else ""
                pdf.set_text_color(30, 30, 30)

                if g.get("target_type") == "income":
                    period = g.get("income_period", "monthly")
                    pdf.set_font("Helvetica", "B", 10)
                    goal_name = _sanitize_for_pdf(g.get("name", ""))
                    pdf.cell(
                        0, 7,
                        f"{goal_name} (Income/{period.capitalize()}) - {status}",
                        new_x="LMARGIN", new_y="NEXT",
                    )
                    pdf.set_font("Helvetica", "", 9)
                    pdf.set_text_color(80, 80, 80)
                    pdf.cell(
                        0, 6,
                        f"Target: {pfx}{g.get('target_value', 0)} {curr}/{period} | "
                        f"Linear: {pfx}{g.get('projected_income_linear', 0)} | "
                        f"Compound: {pfx}{g.get('projected_income_compound', 0)}",
                        new_x="LMARGIN", new_y="NEXT",
                    )
                    sample = g.get("sample_trades", 0)
                    lookback = g.get("lookback_days_used", 0)
                    pdf.cell(
                        0, 6,
                        f"Based on {sample} trades over {lookback} days",
                        new_x="LMARGIN", new_y="NEXT",
                    )
                    pdf.set_font("Helvetica", "", 10)
                elif g.get("target_type") == "expenses":
                    coverage = g.get("expense_coverage", {})
                    exp_period = g.get("expense_period", "monthly")
                    cov_pct = coverage.get("coverage_pct", 0)
                    total_exp = coverage.get("total_expenses", 0)
                    income_at = coverage.get("income_after_tax", 0)
                    pdf.set_font("Helvetica", "B", 10)
                    goal_name = _sanitize_for_pdf(g.get("name", ""))
                    pdf.cell(
                        0, 7,
                        f"{goal_name} (Expenses/{exp_period.capitalize()}) "
                        f"- {_fmt_coverage_pct(cov_pct)} Covered",
                        new_x="LMARGIN", new_y="NEXT",
                    )
                    pdf.set_font("Helvetica", "", 9)
                    pdf.set_text_color(80, 80, 80)
                    pdf.cell(
                        0, 6,
                        f"Total: {pfx}{total_exp:,.2f} {curr}/{exp_period} | "
                        f"Income after tax: {pfx}{income_at:,.2f}",
                        new_x="LMARGIN", new_y="NEXT",
                    )
                    # List expense items in waterfall order
                    for ei in coverage.get("items", []):
                        s = ei.get("status", "uncovered")
                        badge = "OK" if s == "covered" else (
                            _fmt_coverage_pct(ei.get('coverage_pct', 0))
                            if s == "partial" else "X"
                        )
                        norm = ei.get("normalized_amount", 0)
                        pdf.cell(
                            0, 5,
                            f"  [{badge}] {ei.get('name', '')} - "
                            f"{pfx}{norm:,.2f}/{exp_period}",
                            new_x="LMARGIN", new_y="NEXT",
                        )
                    # Deposit guidance lines
                    partial_name = coverage.get("partial_item_name")
                    next_name = coverage.get("next_uncovered_name")
                    dep_partial = g.get("deposit_partial")
                    dep_next = g.get("deposit_next")
                    if partial_name and dep_partial is not None:
                        pdf.cell(
                            0, 5,
                            f"  Finish covering {partial_name}: "
                            f"deposit ~{pfx}{dep_partial:,.2f} {curr}",
                            new_x="LMARGIN", new_y="NEXT",
                        )
                    if next_name and dep_next is not None:
                        label = "Then cover" if partial_name else "Cover"
                        pdf.cell(
                            0, 5,
                            f"  {label} {next_name}: "
                            f"deposit ~{pfx}{dep_next:,.2f} {curr}",
                            new_x="LMARGIN", new_y="NEXT",
                        )
                    dep = g.get("deposit_needed")
                    if dep is not None:
                        already = (dep_partial or 0) + (dep_next or 0)
                        extra = dep - already
                        if extra > 0 and already > 0:
                            dep_text = (
                                f"  Cover all: ~{pfx}{dep:,.2f} {curr} total"
                                f" (+{pfx}{extra:,.2f} {curr})"
                            )
                        else:
                            dep_text = (
                                f"  Cover all: deposit ~{pfx}{dep:,.2f} {curr} total"
                            )
                        pdf.cell(
                            0, 5, dep_text,
                            new_x="LMARGIN", new_y="NEXT",
                        )
                    # Upcoming expenses — reuse _get_upcoming_items
                    _now = datetime.utcnow()
                    _upcoming = _get_upcoming_items(
                        coverage.get("items", []), _now,
                    )
                    if _upcoming:
                        pdf.set_font("Helvetica", "B", 9)
                        pdf.set_text_color(80, 80, 80)
                        pdf.cell(
                            0, 6, "Upcoming:",
                            new_x="LMARGIN", new_y="NEXT",
                        )
                        pdf.set_font("Helvetica", "", 9)
                        for _, _ei in _upcoming:
                            _label = _format_due_label(_ei, now=_now)
                            _amt = _ei.get("amount", 0)
                            _s = _ei.get("status", "uncovered")
                            _badge = ("OK" if _s == "covered"
                                      else _fmt_coverage_pct(
                                          _ei.get('coverage_pct', 0))
                                      if _s == "partial" else "X")
                            pdf.cell(
                                0, 5,
                                f"  {_label} - [{_badge}] "
                                f"{_ei.get('name', '')} "
                                f"{pfx}{_amt:,.2f}",
                                new_x="LMARGIN", new_y="NEXT",
                            )
                    # Projection table
                    _daily_inc = g.get("current_daily_income", 0)
                    _proj_lin = g.get("projected_income")
                    _proj_cmp = g.get("projected_income_compound")
                    if _daily_inc or _proj_lin or _proj_cmp:
                        _tax = g.get("tax_withholding_pct", 0)
                        _atf = (1 - _tax / 100) if _tax < 100 else 0
                        _lin_at = (_proj_lin or 0) * _atf
                        _cmp_at = (_proj_cmp or 0) * _atf
                        _dep_lin = g.get("deposit_needed")
                        _dep_cmp = g.get("deposit_needed_compound")
                        pdf.set_font("Helvetica", "B", 9)
                        pdf.set_text_color(80, 80, 80)
                        pdf.cell(
                            0, 6, "Projections:",
                            new_x="LMARGIN", new_y="NEXT",
                        )
                        pdf.set_font("Helvetica", "", 9)
                        _proj_rows = [
                            ("Target", f"{pfx}{total_exp:,.2f} {curr}/{exp_period}"),
                            ("Daily Avg Income", f"{pfx}{_daily_inc:,.2f} {curr}"),
                            ("Linear (after tax)", f"{pfx}{_lin_at:,.2f} {curr}/{exp_period}"),
                            ("Compound (after tax)", f"{pfx}{_cmp_at:,.2f} {curr}/{exp_period}"),
                        ]
                        if _dep_lin is not None:
                            _proj_rows.append(("Deposit Needed (Linear)", f"{pfx}{_dep_lin:,.2f}"))
                        if _dep_cmp is not None:
                            _proj_rows.append(("Deposit Needed (Compound)", f"{pfx}{_dep_cmp:,.2f}"))
                        _smp = g.get("sample_trades", 0)
                        _lbk = g.get("lookback_days_used", 0)
                        _proj_rows.append(("Based on", f"{_smp} trades over {_lbk} days"))
                        for _lbl, _val in _proj_rows:
                            pdf.set_text_color(100, 100, 100)
                            pdf.cell(55, 5, f"  {_lbl}:", new_x="RIGHT")
                            pdf.set_text_color(30, 30, 30)
                            pdf.cell(0, 5, _val, new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Helvetica", "", 10)
                else:
                    goal_name = _sanitize_for_pdf(g.get("name", ""))
                    pdf.cell(
                        0, 7,
                        f"{goal_name}: {pct:.1f}% "
                        f"({pfx}{g.get('current_value', 0)} / "
                        f"{pfx}{g.get('target_value', 0)} {curr}) - {status}",
                        new_x="LMARGIN", new_y="NEXT",
                    )
                    # Render trend chart if data available
                    trend_data = g.get("trend_data")
                    if trend_data:
                        _render_pdf_trend_chart(
                            pdf, trend_data, (br, bg, bb),
                        )

        # Prior Period Comparison
        prior = report_data.get("prior_period")
        if prior:
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 8, "Period Comparison", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 10)

            comparisons = [
                ("Account Value",
                 f"${value_usd:,.2f}",
                 f"${prior.get('account_value_usd', 0):,.2f}"),
                ("Period Profit",
                 f"${profit_usd:,.2f}",
                 f"${prior.get('period_profit_usd', 0):,.2f}"),
            ]
            for label, current, previous in comparisons:
                pdf.set_text_color(100, 100, 100)
                pdf.cell(0, 7, f"{label}: {current} (prev: {previous})",
                         new_x="LMARGIN", new_y="NEXT")

        # AI Summary — render all tiers in PDF
        raw_summary = report_data.get("_ai_summary")
        tiered = _normalize_ai_summary(raw_summary)
        if tiered:
            _render_pdf_tiers(pdf, tiered, br, bg, bb)
        elif isinstance(raw_summary, str) and raw_summary:
            # Legacy plain string
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 8, "AI Analysis", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 6, _sanitize_for_pdf(raw_summary))

        # Footer
        pdf.ln(10)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 5, f"(c) {b['copyright']}", new_x="LMARGIN", new_y="NEXT", align="C")

        buffer = BytesIO()
        pdf.output(buffer)
        return buffer.getvalue()

    except ImportError:
        logger.warning("fpdf2 not installed, skipping PDF generation")
        return None
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return None


def _render_pdf_markdown(pdf, text: str, br: int, bg: int, bb: int):
    """Render markdown-formatted text into PDF with styled headers and bullets.

    Parses markdown line by line:
    - ### Header → bold, brand color, larger size
    - **bold** → handled by fpdf2's markdown=True
    - - bullet → rendered as indented bullet item
    - Regular text → multi_cell with markdown=True
    """
    sanitized = _sanitize_for_pdf(text)
    lines = sanitized.split("\n")
    buf = []  # accumulate regular paragraph lines

    def flush_buf():
        if buf:
            paragraph = " ".join(buf)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 6, paragraph, markdown=True)
            buf.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_buf()
            continue

        if stripped.startswith("### "):
            flush_buf()
            header_text = stripped[4:]
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(br, bg, bb)
            pdf.cell(0, 7, header_text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif stripped.startswith("- "):
            flush_buf()
            bullet_text = stripped[2:]
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            indent = pdf.l_margin + 5
            pdf.set_x(indent)
            avail_w = pdf.w - pdf.r_margin - indent
            pdf.multi_cell(avail_w, 6, "- " + bullet_text, markdown=True)
        else:
            buf.append(stripped)

    flush_buf()


def _render_pdf_tiers(pdf, tiered: dict, br: int, bg: int, bb: int):
    """Render all three AI tiers into the PDF."""
    tier_order = ["beginner", "comfortable", "experienced"]

    for tier in tier_order:
        text = tiered.get(tier)
        if not text:
            continue

        label = _TIER_LABELS.get(tier, tier.capitalize())

        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(br, bg, bb)
        pdf.cell(0, 8, label, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        _render_pdf_markdown(pdf, text, br, bg, bb)


def _render_pdf_trend_chart(pdf, trend_data: Dict, brand_rgb: tuple):
    """
    Draw a trend chart (actual vs ideal) in the PDF using fpdf2 lines.

    Args:
        pdf: fpdf2 FPDF instance
        trend_data: Dict from get_goal_trend_data() with data_points
        brand_rgb: (r, g, b) tuple for the ideal line color
    """
    data_points = trend_data.get("data_points", [])
    if len(data_points) < 2:
        return

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

    # Chart position and size
    chart_x = pdf.l_margin
    chart_y = pdf.get_y() + 3
    chart_w = pdf.w - pdf.l_margin - pdf.r_margin
    chart_h = 40
    n = len(data_points)

    # Check if we need a new page
    if chart_y + chart_h + 12 > pdf.h - pdf.b_margin:
        pdf.add_page()
        chart_y = pdf.get_y() + 3

    def px(i):
        return chart_x + (i / (n - 1)) * chart_w

    def py(v):
        return chart_y + (1 - (v - min_val) / val_range) * chart_h

    # Draw chart border
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.2)
    pdf.rect(chart_x, chart_y, chart_w, chart_h)

    # Draw ideal line (brand color, thin)
    pdf.set_draw_color(*brand_rgb)
    pdf.set_line_width(0.3)
    for i in range(n - 1):
        pdf.line(px(i), py(ideal[i]), px(i + 1), py(ideal[i + 1]))

    # Draw actual line (green/amber, thicker)
    is_on_track = data_points[-1].get("on_track", False)
    if is_on_track:
        pdf.set_draw_color(16, 185, 129)
    else:
        pdf.set_draw_color(245, 158, 11)
    pdf.set_line_width(0.5)
    for i in range(n - 1):
        pdf.line(px(i), py(actual[i]), px(i + 1), py(actual[i + 1]))

    # Reset
    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)

    # Date labels
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(120, 120, 120)
    first_date = data_points[0]["date"]
    last_date = data_points[-1]["date"]
    pdf.text(chart_x, chart_y + chart_h + 4, first_date)
    pdf.text(
        chart_x + chart_w - pdf.get_string_width(last_date),
        chart_y + chart_h + 4,
        last_date,
    )

    # Legend
    pdf.set_y(chart_y + chart_h + 6)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(
        0, 4,
        "--- Ideal trajectory    -- Actual progress",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 30, 30)


def _hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color string to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )
