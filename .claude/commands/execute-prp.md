Execute the PRP (Product Requirements Plan): $ARGUMENTS

## Process

### 1. Load & Understand
- Read the PRP file at `docs/PRPs/$ARGUMENTS`
- Understand all context, requirements, and constraints
- If the PRP references other files, read those too
- Identify any gaps that need additional research

### 2. Plan
- Think carefully before writing code
- Break the work into ordered steps
- Identify dependencies between steps (what must come first?)
- Note which validation gates apply at each step

### 3. Execute
- Implement step by step, following the PRP's blueprint
- Follow CLAUDE.md rules throughout:
  - Layered architecture (models → services → routers)
  - Lint as you go
  - `git diff` before staging
  - No silent code drops
- If the PRP specifies database changes:
  - Create idempotent migration in `backend/migrations/`
  - Update `setup.py` raw SQL for fresh installs
  - Update `database.py` models if needed

### 4. Validate
- Run each validation gate from the PRP
- Fix any failures — iterate until all pass
- Verify no regressions by checking related functionality

### 5. Complete
- Re-read the PRP to confirm everything was implemented
- Summarize what was done
- List any deviations from the PRP and why
- Note files changed for the changelog

### 6. Prepare for Ship
- Stage changes to the dev branch
- Draft a CHANGELOG.md entry (user-facing language)
- Report completion — wait for user to review and `/shipit`

If validation fails, use the PRP's rollback plan. If truly blocked, report what's blocking and ask for guidance.
