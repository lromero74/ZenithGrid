"""Update Gemini budget to 90% and submit strong buy signal for ADA-BTC"""
import sqlite3
import json
from datetime import datetime, timedelta

# Connect to database
conn = sqlite3.connect('trading.db')
cursor = conn.cursor()

# 1. Update Gemini budget to 90%
cursor.execute('SELECT strategy_config FROM bots WHERE id = 1')
config = json.loads(cursor.fetchone()[0])
config['initial_budget_percentage'] = 90
cursor.execute('UPDATE bots SET strategy_config = ?, budget_percentage = 90.0 WHERE id = 1',
               (json.dumps(config),))
print("✅ Updated Gemini budget to 90%")
print(f"   Config: {json.dumps(config, indent=2)}")

# 2. Force last_signal_check to 4 hours ago to trigger immediate run
four_hours_ago = (datetime.utcnow() - timedelta(hours=4)).strftime('%Y-%m-%d %H:%M:%S')
cursor.execute('UPDATE bots SET last_signal_check = ? WHERE id = 1', (four_hours_ago,))
print(f"✅ Set last_signal_check to {four_hours_ago} (will trigger immediate run)")

# 3. Get current ADA-BTC price from market_data
cursor.execute('SELECT price FROM market_data ORDER BY timestamp DESC LIMIT 1')
result = cursor.fetchone()
current_price = result[0] if result else 0.000004  # fallback

print(f"✅ Current market price: {current_price}")

# Commit changes
conn.commit()
conn.close()

print("\n" + "="*60)
print("NEXT STEPS:")
print("="*60)
print("1. Gemini will run on next cycle (check interval: 180 minutes)")
print("2. With 90% budget, per-position budget will be:")
print("   - Total BTC * 90% / 3 deals = much larger orders")
print("3. Monitor logs for execution")
print("="*60)
