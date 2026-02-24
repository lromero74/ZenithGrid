# Custom Bot (Indicator-Based) User Guide

## What is the Custom Bot Strategy?

The Custom Bot (Indicator-Based) strategy is a condition-based trading bot that lets you create custom entry, DCA, and exit conditions using technical indicators with comparison operators.

**Think of it like building trading rules with LEGO blocks:**
- Pick any indicator (RSI, MACD, Bollinger Bands, AI signals, etc.)
- Choose how to compare it (>, <, crossing above, increasing, etc.)
- Set a threshold value
- Choose a timeframe per condition (5m, 15m, 1h, 4h, 1d)
- Combine multiple conditions with AND/OR logic

## Quick Example: Classic RSI Oversold Strategy

**Base Order Condition (entry):**
```
RSI(14) < 30 on 15m timeframe
```

**Take Profit Condition (exit):**
```
RSI(14) > 70 on 15m timeframe
```

The bot will:
1. Buy when RSI drops below 30 (oversold)
2. Add safety orders if price drops further (DCA)
3. Sell when RSI goes above 70 (overbought) OR take profit % hits

## How to Create a Custom Bot

### Step 1: Create New Bot
1. Go to the **Bots** page
2. Click **Create Bot**
3. Fill in basic details (name, trading pairs)
4. Select **"Custom Bot (Indicator-Based)"** as strategy

### Step 2: Configure DCA Settings

**Base Order:**
- Type: % of balance or fixed amount
- Size: How much to invest initially (e.g., 10%)

**Safety Orders:**
- Max Safety Orders: How many times to average down (e.g., 5)
- Price Deviation %: How much price must drop to trigger (e.g., 2%)
- Volume Scale: Make each safety order larger (1.0 = same, 2.0 = double)
- Step Scale: Increase spacing between orders (1.0 = even, 2.0 = exponential)

**Take Profit / Stop Loss:**
- Take Profit %: Target profit to sell (e.g., 3%)
- Stop Loss %: Maximum loss before exit (e.g., -10%)
- Trailing: Follow price up to maximize profits

### Step 3: Build Base Order Conditions (Entry)

These conditions determine when the bot opens a new position. Click **"+ Add Condition"** under "Base Order Conditions".

#### Example: RSI Oversold
1. Select indicator: **RSI**
2. Enter period: **14**
3. Select operator: **<** (less than)
4. Enter value: **30**
5. Select timeframe: **15 Minute**

#### Example: MACD Crossover
1. Select indicator: **MACD**
2. Enter fast: **12**, slow: **26**, signal: **9**
3. Select operator: **Crossing Above**
4. Enter value: **0**
5. Select timeframe: **1 Hour**

#### Example: RSI Increasing (Momentum)
1. Select indicator: **RSI**
2. Enter period: **14**
3. Select operator: **Increasing**
4. Select strength: **Moderate (1%)**
5. Select timeframe: **15 Minute**

### Step 4: Build Safety Order Conditions (DCA)

Optional. These conditions determine when the bot adds to an existing position (dollar-cost averaging). If no safety order conditions are set, the bot uses price deviation instead.

### Step 5: Build Take Profit Conditions (Exit)

Optional. These conditions determine when the bot sells. The bot will ALWAYS sell when:
- Take Profit % is reached
- Stop Loss % is hit (if enabled)

Use take profit conditions for additional exit signals like:
```
RSI(14) > 70 on 15m timeframe
```

### Step 6: Combine Conditions (AND/OR)

**AND Logic:** All conditions must be true simultaneously
```
RSI(14) < 30
AND
MACD Histogram crossing_above 0
```

**OR Logic:** Any one condition can trigger
```
RSI(14) < 30
OR
Stochastic %K(14) < 20
```

Toggle the **AND/OR** button at the top of each phase section.

### Step 7: Review & Create

- Check the configuration preview
- Make sure all values look correct
- Click **Create Bot**
- Start your bot when ready

## Common Strategies

### 1. RSI + MACD Combo
**Base Order (entry):** RSI oversold + MACD bullish crossover
```
Logic: AND
- RSI(14) < 30 [15m]
- MACD crossing_above 0 [1h]
```

**Take Profit (exit):** RSI overbought
```
- RSI(14) > 70 [15m]
```

### 2. Bollinger Bounce
**Base Order:** Price touches lower band
```
- Bollinger Band %(20,2) < 0 [15m]
```

**Take Profit:** Price touches upper band
```
- Bollinger Band %(20,2) > 100 [15m]
```

### 3. Multi-Indicator Confirmation
**Base Order:** Multiple oversold signals
```
Logic: AND
- RSI(14) < 30 [15m]
- Stochastic(14) < 20 [15m]
- Bollinger Band %(20,2) < 0 [15m]
```

**Take Profit:** Any overbought signal
```
Logic: OR
- RSI(14) > 70 [15m]
- Stochastic(14) > 80 [15m]
```

### 4. Trend Following
**Base Order:** Price momentum rising
```
Logic: AND
- EMA Cross crossing_above 0 [1h]
- RSI(14) increasing (Strong) [15m]
```

### 5. AI + Technical Confirmation
**Base Order:** AI buy signal confirmed by indicators
```
Logic: AND
- AI Buy > 0
- RSI(14) < 50 [15m]
```

## Available Indicators

### Oscillators
- **RSI** (Relative Strength Index)
  - Params: period (default 14)
  - Range: 0-100
  - Oversold: < 30, Overbought: > 70

- **Stochastic** (%K line)
  - Params: period (default 14), d_period (default 3)
  - Range: 0-100
  - Oversold: < 20, Overbought: > 80

- **MACD** (Moving Average Convergence Divergence)
  - Params: fast_period (12), slow_period (26), signal_period (9)
  - Crossover: Histogram crosses 0

### Moving Averages
- **EMA Cross** (Exponential Moving Average)
  - Params: period (default 50)
  - Crossing above 0 = bullish crossover

- **SMA Cross** (Simple Moving Average)
  - Params: period (default 50)
  - Crossing above 0 = bullish crossover

### Volatility
- **Bollinger Band %**
  - Params: period (20), std_dev (2)
  - Range: 0-100 typically (can exceed)
  - < 0 = below lower band, > 100 = above upper band

### Price/Volume
- **Price Change** - Recent price movement percentage
- **Volume** - Trading volume

### Aggregate Indicators (Signal-Based)
- **AI Buy** - Multi-timeframe AI confluence buy signal (returns 0 or 1)
- **AI Sell** - Multi-timeframe AI confluence sell signal (returns 0 or 1)
- **Bull Flag** - Bull flag pattern detection (returns 0 or 1)

Use these with `> 0` to check if the signal is active.

## Comparison Operators

### Standard Comparisons
- **>** (greater_than) - Value is above threshold
- **<** (less_than) - Value is below threshold
- **>=** (greater_equal) - Value is at or above
- **<=** (less_equal) - Value is at or below

### Crossing Detection
- **Crossing Above** - Value crosses from below to above threshold
  - Example: MACD crosses above 0 = bullish signal
- **Crossing Below** - Value crosses from above to below threshold
  - Example: Price crosses below SMA = bearish signal
- Requires 2+ candles to detect (compares current vs previous)

### Momentum
- **Increasing** - Value is rising (current > previous)
  - Optional strength threshold: Any (0%), Weak (0.5%), Moderate (1%), Strong (2%), Very Strong (5%)
- **Decreasing** - Value is falling (current < previous)
  - Same strength thresholds available

## Available Timeframes

Each condition can use a different timeframe:
- **5 Minute** (FIVE_MINUTE)
- **15 Minute** (FIFTEEN_MINUTE)
- **30 Minute** (THIRTY_MINUTE)
- **1 Hour** (ONE_HOUR)
- **4 Hour** (SIX_HOUR)
- **1 Day** (ONE_DAY)

## Tips & Best Practices

### 1. Start Simple
- Begin with 1-2 conditions
- Test with small amounts
- Add complexity once you're comfortable

### 2. Use Confirmation
- Don't rely on a single indicator
- Combine trend + momentum indicators
- Example: RSI (momentum) + MACD (trend)

### 3. Use Multiple Timeframes
- Higher timeframe for trend direction (1h, 4h)
- Lower timeframe for entry timing (5m, 15m)

### 4. Consider Aggregate Indicators
- AI Buy/Sell signals incorporate multiple factors
- Bull Flag detects chart patterns automatically
- Use them as confirmation alongside traditional indicators

### 5. Monitor & Adjust
- Watch your bot's performance
- Check indicator logs to see condition evaluations
- Adjust parameters if needed

## Troubleshooting

### "No signals detected"
- Conditions may be too strict
- Try relaxing thresholds (e.g., RSI < 35 instead of < 30)
- Check if indicators need more candles to calculate (MACD needs 26+)

### "Too many signals"
- Conditions may be too loose
- Add more confirmation conditions (use AND logic)
- Increase thresholds

### "Bot not buying/selling"
- Check indicator logs for detailed evaluation results
- Ensure sufficient balance for trades
- Verify conditions are actually being evaluated (check bot logs)

### "Crossing not working"
- Crossing requires 2+ candles of history
- First candle after start won't trigger crossings
- Check if values are actually crossing (not just touching)

## JSON Format Reference

For reference, here's what conditions look like in the backend `strategy_config`:

### Simple RSI Entry
```json
{
  "base_order_conditions": [
    {
      "type": "rsi",
      "period": 14,
      "operator": "less_than",
      "value": 30,
      "timeframe": "FIFTEEN_MINUTE"
    }
  ],
  "base_order_logic": "and",
  "take_profit_conditions": [
    {
      "type": "rsi",
      "period": 14,
      "operator": "greater_than",
      "value": 70,
      "timeframe": "FIFTEEN_MINUTE"
    }
  ],
  "take_profit_logic": "and"
}
```

### Multi-Condition with AI
```json
{
  "base_order_conditions": [
    {
      "type": "ai_buy",
      "operator": "greater_than",
      "value": 0
    },
    {
      "type": "rsi",
      "period": 14,
      "operator": "less_than",
      "value": 50,
      "timeframe": "FIFTEEN_MINUTE"
    }
  ],
  "base_order_logic": "and",
  "safety_order_conditions": [],
  "safety_order_logic": "and",
  "take_profit_conditions": [
    {
      "type": "ai_sell",
      "operator": "greater_than",
      "value": 0
    }
  ],
  "take_profit_logic": "and"
}
```
