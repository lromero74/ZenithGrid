# Conditional Strategy System (3Commas-Style)

## Overview

This document describes the flexible condition-based strategy system that allows users to mix and match technical indicators with various comparison operators, similar to 3Commas DCA bots.

## Problem Statement

**Previous Limitation:**
- Each strategy had hardcoded logic (e.g., "buy when MACD crosses above signal")
- Users couldn't customize indicator combinations
- Limited to predefined strategy templates

**Goal:**
- Allow users to build custom trading conditions
- Support multiple comparison operators (>, <, crossing above, crossing below, etc.)
- Enable AND/OR logic for combining conditions
- Match 3Commas flexibility while maintaining type safety

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

**IndicatorType Enum:**
Supported indicators:
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- MACD_SIGNAL (MACD signal line)
- MACD_HISTOGRAM (MACD histogram)
- EMA (Exponential Moving Average)
- SMA (Simple Moving Average)
- PRICE (current market price)
- BOLLINGER_UPPER (upper Bollinger Band)
- BOLLINGER_MIDDLE (middle Bollinger Band)
- BOLLINGER_LOWER (lower Bollinger Band)
- STOCHASTIC_K (%K line)
- STOCHASTIC_D (%D line)
- VOLUME (trading volume)

**Condition Model:**
```python
Condition:
  - indicator: IndicatorType (e.g., RSI)
  - operator: ComparisonOperator (e.g., LESS_THAN)
  - value_type: "static" or "indicator"
  - static_value: number (e.g., 30 for "RSI < 30")
  - compare_indicator: IndicatorType (for indicator vs indicator)
  - indicator_params: dict (e.g., {"period": 14})
```

**ConditionGroup Model:**
```python
ConditionGroup:
  - logic: AND or OR
  - conditions: List[Condition]
  - sub_groups: List[ConditionGroup] (for nesting)
```

**ConditionEvaluator Class:**
- `evaluate_condition()` - evaluates single condition
- `evaluate_group()` - evaluates group with AND/OR logic
- Handles crossing detection using current + previous values

#### 2. Indicator Calculator (`backend/app/indicator_calculator.py`)

**Status:** To be implemented

Will calculate all technical indicators from candle data and return standardized dictionary:

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
  # ... etc
}
```

#### 3. Conditional DCA Strategy (`backend/app/strategies/conditional_dca.py`)

**Status:** To be implemented

A DCA strategy that uses condition groups for buy/sell decisions:

```python
@StrategyRegistry.register
class ConditionalDCAStrategy(TradingStrategy):
    config:
      - base_order_size
      - safety_order_size
      - max_safety_orders
      - price_deviation
      - take_profit_percentage
      - stop_loss_percentage
      - buy_conditions: ConditionGroup
      - sell_conditions: ConditionGroup
```

**Buy Logic:**
1. If no position: Check `buy_conditions` group
   - If conditions met → create base order
2. If position exists: Check price deviation for safety orders
   - If price dropped enough → create safety order

**Sell Logic:**
1. Check `sell_conditions` group
2. Also check take profit / stop loss targets

## Example Use Cases

### Example 1: Simple RSI Oversold
```json
{
  "buy_conditions": {
    "logic": "AND",
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
**Translation:** Buy when RSI(14) < 30

### Example 2: MACD Crossover with RSI Filter
```json
{
  "buy_conditions": {
    "logic": "AND",
    "conditions": [
      {
        "indicator": "macd_histogram",
        "operator": "crossing_above",
        "value_type": "static",
        "static_value": 0,
        "indicator_params": {"fast_period": 12, "slow_period": 26, "signal_period": 9}
      },
      {
        "indicator": "rsi",
        "operator": "less_than",
        "value_type": "static",
        "static_value": 50,
        "indicator_params": {"period": 14}
      }
    ]
  }
}
```
**Translation:** Buy when (MACD crosses above 0 AND RSI < 50)

### Example 3: Price Below Bollinger Band
```json
{
  "buy_conditions": {
    "logic": "AND",
    "conditions": [
      {
        "indicator": "price",
        "operator": "less_than",
        "value_type": "indicator",
        "compare_indicator": "bollinger_lower",
        "compare_indicator_params": {"period": 20, "std_dev": 2}
      }
    ]
  }
}
```
**Translation:** Buy when Price < Bollinger Lower Band(20, 2)

### Example 4: Complex Multi-Condition
```json
{
  "buy_conditions": {
    "logic": "OR",
    "sub_groups": [
      {
        "logic": "AND",
        "conditions": [
          {"indicator": "rsi", "operator": "less_than", "static_value": 30},
          {"indicator": "macd_histogram", "operator": "crossing_above", "static_value": 0}
        ]
      },
      {
        "logic": "AND",
        "conditions": [
          {"indicator": "stochastic_k", "operator": "less_than", "static_value": 20},
          {"indicator": "price", "operator": "crossing_below", "compare_indicator": "sma", "compare_indicator_params": {"period": 50}}
        ]
      }
    ]
  }
}
```
**Translation:** Buy when:
- (RSI < 30 AND MACD crosses above 0) OR
- (Stochastic %K < 20 AND Price crosses below SMA(50))

## Implementation Plan

### Phase 1: Backend Core (Current)
- [x] Create `conditions.py` with condition framework
- [ ] Create `indicator_calculator.py` for computing indicators
- [ ] Create `conditional_dca.py` strategy
- [ ] Add tests for condition evaluation

### Phase 2: Strategy Integration
- [ ] Register conditional strategy in registry
- [ ] Add API endpoints for condition validation
- [ ] Update bot model to support condition groups
- [ ] Test with real market data

### Phase 3: Frontend UI
- [ ] Create condition builder UI component
- [ ] Dropdown for indicator selection
- [ ] Dropdown for operator selection
- [ ] Input fields for parameters
- [ ] Add/remove conditions
- [ ] AND/OR logic toggle
- [ ] Nested groups support
- [ ] Visual preview of conditions

### Phase 4: Testing & Refinement
- [ ] Backtest with various condition combinations
- [ ] Performance optimization
- [ ] Error handling and validation
- [ ] User documentation

## Technical Considerations

### Crossing Detection
Requires storing previous indicator values:
- Store last 2 candle's indicator values
- Compare previous vs current to detect crossings
- Handle edge cases (first candle, missing data)

### Indicator Calculation Efficiency
- Cache calculated indicators between evaluations
- Only recalculate when new candle arrives
- Use vectorized calculations where possible

### Condition Validation
- Validate condition structure before saving bot
- Check for contradictory conditions (RSI > 70 AND RSI < 30)
- Warn about computationally expensive combinations

### Database Schema
Bot model already has `strategy_config` JSON field, which can store:
```json
{
  "strategy_type": "conditional_dca",
  "base_order_btc": 0.001,
  "safety_order_btc": 0.0005,
  "max_safety_orders": 5,
  "price_deviation": 2.0,
  "take_profit_percentage": 3.0,
  "buy_conditions": { /* ConditionGroup */ },
  "sell_conditions": { /* ConditionGroup */ }
}
```

## UI Wireframe (Conceptual)

```
┌─────────────────────────────────────────────────────┐
│ Buy Conditions                                      │
├─────────────────────────────────────────────────────┤
│ Logic: [AND ▼]                                      │
│                                                     │
│ ┌─ Condition 1 ──────────────────────────────────┐ │
│ │ [RSI ▼] [less than ▼] [30] period: [14]   [x]│ │
│ └───────────────────────────────────────────────┘ │
│                                                     │
│ ┌─ Condition 2 ──────────────────────────────────┐ │
│ │ [MACD Histogram ▼] [crossing above ▼] [0] [x]│ │
│ │ fast: [12] slow: [26] signal: [9]           │ │
│ └───────────────────────────────────────────────┘ │
│                                                     │
│ [+ Add Condition] [+ Add Group]                    │
└─────────────────────────────────────────────────────┘
```

## Files Modified/Created

### New Files:
- `backend/app/conditions.py` - Condition framework
- `backend/app/indicator_calculator.py` - Indicator calculation (TODO)
- `backend/app/strategies/conditional_dca.py` - Conditional DCA strategy (TODO)
- `frontend/src/components/ConditionBuilder.tsx` - UI for building conditions (TODO)

### Modified Files:
- `backend/app/strategies/__init__.py` - Register new strategy
- `frontend/src/pages/Bots.tsx` - Add condition builder to bot creation

## Benefits

1. **Flexibility:** Users can create any combination of conditions
2. **Reusability:** Same framework works for buy and sell conditions
3. **Extensibility:** Easy to add new indicators or operators
4. **Type Safety:** Enums prevent typos and invalid configurations
5. **Testability:** Each component can be unit tested independently

## Future Enhancements

- **Backtesting UI:** Test conditions against historical data
- **Templates:** Pre-built condition templates (e.g., "Classic MACD Crossover")
- **Condition Analytics:** Show how often conditions are met
- **Multi-Timeframe:** Evaluate conditions on different timeframes
- **Advanced Indicators:** Add ATR, ADX, Ichimoku, etc.
- **Custom Indicators:** Allow users to define custom formulas

## Status

**Current Phase:** Phase 1 - Backend Core (In Progress)
**Next Steps:**
1. Create `indicator_calculator.py`
2. Create `conditional_dca.py` strategy
3. Test condition evaluation with sample data
