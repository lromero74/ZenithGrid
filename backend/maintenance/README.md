# Maintenance Scripts

Production maintenance scripts for the trading bot backend.

## Scripts

### cleanup_database.py

Prevents database bloat by removing old log entries and vacuuming the database.

**What it cleans:**
- `indicator_logs`: Entries older than 1 day (these accumulate rapidly)
- `ai_bot_logs`: Entries older than 7 days (AI decision history)

**Usage:**
```bash
# On EC2 (testbot) - uses defaults
python3 cleanup_database.py

# Custom paths (e.g., local development)
python3 cleanup_database.py --db-path ./trading.db --log-path ./cleanup.log
```

**Scheduled Execution:**

On EC2, this runs daily at 3 AM UTC via systemd timer:

```
/etc/systemd/system/db-cleanup.service  - The service unit
/etc/systemd/system/db-cleanup.timer    - The timer (triggers at 03:00 UTC)
```

**Management commands:**
```bash
# Check timer status
sudo systemctl status db-cleanup.timer

# View cleanup logs
cat ~/cleanup-database.log

# Manually trigger cleanup
sudo systemctl start db-cleanup.service

# Disable automatic cleanup
sudo systemctl disable db-cleanup.timer
```

## Why This Matters

Without regular cleanup, the database can grow significantly:
- Our database grew from ~50MB to 513MB over a few weeks
- `indicator_logs` alone accumulated 7,934+ rows per day
- `ai_bot_logs` accumulated 31,254+ rows per week

After cleanup and VACUUM: 513MB -> 276MB (46% reduction)
