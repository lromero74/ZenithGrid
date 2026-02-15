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

## Pending Security TODOs (Evaluate Before Multi-User Launch)

These items were deferred from v1.31.x. Before opening the app to internet users
beyond the single admin, evaluate which (if any) actually make sense to implement.
For a single-user setup accessed only by the owner, some of these may be unnecessary overhead.

- **HTTPS/TLS**: Requires nginx/Caddy reverse proxy. Essential if exposing to the public
  internet, but may be overkill if only accessed via SSH tunnel or VPN.
- **Bind to 127.0.0.1**: Only matters if a reverse proxy is set up — keeps the backend
  off the public interface. If no reverse proxy, backend needs to stay on 0.0.0.0.
- **Production frontend build**: Currently running Vite dev server. A production build
  (served by nginx or similar) would be faster and more secure, but the dev server works
  fine for a single user.
- **CORS localhost origins**: Defaults include localhost for development. In production
  the actual origins come from .env. Only matters if the app is served on a real domain.
- **JWT in localStorage**: Standard SPA pattern. Moving to httpOnly cookies would add
  XSS protection but adds complexity. Low priority for single-user setup.
