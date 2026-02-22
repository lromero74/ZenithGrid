"""
Report Generator Service

Builds HTML report content and generates PDF from it.
Reuses brand styling from email_service (dark theme).

Supports tiered AI summaries (beginner/comfortable/experienced) and
uses the brand's primary accent color instead of hardcoded blue.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from app.services.brand_service import get_brand

logger = logging.getLogger(__name__)

# Tier display labels
_TIER_LABELS = {
    "beginner": "Summary (Simplified)",
    "comfortable": "AI Performance Analysis",
    "experienced": "Technical Analysis",
}


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

    Returns:
        Complete HTML string
    """
    b = get_brand()
    brand_color = b["colors"]["primary"]

    metrics_html = _build_metrics_section(report_data)
    goals_html = _build_goals_section(report_data.get("goals", []), brand_color)
    comparison_html = _build_comparison_section(report_data)

    tiered = _normalize_ai_summary(ai_summary)
    ai_html = ""
    if tiered:
        ai_html = _build_tiered_ai_section(tiered, default_level, brand_color)
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
    {goals_html}
    {comparison_html}
    {ai_html}
    {_report_footer(b)}
</div>
</body>
</html>"""


def _build_tiered_ai_section(
    ai_summary: dict,
    default_level: str,
    brand_color: str,
) -> str:
    """
    Render all available tiers as stacked sections.

    The default_level tier gets brand-colored left border and full prominence.
    Other tiers are visually secondary (gray border, muted text).
    Email-safe — no JS, no interactive elements.
    """
    sections = []
    tier_order = ["beginner", "comfortable", "experienced"]

    for tier in tier_order:
        text = ai_summary.get(tier)
        if not text:
            continue

        label = _TIER_LABELS.get(tier, tier.capitalize())
        is_default = tier == default_level

        paragraphs = text.strip().split("\n\n")
        rendered_paragraphs = "".join(
            f'<p style="color: {"#cbd5e1" if is_default else "#94a3b8"}; '
            f'line-height: 1.7; margin: 0 0 12px 0; '
            f'font-size: {"14px" if is_default else "13px"};">'
            f"{p.strip()}</p>"
            for p in paragraphs
            if p.strip()
        )

        if is_default:
            sections.append(f"""
        <div style="margin: 25px 0; padding: 20px; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155;
                    border-left: 4px solid {brand_color};">
            <h3 style="color: {brand_color}; margin: 0 0 15px 0; font-size: 16px;">
                {label}</h3>
            {rendered_paragraphs}
        </div>""")
        else:
            sections.append(f"""
        <div style="margin: 15px 0; padding: 16px; background-color: #1a2332;
                    border-radius: 8px; border: 1px solid #2d3a4a;
                    border-left: 4px solid #475569;">
            <h4 style="color: #94a3b8; margin: 0 0 10px 0; font-size: 13px;
                       text-transform: uppercase; letter-spacing: 0.5px;">
                {label}</h4>
            {rendered_paragraphs}
        </div>""")

    return "\n".join(sections)


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
    if net_deposits != 0 and adjusted_growth is not None:
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
) -> str:
    """Goal progress bars with optional trend charts."""
    if not goals:
        return ""

    goal_rows = ""
    for g in goals:
        if g.get("target_type") == "income":
            goal_rows += _build_income_goal_card(g)
        elif g.get("target_type") == "expenses":
            goal_rows += _build_expenses_goal_card(g)
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


def _build_expenses_goal_card(g: Dict[str, Any]) -> str:
    """Expenses goal card with coverage waterfall and itemized table."""
    coverage = g.get("expense_coverage", {})
    pct = coverage.get("coverage_pct", 0)
    bar_color = "#10b981" if pct >= 100 else "#f59e0b" if pct >= 50 else "#ef4444"
    bar_width = min(pct, 100)
    currency = g.get("target_currency", "USD")
    fmt = ".8f" if currency == "BTC" else ",.2f"
    prefix = "" if currency == "BTC" else "$"
    period = g.get("expense_period", "monthly")
    tax_pct = g.get("tax_withholding_pct", 0)

    total_exp = coverage.get("total_expenses", 0)
    income_at = coverage.get("income_after_tax", 0)
    covered = coverage.get("covered_count", 0)
    total = coverage.get("total_count", 0)

    # Build itemized table rows
    item_rows = ""
    for item in coverage.get("items", []):
        status = item.get("status", "uncovered")
        if status == "covered":
            badge_bg, badge_color, badge_text = "#065f46", "#6ee7b7", "Covered"
        elif status == "partial":
            cp = item.get("coverage_pct", 0)
            badge_bg, badge_color, badge_text = "#78350f", "#fcd34d", f"{cp:.0f}%"
        else:
            badge_bg, badge_color, badge_text = "#7f1d1d", "#fca5a5", "Uncovered"

        norm = item.get("normalized_amount", 0)
        item_rows += f"""
            <tr>
                <td style="padding: 4px 0; color: #94a3b8; font-size: 11px;">
                    {item.get('category', '')}</td>
                <td style="padding: 4px 0; color: #f1f5f9; font-size: 12px;">
                    {item.get('name', '')}</td>
                <td style="padding: 4px 0; color: #f1f5f9; text-align: right; font-size: 12px;">
                    {prefix}{norm:{fmt}}</td>
                <td style="padding: 4px 6px; text-align: center;">
                    <span style="background: {badge_bg}; color: {badge_color};
                                 padding: 1px 6px; border-radius: 4px; font-size: 10px;
                                 font-weight: 600;">{badge_text}</span></td>
            </tr>"""

    dep = g.get("deposit_needed")
    dep_line = ""
    if dep is not None:
        dep_line = f"""
            <p style="color: #94a3b8; font-size: 11px; margin: 8px 0 0 0;">
                Deposit needed to cover all expenses: {prefix}{dep:{fmt}} {currency}</p>"""

    tax_line = ""
    if tax_pct > 0:
        tax_line = f"""
                <tr>
                    <td style="padding: 4px 0; color: #94a3b8;">Tax Withholding</td>
                    <td style="padding: 4px 0; color: #f1f5f9; text-align: right;">
                        {tax_pct:.1f}%</td>
                </tr>"""

    return f"""
        <div style="margin: 0 0 15px 0; padding: 12px; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155;">
            <div style="display: flex; justify-content: space-between; align-items: center;
                        margin: 0 0 8px 0;">
                <span style="color: #f1f5f9; font-weight: 600; font-size: 14px;">
                    {g.get('name', '')}
                    <span style="color: #94a3b8; font-weight: 400; font-size: 12px;
                                 margin-left: 6px;">Expenses / {period.capitalize()}</span>
                </span>
                <span style="color: {bar_color}; font-size: 12px; font-weight: 600;">
                    {pct:.0f}% Covered</span>
            </div>
            <div style="background-color: #334155; border-radius: 4px; height: 8px;
                        overflow: hidden; margin-bottom: 10px;">
                <div style="background-color: {bar_color}; width: {bar_width}%;
                            height: 100%; border-radius: 4px;"></div>
            </div>
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
            {dep_line}
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


def _sanitize_for_pdf(text: str) -> str:
    """Replace Unicode characters unsupported by Helvetica (Latin-1) with ASCII equivalents."""
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

        # Add deposit/withdrawal metrics to PDF if present
        pdf_net_deposits = report_data.get("net_deposits_usd", 0)
        pdf_adj_growth = report_data.get("adjusted_account_growth_usd")
        if pdf_net_deposits != 0 and pdf_adj_growth is not None:
            dep_sign = "+" if pdf_net_deposits >= 0 else "-"
            adj_sign = "+" if pdf_adj_growth >= 0 else "-"
            metrics.append(
                ("Net Deposits", f"{dep_sign}${abs(pdf_net_deposits):,.2f}")
            )
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
                        f"- {cov_pct:.0f}% Covered",
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
                            f"{ei.get('coverage_pct', 0):.0f}%" if s == "partial"
                            else "X"
                        )
                        norm = ei.get("normalized_amount", 0)
                        pdf.cell(
                            0, 5,
                            f"  [{badge}] {ei.get('name', '')} - "
                            f"{pfx}{norm:,.2f}/{exp_period}",
                            new_x="LMARGIN", new_y="NEXT",
                        )
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
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(0, 6, _sanitize_for_pdf(text))


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
