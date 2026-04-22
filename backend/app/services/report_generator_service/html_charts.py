"""
HTML Charts — SVG chart rendering helpers (trend chart, minimap, value formatting).

Part of the report_generator_service package.
"""

from typing import Any, Dict


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

    # Extract values (target endpoint may have current_value=None)
    actual = [p["current_value"] for p in data_points]
    ideal = [p["ideal_value"] for p in data_points]
    all_vals = [v for v in actual + ideal if v is not None]
    if not all_vals:
        return ""

    min_val = min(all_vals)
    max_val = max(all_vals)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = max_val * 0.1 or 1.0
    # Add 5% padding
    min_val -= val_range * 0.05
    max_val += val_range * 0.05
    val_range = max_val - min_val

    # Map x-axis by date proportion (not index) for consistent spacing
    from datetime import datetime as _dt
    date_ts = [_dt.strptime(p["date"], "%Y-%m-%d").timestamp() for p in data_points]
    first_ts, last_ts = date_ts[0], date_ts[-1]
    ts_range = last_ts - first_ts or 1.0

    def sx(i):
        return ml + ((date_ts[i] - first_ts) / ts_range) * cw

    def sy(v):
        return mt + (1 - (v - min_val) / val_range) * ch

    # Build polyline points (skip None actual values from target endpoint)
    actual_real = [(i, v) for i, v in enumerate(actual) if v is not None]
    actual_pts = " ".join(
        f"{sx(i):.1f},{sy(v):.1f}" for i, v in actual_real
    )
    ideal_pts = " ".join(
        f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(ideal)
    )

    # Area fill under actual line
    if actual_real:
        last_i = actual_real[-1][0]
        first_i = actual_real[0][0]
        area_pts = (
            actual_pts
            + f" {sx(last_i):.1f},{mt + ch:.1f} {sx(first_i):.1f},{mt + ch:.1f}"
        )
    else:
        area_pts = ""

    # Use last real data point for on_track (skip projected endpoint)
    real_points = [p for p in data_points if p.get("on_track") is not None]
    is_on_track = real_points[-1].get("on_track", False) if real_points else False
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


def _build_minimap_svg(
    full_data_points: list,
    horizon_date: str,
    target_date: str,
    brand_color: str = "#3b82f6",
    currency: str = "USD",
) -> str:
    """Build a compact minimap SVG showing the full timeline with a viewport indicator.

    Returns HTML containing the SVG with class 'minimap', or empty string.
    """
    if len(full_data_points) < 2:
        return ""

    from datetime import datetime as _dt

    width, height = 660, 45
    ml, mr, mt, mb = 5, 5, 5, 18
    cw = width - ml - mr
    ch = height - mt - mb

    # Extract values
    actual = [p["current_value"] for p in full_data_points]
    ideal = [p["ideal_value"] for p in full_data_points]
    all_vals = [v for v in actual + ideal if v is not None]
    if not all_vals:
        return ""

    min_val = min(all_vals)
    max_val = max(all_vals)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = max_val * 0.1 or 1.0
    min_val -= val_range * 0.05
    max_val += val_range * 0.05
    val_range = max_val - min_val

    # Map x-axis by date proportion
    date_ts = [_dt.strptime(p["date"], "%Y-%m-%d").timestamp() for p in full_data_points]
    first_ts, last_ts = date_ts[0], date_ts[-1]
    ts_range = last_ts - first_ts or 1.0

    def sx(i):
        return ml + ((date_ts[i] - first_ts) / ts_range) * cw

    def sy(v):
        return mt + (1 - (v - min_val) / val_range) * ch

    # Ideal line (dashed)
    ideal_pts = " ".join(
        f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(ideal)
    )

    # Actual line (solid, only non-None)
    actual_real = [(i, v) for i, v in enumerate(actual) if v is not None]
    actual_pts = " ".join(
        f"{sx(i):.1f},{sy(v):.1f}" for i, v in actual_real
    )

    # Viewport rectangle: from first data to horizon_date
    horizon_ts = _dt.strptime(horizon_date, "%Y-%m-%d").timestamp()
    vp_x1 = ml
    vp_x2 = ml + ((horizon_ts - first_ts) / ts_range) * cw
    vp_x2 = min(vp_x2, ml + cw)  # clamp

    # Date labels
    first_date = full_data_points[0]["date"]
    last_date = full_data_points[-1]["date"]

    return f"""
            <div style="margin-top: 4px;" class="minimap">
                <svg xmlns="http://www.w3.org/2000/svg"
                     viewBox="0 0 {width} {height}"
                     style="width:100%;height:auto;display:block;">
                    <rect width="{width}" height="{height}"
                          rx="4" fill="#131c2a"/>
                    <rect x="{vp_x1:.1f}" y="{mt}" width="{vp_x2 - vp_x1:.1f}"
                          height="{ch}" rx="2" fill="#3b82f6" opacity="0.12"
                          stroke="#3b82f6" stroke-width="0.5" stroke-opacity="0.4"
                          class="viewport"/>
                    <polyline points="{ideal_pts}" fill="none"
                        stroke="{brand_color}" stroke-width="1"
                        stroke-dasharray="4,3" opacity="0.5"/>
                    <polyline points="{actual_pts}" fill="none"
                        stroke="#10b981" stroke-width="1.5" opacity="0.8"/>
                    <text x="{ml}" y="{height - 3}" fill="#475569"
                        font-size="8" font-family="sans-serif">{first_date}</text>
                    <text x="{width - mr}" y="{height - 3}"
                        text-anchor="end" fill="#475569"
                        font-size="8" font-family="sans-serif">{last_date}</text>
                </svg>
            </div>"""
