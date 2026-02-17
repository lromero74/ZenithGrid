Switch the EC2 environment to DEV mode (Vite dev server with HMR).

In dev mode, the Vite dev server on port 5173 serves the frontend with hot module replacement, and proxies `/api` and `/ws` requests to the backend on port 8100. Nginx points to port 5173.

**Execute these steps in order:**

### 1. Enable and start the frontend service
```
sudo systemctl enable trading-bot-frontend
sudo systemctl start trading-bot-frontend
```

### 2. Update nginx to proxy to Vite dev server (port 5173)
Edit `/etc/nginx/conf.d/tradebot.conf`:
- Both `location /` and `location /ws` blocks should `proxy_pass` to `http://127.0.0.1:5173`

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
- Confirm nginx config points to 5173
- Report the final state to the user

**Dev mode summary:**
- Nginx (443) → Vite dev server (5173) → proxies API to backend (8100)
- Frontend service: **enabled + running**
- HMR active: React/TS/CSS changes apply instantly without restart
