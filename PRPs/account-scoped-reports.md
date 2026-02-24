# PRP: Account-Scoped Reports

**Feature**: Goals, schedules, and report history should be filtered by the active account (paper trading vs live trading), so switching accounts shows only that account's data
**Created**: 2026-02-24
**One-Pass Confidence Score**: 9/10

---

## Context & Goal

### Problem
When the user switches between accounts (e.g., live trading vs paper trading), the Reports page still shows **all** goals, schedules, and report history regardless of which account is selected. This means paper trading and live trading data are mixed together, which is confusing — users expect the same account isolation they see on Dashboard, Positions, and Portfolio pages.

### Solution
Add `account_id` filtering throughout the reports system:
1. **Goals** — add `account_id` column to `ReportGoal`, filter by selected account
2. **Schedules** — already have `account_id` column, just need to filter the list endpoint
3. **Report History** — add `account_id` column to `Report`, filter by selected account
4. **Frontend** — pass `selectedAccount.id` to all report API calls and query keys

### Who Benefits
All multi-account users. Currently the only multi-account scenario is paper trading vs live trading.

### Design Decisions

**Goals ARE account-scoped**: Even though goals are conceptual targets ("Reach 1 BTC"), they track balance/profit relative to a specific account's positions and balances. A paper trading goal of "Reach $10k" is completely different from a live trading goal of "Reach $10k". The user expects to see different goals per account.

**Backward compatibility**: Existing goals/reports with NULL `account_id` should be treated as belonging to the user's default (first) account. The migration should backfill NULL values to the default account ID where possible. The frontend will also handle this gracefully.

---

## Existing Code Patterns (Reference)

### Account-scoped query pattern (backend)
Every router that supports account filtering uses the same pattern — an optional `account_id` query parameter:

```python
# From order_history.py, transfers_router.py, account_value_router.py
account_id: Optional[int] = Query(None, description="Filter by account ID")

# Applied in the query:
if account_id:
    filters.append(Model.account_id == account_id)
```

### Account context pattern (frontend)
Every page that is account-aware follows this pattern:

```tsx
// From Dashboard.tsx, Positions.tsx, Portfolio.tsx
import { useAccount } from '../contexts/AccountContext'

const { selectedAccount } = useAccount()

// Query key includes account ID for cache isolation
queryKey: ['some-data', selectedAccount?.id],
queryFn: () => someApi.getData(selectedAccount?.id),
```

API functions pass `account_id` as a query parameter:
```typescript
// From api.ts — transfers, account value, etc.
getData: (accountId?: number) =>
  api.get('/some/endpoint', {
    params: accountId ? { account_id: accountId } : {}
  }).then(r => r.data),
```

### ReportSchedule already has account_id
`ReportSchedule` model (`models.py:1445`) already has:
```python
account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
```
And `setup.py` line 1558 already includes it. The schedule form type (`ScheduleForm.tsx:25`) already has `account_id?: number | null` but the form UI never populates it.

### Report generation already uses account_id
`report_scheduler.py:167` passes `schedule.account_id` to `gather_report_data()`, which correctly filters positions, transfers, and snapshots by account.

### Report model does NOT have account_id
`Report` model (`models.py:1497`) only has `user_id` and `schedule_id`. Reports inherit their account scope through the schedule relationship, but there's no direct `account_id` for efficient filtering.

---

## Implementation Tasks (in order)

### Task 1: Add `account_id` to ReportGoal model + migration

**File**: `backend/app/models.py` (~line 1331, after `user_id`)
```python
account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
```

**File**: `backend/migrations/add_account_id_to_goals_and_reports.py` (NEW)
```python
"""Add account_id to report_goals and reports tables for account-scoped filtering."""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Add account_id to report_goals
    try:
        cursor.execute("ALTER TABLE report_goals ADD COLUMN account_id INTEGER REFERENCES accounts(id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_report_goals_account_id ON report_goals(account_id)")
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise

    # Add account_id to reports
    try:
        cursor.execute("ALTER TABLE reports ADD COLUMN account_id INTEGER REFERENCES accounts(id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_reports_account_id ON reports(account_id)")
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise

    # Backfill: set account_id on existing goals to the user's default account
    try:
        cursor.execute("""
            UPDATE report_goals
            SET account_id = (
                SELECT a.id FROM accounts a
                WHERE a.user_id = report_goals.user_id
                  AND a.is_default = 1
                LIMIT 1
            )
            WHERE account_id IS NULL
        """)
    except Exception:
        pass  # Best-effort backfill

    # Backfill: set account_id on existing reports from their schedule's account_id,
    # falling back to the user's default account
    try:
        cursor.execute("""
            UPDATE reports
            SET account_id = COALESCE(
                (SELECT rs.account_id FROM report_schedules rs WHERE rs.id = reports.schedule_id),
                (SELECT a.id FROM accounts a WHERE a.user_id = reports.user_id AND a.is_default = 1 LIMIT 1)
            )
            WHERE account_id IS NULL
        """)
    except Exception:
        pass  # Best-effort backfill

    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
```

**File**: `setup.py` — Add `account_id INTEGER REFERENCES accounts(id)` to `report_goals` and `reports` CREATE TABLE statements.

### Task 2: Add `account_id` to Report model

**File**: `backend/app/models.py` (~line 1507, after `user_id`)
```python
account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
```

### Task 3: Update backend — Goals endpoints

**File**: `backend/app/routers/reports_router.py`

Add `account_id` parameter to goal endpoints:

- `list_goals` (line 374): Add `account_id: Optional[int] = Query(None)` parameter. If provided, filter `ReportGoal.account_id == account_id`.
- `create_goal` (line 390): Add `account_id` to `GoalCreate` schema. Store on the goal model.
- `update_goal`: No change needed (goal ID is unique).
- `delete_goal`: No change needed.
- `get_goal_trend`: No change needed (goal ID is unique).

Update `GoalCreate` Pydantic schema:
```python
account_id: Optional[int] = None
```

Update `_goal_to_dict`:
```python
"account_id": g.account_id,
```

### Task 4: Update backend — Schedules list endpoint

**File**: `backend/app/routers/reports_router.py`

- `list_schedules` (line 746): Add `account_id: Optional[int] = Query(None)` parameter. If provided, filter `ReportSchedule.account_id == account_id`.

### Task 5: Update backend — Report history endpoint

**File**: `backend/app/routers/reports_router.py`

- `list_reports` (line 986): Add `account_id: Optional[int] = Query(None)` parameter. If provided, filter `Report.account_id == account_id`.

Also: When generating a report (`generate_report`, `preview_report`), stamp `report.account_id = schedule.account_id`.

**File**: `backend/app/services/report_scheduler.py`

In `generate_report_for_schedule()`, when creating the Report object, set:
```python
account_id=schedule.account_id,
```

### Task 6: Update `_report_to_dict` and `_goal_to_dict`

Include `account_id` in the serialized output so the frontend can see it:

```python
# In _report_to_dict:
"account_id": report.account_id,

# In _goal_to_dict:
"account_id": g.account_id,
```

### Task 7: Update frontend API client

**File**: `frontend/src/services/api.ts`

Update `reportsApi` methods to accept optional `accountId`:

```typescript
getGoals: (accountId?: number) =>
  api.get<ReportGoal[]>('/reports/goals', {
    params: accountId ? { account_id: accountId } : {}
  }).then(r => r.data),

getSchedules: (accountId?: number) =>
  api.get<ReportSchedule[]>('/reports/schedules', {
    params: accountId ? { account_id: accountId } : {}
  }).then(r => r.data),

getHistory: (limit: number = 20, offset: number = 0, scheduleId?: number, accountId?: number) =>
  api.get<{ total: number; reports: ReportSummary[] }>('/reports/history', {
    params: {
      limit, offset,
      ...(scheduleId ? { schedule_id: scheduleId } : {}),
      ...(accountId ? { account_id: accountId } : {}),
    }
  }).then(r => r.data),
```

### Task 8: Update frontend Reports page

**File**: `frontend/src/pages/Reports.tsx`

1. Import `useAccount`:
```tsx
import { useAccount } from '../contexts/AccountContext'
```

2. Get `selectedAccount`:
```tsx
const { selectedAccount } = useAccount()
```

3. Update ALL query keys and queryFn calls to include `selectedAccount?.id`:
```tsx
// Goals
queryKey: ['report-goals', selectedAccount?.id],
queryFn: () => reportsApi.getGoals(selectedAccount?.id),

// Schedules
queryKey: ['report-schedules', selectedAccount?.id],
queryFn: () => reportsApi.getSchedules(selectedAccount?.id),

// History
queryKey: ['report-history', historyPage, selectedScheduleFilter, selectedAccount?.id],
queryFn: () => reportsApi.getHistory(20, (historyPage - 1) * 20, selectedScheduleFilter, selectedAccount?.id),
```

4. When creating a goal (in the goal creation handler), include `account_id: selectedAccount?.id`.

5. When creating a schedule (in ScheduleForm), auto-populate `account_id` from `selectedAccount?.id`.

### Task 9: Update ScheduleForm — auto-populate account_id

**File**: `frontend/src/components/reports/ScheduleForm.tsx`

The form already has `account_id` in its data type. Update the `handleSubmit` to include `account_id` from the currently selected account. Import and use `useAccount()`.

```tsx
import { useAccount } from '../../contexts/AccountContext'

// In the component:
const { selectedAccount } = useAccount()

// In handleSubmit, include:
account_id: selectedAccount?.id ?? null,
```

### Task 10: Update frontend types

**File**: `frontend/src/types/index.ts`

Add `account_id` to `ReportGoal` and `ReportSummary`:
```typescript
export interface ReportGoal {
  // ... existing fields
  account_id?: number | null
}

export interface ReportSummary {
  // ... existing fields
  account_id?: number | null
}
```

### Task 11: Write tests

**File**: `backend/tests/routers/test_reports_router.py` (append)

Tests:
- `test_list_goals_filters_by_account_id` — create goals on two accounts, filter returns only the matching account's goals
- `test_list_schedules_filters_by_account_id` — same pattern for schedules
- `test_list_reports_filters_by_account_id` — same pattern for report history
- `test_create_goal_stores_account_id` — verify account_id is persisted on creation
- `test_report_generation_stamps_account_id` — verify generated report gets account_id from schedule

---

## Files to Modify

| File | Changes |
|------|---------|
| `backend/app/models.py` | Add `account_id` to `ReportGoal` and `Report` |
| `backend/app/routers/reports_router.py` | Add `account_id` query param to list endpoints, `GoalCreate` schema, `_goal_to_dict`, `_report_to_dict` |
| `backend/app/services/report_scheduler.py` | Stamp `account_id` on Report during generation |
| `backend/migrations/add_account_id_to_goals_and_reports.py` | **NEW** — idempotent migration |
| `setup.py` | Add `account_id` to `report_goals` and `reports` CREATE TABLE |
| `frontend/src/services/api.ts` | Add `accountId` param to goals/schedules/history API functions |
| `frontend/src/pages/Reports.tsx` | Import `useAccount`, pass `selectedAccount?.id` to queries |
| `frontend/src/components/reports/ScheduleForm.tsx` | Auto-populate `account_id` from `useAccount()` |
| `frontend/src/types/index.ts` | Add `account_id` to `ReportGoal` and `ReportSummary` interfaces |
| `backend/tests/routers/test_reports_router.py` | Add account-scoping tests |

No new endpoints. No breaking changes (all account_id params are optional with null fallback).

---

## Validation Gates

```bash
# Backend lint
cd /home/ec2-user/ZenithGrid && backend/venv/bin/python3 -m flake8 --max-line-length=120 backend/app/routers/reports_router.py backend/app/models.py backend/app/services/report_scheduler.py

# Frontend TypeScript
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Run migration
cd /home/ec2-user/ZenithGrid/backend && ../backend/venv/bin/python3 -c "from migrations.add_account_id_to_goals_and_reports import migrate; migrate()"

# Unit tests
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/routers/test_reports_router.py -v

# Full test suite
./venv/bin/python3 -m pytest tests/ -v
```

---

## Edge Cases & Gotchas

1. **NULL account_id**: Existing data will have NULL before migration backfill runs. Backend queries use `if account_id: filters.append(...)` so passing no account_id returns everything (backward compatible).

2. **Backfill accuracy**: The migration backfills goals to the user's default account. If a user has goals that should span multiple accounts, they'll need to manually reassign via the UI. This is acceptable since multi-account is new.

3. **Schedule↔Goal cross-account**: A schedule has `account_id` and links to goals. We should NOT enforce that linked goals must have the same account_id — a schedule could reference global goals. The filtering is on the list endpoints, not on the relationships.

4. **GoalProgressSnapshot**: These are captured by the daily snapshot cycle. Currently they use `goal_id` + `user_id`. Since goals are now account-scoped, the snapshots implicitly inherit account scope through their goal. No column change needed on `goal_progress_snapshots`.

5. **ExpenseItem**: Expenses belong to a goal (via `goal_id`). Since goals are account-scoped, expenses inherit account scope. No column change needed on `expense_items`.

6. **Report PDF/email generation**: The `report_scheduler.py` already passes `schedule.account_id` to `gather_report_data()`. The only change is stamping `account_id` on the Report row for later filtering.

7. **Query cache invalidation**: When the user switches accounts, all report queries re-fetch because `selectedAccount?.id` is in the query keys. This is the standard pattern used by Dashboard, Positions, etc.
