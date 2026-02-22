Run a comprehensive code quality sweep. Focus area: $ARGUMENTS

## Instructions

You are running a `/code-quality` sweep on the ZenithGrid codebase. Parse the focus area from the arguments above. If no argument is provided, default to `general`.

### Focus Areas & Agent Routing

| Focus | Agents to Spawn | Purpose |
|-------|-----------------|---------|
| `general` | multiuser-security, test-auditor, code-hygiene, validation-gates | Full sweep across all quality dimensions |
| `security` | multiuser-security, code-hygiene (hardcoded + error-handling focus) | Security vulnerabilities, hardcoded secrets, unsafe error handling |
| `testing` | test-auditor, validation-gates | Test coverage gaps, lint errors, type check failures |
| `architecture` | code-hygiene (modularization focus), validation-gates | Structural violations, god files, dependency direction, lint/type errors |
| `dead-code` | code-hygiene (dead-code focus only) | Unused imports, unreferenced functions, commented-out code |
| `documentation` | architecture-sync, code-hygiene (documentation focus) | Doc-code drift, architecture.json gaps, missing docstrings |

### Orchestration Process

1. **Create a team** using TeamCreate named `code-quality-sweep`
2. **Create tasks** using TaskCreate — one per agent to spawn, with clear descriptions of what each agent should audit
3. **Spawn agents in parallel** using the Task tool:
   - Each agent runs as a teammate in the `code-quality-sweep` team
   - All agents run **read-only** — they report findings but do NOT modify code
   - For `code-hygiene`, pass the appropriate focus mode based on the sweep type:
     - `general` → `full` (all 5 audit areas)
     - `security` → `hardcoded` + `error-handling`
     - `architecture` → `modularization`
     - `dead-code` → `dead-code`
     - `documentation` → `documentation`
   - For `validation-gates`, instruct it to run lint (`flake8`) and type checks (`tsc --noEmit`) only — no code fixes
   - For `test-auditor`, instruct it to scan and report coverage gaps only — no test writing
   - For `multiuser-security`, run a full audit
   - For `architecture-sync`, instruct it to check for doc drift only — no doc updates
4. **Wait for all agents** to complete and send their reports
5. **Consolidate findings** into a single unified report

### Consolidated Report Format

After all agents report back, produce a single combined report:

```
## Code Quality Sweep — [focus area]

### Findings by Severity

| # | Severity | Category | File | Line | Issue | Source Agent | Recommendation |
|---|----------|----------|------|------|-------|-------------|----------------|

Categories: Security / Testing / Dead Code / Modularization / Hardcoded Values / Documentation / Error Handling / Lint / Type Safety

### Summary Statistics

- Agents run: [list]
- Files scanned: ~N
- Total findings: N (N critical, N high, N medium, N low)

### Quick Wins (can fix immediately)
- [ ] Item 1
- [ ] Item 2

### Refactoring Items (need planning)
- [ ] Item 1
- [ ] Item 2

### Deferred (low priority)
- [ ] Item 1
```

### Deduplication Rules

When multiple agents flag the same file:line location:
- Keep the finding with the highest severity
- Merge recommendations from all agents that flagged it
- Note which agents independently identified the issue (higher confidence)

### Important Rules

- **All agents are read-only** — no code modifications, no file writes, no git operations
- **No false positives** — each agent must verify findings by reading actual code
- **Respect project conventions** — check CLAUDE.md for project-specific rules before flagging
- **Shutdown the team** when done — send shutdown_request to all teammates after consolidating the report
- **Clean up** — use TeamDelete after all teammates have shut down
