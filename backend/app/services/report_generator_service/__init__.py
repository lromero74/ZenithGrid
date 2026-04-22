"""
Report Generator Service

Split into focused modules:
- html_builder: HTML report generation, AI summaries, metrics, goals
- html_charts: SVG trend chart + minimap rendering
- expense_schedule: Date math + lookahead helpers for expense goal cards
- expense_sections: HTML section builders (coverage, changes, savings)
- expense_card: Expense goal card header + tab assembly
- pdf_generator: PDF generation with fpdf2
"""

from app.services.report_generator_service.html_builder import build_report_html  # noqa: F401
from app.services.report_generator_service.html_builder import BuildReportHtmlParams  # noqa: F401
from app.services.report_generator_service.pdf_generator import generate_pdf  # noqa: F401

# Re-export internals used by tests.
# Tests import these from "app.services.report_generator_service",
# which now resolves to this package's __init__.py.
from app.services.report_generator_service.html_builder import (  # noqa: F401
    _build_standard_goal_card,
    _build_tabbed_ai_section,
    _build_transfers_section,
    _md_to_styled_html,
    _normalize_ai_summary,
    _transfer_label,
)
from app.services.report_generator_service.html_charts import (  # noqa: F401
    _build_minimap_svg,
    _build_trend_chart_svg,
    _format_chart_value,
)
from app.services.report_generator_service.chart_renderer import (  # noqa: F401
    _render_trend_chart_png,
)
from app.services.report_generator_service.expense_schedule import (  # noqa: F401
    LOOKAHEAD_DAYS,
    _fmt_coverage_pct,
    _format_due_label,
    _get_lookahead_items,
    _get_upcoming_items,
    _next_biweekly_date,
    _next_every_n_days_date,
    _ordinal_day,
)
from app.services.report_generator_service.expense_sections import (  # noqa: F401
    _build_expense_changes_html,
    _expense_name_html,
)
from app.services.report_generator_service.expense_card import (  # noqa: F401
    _build_expenses_goal_card,
)
from app.services.report_generator_service.pdf_generator import (  # noqa: F401
    _render_pdf_markdown,
    _sanitize_for_pdf,
)
