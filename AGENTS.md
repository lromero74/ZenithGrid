# AGENTS.md — ZenithGrid

Guidance for AI coding agents (Codex, Claude, and any other automated contributor)
working in this repository. The authoritative development guide is **`CLAUDE.md`** —
read it fully. This file highlights the rules that matter most for agents that share
the repo with other agents and with the production host.

## Always sync before you edit

**Before reading or editing any code, bring your checkout up to date:**

```bash
git fetch origin
git pull --ff-only origin main      # or: git rebase origin/main on your branch
git describe --tags                  # confirm what version you're actually on
```

Why this is non-negotiable here:

- **Multiple agents push to this repo.** Claude, Codex, and the prod host all
  commit and tag. A checkout that looked current an hour ago can be several
  releases behind. (Real example: a local `main` sat at `v2.167.1` while
  `origin/main` and production were at `v2.167.8` — seven releases of
  soft-ceiling/rebalancer fixes missing.)
- **Editing a stale tree silently re-introduces already-fixed bugs** and produces
  diffs that conflict with work another agent already shipped.
- **When diagnosing production behavior, match versions first.** Compare your local
  `git describe --tags` against the deployed tag on `fedora.local`
  (`ssh fedora.local "cd ~/ZenithGrid && git describe --tags"`) before reasoning
  about code paths — otherwise you may be reading code that no longer runs in prod.

If `git pull --ff-only` is rejected (diverged history), **stop and reconcile**
before touching code. Do not force anything.

## Core rules (see CLAUDE.md for the full set)

- **New work in dev branches** — never commit directly to `main`. Merge only after
  the user confirms.
- **Test first (TDD).** Write the failing test before the implementation.
- **Lint everything.** Python: `flake8 --max-line-length=120`. TypeScript:
  `npx tsc --noEmit`. Tests must pass with **zero failures and zero warnings**.
- **Never silently drop code.** `git diff` before staging; confirm any deleted
  logic was intentional.
- **Always update `CHANGELOG.md`** (Keep a Changelog format, user-facing language)
  as part of every tagged commit.
- **Back up the DB and stop services before migrations.**
- **Bots created during development must NOT be started** — create them stopped.

## Always be wary of cross-account contamination (HARD RULE)

Every balance, position, budget, soft-ceiling, P&L, cache, or aggregate
calculation **must be scoped to a single `account_id`** — never just `user_id`,
and never unscoped.

A single user owns **multiple accounts** (several exchanges + paper accounts).
"Scoped to the user" is therefore NOT enough: a real Coinbase account's budget
must never include a paper account's positions, and vice-versa. This was a real
bug — a USD bot on a ~$50 account showed a ~$17,685 budget base because the
market-budget calc summed every USD-quoted position across all accounts and
users (root cause: an exchange client built without `account_id`).

Concretely:
1. Any DB query touching `positions`, `bots`, `trades`, `orders`, or balances
   must filter by `account_id` (join `bots.account_id` when starting from
   positions).
2. Any cache key for per-account data must include `account_id` in the key — a
   `None`/`"none"` suffix leaks across **all accounts and all users**.
3. Any exchange client built from an `Account` must pass `account_id=account.id`
   into `CoinbaseCredentials` / the client config so downstream calls inherit
   the scope.

When you add or modify any of these paths, write a test proving a second account
(same user, *and* a different user) does not bleed in, and run the
`multiuser-security` agent. Reference regression:
`backend/tests/services/test_portfolio_service.py::TestGetCoinbaseFromDbAccountScoping`.

## Environment note

- `fedora.local` is **production**. ZenithGrid runs as `zenithgrid.service` in the
  `zenith-box` distrobox on `127.0.0.1:8100`; PostgreSQL is in `postgres-box`.
  See the deploy/environment sections of `CLAUDE.md`.
- Otherwise you are on a dev machine — push to git, deploy on the prod host.
