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
) -> str:
    """
    Build the full HTML report.

    Args:
        report_data: Metrics dictionary
        ai_summary: AI-generated summary — dict of tiers, plain string, or None
        user_name: User's display name or email
        period_label: e.g. "January 1 - January 7, 2026"
        default_level: Which tier gets visual prominence

    Returns:
        Complete HTML string
    """
    b = get_brand()
    brand_color = b["colors"]["primary"]

    metrics_html = _build_metrics_section(report_data)
    goals_html = _build_goals_section(report_data.get("goals", []))
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
    {_report_header(b, user_name, period_label, brand_color)}
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
) -> str:
    """Report header with brand name and period."""
    return f"""
    <div style="text-align: center; padding: 25px 0; border-bottom: 1px solid #334155;">
        <h1 style="color: {brand_color}; margin: 0; font-size: 26px;">{brand['shortName']}</h1>
        <p style="color: #94a3b8; margin: 5px 0 0 0; font-size: 14px;">
            {brand['tagline']}</p>
    </div>
    <div style="padding: 20px 0 10px 0;">
        <h2 style="color: #f1f5f9; margin: 0 0 5px 0; font-size: 20px;">
            Performance Report</h2>
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

    profit_color = "#10b981" if profit_usd >= 0 else "#ef4444"
    profit_sign = "+" if profit_usd >= 0 else ""

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
                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">Total Trades</p>
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
            </tr>
        </table>
    </div>"""


def _build_goals_section(goals: List[Dict[str, Any]]) -> str:
    """Goal progress bars."""
    if not goals:
        return ""

    goal_rows = ""
    for g in goals:
        if g.get("target_type") == "income":
            goal_rows += _build_income_goal_card(g)
        else:
            goal_rows += _build_standard_goal_card(g)

    return f"""
    <div style="margin: 25px 0;">
        <h3 style="color: #94a3b8; font-size: 13px; text-transform: uppercase;
                   letter-spacing: 1px; margin: 0 0 15px 0;">Goal Progress</h3>
        {goal_rows}
    </div>"""


def _build_standard_goal_card(g: Dict[str, Any]) -> str:
    """Standard balance/profit/both goal card with progress bar."""
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


def _build_comparison_section(data: Dict[str, Any]) -> str:
    """Period-on-period comparison table."""
    prior = data.get("prior_period")
    if not prior:
        return ""

    rows = [
        ("Account Value", data.get("account_value_usd", 0),
         prior.get("account_value_usd", 0), "usd"),
        ("Period Profit", data.get("period_profit_usd", 0),
         prior.get("period_profit_usd", 0), "usd"),
        ("Total Trades", data.get("total_trades", 0),
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


def generate_pdf(
    html_content: str,
    report_data: Optional[Dict] = None,
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
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 10, "Performance Report", new_x="LMARGIN", new_y="NEXT")
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

        metrics = [
            ("Account Value", f"${value_usd:,.2f} ({value_btc:.6f} BTC)"),
            ("Period Profit", f"${profit_usd:,.2f}"),
            ("Total Trades", str(total_trades)),
            ("Win Rate", f"{win_rate:.1f}%"),
            ("Winning Trades", str(report_data.get("winning_trades", 0))),
            ("Losing Trades", str(report_data.get("losing_trades", 0))),
        ]

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
                    pdf.cell(
                        0, 7,
                        f"{g.get('name', '')} (Income/{period.capitalize()}) - {status}",
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
                else:
                    pdf.cell(
                        0, 7,
                        f"{g.get('name', '')}: {pct:.1f}% "
                        f"({pfx}{g.get('current_value', 0)} / "
                        f"{pfx}{g.get('target_value', 0)} {curr}) - {status}",
                        new_x="LMARGIN", new_y="NEXT",
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
            pdf.multi_cell(0, 6, raw_summary)

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
        pdf.multi_cell(0, 6, text)


def _hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color string to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )
