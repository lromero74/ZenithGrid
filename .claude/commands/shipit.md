Execute the full "Ship It" release process as defined in CLAUDE.md.

Follow every step of the "Ship It — Full Release Process" section in CLAUDE.md exactly:

1. Determine version bump (patch for fixes, minor for features) from the current tag
2. Pre-flight: review diffs, lint all changed files, ensure branch is clean
3. **Detect frontend deployment mode**: Run `./bot.sh status` to check current mode (DEV or PROD). This determines step 8 behavior.
4. Database & schema: if models changed, back up DB, stop services, run migrations, update setup.py and database.py
5. **Documentation** — do ALL of these BEFORE creating the version commit or tag:
   - Run the `architecture-sync` agent to update `docs/architecture/backend.json` and `docs/architecture/frontend.json` with any new/changed routers, models, services, hooks, or components
   - If the feature changes user-facing behavior significantly, update `README.md` (installation steps, feature list, screenshots)
   - Update `CHANGELOG.md` with the new version section (user-facing plain language, Keep a Changelog format: Added / Changed / Fixed / Removed / Security)
   - Update `docs/architecture/index.json` version field
   - Wait for architecture-sync to complete before tagging — all docs must be in the same commit as the version bump
6. Commit all changes (code + all documentation updates) in a single commit, then tag on main
7. Delete dev branch locally and on remote (if applicable)
8. Push main with tags, deploy:
   - **Backend changes**: `./bot.sh restart --dev --back-end` (or `--prod`)
   - **Frontend in DEV mode** (Vite HMR): Do NOT run `npm run build`. HMR picks up changes automatically. Only restart frontend service if Vite config or dependencies changed (`./bot.sh restart --dev --front-end`).
   - **Frontend-only in PROD mode**: `./bot.sh build` — rebuilds dist/ without restarting the backend. The backend reads git tags live and serves static files from disk, so new bundles and version are live immediately. Users get a "new version" toast prompting them to reload. No restart needed.
   - **Backend changes in PROD mode**: `./bot.sh restart --prod` (rebuilds dist/ + restarts backend)
   - **Both changed in PROD mode**: `./bot.sh restart --prod`
9. Post-ship verification: confirm tag, no stale branches, services healthy

Do NOT skip any steps. The end state must be: main is tagged, all docs updated, all versions match, dev branch is gone, production is running the new code.
