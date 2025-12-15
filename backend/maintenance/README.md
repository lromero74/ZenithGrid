# Maintenance Scripts

Production maintenance scripts for the trading bot backend.

## Scripts

### cleanup_database.py

Prevents database bloat by removing old data and vacuuming the database.

**Retention Policies:**
- `news_articles`: 14 days (articles are shared up to 14 days old)
- `video_articles`: 14 days
- `signals`: 7 days
- `scanner_logs`: 7 days
- `ai_bot_logs`: 7 days
- `indicator_logs`: 7 days

**Usage:**
```bash
# On EC2 (testbot) - uses defaults
python3 cleanup_database.py

# Custom paths (e.g., local development)
python3 cleanup_database.py --db-path ./trading.db --log-path ./cleanup.log
```

**Scheduled Execution:**

On EC2, this runs daily at 3 AM UTC via systemd timer. Install via `setup.py` or manually:

```
/etc/systemd/system/zenith-db-cleanup.service  - The service unit
/etc/systemd/system/zenith-db-cleanup.timer    - The timer (triggers at 03:00 UTC)
```

**Management commands:**
```bash
# Check timer status
sudo systemctl status zenith-db-cleanup.timer
sudo systemctl list-timers | grep zenith

# View cleanup logs
cat ~/cleanup-database.log

# Manually trigger cleanup
sudo systemctl start zenith-db-cleanup.service

# Disable automatic cleanup
sudo systemctl disable zenith-db-cleanup.timer
```

## Why This Matters

Without regular cleanup, the database can grow significantly:
- `news_articles` with embedded base64 images can grow to 180MB+
- `signals` table can accumulate 500K+ rows
- `scanner_logs` can accumulate 170K+ rows

Example cleanup result: 292MB -> 224MB (24% reduction, 68MB saved)
