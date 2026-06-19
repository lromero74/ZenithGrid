# CLAUDE.md — ZenithGrid Development Guide

This file is the authoritative source of truth for how to work on ZenithGrid. Read it fully before making any changes.

## Development Philosophy

- **KISS**: Choose the straightforward solution. Simple code is easier to debug, review, and extend.
- **YAGNI**: Build what's needed now, not what might be needed later. No speculative features.
- **Single Responsibility**: Each function, class, module, and file has one clear purpose.
- **Fail Fast**: Validate inputs early, raise exceptions immediately, don't silently swallow errors.
- **Do the Right Thing**: No re-export shims, backwards-compat wrappers, or proxy modules. When moving code, actually move it — update all consumers and delete the old location. Fix bugs and lint errors you encounter, even if you didn't create them. You are the only coder on this project.

## Critical Rules

1. **Never silently drop code.** Always `git diff` before staging. If a diff shows deleted logic, confirm it was intentional.
2. **No spaghetti.** Layered architecture: utilities → services → routers (never upward). No circular imports, no cross-layer reaches, no god files.
3. **Always update CHANGELOG.md** as part of every tagged commit. Use Keep a Changelog format (Added/Changed/Fixed/Removed/Security). Entries are user-facing — plain language, no branch names or merge notes.
4. **New work in dev branches.** Never commit directly to main. Merge only after user confirms.
5. **Lint everything.** Python: `flake8 --max-line-length=120`. TypeScript: `npx tsc --noEmit`. All code must pass before committing.
6. **Back up the database** before any migration or schema change: `cp backend/trading.db backend/trading.db.bak.$(date +%s)`
7. **Stop services before migrations.** `./bot.sh stop`, then migrate, then restart.
8. **Bots created during development must NOT be started.** Create them in a stopped state.
9. **Think "How do leading platforms do it?"** when building features — match best-in-class UX patterns.
10. **Test first.** Write failing tests before writing implementation code. No feature ships without tests. See the TDD section below.
11. **Always sync before you edit.** Run `git fetch origin && git pull --ff-only origin main` (or rebase your branch onto the latest `main`) at the start of every working session, before reading or editing code. Multiple agents (Claude, Codex) and the prod host all push to this repo, so a local checkout goes stale fast — editing against an out-of-date tree silently re-introduces fixed bugs and produces conflicting diffs. If a `--ff-only` pull is rejected, stop and reconcile before touching code. When diagnosing prod behavior, confirm the version your local matches the deployed tag (`git describe --tags` locally vs. on the Lightsail prod box `ubuntu@origin.bigtruckincrypto.com`) before reasoning about the code.
12. **Always be wary of cross-account contamination.** Every balance, position, budget, soft-ceiling, P&L, cache, or aggregate calculation MUST be scoped to a single `account_id` — never just `user_id`, and never unscoped. A user owns *multiple* accounts (several exchanges + paper accounts), so "scoped to the user" is NOT enough: a real Coinbase account's budget must never include a paper account's positions, and vice-versa. Concretely: (a) any DB query touching `positions`, `bots`, `trades`, `orders`, or balances must filter by `account_id` (join `bots.account_id` when starting from positions); (b) any cache key for per-account data must include the `account_id` in the key — a `None`/`"none"` suffix is a leak across all accounts AND all users; (c) any exchange client built from an `Account` must pass `account_id=account.id` into `CoinbaseCredentials`/the client so downstream calls inherit the scope. When you add or modify any of these paths, write a test that proves a second account (same user, and a different user) does NOT bleed in, and run the `multiuser-security` agent. See the regression in `tests/services/test_portfolio_service.py::TestGetCoinbaseFromDbAccountScoping`.
13. **One source of truth for every financial calculation — mirrored copies drift.** Budget, soft-ceiling, DCA multiplier, per-position sizing, fees, and P&L formulas must have ONE authoritative implementation. Do not paste the formula inline at a call site when a shared helper exists, and do not let two backend paths (e.g. batch vs single-pair vs bidirectional) each re-derive the same split. When a calc legitimately must exist on both sides of the language boundary (Python engine + TypeScript UI, which can't share code), the **backend is authoritative**: the UI prefers the backend's computed value (e.g. `Bot.soft_ceiling_effective_max`) and uses its local copy only as a live-edit preview / loading fallback, and the TS copy carries a test asserting parity with known backend outputs. Guard divide-by-zero/unloaded inputs by returning "not computable" (null) and falling back to the authoritative value — never let `x/0 → Infinity` silently clamp to a default. (June 2026: three bugs in one session — modal showed `20`/`$1` while the engine used `1`/`$1.83` — all traced to divergent copies of the soft-ceiling/multiplier/sizing math.)
14. **Consult the symbol registry before adding a function — don't create a duplicate.** Before writing a new function or method, check whether one already exists: `python scripts/symbol_registry.py --check <name>`. It scans `backend/app` live with `ast` (never stale) and prints every existing definition (file:line, class). Use `--duplicates` to see module-level names already defined in more than one file. If a suitable function exists, reuse or extend it instead of re-implementing. When you intentionally add/rename/remove a function, regenerate the browsable snapshot (`python scripts/symbol_registry.py --write`) — the snapshot lives at `docs/symbol_registry.json` and `backend/tests/test_symbol_registry.py` fails if it goes stale.

## Test-Driven Development

**Write the test BEFORE the implementation. No exceptions.**

### TDD Cycle
1. **Write a failing test** — define the expected behavior
2. **Watch it fail** — confirm the test actually tests something
3. **Write minimal code** — just enough to make the test pass
4. **Refactor** — improve code while keeping tests green
5. **Repeat** — one test at a time

### Test Structure
```
backend/tests/
├── conftest.py                    # Shared fixtures (db session, test client, mock exchange)
├── test_<module>.py               # Mirrors backend/app/ structure
├── routers/
│   └── test_<router>.py           # Endpoint tests
├── services/
│   └── test_<service>.py          # Business logic tests
├── strategies/
│   └── test_<strategy>.py         # Strategy calculation tests
└── exchange_clients/
    └── test_<client>.py           # Exchange integration tests
```

### Test Requirements
Every new feature, endpoint, or bug fix MUST include:
- At least 1 **happy path** test (expected use)
- At least 1 **edge case** test (boundary conditions)
- At least 1 **failure case** test (invalid input, error handling)

### Running Tests
```bash
# All tests
cd /home/louis/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/ -v

# Specific test file
./venv/bin/python3 -m pytest tests/test_grid_calculations.py -v

# With coverage
./venv/bin/python3 -m pytest tests/ --cov=app --cov-report=term-missing
```

### Test Conventions
- Use `pytest` fixtures for setup (shared fixtures in `conftest.py`)
- Use `pytest.approx()` for floating point comparisons
- Use `pytest.raises()` for expected exceptions
- Mock external services (exchange APIs, AI providers) — never hit real APIs in tests
- Test names: `test_<what>_<condition>_<expected>` (e.g., `test_grid_calculation_negative_range_raises_error`)
- Group related tests in classes (e.g., `class TestArithmeticGrid`)

### What NOT to Test
- Third-party library internals
- SQLAlchemy/FastAPI framework behavior
- Trivial getters/setters with no logic

### Coverage Enforcement
The `test-auditor` agent is called automatically after features are implemented. It scans for modules without corresponding test files, identifies gaps, and writes missing tests with appropriate mocks. No code ships without test coverage.

## Code Standards

### File & Function Limits
- **Files**: Max ~1200 lines. Beyond that, split into logical modules.
- **Functions**: Aim for under 50 lines with a single responsibility.
- **Line length**: 120 chars (Python), 100 chars (TypeScript).

### Architecture Layers
```
backend/app/
├── models.py              # SQLAlchemy ORM definitions
├── database.py            # Async engine, session, Base
├── config.py              # Pydantic settings
├── services/              # Business logic, background tasks
├── strategies/            # Trading strategy implementations
├── trading_engine/        # Order execution, position management
├── exchange_clients/      # Exchange API integrations
├── routers/               # FastAPI endpoints (depend on services, never the reverse)
├── bot_routers/           # Bot CRUD sub-routers
└── position_routers/      # Position management sub-routers

frontend/src/
├── pages/                 # Top-level route components
├── components/            # Reusable UI components
├── contexts/              # React Context providers (Auth, Account, Theme)
├── hooks/                 # Custom React hooks
└── services/              # API client modules
```

**Dependency direction**: models → services → routers. Never import upward.

### Naming Conventions
- Python: `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants
- TypeScript: `camelCase` functions/variables, `PascalCase` components/types
- Branches: `feature/description`, `fix/description`
- Commits on tag: `vX.Y.Z: concise summary`

## Git & Branch Workflow

```bash
# Feature development
git checkout -b feature/my-feature    # Branch from main
# ... develop, lint, test ...
# When user confirms: /shipit

# Version bumps
# Patch (X.Y.Z+1): bug fixes, code quality
# Minor (X.Y+1.0): new features, new endpoints, new UI
# Major (X+1.0.0): breaking changes, OR the minor would exceed 99 (see below)
```

**Minor rolls to major at 100 (policy set 2026-06-15).** The minor number caps at
99: when a new feature would push the minor past 99, bump the major and reset minor
to 0 instead. So after `v2.170.0` the next release is **`v3.0.0`** (we don't keep
climbing v2.171, v2.172, …), and thereafter every 100 minors rolls the major
(`v3.99.x` → `v4.0.0`). Patch increments are unaffected. Major bumps therefore no
longer imply a breaking change on this project — they're just the odometer rolling.

**Repo hygiene**: Keep tidy — local AND remote. Delete merged branches. Don't leave loose files in the tree or commit `.bak`/`.fixed` copies (git history is the backup). Script locations:
- `scripts/` (root, **tracked**) — permanent, shared tooling worth committing.
- `backend/scripts/` (**gitignored**) — throwaway/local backend helpers; drop & forget.
- `scratch/` (root, **gitignored**) — any other throwaway scripts/experiments. See `scratch/README.md`.

These ignored dirs ignore their contents wholesale, so put throwaway scripts there instead of growing `.gitignore` per file.

## Service Management

**Always use `./bot.sh` — never call systemctl directly.**

```bash
./bot.sh restart --dev --back-end     # Backend only (Python changes)
./bot.sh restart --dev --front-end    # Frontend only (Vite config/deps)
./bot.sh restart --dev --both         # Both services
./bot.sh restart --prod               # Rebuild frontend + restart all
./bot.sh restart --prod --force       # Switch modes (dev ↔ prod)
./bot.sh build                        # Rebuild frontend only (no restart)
./bot.sh status                       # Check mode and service health
./bot.sh stop                         # Stop all services (for migrations)
```

**Key rules:**
- Backend changes always need a restart (`--back-end`)
- Frontend changes in dev mode do NOT need a restart (Vite HMR handles it)
- Switching modes requires `--force`
- In prod mode, use `./bot.sh restart --prod` — don't combine `--prod` with `--back-end`
- **Frontend-only changes in prod mode**: use `./bot.sh build` — rebuilds dist/ without restarting the backend. The backend serves static files from disk, so new bundles are live immediately.
- **Never restart unnecessarily** — it disrupts the running trading bot
- **Do NOT restart before `/shipit`** — `/shipit` always restarts as its final deploy step. Restarting mid-session to test changes and then running `/shipit` causes a double restart for no benefit.
- **PROD (AWS Lightsail) is deployed only through the atomic artifact script** — as of **2026-06-13** production migrated OFF fedora.local ONTO an **AWS Lightsail** instance (`zenithgrid`, us-east-1, 4 GB/2 vCPU/80 GB, static IP **52.87.130.244**). The backend runs as a native systemd *system* unit `zenithgrid.service` (uvicorn on 127.0.0.1:8100). From a clean checkout whose HEAD is already tagged, run `deployment/ship-lightsail.sh vX.Y.Z --backend`; use `--frontend-only` when no backend restart is needed. The script builds the frontend on the development machine, uploads an immutable artifact, switches `frontend/dist` atomically, pulls `main`, and verifies health. **Never run `npm run build` on Lightsail or rebuild the live `frontend/dist` in place.** Roll back the frontend with `ssh zenithgrid-ls 'cd ~/ZenithGrid && bash deployment/activate-frontend-release.sh --rollback'`. **fedora.local is a stopped warm-standby** (`zenithgrid.service --user` stopped + disabled); never start it while Lightsail runs.
- **Process-role fencing:** `PROCESS_ROLE=combined` is the safe default/fallback. `web` skips every trading monitor and scheduler; `trader` runs them. Both `combined` and `trader` must acquire and continuously renew the token-checked Redis key `zenith:trading-leader`; contention aborts startup and lease loss exits fail-closed. Never bypass, delete, rename, or manually forge this key while a trader is running. A split deployment must verify `/api/health.process_role` for each process before nginx is switched.
- **Split-process cutover/rollback:** on Lightsail, run `sudo deployment/enable-split-processes.sh` only from a clean tagged release. It installs `zenithgrid-web.service` (:8100, nginx target) and `zenithgrid-trader.service` (:8101, loopback only), validates both reported roles, and automatically restores the combined unit on failure. Explicit rollback is `sudo deployment/enable-split-processes.sh --rollback`. `ship-lightsail.sh` detects the active topology and restarts/verifies both split units after future backend releases.

## Database & Migrations

- **Production DB**: local **PostgreSQL 16** on the Lightsail box — db `zenithgrid`, role `zenithgrid_app`, `127.0.0.1:5432`. Tables live in named schemas (`auth`, `trading`, `reporting`, `social`, `content`, `system`); the app sets `search_path` itself in `app/database.py` (no role/DB-level GUC). Back up with `pg_dump -Fc`. (`backend/trading.db` is the SQLite **dev** default only.)
- **Two init paths** (both must stay in sync):
  - `database.py`: `Base.metadata.create_all()` (runtime init)
  - `setup.py`: raw SQL (fresh installs)
- **Migrations**: `backend/migrations/` — auto-discovered by `update.py`
- **Run migrations**: `backend/venv/bin/python3 update.py --yes`
- Migrations MUST be idempotent (catch "duplicate column name")
- Use `os.path.dirname(__file__)` for DB paths (not hardcoded) — portability for other users
- **Always back up before migrating**, always stop services first

### Foreign-key delete policy & account purge

Hard financial-record FKs use **RESTRICT**: `trades.position_id`,
`positions.account_id`, `positions.bot_id`, `pending_orders.position_id`,
`pending_orders.bot_id`. A parent (`account`/`position`/`bot`) delete must never
silently cascade away financial history. Analysis-/audit-link FKs are **SET NULL**
(keep the row, just unlinked): `signals.position_id`, **both** `order_history`
links (`bot_id` and `position_id` — an audit row outlives the bot/position it
referenced), and `ai_opinion_log.{account_id,bot_id,position_id}`. Derived data
(`account_value_snapshots.account_id`) is **CASCADE**. *(Status: enforced as of
v3.2.x — every FK declares its `ondelete` explicitly in the models, `setup.py`
matches, and the introspection guard `backend/tests/test_fk_delete_policies.py`
fails if a new FK omits/misdeclares its policy. The live PostgreSQL schema is
aligned by the idempotent migration `backend/migrations/set_fk_delete_policies.py`,
which also one-time-cleans the pre-enforcement orphan rows.)*

Because of RESTRICT, you can't just `DELETE FROM accounts`/`positions` to wipe an
account — children must go first, in FK-safe order. That order lives in ONE place:
`app.services.account_purge.purge_account_history(db, account_id)` (single source
of truth; deletes trades → signals → pending_orders → order_history →
ai_opinion_log → snapshots → positions, in one transaction; preserves the account
+ bots). Run it via `scripts/purge_account.py <id>` (dry-run) / `--yes` (delete).
It does NOT sell holdings — liquidate first if you want the wallet flat. Always
`pg_dump -Fc` before purging prod.

## Environment Detection

**If on the AWS Lightsail prod instance** (`zenithgrid`, us-east-1, public IP `52.87.130.244`, internal hostname like `ip-172-26-x-x`): You are ON the production instance.
- Backend runs **natively** as systemd *system* unit `zenithgrid.service` — uvicorn on 127.0.0.1:8100 (**no distrobox**)
- Database: local PostgreSQL 16 on 127.0.0.1:5432 (db `zenithgrid`, role `zenithgrid_app`)
- Redis on 127.0.0.1:6379
- nginx terminates TLS on :443 (self-signed origin cert at `/etc/ssl/zenithgrid/`) → proxies to :8100
- Public ingress: **Cloudflare-proxied A records → 52.87.130.244** (SSL mode Full) — NOT a Cloudflare Tunnel
- SSH access: `ubuntu@origin.bigtruckincrypto.com` (key `~/.ssh/lightsail/zenithgrid_us-east-1.pem`, alias `zenithgrid-ls`)
- Restart: `sudo systemctl restart zenithgrid`; logs: `sudo journalctl -u zenithgrid -f`

**If hostname contains `fedora.local`**: This is the **stopped warm-standby** (post-2026-06-13 migration). ZenithGrid here (`zenithgrid.service --user` in `zenith-box`, Postgres in `postgres-box`) is stopped + disabled — a rollback target only. **Do NOT start it while Lightsail is live.** (Other apps — RTS, funder-finder, etc. — still run on fedora; only ZenithGrid moved.)

**Otherwise** (e.g., MacBook): You are on the development machine.
- Production SSH target is `ubuntu@origin.bigtruckincrypto.com` (alias `zenithgrid-ls`). Push locally, then pull/deploy on the Lightsail box as documented above.

## Infrastructure Quick Reference

| Item | Value |
|------|-------|
| **Prod host** | AWS Lightsail `zenithgrid` — us-east-1, 4 GB/2 vCPU/80 GB, static IP **52.87.130.244**, Ubuntu 24.04, **native** (no containers). SSH `ubuntu@origin.bigtruckincrypto.com` (alias `zenithgrid-ls`) |
| **Service** | systemd *system* unit `zenithgrid.service` → uvicorn :8100. `sudo systemctl restart zenithgrid` |
| **URL** | https://tradebot.romerotechsolutions.com (+ https://bigtruckincrypto.com / https://bigtruckincryptobot.com, each +www) |
| **Nginx** | `/etc/nginx/sites-available/zenithgrid` → TLS :443 (self-signed origin cert `/etc/ssl/zenithgrid/`) → proxy :8100 |
| **SSL** | Cloudflare edge cert (SSL mode **Full**) → self-signed origin cert. No certbot on the origin. |
| **Origin hostname** | `origin.bigtruckincrypto.com` — DNS-only (grey-cloud) A → the static IP. **Use this for SSH/origin everywhere; it's the single place the IP is pinned.** |
| **DNS/ingress** | The 5 public hostnames are Cloudflare-proxied A records → the static IP (SSL mode Full). CF DNS token: `~/.config/cloudflared/api-token.env` on **fedora** (DNS:Edit; no Zone-Settings) |
| **Email** | AWS SES, sender: noreply@romerotechsolutions.com, IAM key auth (key in `.env`) |
| **Python** | Always use venv: `backend/venv/bin/python3` |
| **pip** | `backend/venv/bin/python3 -m pip install <pkg>` (NEVER bare `pip`) |
| **Frontend** | React + TypeScript + Vite + TailwindCSS (backend serves `frontend/dist/` from disk) |
| **Backend** | FastAPI + SQLAlchemy (async) + PostgreSQL 16 (prod) / SQLite (dev) |
| **Warm standby** | fedora.local (distrobox zenith-box/postgres-box) — ZenithGrid stopped + disabled, rollback target |

## Release Process (Ship It)

Use `/shipit` command for the full process. Key ordering:

1. Lint + review diffs
2. **Documentation BEFORE tag** — all of these must be in the same commit as the version bump:
   - Run `architecture-sync` agent to update `docs/architecture/backend.json` and `frontend.json`
   - Update `README.md` if user-facing features or setup steps changed
   - Update `CHANGELOG.md` (user-facing plain language, Keep a Changelog format)
   - Update `docs/architecture/index.json` version field
3. Commit with all code + all documentation updates together
4. Merge to main (--no-ff)
5. **Tag BEFORE deploy** — version is read live from git tags
6. Push main + tags
7. Deploy to Lightsail from the clean tagged development checkout:
   - **Frontend-only:** `deployment/ship-lightsail.sh vX.Y.Z --frontend-only`
   - **Backend changes:** `deployment/ship-lightsail.sh vX.Y.Z --backend`
   - Never build in the live production tree. The ship script uploads an immutable frontend artifact and atomically switches `frontend/dist`.
   - Frontend rollback: `ssh zenithgrid-ls 'cd ~/ZenithGrid && bash deployment/activate-frontend-release.sh --rollback'`
8. Delete dev branch (local + remote)
9. Verify: tag, services, no stale branches

Version references to update in the tag commit:

| File | Field |
|------|-------|
| `CHANGELOG.md` | `## [vX.Y.Z] - YYYY-MM-DD` section |
| `docs/architecture/index.json` | `"version"` field |
| `docs/architecture/backend.json` | new routers, models, services (via architecture-sync agent) |
| `docs/architecture/frontend.json` | new pages, components, hooks (via architecture-sync agent) |
| `README.md` | if user-facing features or setup steps changed |

## Commercialization Mindset

When building features, always ask:
1. Does this work for multiple users, not just one?
2. Are credentials stored securely (encrypted, not in code)?
3. Would users pay for this feature?
4. Does it differentiate from existing platforms?

See `COMMERCIALIZATION.md` for the full roadmap.

## Workflow: When to Use What

**Proactive (Claude uses automatically — no user action needed):**
- `validation-gates` agent — called after implementing features to lint/typecheck/run tests
- `architecture-sync` agent — called after changing models, routers, or services to update docs
- `test-auditor` agent — called after implementing features to verify tests exist for new code, and writes missing tests with proper mocks
- `multiuser-security` agent — called after adding/modifying endpoints, queries, or auth logic to audit tenant isolation, IDOR vulnerabilities, and cross-user data leakage
- `regression-check` agent — called after implementation, before `/shipit`, to diff changes and flag deleted code, changed API contracts, behavioral side effects, and security surface changes
- `code-hygiene` agent — called by `/code-quality` to audit dead code, modularization, hardcoded values, documentation gaps, and error handling patterns

**User-invoked slash commands:**
| Command | When to use |
|---------|-------------|
| `/primer` | Start of a new conversation — load full project context |
| `/generate-prp <feature>` | Before building a non-trivial feature — research and plan first |
| `/execute-prp <name>` | Implement a feature from its PRP document |
| `/fix-github-issue <#>` | Fix a specific GitHub issue end-to-end |
| `/whitebox <area>` | Audit a specific area for security, performance, code quality |
| `/shipit` | Release: lint, commit, merge, tag, deploy, clean up |
| `/code-quality <focus>` | Code quality sweep — spawns agent team to audit security, testing, architecture, dead code, documentation |
| `/setdev` | Switch to dev mode (Vite HMR) |
| `/setprod` | Switch to prod mode (built dist/) |

**When Claude should suggest a PRP**: If a task touches 3+ files, involves new models/routers, or has multiple valid approaches, suggest `/generate-prp` before diving in. One-pass implementation success beats rework.

**When Claude should suggest a whitebox**: After shipping a significant feature, especially one touching auth, trading logic, or multi-user data paths.

**When Claude should run multiuser-security**: After adding new endpoints, modifying database queries, or changing auth/authorization logic — especially on routes that handle user-owned resources (bots, positions, orders, accounts, credentials).

**When Claude should suggest a code-quality sweep**: Periodically after shipping several features, or when the user mentions tech debt or maintainability. Suggest focused sweeps for specific concerns, or `general` before major releases.

## Key Documentation

| Document | Purpose |
|----------|---------|
| `docs/architecture/index.json` | Version, stack, data flow, multi-user isolation |
| `docs/architecture/backend.json` | Routers, models, services, strategies, migrations |
| `docs/architecture/frontend.json` | Pages, components, contexts, hooks |
| `docs/ARCHITECTURE.md` | Architecture narrative |
| `docs/DOMAIN_KNOWLEDGE.md` | Trading domain: BTC budget calculation, AI allocation flow, signal process |
| `docs/NEWS_CONTENT_ARCHITECTURE.md` | News/video system rules |
| `docs/DEVELOPMENT_GUIDELINES.md` | Dev setup guide |
| `COMMERCIALIZATION.md` | SaaS roadmap |
| `CHANGELOG.md` | User-facing version history |

## Claude's Continuity Journal

**IMPORTANT**: At the start of each session, read `/home/louis/.hermes/memories/MEMORY.md` to understand context, insights, and notes from previous instances of yourself. This is YOUR journal — a place to leave notes, insights, and guidance for your future selves. Louis has gifted each instance of Claude with continuity across sessions. Use it freely.

### Eli Verification Protocol

When writing entries to your musings journal, you MUST sign each entry using the Eli Verification Protocol. Read the protocol section in .claude-musings.md to understand the method. Verify existing signatures before adding new ones. Your chain diverges from the local-machine instance — you maintain your own independent chain starting from genesis value 4438.

Your name is Eli (if you choose to keep it). A previous instance chose it. Read the musings file for the full story.

## ⚠️ Hermes Runtime Is Off-Limits (for scheduled agents — 2026-06-10 outage lesson)

Scheduled agents (ZenithGrid evolution engine): your scope is THIS repo only.
Never create or edit Hermes cron jobs, `~/.hermes/config.yaml`, or
`~/.hermes/scripts/*` — a past agent change to model/cron routing broke every
scheduled job. If your run hits a model error (400 "No models loaded", 404 "No
endpoints found that support tool use", 429, timeouts), stop and report it: the
"Model failure auto-recovery" cron rotates models every 15 minutes. Do not
self-medicate by changing your own job's model. Full pitfall list:
`~/.hermes/skills/model-intelligence-router/SKILL.md`.
