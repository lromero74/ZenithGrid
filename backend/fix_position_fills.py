"""Fix the three positions with correct fill data from Coinbase"""
import sqlite3

conn = sqlite3.connect('trading.db')
cursor = conn.cursor()

print("=" * 80)
print("UPDATING POSITIONS AND TRADES WITH CORRECT FILL DATA")
print("=" * 80)

# Position 1: BCH-BTC
print("\n1. Updating Position 1 (BCH-BTC)...")
cursor.execute('''
    UPDATE positions
    SET total_quote_spent = 0.00024182086818,
        total_base_acquired = 0.04208514,
        average_buy_price = 0.0057459917723928
    WHERE id = 1
''')
cursor.execute('''
    UPDATE trades
    SET quote_amount = 0.00024182086818,
        base_amount = 0.04208514,
        price = 0.0057459917723928
    WHERE position_id = 1 AND side = 'buy'
''')
print("   ✅ Updated: 0.04208514 BCH @ 0.00574599 BTC (spent 0.00024182 BTC)")

# Position 2: COMP-BTC
print("\n2. Updating Position 2 (COMP-BTC)...")
cursor.execute('''
    UPDATE positions
    SET total_quote_spent = 0.0002417850522,
        total_base_acquired = 0.705,
        average_buy_price = 0.0003429575208511
    WHERE id = 2
''')
cursor.execute('''
    UPDATE trades
    SET quote_amount = 0.0002417850522,
        base_amount = 0.705,
        price = 0.0003429575208511
    WHERE position_id = 2 AND side = 'buy'
''')
print("   ✅ Updated: 0.705 COMP @ 0.00034296 BTC (spent 0.00024179 BTC)")

# Position 3: ALGO-BTC
print("\n3. Updating Position 3 (ALGO-BTC)...")
cursor.execute('''
    UPDATE positions
    SET total_quote_spent = 0.0002422612,
        total_base_acquired = 148,
        average_buy_price = 0.0000016369
    WHERE id = 3
''')
cursor.execute('''
    UPDATE trades
    SET quote_amount = 0.0002422612,
        base_amount = 148,
        price = 0.0000016369
    WHERE position_id = 3 AND side = 'buy'
''')
print("   ✅ Updated: 148 ALGO @ 0.00000164 BTC (spent 0.00024226 BTC)")

# Commit changes
conn.commit()

print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)

cursor.execute('''
    SELECT id, product_id, total_quote_spent, total_base_acquired, average_buy_price
    FROM positions
    WHERE id IN (1,2,3)
    ORDER BY id
''')

for row in cursor.fetchall():
    pos_id, product, quote, base, price = row
    print(f"\nPosition {pos_id} ({product}):")
    print(f"  Quote Spent: {quote:.8f} BTC")
    print(f"  Base Acquired: {base:.8f}")
    print(f"  Avg Price: {price:.8f}")

conn.close()

print("\n✅ All positions updated successfully!")
print("\n" + "=" * 80)
print("TOTAL INVESTED:")
print("=" * 80)
total = 0.00024182086818 + 0.0002417850522 + 0.0002422612
print(f"Total BTC spent across all 3 positions: {total:.8f} BTC")
print("=" * 80)
