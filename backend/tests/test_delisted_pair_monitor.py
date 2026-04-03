"""
TradingPairMonitor regression tests

Covers two bugs fixed in the pair-sync daily job:

1. product_id (legacy single-pair field) was never checked — only product_ids list was
   scanned, so a bot whose pair was delisted but stored in the legacy field would keep
   firing 404s forever.

2. Paper accounts accumulate residual balances of delisted coins (mirrors real-exchange
   behaviour where you can't remove worthless coins). The monitor must identify these
   coins and publish them to _unresolvable_paper_coins so the paper trading client can
   skip pricing attempts rather than hammering the exchange with 404 requests every cycle.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Imports under test ────────────────────────────────────────────────────────
from app.services.delisted_pair_monitor import (
    TradingPairMonitor,
    _unresolvable_paper_coins,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_bot(
    bot_id: int = 1,
    name: str = "Test Bot",
    product_id: str | None = None,
    product_ids: list | None = None,
    is_active: bool = True,
    strategy_config: dict | None = None,
    user_id: int = 1,
):
    bot = MagicMock()
    bot.id = bot_id
    bot.name = name
    bot.product_id = product_id
    bot.product_ids = product_ids
    bot.is_active = is_active
    bot.strategy_config = strategy_config or {}
    bot.user_id = user_id
    return bot


def _make_account(
    account_id: int = 10,
    name: str = "Paper Account",
    paper_balances: dict | None = None,
    is_paper_trading: bool = True,
):
    account = MagicMock()
    account.id = account_id
    account.name = name
    account.paper_balances = json.dumps(paper_balances or {})
    account.is_paper_trading = is_paper_trading
    return account


def _monitor_with_products(available: set[str]) -> TradingPairMonitor:
    """Return a TradingPairMonitor whose _available_products are pre-seeded."""
    monitor = TradingPairMonitor()
    monitor._available_products = available
    monitor._usd_pairs = {p for p in available if p.endswith("-USD")}
    monitor._btc_pairs = {p for p in available if p.endswith("-BTC")}
    return monitor


def _db_returning(bots=(), accounts=()):
    """Return a mock AsyncSession that yields the given bots and accounts."""
    db = AsyncMock()

    async def _execute(stmt):
        result = MagicMock()
        # Decide which collection to return based on which model the query targets
        stmt_str = str(stmt)
        if "paper_balances" in stmt_str or "is_paper_trading" in stmt_str:
            result.scalars.return_value.all.return_value = list(accounts)
        else:
            result.scalars.return_value.all.return_value = list(bots)
        return result

    db.execute = _execute
    db.commit = AsyncMock()
    return db


# ── Tests: product_id single-pair field ──────────────────────────────────────

class TestProductIdDelisting:
    """Bug: product_id (legacy single-pair) was never checked for delisted status."""

    @pytest.mark.asyncio
    async def test_delisted_product_id_is_cleared_and_bot_deactivated(self):
        """A bot using only product_id whose pair is delisted must have that field
        cleared and is_active set to False."""
        bot = _make_bot(product_id="RONIN-USD", product_ids=None)
        available = {"BTC-USD", "ETH-USD", "SOL-USD"}  # RONIN-USD not present

        monitor = _monitor_with_products(available)
        monitor.get_available_products = AsyncMock(return_value=available)

        db = _db_returning(bots=[bot])
        sm = MagicMock()
        sm.return_value.__aenter__ = AsyncMock(return_value=db)
        sm.return_value.__aexit__ = AsyncMock(return_value=False)
        monitor.set_session_maker(sm)
        monitor.detect_stable_pairs = AsyncMock(return_value=[])

        results = await monitor.check_and_sync_pairs()

        assert bot.product_id is None, "product_id should be cleared after delisting"
        assert bot.is_active is False, "bot should be deactivated when its only pair is delisted"
        assert results["pairs_removed"] == 1
        assert any(
            b["bot_id"] == bot.id for b in results["affected_bots"]
        ), "affected_bots should include the deactivated bot"

    @pytest.mark.asyncio
    async def test_valid_product_id_is_left_alone(self):
        """A bot using product_id with a live pair must not be touched."""
        bot = _make_bot(product_id="BTC-USD", product_ids=None)
        available = {"BTC-USD", "ETH-USD"}

        monitor = _monitor_with_products(available)
        monitor.get_available_products = AsyncMock(return_value=available)

        db = _db_returning(bots=[bot])
        sm = MagicMock()
        sm.return_value.__aenter__ = AsyncMock(return_value=db)
        sm.return_value.__aexit__ = AsyncMock(return_value=False)
        monitor.set_session_maker(sm)
        monitor.detect_stable_pairs = AsyncMock(return_value=[])

        results = await monitor.check_and_sync_pairs()

        assert bot.product_id == "BTC-USD", "live product_id must not be modified"
        assert bot.is_active is True, "active bot must stay active"
        assert results["pairs_removed"] == 0

    @pytest.mark.asyncio
    async def test_multi_pair_bot_product_id_field_ignored(self):
        """A bot that has product_ids set should use the list logic, not the legacy path,
        even if product_id is also populated."""
        bot = _make_bot(product_id="BTC-USD", product_ids=["ETH-USD", "SOL-USD"])
        available = {"BTC-USD", "ETH-USD", "SOL-USD"}

        monitor = _monitor_with_products(available)
        monitor.get_available_products = AsyncMock(return_value=available)

        db = _db_returning(bots=[bot])
        sm = MagicMock()
        sm.return_value.__aenter__ = AsyncMock(return_value=db)
        sm.return_value.__aexit__ = AsyncMock(return_value=False)
        monitor.set_session_maker(sm)
        monitor.detect_stable_pairs = AsyncMock(return_value=[])

        results = await monitor.check_and_sync_pairs()

        # product_ids list is valid — nothing removed
        assert results["pairs_removed"] == 0
        assert bot.is_active is True


# ── Tests: _get_unresolvable_coins / paper balance noise suppression ──────────

class TestUnresolvableCoins:
    """Bug: delisted coins in paper balances caused 404 on every pricing cycle."""

    @pytest.mark.asyncio
    async def test_delisted_coin_in_paper_balance_identified(self):
        """RONIN in a paper account with no RONIN-USD or RONIN-BTC pair should appear
        in the unresolvable set."""
        account = _make_account(paper_balances={"USD": 1000.0, "RONIN": 0.05, "BTC": 0.1})
        available = {"BTC-USD", "ETH-USD", "SOL-USD"}  # no RONIN pairs

        monitor = _monitor_with_products(available)
        db = _db_returning(accounts=[account])

        result = await monitor._get_unresolvable_coins(db, available)

        assert "RONIN" in result, "RONIN should be identified as unresolvable"

    @pytest.mark.asyncio
    async def test_fiat_and_majors_never_flagged(self):
        """USD, BTC, ETH, USDC, USDT are always priceable and must never appear in
        unresolvable even if they have no explicit pair entry."""
        account = _make_account(paper_balances={
            "USD": 500.0, "BTC": 0.01, "ETH": 1.0, "USDC": 200.0, "USDT": 100.0,
        })
        available = {"ETH-USD", "SOL-USD"}  # minimal, no BTC-USD

        monitor = _monitor_with_products(available)
        db = _db_returning(accounts=[account])

        result = await monitor._get_unresolvable_coins(db, available)

        for safe in ("USD", "BTC", "ETH", "USDC", "USDT"):
            assert safe not in result, f"{safe} should never be flagged as unresolvable"

    @pytest.mark.asyncio
    async def test_dust_balances_not_flagged(self):
        """A balance below 1e-4 (dust) must not trigger the unresolvable flag since
        the pricing code already skips dust."""
        account = _make_account(paper_balances={"RONIN": 5e-5, "USD": 100.0})
        available = {"BTC-USD", "ETH-USD"}

        monitor = _monitor_with_products(available)
        db = _db_returning(accounts=[account])

        result = await monitor._get_unresolvable_coins(db, available)

        assert "RONIN" not in result, "dust RONIN balance should not be flagged"

    @pytest.mark.asyncio
    async def test_active_coin_not_flagged(self):
        """A coin that has a tradeable pair on the exchange must not appear in the
        unresolvable set."""
        account = _make_account(paper_balances={"SOL": 5.0, "USD": 100.0})
        available = {"SOL-USD", "BTC-USD", "ETH-USD"}

        monitor = _monitor_with_products(available)
        db = _db_returning(accounts=[account])

        result = await monitor._get_unresolvable_coins(db, available)

        assert "SOL" not in result, "SOL has SOL-USD so it should not be flagged"

    @pytest.mark.asyncio
    async def test_check_and_sync_populates_module_cache(self):
        """After check_and_sync_pairs() the module-level _unresolvable_paper_coins set
        must contain RONIN so the paper trading client can skip pricing it."""
        import app.services.delisted_pair_monitor as monitor_module

        # Reset module cache
        monitor_module._unresolvable_paper_coins.clear()

        account = _make_account(paper_balances={"RONIN": 0.05, "USD": 1000.0})
        available = {"BTC-USD", "ETH-USD", "SOL-USD"}

        monitor = _monitor_with_products(available)
        monitor.get_available_products = AsyncMock(return_value=available)
        monitor.detect_stable_pairs = AsyncMock(return_value=[])

        db = _db_returning(bots=[], accounts=[account])
        sm = MagicMock()
        sm.return_value.__aenter__ = AsyncMock(return_value=db)
        sm.return_value.__aexit__ = AsyncMock(return_value=False)
        monitor.set_session_maker(sm)

        await monitor.check_and_sync_pairs()

        assert "RONIN" in monitor_module._unresolvable_paper_coins, (
            "_unresolvable_paper_coins should be populated after sync so "
            "paper_trading_client skips pricing"
        )

        # Cleanup
        monitor_module._unresolvable_paper_coins.clear()

    @pytest.mark.asyncio
    async def test_balances_are_preserved_not_zeroed(self):
        """Delisted coins must keep their balance — mirrors real-exchange behaviour
        where you can't remove worthless coins."""
        original_ronin = 0.05407
        account = _make_account(paper_balances={"RONIN": original_ronin, "USD": 1000.0})
        available = {"BTC-USD", "ETH-USD"}

        monitor = _monitor_with_products(available)
        monitor.get_available_products = AsyncMock(return_value=available)
        monitor.detect_stable_pairs = AsyncMock(return_value=[])

        db = _db_returning(bots=[], accounts=[account])
        sm = MagicMock()
        sm.return_value.__aenter__ = AsyncMock(return_value=db)
        sm.return_value.__aexit__ = AsyncMock(return_value=False)
        monitor.set_session_maker(sm)

        await monitor.check_and_sync_pairs()

        # account.paper_balances must NOT have been mutated
        stored = json.loads(account.paper_balances)
        assert stored.get("RONIN") == original_ronin, (
            "RONIN balance must be preserved — paper account mirrors real exchange "
            "where delisted coins sit in your account"
        )


# ── Tests: paper trading client pricing skip ──────────────────────────────────

class TestPaperClientPricingSkip:
    """The paper trading client must skip pricing (and avoid HTTP requests) for
    coins already flagged as unresolvable by the pair monitor."""

    def test_is_known_unresolvable_returns_true_when_in_set(self):
        """_is_known_unresolvable must return True for coins in the module-level set."""
        import app.services.delisted_pair_monitor as monitor_module
        from app.exchange_clients.paper_trading_client import PaperTradingClient

        monitor_module._unresolvable_paper_coins.clear()
        monitor_module._unresolvable_paper_coins.add("RONIN")

        assert PaperTradingClient._is_known_unresolvable("RONIN") is True
        assert PaperTradingClient._is_known_unresolvable("SOL") is False

        monitor_module._unresolvable_paper_coins.clear()

    def test_is_known_unresolvable_returns_false_when_set_empty(self):
        """When _unresolvable_paper_coins is empty nothing should be flagged."""
        import app.services.delisted_pair_monitor as monitor_module
        from app.exchange_clients.paper_trading_client import PaperTradingClient

        monitor_module._unresolvable_paper_coins.clear()

        assert PaperTradingClient._is_known_unresolvable("RONIN") is False
        assert PaperTradingClient._is_known_unresolvable("OOKI") is False
