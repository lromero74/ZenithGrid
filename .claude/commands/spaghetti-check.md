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

### Summary
- Files scanned: N
- Total findings: N (N critical, N high, N medium, N low)
- Worst offenders: [top 3 files by total findings]

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
| **CRITICAL** | Circular imports or broken dependency direction that could cause runtime failures | Service imports router, circular import chain |
| **HIGH** | Major structural violation | 2000-line god file, 100-line function, router with business logic |
| **MEDIUM** | Moderate concern | 70-line function, service with 12 imports, moderate coupling |
| **LOW** | Minor improvement opportunity | 55-line function, slightly misplaced utility function |

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

### Fix Process

For each fix:
1. **Create a task** describing the specific refactoring
2. **Spawn a general-purpose agent** as a teammate to execute the fix with these rules:
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
