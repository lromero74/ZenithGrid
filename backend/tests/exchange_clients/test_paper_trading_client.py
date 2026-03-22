"""
Tests for backend/app/exchange_clients/paper_trading_client.py

Tests the paper trading exchange client that simulates order execution
without hitting real exchanges. Uses mock Account and db sessions.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.exchange_clients.paper_trading_client import (
    PaperTradingClient,
    _account_balance_locks,
    simulate_slippage_ctx,
)


# =========================================================
# Fixtures
# =========================================================


def _make_mock_account(
    is_paper=True,
    paper_balances=None,
    account_id=1,
):
    """Create a mock Account object for paper trading tests."""
    account = MagicMock()
    account.id = account_id
    account.is_paper_trading = is_paper
    account.paper_balances = (
        json.dumps(paper_balances) if paper_balances else None
    )
    return account


def _make_mock_db(account=None):
    """Create a mock async db session.

    If ``account`` is given, ``db.execute()`` returns a result whose
    ``.scalar_one_or_none()`` yields that account — used by
    ``_reload_balances()`` to fetch fresh paper_balances from DB.
    When ``account`` is None, ``scalar_one_or_none()`` returns None
    so ``_reload_balances()`` keeps the in-memory snapshot.
    """
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.merge = AsyncMock(side_effect=lambda obj: obj)

    # Always wire up execute → scalar_one_or_none properly
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = account  # None when no account
    db.execute = AsyncMock(return_value=result_mock)

    return db


def _make_mock_session_maker(account=None):
    """Create a mock async_session_maker for paper trading tests.

    Returns a callable that yields mock sessions.  When ``account`` is
    provided, ``_reload_balances()`` will pick it up via
    ``scalar_one_or_none()``.  When None, reload keeps in-memory balances
    and save is a silent no-op.
    """
    def factory():
        mock_db = _make_mock_db(account=account)

        @asynccontextmanager
        async def ctx():
            yield mock_db

        return ctx()

    return factory


def _make_shared_session_maker(db_state):
    """Create a session maker tied to a shared ``db_state`` dict.

    ``db_state["balances"]`` is the JSON string representing the DB row.
    ``_reload_balances`` reads it; ``_save_balances`` writes it on commit.
    Used by the concurrent balance safety tests.
    """
    def factory():
        mock_db = AsyncMock()
        captured_account = {}

        async def fake_execute(stmt):
            result = MagicMock()
            fresh_account = MagicMock()
            fresh_account.paper_balances = db_state["balances"]
            captured_account["ref"] = fresh_account
            result.scalar_one_or_none.return_value = fresh_account
            return result

        async def fake_commit():
            if "ref" in captured_account:
                db_state["balances"] = captured_account["ref"].paper_balances

        mock_db.execute = AsyncMock(side_effect=fake_execute)
        mock_db.commit = AsyncMock(side_effect=fake_commit)

        @asynccontextmanager
        async def ctx():
            yield mock_db

        return ctx()

    return factory


@pytest.fixture(autouse=True)
def _patch_session_maker():
    """Prevent _reload/_save from hitting the real database by default."""
    with patch(
        "app.database.async_session_maker",
        _make_mock_session_maker(account=None),
    ):
        yield


def _make_mock_real_client(price=50000.0):
    """Create a mock real exchange client for price data."""
    client = AsyncMock()
    client.get_current_price = AsyncMock(return_value=price)
    client.get_btc_usd_price = AsyncMock(return_value=price)
    client.get_eth_usd_price = AsyncMock(return_value=3000.0)
    client.list_products = AsyncMock(return_value=[])
    client.get_product = AsyncMock(return_value={})
    client.get_ticker = AsyncMock(return_value={})
    client.get_product_stats = AsyncMock(return_value={})
    client.get_candles = AsyncMock(return_value=[])
    client.get_order_book = AsyncMock(return_value={"bids": [], "asks": []})
    client.get_recent_trades = AsyncMock(return_value=[])
    return client


# =========================================================
# Initialization
# =========================================================


class TestPaperTradingClientInit:
    """Tests for PaperTradingClient initialization."""

    def test_init_with_paper_account(self):
        """Happy path: initializes with a paper trading account."""
        account = _make_mock_account(is_paper=True)
        client = PaperTradingClient(account)

        assert client.account is account
        assert client.account_id == account.id
        assert client.is_paper_trading() is True

    def test_init_with_custom_balances(self):
        """Happy path: initializes with custom balances from account."""
        balances = {"BTC": 5.0, "ETH": 50.0, "USD": 50000.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        assert client.balances["BTC"] == 5.0
        assert client.balances["ETH"] == 50.0
        assert client.balances["USD"] == 50000.0

    def test_init_non_paper_account_raises(self):
        """Failure case: non-paper trading account raises ValueError."""
        account = _make_mock_account(is_paper=False)
        db = _make_mock_db()

        with pytest.raises(ValueError, match="paper trading account"):
            PaperTradingClient(account, db)

    def test_init_default_balances_when_none(self):
        """Edge case: no paper_balances on account uses defaults."""
        account = _make_mock_account(paper_balances=None)
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        assert client.balances["BTC"] == 1.0
        assert client.balances["ETH"] == 10.0
        assert client.balances["USD"] == 100000.0


# =========================================================
# place_order
# =========================================================


class TestPlaceOrder:
    """Tests for PaperTradingClient.place_order()"""

    @pytest.mark.asyncio
    async def test_buy_with_funds(self):
        """Happy path: buy ETH with BTC funds."""
        balances = {"BTC": 1.0, "ETH": 0.0, "USD": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=0.05)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.place_order(
            product_id="ETH-BTC",
            side="buy",
            order_type="market",
            funds=0.1,
        )

        assert result["success"] is True
        assert result["status"] == "filled"
        assert result["paper_trading"] is True
        assert result["order_id"].startswith("paper-")
        # 0.1 BTC / 0.05 price = 2.0 ETH
        assert float(result["filled_size"]) == pytest.approx(2.0)
        assert client.balances["BTC"] == pytest.approx(0.9)
        assert client.balances["ETH"] == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_buy_with_size(self):
        """Happy path: buy specific amount of base currency."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=0.05)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.place_order(
            product_id="ETH-BTC",
            side="buy",
            order_type="market",
            size=5.0,
        )

        assert result["success"] is True
        # 5 ETH * 0.05 BTC = 0.25 BTC spent
        assert client.balances["BTC"] == pytest.approx(0.75)
        assert client.balances["ETH"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_sell_with_size(self):
        """Happy path: sell ETH for BTC."""
        balances = {"BTC": 0.0, "ETH": 10.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=0.05)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.place_order(
            product_id="ETH-BTC",
            side="sell",
            order_type="market",
            size=5.0,
        )

        assert result["success"] is True
        # 5 ETH * 0.05 = 0.25 BTC received
        assert client.balances["ETH"] == pytest.approx(5.0)
        assert client.balances["BTC"] == pytest.approx(0.25)

    @pytest.mark.asyncio
    async def test_buy_insufficient_funds_raises(self):
        """Failure case: insufficient quote currency for buy."""
        balances = {"BTC": 0.01, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=0.05)
        client = PaperTradingClient(account, db, real_client=real_client)

        with pytest.raises(Exception, match="Insufficient BTC balance"):
            await client.place_order(
                product_id="ETH-BTC",
                side="buy",
                order_type="market",
                funds=1.0,  # Need 1.0 BTC, only have 0.01
            )

    @pytest.mark.asyncio
    async def test_sell_insufficient_base_raises(self):
        """Failure case: insufficient base currency for sell."""
        balances = {"BTC": 0.0, "ETH": 0.5}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=0.05)
        client = PaperTradingClient(account, db, real_client=real_client)

        with pytest.raises(Exception, match="Insufficient ETH balance"):
            await client.place_order(
                product_id="ETH-BTC",
                side="sell",
                order_type="market",
                size=5.0,  # Need 5 ETH, only have 0.5
            )

    @pytest.mark.asyncio
    async def test_buy_no_size_or_funds_raises(self):
        """Failure case: buy without size or funds raises ValueError."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=0.05)
        client = PaperTradingClient(account, db, real_client=real_client)

        with pytest.raises(ValueError, match="Must specify either size or funds"):
            await client.place_order(
                product_id="ETH-BTC",
                side="buy",
                order_type="market",
            )

    @pytest.mark.asyncio
    async def test_sell_no_size_raises(self):
        """Failure case: sell without size raises ValueError."""
        balances = {"BTC": 0.0, "ETH": 10.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=0.05)
        client = PaperTradingClient(account, db, real_client=real_client)

        with pytest.raises(ValueError, match="Must specify size for sell order"):
            await client.place_order(
                product_id="ETH-BTC",
                side="sell",
                order_type="market",
            )

    @pytest.mark.asyncio
    async def test_price_unavailable_raises(self):
        """Failure case: cannot get price from real exchange."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=None)
        # Return None for price
        real_client.get_current_price = AsyncMock(return_value=None)
        client = PaperTradingClient(account, db, real_client=real_client)

        with pytest.raises(Exception, match="Could not get price"):
            await client.place_order(
                product_id="ETH-BTC",
                side="buy",
                order_type="market",
                funds=0.1,
            )

    @pytest.mark.asyncio
    async def test_order_cache_limit(self):
        """Edge case: order cache prunes oldest entries beyond 100."""
        balances = {"BTC": 100.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=0.05)
        client = PaperTradingClient(account, db, real_client=real_client)

        # Place 101 orders
        for _ in range(101):
            await client.place_order(
                product_id="ETH-BTC",
                side="buy",
                order_type="market",
                funds=0.001,
            )

        # Cache should be pruned to 100
        assert len(client._order_cache) == 100


# =========================================================
# cancel_order
# =========================================================


class TestCancelOrder:
    """Tests for PaperTradingClient.cancel_order()"""

    @pytest.mark.asyncio
    async def test_cancel_always_fails(self):
        """Happy path: paper orders fill instantly, cancel always fails."""
        account = _make_mock_account()
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.cancel_order("paper-abc123")
        assert result["success"] is False
        assert "instantly" in result["error"]


# =========================================================
# get_order
# =========================================================


class TestGetOrder:
    """Tests for PaperTradingClient.get_order()"""

    @pytest.mark.asyncio
    async def test_get_cached_order(self):
        """Happy path: returns cached order data."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=0.05)
        client = PaperTradingClient(account, db, real_client=real_client)

        order = await client.place_order(
            product_id="ETH-BTC",
            side="buy",
            order_type="market",
            funds=0.1,
        )
        order_id = order["order_id"]

        result = await client.get_order(order_id)
        assert result is not None
        assert result["order_id"] == order_id
        assert result["status"] == "filled"

    @pytest.mark.asyncio
    async def test_get_order_not_in_cache(self):
        """Edge case: paper order from previous session returns minimal data."""
        account = _make_mock_account()
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.get_order("paper-old-session-id")
        assert result is not None
        assert result["status"] == "filled"
        assert result["filled_size"] == "0"
        assert result["paper_trading"] is True

    @pytest.mark.asyncio
    async def test_get_order_non_paper_id_returns_none(self):
        """Edge case: non-paper order ID returns None."""
        account = _make_mock_account()
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.get_order("coinbase-order-123")
        assert result is None


# =========================================================
# Balance methods
# =========================================================


class TestBalanceMethods:
    """Tests for paper trading balance-related methods."""

    @pytest.mark.asyncio
    async def test_get_btc_balance(self):
        """Happy path: returns BTC balance."""
        balances = {"BTC": 2.5, "ETH": 10.0, "USD": 100000.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.get_btc_balance()
        assert result == pytest.approx(2.5)

    @pytest.mark.asyncio
    async def test_get_eth_balance(self):
        """Happy path: returns ETH balance."""
        balances = {"BTC": 1.0, "ETH": 15.0, "USD": 50000.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.get_eth_balance()
        assert result == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_get_usd_balance_returns_usd_only(self):
        """Happy path: USD balance returns USD only, not stablecoins."""
        balances = {"BTC": 0.0, "USD": 1000.0, "USDC": 500.0, "USDT": 200.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.get_usd_balance()
        assert result == pytest.approx(1000.0)
        # USDC and USDT are separate
        assert await client.get_usdc_balance() == pytest.approx(500.0)
        assert await client.get_usdt_balance() == pytest.approx(200.0)

    @pytest.mark.asyncio
    async def test_get_balance_specific_currency(self):
        """Happy path: get balance for a specific currency."""
        balances = {"BTC": 0.5, "ETH": 10.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.get_balance("btc")
        assert result["currency"] == "BTC"
        assert result["available"] == "0.5"
        assert result["hold"] == "0.00"

    @pytest.mark.asyncio
    async def test_get_balance_missing_currency_returns_zero(self):
        """Edge case: balance for non-existent currency returns zero."""
        balances = {"BTC": 1.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.get_balance("SOL")
        assert result["currency"] == "SOL"
        assert result["available"] == "0.0"

    @pytest.mark.asyncio
    async def test_get_all_balances_returns_copy(self):
        """Edge case: get_all_balances returns a copy, not the original."""
        balances = {"BTC": 1.0, "ETH": 10.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.get_all_balances()
        result["BTC"] = 999.0  # Modify the copy

        # Original should be unchanged
        assert client.balances["BTC"] == 1.0


# =========================================================
# Aggregate value calculations
# =========================================================


class TestAggregateValues:
    """Tests for aggregate BTC/USD value calculations."""

    @pytest.mark.asyncio
    async def test_calculate_aggregate_btc_value(self):
        """Happy path: calculates total portfolio value in BTC."""
        balances = {"BTC": 1.0, "ETH": 10.0, "USD": 50000.0, "USDC": 0.0, "USDT": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = AsyncMock()

        async def fake_price(product_id):
            return {"ETH-BTC": 0.05}.get(product_id, 0.0)
        real_client.get_current_price = AsyncMock(side_effect=fake_price)
        real_client.get_btc_usd_price = AsyncMock(return_value=50000.0)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.calculate_aggregate_btc_value()
        # 1.0 BTC + (10 ETH * 0.05 BTC/ETH) + (50000 USD / 50000 USD/BTC)
        # = 1.0 + 0.5 + 1.0 = 2.5
        assert result == pytest.approx(2.5)

    @pytest.mark.asyncio
    async def test_calculate_aggregate_usd_value(self):
        """Happy path: calculates total portfolio value in USD."""
        balances = {"BTC": 1.0, "ETH": 10.0, "USD": 10000.0, "USDC": 0.0, "USDT": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = AsyncMock()
        real_client.get_btc_usd_price = AsyncMock(return_value=50000.0)

        async def fake_price(product_id):
            return {"BTC-USD": 50000.0, "ETH-USD": 3000.0}.get(product_id, 0.0)
        real_client.get_current_price = AsyncMock(side_effect=fake_price)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.calculate_aggregate_usd_value()
        # 10000 USD + (1 BTC * 50000) + (10 ETH * 3000)
        # = 10000 + 50000 + 30000 = 90000
        assert result == pytest.approx(90000.0)

    @pytest.mark.asyncio
    async def test_calculate_aggregate_usd_value_includes_altcoins(self):
        """Happy path: altcoin balances are included in USD aggregate value."""
        balances = {
            "USD": 800.0, "USDC": 0.0, "USDT": 0.0,
            "BTC": 0.0, "ETH": 0.0,
            "HBAR": 500.0, "DOT": 10.0, "AMP": 3000.0,
        }
        account = _make_mock_account(paper_balances=balances)
        real_client = AsyncMock()
        real_client.get_btc_usd_price = AsyncMock(return_value=80000.0)
        real_client.get_eth_usd_price = AsyncMock(return_value=3000.0)

        # get_current_price returns different prices per pair
        async def fake_price(product_id):
            prices = {"HBAR-USD": 0.10, "DOT-USD": 5.0, "AMP-USD": 0.005}
            return prices.get(product_id, 0.0)
        real_client.get_current_price = AsyncMock(side_effect=fake_price)

        client = PaperTradingClient(account, real_client=real_client)
        result = await client.calculate_aggregate_usd_value()
        # 800 USD + 500*0.10 HBAR + 10*5.0 DOT + 3000*0.005 AMP
        # = 800 + 50 + 50 + 15 = 915
        assert result == pytest.approx(915.0)

    @pytest.mark.asyncio
    async def test_calculate_aggregate_btc_value_includes_altcoins(self):
        """Happy path: altcoin balances are included in BTC aggregate value."""
        balances = {
            "BTC": 1.0, "ETH": 0.0,
            "USD": 0.0, "USDC": 0.0, "USDT": 0.0,
            "SOL": 5.0,
        }
        account = _make_mock_account(paper_balances=balances)
        real_client = AsyncMock()
        real_client.get_btc_usd_price = AsyncMock(return_value=80000.0)

        async def fake_price(product_id):
            prices = {"SOL-BTC": 0.002}
            return prices.get(product_id, 0.0)
        real_client.get_current_price = AsyncMock(side_effect=fake_price)

        client = PaperTradingClient(account, real_client=real_client)
        result = await client.calculate_aggregate_btc_value()
        # 1.0 BTC + 5*0.002 SOL-BTC = 1.0 + 0.01 = 1.01
        assert result == pytest.approx(1.01)

    @pytest.mark.asyncio
    async def test_aggregate_usd_value_uses_btc_fallback(self):
        """Happy path: coin with no USD pair falls back via BTC → USD."""
        balances = {
            "USD": 1000.0, "USDC": 0.0, "USDT": 0.0,
            "BTC": 0.0, "ETH": 0.0,
            "OBSCURE": 10.0,
        }
        account = _make_mock_account(paper_balances=balances)
        real_client = AsyncMock()
        real_client.get_btc_usd_price = AsyncMock(return_value=80000.0)

        # OBSCURE-USD fails, OBSCURE-BTC works
        async def fake_price(product_id):
            if product_id == "OBSCURE-USD":
                return None  # no direct USD pair
            if product_id == "OBSCURE-BTC":
                return 0.001  # 0.001 BTC per OBSCURE
            return 0.0
        real_client.get_current_price = AsyncMock(side_effect=fake_price)

        client = PaperTradingClient(account, real_client=real_client)
        result = await client.calculate_aggregate_usd_value()
        # 1000 USD + 10 * 0.001 BTC * 80000 USD/BTC = 1000 + 800 = 1800
        assert result == pytest.approx(1800.0)

    @pytest.mark.asyncio
    async def test_aggregate_btc_value_uses_usd_fallback(self):
        """Happy path: coin with no BTC pair falls back via USD → BTC."""
        balances = {
            "BTC": 1.0, "ETH": 0.0,
            "USD": 0.0, "USDC": 0.0, "USDT": 0.0,
            "HBAR": 1000.0,
        }
        account = _make_mock_account(paper_balances=balances)
        real_client = AsyncMock()
        real_client.get_btc_usd_price = AsyncMock(return_value=80000.0)

        # HBAR-BTC fails, HBAR-USD works
        async def fake_price(product_id):
            if product_id == "HBAR-BTC":
                return None
            if product_id == "HBAR-USD":
                return 0.10
            return 0.0
        real_client.get_current_price = AsyncMock(side_effect=fake_price)

        client = PaperTradingClient(account, real_client=real_client)
        result = await client.calculate_aggregate_btc_value()
        # 1.0 BTC + 1000 * 0.10 USD / 80000 USD/BTC = 1.0 + 0.00125 = 1.00125
        assert result == pytest.approx(1.00125)

    @pytest.mark.asyncio
    async def test_aggregate_usd_value_altcoin_price_failure_skipped(self):
        """Edge case: failing altcoin price doesn't break aggregate calculation."""
        balances = {
            "USD": 1000.0, "USDC": 0.0, "USDT": 0.0,
            "BTC": 0.0, "ETH": 0.0,
            "HBAR": 500.0,
        }
        account = _make_mock_account(paper_balances=balances)
        real_client = AsyncMock()
        real_client.get_btc_usd_price = AsyncMock(return_value=80000.0)
        real_client.get_current_price = AsyncMock(side_effect=Exception("No price"))

        client = PaperTradingClient(account, real_client=real_client)
        result = await client.calculate_aggregate_usd_value()
        # HBAR price fails on both paths, but USD balance is still counted
        assert result == pytest.approx(1000.0)

    @pytest.mark.asyncio
    async def test_aggregate_usd_value_skips_dust(self):
        """Edge case: tiny dust balances are skipped (not worth pricing)."""
        balances = {
            "USD": 1000.0, "USDC": 0.0, "USDT": 0.0,
            "BTC": 1e-9, "ETH": 0.0,
            "DASH": 1e-8, "UNI": 1e-6,
        }
        account = _make_mock_account(paper_balances=balances)
        real_client = AsyncMock()
        real_client.get_btc_usd_price = AsyncMock(return_value=80000.0)
        real_client.get_eth_usd_price = AsyncMock(return_value=3000.0)
        # Should NOT be called for dust amounts
        real_client.get_current_price = AsyncMock(return_value=100.0)

        client = PaperTradingClient(account, real_client=real_client)
        result = await client.calculate_aggregate_usd_value()
        assert result == pytest.approx(1000.0, abs=0.01)
        # get_current_price should not be called for dust
        real_client.get_current_price.assert_not_called()

    @pytest.mark.asyncio
    async def test_aggregate_btc_value_price_failure_graceful(self):
        """Edge case: price fetch failure is handled gracefully."""
        balances = {"BTC": 1.0, "USD": 0.0, "USDC": 0.0, "USDT": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = AsyncMock()
        real_client.get_current_price = AsyncMock(side_effect=Exception("Network error"))
        real_client.get_btc_usd_price = AsyncMock(side_effect=Exception("Network error"))
        client = PaperTradingClient(account, db, real_client=real_client)

        # Should still return BTC balance even if price fetches fail
        result = await client.calculate_aggregate_btc_value()
        assert result == pytest.approx(1.0)


# =========================================================
# Account and metadata methods
# =========================================================


class TestAccountAndMetadata:
    """Tests for account listings and metadata."""

    @pytest.mark.asyncio
    async def test_get_accounts_lists_positive_balances(self):
        """Happy path: get_accounts returns accounts for positive balances."""
        balances = {"BTC": 1.0, "ETH": 0.0, "USD": 50000.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.get_accounts()
        currencies = [a["currency"] for a in result]
        assert "BTC" in currencies
        assert "USD" in currencies
        assert "ETH" not in currencies  # Zero balance excluded

    @pytest.mark.asyncio
    async def test_get_account_returns_balances_copy(self):
        """Happy path: get_account returns all balances."""
        balances = {"BTC": 1.0, "ETH": 10.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        client = PaperTradingClient(account, db)

        result = await client.get_account()
        assert result["BTC"] == 1.0
        assert result["ETH"] == 10.0

    def test_get_exchange_type_returns_cex(self):
        """Happy path: paper trading simulates CEX behavior."""
        account = _make_mock_account()
        db = _make_mock_db()
        client = PaperTradingClient(account, db)
        assert client.get_exchange_type() == "cex"

    @pytest.mark.asyncio
    async def test_test_connection_always_true(self):
        """Happy path: paper trading connection always succeeds."""
        account = _make_mock_account()
        db = _make_mock_db()
        client = PaperTradingClient(account, db)
        assert await client.test_connection() is True

    @pytest.mark.asyncio
    async def test_invalidate_balance_cache_is_noop(self):
        """Edge case: invalidate_balance_cache does nothing (no exception)."""
        account = _make_mock_account()
        db = _make_mock_db()
        client = PaperTradingClient(account, db)
        await client.invalidate_balance_cache()  # Should not raise

    @pytest.mark.asyncio
    async def test_list_orders_returns_empty(self):
        """Happy path: paper trading orders fill instantly, no open orders."""
        account = _make_mock_account()
        db = _make_mock_db()
        client = PaperTradingClient(account, db)
        result = await client.list_orders()
        assert result == []


# =========================================================
# Market data delegation
# =========================================================


class TestMarketDataDelegation:
    """Tests for market data methods that delegate to real_client."""

    @pytest.mark.asyncio
    async def test_get_price_delegates_to_real_client(self):
        """Happy path: get_price uses real_client when available."""
        account = _make_mock_account()
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=42000.0)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.get_price("BTC-USD")
        assert result == 42000.0
        real_client.get_current_price.assert_called_once_with("BTC-USD")

    @pytest.mark.asyncio
    async def test_get_price_falls_back_to_public_api(self):
        """Edge case: no real_client, falls back to public API."""
        account = _make_mock_account()
        db = _make_mock_db()
        client = PaperTradingClient(account, db, real_client=None)

        mock_module = MagicMock()
        mock_module.get_current_price = AsyncMock(return_value=45000.0)
        with patch.dict("sys.modules", {"app.coinbase_api": MagicMock(public_market_data=mock_module)}):
            result = await client.get_price("BTC-USD")
            assert result == 45000.0

    @pytest.mark.asyncio
    async def test_get_price_public_api_failure_returns_none(self):
        """Failure case: public API import failure returns None."""
        account = _make_mock_account()
        db = _make_mock_db()
        client = PaperTradingClient(account, db, real_client=None)

        with patch.dict("sys.modules", {"app.coinbase_api": None}):
            result = await client.get_price("BTC-USD")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_candles_with_real_client(self):
        """Happy path: candles delegate to real_client."""
        account = _make_mock_account()
        db = _make_mock_db()
        real_client = _make_mock_real_client()
        real_client.get_candles = AsyncMock(return_value=[{"close": "100"}])
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.get_candles("BTC-USD", 1000, 2000, "ONE_HOUR")
        assert len(result) == 1
        real_client.get_candles.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_order_book_with_real_client(self):
        """Happy path: order book delegates to real_client."""
        account = _make_mock_account()
        db = _make_mock_db()
        real_client = _make_mock_real_client()
        client = PaperTradingClient(account, db, real_client=real_client)

        await client.get_order_book("BTC-USD")
        real_client.get_order_book.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_order_book_no_real_client(self):
        """Edge case: no real_client returns empty order book."""
        account = _make_mock_account()
        db = _make_mock_db()
        client = PaperTradingClient(account, db, real_client=None)

        result = await client.get_order_book("BTC-USD")
        assert result == {"bids": [], "asks": []}


# =========================================================
# create_market_order / create_limit_order wrappers
# =========================================================


class TestOrderWrappers:
    """Tests for create_market_order and create_limit_order."""

    @pytest.mark.asyncio
    async def test_create_market_order_wraps_in_envelope(self):
        """Happy path: create_market_order returns standard envelope format."""
        balances = {"BTC": 0.0, "ETH": 0.0, "USD": 100000.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=50000.0)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.create_market_order(
            product_id="BTC-USD",
            side="buy",
            funds="10000",
        )

        assert result["success"] is True
        assert "success_response" in result
        assert "order_id" in result["success_response"]
        assert result["paper_trading"] is True

    @pytest.mark.asyncio
    async def test_create_limit_order_executes_as_market(self):
        """Happy path: create_limit_order delegates to create_market_order."""
        balances = {"BTC": 0.0, "ETH": 0.0, "USD": 100000.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=50000.0)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.create_limit_order(
            product_id="BTC-USD",
            side="buy",
            limit_price=49000.0,
            funds="10000",
        )

        # Should still succeed (executed as market order)
        assert result["success"] is True
        assert result["paper_trading"] is True

    @pytest.mark.asyncio
    async def test_create_market_order_with_size(self):
        """Happy path: market order with size parameter."""
        balances = {"BTC": 1.0, "ETH": 0.0, "USD": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=50000.0)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.create_market_order(
            product_id="BTC-USD",
            side="sell",
            size="0.5",
        )

        assert result["success"] is True
        assert float(result["filled_size"]) == pytest.approx(0.5)


# =========================================================
# Convenience trading methods
# =========================================================


class TestConvenienceMethods:
    """Tests for convenience trading methods (buy_with_usd, etc.)."""

    @pytest.mark.asyncio
    async def test_buy_with_usd(self):
        """Happy path: buy_with_usd creates market order."""
        balances = {"BTC": 0.0, "USD": 100000.0, "USDC": 0.0, "USDT": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=50000.0)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.buy_with_usd(10000.0, "BTC-USD")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_sell_for_usd(self):
        """Happy path: sell_for_usd creates market order."""
        balances = {"BTC": 1.0, "USD": 0.0, "USDC": 0.0, "USDT": 0.0}
        account = _make_mock_account(paper_balances=balances)
        db = _make_mock_db()
        real_client = _make_mock_real_client(price=50000.0)
        client = PaperTradingClient(account, db, real_client=real_client)

        result = await client.sell_for_usd(0.5, "BTC-USD")
        assert result["success"] is True


# =========================================================
# Concurrent balance safety (race condition fix)
# =========================================================


class TestConcurrentBalanceSafety:
    """Tests for per-account locking and fresh DB reads in place_order.

    These verify that concurrent paper trading clients sharing the same
    account do not silently overwrite each other's balance changes.
    """

    @pytest.fixture(autouse=True)
    def clear_lock_registry(self):
        """Ensure a clean lock registry for each test."""
        _account_balance_locks.clear()
        yield
        _account_balance_locks.clear()

    @pytest.mark.asyncio
    async def test_concurrent_buys_same_account_no_balance_loss(self):
        """Happy path: two concurrent buys on the same account both deduct BTC.

        Simulates two bots buying different alts from the same paper account.
        Without locking, last-writer-wins would silently drop one deduction.
        """
        ACCOUNT_ID = 3
        initial = {"BTC": 1.0, "ETH": 0.0, "UNI": 0.0}
        account = _make_mock_account(paper_balances=initial, account_id=ACCOUNT_ID)

        db_state = {"balances": json.dumps(initial)}
        shared_maker = _make_shared_session_maker(db_state)
        real_client = _make_mock_real_client(price=0.001)  # cheap alts

        with patch("app.database.async_session_maker", shared_maker):
            client1 = PaperTradingClient(account, real_client=real_client)
            client2 = PaperTradingClient(account, real_client=real_client)

            # Run two buys concurrently
            results = await asyncio.gather(
                client1.place_order("ETH-BTC", "buy", "market", funds=0.1),
                client2.place_order("UNI-BTC", "buy", "market", funds=0.2),
            )

        assert results[0]["success"] is True
        assert results[1]["success"] is True

        # Final DB state should reflect BOTH deductions
        final = json.loads(db_state["balances"])
        assert final["BTC"] == pytest.approx(0.7, abs=1e-8)

    @pytest.mark.asyncio
    async def test_concurrent_buy_and_sell_same_account(self):
        """Edge case: concurrent buy + sell produce correct final balances."""
        ACCOUNT_ID = 3
        initial = {"BTC": 1.0, "ETH": 10.0, "UNI": 0.0}
        account = _make_mock_account(paper_balances=initial, account_id=ACCOUNT_ID)

        db_state = {"balances": json.dumps(initial)}
        shared_maker = _make_shared_session_maker(db_state)
        real_client = _make_mock_real_client(price=0.05)  # ETH-BTC

        with patch("app.database.async_session_maker", shared_maker):
            client1 = PaperTradingClient(account, real_client=real_client)
            client2 = PaperTradingClient(account, real_client=real_client)

            # Buy ETH with 0.1 BTC, sell 5 ETH for BTC — concurrently
            results = await asyncio.gather(
                client1.place_order("ETH-BTC", "buy", "market", funds=0.1),
                client2.place_order("ETH-BTC", "sell", "market", size=5.0),
            )

        assert results[0]["success"] is True
        assert results[1]["success"] is True

        final = json.loads(db_state["balances"])
        # BTC: 1.0 - 0.1 (buy) + 0.25 (sell 5 ETH * 0.05) = 1.15
        assert final["BTC"] == pytest.approx(1.15, abs=1e-8)
        # ETH: 10 + 2 (bought 0.1/0.05) - 5 (sold) = 7
        assert final["ETH"] == pytest.approx(7.0, abs=1e-8)

    @pytest.mark.asyncio
    async def test_lock_released_on_insufficient_balance_error(self):
        """Failure case: insufficient funds error still releases the lock.

        If the lock wasn't released, a subsequent order would deadlock.
        """
        ACCOUNT_ID = 3
        initial = {"BTC": 0.01, "ETH": 0.0}
        account = _make_mock_account(paper_balances=initial, account_id=ACCOUNT_ID)

        db_state = {"balances": json.dumps(initial)}
        shared_maker = _make_shared_session_maker(db_state)
        real_client = _make_mock_real_client(price=0.05)

        with patch("app.database.async_session_maker", shared_maker):
            client = PaperTradingClient(account, real_client=real_client)

            # First order fails — insufficient funds
            with pytest.raises(Exception, match="Insufficient BTC"):
                await client.place_order("ETH-BTC", "buy", "market", funds=1.0)

            # Give the account enough funds via shared DB state
            db_state["balances"] = json.dumps({"BTC": 5.0, "ETH": 0.0})

            # Second order should NOT deadlock (lock was released)
            result = await asyncio.wait_for(
                client.place_order("ETH-BTC", "buy", "market", funds=0.1),
                timeout=2.0,  # Would hang forever if lock stuck
            )
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_reload_balances_reads_fresh_from_db(self):
        """Happy path: _reload_balances() picks up externally modified balances.

        After another client modifies the DB, reloading should see the new values.
        """
        ACCOUNT_ID = 3
        initial = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=initial, account_id=ACCOUNT_ID)

        # DB returns different balances than what we initialized with
        modified = {"BTC": 0.5, "ETH": 5.0, "UNI": 100.0}
        db_account = MagicMock()
        db_account.paper_balances = json.dumps(modified)

        client = PaperTradingClient(account, real_client=None)

        # Initially has the stale snapshot
        assert client.balances["BTC"] == 1.0

        # Patch session maker to return modified balances
        with patch(
            "app.database.async_session_maker",
            _make_mock_session_maker(account=db_account),
        ):
            await client._reload_balances()

        assert client.balances["BTC"] == pytest.approx(0.5)
        assert client.balances["ETH"] == pytest.approx(5.0)
        assert client.balances["UNI"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_get_balance_reloads_from_db(self):
        """get_balance() must reload from DB to avoid stale snapshots.

        Regression test for the partial-sell bug: when two bots share a
        paper account, bot B's session could hold a stale transaction
        snapshot from SQLite WAL mode.  get_balance() now acquires the
        per-account lock and calls _reload_balances() to force a fresh
        DB read, ensuring the sell executor sees the true available amount.
        """
        ACCOUNT_ID = 42
        initial = {"BTC": 1.0, "USD": 500.0}
        account = _make_mock_account(paper_balances=initial, account_id=ACCOUNT_ID)

        # Simulate another bot having modified the balance in the DB
        modified = {"BTC": 0.3, "USD": 800.0}
        db_account = MagicMock()
        db_account.paper_balances = json.dumps(modified)

        client = PaperTradingClient(account, real_client=None)

        # In-memory snapshot still shows stale value
        assert client.balances["BTC"] == 1.0

        # get_balance() should reload from DB and return the fresh value
        with patch(
            "app.database.async_session_maker",
            _make_mock_session_maker(account=db_account),
        ):
            result = await client.get_balance("BTC")

        assert result["available"] == "0.3"
        assert result["currency"] == "BTC"

    @pytest.mark.asyncio
    async def test_get_accounts_force_fresh_reloads(self):
        """get_accounts(force_fresh=True) must reload balances from DB."""
        ACCOUNT_ID = 43
        initial = {"ETH": 10.0}
        account = _make_mock_account(paper_balances=initial, account_id=ACCOUNT_ID)

        modified = {"ETH": 7.5, "LINK": 50.0}
        db_account = MagicMock()
        db_account.paper_balances = json.dumps(modified)

        client = PaperTradingClient(account, real_client=None)

        with patch(
            "app.database.async_session_maker",
            _make_mock_session_maker(account=db_account),
        ):
            accounts = await client.get_accounts(force_fresh=True)

        # Should see the refreshed ETH balance
        eth_acc = next(a for a in accounts if a["currency"] == "ETH")
        assert float(eth_acc["available_balance"]["value"]) == pytest.approx(7.5)


# =========================================================
# Slippage simulation (VWAP fills)
# =========================================================


class TestSlippageSimulation:
    """Tests for paper trade slippage simulation via order book VWAP.

    When simulate_slippage_ctx is True and a real_client is available,
    place_order should walk the order book and fill at VWAP instead of
    mid-price.
    """

    @pytest.fixture(autouse=True)
    def _reset_slippage_ctx(self):
        """Reset the context var to False before each test."""
        token = simulate_slippage_ctx.set(False)
        yield
        simulate_slippage_ctx.reset(token)

    def _mock_order_book(self, bids=None, asks=None):
        """Build a mock product_book response in Coinbase format."""
        return {
            "pricebook": {
                "bids": bids or [],
                "asks": asks or [],
            }
        }

    @pytest.mark.asyncio
    async def test_buy_with_funds_uses_vwap_from_asks(self):
        """Happy path: buy with funds fills at ask VWAP, not mid-price."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        real_client = _make_mock_real_client(price=0.050)  # mid-price
        # Order book: 10 ETH at 0.051, 10 ETH at 0.052
        real_client.get_product_book = AsyncMock(return_value=self._mock_order_book(
            asks=[
                {"price": "0.051", "size": "10"},
                {"price": "0.052", "size": "10"},
            ]
        ))
        client = PaperTradingClient(account, real_client=real_client)

        simulate_slippage_ctx.set(True)

        result = await client.place_order(
            product_id="ETH-BTC",
            side="buy",
            order_type="market",
            funds=0.1,
        )

        assert result["success"] is True
        # VWAP for 0.1 BTC across asks:
        # Level 1: 10 ETH * 0.051 = 0.51 BTC available → spend 0.1 BTC → get ~1.9608 ETH
        # All filled at 0.051 (first level has enough)
        # VWAP = 0.051
        vwap = 0.051
        expected_size = 0.1 / vwap
        assert float(result["filled_size"]) == pytest.approx(expected_size, rel=1e-6)
        # Balance should reflect VWAP, not mid-price
        assert client.balances["BTC"] == pytest.approx(0.9, rel=1e-6)
        assert client.balances["ETH"] == pytest.approx(expected_size, rel=1e-6)

    @pytest.mark.asyncio
    async def test_sell_uses_vwap_from_bids(self):
        """Happy path: sell fills at bid VWAP, not mid-price."""
        balances = {"BTC": 0.0, "ETH": 10.0}
        account = _make_mock_account(paper_balances=balances)
        real_client = _make_mock_real_client(price=0.050)  # mid-price
        # Order book: 3 ETH at 0.049, 10 ETH at 0.048
        real_client.get_product_book = AsyncMock(return_value=self._mock_order_book(
            bids=[
                {"price": "0.049", "size": "3"},
                {"price": "0.048", "size": "10"},
            ]
        ))
        client = PaperTradingClient(account, real_client=real_client)

        simulate_slippage_ctx.set(True)

        result = await client.place_order(
            product_id="ETH-BTC",
            side="sell",
            order_type="market",
            size=5.0,
        )

        assert result["success"] is True
        # VWAP: 3 ETH * 0.049 + 2 ETH * 0.048 = 0.147 + 0.096 = 0.243
        # VWAP = 0.243 / 5 = 0.0486
        expected_funds = 3 * 0.049 + 2 * 0.048
        assert client.balances["ETH"] == pytest.approx(5.0)
        assert client.balances["BTC"] == pytest.approx(expected_funds, rel=1e-6)

    @pytest.mark.asyncio
    async def test_buy_with_size_uses_vwap(self):
        """Happy path: buy with size calculates cost at ask VWAP."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        real_client = _make_mock_real_client(price=0.050)
        # 5 ETH at 0.051, 5 ETH at 0.053
        real_client.get_product_book = AsyncMock(return_value=self._mock_order_book(
            asks=[
                {"price": "0.051", "size": "5"},
                {"price": "0.053", "size": "5"},
            ]
        ))
        client = PaperTradingClient(account, real_client=real_client)

        simulate_slippage_ctx.set(True)

        result = await client.place_order(
            product_id="ETH-BTC",
            side="buy",
            order_type="market",
            size=8.0,
        )

        assert result["success"] is True
        # Walk asks to buy 8 ETH:
        # 5 * 0.051 = 0.255, 3 * 0.053 = 0.159
        # total cost = 0.414, VWAP = 0.414 / 8 = 0.05175
        expected_cost = 5 * 0.051 + 3 * 0.053
        assert client.balances["BTC"] == pytest.approx(1.0 - expected_cost, rel=1e-6)
        assert client.balances["ETH"] == pytest.approx(8.0, rel=1e-6)

    @pytest.mark.asyncio
    async def test_slippage_disabled_uses_mid_price(self):
        """Edge case: when simulate_slippage_ctx is False, uses mid-price."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        real_client = _make_mock_real_client(price=0.050)
        real_client.get_product_book = AsyncMock()  # Should not be called
        client = PaperTradingClient(account, real_client=real_client)

        simulate_slippage_ctx.set(False)

        result = await client.place_order(
            product_id="ETH-BTC",
            side="buy",
            order_type="market",
            funds=0.1,
        )

        assert result["success"] is True
        # Mid-price = 0.050, so 0.1 / 0.050 = 2.0 ETH
        assert float(result["filled_size"]) == pytest.approx(2.0)
        real_client.get_product_book.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_book_falls_back_to_mid_price(self):
        """Edge case: empty order book falls back to mid-price."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        real_client = _make_mock_real_client(price=0.050)
        real_client.get_product_book = AsyncMock(return_value=self._mock_order_book())
        client = PaperTradingClient(account, real_client=real_client)

        simulate_slippage_ctx.set(True)

        result = await client.place_order(
            product_id="ETH-BTC",
            side="buy",
            order_type="market",
            funds=0.1,
        )

        assert result["success"] is True
        # Falls back to mid-price: 0.1 / 0.05 = 2.0
        assert float(result["filled_size"]) == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_book_fetch_error_falls_back_to_mid_price(self):
        """Failure case: order book fetch error falls back to mid-price."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        real_client = _make_mock_real_client(price=0.050)
        real_client.get_product_book = AsyncMock(side_effect=Exception("Network timeout"))
        client = PaperTradingClient(account, real_client=real_client)

        simulate_slippage_ctx.set(True)

        result = await client.place_order(
            product_id="ETH-BTC",
            side="buy",
            order_type="market",
            funds=0.1,
        )

        assert result["success"] is True
        assert float(result["filled_size"]) == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_no_real_client_falls_back_to_mid_price(self):
        """Edge case: no real_client skips slippage simulation."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        # Use public API mock for price
        client = PaperTradingClient(account, real_client=None)

        simulate_slippage_ctx.set(True)

        mock_module = MagicMock()
        mock_module.get_current_price = AsyncMock(return_value=0.050)
        with patch.dict(
            "sys.modules",
            {"app.coinbase_api": MagicMock(public_market_data=mock_module)},
        ):
            result = await client.place_order(
                product_id="ETH-BTC",
                side="buy",
                order_type="market",
                funds=0.1,
            )

        assert result["success"] is True
        # No real_client → can't fetch book → mid-price fallback
        assert float(result["filled_size"]) == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_slippage_logged(self):
        """Happy path: slippage percentage is logged."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        real_client = _make_mock_real_client(price=0.050)
        real_client.get_product_book = AsyncMock(return_value=self._mock_order_book(
            asks=[{"price": "0.052", "size": "100"}]
        ))
        client = PaperTradingClient(account, real_client=real_client)

        simulate_slippage_ctx.set(True)

        with patch("app.exchange_clients.paper_trading_client.logger") as mock_logger:
            await client.place_order(
                product_id="ETH-BTC",
                side="buy",
                order_type="market",
                funds=0.1,
            )
            # Should log slippage info
            log_calls = [str(c) for c in mock_logger.info.call_args_list]
            slippage_logged = any("Paper slippage" in c for c in log_calls)
            assert slippage_logged, f"Expected slippage log, got: {log_calls}"

    @pytest.mark.asyncio
    async def test_order_response_contains_vwap_price(self):
        """Happy path: order response price field reflects VWAP, not mid-price."""
        balances = {"BTC": 1.0, "ETH": 0.0}
        account = _make_mock_account(paper_balances=balances)
        real_client = _make_mock_real_client(price=0.050)
        real_client.get_product_book = AsyncMock(return_value=self._mock_order_book(
            asks=[{"price": "0.055", "size": "100"}]
        ))
        client = PaperTradingClient(account, real_client=real_client)

        simulate_slippage_ctx.set(True)

        result = await client.place_order(
            product_id="ETH-BTC",
            side="buy",
            order_type="market",
            funds=0.1,
        )

        # Response price and average_filled_price should be VWAP (0.055)
        assert float(result["price"]) == pytest.approx(0.055, rel=1e-6)
        assert float(result["average_filled_price"]) == pytest.approx(0.055, rel=1e-6)


class TestSessionMakerInjection:
    """
    Verify that PaperTradingClient uses an injected session_maker instead
    of importing app.database.async_session_maker directly.

    This ensures secondary-event-loop callers (e.g., RebalanceMonitor) get
    DB connections from the correct pool (secondary) rather than the main
    loop's pool — which would raise 'Queue is bound to a different event loop'.
    """

    def _make_account(self):
        account = MagicMock(spec=["id", "is_paper_trading", "paper_balances", "user_id"])
        account.id = 42
        account.is_paper_trading = True
        account.paper_balances = json.dumps({"USD": 5000.0, "BTC": 0.5})
        account.user_id = 1
        return account

    def _make_session_maker(self, account=None):
        """Create a session_maker that records calls."""
        calls = []

        def factory():
            calls.append(1)
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            ))
            mock_db.commit = AsyncMock()

            @asynccontextmanager
            async def ctx():
                yield mock_db

            return ctx()

        factory.calls = calls
        return factory

    def test_accepts_session_maker_parameter(self):
        """Happy path: PaperTradingClient accepts a session_maker kwarg."""
        account = self._make_account()
        sm = self._make_session_maker()
        client = PaperTradingClient(account=account, session_maker=sm)
        assert client._session_maker is sm

    def test_defaults_to_none_without_injection(self):
        """Edge case: no session_maker → _session_maker is None (falls back to global)."""
        account = self._make_account()
        client = PaperTradingClient(account=account)
        assert client._session_maker is None

    @pytest.mark.asyncio
    async def test_reload_balances_uses_injected_session_maker(self):
        """_reload_balances calls the injected session_maker, not the global one."""
        account = self._make_account()
        sm = self._make_session_maker(account)

        fresh_account = MagicMock()
        fresh_account.paper_balances = json.dumps({"USD": 9999.0})

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fresh_account

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def ctx():
            yield mock_db

        def injected_sm():
            return ctx()

        injected_sm.called = []

        original_ctx = ctx

        def counting_sm():
            injected_sm.called.append(1)
            return original_ctx()

        client = PaperTradingClient(account=account, session_maker=counting_sm)

        with patch("app.database.async_session_maker") as global_sm:
            await client._reload_balances()
            global_sm.assert_not_called()

        assert injected_sm.called  # injected sm was used

    @pytest.mark.asyncio
    async def test_calculate_aggregate_quote_value_uses_injected_session_maker(self):
        """calculate_aggregate_quote_value uses injected session_maker, not global."""
        account = self._make_account()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []  # No open positions

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        injected_calls = []

        @asynccontextmanager
        async def ctx():
            yield mock_db

        def injected_sm():
            injected_calls.append(1)
            return ctx()

        client = PaperTradingClient(account=account, session_maker=injected_sm)

        with patch("app.database.async_session_maker") as global_sm:
            result = await client.calculate_aggregate_quote_value("USD")
            global_sm.assert_not_called()

        assert injected_calls, "injected session_maker was not called"
        assert result == 5000.0  # Just the balance, no positions
