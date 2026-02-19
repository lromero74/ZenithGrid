"""
Report Generator Service

Builds HTML report content and generates PDF from it.
Reuses brand styling from email_service (dark theme).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.brand_service import get_brand

logger = logging.getLogger(__name__)


def build_report_html(
    report_data: Dict[str, Any],
    ai_summary: Optional[str],
    user_name: str,
    period_label: str,
) -> str:
    """
    Build the full HTML report.

    Args:
        report_data: Metrics dictionary
        ai_summary: AI-generated summary text (or None)
        user_name: User's display name or email
        period_label: e.g. "January 1 - January 7, 2026"

    Returns:
        Complete HTML string
    """
    b = get_brand()

    # Key metrics section
    metrics_html = _build_metrics_section(report_data)

    # Goal progress section
    goals_html = _build_goals_section(report_data.get("goals", []))

    # Period comparison section
    comparison_html = _build_comparison_section(report_data)

    # AI summary section
    ai_html = ""
    if ai_summary:
        paragraphs = ai_summary.strip().split("\n\n")
        ai_paragraphs = "".join(
            f'<p style="color: #cbd5e1; line-height: 1.7; margin: 0 0 12px 0;">'
            f'{p.strip()}</p>'
            for p in paragraphs if p.strip()
        )
        ai_html = f"""
        <div style="margin: 25px 0; padding: 20px; background-color: #1e293b;
                    border-radius: 8px; border: 1px solid #334155;">
            <h3 style="color: #3b82f6; margin: 0 0 15px 0; font-size: 16px;">
                AI Performance Analysis</h3>
            {ai_paragraphs}
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
    {_report_header(b, user_name, period_label)}
    {metrics_html}
    {goals_html}
    {comparison_html}
    {ai_html}
    {_report_footer(b)}
</div>
</body>
</html>"""


def _report_header(brand: dict, user_name: str, period_label: str) -> str:
    """Report header with brand name and period."""
    return f"""
    <div style="text-align: center; padding: 25px 0; border-bottom: 1px solid #334155;">
        <h1 style="color: #3b82f6; margin: 0; font-size: 26px;">{brand['shortName']}</h1>
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

        goal_rows += f"""
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

    return f"""
    <div style="margin: 25px 0;">
        <h3 style="color: #94a3b8; font-size: 13px; text-transform: uppercase;
                   letter-spacing: 1px; margin: 0 0 15px 0;">Goal Progress</h3>
        {goal_rows}
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


def generate_pdf(html_content: str, report_data: Optional[Dict] = None) -> Optional[bytes]:
    """
    Generate a PDF report using fpdf2.

    Since fpdf2 is not an HTML-to-PDF converter, we build the PDF
    directly from report_data (or extract key info from the HTML).

    Returns PDF bytes, or None on failure.
    """
    if not report_data:
        logger.warning("No report_data provided for PDF generation")
        return None

    try:
        from io import BytesIO

        from fpdf import FPDF

        b = get_brand()
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Header
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(59, 130, 246)  # blue-500
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

        # AI Summary
        ai_summary = report_data.get("_ai_summary")
        if ai_summary:
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 8, "AI Analysis", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 6, ai_summary)

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
