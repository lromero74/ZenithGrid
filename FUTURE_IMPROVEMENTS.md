# Future Improvements

## Setup Script Modularization

**Issue**: setup.py is currently 33,036 tokens (very large, hard to maintain)

**Proposed Solution**: Break setup.py into modular components:
- `setup.py` - Main entry point, CLI arg parsing
- `setup/database.py` - Database initialization and schema creation
- `setup/services.py` - Service installation (systemd/launchd)
- `setup/dependencies.py` - Python/npm dependency installation
- `setup/config.py` - .env configuration and user creation
- `setup/utils.py` - Helper functions (colors, prompts, etc.)

**Benefits**:
- Easier to maintain and update
- Fits in AI context windows
- More testable
- Clearer separation of concerns

**Priority**: Low (setup.py works fine, but would be nice for future maintenance)

---

Created: 2026-01-26
