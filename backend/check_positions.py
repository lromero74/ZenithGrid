"""Check position and trade data for positions 1, 2, 3"""
import sqlite3
import json

conn = sqlite3.connect('trading.db')
cursor = conn.cursor()

print("=" * 80)
print("POSITIONS (ID 1, 2, 3)")
print("=" * 80)

cursor.execute('''
    SELECT id, product_id, status, total_quote_spent, total_base_acquired,
           average_buy_price, opened_at, bot_id
    FROM positions
    WHERE id IN (1,2,3)
    ORDER BY id
''')

for row in cursor.fetchall():
    pos_id, product_id, status, quote_spent, base_acquired, avg_price, opened_at, bot_id = row
    print(f"\nPosition {pos_id} ({product_id}):")
    print(f"  Status: {status}")
    print(f"  Total Quote Spent: {quote_spent:.8f} BTC")
    print(f"  Total Base Acquired: {base_acquired:.8f}")
    print(f"  Average Buy Price: {avg_price:.8f}")
    print(f"  Opened: {opened_at}")
    print(f"  Bot ID: {bot_id}")

print("\n" + "=" * 80)
print("TRADES FOR THESE POSITIONS")
print("=" * 80)

cursor.execute('''
    SELECT position_id, side, quote_amount, base_amount, price, trade_type,
           order_id, timestamp
    FROM trades
    WHERE position_id IN (1,2,3)
    ORDER BY position_id, timestamp
''')

trades = cursor.fetchall()
if trades:
    for row in trades:
        pos_id, side, quote_amt, base_amt, price, trade_type, order_id, ts = row
        print(f"\nPosition {pos_id} Trade:")
        print(f"  Side: {side}")
        print(f"  Quote Amount: {quote_amt:.8f} BTC")
        print(f"  Base Amount: {base_amt:.8f}")
        print(f"  Price: {price:.8f}")
        print(f"  Type: {trade_type}")
        print(f"  Order ID: {order_id}")
        print(f"  Timestamp: {ts}")
else:
    print("\n⚠️  NO TRADES FOUND - This explains why balances are zero!")

print("\n" + "=" * 80)
print("ORDER HISTORY FOR THESE POSITIONS")
print("=" * 80)

cursor.execute('''
    SELECT position_id, product_id, side, order_type, trade_type,
           quote_amount, base_amount, status, order_id, error_message, timestamp
    FROM order_history
    WHERE position_id IN (1,2,3) OR position_id IS NULL
    ORDER BY timestamp DESC
    LIMIT 20
''')

orders = cursor.fetchall()
if orders:
    for row in orders:
        pos_id, product_id, side, order_type, trade_type, quote_amt, base_amt, status, order_id, error, ts = row
        print(f"\nOrder (Position {pos_id}, {product_id}):")
        print(f"  Type: {order_type} {side} ({trade_type})")
        print(f"  Quote: {quote_amt:.8f} BTC")
        print(f"  Base: {base_amt if base_amt else 'NULL'}")
        print(f"  Status: {status}")
        print(f"  Order ID: {order_id if order_id else 'NULL'}")
        if error:
            print(f"  Error: {error}")
        print(f"  Timestamp: {ts}")
else:
    print("\n⚠️  NO ORDER HISTORY FOUND")

conn.close()
