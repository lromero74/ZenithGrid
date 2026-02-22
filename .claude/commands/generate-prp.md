Generate a Product Requirements Plan (PRP) for: $ARGUMENTS

A PRP gives Claude all the context needed for one-pass implementation success.

## Research Phase

### 1. Codebase Analysis
- Search for similar features/patterns already in the codebase
- Identify files that will need changes
- Note existing conventions to follow (naming, structure, patterns)
- Check how related features were implemented (study the precedent)

### 2. Architecture Review
- Read `docs/architecture.json` for relevant models, routers, services
- Read `docs/DOMAIN_KNOWLEDGE.md` if the feature touches trading logic
- Identify which layers will be affected (models? services? routers? frontend?)

### 3. External Research (if needed)
- Search for library documentation, API references
- Look for implementation examples and best practices
- Note any gotchas, version-specific quirks, or common pitfalls

### 4. User Clarification (if needed)
- Ask about ambiguous requirements before writing the PRP
- Confirm the scope — what's in, what's out

## PRP Generation

Write the PRP with these sections:

### Context & Goal
- What problem does this solve?
- Who benefits? (user-facing? internal?)
- How does 3Commas handle this? (if applicable)

### Implementation Blueprint
- Pseudocode or step-by-step approach
- Reference existing files for patterns to follow
- List all files that will be created or modified
- Database changes (new models, migrations, setup.py updates)

### Validation Gates
```bash
# Python lint
backend/venv/bin/python3 -m flake8 --max-line-length=120 <files>

# TypeScript check (if frontend)
cd frontend && npx tsc --noEmit

# Import validation (if new modules)
backend/venv/bin/python3 -c "from app.<module> import <thing>"
```

### Commercialization Check
- [ ] Works for multiple users?
- [ ] Credentials stored securely?
- [ ] Would users pay for this?

### Rollback Plan
- What to revert if something goes wrong
- Database backup command if schema changes

## Output

Save as: `docs/PRPs/{feature-name}.md`

## Quality Score

Rate your confidence (1-10) that this PRP enables one-pass implementation:
- 8-10: All context provided, clear path, validated against codebase
- 5-7: Some gaps, may need mid-implementation research
- 1-4: Too many unknowns, needs more research before execution
