"""
Migration: Repair paper trading balances from open positions

Scans all open positions on the paper trading account and ensures the
paper_balances JSON has at least enough of each base currency to cover
the position's total_base_acquired.  Also clears the error message on
position 2765 (deal #212, UNI-BTC) so the exclamation mark disappears.

Idempotent: skips currencies where balance >= position amount.
"""

import json
import os
import sqlite3


# Paper trading account ID
PAPER_ACCOUNT_ID = 3

# Position whose error should be cleared (UNI-BTC stuck deal)
CLEAR_ERROR_POSITION_ID = 2765

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading.db")


def run():
    """Repair paper balances so they reflect open position holdings."""
    if not os.path.exists(DB_PATH):
        print(f"  Database not found at {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Load current paper balances
        cursor.execute(
            "SELECT paper_balances FROM accounts WHERE id = ?",
            (PAPER_ACCOUNT_ID,),
        )
        row = cursor.fetchone()
        if not row:
            print(f"  Paper account {PAPER_ACCOUNT_ID} not found — skipping")
            return False

        balances = json.loads(row[0]) if row[0] else {}
        print(f"  Current paper balances: {balances}")

        # 2. Scan all open positions on the paper account
        cursor.execute(
            """
            SELECT id, product_id, total_base_acquired
            FROM positions
            WHERE account_id = ? AND status = 'open' AND total_base_acquired > 0
            """,
            (PAPER_ACCOUNT_ID,),
        )
        positions = cursor.fetchall()

        if not positions:
            print("  No open positions with base holdings — nothing to repair")
        else:
            changed = False
            for pos_id, product_id, base_acquired in positions:
                base_currency = product_id.split("-")[0]
                current = balances.get(base_currency, 0.0)
                if current < base_acquired:
                    print(
                        f"  Position {pos_id} ({product_id}): "
                        f"{base_currency} balance {current} < acquired {base_acquired} — restoring"
                    )
                    balances[base_currency] = base_acquired
                    changed = True
                else:
                    print(
                        f"  Position {pos_id} ({product_id}): "
                        f"{base_currency} balance {current} >= acquired {base_acquired} — OK"
                    )

            if changed:
                cursor.execute(
                    "UPDATE accounts SET paper_balances = ? WHERE id = ?",
                    (json.dumps(balances), PAPER_ACCOUNT_ID),
                )
                print(f"  Updated paper balances: {balances}")

        # 3. Clear error message on the stuck UNI position
        cursor.execute(
            "SELECT id, last_error_message FROM positions WHERE id = ?",
            (CLEAR_ERROR_POSITION_ID,),
        )
        err_row = cursor.fetchone()
        if err_row and err_row[1]:
            cursor.execute(
                "UPDATE positions SET last_error_message = NULL WHERE id = ?",
                (CLEAR_ERROR_POSITION_ID,),
            )
            print(f"  Cleared error on position {CLEAR_ERROR_POSITION_ID}: was '{err_row[1]}'")
        elif err_row:
            print(f"  Position {CLEAR_ERROR_POSITION_ID} already has no error — OK")
        else:
            print(f"  Position {CLEAR_ERROR_POSITION_ID} not found — skipping error clear")

        conn.commit()
        print("  Paper balance repair complete")
        return True

    except Exception as e:
        conn.rollback()
        print(f"  Paper balance repair failed: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    run()
