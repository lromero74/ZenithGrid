"""
Expense Card — goal card header, tab assembly, full card renderer.

Part of the report_generator_service package.
"""

from typing import Any, Dict, List, Optional, Tuple

from app.services.report_generator_service.expense_schedule import (
    _fmt_coverage_pct,
)
from app.services.report_generator_service.expense_sections import (
    _build_expense_coverage_html,
    _build_expense_projection_html,
    _build_expense_upcoming_html,
)


def _build_expense_card_header(
    g: Dict[str, Any], pct: float, bar_color: str, period: str,
    goal_id: int, email_mode: bool, brand_color: str, currency: str,
    inline_images: Optional[List[Tuple[str, bytes]]],
) -> str:
    """Build card header: name, progress bar, trend chart, minimap."""
    bar_width = min(pct, 100)
    track_label = "On Track" if g.get("on_track") else "Behind"
    track_color = "#10b981" if g.get("on_track") else "#f59e0b"

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
                    <span style="font-size: 12px; font-weight: 600;">
                        <span style="color: {bar_color};">{_fmt_coverage_pct(pct)} Covered</span>
                        <span style="color: {track_color}; margin-left: 8px;">
                            &bull; {track_label}</span>
                    </span>
                </div>
                <div style="background-color: #334155; border-radius: 4px; height: 8px;
                            overflow: hidden; margin-bottom: 10px;">
                    <div style="background-color: {bar_color}; width: {bar_width}%;
                                height: 100%; border-radius: 4px;"></div>
                </div>
            </div>"""

    trend_data = g.get("trend_data")
    if trend_data:
        from app.services.report_generator_service.html_builder import (
            _build_trend_chart_svg,
        )
        from app.services.report_generator_service.chart_renderer import (
            _render_trend_chart_png,
        )
        if email_mode and inline_images is not None:
            png_bytes = _render_trend_chart_png(trend_data, brand_color, currency)
            if png_bytes:
                cid = f"goal-chart-{goal_id}"
                inline_images.append((cid, png_bytes))
                header_html += (
                    '<div style="padding: 0 12px 10px 12px;">'
                    f'<img src="cid:{cid}" width="660"'
                    ' style="width:100%;height:auto;display:block;'
                    'border-radius:6px;" alt="Expense coverage trend"/>'
                    '</div>'
                )
        else:
            svg_html = _build_trend_chart_svg(trend_data, brand_color, currency)
            header_html += (
                f'<div style="padding: 0 12px 10px 12px;">'
                f'{svg_html}</div>'
            )

    chart_settings = g.get("chart_settings", {})
    if chart_settings.get("show_minimap") and trend_data:
        try:
            from app.services.report_generator_service.html_builder import (
                _build_minimap_svg,
            )
            minimap_html = _build_minimap_svg(
                full_data_points=chart_settings.get("full_data_points", []),
                horizon_date=chart_settings.get("horizon_date", ""),
                target_date=chart_settings["target_date"],
                brand_color=brand_color,
                currency=currency,
            )
            header_html += minimap_html
        except (KeyError, ValueError):
            pass

    return header_html


def _build_expenses_goal_card(
    g: Dict[str, Any], email_mode: bool = False,
    schedule_meta: Optional[Dict[str, Any]] = None,
    brand_color: str = "#3b82f6",
    inline_images: Optional[List[Tuple[str, bytes]]] = None,
) -> str:
    """Expenses goal card with Coverage + Upcoming tabs."""
    coverage = g.get("expense_coverage", {})
    pct = coverage.get("coverage_pct", 0)
    bar_color = "#10b981" if pct >= 100 else "#f59e0b" if pct >= 50 else "#ef4444"
    currency = g.get("target_currency", "USD")
    fmt = ".8f" if currency == "BTC" else ",.2f"
    prefix = "" if currency == "BTC" else "$"
    period = g.get("expense_period", "monthly")
    tax_pct = g.get("tax_withholding_pct", 0)
    goal_id = g.get("goal_id") or g.get("id") or 0
    items = coverage.get("items", [])
    savings_targets = coverage.get("savings_targets", [])
    total_exp = coverage.get("total_expenses", 0)

    coverage_content = _build_expense_coverage_html(
        g, coverage, items, prefix, fmt, currency, period, tax_pct, savings_targets,
    )
    upcoming_content = _build_expense_upcoming_html(
        items, prefix, fmt, schedule_meta,
    )
    projection_content = _build_expense_projection_html(
        g, prefix, fmt, currency, period, total_exp, tax_pct,
    )
    header_html = _build_expense_card_header(
        g, pct, bar_color, period, goal_id, email_mode,
        brand_color, currency, inline_images,
    )

    if email_mode:
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

    return _build_expense_card_css_tabs(
        header_html, coverage_content, upcoming_content,
        projection_content, goal_id,
    )


def _build_expense_card_css_tabs(
    header_html: str, coverage_content: str, upcoming_content: str,
    projection_content: str, goal_id: int,
) -> str:
    """Assemble the in-app CSS-only tabbed card layout."""
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
