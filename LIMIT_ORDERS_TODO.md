# Limit Orders Implementation - Remaining Work

## ✅ Completed (Commits: 27f0052, b92bb42)

1. **Database & Models**
   - Created `PendingOrder` model
   - Added `pending_orders` table with migration
   - Added relationships to Position and Bot models

2. **Coinbase API Support**
   - `create_limit_order()` - Place GTC limit orders
   - `get_order()` - Fetch order status
   - `cancel_order()` - Cancel pending orders

3. **Configuration**
   - Added `safety_order_type` parameter to AI Autonomous strategy
   - Options: "market" or "limit"
   - Default: "market" for AI bots

## 🔄 Remaining Implementation

### 1. Update Trading Engine (trading_engine_v2.py)

Add new method `execute_limit_buy()`:

```python
async def execute_limit_buy(
    self,
    position: Position,
    bot_id: int,
    quote_amount: float,
    limit_price: float,
    trade_type: str
) -> PendingOrder:
    """
    Place a limit buy order and track it in pending_orders table

    Args:
        position: Position to add order to
        bot_id: Bot placing the order
        quote_amount: Amount of quote currency (BTC/USD)
        limit_price: Target price for the order
        trade_type: "safety_order_1", "safety_order_2", etc.

    Returns:
        PendingOrder record
    """
    # 1. Place limit order via Coinbase API
    # 2. Create PendingOrder record in database
    # 3. Return PendingOrder
```

Update `execute_buy()` to check config and route to limit or market:

```python
# In execute_buy, check strategy config
safety_order_type = position.strategy_config_snapshot.get("safety_order_type", "market")

if trade_type != "initial" and safety_order_type == "limit":
    # Calculate limit price based on strategy
    limit_price = current_price  # Or apply discount based on strategy
    return await self.execute_limit_buy(position, bot_id, quote_amount, limit_price, trade_type)
else:
    # Existing market order logic
    ...
```

### 2. Create Order Monitoring Service

Create `app/services/order_monitor.py`:

```python
"""
Order Monitoring Service

Periodically checks pending orders and updates their status.
When orders fill, creates Trade records and updates Position.
"""

class OrderMonitorService:
    async def check_pending_orders(self):
        """Check all pending orders and update status"""
        # 1. Fetch all pending orders from database
        # 2. For each order, call trading_client.get_order(order_id)
        # 3. If status == "filled":
        #    - Create Trade record
        #    - Update Position averages
        #    - Mark PendingOrder as filled
        # 4. If status == "canceled" or "expired":
        #    - Mark PendingOrder accordingly

    async def start_monitoring(self):
        """Start background task to monitor orders"""
        # Run check_pending_orders() every 30 seconds
```

Add to `multi_bot_monitor.py`:
```python
# Start order monitor alongside bot monitor
order_monitor = OrderMonitorService()
asyncio.create_task(order_monitor.start_monitoring())
```

### 3. API Endpoint Updates

Update `app/routers/positions.py`:

```python
@router.get("/{position_id}")
async def get_position(position_id: int):
    position = db.query(Position).filter(Position.id == position_id).first()

    # Count pending orders
    pending_count = db.query(PendingOrder).filter(
        PendingOrder.position_id == position_id,
        PendingOrder.status == "pending"
    ).count()

    return {
        **position.dict(),
        "pending_orders_count": pending_count
    }
```

Update `app/routers/positions.py` list endpoint:

```python
@router.get("/")
async def list_positions():
    positions = db.query(Position).all()

    result = []
    for position in positions:
        pending_count = db.query(PendingOrder).filter(
            PendingOrder.position_id == position.id,
            PendingOrder.status == "pending"
        ).count()

        result.append({
            **position.dict(),
            "pending_orders_count": pending_count
        })

    return result
```

### 4. Frontend Updates

Update `frontend/src/types/index.ts`:

```typescript
export interface Position {
  // ... existing fields ...
  pending_orders_count?: number;  // Count of unfilled limit orders
}
```

Update `frontend/src/pages/Positions.tsx` line 1818:

```typescript
// Before:
<div className="text-slate-400">Active: 0</div>

// After:
<div className="text-slate-400">Active: {position.pending_orders_count || 0}</div>
```

### 5. Testing

Test scenarios:
1. Create bot with `safety_order_type: "limit"`
2. Place initial order (market)
3. Price drops, bot places limit order for safety order
4. Verify `pending_orders` table has record
5. Verify frontend shows "Active: 1"
6. Let order fill
7. Verify order monitor creates Trade record
8. Verify frontend shows "Completed: 1, Active: 0"

## Notes

- AI bots always use market orders (safety_order_type defaults to "market")
- Non-AI DCA bots can configure limit orders for price-based safety orders
- Limit orders use Good-Til-Cancelled (GTC) - stay open until filled or canceled
- Order monitor should handle partial fills appropriately
- Consider adding cancel functionality for stale orders (e.g., > 7 days old)
