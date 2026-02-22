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
9. **Think "How does 3Commas do it?"** when building features — match their UX patterns.

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
# Major (X+1.0.0): breaking changes (rare, user specifies)
```

**Repo hygiene**: Keep tidy — local AND remote. Delete merged branches. One-off scripts go in `scripts/`.

## Service Management

**Always use `./bot.sh` — never call systemctl directly.**

```bash
./bot.sh restart --dev --back-end     # Backend only (Python changes)
./bot.sh restart --dev --front-end    # Frontend only (Vite config/deps)
./bot.sh restart --dev --both         # Both services
./bot.sh restart --prod               # Rebuild frontend + restart all
./bot.sh restart --prod --force       # Switch modes (dev ↔ prod)
./bot.sh status                       # Check mode and service health
./bot.sh stop                         # Stop all services (for migrations)
```

**Key rules:**
- Backend changes always need a restart (`--back-end`)
- Frontend changes in dev mode do NOT need a restart (Vite HMR handles it)
- Switching modes requires `--force`
- In prod mode, use `./bot.sh restart --prod` — don't combine `--prod` with `--back-end`
- **Never restart unnecessarily** — it disrupts the running trading bot

## Database & Migrations

- **Production DB**: `backend/trading.db`
- **Two init paths** (both must stay in sync):
  - `database.py`: `Base.metadata.create_all()` (runtime init)
  - `setup.py`: raw SQL (fresh installs)
- **Migrations**: `backend/migrations/` — auto-discovered by `update.py`
- **Run migrations**: `backend/venv/bin/python3 update.py --yes`
- Migrations MUST be idempotent (catch "duplicate column name")
- Use `os.path.dirname(__file__)` for DB paths (not hardcoded) — portability for other users
- **Always back up before migrating**, always stop services first

## Environment Detection

**If hostname contains `ec2.internal`**: You are ON the EC2 production instance.
- Services run locally — no SSH needed
- Database is local: `backend/trading.db`
- This IS production — be careful

**Otherwise** (e.g., MacBook): You are on the development machine.
- Push to git, pull on testbot via SSH

## Infrastructure Quick Reference

| Item | Value |
|------|-------|
| **EC2** | t2.micro, 1 vCPU, 1GB RAM, Amazon Linux 2023, us-east-1 |
| **URL** | https://tradebot.romerotechsolutions.com |
| **Nginx** | `/etc/nginx/conf.d/tradebot.conf` → reverse proxy to :8100 |
| **SSL** | Let's Encrypt via certbot (`sudo certbot renew --nginx`) |
| **Email** | AWS SES, sender: noreply@romerotechsolutions.com, IAM role auth |
| **Python** | Always use venv: `backend/venv/bin/python3` |
| **pip** | `backend/venv/bin/python3 -m pip install <pkg>` (NEVER bare `pip`) |
| **Frontend** | React + TypeScript + Vite + TailwindCSS |
| **Backend** | FastAPI + SQLAlchemy (async) + SQLite |

## Release Process (Ship It)

Use `/shipit` command for the full process. Key ordering:

1. Lint + review diffs
2. Commit with changelog + version updates (same commit)
3. Merge to main (--no-ff)
4. **Tag BEFORE restart** — backend snapshots `git describe --tags` at import time
5. Push main + tags
6. Deploy via `./bot.sh restart`
7. Delete dev branch (local + remote)
8. Verify: tag, services, no stale branches

Version references to update in the tag commit:

| File | Field |
|------|-------|
| `CHANGELOG.md` | `## [vX.Y.Z] - YYYY-MM-DD` section |
| `docs/architecture.json` | `"version"` field |

## Commercialization Mindset

When building features, always ask:
1. Does this work for multiple users, not just one?
2. Are credentials stored securely (encrypted, not in code)?
3. Would users pay for this feature?
4. Does it differentiate from 3Commas?

See `COMMERCIALIZATION.md` for the full roadmap.

## Workflow: When to Use What

**Proactive (Claude uses automatically — no user action needed):**
- `validation-gates` agent — called after implementing features to lint/typecheck
- `architecture-sync` agent — called after changing models, routers, or services to update docs

**User-invoked slash commands:**
| Command | When to use |
|---------|-------------|
| `/primer` | Start of a new conversation — load full project context |
| `/generate-prp <feature>` | Before building a non-trivial feature — research and plan first |
| `/execute-prp <name>` | Implement a feature from its PRP document |
| `/fix-github-issue <#>` | Fix a specific GitHub issue end-to-end |
| `/whitebox <area>` | Audit a specific area for security, performance, code quality |
| `/shipit` | Release: lint, commit, merge, tag, deploy, clean up |
| `/setdev` | Switch EC2 to dev mode (Vite HMR) |
| `/setprod` | Switch EC2 to prod mode (built dist/) |

**When Claude should suggest a PRP**: If a task touches 3+ files, involves new models/routers, or has multiple valid approaches, suggest `/generate-prp` before diving in. One-pass implementation success beats rework.

**When Claude should suggest a whitebox**: After shipping a significant feature, especially one touching auth, trading logic, or multi-user data paths.

## Key Documentation

| Document | Purpose |
|----------|---------|
| `docs/architecture.json` | Complete architecture reference (models, routers, services, migrations) |
| `docs/ARCHITECTURE.md` | Architecture narrative |
| `docs/DOMAIN_KNOWLEDGE.md` | Trading domain: BTC budget calculation, AI allocation flow, signal process |
| `docs/NEWS_CONTENT_ARCHITECTURE.md` | News/video system rules |
| `docs/DEVELOPMENT_GUIDELINES.md` | Dev setup guide |
| `COMMERCIALIZATION.md` | SaaS roadmap |
| `CHANGELOG.md` | User-facing version history |
