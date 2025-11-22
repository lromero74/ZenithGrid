"""Update Gemini to 4 deals and create missing ADA position"""
import sqlite3
import json
from datetime import datetime

conn = sqlite3.connect('trading.db')
cursor = conn.cursor()

print("=" * 80)
print("1. UPDATING GEMINI TO 4 MAX CONCURRENT DEALS")
print("=" * 80)

cursor.execute('SELECT strategy_config FROM bots WHERE id = 1')
config = json.loads(cursor.fetchone()[0])
config['max_concurrent_deals'] = 4
cursor.execute('UPDATE bots SET strategy_config = ? WHERE id = 1',
               (json.dumps(config),))
print("✅ Updated Gemini max_concurrent_deals: 3 → 4")

print("\n" + "=" * 80)
print("2. CREATING MISSING ADA POSITION")
print("=" * 80)

# ADA purchase details from test_buy_ada.py:
# Order ID: 4c385bdc-2826-4c19-8c1c-e3039389bed7
# Filled Size: 30.57 ADA
# Filled Value: 0.0001488759 BTC
# Average Price: 0.00000487 BTC/ADA
# Timestamp: 2025-11-21 11:50:00

# Create position
cursor.execute('''
    INSERT INTO positions (
        bot_id, product_id, status, opened_at,
        initial_quote_balance, max_quote_allowed,
        total_quote_spent, total_base_acquired, average_buy_price,
        strategy_config_snapshot
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (
    1,  # Gemini bot
    'ADA-BTC',
    'open',
    '2025-11-21 11:50:00',
    0.00162552,  # Per-position budget (90% / 3 deals - will be 90% / 4 after update)
    0.00162552,
    0.0001488759,  # Actual filled value
    30.57,  # Actual filled size
    0.00000487,  # Average price
    json.dumps(config)  # Same config as other positions
))

position_id = cursor.lastrowid
print(f"✅ Created Position {position_id} (ADA-BTC)")

# Create trade record
cursor.execute('''
    INSERT INTO trades (
        position_id, timestamp, side, quote_amount, base_amount, price,
        trade_type, order_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
''', (
    position_id,
    '2025-11-21 11:50:00',
    'buy',
    0.0001488759,
    30.57,
    0.00000487,
    'initial',
    '4c385bdc-2826-4c19-8c1c-e3039389bed7'
))

print(f"✅ Created Trade for Position {position_id}")

# Create order history record
cursor.execute('''
    INSERT INTO order_history (
        timestamp, bot_id, position_id, product_id, side, order_type,
        trade_type, quote_amount, base_amount, price, status, order_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (
    '2025-11-21 11:50:00',
    1,  # Gemini bot
    position_id,
    'ADA-BTC',
    'BUY',
    'MARKET',
    'initial',
    0.0001488759,
    30.57,
    0.00000487,
    'success',
    '4c385bdc-2826-4c19-8c1c-e3039389bed7'
))

print(f"✅ Created Order History for Position {position_id}")

conn.commit()

print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)

cursor.execute('SELECT id, product_id, total_quote_spent, total_base_acquired FROM positions WHERE bot_id = 1 ORDER BY id')
print("\nAll Gemini positions:")
for row in cursor.fetchall():
    pos_id, product, quote, base = row
    print(f"  Position {pos_id} ({product}): {base:.8f} (spent {quote:.8f} BTC)")

conn.close()

print("\n✅ All updates complete!")
