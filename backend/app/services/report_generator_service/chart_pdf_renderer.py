"""
Chart PDF Renderer — PDF trend chart and minimap rendering using fpdf2.

Extracted from pdf_generator.py to keep file sizes manageable.
"""

from datetime import datetime as _dt
from typing import Dict


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

    # Extract values (target endpoint may have current_value=None)
    actual = [p["current_value"] for p in data_points]
    ideal = [p["ideal_value"] for p in data_points]
    all_vals = [v for v in actual + ideal if v is not None]
    if not all_vals:
        return

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

    # Map x-axis by date proportion (not index) for consistent spacing
    date_ts = [_dt.strptime(p["date"], "%Y-%m-%d").timestamp() for p in data_points]
    first_ts, last_ts = date_ts[0], date_ts[-1]
    ts_range = last_ts - first_ts or 1.0

    def px(i):
        return chart_x + ((date_ts[i] - first_ts) / ts_range) * chart_w

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

    # Draw actual line (green/amber, thicker) — skip None values
    real_points = [p for p in data_points if p.get("on_track") is not None]
    is_on_track = real_points[-1].get("on_track", False) if real_points else False
    if is_on_track:
        pdf.set_draw_color(16, 185, 129)
    else:
        pdf.set_draw_color(245, 158, 11)
    pdf.set_line_width(0.5)
    actual_indices = [(i, v) for i, v in enumerate(actual) if v is not None]
    for j in range(len(actual_indices) - 1):
        i0, v0 = actual_indices[j]
        i1, v1 = actual_indices[j + 1]
        pdf.line(px(i0), py(v0), px(i1), py(v1))

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


def _render_pdf_minimap(pdf, full_data_points: list, horizon_date: str,
                        target_date: str, brand_rgb: tuple):
    """Render a compact minimap chart in the PDF with viewport indicator."""
    if len(full_data_points) < 2:
        return

    actual = [p["current_value"] for p in full_data_points]
    ideal = [p["ideal_value"] for p in full_data_points]
    all_vals = [v for v in actual + ideal if v is not None]
    if not all_vals:
        return

    min_val = min(all_vals)
    max_val = max(all_vals)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = max_val * 0.1 or 1.0
    min_val -= val_range * 0.05
    max_val += val_range * 0.05
    val_range = max_val - min_val

    chart_x = pdf.l_margin
    chart_y = pdf.get_y() + 1
    chart_w = pdf.w - pdf.l_margin - pdf.r_margin
    chart_h = 15
    n = len(full_data_points)

    if chart_y + chart_h + 6 > pdf.h - pdf.b_margin:
        pdf.add_page()
        chart_y = pdf.get_y() + 1

    date_ts = [_dt.strptime(p["date"], "%Y-%m-%d").timestamp() for p in full_data_points]
    first_ts, last_ts = date_ts[0], date_ts[-1]
    ts_range = last_ts - first_ts or 1.0

    def px(i):
        return chart_x + ((date_ts[i] - first_ts) / ts_range) * chart_w

    def py(v):
        return chart_y + (1 - (v - min_val) / val_range) * chart_h

    # Viewport rectangle
    horizon_ts = _dt.strptime(horizon_date, "%Y-%m-%d").timestamp()
    vp_w = ((horizon_ts - first_ts) / ts_range) * chart_w
    vp_w = min(vp_w, chart_w)
    with pdf.local_context(
        fill_color=(59, 130, 246), fill_opacity=0.08,
        draw_color=(59, 130, 246),
    ):
        pdf.rect(chart_x, chart_y, vp_w, chart_h, style="DF")
    pdf.set_line_width(0.15)

    # Chart border
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.15)
    pdf.rect(chart_x, chart_y, chart_w, chart_h)

    # Ideal line
    pdf.set_draw_color(*brand_rgb)
    pdf.set_line_width(0.2)
    for i in range(n - 1):
        pdf.line(px(i), py(ideal[i]), px(i + 1), py(ideal[i + 1]))

    # Actual line
    pdf.set_draw_color(16, 185, 129)
    pdf.set_line_width(0.3)
    actual_indices = [(i, v) for i, v in enumerate(actual) if v is not None]
    for j in range(len(actual_indices) - 1):
        i0, v0 = actual_indices[j]
        i1, v1 = actual_indices[j + 1]
        pdf.line(px(i0), py(v0), px(i1), py(v1))

    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_y(chart_y + chart_h + 2)


def _hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color string to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )
