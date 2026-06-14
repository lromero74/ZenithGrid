# PRP: Shared-account scoping for `market_sell`

**Date:** 2026-06-13
**Origin:** Deferred from the v2.168.8 bug sweep (#4). The only deferred item with real-money implications, so it gets its own careful PRP + test instead of a batch edit.

## TL;DR

`POST /api/trading/market-sell` is scoped owner-only (`Account.user_id == current_user.id`), inconsistent with every other position/account action endpoint (which use `manager_account_ids`). A shared-account **manager** who can cancel, force-close, and add funds on a managed account **cannot** market-sell on it. Fix: allow managers when an `account_id` is explicitly supplied; keep the `is_default` fallback owner-only (a manager has no "default" among accounts they don't own). This sells **real holdings**, so the fix must (a) verify the order routes to the *account's owner's* broker, not the caller's, and (b) ship with tests proving manager-can / view-only-member-cannot / non-member-cannot.

## Context & Goal

### User Story
As a shared-account **manager**, I can trigger a market sell on an account that has been shared with me (manager role), the same way I can already cancel/force-close positions and add funds on it.

### Problem
`backend/app/routers/trading_router.py:~48-58` selects the target account with:
```python
query = select(Account).where(
    Account.user_id == current_user.id,
    Account.is_active.is_(True),
    Account.type == 'cex',
)
if request.account_id:
    query = query.where(Account.id == request.account_id)
else:
    query = query.where(Account.is_default.is_(True))
```
The `Account.user_id == current_user.id` clause means only the **owner** can market-sell. Other position-action endpoints (e.g. `position_manual_ops_router.py:38,126`) already use `manager_account_ids(db, current_user.id)`.

### Goal
- A manager can market-sell on a managed account **when they pass `request.account_id`** for an account they manage.
- The owner keeps the existing `is_default` (no-account_id) convenience path.
- The actual order executes against the **owning account's** broker/credentials (no cross-credential borrowing).

### Non-Goals
- No change to view-only ("shadow"/read) members — they must NOT be able to market-sell.
- No change to the `is_default` fallback semantics for owners.
- Not touching other trading_router endpoints in this PRP.

## Constraints
- **Real money.** A wrong scope here sells someone's holdings. The default must remain restrictive; only the explicit-account_id path widens to managers.
- **Credential isolation (CLAUDE.md rule 12).** The exchange client MUST be built from the *owning* account (pass `account_id=account.id`), never the caller's default broker. Mirror the v2.166.5 fix in `position_manual_ops_router` (manager `add_funds` formerly routed to the caller's broker — that exact bug).
- **No IDOR.** Passing an `account_id` you neither own nor manage must 404/403, not sell.

## Existing Patterns (Reference)
- `app/services/account_access.py::manager_account_ids(db, current_user_id) -> List[int]` — owned + manager-role accounts. This is the authoritative helper.
- `app/position_routers/position_manual_ops_router.py:38` — the canonical "action endpoint" scoping: `user_account_ids = await manager_account_ids(db, current_user.id)` then `Account.id.in_(user_account_ids)` / `Position.account_id.in_(...)`.
- v2.166.5 changelog entry: "manager `add_funds` formerly routed to the caller's default broker instead of the position's account broker — fixed." The broker for the sell must come from the resolved account.

## Recommended Design
1. Compute `manager_ids = await manager_account_ids(db, current_user.id)`.
2. Rewrite the account selection:
   ```python
   query = select(Account).where(
       Account.id.in_(manager_ids),
       Account.is_active.is_(True),
       Account.type == 'cex',
   )
   if request.account_id is not None:
       query = query.where(Account.id == request.account_id)
   else:
       # Convenience default only applies to the caller's OWN accounts; a manager
       # has no "default" among managed accounts and must name one explicitly.
       query = query.where(Account.user_id == current_user.id, Account.is_default.is_(True))
   ```
   This keeps the no-`account_id` path owner-only (via the `is_default` branch's `user_id` filter) while letting the explicit-`account_id` path resolve any managed account.
3. After resolving `account`, build the exchange client from **that account** (confirm the existing `get_coinbase_for_account`/equivalent is used with `account.id`), so the sell hits the owner's broker.
4. If no account resolves → 404 (don't fall through to selling the wrong account).

## Implementation Tasks (in order)
1. **Test first (TDD):** add `tests/routers/test_trading_router.py` (or extend existing) with three cases driving `market_sell`:
   - manager + explicit `account_id` of a managed account → sell proceeds, broker built from that account.
   - view-only member + explicit `account_id` → 403/404, no sell.
   - any user + `account_id` of an unrelated account → 404, no sell.
   - owner + no `account_id` → existing default path still works.
2. Import `manager_account_ids`; rewrite the account-selection query per the design.
3. Verify/keep the broker construction account-scoped.
4. Run validation gates; ship per `/shipit` (backend restart, no migration).

## Validation Gates (executable)
```bash
cd backend
./venv/bin/python3 -m pytest tests/ -q -k "trading_router or market_sell or account_access"
./venv/bin/python3 -m flake8 --max-line-length=120 app/routers/trading_router.py
# then run the multiuser-security agent on app/routers/trading_router.py
```

## Gotchas & Pitfalls
- The `is_default` fallback must stay **owner-only** — don't let a manager's no-account_id call silently sell the owner's default account.
- Don't reuse a caller-default `CoinbaseClient`; build it from the resolved account (re-introduces the v2.166.5 bug otherwise).
- `account_id is not None` (not truthy) — `account_id == 0` is not a valid id but `if request.account_id:` would skip a legit explicit selection only if ids can be 0 (they can't, but be explicit).

## Test Coverage Summary
manager-can / view-only-cannot / non-member-cannot / owner-default-still-works — 4 cases minimum.

## Rollout
Backend code-only; `./bot.sh restart --prod` equivalent (on Lightsail: `sudo systemctl restart zenithgrid`). No migration.
