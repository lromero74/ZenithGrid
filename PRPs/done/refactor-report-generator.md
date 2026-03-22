# PRP: Refactor report_generator_service.py

**Feature**: Split the 2900+ line report generator service into focused modules under the 1200 line limit
**Created**: 2026-02-25
**One-Pass Confidence Score**: 9/10

---

## Context & Goal

### Problem
`backend/app/services/report_generator_service.py` has grown to ~2900 lines — well over the 1200-line CLAUDE.md limit. The file contains three distinct responsibilities: HTML report building, expense goal rendering with schedule logic, and PDF generation. This makes navigation, testing, and maintenance harder than it needs to be.

### Solution
Split into 3 focused modules under a new `backend/app/services/report_generator/` package. Each module stays under ~1000 lines. Public API (`build_report_html`, `generate_pdf`) remains importable from the package `__init__.py`. All existing tests and consumers continue working with updated imports.

### Who Benefits
Developer productivity — smaller files are easier to navigate, modify, and test in isolation.

### Scope
- **In**: Splitting functions into 3 modules, updating all imports (services + tests), re-exporting public API from `__init__.py`
- **Out**: No functional changes, no new features, no test behavior changes

---

## Existing Code Patterns (Reference)

### Current File Structure (~2900 lines)

The file has 2 public functions and ~38 private functions that fall into 3 natural clusters:

**Cluster 1: HTML Report Builder** (~650 lines)
- `build_report_html()` — main HTML orchestrator
- `_report_header()`, `_report_footer()`
- `_build_metrics_section()`
- `_build_transfers_section()`, `_transfer_label()`
- `_build_goals_section()`, `_build_standard_goal_card()`, `_build_income_goal_card()`
- `_build_comparison_section()`
- AI summary handling: `_normalize_ai_summary()`, `_migrate_legacy_tiers()`, `_build_tabbed_ai_section()`, `_build_email_ai_section()`, `_render_single_ai_section()`
- Markdown: `_md_to_styled_html()`
- Charts: `_format_chart_value()`, `_build_trend_chart_svg()`, `_load_chart_font()`, `_render_trend_chart_png()`

**Cluster 2: Expense Goal Rendering** (~650 lines)
- `_build_expenses_goal_card()` — the massive expense card builder
- Schedule helpers: `_ordinal_day()`, `_next_biweekly_date()`, `_next_every_n_days_date()`, `_get_upcoming_items()`, `_get_lookahead_items()`, `_format_due_label()`
- UI helpers: `_build_expense_status_badge()`, `_expense_name_html()`

**Cluster 3: PDF Generation** (~750 lines)
- `generate_pdf()` — main PDF orchestrator (700+ lines itself)
- `_sanitize_for_pdf()`, `_truncate_to_width()`
- `_render_pdf_markdown()`, `_render_pdf_tiers()`
- `_render_pdf_trend_chart()`
- `_hex_to_rgb()`

### Shared Utilities (used across clusters)
- `_fmt_coverage_pct()` — used by expense HTML + PDF
- `_transfer_label()` — used by HTML + PDF
- `_format_due_label()` — used by expense HTML + PDF
- `_get_upcoming_items()`, `_get_lookahead_items()` — used by expense HTML + PDF
- `_build_expense_status_badge()`, `_expense_name_html()` — used by expense HTML + PDF
- `_normalize_ai_summary()`, `_migrate_legacy_tiers()` — used by HTML + PDF
- `_format_chart_value()`, `_render_trend_chart_png()`, `_load_chart_font()` — used by HTML + PDF
- `LOOKAHEAD_DAYS` — constant used by expense helpers + tests

### Current Consumers

| File | Imports |
|------|---------|
| `report_scheduler.py` | `build_report_html`, `generate_pdf` (local imports in 2 functions) |
| `test_report_generator_service.py` | 14 functions + 2 public |
| `test_report_generator_charts.py` | 4 chart functions |
| `test_report_generator_expense.py` | 4 expense/schedule functions |
| `test_expense_lookahead.py` | 3 functions + `LOOKAHEAD_DAYS` |

---

## Implementation Blueprint

### Target Structure

```
backend/app/services/report_generator/
├── __init__.py              # Re-exports public API + all private functions for test compat
├── html_builder.py          # HTML report, metrics, goals, transfers, charts, AI sections
├── expense_builder.py       # Expense goal cards, schedule helpers, upcoming/lookahead
└── pdf_generator.py         # PDF generation, PDF-specific helpers
```

### Step 1: Create the package directory

```bash
mkdir -p backend/app/services/report_generator
```

### Step 2: Create `expense_builder.py` (~650 lines)

Move these functions from the monolith:
- Constants: `LOOKAHEAD_DAYS`, `_DOW_NAMES`, `_MONTH_ABBREVS`
- Schedule helpers: `_ordinal_day()`, `_next_biweekly_date()`, `_next_every_n_days_date()`, `_get_upcoming_items()`, `_get_lookahead_items()`, `_format_due_label()`
- Expense rendering: `_build_expense_status_badge()`, `_expense_name_html()`, `_build_expenses_goal_card()`
- Shared utility: `_fmt_coverage_pct()`

**Imports needed**:
```python
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
```

**Internal cross-dependencies**: `_build_expenses_goal_card()` calls `_get_upcoming_items()`, `_get_lookahead_items()`, `_format_due_label()`, `_build_expense_status_badge()`, `_expense_name_html()`, `_fmt_coverage_pct()` — all within this module.

### Step 3: Create `pdf_generator.py` (~950 lines)

Move these functions:
- Constants: `_EMOJI_RE`
- PDF main: `generate_pdf()`
- PDF helpers: `_sanitize_for_pdf()`, `_truncate_to_width()`, `_render_pdf_markdown()`, `_render_pdf_tiers()`, `_render_pdf_trend_chart()`, `_hex_to_rgb()`

**Imports from siblings**:
```python
from app.services.report_generator.expense_builder import (
    LOOKAHEAD_DAYS,
    _fmt_coverage_pct,
    _get_upcoming_items,
    _get_lookahead_items,
    _format_due_label,
    _build_expense_status_badge,
    _expense_name_html,
    _DOW_NAMES,
    _MONTH_ABBREVS,
    _ordinal_day,
)
from app.services.report_generator.html_builder import (
    _normalize_ai_summary,
    _transfer_label,
    _format_chart_value,
    _render_trend_chart_png,
    _load_chart_font,
)
```

### Step 4: Create `html_builder.py` (~800 lines)

Move remaining functions:
- Constants: `_TIER_LABELS`, `_TRANSFER_LABELS`
- Main: `build_report_html()`
- AI: `_normalize_ai_summary()`, `_migrate_legacy_tiers()`, `_build_tabbed_ai_section()`, `_build_email_ai_section()`, `_render_single_ai_section()`
- Markdown: `_md_to_styled_html()`
- Header/footer: `_report_header()`, `_report_footer()`
- Sections: `_build_metrics_section()`, `_build_transfers_section()`, `_transfer_label()`
- Goals: `_build_goals_section()`, `_build_standard_goal_card()`, `_build_income_goal_card()`
- Charts: `_format_chart_value()`, `_build_trend_chart_svg()`, `_load_chart_font()`, `_render_trend_chart_png()`
- Comparison: `_build_comparison_section()`

**Imports from siblings**:
```python
from app.services.report_generator.expense_builder import (
    _build_expenses_goal_card,
    _fmt_coverage_pct,
)
```

### Step 5: Create `__init__.py` — Public API + test compatibility re-exports

```python
"""
Report Generator Service

Split into focused modules:
- html_builder: HTML report generation, charts, AI summaries
- expense_builder: Expense goal cards, schedule logic, upcoming/lookahead
- pdf_generator: PDF generation with fpdf2
"""

from app.services.report_generator.html_builder import build_report_html  # noqa: F401
from app.services.report_generator.pdf_generator import generate_pdf  # noqa: F401

# Re-export internals used by tests.
# Tests import these from "app.services.report_generator_service",
# which now resolves to this package's __init__.py.
from app.services.report_generator.html_builder import (  # noqa: F401
    _build_standard_goal_card,
    _build_tabbed_ai_section,
    _build_trend_chart_svg,
    _format_chart_value,
    _md_to_styled_html,
    _normalize_ai_summary,
    _render_trend_chart_png,
    _transfer_label,
    _build_transfers_section,
)
from app.services.report_generator.expense_builder import (  # noqa: F401
    LOOKAHEAD_DAYS,
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
from app.services.report_generator.pdf_generator import (  # noqa: F401
    _render_pdf_markdown,
    _sanitize_for_pdf,
)
```

### Step 6: Delete the old monolith file

```bash
rm backend/app/services/report_generator_service.py
```

The old `from app.services.report_generator_service import X` imports in tests and services resolve to the package `__init__.py` since `report_generator_service/` directory replaces the `report_generator_service.py` file. Python treats `app.services.report_generator_service` as the package.

**CRITICAL**: The package directory MUST be named `report_generator_service` (not `report_generator`) so existing import paths continue to work. This avoids touching any test or service import statements.

### Step 7: Update `report_scheduler.py` local imports

The local imports in `report_scheduler.py` use:
```python
from app.services.report_generator_service import build_report_html, generate_pdf
```

These will resolve to the `__init__.py` re-exports — **no changes needed** in `report_scheduler.py`.

### Step 8: Update test imports

Similarly, all test files import from `app.services.report_generator_service` which resolves to the package. The `__init__.py` re-exports everything tests need — **no changes needed** in test files.

### Step 9: Verify and lint

```bash
cd /home/ec2-user/ZenithGrid/backend

# Verify imports resolve
./venv/bin/python3 -c "from app.services.report_generator_service import build_report_html, generate_pdf; print('OK')"

# Lint all new files
./venv/bin/python3 -m flake8 --max-line-length=120 \
  app/services/report_generator_service/__init__.py \
  app/services/report_generator_service/html_builder.py \
  app/services/report_generator_service/expense_builder.py \
  app/services/report_generator_service/pdf_generator.py

# Line count check (all under 1200)
wc -l app/services/report_generator_service/*.py

# Full test suite
./venv/bin/python3 -m pytest tests/ -v
```

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/services/report_generator_service.py` | **DELETE** — replaced by package |
| `backend/app/services/report_generator_service/__init__.py` | **NEW** — public API + test re-exports |
| `backend/app/services/report_generator_service/html_builder.py` | **NEW** — HTML, charts, AI, metrics, goals |
| `backend/app/services/report_generator_service/expense_builder.py` | **NEW** — expense cards, schedule logic |
| `backend/app/services/report_generator_service/pdf_generator.py` | **NEW** — PDF generation |
| `docs/architecture.json` | Update service entry for the split |
| `CHANGELOG.md` | v2.56.0 entry |

**No changes needed**: `report_scheduler.py`, all test files (imports resolve via package `__init__.py`)

---

## Validation Gates

```bash
cd /home/ec2-user/ZenithGrid/backend

# 1. Lint all new modules
./venv/bin/python3 -m flake8 --max-line-length=120 \
  app/services/report_generator_service/__init__.py \
  app/services/report_generator_service/html_builder.py \
  app/services/report_generator_service/expense_builder.py \
  app/services/report_generator_service/pdf_generator.py

# 2. Line count verification (all under 1200)
wc -l app/services/report_generator_service/*.py

# 3. Import verification
./venv/bin/python3 -c "
from app.services.report_generator_service import build_report_html, generate_pdf
from app.services.report_generator_service import LOOKAHEAD_DAYS
from app.services.report_generator_service import _build_expenses_goal_card
from app.services.report_generator_service import _sanitize_for_pdf
print('All imports OK')
"

# 4. Full test suite (all 2982+ tests must pass)
./venv/bin/python3 -m pytest tests/ -v

# 5. TypeScript check (no frontend changes expected)
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit
```

---

## Edge Cases & Gotchas

1. **Package vs module naming**: The package directory MUST be named `report_generator_service/` (matching the old file name minus `.py`) so all existing `from app.services.report_generator_service import X` statements continue working. Do NOT name it `report_generator/` — that would break every import.

2. **Circular imports**: The dependency direction is `html_builder` → `expense_builder` (for `_build_expenses_goal_card`) and `pdf_generator` → both. The `__init__.py` imports from all three. No circular dependencies exist in this layout.

3. **`generate_pdf()` is 700+ lines**: This single function can't be split further without major structural changes. It's imperative PDF drawing code. The module will be ~950 lines total, which is under the 1200 limit.

4. **Shared utilities placement**: `_fmt_coverage_pct()` is used by both expense HTML and PDF. Place it in `expense_builder.py` (where the expense logic lives) and import it in `pdf_generator.py`.

5. **`_TRANSFER_LABELS` and `_transfer_label()`**: Used by HTML builder AND PDF generator. Place in `html_builder.py` (where most HTML code lives) and import in `pdf_generator.py`.

6. **Test re-exports in `__init__.py`**: Tests import private functions (with `_` prefix) from the package. The `__init__.py` must re-export ALL of these. Use `# noqa: F401` to suppress unused-import lint warnings.

7. **`fpdf` lazy import**: `generate_pdf()` currently does `from fpdf import FPDF` as a local import inside the function. Keep this pattern — fpdf2 is only needed for PDF generation.

8. **Brand service import**: `from app.services.brand_service import get_brand` is used by `build_report_html()` only. Keep it in `html_builder.py`.

9. **PIL imports**: Used by chart rendering (`_render_trend_chart_png`, `_load_chart_font`). These functions live in `html_builder.py`, so the PIL import stays there.

---

## Implementation Order

1. Create package directory
2. Write `expense_builder.py` (no external deps within package)
3. Write `html_builder.py` (imports from expense_builder)
4. Write `pdf_generator.py` (imports from both)
5. Write `__init__.py` (re-exports from all three)
6. Delete old monolith `report_generator_service.py`
7. Lint + test
8. Update docs/architecture.json
9. Ship

---

## Confidence Assessment

**Score: 9/10**

**Why high**: This is a pure mechanical refactor — no logic changes, no API changes, no new features. The function clusters are cleanly separated with minimal cross-dependencies. The package naming trick (`report_generator_service/` replacing `report_generator_service.py`) means zero changes to consumers.

**Risk**: The main risk is missing a re-export in `__init__.py`, which would show up immediately as an ImportError in tests. The full test suite catches this.
