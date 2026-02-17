Execute the full "Ship It" release process as defined in CLAUDE.md.

Follow every step of the "Ship It — Full Release Process" section in CLAUDE.md exactly:

1. Determine version bump (patch for fixes, minor for features) from the current tag
2. Pre-flight: review diffs, lint all changed files, ensure branch is clean
3. **Detect frontend deployment mode**: Run `systemctl status trading-bot-frontend` to check if the frontend is running `npm run dev` (DEV mode with HMR) or serving from `dist/` (PROD mode). This determines step 7 behavior.
4. Database & schema: if models changed, back up DB, stop services, run migrations, update setup.py and database.py
5. Update all version references (CHANGELOG.md, docs/architecture.json) in the same commit
6. Commit, tag, merge dev branch into main
7. Delete dev branch locally and on remote
8. Push main with tags, deploy:
   - **Backend**: Always restart (`sudo systemctl restart trading-bot-backend`) if Python files changed
   - **Frontend in DEV mode** (Vite HMR): Do NOT run `npm run build`. HMR picks up changes automatically. Only restart frontend service if Vite config or dependencies changed.
   - **Frontend in PROD mode** (serving dist/): Run `cd frontend && npm run build` to rebuild, then restart frontend service if needed.
9. Post-ship verification: confirm tag, no stale branches, services healthy

Do NOT skip any steps. The end state must be: main is tagged, all versions match, dev branch is gone, production is running the new code.
