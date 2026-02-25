"""
Report Generator Service

Split into focused modules:
- html_builder: HTML report generation, charts, AI summaries
- expense_builder: Expense goal cards, schedule logic, upcoming/lookahead
- pdf_generator: PDF generation with fpdf2
"""

from app.services.report_generator_service.html_builder import build_report_html  # noqa: F401
from app.services.report_generator_service.pdf_generator import generate_pdf  # noqa: F401

# Re-export internals used by tests.
# Tests import these from "app.services.report_generator_service",
# which now resolves to this package's __init__.py.
from app.services.report_generator_service.html_builder import (  # noqa: F401
    _build_standard_goal_card,
    _build_tabbed_ai_section,
    _build_transfers_section,
    _build_trend_chart_svg,
    _format_chart_value,
    _md_to_styled_html,
    _normalize_ai_summary,
    _render_trend_chart_png,
    _transfer_label,
)
from app.services.report_generator_service.expense_builder import (  # noqa: F401
    LOOKAHEAD_DAYS,
    _build_expense_changes_html,
    _build_expenses_goal_card,
    _expense_name_html,
    _fmt_coverage_pct,
    _format_due_label,
    _get_lookahead_items,
    _get_upcoming_items,
    _next_biweekly_date,
    _next_every_n_days_date,
    _ordinal_day,
)
from app.services.report_generator_service.pdf_generator import (  # noqa: F401
    _render_pdf_markdown,
    _sanitize_for_pdf,
)
