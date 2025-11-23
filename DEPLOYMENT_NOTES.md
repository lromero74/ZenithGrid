# Deployment Notes for v1.5.0

## Database Migration Required

**Migration File:** `backend/migrations/add_limit_close_tracking.py`

### Fields Added:

**positions table:**
- `closing_via_limit` (BOOLEAN) - Whether position is closing via limit order
- `limit_close_order_id` (TEXT) - Coinbase order ID for limit close order

**pending_orders table:**
- `fills` (TEXT/JSON) - Array of fill records
- `remaining_base_amount` (REAL) - Unfilled base amount for partial fills

### Steps to Deploy:

#### On testbot (EC2):
```bash
ssh testbot
cd ~/GetRidOf3CommasBecauseTheyGoDownTooOften
git pull origin main
cd backend
python migrations/add_limit_close_tracking.py
sudo systemctl restart trading-bot-backend
```

#### On local development:
```bash
cd /Users/louis/GetRidOf3CommasBecauseTheyGoDownTooOften/backend
python migrations/add_limit_close_tracking.py
# Restart backend if running
```

### New Features Enabled:
- Limit order position closing with interactive slider
- Edit/cancel pending limit orders
- Partial fill tracking
- Automatic order monitoring (background service)
- Fill history and status badges

### Important Notes:
- Migration is idempotent (safe to run multiple times)
- No data loss - only adds new columns
- Existing positions unaffected
- Background monitor service created but not yet integrated into bot runner

### Next Steps:
1. Run migration on both testbot and local
2. Test limit order placement
3. Integrate `limit_order_monitor.py` into bot runner
4. Monitor logs for order status updates
