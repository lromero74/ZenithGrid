Switch the EC2 environment to PROD mode (frontend served from dist/ by backend).

In prod mode, the backend on port 8100 serves both the API and the built frontend from `frontend/dist/`. The Vite dev server is not used. Nginx points everything (including `/ws`) to port 8100.

**Execute this command:**

```bash
./bot.sh restart --prod --force
```

The bot.sh script handles:
1. Building frontend (`npm run build` → `frontend/dist/`)
2. Stopping and disabling the frontend service
3. Updating nginx to proxy both `/` and `/ws` to backend (port 8100)
4. Reloading nginx
5. Restarting the backend

**Verify with:**
```bash
./bot.sh status
```

**Prod mode summary:**
- Nginx (443) → Backend (8100) → serves API + frontend/dist/ + WebSocket
- Frontend service: **disabled + stopped**
- No HMR: frontend changes require `npm run build` and backend restart
