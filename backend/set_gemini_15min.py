"""Set Gemini to check every 15 minutes"""
import sqlite3

conn = sqlite3.connect('trading.db')
cursor = conn.cursor()

print("=" * 80)
print("UPDATING GEMINI CHECK INTERVAL")
print("=" * 80)

# 15 minutes = 900 seconds
new_interval = 15 * 60  # 900 seconds

cursor.execute('''
    UPDATE bots
    SET check_interval_seconds = ?
    WHERE id = 1
''', (new_interval,))

print(f"✅ Updated Gemini check interval:")
print(f"   Old: 180 minutes (10,800 seconds)")
print(f"   New: 15 minutes (900 seconds)")
print()
print(f"📊 Daily API calls: ~96 calls/day")
print(f"📊 Token usage: ~768,000 tokens/day (well within 1M limit)")
print()
print("Gemini will now check positions 4x per hour!")

conn.commit()

# Verify
cursor.execute('SELECT check_interval_seconds FROM bots WHERE id = 1')
current = cursor.fetchone()[0]
print(f"\n✅ Verified: check_interval_seconds = {current} ({current/60} minutes)")

conn.close()
