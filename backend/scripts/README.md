# Backend Helper Scripts

This folder contains one-off debugging, testing, and database management scripts that are NOT part of the main application.

**Purpose**: Keep helper scripts separate from actual application code to avoid confusion.

**What goes here**:
- Database debugging scripts (check_*.py, verify_*.py)
- One-time data fixes (fix_*.py, update_*.py)
- Manual test scripts (test_*.py, force_*.py)
- Configuration utilities (set_*.py)

**What does NOT go here**:
- Application code (belongs in `app/`)
- Reusable utilities (belongs in `app/utils/`)
- Database migrations (would go in future `migrations/` folder)
- Production scripts (deployment, monitoring, etc.)

**Note**: This entire folder is git-ignored, so scripts here won't be committed to version control. This is intentional - these are temporary development tools.
