# STEP 4 Progress: coinbase_unified_client.py Refactoring

## Status: IN PROGRESS (1/4 modules complete)

### Original File: 874 lines

### Target Structure:
```
app/coinbase_api/
├── __init__.py (created)
├── auth.py (220 lines) ✅ COMPLETE
├── account_balance_api.py (~260 lines) TODO
├── market_data_api.py (~130 lines) TODO
└── order_api.py (~250 lines) TODO

app/coinbase_unified_client.py (~150 lines wrapper) TODO
```

### Completed:
- ✅ **auth.py** (220 lines)
  - `load_cdp_credentials_from_file()` - Load CDP creds from JSON
  - `generate_jwt()` - Generate JWT tokens for CDP auth
  - `generate_hmac_signature()` - Generate HMAC signatures
  - `authenticated_request()` - Make authenticated HTTP requests with retry logic

### Remaining Work:

#### account_balance_api.py (~260 lines)
**Lines to extract:** 247-399, 762-863

**Methods:**
- `get_accounts()` - Get all accounts (cached)
- `get_account()` - Get specific account
- `get_portfolios()` - Get portfolio list
- `get_portfolio_breakdown()` - Get portfolio breakdown
- `get_btc_balance()` - Get BTC balance
- `get_eth_balance()` - Get ETH balance
- `get_usd_balance()` - Get USD balance
- `invalidate_balance_cache()` - Clear balance cache
- `calculate_aggregate_btc_value()` - Total BTC value (available + positions)
- `calculate_aggregate_usd_value()` - Total USD value

**Note:** `calculate_aggregate_btc_value()` has hardcoded DB path `/home/ec2-user/ZenithGrid/backend/trading.db`. This is preserved as-is (refactoring = no functionality changes).

#### market_data_api.py (~130 lines)
**Lines to extract:** 402-515, 867-874

**Methods:**
- `list_products()` - Get all trading pairs
- `get_product()` - Get product details
- `get_ticker()` - Get current ticker
- `get_current_price()` - Get current price (cached 10s)
- `get_btc_usd_price()` - Get BTC/USD price
- `get_product_stats()` - Get 24h stats
- `get_candles()` - Get historical candles
- `test_connection()` - Test API connectivity

#### order_api.py (~250 lines)
**Lines to extract:** 516-761

**Methods:**
- `create_market_order()` - Create market order
- `create_limit_order()` - Create limit order
- `get_order()` - Get order details
- `cancel_order()` - Cancel order
- `list_orders()` - List orders with filters
- `buy_eth_with_btc()` - Helper: Buy ETH with BTC
- `sell_eth_for_btc()` - Helper: Sell ETH for BTC
- `buy_with_usd()` - Helper: Buy with USD
- `sell_for_usd()` - Helper: Sell for USD

#### Wrapper (coinbase_unified_client.py ~150 lines)
Create new client that:
1. Initializes auth credentials in `__init__`
2. Delegates all API calls to imported modules
3. Maintains same public API (100% backward compatible)
4. Move original to `coinbase_unified_client_OLD_BACKUP.py`

### Next Steps:
1. Extract account_balance_api.py
2. Extract market_data_api.py
3. Extract order_api.py
4. Create refactored wrapper
5. Verify syntax on all files
6. Commit with detailed message

### Estimated Time: 2-3 hours to complete STEP 4
