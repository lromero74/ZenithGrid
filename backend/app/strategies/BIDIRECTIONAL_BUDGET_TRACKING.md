# Bidirectional DCA Budget Tracking

## Critical Concept: Asset Conversion Tracking

When a bidirectional bot operates, assets convert between USD and BTC. **These converted assets must remain reserved** so other bots can't use them.

## Example Scenario

### Initial State
- User deposits: $5,000 USD + 0.05 BTC
- Creates bidirectional bot with 40% budget, 50/50 split:
  - `reserved_usd_for_longs = $1,000` (for buying BTC)
  - `reserved_btc_for_shorts = 0.01 BTC` (for selling BTC)

### After Long Position Opens
- Bot buys $500 worth of BTC at $100,000/BTC → Gets 0.005 BTC
- **Problem**: That 0.005 BTC now sits in the account
- **Solution**: Other bots must see it as RESERVED because:
  - The bidirectional bot may add safety orders (buy more)
  - The bidirectional bot will sell it when TP hits
  - It's part of the bot's allocated capital

### After Short Position Opens
- Bot sells 0.005 BTC at $100,000/BTC → Gets $500 USD
- **Problem**: That $500 USD now sits in the account
- **Solution**: Other bots must see it as RESERVED because:
  - The bidirectional bot may add safety orders (sell more BTC)
  - The bidirectional bot needs it to buy back BTC later
  - It's part of the bot's allocated capital

## Implementation

### Bot Model Methods

#### `get_total_reserved_usd(current_btc_price)`
Returns total USD locked by this bot:
- Initial USD reserved for longs (`reserved_usd_for_longs`)
- **PLUS** USD value of BTC in long positions (bought BTC, will sell later)
- **PLUS** USD received from short positions (sold BTC, needs to buy back)

#### `get_total_reserved_btc(current_btc_price)`
Returns total BTC locked by this bot:
- Initial BTC reserved for shorts (`reserved_btc_for_shorts`)
- **PLUS** BTC acquired from long positions (bought BTC, will sell later)
- **PLUS** BTC equivalent of USD from shorts (got USD, needs to buy BTC back)

### Budget Calculator Service

`calculate_available_usd()`:
```python
available_usd = raw_usd_balance - sum(all_bidirectional_bots.get_total_reserved_usd())
```

`calculate_available_btc()`:
```python
available_btc = raw_btc_balance - sum(all_bidirectional_bots.get_total_reserved_btc())
```

## Why This Matters

**Without this tracking:**
- Bidirectional bot reserves $1,000 for longs
- Opens long position, buys 0.01 BTC
- Another bot sees: "Ooh, 0.01 BTC available!"
- Other bot tries to use that BTC
- **Result**: Bidirectional bot can't sell when TP hits (insufficient funds)

**With this tracking:**
- Bidirectional bot reserves $1,000 for longs
- Opens long position, buys 0.01 BTC
- `get_total_reserved_btc()` returns 0.01 BTC (from long position)
- Other bots see: "0.01 BTC is reserved"
- **Result**: Capital stays allocated correctly ✓

## Usage in Bot Creation

When creating a new bot, validate available capital:

```python
from app.services.budget_calculator import (
    calculate_available_usd,
    calculate_available_btc,
    validate_bidirectional_budget
)

# Get raw balances
balances = await exchange.get_account()
raw_usd = balances.get("USD", 0.0)
raw_btc = balances.get("BTC", 0.0)

# Calculate available (excluding bidirectional reservations)
current_btc_price = await exchange.get_btc_usd_price()
available_usd = await calculate_available_usd(db, raw_usd, current_btc_price)
available_btc = await calculate_available_btc(db, raw_btc, current_btc_price)

# For bidirectional bot creation
if bot.strategy_config.get("enable_bidirectional"):
    required_usd = bot_budget * (long_budget_pct / 100.0)
    required_btc = bot_budget_btc * (short_budget_pct / 100.0)

    valid, error = await validate_bidirectional_budget(
        db, bot, required_usd, required_btc, current_btc_price
    )

    if not valid:
        raise HTTPException(status_code=400, detail=error)
```

## Key Principles

1. **Bidirectional bots reserve capital in BOTH currencies simultaneously**, and that capital converts between currencies as positions are opened/closed. Track the converted value to prevent other bots from "stealing" it.

2. **Live and paper trading have separate reservations**. Paper trading bots reserve "virtual" capital that should NOT affect live trading bots' available balance calculations, and vice versa.

## Live vs Paper Trading Separation

**Critical Implementation Detail**: Reservations are filtered by `account_id`:

```python
# When calculating available USD for a live trading bot
available_usd = await calculate_available_usd(
    db, raw_usd, current_btc_price,
    account_id=live_account.id,  # Only count live trading bot reservations
    exclude_bot_id=current_bot.id
)

# When calculating available USD for a paper trading bot
available_usd = await calculate_available_usd(
    db, raw_usd, current_btc_price,
    account_id=paper_account.id,  # Only count paper trading bot reservations
    exclude_bot_id=current_bot.id
)
```

**Why this matters**:
- Paper trading bot reserves $10,000 (virtual money)
- Live trading bot should still see full $50,000 real balance available
- Without account filtering, live bot would see only $40,000 available (incorrect!)

**Implementation**: Budget calculator functions (`calculate_available_usd`, `calculate_available_btc`) filter bidirectional bots by account_id before summing reservations.
