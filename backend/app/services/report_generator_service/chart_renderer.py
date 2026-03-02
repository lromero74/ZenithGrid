"""
Chart Renderer — PNG trend chart rendering using Pillow.

Extracted from html_builder.py to keep file sizes manageable.
"""

import io
from datetime import datetime as _dt
from typing import Any, Dict

from PIL import Image, ImageDraw, ImageFont

from app.services.report_generator_service.html_builder import _format_chart_value


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

    # Extract values (target endpoint may have current_value=None)
    actual = [p["current_value"] for p in data_points]
    ideal = [p["ideal_value"] for p in data_points]
    all_vals = [v for v in actual + ideal if v is not None]
    if not all_vals:
        return b""

    min_val = min(all_vals)
    max_val = max(all_vals)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = max_val * 0.1 or 1.0
    min_val -= val_range * 0.05
    max_val += val_range * 0.05
    val_range = max_val - min_val

    # Map x-axis by date proportion (not index) for consistent spacing
    date_ts = [_dt.strptime(p["date"], "%Y-%m-%d").timestamp() for p in data_points]
    first_ts, last_ts = date_ts[0], date_ts[-1]
    ts_range = last_ts - first_ts or 1.0

    def sx(i):
        return ml + ((date_ts[i] - first_ts) / ts_range) * cw

    def sy(v):
        return mt + (1 - (v - min_val) / val_range) * ch

    # Use last real data point for on_track (skip projected endpoint)
    real_points = [p for p in data_points if p.get("on_track") is not None]
    is_on_track = real_points[-1].get("on_track", False) if real_points else False
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

    # Build coordinate lists (skip None actual values from target endpoint)
    actual_real = [(i, v) for i, v in enumerate(actual) if v is not None]
    actual_coords = [(int(sx(i)), int(sy(v))) for i, v in actual_real]
    ideal_coords = [(int(sx(i)), int(sy(v))) for i, v in enumerate(ideal)]

    # Area fill under actual line (semi-transparent)
    area_fill_color = actual_rgb + (20,)  # ~8% opacity
    if actual_coords:
        last_actual_i = actual_real[-1][0]
        first_actual_i = actual_real[0][0]
        area_polygon = actual_coords + [
            (int(sx(last_actual_i)), int(mt + ch)),
            (int(sx(first_actual_i)), int(mt + ch)),
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
