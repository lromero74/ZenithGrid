Run a spaghetti code audit focused on code length, modularity, and separation of concerns. Focus area: $ARGUMENTS

## Instructions

You are running a `/spaghetti-check` — a focused structural quality audit of the ZenithGrid codebase. This is NOT a full code-quality sweep. It targets exactly three things:

1. **Code Length Violations** — files and functions that exceed project limits
2. **Modularity & Separation of Concerns** — dependency direction, god files, cross-layer reaches
3. **Spaghetti Detection** — circular imports, tangled dependencies, functions doing too much

### Argument Parsing

Parse the arguments for **scope** and **mode**:

**Scope** (what to audit):
- `backend` — audit only `backend/app/`
- `frontend` — audit only `frontend/src/`
- `full` or no scope argument — audit both

**Mode** (what to do):
- `--fix` — after auditing, fix all findings and validate with tests
- No flag — audit only (read-only, report findings)

Examples:
- `/spaghetti-check` → full audit, read-only
- `/spaghetti-check backend` → backend audit, read-only
- `/spaghetti-check --fix` → full audit + fix + validate
- `/spaghetti-check backend --fix` → backend audit + fix + validate
- `/spaghetti-check frontend --fix` → frontend audit + fix + validate

---

## Phase 1: Audit

### Orchestration

1. **Create a team** using TeamCreate named `spaghetti-check`
2. **Create and assign tasks** for three parallel agents:

#### Agent 1: File & Function Size Auditor (code-hygiene agent, modularization focus)

Spawn a `code-hygiene` agent with these specific instructions:
- Run modularization focus ONLY (Section 2 from code-hygiene.md)
- Measure every file with `wc -l` — flag any > 1200 lines
- Measure every function — flag any > 50 lines (exclude test files)
- Flag functions with 5+ parameters (excluding `self`, `db`, `current_user`)
- Flag files with 10+ distinct module imports (god files)
- For each violation, suggest specific split points or decomposition strategies
- **Read-only** — report only, do not modify code

#### Agent 2: Dependency Direction & Import Auditor (general-purpose agent)

Spawn a `general-purpose` agent with these instructions:
- **Check dependency direction violations** in `backend/app/`:
  - Routers must NOT import from other routers
  - Services must NOT import from routers
  - Models must NOT import from services or routers
  - Scan every `import` and `from ... import` statement in each layer
- **Check circular imports**:
  - Build an import graph for `backend/app/`
  - Test with: `cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -c "from app.routers.<module> import router"` for each router
  - Test with: `cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -c "from app.services.<module> import <class>"` for each service
- **Check frontend import hygiene** (if auditing frontend):
  - Pages should import from components/hooks/services/contexts — not from other pages
  - Components should not import from pages
  - Hooks should not import from components or pages
- Report every violation with file:line and the offending import
- **Read-only** — report only, do not modify code

#### Agent 3: Coupling & Complexity Analyzer (general-purpose agent)

Spawn a `general-purpose` agent with these instructions:
- **Identify tightly coupled modules**:
  - Find files that import 5+ symbols from a single other module (high coupling)
  - Find modules imported by 10+ other files (potential god modules)
  - Find functions that call 5+ other functions from different modules (orchestration bloat)
- **Identify responsibility violations**:
  - Scan router files for business logic (math, loops, conditionals beyond request/response handling) — this belongs in services
  - Scan service files for HTTP/request handling logic — this belongs in routers
  - Scan model files for business logic — this belongs in services
- **Measure function complexity** (Python backend):
  - Count `if/elif/else/for/while/try/except/with` keywords per function
  - Flag functions with cyclomatic complexity > 10 (rough proxy: count branches)
- Report each finding with file:line, what's wrong, and where the logic should live
- **Read-only** — report only, do not modify code

#### Agent 4: Horizontal Scalability Auditor (general-purpose agent)

Spawn a `general-purpose` agent with these instructions:

**First, read `/home/ec2-user/ZenithGrid/docs/SCALABILITY_ROADMAP.md` in full.** It defines the architectural direction (Phase 1 done, Phase 2 in progress, Phase 3 future). Use it as the reference for what patterns are intended vs. accidental violations.

Audit `backend/app/` for patterns that would prevent horizontal scaling (running 2+ backend processes) or make microservice extraction harder. Flag regressions — patterns that undo or bypass Phase 2 prep work already done.

**Check 1 — Module-level mutable singletons (break multi-process)**
Scan for module-level variables that hold mutable shared state:
- `asyncio.Lock()` or `asyncio.Queue()` at module level (loop-bound — break when shared across threads or processes)
- In-memory dicts/lists used as caches or rate-limit state outside of `SimpleCache` or `ServiceRegistry`
- Module-level exchange client instances or DB session objects
- Any `asyncio.Lock` NOT using the `(id(loop), key)` per-loop pattern (see roadmap Fix I/J for the approved pattern)

**Check 2 — Cross-domain direct DB queries (prevent schema extraction)**
The 6 database schemas are: `auth`, `trading`, `reporting`, `social`, `content`, `system`.
Flag any service in one domain that directly queries a model from a different domain — especially:
- `content` or `social` services querying `trading` models directly
- `reporting` services querying `trading` tables via ORM (instead of through a service interface)
- Any file in `services/` joining across schema boundaries in a single query
These cross-schema joins are the main blocker for extracting a domain into its own service/database.

**Check 3 — Direct DB polling instead of event bus**
The event bus (`app/event_bus.py`) publishes: `ORDER_FILLED`, `POSITION_OPENED`, `POSITION_CLOSED`, `BOT_STARTED`, `BOT_STOPPED`, `GOAL_ACHIEVED`.
Flag any service or monitor that:
- Polls a DB table on a timer to detect order fills, position changes, or bot state changes — when it should subscribe to the event bus instead
- Imports from `buy_executor`, `sell_executor`, or `limit_order_monitor` to react to fills (instead of subscribing to `ORDER_FILLED`)

**Check 4 — ServiceRegistry bypass**
`app/registry.py` provides `ServiceRegistry` with: `event_bus`, `broadcast`, `rate_limiter`, `credentials`.
Flag any file that:
- Imports `ws_manager` directly instead of using `registry.broadcast` (bypasses `BroadcastBackend` seam)
- Imports `rate_limiters` helpers directly in new code instead of using `registry.rate_limiter`
- Imports `get_exchange_client_for_account` directly instead of using `registry.credentials`
These bypasses add new call sites that would need manual migration during Phase 3 extraction.

**Check 5 — Sleep-loop background tasks (should be APScheduler)**
The roadmap completed migration of Tier 2/3 tasks to APScheduler (v2.126.0).
Flag any new `asyncio.sleep()` loop pattern in non-Tier-1 code (i.e., outside the 6 main trading monitors: MultiBotMonitor, LimitOrderMonitor, OrderReconciliationMonitor, PropGuardMonitor, PerpsMonitor, MissingOrderDetector).
New background tasks should use `scheduler.add_job()` not hand-rolled sleep loops.

**Check 6 — Hardcoded `async_session_maker` imports (break secondary loop)**
The roadmap (Fix K) established that services used from the secondary event loop must accept an injected `session_maker` parameter. Hardcoded `from app.database import async_session_maker` inside exchange clients or monitors creates cross-loop DB pool conflicts.
Flag any new occurrences of `from app.database import async_session_maker` inside:
- Exchange client implementations (`*_client.py`)
- Monitor classes (`*_monitor.py`)
- Services that are registered on the secondary loop

**Check 7 — WebSocket manager direct fan-out calls (prevent Redis swap)**
`app/services/broadcast_backend.py` provides the `BroadcastBackend` seam. The swap point (`InProcessBroadcast` → `RedisBroadcast`) only works if all fan-out calls go through it.
Grep for direct calls to `ws_manager.broadcast(`, `ws_manager.send_to_user(`, `ws_manager.send_to_room(` in routers and services. Each is a call site that bypasses the seam and would need manual migration in Phase 3.

Report each finding with file:line, the specific scalability concern, and the correct pattern from the roadmap.
**Read-only** — report only, do not modify code.

#### Agent 5: Security & RBAC Auditor (multiuser-security agent)

Spawn a `multiuser-security` agent with these instructions:

Perform a full security and RBAC audit of `backend/app/`. This is a multi-user trading platform — every endpoint that touches user data must be protected. Flag anything that could allow one user to access or modify another user's data (IDOR), bypass authentication, or escalate privileges.

**Check 1 — Missing auth dependencies**
Every endpoint that touches user-owned data must have `Depends(get_current_user)` (or an equivalent admin/MFA dependency). Scan all routers for:
- Endpoints with no auth dependency at all
- Endpoints that accept a `user_id` or `account_id` from the request body/query params without verifying it matches the authenticated user
- POST/PUT/DELETE endpoints with weaker auth than their corresponding GET endpoints

**Check 2 — IDOR vulnerabilities (tenant isolation)**
For every endpoint that accepts a resource ID (bot_id, account_id, position_id, report_id, etc.), verify that the query filters by `user_id` or validates ownership before returning/modifying the record. Flag any query that fetches by ID alone without a user ownership check.

**Check 3 — RBAC enforcement**
The app has roles/permissions in the `auth` schema. Audit:
- Admin-only operations (ban, user management, system settings) — do they check admin role?
- Any endpoint that performs privileged actions (e.g., force-selling another user's positions, accessing all users' data) without an explicit role check
- The `admin_router.py` endpoints — do they ALL require admin role, or are some accessible by regular users?

**Check 4 — MFA bypass paths**
Panic sell and other high-risk operations require MFA. Flag:
- Any high-risk endpoint (mass liquidation, account deletion, API key changes) that does NOT require MFA
- Any path where MFA can be skipped (e.g., via a different endpoint that does the same action)

**Check 5 — Sensitive data exposure**
- Endpoints that return API keys, decrypted credentials, or secrets in responses
- Error messages that leak internal implementation details (stack traces, SQL errors, file paths)
- Endpoints that return other users' data in aggregate responses (e.g., leaderboards including private info)

**Check 6 — Rate limiting coverage**
The app has rate limiters in `auth_routers/rate_limiters.py`. Flag:
- Auth endpoints (login, register, password reset, MFA verify) missing rate limiting
- Any endpoint that could be used for enumeration (user lookup, exists checks) without rate limiting

Report every finding with file:line, the vulnerability type, severity, and specific fix.
**Read-only** — report only, do not modify code.

3. **Wait for all agents** to complete
4. **Consolidate** into a single report

### Report Format

```
## Spaghetti Check — [focus area]

### File Size Violations
| Severity | File | Lines | Limit | Recommendation |
|----------|------|-------|-------|----------------|

### Function Size Violations
| Severity | File | Function | Lines | Recommendation |
|----------|------|----------|-------|----------------|

### God Files (10+ distinct imports)
| Severity | File | Import Count | Top Imports |
|----------|------|-------------|-------------|

### Dependency Direction Violations
| Severity | File | Line | Violation | Fix |
|----------|------|------|-----------|-----|

### Circular Imports
| Severity | Cycle | How Detected |
|----------|-------|-------------|

### High Coupling
| Severity | File | Coupling Type | Details | Recommendation |
|----------|------|--------------|---------|----------------|

### Misplaced Logic (SoC Violations)
| Severity | File | Line | What's There | Where It Should Be |
|----------|------|------|-------------|-------------------|

### Complex Functions (high cyclomatic complexity)
| Severity | File | Function | Branches | Recommendation |
|----------|------|----------|----------|----------------|

### Scalability Violations
| Severity | File | Line | Check | Problem | Correct Pattern |
|----------|------|------|-------|---------|----------------|

### Security & RBAC Violations
| Severity | File | Line | Vulnerability Type | Details | Fix |
|----------|------|------|-------------------|---------|-----|

### Summary
- Files scanned: N
- Total findings: N (N critical, N high, N medium, N low)
- Worst offenders: [top 3 files by total findings]
- Scalability blockers for Phase 3: N
- Security/RBAC gaps: N

### Priority Actions
1. [ ] [Most impactful fix]
2. [ ] [Second most impactful]
3. [ ] [Third most impactful]

### Quick Wins
- [ ] [Easy fix 1]
- [ ] [Easy fix 2]
```

### Severity Levels

| Level | Meaning | Example |
|-------|---------|---------|
| **CRITICAL** | Runtime failure risk or active security vulnerability | Circular import, IDOR with no ownership check, asyncio.Lock cross-loop |
| **HIGH** | Major structural or security violation | 2000-line god file, missing auth on sensitive endpoint, Phase 3 extraction blocker |
| **MEDIUM** | Moderate concern | 70-line function, misplaced business logic, new sleep-loop task |
| **LOW** | Minor improvement opportunity | 55-line function, slightly misplaced utility, low-traffic registry bypass |

### Important Rules (Phase 1)

- **All agents are read-only** — no code modifications, no file writes, no git operations
- **No false positives** — each agent must read the actual code and verify
- **Respect project conventions** — limits are in CLAUDE.md (1200 lines/file, 50 lines/function, 120 char Python, 100 char TypeScript)
- **Exclude test files** from function length checks (tests can be longer)
- **Exclude `__init__.py`** from god file checks (re-exports are expected there)

---

## Phase 2: Fix (only if `--fix` flag is present)

**If `--fix` was NOT passed, skip this phase entirely.** Shutdown the team, clean up, and present the audit report.

**If `--fix` WAS passed**, proceed after consolidating the audit report:

### Fix Prioritization

Work through findings in this order:
1. **CRITICAL** — circular imports, broken dependency direction (runtime failures)
2. **HIGH** — god files (>2000 lines), god functions (>100 lines), service→router inversions
3. **MEDIUM** — moderate size violations (>1200 lines, >50 lines), misplaced logic, coupling
4. **LOW** — skip unless quick wins (constant moves, minor import cleanups)

### TDD & Diff-Safety Rules (MANDATORY for every fix)

These rules apply to every fix agent, no exceptions:

#### Before touching any code:
1. **Check for existing test coverage** — search `tests/` for tests that exercise the function/module you're about to refactor
2. **If no test covers the behavior** — write the test FIRST:
   - Write the test, run it, confirm it **passes** (proving the behavior exists)
   - Commit the test on its own before making any structural change
   - This is your safety net — it proves you haven't broken anything after refactoring
3. **If a test already exists** — run it now to confirm it passes before you touch the code

#### While making changes:
4. **Run `git diff` before and after** each logical change — read the diff to verify:
   - No behavior was removed (deleted code should only be structural, never logic)
   - No function signatures changed unless all callers were updated
   - No import was removed unless the symbol moved somewhere else
5. **Run affected tests after each file change** — don't batch up changes and test at the end

#### After the fix:
6. **Run the test you wrote (or found) again** — confirm it still passes
7. **Run the full test file** for each module you touched — not just the one test

### Fix Process

For each fix:
1. **Create a task** describing the specific refactoring
2. **Spawn a general-purpose agent** as a teammate to execute the fix with these rules:
   - Follow the TDD & Diff-Safety Rules above — no exceptions
   - Work on one file/module at a time
   - When splitting files: update ALL import consumers across the codebase
   - When moving functions: update ALL callers, delete the old location completely
   - No re-export shims, no backwards-compat wrappers, no proxy modules (per CLAUDE.md)
   - Preserve all existing behavior — refactoring only, no feature changes
   - Run `flake8 --max-line-length=120` on every modified Python file
   - Run `npx tsc --noEmit` if any TypeScript files were modified
3. **Parallelize independent fixes** — fixes to unrelated files can run simultaneously
4. **Serialize dependent fixes** — if fix B depends on fix A's output (e.g., splitting a file then moving logic out of it), run them sequentially

### Fix Limits

- **Maximum 5 fix agents** running in parallel (to stay within resource limits)
- **Quick wins first** — knock out constant moves, import cleanups, and small extractions before tackling large file splits
- **Large refactors get their own branch** — if a fix touches 5+ files, note it for a separate PRP rather than fixing inline

---

## Phase 3: Validate (only if `--fix` flag is present)

After all fixes are complete:

### 3a. Run Full Test Suite
```bash
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/ -v
```
- ALL existing tests must pass
- If any test fails, diagnose and fix immediately — the refactoring broke something

### 3b. Run Linting
```bash
cd /home/ec2-user/ZenithGrid
backend/venv/bin/python3 -m flake8 --max-line-length=120 backend/app/
cd frontend && npx tsc --noEmit
```
- Fix any lint or type errors introduced by the refactoring

### 3c. Run Import Validation
For every module that was modified, verify it still imports cleanly:
```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -c "from app.routers.<module> import router"
./venv/bin/python3 -c "from app.services.<module> import <class>"
```

### 3d. Re-audit
Run a quick re-audit of the fixed files to confirm:
- File sizes are now within limits
- Function sizes are now within limits
- Dependency direction is correct
- No new circular imports were introduced

### 3e. Report Results

Produce a final fix report:
```
## Spaghetti Check — Fix Results

### Fixes Applied
| # | Category | File(s) | What Changed | Before | After |
|---|----------|---------|-------------|--------|-------|

### Validation Results
- Tests: X passed, Y failed
- Lint (Python): PASS/FAIL
- Type check (TS): PASS/FAIL
- Import validation: PASS/FAIL

### Remaining Issues (deferred)
| # | Severity | Issue | Reason Deferred |
|---|----------|-------|----------------|

### Files Modified
[list of all files touched by fixes]
```

---

## Cleanup

- **Shutdown the team** — send shutdown_request to all teammates after Phase 1 (audit-only mode) or Phase 3 (fix mode)
- **Clean up** — TeamDelete after all teammates have shut down
