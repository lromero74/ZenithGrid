# PRP: Move Chart Horizon Control to Schedule Level

## Current State (v2.62.0)

We shipped configurable chart horizon and minimap in v2.62.0 with settings on the **goal** level:
- `ReportGoal.chart_horizon` — "auto", "full", or integer days
- `ReportGoal.show_minimap` — boolean
- `ReportGoal.minimap_threshold_days` — integer

**Bug found**: PDF generation crashed because `_render_pdf_minimap()` in `pdf_generator.py:1232` used `pdf.set_alpha(0.08)` which doesn't exist in fpdf2 v2.8.6. **Fix already written** on branch `fix/chart-horizon-pdf-and-default`: replaced with `pdf.local_context(fill_opacity=0.08)`.

**Design change requested**: Move chart horizon to the **schedule** level so different schedules can have different look-aheads for the same goal. The auto look-ahead should be a **multiplier × schedule period days** (e.g., quarterly schedule with multiplier 0.33 → ~1 month look-ahead).

## Target Design

### Schedule-level fields (NEW)
Add to `ReportSchedule` model:
- `chart_lookahead_multiplier` — Float, default 1.0 (auto = multiplier × period_days)
- `chart_horizon` — String, default "auto" ("auto", "full", or integer days string)

### Goal-level fields (KEEP)
- `show_minimap` — Boolean, stays on goal (goal-inherent, not schedule-dependent)
- `minimap_threshold_days` — Integer, stays on goal
- `chart_horizon` — KEEP on goal as **fallback for the interactive frontend chart** (which has no schedule context). Don't show in GoalForm UI anymore.

## Implementation Steps

### 1. Fix the PDF crash (already done on current branch)
- File: `backend/app/services/report_generator_service/pdf_generator.py`
- Change: `pdf.set_alpha(0.08)` → `pdf.local_context(fill_opacity=0.08, fill_color=..., draw_color=...)`
- This is already done on the `fix/chart-horizon-pdf-and-default` branch.

### 2. Backend Model — Add to ReportSchedule
- File: `backend/app/models.py` (~line 1478, before relationships)
- Add:
  ```python
  chart_horizon = Column(String, default="auto")  # "auto", "full", or integer days
  chart_lookahead_multiplier = Column(Float, default=1.0)  # For auto: multiplier × period_days
  ```

### 3. Migration — add_schedule_chart_settings.py
- File: `backend/migrations/add_schedule_chart_settings.py` (NEW)
- Idempotent ALTER TABLE adding 2 columns to `report_schedules`
  ```sql
  ALTER TABLE report_schedules ADD COLUMN chart_horizon TEXT DEFAULT 'auto';
  ALTER TABLE report_schedules ADD COLUMN chart_lookahead_multiplier REAL DEFAULT 1.0;
  ```

### 4. setup.py — Fresh install schema
- File: `setup.py` (~line 1600, inside CREATE TABLE report_schedules)
- Add both columns to the raw SQL

### 5. API Schemas — ScheduleCreate/Update
- File: `backend/app/routers/reports_router.py`
- `ScheduleCreate` (~line 131): Add:
  ```python
  chart_horizon: Optional[str] = Field("auto", pattern=r"^(auto|full|[0-9]+)$")
  chart_lookahead_multiplier: Optional[float] = Field(1.0, ge=0.1, le=10.0)
  ```
- `ScheduleUpdate` (~line 174): Add same fields with `None` defaults
- `_schedule_to_dict()` (~line 314): Add both fields to output dict

### 6. Schedule Service — Pass through to constructor
- File: `backend/app/services/report_schedule_service.py` (~line 100)
- Add both fields to the `ReportSchedule(...)` constructor call
- The update_schedule_record uses setattr loop on model_dump(exclude_unset=True), so new fields auto-handled

### 7. compute_horizon_date — Accept schedule_period_days
- File: `backend/app/services/goal_snapshot_service.py` (~line 660)
- Change signature:
  ```python
  def compute_horizon_date(
      data_points: list,
      target_date_str: str,
      chart_horizon: str = "auto",
      schedule_period_days: int = 30,
      lookahead_multiplier: float = 1.0,
  ) -> str:
  ```
- Auto mode logic:
  ```python
  # Auto: multiplier × schedule period
  look_ahead_days = max(int(schedule_period_days * lookahead_multiplier), 1)
  horizon = last_data_date + timedelta(days=look_ahead_days)
  return min(horizon, target_date).strftime("%Y-%m-%d")
  ```

### 8. report_scheduler.py — Wire schedule settings
- File: `backend/app/services/report_scheduler.py` (~line 210)
- The `schedule` ORM object is in scope. `period_days` is already computed at line 170.
- Change compute_horizon_date call:
  ```python
  chart_horizon = getattr(schedule, "chart_horizon", "auto") or "auto"
  lookahead_mult = getattr(schedule, "chart_lookahead_multiplier", 1.0) or 1.0

  horizon_date = compute_horizon_date(
      trend["data_points"], target_date_str, chart_horizon,
      schedule_period_days=period_days,
      lookahead_multiplier=lookahead_mult,
  )
  ```
- ALSO: Remove the `chart_horizon` read from `goal_orm` (it was reading from goal before)

### 9. Frontend Types — Add to ReportSchedule interface
- File: `frontend/src/types/index.ts` (~line 537, in ReportSchedule interface)
- Add:
  ```tsx
  chart_horizon?: string
  chart_lookahead_multiplier?: number
  ```

### 10. Frontend ScheduleForm — Add chart settings UI
- File: `frontend/src/components/reports/ScheduleForm.tsx`
- Add `ScheduleFormData` fields:
  ```tsx
  chart_horizon?: string
  chart_lookahead_multiplier?: number
  ```
- Add state variables:
  ```tsx
  const [chartHorizon, setChartHorizon] = useState<string>('auto')
  const [customHorizonDays, setCustomHorizonDays] = useState('90')
  const [lookaheadMultiplier, setLookaheadMultiplier] = useState('1')
  ```
- Initialize from `initialData` in useEffect
- Add to handleSubmit data
- UI: Add collapsible "Chart Display" section before submit button (same pattern as existing sections):
  - **Chart Horizon** select: "Auto (Period × Multiplier)" / "Full Timeline" / "Custom Days"
  - **Look-Ahead Multiplier** (shown when Auto selected): number input
    - Helper text showing computed look-ahead: "e.g., quarterly × 1.0 = ~3 months ahead"
  - If "Custom Days": number input for days

### 11. Frontend GoalForm — Remove chart horizon control, keep minimap
- File: `frontend/src/components/reports/GoalForm.tsx`
- Remove the "Chart Horizon" select and "Custom Days" input from the Chart Display section
- Keep only the minimap toggle and threshold in the "Chart Display" section
- Remove `chartHorizon`, `customHorizonDays` state variables
- Remove `chart_horizon` from GoalFormData and handleSubmit
- Keep `show_minimap` and `minimap_threshold_days`

### 12. Frontend GoalTrendChart — Fallback for interactive chart
- File: `frontend/src/components/reports/GoalTrendChart.tsx`
- The interactive chart has no schedule context. Use the goal's `chart_horizon` from chart_settings (which defaults to "auto")
- For auto mode with no schedule: use 30-day fallback
- The backend trend endpoint already returns chart_settings; update it to also return `chart_lookahead_multiplier: null` so frontend knows to use fallback

### 13. Update Tests
- File: `backend/tests/services/test_chart_horizon.py`
- Update tests for `compute_horizon_date` to test new signature:
  - `test_auto_with_monthly_schedule` — period=30, mult=1.0 → 30 days ahead
  - `test_auto_with_quarterly_schedule_third` — period=90, mult=0.33 → ~30 days
  - `test_auto_with_weekly_schedule` — period=7, mult=1.0 → 7 days
  - `test_auto_with_large_multiplier` — period=30, mult=3.0 → 90 days
  - Keep existing "full" and "custom days" tests (unchanged)

### 14. Lint + TypeScript Check
- `flake8 --max-line-length=120` on all changed Python files
- `npx tsc --noEmit` for frontend

## Files Summary

| File | Change |
|------|--------|
| `backend/app/services/report_generator_service/pdf_generator.py` | Fix `set_alpha` → `local_context(fill_opacity=...)` |
| `backend/app/models.py` | Add 2 columns to ReportSchedule |
| `backend/migrations/add_schedule_chart_settings.py` | NEW — idempotent migration |
| `setup.py` | 2 new columns in CREATE TABLE report_schedules |
| `backend/app/routers/reports_router.py` | ScheduleCreate/Update schemas, _schedule_to_dict |
| `backend/app/services/report_schedule_service.py` | Pass new fields to constructor |
| `backend/app/services/goal_snapshot_service.py` | Update compute_horizon_date signature + auto logic |
| `backend/app/services/report_scheduler.py` | Wire schedule settings into horizon computation |
| `backend/tests/services/test_chart_horizon.py` | Update tests for new signature |
| `frontend/src/types/index.ts` | Add to ReportSchedule interface |
| `frontend/src/components/reports/ScheduleForm.tsx` | Add chart horizon + multiplier UI |
| `frontend/src/components/reports/GoalForm.tsx` | Remove chart horizon UI (keep minimap) |
| `frontend/src/components/reports/GoalTrendChart.tsx` | Update auto fallback |

## Schedule Period Days Reference

| schedule_type | Approximate period_days |
|---------------|------------------------|
| daily | 1 |
| weekly | 7 |
| monthly | 30 |
| quarterly | 90 |
| yearly | 365 |

## Examples

| Schedule | Multiplier | Auto Look-Ahead |
|----------|-----------|-----------------|
| Weekly, 1.0 | 7 days |
| Monthly, 1.0 | 30 days |
| Monthly, 0.5 | 15 days |
| Quarterly, 0.33 | ~30 days (1 month) |
| Quarterly, 1.0 | 90 days (3 months) |
| Quarterly, 3.0 | 270 days (9 months) |
| Yearly, 0.25 | ~91 days (1 quarter) |
