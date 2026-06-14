"""
Tests for the SQL-aggregated realized-PnL path.

- aggregate_pnl_rows(): pure bucketing of pre-grouped (product_id, all_time, today)
  sums into usd/btc/usdc, preserving the old per-position quote semantics.
- _query_closed_pnl(): the DB aggregate — proves parity with hand-summed values,
  the "today" filter, status scoping, and (critically) account isolation.
"""

from datetime import timedelta

from app.models import Account, Position, User
from app.services.portfolio_calculations import aggregate_pnl_rows
from app.services.portfolio_service import _query_closed_pnl
from app.utils.timeutil import utcnow


async def _seed_account(db, email):
    user = User(email=email, hashed_password="fakehash")
    db.add(user)
    await db.flush()
    account = Account(user_id=user.id, name="Acct", type="cex", is_active=True)
    db.add(account)
    await db.flush()
    return account


def _closed(account_id, product_id, profit, closed_at, status="closed"):
    return Position(
        account_id=account_id, product_id=product_id, status=status,
        profit_quote=profit, closed_at=closed_at,
    )


class TestAggregatePnlRows:
    def test_happy_buckets_by_quote_currency(self):
        """USD/BTC/USDC pairs land in their own buckets for both totals."""
        rows = [
            ("BTC-USD", 100.0, 10.0),
            ("ETH-BTC", 0.5, 0.1),
            ("SOL-USDC", 20.0, 0.0),
        ]
        all_time, today = aggregate_pnl_rows(rows)
        assert all_time == {"usd": 100.0, "btc": 0.5, "usdc": 20.0}
        assert today == {"usd": 10.0, "btc": 0.1, "usdc": 0.0}

    def test_edge_unknown_quote_and_malformed_product_id(self):
        """Unknown quote (USDT) buckets into usd; a product_id without '-'
        falls back to BTC (mirrors Position.get_quote_currency)."""
        rows = [
            ("DOGE-USDT", 7.0, 1.0),   # unknown quote -> usd bucket
            ("WEIRD", 3.0, 2.0),        # no '-' -> BTC
        ]
        all_time, today = aggregate_pnl_rows(rows)
        assert all_time == {"usd": 7.0, "btc": 3.0, "usdc": 0.0}
        assert today == {"usd": 1.0, "btc": 2.0, "usdc": 0.0}

    def test_failure_none_sums_and_empty(self):
        """NULL sums (SQL may return None) coerce to 0; empty rows -> all zeros."""
        assert aggregate_pnl_rows([]) == (
            {"usd": 0.0, "btc": 0.0, "usdc": 0.0},
            {"usd": 0.0, "btc": 0.0, "usdc": 0.0},
        )
        all_time, today = aggregate_pnl_rows([("BTC-USD", None, None)])
        assert all_time["usd"] == 0.0 and today["usd"] == 0.0


class TestQueryClosedPnl:
    async def test_sums_match_and_today_filter(self, db_session):
        """Happy path: SQL aggregate matches hand-summed totals; the 'today'
        bucket only includes positions closed since local midnight."""
        acct = await _seed_account(db_session, "pnl1@example.com")
        now = utcnow()
        yesterday = now - timedelta(days=1)
        db_session.add_all([
            _closed(acct.id, "BTC-USD", 100.0, now),        # today
            _closed(acct.id, "BTC-USD", 25.0, yesterday),   # old
            _closed(acct.id, "ETH-BTC", 0.4, now),          # today, btc
            _closed(acct.id, "SOL-USDC", 9.0, yesterday),   # old, usdc
        ])
        await db_session.flush()

        all_time, today = await _query_closed_pnl(db_session, [acct.id])
        assert all_time == {"usd": 125.0, "btc": 0.4, "usdc": 9.0}
        assert today == {"usd": 100.0, "btc": 0.4, "usdc": 0.0}

    async def test_excludes_open_positions(self, db_session):
        """Edge: open positions are not counted toward realized PnL."""
        acct = await _seed_account(db_session, "pnl2@example.com")
        now = utcnow()
        db_session.add_all([
            _closed(acct.id, "BTC-USD", 50.0, now),
            _closed(acct.id, "BTC-USD", 999.0, now, status="open"),  # ignored
        ])
        await db_session.flush()

        all_time, _ = await _query_closed_pnl(db_session, [acct.id])
        assert all_time["usd"] == 50.0

    async def test_does_not_bleed_across_accounts(self, db_session):
        """Failure/security (CLAUDE.md rule 12): a second account's closed
        positions must NOT contaminate the first account's PnL."""
        acct_a = await _seed_account(db_session, "pnl_a@example.com")
        acct_b = await _seed_account(db_session, "pnl_b@example.com")
        now = utcnow()
        db_session.add_all([
            _closed(acct_a.id, "BTC-USD", 30.0, now),
            _closed(acct_b.id, "BTC-USD", 7000.0, now),  # must not leak into A
        ])
        await db_session.flush()

        all_time, _ = await _query_closed_pnl(db_session, [acct_a.id])
        assert all_time["usd"] == 30.0

    async def test_empty_account_list_returns_zeros(self, db_session):
        """Edge: no accounts -> zero PnL, no query needed."""
        all_time, today = await _query_closed_pnl(db_session, [])
        assert all_time == {"usd": 0.0, "btc": 0.0, "usdc": 0.0}
        assert today == {"usd": 0.0, "btc": 0.0, "usdc": 0.0}
