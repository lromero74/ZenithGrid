Switch the EC2 environment to DEV mode (Vite dev server with HMR).

In dev mode, the Vite dev server on port 5173 serves the frontend with hot module replacement, and proxies `/api` requests to the backend on port 8100. Nginx routes `/ws` directly to the backend (WebSocket proxying through Vite is fragile).

**Execute these steps in order:**

### 1. Enable and start the frontend service
```
sudo systemctl enable trading-bot-frontend
sudo systemctl start trading-bot-frontend
```

### 2. Update nginx to proxy to Vite dev server (port 5173), except WebSocket
Edit `/etc/nginx/conf.d/tradebot.conf`:
- `location /` block: `proxy_pass http://127.0.0.1:5173`
- `location /ws` block: `proxy_pass http://127.0.0.1:8100` (direct to backend — do NOT route through Vite)

### 3. Reload nginx
```
sudo nginx -t && sudo systemctl reload nginx
```

### 4. Restart backend (serves API on 8100, Vite proxies to it)
```
sudo systemctl restart trading-bot-backend
```

### 5. Verify
- `sudo systemctl status trading-bot-frontend` — should be active
- `sudo systemctl status trading-bot-backend` — should be active
- Confirm nginx config: `/` → 5173, `/ws` → 8100
- Report the final state to the user

**Dev mode summary:**
- Nginx (443) → Vite dev server (5173) for pages/assets, proxies `/api` to backend (8100)
- Nginx (443) → Backend (8100) directly for `/ws` (WebSocket)
- Frontend service: **enabled + running**
- HMR active: React/TS/CSS changes apply instantly without restart
