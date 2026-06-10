# scratch/

Throwaway space for one-off scripts, experiments, and debugging helpers that
should **not** be committed.

Everything in this directory is gitignored except this README, so you can drop
files here freely and they'll never show up in `git status` or get committed.

## Where scripts go

| Location | Tracked? | Use for |
|----------|----------|---------|
| `scripts/` (repo root) | **tracked** | Permanent, shared tooling worth committing (e.g. `analyze_database.py`, `audit_csp.sh`). |
| `backend/scripts/` | **ignored** | Throwaway / local **backend** helpers (DB pokes, one-off fixes). A few are explicitly tracked via `!` exceptions in `.gitignore`. |
| `scratch/` (here) | **ignored** | Anything else throwaway — frontend experiments, repo-root one-liners, sweep/migration scripts you'll delete after. |

Rule of thumb: if you're tempted to make a `foo.py.bak` or leave a `patch_x.py`
in the tree, put it in `scratch/` (or `backend/scripts/`) instead. Git history is
your real backup — don't commit `.bak`/`.fixed` copies.
