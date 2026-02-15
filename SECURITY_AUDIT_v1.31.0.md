# Security Audit Plan — Post v1.31.0

**Date:** 2026-02-15
**Target Version:** v1.31.1 (patch — fixes only, no new features)

---

## Findings & Fixes

### CRITICAL

| # | Finding | File | Status |
|---|---------|------|--------|
| 1 | console.log leaks wallet_private_key | `BotFormModal.tsx:232` | FIXED |

### HIGH

| # | Finding | File | Status |
|---|---------|------|--------|
| 2 | .env world-readable (0644) | `backend/.env` | FIXED (chmod 600) |
| 3 | trading.db world-readable (0644) | `backend/trading.db` | FIXED (chmod 600) |
| 4 | 4 backup DBs world-readable (0644) | `backend/trading.db.bak*` | FIXED (chmod 600) |
| 5 | WebSocket URL with JWT logged to console | `NotificationContext.tsx:147` | FIXED |
| 6 | No HTTPS/TLS | systemd + network | OUT OF SCOPE (needs reverse proxy) |
| 7 | Backend on 0.0.0.0 | systemd service | OUT OF SCOPE (needs reverse proxy first) |

### MEDIUM

| # | Finding | File | Status |
|---|---------|------|--------|
| 8 | ~20 remaining `str(e)` in error responses | Multiple routers | FIXED (all sanitized) |
| 9 | Wrong env var in helpers.ts | `helpers.ts:72` | FIXED (authFetch) |
| 10 | Frontend runs Vite dev server in production | systemd service | KNOWN LIMITATION |
| 11 | No CSP or X-Frame-Options headers | `main.py` | FIXED (SecurityHeadersMiddleware) |
| 12 | CORS origins include localhost | `config.py` | KNOWN LIMITATION (origins from .env) |
| 13 | `get_current_user_optional` still exists | `auth_dependencies.py`, `auth_router.py` | FIXED (removed from both) |

### LOW

| # | Finding | File | Status |
|---|---------|------|--------|
| 14 | Unbounded query `limit` parameter | Multiple routers | FIXED (Query bounds added) |
| 15 | Race condition in bot name uniqueness | `bot_crud_router.py` | FIXED (migration added) |
| 16 | JWT tokens in localStorage | `AuthContext.tsx` | ACCEPTED RISK (standard SPA pattern) |
| 17 | Debug console.log statements | Multiple frontend files | FIXED (sensitive ones sanitized) |

---

## Known Limitations (Accepted / Out of Scope)

- **HTTPS/TLS**: Requires nginx/Caddy reverse proxy — separate infrastructure task
- **Bind to 127.0.0.1**: Dependent on reverse proxy being set up first
- **Production frontend build**: Requires build pipeline changes (currently Vite dev server)
- **CORS localhost origins**: Default in config, actual origins set via .env in production
- **JWT in localStorage**: Standard SPA pattern, acceptable tradeoff vs cookie-based auth
