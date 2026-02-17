Switch the EC2 environment to DEV mode (Vite dev server with HMR).

In dev mode, the Vite dev server on port 5173 serves the frontend with hot module replacement, and proxies `/api` requests to the backend on port 8100. Nginx routes `/ws` directly to the backend (WebSocket proxying through Vite is fragile).

**Execute this command:**

```bash
./bot.sh restart --dev --both --force
```

The bot.sh script handles:
1. Updating nginx to proxy to Vite dev server (port 5173) for `/` and backend (port 8100) for `/ws`
2. Enabling and starting the frontend service
3. Reloading nginx
4. Restarting the backend

**Verify with:**
```bash
./bot.sh status
```

**Dev mode summary:**
- Nginx (443) → Vite dev server (5173) for pages/assets, proxies `/api` to backend (8100)
- Nginx (443) → Backend (8100) directly for `/ws` (WebSocket)
- Frontend service: **enabled + running**
- HMR active: React/TS/CSS changes apply instantly without restart
