# PRP: Shared-account visibility for transfer history

**Date:** 2026-06-13
**Origin:** Deferred from the v2.168.8 bug sweep (#4). Read-only, low-risk, mechanical — deferred only to avoid ballooning the batch.

## TL;DR

`GET` transfers endpoints in `backend/app/routers/transfers_router.py` filter by `AccountTransfer.user_id == current_user.id` (4 sites). Shared-account **members** who can see positions, bots, and order history on a managed account cannot see its **transfer history** (deposits/withdrawals) — they get a silently-empty list. `AccountTransfer` has an `account_id` FK, so the fix is the same membership-union read pattern used elsewhere: `or_(AccountTransfer.user_id == current_user.id, AccountTransfer.account_id.in_(accessible_account_ids))`. No data leaves the account boundary; this only un-hides managed-account data from the members who already see everything else on that account.

## Context & Goal

### User Story
As a shared-account member, the deposit/withdrawal history of an account shared with me shows up in transfer views, consistent with the positions/bots/order-history I can already see for it.

### Problem
`transfers_router.py` — four filter sites use owner-only scoping:
- `:101` `list_transfers` → `filters = [AccountTransfer.user_id == current_user.id]`
- `:185` (account-filter branch within list)
- `:206` `get_transfer_summary` → same
- `:267` (account-filter branch within summary)

`AccountTransfer` (`app/models/reporting.py:388`) has `account_id = Column(Integer, ForeignKey("trading.accounts.id"))`, so transfers ARE per-account; scoping by `user_id` only excludes managed accounts.

### Goal
Reads (`list_transfers`, `get_transfer_summary`) return transfers for accounts the user owns **or** can access via shared-account membership.

### Non-Goals
- No write paths here (transfer ingest is server-side via the Coinbase sync; not user-triggered).
- No change to the optional `account_id` query-param filter behavior (it further-narrows; must still verify the requested `account_id` is within the accessible set to avoid IDOR).

## Constraints
- **Read-only, but no IDOR.** When the caller passes `?account_id=X`, X must be in the accessible set; otherwise return empty (don't expose another user's transfers by id).
- Reuse `accessible_account_ids` (view-level), not `manager_account_ids` — viewing is the right grant level for history.

## Existing Patterns (Reference)
- `app/services/account_access.py::accessible_account_ids(db, current_user_id) -> List[int]` — owned + any-role shared accounts (view level).
- The exact union already applied in this sweep: `app/routers/order_history.py` and `app/bot_routers/bot_ai_logs_router.py:92` —
  `.where(or_(Model.user_id == current_user.id, Model.account_id.in_(acc_ids)))`.

## Recommended Design
In each of the two endpoint functions, compute `acc_ids = await accessible_account_ids(db, current_user.id)` once, then replace the base filter:
```python
filters = [or_(AccountTransfer.user_id == current_user.id,
               AccountTransfer.account_id.in_(acc_ids))]
```
For the optional `account_id` query param, keep the existing `AccountTransfer.account_id == account_id` narrowing AND ensure it can only narrow *within* `acc_ids` (it already does, because the base filter is ANDed; an out-of-scope `account_id` yields empty). `transfers_router.py` imports `and_` already; add `or_` to that import.

## Implementation Tasks (in order)
1. **Test first:** extend `tests/routers/test_transfers_router.py` (create if absent): a manager/member sees a managed account's transfers; a non-member sees none; passing `?account_id` of an unrelated account returns empty (no IDOR).
2. Add `or_` to the `from sqlalchemy import ...` line; import `accessible_account_ids`.
3. In `list_transfers` and `get_transfer_summary`, fetch `acc_ids` and swap the base filter (covers all 4 sites — 101/185 in list, 206/267 in summary).
4. Validation gates; ship (backend restart, no migration).

## Validation Gates (executable)
```bash
cd backend
./venv/bin/python3 -m pytest tests/ -q -k "transfer or account_access"
./venv/bin/python3 -m flake8 --max-line-length=120 app/routers/transfers_router.py
# multiuser-security agent on app/routers/transfers_router.py
```

## Gotchas & Pitfalls
- Compute `acc_ids` once per request, not per filter site.
- The summary endpoint aggregates (sum of deposits/withdrawals) — make sure the union applies to the aggregate's WHERE, or the totals will under-report for members.
- Don't switch to `manager_account_ids` — view-only members should still SEE transfer history.

## Test Coverage Summary
member-sees / non-member-empty / IDOR-by-account_id-blocked — for both list and summary.

## Rollout
Backend code-only; `sudo systemctl restart zenithgrid`. No migration.
