# Auto-Calculate Order Sizing Logic

## Overview
When `auto_calculate_order_sizes = True`, the bot dynamically calculates order sizes to fit within the allocated per-position budget.

## How It Works

### Fixed Base + Fixed Safety Orders (Fixed BTC Mode)

When both `base_order_type = "fixed_btc"` AND `safety_order_type = "fixed_btc"`:

**Goal:** Find value `X` where:
- Base order = `X`
- SO1 = `X` (same as base)
- SO2 = `X * volume_scale`
- SO3 = `X * volume_scale²`
- ...
- **Total = per_position_budget**

**Math:**
```
Total = X + X + X*scale + X*scale² + ... + X*scale^(n-1)
Total = X * (1 + 1 + scale + scale² + ... + scale^(n-1))
X = Total / multiplier_sum
```

Where `multiplier_sum = 1 + 1 + scale + scale² + ... + scale^(n-1)`

### Example Configuration (Bot 6)

```json
{
  "auto_calculate_order_sizes": true,
  "base_order_type": "fixed_btc",
  "base_order_btc": 0.00012,
  "safety_order_type": "fixed_btc",
  "safety_order_btc": 0.00012,
  "safety_order_volume_scale": 2,
  "max_safety_orders": 2,
  "max_concurrent_deals": 2,
  "budget_percentage": 100,
  "split_budget_across_pairs": true
}
```

**Calculation:**
- Aggregate BTC: 0.00336643 BTC
- Budget (100%): 0.00336643 BTC
- Per-position budget (split across 2 deals): 0.00336643 / 2 = **0.00168 BTC**

**multiplier_sum:**
- Base: 1
- SO1: 1 (same as base)
- SO2: 2¹ = 2
- **Total:** 1 + 1 + 2 = 4

**Calculated X:**
```
X = 0.00168 / 4 = 0.00042 BTC
```

**Order Sizes:**
- Base order: **0.00042 BTC**
- SO1: 0.00042 * 2⁰ = **0.00042 BTC**
- SO2: 0.00042 * 2¹ = **0.00084 BTC**
- **Total: 0.00168 BTC** ✓

## What the Configured Values Mean

### When `auto_calculate = true`:

- `base_order_btc` and `safety_order_btc` being **equal** is a signal that base and SO1 should be the same size
- The actual values (0.00012) are **ignored** during calculation
- They serve as:
  - Fallback values when auto_calculate is disabled
  - Signal that base and SO1 should scale together
  - Minimum order size reference

### When `auto_calculate = false`:

- `base_order_btc = 0.00012` means **exactly 0.00012 BTC** per base order
- `safety_order_btc = 0.00012` means **exactly 0.00012 BTC** for SO1, 0.00024 for SO2, etc.
- No dynamic calculation - fixed amounts are used

## Key Implementation Points

### In `calculate_base_order_size()`:

```python
if auto_calculate_order_sizes and safety_order_type == "fixed_btc":
    # Calculate multiplier: 1 (base) + 1 (SO1) + scale + scale² + ...
    total_multiplier = 1.0 + 1.0  # Base + SO1
    for order_num in range(2, max_safety_orders + 1):
        total_multiplier += volume_scale ** (order_num - 1)

    # Solve for X
    return balance / total_multiplier
```

### In `calculate_safety_order_size()`:

```python
if safety_order_type == "fixed_btc" and auto_calculate_order_sizes:
    # SO size = base order size * volume_scale^(order_num-1)
    # (NOT the configured safety_order_btc value!)
    base_safety_size = base_order_size
    return base_safety_size * (volume_scale ** (order_number - 1))
```

## Common Mistakes to Avoid

❌ **WRONG:** Using configured `base_order_btc` value directly when auto_calculate is enabled
✓ **RIGHT:** Calculate X dynamically to fit budget

❌ **WRONG:** Using configured `safety_order_btc` value when auto_calculate is enabled
✓ **RIGHT:** Use calculated base_order_size as the base for safety orders

❌ **WRONG:** Calculating base = budget - (all safety orders)
✓ **RIGHT:** Calculate X where base + all SOs = budget

❌ **WRONG:** Thinking total should always use full budget
✓ **RIGHT:** Total should equal exactly the per-position budget when all orders are placed

## Why This Matters

If auto_calculate doesn't work correctly:
- Orders may be too large (exceeding exchange minimums causes rejection)
- Budget utilization is inefficient
- Risk management is broken (position sizes don't match strategy)
- User configuration intent is ignored

## Testing

Always verify calculations match expected behavior:
```python
base = calculate_base_order_size(per_position_budget, max_safety_orders)
so1 = calculate_safety_order_size(base, 1)
so2 = calculate_safety_order_size(base, 2)
total = base + so1 + so2
assert abs(total - per_position_budget) < 0.00000001
```
