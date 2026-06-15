"""Tests for the position-coin coverage audit (do open longs still hold their coins?)."""
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import Account, Bot, Position
from app.services.position_coin_audit import (
    audit_account,
    expected_base_by_currency,
    find_coin_shortfalls,
)


class _FakeClient:
    """Stands in for the account-scoped Coinbase client."""

    def __init__(self, balances):
        # balances: {currency: available_value}
        self._accounts = [
            {"currency": cur, "available_balance": {"value": str(val)}}
            for cur, val in balances.items()
        ]

    async def get_accounts(self, force_fresh=False):
        return self._accounts


def _pos(**kw):
    """Minimal position double with the fields the audit reads."""
    defaults = dict(
        id=1, status="open", direction="long", product_type="spot",
        product_id="FOX-USD", total_base_acquired=10.0,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestExpectedBaseByCurrency:
    def test_sums_long_spot_positions_per_base_currency(self):
        positions = [
            _pos(id=1, product_id="FOX-USD", total_base_acquired=10.0),
            _pos(id=2, product_id="JTO-USD", total_base_acquired=5.0),
        ]
        assert expected_base_by_currency(positions) == {"FOX": 10.0, "JTO": 5.0}

    def test_groups_same_base_currency_across_positions(self):
        positions = [
            _pos(id=1, product_id="BTC-USD", total_base_acquired=0.1),
            _pos(id=2, product_id="BTC-USD", total_base_acquired=0.2),
        ]
        result = expected_base_by_currency(positions)
        assert set(result) == {"BTC"}
        assert result["BTC"] == pytest.approx(0.3)

    def test_excludes_short_futures_closed_and_malformed(self):
        positions = [
            _pos(id=1, direction="short", product_id="BTC-USD", total_base_acquired=1.0),
            _pos(id=2, product_type="future", product_id="ETH-USD", total_base_acquired=1.0),
            _pos(id=3, status="closed", product_id="SOL-USD", total_base_acquired=1.0),
            _pos(id=4, product_id="NODASH", total_base_acquired=1.0),
            _pos(id=5, product_id="AKT-USD", total_base_acquired=2.0),
        ]
        assert expected_base_by_currency(positions) == {"AKT": 2.0}

    def test_treats_missing_direction_and_type_as_long_spot(self):
        positions = [_pos(id=1, direction=None, product_type=None,
                          product_id="OXT-USD", total_base_acquired=155.0)]
        assert expected_base_by_currency(positions) == {"OXT": 155.0}


class TestFindCoinShortfalls:
    def test_no_shortfall_when_wallet_meets_or_exceeds(self):
        expected = {"FOX": 10.0, "JTO": 5.0}
        wallet = {"FOX": 10.0, "JTO": 6.0}
        assert find_coin_shortfalls(expected, wallet) == []

    def test_flags_currency_below_haircut(self):
        expected = {"FOX": 100.0}
        wallet = {"FOX": 80.0}
        shortfalls = find_coin_shortfalls(expected, wallet)
        assert len(shortfalls) == 1
        sf = shortfalls[0]
        assert sf["currency"] == "FOX"
        assert sf["expected"] == 100.0
        assert sf["available"] == 80.0
        assert sf["deficit"] == pytest.approx(20.0)
        assert sf["coverage_pct"] == pytest.approx(80.0)

    def test_missing_wallet_entry_is_full_deficit(self):
        shortfalls = find_coin_shortfalls({"GWEI": 7.0}, {})
        assert len(shortfalls) == 1
        assert shortfalls[0]["available"] == 0.0
        assert shortfalls[0]["deficit"] == pytest.approx(7.0)

    def test_haircut_tolerates_tiny_shortfall(self):
        # 99.95 >= 100 * 0.999 (=99.9) -> within tolerance, not flagged.
        assert find_coin_shortfalls({"X": 100.0}, {"X": 99.95}) == []
        # 99.8 < 99.9 -> flagged.
        assert len(find_coin_shortfalls({"X": 100.0}, {"X": 99.8})) == 1

    def test_zero_expected_never_flagged(self):
        assert find_coin_shortfalls({"X": 0.0}, {"X": 0.0}) == []


async def _seed_real_account_with_long(db, account_id=1, recorded=10.0):
    db.add(Account(id=account_id, user_id=1, name="Real", type="cex",
                   is_paper_trading=False, is_active=True))
    db.add(Bot(id=account_id * 10, account_id=account_id, user_id=1,
               name=f"Bot{account_id}", strategy_type="rsi", is_active=True))
    db.add(Position(id=account_id * 100, account_id=account_id, bot_id=account_id * 10,
                    user_id=1, product_id="FOX-USD", status="open", direction="long",
                    product_type="spot", total_base_acquired=recorded,
                    total_quote_spent=5.0, average_buy_price=0.5))
    await db.flush()
    return (await db.execute(
        select(Account).where(Account.id == account_id)
    )).scalar_one()


@pytest.mark.asyncio
class TestAuditAccountIntegration:
    async def test_reports_ok_when_wallet_covers(self, db_session, monkeypatch):
        account = await _seed_real_account_with_long(db_session, recorded=10.0)
        monkeypatch.setattr(
            "app.services.exchange_service.get_coinbase_for_account",
            lambda acct: _async_return(_FakeClient({"FOX": 10.0})),
        )
        summary = await audit_account(db_session, account)
        assert summary["coins_checked"] == 1
        assert summary["shortfalls"] == []

    async def test_records_shortfall_when_wallet_short(self, db_session, monkeypatch):
        account = await _seed_real_account_with_long(db_session, recorded=10.0)
        monkeypatch.setattr(
            "app.services.exchange_service.get_coinbase_for_account",
            lambda acct: _async_return(_FakeClient({"FOX": 3.0})),
        )
        summary = await audit_account(db_session, account)
        assert len(summary["shortfalls"]) == 1
        sf = summary["shortfalls"][0]
        assert sf["currency"] == "FOX"
        assert sf["available"] == 3.0
        assert sf["deficit"] == pytest.approx(7.0)

    async def test_account_with_no_open_longs_returns_none(self, db_session, monkeypatch):
        db_session.add(Account(id=2, user_id=1, name="Empty", type="cex",
                               is_paper_trading=False, is_active=True))
        await db_session.flush()
        account = (await db_session.execute(
            select(Account).where(Account.id == 2)
        )).scalar_one()
        # Should not even build a client.
        monkeypatch.setattr(
            "app.services.exchange_service.get_coinbase_for_account",
            lambda acct: (_ for _ in ()).throw(AssertionError("should not build client")),
        )
        assert await audit_account(db_session, account) is None


async def _async_return(value):
    return value
