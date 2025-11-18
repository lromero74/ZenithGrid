# Conditional Strategy User Guide

## What is the Conditional DCA Strategy?

The Conditional DCA Strategy is a powerful 3Commas-style trading bot that lets you create custom buy and sell conditions by mixing and matching technical indicators with various comparison operators.

**Think of it like building trading rules with LEGO blocks:**
- Pick any indicator (RSI, MACD, Bollinger Bands, etc.)
- Choose how to compare it (>, <, crossing above, etc.)
- Compare against a value OR another indicator
- Combine multiple conditions with AND/OR logic
- Nest groups for complex strategies

## Quick Example: Classic RSI Oversold Strategy

**Goal:** Buy when RSI is oversold, sell when overbought

**Buy Condition:**
```
RSI(14) < 30
```

**Sell Condition:**
```
RSI(14) > 70
```

That's it! The bot will:
1. Buy when RSI drops below 30 (oversold)
2. Add safety orders if price drops further (traditional DCA)
3. Sell when RSI goes above 70 (overbought) OR take profit hits

## How to Create a Conditional Bot

### Step 1: Create New Bot
1. Go to the **Bots** page
2. Click **Create Bot**
3. Fill in basic details (name, trading pair)
4. Select **"Conditional DCA (Custom Conditions)"** as strategy

### Step 2: Configure DCA Settings

Set your Dollar Cost Averaging parameters:

**Base Order:**
- Type: % of BTC Balance or Fixed BTC Amount
- Size: How much to invest initially (e.g., 10% or 0.001 BTC)

**Safety Orders:**
- Max Safety Orders: How many times to average down (e.g., 5)
- Price Deviation %: How much price must drop to trigger safety order (e.g., 2%)
- Safety Order Size: Size of each safety order (e.g., 50% of base)

**Take Profit / Stop Loss:**
- Take Profit %: Target profit to sell (e.g., 3%)
- Stop Loss %: Maximum loss before exit (e.g., -10%)
- Trailing: Follow price up to maximize profits

**Advanced (Optional):**
- Volume Scale: Make each safety order larger (1.0 = same size, 2.0 = double)
- Step Scale: Increase spacing between safety orders (1.0 = even, 2.0 = exponential)

### Step 3: Build Buy Conditions

This is where the magic happens! Click **"+ Add Condition"** under "Buy Conditions"

#### Example 1: Simple RSI
```
RSI(14) less_than 30
```

How to build:
1. Select indicator: **RSI**
2. Enter period: **14**
3. Select operator: **<** (less_than)
4. Select value type: **Value**
5. Enter value: **30**

#### Example 2: MACD Crossover
```
MACD Histogram(12,26,9) crossing_above 0
```

How to build:
1. Select indicator: **MACD Histogram**
2. Enter fast: **12**, slow: **26**, signal: **9**
3. Select operator: **Crossing Above**
4. Select value type: **Value**
5. Enter value: **0**

#### Example 3: Price vs Moving Average
```
Price crossing_below SMA(50)
```

How to build:
1. Select indicator: **Price**
2. Select operator: **Crossing Below**
3. Select value type: **Indicator** ← Important!
4. Select compare indicator: **SMA**
5. Enter period: **50**

### Step 4: Combine Conditions (AND/OR)

**AND Logic:** All conditions must be true
```
RSI(14) < 30
AND
MACD Histogram(12,26,9) crossing_above 0
```

**OR Logic:** Any condition can be true
```
RSI(14) < 30
OR
Stochastic %K(14,3) < 20
```

Toggle the **AND/OR** button at the top of the group!

### Step 5: Nested Groups (Advanced)

Create complex strategies with nested conditions:

```
(RSI < 30 AND MACD crosses above 0)
OR
(Price < Bollinger Lower AND Volume > 1000000)
```

How to build:
1. Click **"+ Add Group"**
2. Inside the group, add your conditions
3. Set the group's logic (AND/OR)
4. Add another group for the second part
5. Set the parent group logic to OR

### Step 6: Build Sell Conditions

Same process as buy conditions, but for selling.

**Note:** Sell conditions are OPTIONAL. The bot will ALWAYS sell when:
- Take Profit % is reached
- Stop Loss % is hit (if enabled)

Use sell conditions for additional exit signals like:
```
RSI(14) > 70
```

### Step 7: Review & Create

- Check the **Configuration Preview** at the bottom
- Make sure all values look correct
- Click **Create Bot**
- Start your bot when ready!

## Common Strategies

### 1. RSI + MACD Combo
**Buy:** RSI oversold + MACD bullish crossover
```
Logic: AND
- RSI(14) < 30
- MACD Histogram crossing_above 0
```

**Sell:** RSI overbought
```
- RSI(14) > 70
```

### 2. Bollinger Bounce
**Buy:** Price touches lower band
```
- Price crossing_below Bollinger Lower(20,2)
```

**Sell:** Price touches upper band
```
- Price crossing_above Bollinger Upper(20,2)
```

### 3. Multi-Indicator Confirmation
**Buy:** Multiple oversold signals
```
Logic: AND
- RSI(14) < 30
- Stochastic %K(14,3) < 20
- Price < Bollinger Lower(20,2)
```

**Sell:** Any overbought signal
```
Logic: OR
- RSI(14) > 70
- Stochastic %K(14,3) > 80
- Price > Bollinger Upper(20,2)
```

### 4. Trend Following
**Buy:** Price breaks above moving average
```
Logic: AND
- Price crossing_above SMA(50)
- MACD Histogram > 0
```

**Sell:** Price breaks below moving average
```
- Price crossing_below SMA(50)
```

## Available Indicators

### Oscillators
- **RSI** (Relative Strength Index)
  - Params: period (default 14)
  - Range: 0-100
  - Oversold: < 30, Overbought: > 70

- **Stochastic**
  - **%K** and **%D** lines
  - Params: k_period, d_period (default 14, 3)
  - Range: 0-100
  - Oversold: < 20, Overbought: > 80

- **MACD** (Moving Average Convergence Divergence)
  - **MACD Line**, **Signal Line**, **Histogram**
  - Params: fast_period, slow_period, signal_period (default 12, 26, 9)
  - Crossover: Histogram crosses 0

### Moving Averages
- **SMA** (Simple Moving Average)
  - Params: period (default 20)
  - Use for support/resistance

- **EMA** (Exponential Moving Average)
  - Params: period (default 20)
  - More responsive than SMA

### Volatility
- **Bollinger Bands**
  - **Upper**, **Middle**, **Lower** bands
  - Params: period, std_dev (default 20, 2)
  - Price at bands = potential reversal

### Price/Volume
- **Price** - Current market price
- **Volume** - Trading volume

## Comparison Operators

### Static Comparisons
- **>** (greater_than) - Value is above threshold
- **<** (less_than) - Value is below threshold
- **≥** (greater_equal) - Value is at or above
- **≤** (less_equal) - Value is at or below
- **=** (equal) - Value equals exactly

### Crossing Detection
- **Crossing Above** - Value crosses from below to above
  - Example: MACD crosses above signal = bullish
- **Crossing Below** - Value crosses from above to below
  - Example: Price crosses below SMA = bearish

**Important:** Crossing operators require 2 candles to detect the cross!

## Tips & Best Practices

### 1. Start Simple
- Begin with 1-2 conditions
- Test with small amounts
- Add complexity once you're comfortable

### 2. Use Confirmation
- Don't rely on a single indicator
- Combine trend + momentum indicators
- Example: RSI (momentum) + MACD (trend)

### 3. Avoid Contradictions
- Don't create impossible conditions
- Bad: `RSI > 70 AND RSI < 30`
- Good: `RSI < 30` (buy) and `RSI > 70` (sell)

### 4. Test Different Timeframes
- Different indicators work better on different timeframes
- Short-term: 5m, 15m (more signals, more noise)
- Long-term: 1h, 4h, 1d (fewer signals, more reliable)

### 5. Consider Market Conditions
- Oscillators work well in ranging markets
- Trend indicators work well in trending markets
- Adjust strategy based on market state

### 6. Backtest (Coming Soon)
- Test your conditions on historical data
- See how they would have performed
- Refine based on results

### 7. Monitor & Adjust
- Watch your bot's performance
- Adjust parameters if needed
- Markets change - strategies should too

## Troubleshooting

### "No signals detected"
- Conditions may be too strict
- Try relaxing thresholds (e.g., RSI < 35 instead of < 30)
- Check if indicators need more candles to calculate

### "Too many signals"
- Conditions may be too loose
- Add more confirmation (use AND)
- Increase thresholds

### "Bot not buying/selling"
- Check if conditions are actually being met
- View bot logs for detailed reasons
- Ensure sufficient balance for trades

### "Crossing not working"
- Crossing requires 2+ candles
- First candle after start won't trigger crossings
- Check if values are actually crossing (not just touching)

## Examples in JSON Format

For reference, here's what your conditions look like in the backend:

### Simple RSI
```json
{
  "buy_conditions": {
    "logic": "and",
    "conditions": [
      {
        "indicator": "rsi",
        "operator": "less_than",
        "value_type": "static",
        "static_value": 30,
        "indicator_params": {"period": 14}
      }
    ]
  }
}
```

### Complex Multi-Condition
```json
{
  "buy_conditions": {
    "logic": "or",
    "sub_groups": [
      {
        "logic": "and",
        "conditions": [
          {
            "indicator": "rsi",
            "operator": "less_than",
            "value_type": "static",
            "static_value": 30,
            "indicator_params": {"period": 14}
          },
          {
            "indicator": "macd_histogram",
            "operator": "crossing_above",
            "value_type": "static",
            "static_value": 0,
            "indicator_params": {
              "fast_period": 12,
              "slow_period": 26,
              "signal_period": 9
            }
          }
        ]
      },
      {
        "logic": "and",
        "conditions": [
          {
            "indicator": "price",
            "operator": "crossing_below",
            "value_type": "indicator",
            "compare_indicator": "bollinger_lower",
            "compare_indicator_params": {
              "period": 20,
              "std_dev": 2
            }
          }
        ]
      }
    ]
  }
}
```

## Next Steps

1. **Create your first conditional bot** with a simple RSI strategy
2. **Monitor its performance** and learn how conditions behave
3. **Experiment with different indicators** to find what works for you
4. **Combine multiple conditions** for more robust strategies
5. **Share your strategies** with the community!

Happy trading! 🚀
