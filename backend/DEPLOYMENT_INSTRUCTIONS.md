# HouseKeeping_1.0 - Deployment Instructions for Production Testing

**Branch:** HouseKeeping_1.0
**Status:** Pushed to GitHub - Ready for Production Testing
**Date:** 2025-01-23

---

## 📋 Pre-Deployment Checklist

✅ All major files refactored to <500 lines
✅ 43 commits with detailed history
✅ All syntax checks passed
✅ 100% backward compatible API
✅ Branch pushed to GitHub
✅ Original files preserved as _OLD_BACKUP.py

---

## 🚀 Deployment to Production (testbot)

### Step 1: SSH to Production Server

```bash
ssh testbot
cd ~/ZenithGrid
```

### Step 2: Fetch Latest Changes

```bash
git fetch origin
```

### Step 3: Checkout HouseKeeping_1.0 Branch

```bash
# Switch to the refactored branch
git checkout HouseKeeping_1.0

# Verify you're on the correct branch
git branch --show-current
# Should output: HouseKeeping_1.0

# Pull latest changes (if any)
git pull origin HouseKeeping_1.0
```

### Step 4: Verify File Structure

```bash
# Check that new modules exist
ls -la app/ai_autonomous/
ls -la app/trading_engine/
ls -la app/coinbase_api/
ls -la app/bot_routers/
ls -la app/position_routers/

# Verify main files are small
wc -l app/main.py
# Should show ~133 lines

wc -l app/trading_engine_v2.py
# Should show ~180 lines

wc -l app/coinbase_unified_client.py
# Should show ~260 lines
```

### Step 5: Install Dependencies (if needed)

```bash
cd backend
./venv/bin/pip install -r requirements.txt
```

### Step 6: Restart Backend Service

```bash
sudo systemctl restart trading-bot-backend
```

### Step 7: Monitor Logs

```bash
# Watch backend logs in real-time
sudo journalctl -u trading-bot-backend -f

# Look for any import errors or startup issues
# Expected: Normal startup messages, no errors
```

### Step 8: Verify API Endpoints

```bash
# Test that API is responding
curl http://localhost:8000/api/health

# Test a few key endpoints
curl http://localhost:8000/api/bots/strategies
curl http://localhost:8000/api/positions?limit=1
```

---

## 🧪 Testing Plan

### Critical Functionality to Test:

1. **Bot Management**
   - Create a test bot (DON'T start it)
   - View bot list
   - Edit bot configuration
   - Delete bot

2. **Position Viewing**
   - View open positions
   - View closed positions
   - View position details
   - View P&L charts

3. **Bot Operations** (if safe to test)
   - Start/stop bot
   - View bot stats
   - Check AI logs

4. **Market Data**
   - View current prices
   - Check candle data

5. **Order History**
   - View successful orders
   - View failed orders

### What to Watch For:

- ✅ **No import errors** on startup
- ✅ **All API endpoints respond** correctly
- ✅ **Bot creation/editing** works
- ✅ **Position data** displays correctly
- ✅ **No database errors** in logs
- ✅ **Existing bots continue to work** (if active)

---

## 🔄 Rollback Plan (If Issues Found)

### Quick Rollback to Main Branch:

```bash
# Switch back to main branch
git checkout main

# Restart service
sudo systemctl restart trading-bot-backend

# Monitor logs
sudo journalctl -u trading-bot-backend -f
```

### Report Issues:

If you encounter any issues:
1. Note the specific error message
2. Check logs: `sudo journalctl -u trading-bot-backend --since "5 minutes ago"`
3. Rollback to main if critical
4. Report findings

---

## 📊 What Changed (Architecture Overview)

### Before → After:

1. **ai_autonomous.py** (1,745 lines)
   - Now split into `app/ai_autonomous/` with 8 modules
   - Main file: `app/ai_autonomous/__init__.py` (451 lines)

2. **main.py** (1,658 lines)
   - Now 133 lines with routers in `app/routers/`
   - Positions, accounts, market data, settings, system endpoints

3. **trading_engine_v2.py** (1,099 lines)
   - Now split into `app/trading_engine/` with 6 modules
   - Main file: `app/trading_engine_v2.py` (180 lines wrapper)

4. **coinbase_unified_client.py** (874 lines)
   - Now split into `app/coinbase_api/` with 5 modules
   - Main file: `app/coinbase_unified_client.py` (260 lines wrapper)

5. **bots.py router** (760 lines)
   - Now split into `app/bot_routers/` with 5 modules
   - Main file: `app/routers/bots.py` (19 lines wrapper)

6. **positions_router.py** (804 lines)
   - Now split into `app/position_routers/` with 6 modules
   - Main file: `app/routers/positions_router.py` (27 lines wrapper)

### Key Points:

- ✅ **100% Backward Compatible** - Same API routes, same functionality
- ✅ **Wrapper Pattern** - All refactored files use wrapper classes/routers
- ✅ **No Breaking Changes** - Existing code imports still work
- ✅ **Clean Modules** - Each module has single responsibility

---

## 📝 Files to Monitor

### If Something Breaks:

Check these log locations:
- Backend logs: `sudo journalctl -u trading-bot-backend -f`
- Python errors: Look for `ModuleNotFoundError`, `ImportError`
- Database errors: Look for `sqlalchemy` errors

### Common Issues (if any):

1. **Import Errors**
   - Solution: Check Python path, restart service

2. **Database Connection**
   - Solution: Verify database.py is working

3. **Missing Dependencies**
   - Solution: Run `pip install -r requirements.txt`

---

## ✅ Success Criteria

Production testing is successful if:

1. ✅ Backend starts without errors
2. ✅ All API endpoints respond
3. ✅ Bot creation/editing works
4. ✅ Positions display correctly
5. ✅ No new errors in logs
6. ✅ Existing functionality preserved

---

## 🎯 Next Steps After Testing

### If Testing Succeeds:

1. **Run for a test period** (hours/days as you see fit)
2. **Monitor logs** for any unexpected issues
3. **Verify all bot operations** work as expected
4. **When confident**, merge to main:
   ```bash
   git checkout main
   git merge HouseKeeping_1.0
   git push origin main
   ```

### If Testing Fails:

1. **Document the issue**
2. **Rollback to main** (see above)
3. **Report findings** for fixes

---

## 🔗 Related Documentation

- `REFACTORING_COMPLETE.md` - Full refactoring details
- `HOUSEKEEPING_PROGRESS.md` - Progress tracking
- `SESSION_SUMMARY.md` - Session overview

---

**Current Status:** Branch pushed to GitHub, ready for deployment to testbot
**Branch:** HouseKeeping_1.0
**Last Updated:** 2025-01-23
