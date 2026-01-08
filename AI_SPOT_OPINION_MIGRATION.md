# AI Spot Opinion Migration Guide

## Overview

The AI indicator system has been completely redesigned for simplicity and better LLM integration.

**Old System** (Removed):
- `AI_BUY` / `AI_SELL` indicators
- Confluence-based scoring (0-100)
- Multiple timeframe analysis
- Complex configuration

**New System**:
- `ai_opinion` indicator (buy/sell/hold)
- `ai_confidence` indicator (0-100)
- `ai_reasoning` indicator (text explanation)
- LLM-powered with user-selectable models
- Time-gated per candle timeframe
- Pre-filter to reduce LLM costs

---

## What Changed

### Backend Changes

**Files Added:**
- `backend/app/indicators/ai_spot_opinion.py` - New unified AI indicator

**Files Removed:**
- `backend/app/indicators/ai_indicator.py` - Old confluence-based indicator
- `backend/app/indicators/confluence_calculator.py` - Old multi-timeframe analyzer

**Files Modified:**
- `backend/app/indicators/__init__.py` - Updated imports
- `backend/app/strategies/indicator_based.py` - New AI parameters and evaluation logic

### New Bot Parameters

When creating/editing indicator-based bots, you'll see new AI settings:

```python
{
  "ai_model": "claude" | "gpt" | "gemini",  # Which LLM to use
  "ai_timeframe": "5m" | "15m" | "30m" | "1h" | "4h",  # How often to check
  "ai_min_confidence": 60,  # Minimum confidence to act (0-100)
  "enable_buy_prefilter": true  # Use technical pre-filter to save LLM costs
}
```

**Old parameters removed:**
- `ai_risk_preset`
- `ai_min_confluence_score`
- `ai_entry_timeframe`
- `ai_trend_timeframe`

### New Indicators for Conditions

**Old Way:**
```json
{
  "indicator": "AI_BUY",
  "operator": "==",
  "value": 1
}
```

**New Way:**
```json
{
  "indicator": "ai_opinion",
  "operator": "==",
  "value": "buy",
  "AND": {
    "indicator": "ai_confidence",
    "operator": ">=",
    "value": 70
  }
}
```

**Available indicators:**
- `ai_opinion` - The AI's decision: "buy", "sell", or "hold"
- `ai_confidence` - Confidence percentage (0-100)
- `ai_reasoning` - Text explanation from the AI (for logging/debugging)

---

## Migration Process

### Step 1: Check for Affected Bots

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 scripts/migrate_ai_indicators.py
```

This shows which bots need migration (dry run, no changes).

### Step 2: Backup Database

The migration script automatically backs up the database, but you can also do it manually:

```bash
cp backend/trading.db backend/trading.db.backup_$(date +%Y%m%d_%H%M%S)
```

### Step 3: Run Migration

```bash
./venv/bin/python3 scripts/migrate_ai_indicators.py --apply
```

Or skip confirmation:

```bash
./venv/bin/python3 scripts/migrate_ai_indicators.py --apply --yes
```

The script will:
1. Find all bots using AI_BUY or AI_SELL
2. Convert conditions to new format
3. Update bot configuration parameters
4. Backup database before applying changes

### Step 4: Restart Backend

```bash
sudo systemctl restart trading-bot-backend
```

---

## How It Works

### Pre-Filter Logic (Buys Only)

To save LLM costs, the system pre-filters buy opportunities before asking the AI:

**Pre-filter checks:**
1. RSI < 70 (not overbought)
2. Volume > 1.2x average (decent activity)
3. 24h price change > -10% (not crashing)

If pre-filter fails, returns `"hold"` without calling LLM.

**To disable pre-filter:**
Set `enable_buy_prefilter: false` in bot config (will increase LLM costs).

### Time-Gating

The AI is called **once per candle close** based on `ai_timeframe`:

- `5m` timeframe = Check every 5 minutes (max 288 LLM calls/day per pair)
- `15m` timeframe = Check every 15 minutes (max 96 calls/day)
- `1h` timeframe = Check every hour (max 24 calls/day)
- `4h` timeframe = Check every 4 hours (max 6 calls/day)

This prevents redundant LLM calls on the same candle.

### LLM Integration

The AI receives:
- Current technical metrics (RSI, MACD, MA, Bollinger, volume, price action)
- Historical context (from candles)
- Trading pair name

And returns:
- Signal: "buy", "sell", or "hold"
- Confidence: 0-100%
- Reasoning: 1-2 sentence explanation

**Supported models:**
- `claude` - Claude Sonnet 4.5 (recommended, most accurate)
- `gpt` - GPT-4o (good alternative)
- `gemini` - Gemini 2.0 Flash (fastest, cheapest)

### Sell Logic

For sell signals:
- Only evaluated for positions you already hold
- No pre-filter (always asks AI)
- Self-limiting (can't sell what you don't own)

---

## Example Bot Configurations

### Conservative AI Bot (15min, High Confidence)

```json
{
  "strategy_type": "indicator_based",
  "ai_model": "claude",
  "ai_timeframe": "15m",
  "ai_min_confidence": 75,
  "enable_buy_prefilter": true,
  "base_order_conditions": {
    "indicator": "ai_opinion",
    "operator": "==",
    "value": "buy",
    "AND": {
      "indicator": "ai_confidence",
      "operator": ">=",
      "value": 75
    }
  },
  "take_profit_conditions": {
    "indicator": "ai_opinion",
    "operator": "==",
    "value": "sell",
    "AND": {
      "indicator": "ai_confidence",
      "operator": ">=",
      "value": 70
    }
  }
}
```

### Aggressive AI Bot (5min, Lower Confidence)

```json
{
  "ai_model": "gemini",
  "ai_timeframe": "5m",
  "ai_min_confidence": 60,
  "enable_buy_prefilter": true,
  "base_order_conditions": {
    "indicator": "ai_opinion",
    "operator": "==",
    "value": "buy",
    "AND": {
      "indicator": "ai_confidence",
      "operator": ">=",
      "value": 60
    }
  }
}
```

---

## Cost Considerations

### LLM API Costs (Approximate)

**Per 1000 calls:**
- Claude Sonnet 4.5: ~$0.30 (input) + ~$1.50 (output) = **~$1.80**
- GPT-4o: ~$0.25 (input) + ~$1.00 (output) = **~$1.25**
- Gemini 2.0 Flash: ~$0.10 (input) + ~$0.30 (output) = **~$0.40**

**Daily cost examples (1 bot, 1 pair):**
- 5m timeframe (288 calls/day): Claude ~$0.52, GPT ~$0.36, Gemini ~$0.12
- 15m timeframe (96 calls/day): Claude ~$0.17, GPT ~$0.12, Gemini ~$0.04
- 1h timeframe (24 calls/day): Claude ~$0.04, GPT ~$0.03, Gemini ~$0.01

**Cost-saving tips:**
1. Use longer timeframes (15m-1h optimal)
2. Enable `enable_buy_prefilter` to reduce unnecessary LLM calls
3. Use Gemini for testing, Claude for production
4. Limit number of pairs per bot

---

## Testing Checklist

After deployment, verify:

- [ ] Backend starts without errors: `sudo systemctl status trading-bot-backend`
- [ ] Check logs for import errors: `sudo journalctl -u trading-bot-backend -f`
- [ ] Create a new indicator-based bot via frontend
- [ ] Verify new AI parameters show in bot config
- [ ] Verify ai_opinion, ai_confidence appear in condition dropdowns
- [ ] Test creating a condition with ai_opinion == "buy"
- [ ] Start bot and watch for AI decisions in logs
- [ ] Check indicator logs show AI reasoning

**Expected log output:**
```
AI Opinion for ETH-BTC: BUY (confidence: 75%, reason: Bullish MACD crossover with strong volume...)
```

---

## Backward Compatibility

The new system includes **temporary backward compatibility** for AI_BUY/AI_SELL:

- Old conditions using AI_BUY/AI_SELL will still work
- They are mapped internally from ai_opinion results
- **Migration is still recommended** for cleaner config

**Compatibility mapping:**
- `ai_opinion == "buy"` → `AI_BUY = 1`, `AI_SELL = 0`
- `ai_opinion == "sell"` → `AI_BUY = 0`, `AI_SELL = 1`
- `ai_opinion == "hold"` → `AI_BUY = 0`, `AI_SELL = 0`

---

## Troubleshooting

### "No module named 'anthropic'" Error

Install missing LLM SDKs:

```bash
cd backend
./venv/bin/pip install anthropic openai google-generativeai
sudo systemctl restart trading-bot-backend
```

### "ANTHROPIC_API_KEY not configured" Error

Set API keys in `.env` file:

```bash
cd backend
echo "ANTHROPIC_API_KEY=your_key_here" >> .env
echo "OPENAI_API_KEY=your_key_here" >> .env
echo "GEMINI_API_KEY=your_key_here" >> .env
sudo systemctl restart trading-bot-backend
```

### AI Always Returns "hold"

Check:
1. Pre-filter may be too strict - try `enable_buy_prefilter: false`
2. Timeframe gating - wait for next candle close
3. Check logs for LLM errors
4. Verify API keys are valid

### High LLM Costs

Reduce costs by:
1. Increasing `ai_timeframe` (15m or 1h recommended)
2. Enabling `enable_buy_prefilter: true`
3. Switching to `gemini` model
4. Reducing number of trading pairs

---

## Support

If you encounter issues:

1. Check logs: `sudo journalctl -u trading-bot-backend -n 100`
2. Run migration script in dry-run mode to see what would change
3. Verify database backup exists before applying changes
4. Test with a single bot first before migrating all bots

---

**Migration Script:** `backend/scripts/migrate_ai_indicators.py`
**Documentation:** This file (`AI_SPOT_OPINION_MIGRATION.md`)
