Execute the full "Ship It" release process as defined in CLAUDE.md.

Follow every step of the "Ship It — Full Release Process" section in CLAUDE.md exactly:

1. Determine version bump (patch for fixes, minor for features) from the current tag
2. Pre-flight: review diffs, lint all changed files, ensure branch is clean
3. Database & schema: if models changed, back up DB, stop services, run migrations, update setup.py and database.py
4. Update all version references (CHANGELOG.md, docs/architecture.json) in the same commit
5. Commit, tag, merge dev branch into main
6. Delete dev branch locally and on remote
7. Push main with tags, restart EC2 services
8. Post-ship verification: confirm tag, no stale branches, services healthy

Do NOT skip any steps. The end state must be: main is tagged, all versions match, dev branch is gone, production is running the new code.
