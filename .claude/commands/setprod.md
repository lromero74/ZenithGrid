Switch the EC2 environment to PROD mode (frontend served from dist/ by backend).

In prod mode, the backend on port 8100 serves both the API and the built frontend from `frontend/dist/`. The Vite dev server is not used. Nginx points directly to port 8100.

**Execute these steps in order:**

### 1. Build the frontend
```
cd /home/ec2-user/ZenithGrid/frontend && npm run build
```
Verify that `frontend/dist/` exists and contains `index.html` and `assets/`.

### 2. Stop and disable the frontend service
```
sudo systemctl stop trading-bot-frontend
sudo systemctl disable trading-bot-frontend
```

### 3. Update nginx to proxy to backend (port 8100)
Edit `/etc/nginx/conf.d/tradebot.conf`:
- Both `location /` and `location /ws` blocks should `proxy_pass` to `http://127.0.0.1:8100`

### 4. Reload nginx
```
sudo nginx -t && sudo systemctl reload nginx
```

### 5. Restart backend (now serves both API + frontend dist/)
```
sudo systemctl restart trading-bot-backend
```

### 6. Verify
- `sudo systemctl status trading-bot-frontend` — should be inactive/disabled
- `sudo systemctl status trading-bot-backend` — should be active
- Confirm nginx config points to 8100
- Curl test: `curl -s -o /dev/null -w "%{http_code}" https://tradebot.romerotechsolutions.com/` should return 200
- Report the final state to the user

**Prod mode summary:**
- Nginx (443) → Backend (8100) → serves API + frontend/dist/
- Frontend service: **disabled + stopped**
- No HMR: frontend changes require `npm run build` and backend restart
