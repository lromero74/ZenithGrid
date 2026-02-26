"""
PDF Generator — PDF report generation with fpdf2.

Part of the report_generator_service package.
"""

import logging
import re as _re
from datetime import datetime
from typing import Dict, Optional

from app.services.brand_service import get_brand
from app.services.report_generator_service.expense_builder import (
    _MONTH_ABBREVS,
    _fmt_coverage_pct,
    _format_due_label,
    _get_lookahead_items,
    _get_upcoming_items,
    _ordinal_day,
)
from app.services.report_generator_service.html_builder import (
    _TIER_LABELS,
    _normalize_ai_summary,
    _transfer_label,
)

logger = logging.getLogger(__name__)

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


def _truncate_to_width(pdf, text: str, max_width: float) -> str:
    """Truncate text with '...' suffix if it exceeds the given cell width (mm)."""
    if pdf.get_string_width(text) <= max_width:
        return text
    ellipsis = "..."
    ew = pdf.get_string_width(ellipsis)
    for i in range(len(text), 0, -1):
        if pdf.get_string_width(text[:i]) + ew <= max_width:
            return text[:i] + ellipsis
    return ellipsis


def _build_pdf_header(pdf, brand: Dict, brand_rgb: tuple):
    """Render the brand header: short name and tagline, centered."""
    br, bg, bb = brand_rgb
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(br, bg, bb)
    pdf.cell(0, 12, brand["shortName"], new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(148, 163, 184)  # slate-400
    pdf.cell(0, 6, brand["tagline"], new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)


def _build_pdf_metadata(
    pdf, schedule_name: Optional[str], account_name: Optional[str],
):
    """Render title, account name, and generation timestamp."""
    title = _sanitize_for_pdf(schedule_name) if schedule_name else "Performance Report"
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    if account_name:
        pdf.cell(
            0, 6,
            f"Account: {_sanitize_for_pdf(account_name)}",
            new_x="LMARGIN", new_y="NEXT",
        )
    now_str = datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC")
    pdf.cell(0, 6, f"Generated on {now_str}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)


def _build_pdf_metrics_table(pdf, report_data: Dict):
    """Render the Key Metrics section with all metric rows."""
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
    pdf_mve = report_data.get("market_value_effect_usd")
    if pdf_mve is not None:
        mve_sign = "+" if pdf_mve >= 0 else "-"
        metrics.append(
            ("Market Value Effect",
             f"{mve_sign}${abs(pdf_mve):,.2f}")
        )

    pdf.set_font("Helvetica", "", 10)
    for label, value in metrics:
        pdf.set_text_color(100, 100, 100)
        pdf.cell(60, 7, label + ":", new_x="RIGHT")
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)


def _build_pdf_goals_section(pdf, report_data: Dict, brand_rgb: tuple):
    """Render Goal Progress (income + standard) and Expense Coverage goals."""
    br, bg, bb = brand_rgb
    all_goals = report_data.get("goals", [])
    expense_goals = [g for g in all_goals if g.get("target_type") == "expenses"]
    other_goals = [g for g in all_goals if g.get("target_type") != "expenses"]

    # Goal Progress (income + standard goals) — rendered before Capital Movements
    if other_goals:
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 8, "Goal Progress", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)

        for g in other_goals:
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

    # Expense Coverage goals
    if expense_goals:
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 8, "Expense Coverage", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)

        for g in expense_goals:
            _build_pdf_expense_goal(pdf, g, report_data, brand_rgb)


def _build_pdf_expense_goal(pdf, g: Dict, report_data: Dict, brand_rgb: tuple):
    """Render a single expense coverage goal with tables and projections."""
    br, bg, bb = brand_rgb
    curr = g.get("target_currency", "USD")
    pfx = "$" if curr == "USD" else ""
    pdf.set_text_color(30, 30, 30)
    coverage = g.get("expense_coverage", {})
    exp_period = g.get("expense_period", "monthly")
    cov_pct = coverage.get("coverage_pct", 0)
    total_exp = coverage.get("total_expenses", 0)
    income_at = coverage.get("income_after_tax", 0)
    pdf.set_font("Helvetica", "B", 10)
    goal_name = _sanitize_for_pdf(g.get("name", ""))
    pdf.cell(
        0, 7,
        f"{goal_name} - Returns Cover "
        f"{_fmt_coverage_pct(cov_pct)} of "
        f"{exp_period.capitalize()} Expenses",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(
        0, 6,
        f"Total Required: {pfx}{total_exp:,.2f} {curr}/{exp_period} | "
        f"Income after tax: {pfx}{income_at:,.2f}",
        new_x="LMARGIN", new_y="NEXT",
    )
    # Trend chart
    trend_data = g.get("trend_data")
    if trend_data:
        _render_pdf_trend_chart(pdf, trend_data, (br, bg, bb))
    # Coverage items table header
    cov_items = coverage.get("items", [])
    if cov_items:
        _tbl_inset = 8
        _tbl_x = pdf.l_margin + _tbl_inset
        _tbl_w = pdf.w - pdf.l_margin - pdf.r_margin - 2 * _tbl_inset
        _buf = 4
        # Pre-compute display values
        _cov_rows = []
        for ei in cov_items:
            s = ei.get("status", "uncovered")
            badge = "OK" if s == "covered" else (
                _fmt_coverage_pct(ei.get('coverage_pct', 0))
                if s == "partial" else "X"
            )
            name = _sanitize_for_pdf(ei.get('name', ''))
            cat = ei.get('category', '')
            norm = ei.get("normalized_amount", 0)
            if ei.get("amount_mode") == "percent_of_income":
                pct_val = ei.get("percent_of_income", 0)
                basis_label = ei.get("percent_basis", "pre_tax")
                basis_str = "pre-tax" if basis_label == "pre_tax" else "post-tax"
                amt = f"{pfx}{norm:,.2f} ({pct_val:g}% {basis_str})"
            else:
                amt = f"{pfx}{norm:,.2f}/{exp_period}"
            _cov_rows.append((s, badge, name, cat, amt))
        # Measure column widths from content
        pdf.set_font("Helvetica", "", 9)
        col_status = max(
            pdf.get_string_width("Status"),
            max((pdf.get_string_width(r[1]) for r in _cov_rows), default=0),
        ) + _buf
        col_cat = max(
            pdf.get_string_width("Category"),
            max((pdf.get_string_width(r[3]) for r in _cov_rows), default=0),
        ) + _buf
        col_amt = max(
            pdf.get_string_width("Amount"),
            max((pdf.get_string_width(r[4]) for r in _cov_rows), default=0),
        ) + _buf
        col_name = _tbl_w - col_status - col_cat - col_amt
        # Ensure table fits on current page
        _cov_total_h = 5 + len(_cov_rows) * 5
        if pdf.will_page_break(_cov_total_h):
            pdf.add_page()
        # Draw header
        _tbl_y_start = pdf.get_y()
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(120, 120, 120)
        pdf.set_x(_tbl_x)
        pdf.cell(col_cat, 5, "Category", new_x="RIGHT")
        pdf.cell(col_name, 5, "Name", new_x="RIGHT")
        pdf.cell(col_amt, 5, "Amount", new_x="RIGHT", align="R")
        pdf.cell(col_status, 5, "Status", new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(200, 200, 205)
        pdf.line(_tbl_x, pdf.get_y(), _tbl_x + _tbl_w, pdf.get_y())
        # Draw rows
        pdf.set_font("Helvetica", "", 9)
        for _ri, (s, badge, name, cat, amt) in enumerate(_cov_rows):
            pdf.set_x(_tbl_x)
            if _ri % 2 == 1:
                pdf.set_fill_color(245, 245, 250)
                pdf.rect(_tbl_x, pdf.get_y(), _tbl_w, 5, "F")
            pdf.set_text_color(120, 120, 120)
            _c_txt = _truncate_to_width(pdf, cat, col_cat)
            pdf.cell(col_cat, 5, _c_txt, new_x="RIGHT")
            pdf.set_text_color(80, 80, 80)
            _n_txt = _truncate_to_width(pdf, name, col_name)
            pdf.cell(col_name, 5, _n_txt, new_x="RIGHT")
            pdf.set_text_color(80, 80, 80)
            pdf.cell(col_amt, 5, amt, new_x="RIGHT", align="R")
            if s == "covered":
                pdf.set_text_color(34, 197, 94)
            elif s == "partial":
                pdf.set_text_color(234, 179, 8)
            else:
                pdf.set_text_color(239, 68, 68)
            pdf.cell(
                col_status, 5, badge,
                new_x="LMARGIN", new_y="NEXT",
            )
        # Table outline
        pdf.set_draw_color(200, 200, 205)
        pdf.rect(_tbl_x, _tbl_y_start, _tbl_w, _cov_total_h)
        pdf.set_draw_color(0, 0, 0)
    # Expense changes from prior report
    _render_expense_changes_pdf(
        pdf, g.get("expense_changes"), pfx, curr,
    )
    partial_name = coverage.get("partial_item_name")
    next_name = coverage.get("next_uncovered_name")
    dep_partial = g.get("deposit_partial")
    dep_next = g.get("deposit_next")
    _has_dep_text = False
    if partial_name and dep_partial is not None:
        if not _has_dep_text:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(120, 120, 120)
            _has_dep_text = True
        pdf.cell(
            0, 5,
            f"Finish covering {partial_name}: "
            f"deposit ~{pfx}{dep_partial:,.2f} {curr}",
            new_x="LMARGIN", new_y="NEXT", align="C",
        )
    if next_name and dep_next is not None:
        label = "Then cover" if partial_name else "Cover"
        if not _has_dep_text:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(120, 120, 120)
            _has_dep_text = True
        pdf.cell(
            0, 5,
            f"{label} {next_name}: "
            f"deposit ~{pfx}{dep_next:,.2f} {curr}",
            new_x="LMARGIN", new_y="NEXT", align="C",
        )
    dep = g.get("deposit_needed")
    if dep is not None:
        already = (dep_partial or 0) + (dep_next or 0)
        extra = dep - already
        if extra > 0 and already > 0:
            dep_text = (
                f"Cover all: ~{pfx}{dep:,.2f} {curr} total"
                f" (+{pfx}{extra:,.2f} {curr})"
            )
        else:
            dep_text = (
                f"Cover all: deposit ~{pfx}{dep:,.2f} {curr} total"
            )
        if not _has_dep_text:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(120, 120, 120)
            _has_dep_text = True
        pdf.cell(
            0, 5, dep_text,
            new_x="LMARGIN", new_y="NEXT", align="C",
        )
    if _has_dep_text:
        pdf.ln(4)
    _now = datetime.utcnow()
    _upcoming = _get_upcoming_items(
        coverage.get("items", []), _now,
    )
    _meta = report_data.get("_schedule_meta", {})
    _pw = _meta.get("period_window", "full_prior")
    _show_la = _meta.get("show_expense_lookahead", True)
    _lookahead = []
    if _show_la and _pw in ("mtd", "wtd", "qtd", "ytd"):
        _lookahead = _get_lookahead_items(
            coverage.get("items", []), _now, _pw,
        )
    # Pre-compute display rows for both tables
    _uc_rows = []
    for _, _ei in _upcoming:
        _s = _ei.get("status", "uncovered")
        _badge = ("OK" if _s == "covered"
                  else _fmt_coverage_pct(
                      _ei.get('coverage_pct', 0))
                  if _s == "partial" else "X")
        _uc_rows.append((
            _format_due_label(_ei, now=_now),
            _ei.get('category', ''),
            _sanitize_for_pdf(_ei.get('name', '')),
            f"{pfx}{_ei.get('amount', 0):,.2f}",
            _s, _badge,
        ))
    _la_rows = []
    for _, _la_ei in _lookahead:
        _la_s = _la_ei.get("status", "uncovered")
        _la_badge = ("OK" if _la_s == "covered"
                     else _fmt_coverage_pct(
                         _la_ei.get('coverage_pct', 0))
                     if _la_s == "partial" else "X")
        _la_due = _la_ei.get("_lookahead_due_date")
        if _la_due:
            _la_lbl = (
                f"{_MONTH_ABBREVS[_la_due.month - 1]} "
                f"{_ordinal_day(_la_due.day)}"
            )
        else:
            _la_lbl = _format_due_label(_la_ei, now=_now)
        _la_rows.append((
            _la_lbl,
            _la_ei.get('category', ''),
            _sanitize_for_pdf(_la_ei.get('name', '')),
            f"{pfx}{_la_ei.get('amount', 0):,.2f}",
            _la_s, _la_badge,
        ))
    # Measure shared column widths across both tables
    _uc_inset = 8
    _uc_x = pdf.l_margin + _uc_inset
    _uc_w = pdf.w - pdf.l_margin - pdf.r_margin - 2 * _uc_inset
    _all_sched = _uc_rows + _la_rows
    if _all_sched:
        _buf = 4
        pdf.set_font("Helvetica", "", 9)
        uc_due = max(
            pdf.get_string_width("Due"),
            max((pdf.get_string_width(r[0]) for r in _all_sched), default=0),
        ) + _buf
        uc_cat = max(
            pdf.get_string_width("Category"),
            max((pdf.get_string_width(r[1]) for r in _all_sched), default=0),
        ) + _buf
        uc_amt = max(
            pdf.get_string_width("Amount"),
            max((pdf.get_string_width(r[3]) for r in _all_sched), default=0),
        ) + _buf
        uc_status = max(
            pdf.get_string_width("Status"),
            max((pdf.get_string_width(r[5]) for r in _all_sched), default=0),
        ) + _buf
        uc_name = _uc_w - uc_due - uc_cat - uc_amt - uc_status
    # --- Upcoming table ---
    if _uc_rows:
        # Ensure upcoming table fits on current page
        _uc_total_h = 5 + len(_uc_rows) * 5
        if pdf.will_page_break(6 + _uc_total_h):
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(
            0, 6, "Upcoming:",
            new_x="LMARGIN", new_y="NEXT",
        )
        _uc_y_start = pdf.get_y()
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(120, 120, 120)
        pdf.set_x(_uc_x)
        pdf.cell(uc_due, 5, "Due", new_x="RIGHT")
        pdf.cell(uc_cat, 5, "Category", new_x="RIGHT")
        pdf.cell(uc_name, 5, "Name", new_x="RIGHT")
        pdf.cell(uc_amt, 5, "Amount", new_x="RIGHT", align="R")
        pdf.cell(uc_status, 5, "Status", new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(200, 200, 205)
        pdf.line(_uc_x, pdf.get_y(), _uc_x + _uc_w, pdf.get_y())
        pdf.set_font("Helvetica", "", 9)
        for _ri, (due, cat, name, amt, _s, badge) in enumerate(_uc_rows):
            pdf.set_x(_uc_x)
            if _ri % 2 == 1:
                pdf.set_fill_color(245, 245, 250)
                pdf.rect(_uc_x, pdf.get_y(), _uc_w, 5, "F")
            pdf.set_text_color(80, 80, 80)
            pdf.cell(uc_due, 5, due, new_x="RIGHT")
            pdf.set_text_color(120, 120, 120)
            _c_txt = _truncate_to_width(pdf, cat, uc_cat)
            pdf.cell(uc_cat, 5, _c_txt, new_x="RIGHT")
            pdf.set_text_color(80, 80, 80)
            _n_txt = _truncate_to_width(pdf, name, uc_name)
            pdf.cell(uc_name, 5, _n_txt, new_x="RIGHT")
            pdf.cell(uc_amt, 5, amt, new_x="RIGHT", align="R")
            if _s == "covered":
                pdf.set_text_color(34, 197, 94)
            elif _s == "partial":
                pdf.set_text_color(234, 179, 8)
            else:
                pdf.set_text_color(239, 68, 68)
            pdf.cell(
                uc_status, 5, badge,
                new_x="LMARGIN", new_y="NEXT",
            )
        pdf.set_draw_color(200, 200, 205)
        pdf.rect(_uc_x, _uc_y_start, _uc_w, _uc_total_h)
        pdf.set_draw_color(0, 0, 0)
    # --- Lookahead table ---
    if _la_rows:
        pdf.ln(3)
        # Ensure lookahead table fits on current page
        _la_total_h = 5 + len(_la_rows) * 5
        if pdf.will_page_break(6 + _la_total_h):
            pdf.add_page()
        _la_labels = {
            "mtd": "Next Month",
            "wtd": "Next Week",
            "qtd": "Next Quarter",
            "ytd": "Next Year",
        }
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(
            0, 6,
            f"{_la_labels.get(_pw, 'Next Period')} Preview:",
            new_x="LMARGIN", new_y="NEXT",
        )
        _la_y_start = pdf.get_y()
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(150, 150, 150)
        pdf.set_x(_uc_x)
        pdf.cell(uc_due, 5, "Due", new_x="RIGHT")
        pdf.cell(uc_cat, 5, "Category", new_x="RIGHT")
        pdf.cell(uc_name, 5, "Name", new_x="RIGHT")
        pdf.cell(uc_amt, 5, "Amount", new_x="RIGHT", align="R")
        pdf.cell(uc_status, 5, "Status", new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(200, 200, 205)
        pdf.line(_uc_x, pdf.get_y(), _uc_x + _uc_w, pdf.get_y())
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(150, 150, 150)
        for _ri, (due, cat, name, amt, _s, badge) in enumerate(_la_rows):
            pdf.set_x(_uc_x)
            if _ri % 2 == 1:
                pdf.set_fill_color(245, 245, 250)
                pdf.rect(_uc_x, pdf.get_y(), _uc_w, 5, "F")
            pdf.cell(uc_due, 5, due, new_x="RIGHT")
            _c_txt = _truncate_to_width(pdf, cat, uc_cat)
            pdf.cell(uc_cat, 5, _c_txt, new_x="RIGHT")
            _n_txt = _truncate_to_width(pdf, name, uc_name)
            pdf.cell(uc_name, 5, _n_txt, new_x="RIGHT")
            pdf.cell(uc_amt, 5, amt, new_x="RIGHT", align="R")
            if _s == "covered":
                pdf.set_text_color(34, 197, 94)
            elif _s == "partial":
                pdf.set_text_color(234, 179, 8)
            else:
                pdf.set_text_color(239, 68, 68)
            pdf.cell(
                uc_status, 5, badge,
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.set_text_color(150, 150, 150)
        pdf.set_draw_color(200, 200, 205)
        pdf.rect(_uc_x, _la_y_start, _uc_w, _la_total_h)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_text_color(80, 80, 80)
    _daily_inc = g.get("current_daily_income", 0)
    _proj_lin = g.get("projected_income")
    _proj_cmp = g.get("projected_income_compound")
    if _daily_inc or _proj_lin or _proj_cmp:
        pdf.ln(3)
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


def _build_pdf_capital_movement(pdf, report_data: Dict):
    """Render Capital Movements: trading summary, staking rewards, and transfers table."""
    pdf_trade_summary = report_data.get("trade_summary")
    pdf_transfers = report_data.get("transfer_records", [])
    pdf_has_trades = (
        pdf_trade_summary
        and pdf_trade_summary.get("total_trades", 0) > 0
    )

    if not pdf_has_trades and not pdf_transfers:
        return

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

    # Staking rewards summary row (aggregated)
    pdf_staking = [
        r for r in pdf_transfers
        if r.get("original_type") == "send" and r.get("type") == "deposit"
    ]
    pdf_other = [r for r in pdf_transfers if r not in pdf_staking]
    if pdf_staking:
        stk_total = sum(abs(r.get("amount_usd", 0)) for r in pdf_staking)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(
            80, 7,
            f"Staking Rewards: {len(pdf_staking)} deposits",
            new_x="RIGHT",
        )
        pdf.cell(
            0, 7, f"+${stk_total:,.2f}",
            new_x="LMARGIN", new_y="NEXT", align="R",
        )
        pdf.set_font("Helvetica", "", 10)
        pdf.ln(2)

    # Individual transfers table (styled)
    if pdf_other:
        _tf_inset = 8
        _tf_x = pdf.l_margin + _tf_inset
        _tf_w = pdf.w - pdf.l_margin - pdf.r_margin - 2 * _tf_inset
        _tf_buf = 4
        # Pre-compute row display values
        _tf_rows = []
        for trec in pdf_other:
            t_date = trec.get("date", "")
            t_type = _transfer_label(trec)
            t_amt = abs(trec.get("amount_usd", 0))
            t_sign = "+" if trec.get("type") == "deposit" else "-"
            _tf_rows.append((t_date, t_type, f"{t_sign}${t_amt:,.2f}"))
        # Measure column widths
        pdf.set_font("Helvetica", "", 9)
        col_date = max(
            pdf.get_string_width("Date"),
            max((pdf.get_string_width(r[0]) for r in _tf_rows), default=0),
        ) + _tf_buf
        col_amt = max(
            pdf.get_string_width("Amount"),
            max((pdf.get_string_width(r[2]) for r in _tf_rows), default=0),
        ) + _tf_buf
        col_type = _tf_w - col_date - col_amt
        # Ensure table fits on current page to avoid split border
        _tf_total_h = 5 + len(_tf_rows) * 5
        if pdf.will_page_break(_tf_total_h):
            pdf.add_page()
        # Header
        _tf_y_start = pdf.get_y()
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(120, 120, 120)
        pdf.set_x(_tf_x)
        pdf.cell(col_date, 5, "Date", new_x="RIGHT")
        pdf.cell(col_type, 5, "Type", new_x="RIGHT")
        pdf.cell(
            col_amt, 5, "Amount",
            new_x="LMARGIN", new_y="NEXT", align="R",
        )
        pdf.set_draw_color(200, 200, 205)
        pdf.line(_tf_x, pdf.get_y(), _tf_x + _tf_w, pdf.get_y())
        # Rows
        pdf.set_font("Helvetica", "", 9)
        for _ri, (t_date, t_type, t_amt_str) in enumerate(_tf_rows):
            pdf.set_x(_tf_x)
            if _ri % 2 == 1:
                pdf.set_fill_color(245, 245, 250)
                pdf.rect(_tf_x, pdf.get_y(), _tf_w, 5, "F")
            pdf.set_text_color(100, 100, 100)
            pdf.cell(col_date, 5, t_date, new_x="RIGHT")
            pdf.set_text_color(80, 80, 80)
            _t_txt = _truncate_to_width(pdf, t_type, col_type)
            pdf.cell(col_type, 5, _t_txt, new_x="RIGHT")
            pdf.set_text_color(30, 30, 30)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(
                col_amt, 5, t_amt_str,
                new_x="LMARGIN", new_y="NEXT", align="R",
            )
            pdf.set_font("Helvetica", "", 9)
        # Table outline
        pdf.set_draw_color(200, 200, 205)
        pdf.rect(
            _tf_x, _tf_y_start, _tf_w, _tf_total_h,
        )
        pdf.set_draw_color(0, 0, 0)


def _build_pdf_comparison(pdf, report_data: Dict):
    """Render the Prior Period Comparison section."""
    prior = report_data.get("prior_period")
    if not prior:
        return

    value_usd = report_data.get("account_value_usd", 0)
    profit_usd = report_data.get("period_profit_usd", 0)

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


def _build_pdf_ai_section(pdf, report_data: Dict, brand_rgb: tuple):
    """Render the AI Summary section with tiered or legacy plain text."""
    br, bg, bb = brand_rgb
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


def _build_pdf_footer(pdf, brand: Dict):
    """Render the copyright footer."""
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, f"(c) {brand['copyright']}", new_x="LMARGIN", new_y="NEXT", align="C")


def generate_pdf(
    html_content: str,
    report_data: Optional[Dict] = None,
    schedule_name: Optional[str] = None,
    account_name: Optional[str] = None,
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
        brand_rgb = _hex_to_rgb(brand_hex)

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        _build_pdf_header(pdf, b, brand_rgb)
        _build_pdf_metadata(pdf, schedule_name, account_name)
        _build_pdf_metrics_table(pdf, report_data)
        _build_pdf_goals_section(pdf, report_data, brand_rgb)
        _build_pdf_capital_movement(pdf, report_data)
        _build_pdf_comparison(pdf, report_data)
        _build_pdf_ai_section(pdf, report_data, brand_rgb)
        _build_pdf_footer(pdf, b)

        buffer = BytesIO()
        pdf.output(buffer)
        return buffer.getvalue()

    except ImportError:
        logger.warning("fpdf2 not installed, skipping PDF generation")
        return None
    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        return None


def _render_expense_changes_pdf(pdf, changes: dict, prefix: str, curr: str):
    """Render expense changes section into PDF.

    Args:
        pdf: FPDF instance.
        changes: Dict with keys: increased, decreased, added, removed.
        prefix: Currency prefix ("$" or "").
        curr: Currency label ("USD" or "BTC").
    """
    if not changes:
        return

    section_config = [
        ("increased", "Increased", (239, 68, 68)),       # red
        ("decreased", "Decreased", (16, 185, 129)),      # green
        ("added", "Added", (245, 158, 11)),              # amber
        ("removed", "Removed", (16, 185, 129)),          # green
    ]

    has_any = any(changes.get(k) for k, _, _ in section_config)
    if not has_any:
        return

    # Estimate height needed (header + items)
    total_items = sum(len(changes.get(k, [])) for k, _, _ in section_config)
    est_height = 8 + total_items * 5 + 4 * 6  # header + rows + sub-headers
    if pdf.will_page_break(est_height):
        pdf.add_page()

    # Section header
    pdf.set_draw_color(180, 180, 190)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(100, 100, 110)
    pdf.cell(0, 5, "Changes from Prior Report", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    fmt = ".8f" if curr == "BTC" else ",.2f"

    for key, label, (r, g_c, b) in section_config:
        items = changes.get(key)
        if not items:
            continue

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(r, g_c, b)
        pdf.cell(0, 5, label, new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Helvetica", "", 8)
        for item in items:
            name = _sanitize_for_pdf(item.get("name", ""))
            amount = item.get("amount", 0)

            if key in ("increased", "decreased"):
                delta = item.get("delta", 0)
                pct = item.get("pct_delta", 0)
                sign = "+" if delta > 0 else ""
                right_text = (
                    f"{prefix}{amount:{fmt}}  "
                    f"{sign}{prefix}{delta:{fmt}} ({sign}{pct:.1f}%)"
                )
            elif key == "added":
                right_text = f"{prefix}{amount:{fmt}}  (new)"
            else:
                right_text = f"-{prefix}{amount:{fmt}}  (removed)"

            pdf.set_text_color(80, 80, 80)
            name_w = pdf.w - pdf.l_margin - pdf.r_margin - pdf.get_string_width(right_text) - 4
            name_txt = _truncate_to_width(pdf, name, name_w)
            pdf.cell(name_w, 4, name_txt, new_x="RIGHT")
            pdf.set_text_color(r, g_c, b)
            pdf.cell(0, 4, right_text, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.ln(2)
    pdf.set_draw_color(0, 0, 0)


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
            pdf.set_x(pdf.l_margin)  # Reset x after bullet indents
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
    tier_order = ["simple", "detailed"]

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
