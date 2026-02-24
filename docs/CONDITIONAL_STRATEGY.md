# Conditional Strategy System

## Overview

The condition-based strategy system allows users to mix and match technical indicators with comparison operators to build custom trading rules. Conditions are organized into three phases: base order (entry), safety order (DCA), and take profit (exit).

## Architecture

### Core Components

#### 1. Condition Framework (`backend/app/conditions.py`)

**ComparisonOperator Enum:**
- `GREATER_THAN` (>)
- `LESS_THAN` (<)
- `GREATER_EQUAL` (>=)
- `LESS_EQUAL` (<=)
- `EQUAL` (==)
- `CROSSING_ABOVE` - value crosses from below to above threshold
- `CROSSING_BELOW` - value crosses from above to below threshold
- `INCREASING` - current value > previous value (with optional % strength threshold)
- `DECREASING` - current value < previous value (with optional % strength threshold)

**IndicatorType Enum:**

Traditional indicators:
- `RSI` - Relative Strength Index
- `MACD` - Moving Average Convergence Divergence
- `MACD_SIGNAL` - MACD signal line
- `MACD_HISTOGRAM` - MACD histogram
- `EMA` - Exponential Moving Average
- `SMA` - Simple Moving Average
- `PRICE` - Current market price
- `BOLLINGER_UPPER` - Upper Bollinger Band
- `BOLLINGER_MIDDLE` - Middle Bollinger Band
- `BOLLINGER_LOWER` - Lower Bollinger Band
- `STOCHASTIC_K` - Stochastic %K line
- `STOCHASTIC_D` - Stochastic %D line
- `VOLUME` - Trading volume
- `VOLUME_RSI` - RSI calculated on volume data

Aggregate indicators (return 0 or 1):
- `AI_BUY` - Multi-timeframe AI confluence buy signal
- `AI_SELL` - Multi-timeframe AI confluence sell signal
- `BULL_FLAG` - Bull flag pattern detection

**ConditionEvaluator Class:**
- `evaluate_condition()` - evaluates a single condition against indicator values
- `evaluate_group()` - evaluates a group with AND/OR logic
- Handles crossing detection using current + previous candle values
- Handles increasing/decreasing with configurable strength thresholds

#### 2. Indicator Calculator (`backend/app/indicator_calculator.py`)

Calculates all technical indicators from candle data and returns a standardized dictionary:

```python
{
  "price": 0.035,
  "rsi_14": 45.2,
  "macd_12_26_9": 0.0012,
  "macd_signal_12_26_9": 0.0008,
  "macd_histogram_12_26_9": 0.0004,
  "sma_20": 0.0345,
  "ema_20": 0.0348,
  "bb_upper_20_2": 0.0360,
  "bb_middle_20_2": 0.0345,
  "bb_lower_20_2": 0.0330,
  "stochastic_k_14_3": 35.5,
  "stochastic_d_14_3": 38.2,
  "volume": 1234567,
  "volume_rsi_14": 52.1,
  "ai_buy": 0,
  "ai_sell": 0,
  "bull_flag": 1,
}
```

Supports multi-timeframe evaluation: each condition can specify its own timeframe (5m, 15m, 30m, 1h, 4h, 1d).

#### 3. Indicator-Based Strategy (`backend/app/strategies/indicator_based.py`)

The unified strategy that handles all condition-based trading. Registered as `indicator_based` with display name "Custom Bot (Indicator-Based)".

**Phase-Based Condition Groups:**
```python
config:
  - base_order_conditions: List[Condition]   # Entry signals
  - base_order_logic: "and" | "or"
  - safety_order_conditions: List[Condition]  # DCA signals
  - safety_order_logic: "and" | "or"
  - take_profit_conditions: List[Condition]   # Exit signals
  - take_profit_logic: "and" | "or"
```

**Buy Logic (base order):**
1. If no position: Check `base_order_conditions`
   - If conditions met, create base order
2. If position exists: Check `safety_order_conditions` (or use price deviation)
   - If conditions met, create safety order

**Sell Logic (take profit):**
1. Check `take_profit_conditions`
2. Also check take profit % / stop loss % targets
3. Trailing TP/SL if enabled

#### 4. Frontend Condition Builder (`frontend/src/components/PhaseConditionSelector.tsx`)

Interactive UI for building conditions per phase:
- Dropdown for indicator type selection
- Dropdown for operator selection (including Increasing/Decreasing)
- Input fields for parameters (period, value, etc.)
- Timeframe selector per condition
- Add/remove conditions
- AND/OR logic toggle per phase

**Frontend condition types:** `rsi`, `macd`, `bb_percent`, `ema_cross`, `sma_cross`, `stochastic`, `price_change`, `volume`, `ai_buy`, `ai_sell`, `bull_flag`

**Frontend operators:** `greater_than`, `less_than`, `greater_equal`, `less_equal`, `crossing_above`, `crossing_below`, `increasing`, `decreasing`

## Example Use Cases

### Example 1: Simple RSI Oversold
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
  "base_order_logic": "and"
}
```
**Translation:** Buy when RSI(14) < 30 on 15m timeframe

### Example 2: MACD Crossover with RSI Filter
```json
{
  "base_order_conditions": [
    {
      "type": "macd",
      "fast_period": 12,
      "slow_period": 26,
      "signal_period": 9,
      "operator": "crossing_above",
      "value": 0,
      "timeframe": "ONE_HOUR"
    },
    {
      "type": "rsi",
      "period": 14,
      "operator": "less_than",
      "value": 50,
      "timeframe": "ONE_HOUR"
    }
  ],
  "base_order_logic": "and"
}
```
**Translation:** Buy when (MACD crosses above 0 AND RSI < 50) on 1h

### Example 3: AI + Bull Flag Confirmation
```json
{
  "base_order_conditions": [
    {
      "type": "ai_buy",
      "operator": "greater_than",
      "value": 0
    },
    {
      "type": "bull_flag",
      "operator": "greater_than",
      "value": 0
    }
  ],
  "base_order_logic": "and"
}
```
**Translation:** Buy when AI buy signal is active AND bull flag pattern detected

### Example 4: RSI Momentum with Strength
```json
{
  "base_order_conditions": [
    {
      "type": "rsi",
      "period": 14,
      "operator": "increasing",
      "value": 2,
      "timeframe": "FIFTEEN_MINUTE"
    }
  ],
  "base_order_logic": "and"
}
```
**Translation:** Buy when RSI is increasing with at least 2% strength

## Implementation Status

All phases are complete:

- [x] Condition framework (`conditions.py`) with all operators and indicators
- [x] Indicator calculator (`indicator_calculator.py`) with multi-timeframe support
- [x] Unified `IndicatorBasedStrategy` with phase-based conditions
- [x] Frontend `PhaseConditionSelector` component
- [x] Bot creation UI with per-phase condition builders
- [x] Crossing detection with current + previous values
- [x] Increasing/Decreasing operators with strength thresholds
- [x] Aggregate indicators (AI_BUY, AI_SELL, BULL_FLAG)
- [x] Multi-timeframe per-condition evaluation

## Technical Considerations

### Crossing Detection
- Stores previous candle's indicator values
- Compares previous vs current to detect crossings
- First candle after start won't trigger crossings (needs history)

### Increasing/Decreasing Operators
- Compares current value to previous value
- Optional strength threshold: minimum % change required
- Strength levels: Any (0%), Weak (0.5%), Moderate (1%), Strong (2%), Very Strong (5%)

### Indicator Calculation Efficiency
- Cached indicators between evaluations
- Only recalculates when new candle arrives
- Multi-timeframe: fetches candles at each condition's specified timeframe

### Database Schema
Bot model stores conditions in `strategy_config` JSON field:
```json
{
  "base_order_conditions": [ /* condition objects */ ],
  "base_order_logic": "and",
  "safety_order_conditions": [ /* condition objects */ ],
  "safety_order_logic": "and",
  "take_profit_conditions": [ /* condition objects */ ],
  "take_profit_logic": "and"
}
```

## Key Files

- `backend/app/conditions.py` - Condition framework (operators, indicators, evaluator)
- `backend/app/indicator_calculator.py` - Technical indicator calculations
- `backend/app/strategies/indicator_based.py` - Unified indicator-based strategy
- `backend/app/indicators/` - Aggregate indicator modules (ai_spot_opinion, bull_flag, risk_presets)
- `frontend/src/components/PhaseConditionSelector.tsx` - Condition builder UI
- `frontend/src/components/bots/BotFormModal.tsx` - Bot creation form with condition builders
