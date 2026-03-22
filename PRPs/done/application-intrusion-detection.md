# PRP: Application-Level Intrusion Detection

**Feature**: Detect and ban users attempting injection attacks through POST/PUT request bodies
**Created**: 2026-03-14
**One-Pass Confidence Score**: 8/10

> Focused middleware feature. Similar to the existing PublicEndpointRateLimiter ASGI middleware pattern. Scans request bodies for attack patterns, logs attempts, and auto-bans repeat offenders.

---

## Context & Goal

### Problem
fail2ban only scans nginx access log URL paths. Attacks embedded in POST/PUT request bodies (chat messages, form fields, API payloads) are invisible. Someone can repeatedly attempt SQL injection, XSS, or shell commands through the application without consequence.

### Solution
ASGI middleware that:
1. Intercepts POST/PUT/PATCH request bodies
2. Scans content for injection patterns (SQL, XSS, shell, path traversal)
3. Logs detected attempts with IP, user ID, endpoint, and matched pattern
4. Tracks attempts per IP in memory
5. After N attempts (threshold), writes IP to a file that fail2ban monitors → auto-ban

### Why Not Block Inline?
The middleware should **log and track**, not block the request. Blocking would break legitimate requests that happen to contain pattern-like text (e.g., a user discussing SQL syntax in chat). The ban happens only after repeated attempts from the same IP.

---

## Architecture

```
Request arrives → ASGI middleware intercepts body
  ↓
Body scanned against INJECTION_PATTERNS regex list
  ↓
Match found? → Log to /var/log/zenithgrid/intrusion.log
             → Increment IP counter in memory
             → If counter >= THRESHOLD → write to intrusion.log with [BAN] prefix
  ↓
fail2ban jail monitors intrusion.log → bans IP on [BAN] line
  ↓
Request continues normally (not blocked by middleware)
```

### Key Design Decisions
- **Log-only, don't block** — avoids false positives disrupting legitimate users
- **Threshold before ban** — 5 attempts within 1 hour triggers ban
- **Separate log file** — `/var/log/zenithgrid/intrusion.log` for fail2ban to monitor
- **Skip static/GET requests** — only scan bodies of mutation requests
- **Skip large bodies** — cap scan at first 4KB to avoid performance impact
- **Whitelist admin IPs** — don't flag Louis's IP

---

## Existing Patterns

### PublicEndpointRateLimiter (`backend/app/middleware/public_rate_limit.py`)
Already follows the ASGI middleware pattern:
```python
class PublicEndpointRateLimiter:
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # ... check rate limits ...
        await self.app(scope, receive, send)
```

Registered in `main.py`:
```python
app.add_middleware(PublicEndpointRateLimiter)
```

### fail2ban Custom Filter Pattern
Already using custom filter at `/etc/fail2ban/filter.d/nginx-exploit.conf`.

---

## Implementation Tasks

### 1. Create intrusion detection middleware (`backend/app/middleware/intrusion_detect.py`)

```python
INJECTION_PATTERNS = [
    # SQL injection
    r"(?i)(union\s+select|select\s+.*\s+from|insert\s+into|drop\s+table|delete\s+from|update\s+.*\s+set)",
    r"(?i)(or\s+1\s*=\s*1|'\s*or\s*'|--\s*$|;\s*drop\s)",
    # XSS
    r"(?i)(<script|javascript:|onerror\s*=|onload\s*=|<img\s+.*\s+onerror)",
    r"(?i)(document\.cookie|document\.write|window\.location|eval\s*\()",
    # Shell injection
    r"(?i)(/bin/sh|/bin/bash|/etc/passwd|/etc/shadow|cmd\.exe)",
    r"(?i)(;\s*ls\s|;\s*cat\s|;\s*rm\s|;\s*wget\s|;\s*curl\s.*\|)",
    # Path traversal
    r"\.\./\.\./",
    # PHP/code injection
    r"(?i)(base64_decode|eval\s*\(|system\s*\(|exec\s*\(|phpinfo\s*\()",
]
```

**Middleware flow:**
1. Check `scope["type"] == "http"` and method is POST/PUT/PATCH
2. Read first 4KB of request body
3. Scan against patterns
4. If match: log to intrusion log, increment IP counter
5. If counter >= 5: log [BAN] line
6. Pass request through (don't block)

**Body reading in ASGI:**
Must buffer the body and replay it for the downstream app:
```python
body = b""
async def receive_wrapper():
    nonlocal body
    message = await receive()
    if message["type"] == "http.request":
        body = message.get("body", b"")
    return message
```

### 2. Create log directory and file

```bash
sudo mkdir -p /var/log/zenithgrid
sudo touch /var/log/zenithgrid/intrusion.log
sudo chown ec2-user:ec2-user /var/log/zenithgrid/intrusion.log
```

### 3. Create fail2ban filter (`/etc/fail2ban/filter.d/zenithgrid-intrusion.conf`)

```ini
[Definition]
failregex = ^\[BAN\] <HOST> .*
ignoreregex =
```

### 4. Add fail2ban jail

```ini
[zenithgrid-intrusion]
enabled = true
port = http,https
filter = zenithgrid-intrusion
logpath = /var/log/zenithgrid/intrusion.log
backend = auto
maxretry = 1
findtime = 3600
bantime = 17520h
```

### 5. Register middleware in main.py

```python
from app.middleware.intrusion_detect import IntrusionDetector
app.add_middleware(IntrusionDetector)
```

### 6. Periodic cleanup of in-memory counters

Add to `cleanup_jobs.py` sweep (existing 5-minute cycle):
```python
from app.middleware.intrusion_detect import IntrusionDetector
IntrusionDetector.prune_stale()
```

---

## Log Format

```
2026-03-14 10:30:45 [INTRUSION] 1.2.3.4 user_id=5 POST /api/chat/channels/3/messages pattern=sql_injection content="'; DROP TABLE users;--"
2026-03-14 10:30:50 [INTRUSION] 1.2.3.4 user_id=5 PUT /api/users/display-name pattern=xss content="<script>alert(1)</script>"
2026-03-14 10:31:00 [BAN] 1.2.3.4 user_id=5 threshold=5 attempts in 3600s
```

The `[BAN]` line is what fail2ban keys on.

---

## Validation Gates

```bash
# Python lint
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m flake8 --max-line-length=120 \
  app/middleware/intrusion_detect.py

# Test
./venv/bin/python3 -m pytest tests/middleware/test_intrusion_detect.py -v
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| False positive on legitimate text (e.g., discussing SQL in chat) | Log-only, don't block. Ban requires 5 attempts in 1 hour. |
| Performance impact from body scanning | Only scan first 4KB. Skip GET/HEAD/OPTIONS. Skip WebSocket. |
| Body reading breaks downstream | Buffer and replay body via ASGI receive wrapper |
| Log file grows unbounded | Logrotate config or periodic truncation |
| Admin gets flagged | Whitelist known admin IPs in middleware |

---

## Quality Checklist

- [x] All necessary context included (ASGI middleware pattern, fail2ban filter pattern)
- [x] Validation gates are executable
- [x] References existing patterns (PublicEndpointRateLimiter, nginx-exploit filter)
- [x] Clear implementation path (6 tasks)
- [x] Error handling documented (false positives, performance, body buffering)
