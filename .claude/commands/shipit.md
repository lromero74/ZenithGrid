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
   - Run `python3 scripts/check_version_consistency.py --expected vX.Y.Z` with the release version you are about to tag
   - Wait for architecture-sync to complete before tagging — all docs must be in the same commit as the version bump
6. Commit all changes (code + all documentation updates) in a single commit, then tag on main.
   - **Create the tag ANNOTATED** (`git tag -a vX.Y.Z -m "vX.Y.Z: …"`), not lightweight. This repo historically used lightweight tags, and `git push --follow-tags` silently skips lightweight tags — so the tag never reaches origin/prod and `/api/health` keeps reporting the OLD version.
7. Delete dev branch locally and on remote (if applicable)
8. Push main, then push the tag EXPLICITLY — `git push origin main` followed by `git push origin vX.Y.Z` (do NOT rely on `--follow-tags` alone; it does not push lightweight tags, and a missed tag is the #1 cause of prod reporting a stale version). Confirm the tag is on origin (`git ls-remote --tags origin | grep vX.Y.Z`) before deploying. Then deploy:

   **PRODUCTION = AWS Lightsail (`zenithgrid-ls`), native systemd — NOT `bot.sh`.** (`bot.sh` is the local dev / fedora warm-standby path only.) Real prod deploy:
   - `ssh zenithgrid-ls 'cd ~/ZenithGrid && git pull origin main'`
   - **`ssh zenithgrid-ls 'cd ~/ZenithGrid && git fetch origin --tags'`** — REQUIRED, do not skip. `git pull origin main` fetches the branch but NOT tags, and the backend reads its version live from git tags. Without this the new commit deploys but `/api/health` keeps reporting the *old* version. Confirm with `git describe --tags` → must show the exact `vX.Y.Z` (no `-N-gHASH` suffix).
   - **Backend changes**: `ssh zenithgrid-ls 'sudo systemctl restart zenithgrid'`
   - **Frontend-only changes**: `ssh zenithgrid-ls 'cd ~/ZenithGrid/frontend && npm run build'` — no restart (backend serves `dist/` from disk; version still comes from the fetched tag, so the tag fetch above is still required).
   - Verify: `ssh zenithgrid-ls 'curl -s http://127.0.0.1:8100/api/health'` → `{"status":"ok","version":"vX.Y.Z"}` matching the tag.

   **LOCAL DEV / fedora warm-standby only** (`bot.sh`):
   - **Backend changes**: `./bot.sh restart --dev --back-end`
   - **Frontend in DEV mode** (Vite HMR): Do NOT run `npm run build`. HMR picks up changes automatically. Only restart frontend service if Vite config or dependencies changed (`./bot.sh restart --dev --front-end`).
   - **Frontend-only in PROD mode**: `./bot.sh build` — rebuilds dist/ without restarting the backend.
   - **Backend changes in PROD mode**: `./bot.sh restart --prod`
9. Post-ship verification: run `python3 scripts/check_version_consistency.py`, confirm tag, no stale branches, services healthy

Do NOT skip any steps. The end state must be: main is tagged, all docs updated, all versions match, dev branch is gone, production is running the new code.
