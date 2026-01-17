# Account Isolation: Multi-CEX Budget Tracking Example

## Scenario: User with Multiple Exchanges

User "Alice" has accounts on multiple exchanges:

### Account Configuration

```
┌─────────────────────────────────────────────────────────────────┐
│ Account 1: Coinbase (Live Trading)                              │
│ - Type: CEX                                                      │
│ - Exchange: coinbase                                             │
│ - Balance: $50,000 USD + 0.5 BTC                                │
│ - API Keys: Configured                                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Account 2: Kraken (Live Trading)                                │
│ - Type: CEX                                                      │
│ - Exchange: kraken                                               │
│ - Balance: $25,000 USD + 0.25 BTC                               │
│ - API Keys: Configured                                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Account 3: Paper Trading                                         │
│ - Type: CEX                                                      │
│ - Exchange: paper                                                │
│ - Is Paper Trading: YES                                          │
│ - Balance: $100,000 USD + 1.0 BTC (VIRTUAL)                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Bots Created

### Bot A: Coinbase Bidirectional DCA
- **Account**: Account 1 (Coinbase)
- **Strategy**: Bidirectional DCA
- **Budget**: 40% of Coinbase balance
- **Split**: 50% long / 50% short
- **Reservations**:
  - USD: $50,000 × 0.40 × 0.50 = **$10,000 reserved for longs**
  - BTC: 0.5 × 0.40 × 0.50 = **0.1 BTC reserved for shorts**

### Bot B: Coinbase Traditional DCA
- **Account**: Account 1 (Coinbase)
- **Strategy**: Traditional DCA (long only)
- **Budget**: 20% of Coinbase balance
- **Reservations**:
  - USD: $50,000 × 0.20 = **$10,000 reserved**
  - BTC: 0 (traditional DCA only buys)

### Bot C: Kraken Bidirectional DCA
- **Account**: Account 2 (Kraken)
- **Strategy**: Bidirectional DCA
- **Budget**: 40% of Kraken balance
- **Split**: 60% long / 40% short
- **Reservations**:
  - USD: $25,000 × 0.40 × 0.60 = **$6,000 reserved for longs**
  - BTC: 0.25 × 0.40 × 0.40 = **0.04 BTC reserved for shorts**

### Bot D: Paper Trading Practice
- **Account**: Account 3 (Paper)
- **Strategy**: Bidirectional DCA
- **Budget**: 50% of paper balance
- **Split**: 50% long / 50% short
- **Reservations**:
  - USD: $100,000 × 0.50 × 0.50 = **$25,000 reserved for longs (VIRTUAL)**
  - BTC: 1.0 × 0.50 × 0.50 = **0.25 BTC reserved for shorts (VIRTUAL)**

---

## Available Capital Calculation

### For New Bot on Coinbase (Account 1)

```python
# Raw balance on Coinbase
raw_usd = 50000.0
raw_btc = 0.5

# Calculate reserved by OTHER bots on Coinbase
# Filters: account_id = 1 (Coinbase only)
# Bot A (Coinbase bidirectional): reserves $10,000 USD + 0.1 BTC
# Bot B (Coinbase traditional): reserves $10,000 USD + 0 BTC
# Bot C (Kraken): IGNORED (different account)
# Bot D (Paper): IGNORED (different account)

reserved_usd = 10000 + 10000 = 20000.0  # From Bot A + Bot B
reserved_btc = 0.1 + 0 = 0.1  # From Bot A + Bot B

# Available for new Coinbase bot
available_usd = 50000 - 20000 = $30,000 ✓
available_btc = 0.5 - 0.1 = 0.4 BTC ✓
```

### For New Bot on Kraken (Account 2)

```python
# Raw balance on Kraken
raw_usd = 25000.0
raw_btc = 0.25

# Calculate reserved by OTHER bots on Kraken
# Filters: account_id = 2 (Kraken only)
# Bot A (Coinbase): IGNORED (different account)
# Bot B (Coinbase): IGNORED (different account)
# Bot C (Kraken bidirectional): reserves $6,000 USD + 0.04 BTC
# Bot D (Paper): IGNORED (different account)

reserved_usd = 6000.0  # From Bot C only
reserved_btc = 0.04  # From Bot C only

# Available for new Kraken bot
available_usd = 25000 - 6000 = $19,000 ✓
available_btc = 0.25 - 0.04 = 0.21 BTC ✓
```

### For New Bot on Paper Trading (Account 3)

```python
# Raw balance on Paper account
raw_usd = 100000.0  # VIRTUAL
raw_btc = 1.0  # VIRTUAL

# Calculate reserved by OTHER bots on Paper
# Filters: account_id = 3 (Paper only)
# Bot A (Coinbase): IGNORED (different account)
# Bot B (Coinbase): IGNORED (different account)
# Bot C (Kraken): IGNORED (different account)
# Bot D (Paper bidirectional): reserves $25,000 USD + 0.25 BTC

reserved_usd = 25000.0  # From Bot D only
reserved_btc = 0.25  # From Bot D only

# Available for new Paper bot
available_usd = 100000 - 25000 = $75,000 (virtual) ✓
available_btc = 1.0 - 0.25 = 0.75 BTC (virtual) ✓
```

---

## Key Insights

### ✅ Complete Isolation

1. **Coinbase bots** (Bot A + Bot B) reserve total:
   - $20,000 USD
   - 0.1 BTC
   - This ONLY affects other Coinbase bots

2. **Kraken bots** (Bot C) reserve total:
   - $6,000 USD
   - 0.04 BTC
   - This ONLY affects other Kraken bots

3. **Paper bots** (Bot D) reserve total:
   - $25,000 USD (virtual)
   - 0.25 BTC (virtual)
   - This ONLY affects other paper bots

### ✅ No Cross-Account Interference

- Bot D's $25,000 paper reservation does NOT reduce Coinbase availability
- Bot A's $10,000 Coinbase reservation does NOT reduce Kraken availability
- Each exchange operates independently with its own balance pool

### ✅ Prevents Over-Allocation

**Without account filtering**:
```python
# WRONG: Summing ALL bots across ALL accounts
total_reserved_usd = 10000 + 10000 + 6000 + 25000 = 51000
available_on_coinbase = 50000 - 51000 = -1000  # ❌ NEGATIVE! Incorrectly blocked
```

**With account filtering**:
```python
# CORRECT: Only summing Coinbase bots
total_reserved_usd = 10000 + 10000 = 20000
available_on_coinbase = 50000 - 20000 = 30000  # ✓ Accurate
```

---

## SQL Query Pattern

```sql
-- Calculate available USD for NEW bot on Coinbase (account_id = 1)
SELECT SUM(
  CASE
    WHEN strategy_config->>'enable_bidirectional' = 'true'
    THEN
      -- Use get_total_reserved_usd() which includes position conversions
      reserved_usd_for_longs + position_usd_value
    ELSE
      0
  END
) AS total_reserved
FROM bots
WHERE
  account_id = 1  -- CRITICAL: Only Coinbase bots
  AND is_active = TRUE
  AND id != :new_bot_id  -- Exclude the bot being created
```

---

## Implementation Guarantee

Every budget calculation function **requires** `account_id`:

```python
# ✓ CORRECT: Always pass account_id
available = await calculate_available_usd(
    db=db,
    raw_usd_balance=50000.0,
    current_btc_price=100000.0,
    account_id=1,  # Coinbase account
    exclude_bot_id=None
)

# ✗ WRONG: Missing account_id triggers warning
available = await calculate_available_usd(
    db=db,
    raw_usd_balance=50000.0,
    current_btc_price=100000.0,
    account_id=None,  # ⚠️ Logs warning, returns raw balance as fallback
    exclude_bot_id=None
)
```

**Safety**: If `account_id` is None, function logs warning and returns raw balance (conservative fallback).

---

## Visual Summary

```
┌──────────────────────────────────────────────────────────────────┐
│ COINBASE ACCOUNT ($50k USD + 0.5 BTC)                            │
├──────────────────────────────────────────────────────────────────┤
│ Bot A: Reserves $10k + 0.1 BTC │ Available:                      │
│ Bot B: Reserves $10k + 0 BTC   │ - $30k USD                      │
│                                │ - 0.4 BTC                        │
│ Other bots on Coinbase see:    │ (for new Coinbase bots)         │
│ ONLY Bot A + Bot B reservations│                                 │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ KRAKEN ACCOUNT ($25k USD + 0.25 BTC)                             │
├──────────────────────────────────────────────────────────────────┤
│ Bot C: Reserves $6k + 0.04 BTC │ Available:                      │
│                                │ - $19k USD                       │
│                                │ - 0.21 BTC                       │
│ Other bots on Kraken see:      │ (for new Kraken bots)           │
│ ONLY Bot C reservations        │                                 │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ PAPER ACCOUNT ($100k USD + 1.0 BTC) - VIRTUAL                   │
├──────────────────────────────────────────────────────────────────┤
│ Bot D: Reserves $25k + 0.25 BTC│ Available:                      │
│                                │ - $75k USD (virtual)             │
│                                │ - 0.75 BTC (virtual)             │
│ Other paper bots see:          │ (for new paper bots)            │
│ ONLY Bot D reservations        │                                 │
└──────────────────────────────────────────────────────────────────┘

NO CROSS-CONTAMINATION: Each account's reservations stay isolated!
```

---

**Bottom Line**: By filtering on `account_id`, we ensure that:
1. Each CEX has its own independent budget pool
2. Paper trading never affects live trading
3. Multi-exchange users can allocate capital independently per exchange
4. No risk of one exchange's bots seeing another exchange's balances
