Execute the full "Ship It" release process as defined in CLAUDE.md.

Follow every step of the "Ship It — Full Release Process" section in CLAUDE.md exactly:

1. Determine version bump (patch for fixes, minor for features) from the current tag
2. Pre-flight: review diffs, lint all changed files, ensure branch is clean
3. **Detect frontend deployment mode**: Run `./bot.sh status` to check current mode (DEV or PROD). This determines step 7 behavior.
4. Database & schema: if models changed, back up DB, stop services, run migrations, update setup.py and database.py
5. Update all version references (CHANGELOG.md, docs/architecture.json) in the same commit
   - **CHANGELOG entries are user-facing** — describe features, fixes, and changes in plain language
   - Do NOT include merge notes, branch names, or internal git operations in the changelog
   - Use Keep a Changelog format: Added / Changed / Fixed / Removed / Security sections
6. Commit, merge dev branch into main, then tag the merge commit on main
7. Delete dev branch locally and on remote
8. Push main with tags, deploy:
   - **Backend changes**: `./bot.sh restart --dev --back-end` (or `--prod`)
   - **Frontend in DEV mode** (Vite HMR): Do NOT run `npm run build`. HMR picks up changes automatically. Only restart frontend service if Vite config or dependencies changed (`./bot.sh restart --dev --front-end`).
   - **Frontend in PROD mode** (serving dist/): `./bot.sh restart --prod` (rebuilds dist/ automatically)
   - **Both changed**: `./bot.sh restart --dev --both` (or `--prod`)
9. Post-ship verification: confirm tag, no stale branches, services healthy

Do NOT skip any steps. The end state must be: main is tagged, all versions match, dev branch is gone, production is running the new code.
