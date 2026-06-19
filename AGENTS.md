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
  `git describe --tags` against the deployed tag on the Lightsail prod host
  (`ssh zenithgrid-ls "cd ~/ZenithGrid && git describe --tags"`) before reasoning
  about code paths — otherwise you may be reading code that no longer runs in prod.
  (`zenithgrid-ls` is the SSH alias defined in `~/.ssh/config`; use it rather than a
  raw `user@host`.)

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

## One source of truth for financial calculations (HARD RULE)

Budget, soft-ceiling, DCA-multiplier, per-position sizing, fee, and P&L formulas
must have ONE authoritative implementation. Don't inline a formula at a call site
when a shared helper exists; don't let two backend paths (batch vs single-pair vs
bidirectional) each re-derive the same split. When a calc must exist on both the
Python engine and the TypeScript UI, **the backend is authoritative** — the UI
prefers the backend's computed value (e.g. `Bot.soft_ceiling_effective_max`) and
uses its local copy only as a live-edit preview / loading fallback, with a test
asserting TS↔Py parity. Guard divide-by-zero / not-yet-loaded inputs by returning
"not computable" and falling back to the authoritative value — never let
`x/0 → Infinity` silently clamp to a default.

Why: in one June-2026 session, three separate bugs (the editor showing a `20`
ceiling and a `$1` base order while the engine used `1` and `$1.83`) all traced to
divergent copies of the same soft-ceiling / multiplier / sizing math.

## Consult the symbol registry before adding a function (HARD RULE)

Before writing a new function or method, check whether one already exists and
reuse/extend it instead of re-implementing — duplicated logic drifts and rots.

This repo ships a **live symbol registry** that scans `backend/app` with Python's
`ast` on every run, so it can never go stale:

```bash
python scripts/symbol_registry.py --check <name>   # where is <name> already defined?
python scripts/symbol_registry.py --duplicates     # module-level names defined in >1 file
python scripts/symbol_registry.py --write          # regenerate snapshot after add/rename/remove
python scripts/symbol_registry.py --verify         # exit non-zero if snapshot is stale
```

- Run `--check <name>` **before** adding a function. If a suitable one exists,
  reuse it. (Note many same-named functions are legitimate — e.g. a router
  endpoint delegating to a same-named service method — so `--duplicates` is
  advisory, not a hard gate.)
- The browsable snapshot is `docs/symbol_registry.json`;
  `backend/tests/test_symbol_registry.py` fails if it drifts from a live scan, so
  regenerate it (`--write`) whenever you intentionally add, rename, or remove a
  function.
- When duplication is genuinely unavoidable (e.g. a calc on both the Python and
  TypeScript sides), make one side authoritative and add a parity test.

## Environment note

- **Production is AWS Lightsail** (`zenithgrid`, us-east-1, static IP
  `52.87.130.244`), since 2026-06-13. ZenithGrid runs **natively** as the systemd
  *system* unit `zenithgrid.service` (uvicorn on `127.0.0.1:8100`, **no distrobox**);
  PostgreSQL 16 and Redis run on the same box. SSH via the alias `ssh zenithgrid-ls`
  (defined in `~/.ssh/config` → `origin.bigtruckincrypto.com`; use the alias, not a
  raw `user@host`). **Canonical deploy:** from a clean, tagged development checkout run
  `deployment/ship-lightsail.sh vX.Y.Z --backend` (or `--frontend-only`). This builds
  the frontend off-host, uploads an immutable artifact, and atomically switches
  `frontend/dist`; never run `npm run build` against the live production `dist`.
  Frontend rollback is `ssh zenithgrid-ls 'cd ~/ZenithGrid &&
  bash deployment/activate-frontend-release.sh --rollback'`.
- `fedora.local` is now a **stopped warm-standby / rollback target only** — do NOT
  start ZenithGrid there while Lightsail is live (double-trade risk). See the
  deploy/environment sections of `CLAUDE.md` for the authoritative details.
- Otherwise you are on a dev machine — push to git, deploy on the Lightsail prod host.
