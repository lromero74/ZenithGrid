Analyze and fix the GitHub issue: $ARGUMENTS

## Process

1. **Get issue details**
   ```bash
   gh issue view $ARGUMENTS
   ```

2. **Understand the problem** — Read the issue description, comments, and any linked PRs

3. **Search the codebase** — Find relevant files using the issue's keywords, error messages, or referenced components

4. **Create a fix branch**
   ```bash
   git checkout -b fix/issue-$ARGUMENTS
   ```

5. **Implement the fix**
   - Read all relevant files before making changes
   - Follow CLAUDE.md rules (layered architecture, lint, no regressions)
   - `git diff` before staging to verify no unintended changes

6. **Validate**
   - Lint: `flake8 --max-line-length=120` (Python), `npx tsc --noEmit` (TypeScript)
   - Verify no circular imports if you moved code
   - Check that the fix actually addresses the issue

7. **Commit with a descriptive message**
   - Reference the issue: `Fix #$ARGUMENTS: <description>`

8. **Report** — Summarize what was wrong, what you changed, and how to verify the fix

Wait for user confirmation before pushing or creating a PR.
