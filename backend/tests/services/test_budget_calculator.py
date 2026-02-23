"""
Tests for backend/app/services/budget_calculator.py

Tests available USD/BTC calculation after bidirectional bot reservations,
and validation of bidirectional budget sufficiency.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Account, Bot, User
from app.services.budget_calculator import (
    calculate_available_usd,
    calculate_available_btc,
    validate_bidirectional_budget,
)


async def _create_account_and_user(db_session, email="budget@test.com"):
    """Helper to create a User and CEX Account."""
    user = User(email=email, hashed_password="hash", is_active=True)
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id, name="TestAccount", type="cex",
        is_active=True, is_default=True,
    )
    db_session.add(account)
    await db_session.flush()
    return user, account


class TestCalculateAvailableUsd:
    """Tests for calculate_available_usd()."""

    @pytest.mark.asyncio
    async def test_no_account_id_returns_raw(self, db_session):
        """Edge case: missing account_id returns raw balance unchanged."""
        result = await calculate_available_usd(
            db_session, raw_usd_balance=5000.0, current_btc_price=50000.0,
            account_id=None,
        )
        assert result == 5000.0

    @pytest.mark.asyncio
    async def test_no_bidirectional_bots_returns_full_balance(self, db_session):
        """Happy path: no bidirectional bots means full balance available."""
        user, account = await _create_account_and_user(db_session)

        result = await calculate_available_usd(
            db_session, raw_usd_balance=10000.0, current_btc_price=50000.0,
            account_id=account.id,
        )
        assert result == 10000.0

    @pytest.mark.asyncio
    async def test_reserves_subtracted(self, db_session):
        """Happy path: bidirectional bot reservations are subtracted."""
        user, account = await _create_account_and_user(db_session, email="reserve@test.com")

        bot = Bot(
            user_id=user.id, account_id=account.id,
            name="BiDi Bot", strategy_type="dca_grid",
            strategy_config={"enable_bidirectional": "true"},
            is_active=True, reserved_usd_for_longs=3000.0,
            reserved_btc_for_shorts=0.0,
        )
        db_session.add(bot)
        await db_session.flush()

        # Mock the method on the bot instance since it needs positions
        with patch.object(Bot, "get_total_reserved_usd", return_value=3000.0):
            result = await calculate_available_usd(
                db_session, raw_usd_balance=10000.0, current_btc_price=50000.0,
                account_id=account.id,
            )
        assert result == pytest.approx(7000.0)

    @pytest.mark.asyncio
    async def test_clamps_at_zero(self, db_session):
        """Edge case: available cannot go below zero."""
        user, account = await _create_account_and_user(db_session, email="clamp@test.com")

        bot = Bot(
            user_id=user.id, account_id=account.id,
            name="Heavy Bot", strategy_type="dca_grid",
            strategy_config={"enable_bidirectional": "true"},
            is_active=True, reserved_usd_for_longs=20000.0,
            reserved_btc_for_shorts=0.0,
        )
        db_session.add(bot)
        await db_session.flush()

        with patch.object(Bot, "get_total_reserved_usd", return_value=20000.0):
            result = await calculate_available_usd(
                db_session, raw_usd_balance=5000.0, current_btc_price=50000.0,
                account_id=account.id,
            )
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_exclude_bot_id(self, db_session):
        """Happy path: excluded bot's reservation is not counted."""
        user, account = await _create_account_and_user(db_session, email="exclude@test.com")

        bot = Bot(
            user_id=user.id, account_id=account.id,
            name="Excluded Bot", strategy_type="dca_grid",
            strategy_config={"enable_bidirectional": "true"},
            is_active=True, reserved_usd_for_longs=5000.0,
            reserved_btc_for_shorts=0.0,
        )
        db_session.add(bot)
        await db_session.flush()

        result = await calculate_available_usd(
            db_session, raw_usd_balance=10000.0, current_btc_price=50000.0,
            account_id=account.id, exclude_bot_id=bot.id,
        )
        # Bot is excluded so its reservation not counted
        assert result == 10000.0


class TestCalculateAvailableBtc:
    """Tests for calculate_available_btc()."""

    @pytest.mark.asyncio
    async def test_no_account_id_returns_raw(self, db_session):
        """Edge case: missing account_id returns raw balance unchanged."""
        result = await calculate_available_btc(
            db_session, raw_btc_balance=1.0, current_btc_price=50000.0,
            account_id=None,
        )
        assert result == 1.0

    @pytest.mark.asyncio
    async def test_no_bidirectional_bots_returns_full_balance(self, db_session):
        """Happy path: no bidirectional bots means full BTC available."""
        user, account = await _create_account_and_user(db_session, email="btc@test.com")

        result = await calculate_available_btc(
            db_session, raw_btc_balance=2.0, current_btc_price=50000.0,
            account_id=account.id,
        )
        assert result == 2.0

    @pytest.mark.asyncio
    async def test_reserves_subtracted_btc(self, db_session):
        """Happy path: bidirectional bot BTC reservations subtracted."""
        user, account = await _create_account_and_user(db_session, email="btcres@test.com")

        bot = Bot(
            user_id=user.id, account_id=account.id,
            name="Short Bot", strategy_type="dca_grid",
            strategy_config={"enable_bidirectional": "true"},
            is_active=True, reserved_btc_for_shorts=0.5,
            reserved_usd_for_longs=0.0,
        )
        db_session.add(bot)
        await db_session.flush()

        with patch.object(Bot, "get_total_reserved_btc", return_value=0.5):
            result = await calculate_available_btc(
                db_session, raw_btc_balance=2.0, current_btc_price=50000.0,
                account_id=account.id,
            )
        assert result == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_clamps_btc_at_zero(self, db_session):
        """Edge case: available BTC cannot go below zero."""
        user, account = await _create_account_and_user(db_session, email="btcclamp@test.com")

        bot = Bot(
            user_id=user.id, account_id=account.id,
            name="Overcommit Bot", strategy_type="dca_grid",
            strategy_config={"enable_bidirectional": "true"},
            is_active=True, reserved_btc_for_shorts=5.0,
            reserved_usd_for_longs=0.0,
        )
        db_session.add(bot)
        await db_session.flush()

        with patch.object(Bot, "get_total_reserved_btc", return_value=5.0):
            result = await calculate_available_btc(
                db_session, raw_btc_balance=1.0, current_btc_price=50000.0,
                account_id=account.id,
            )
        assert result == 0.0


class TestValidateBidirectionalBudget:
    """Tests for validate_bidirectional_budget()."""

    @pytest.mark.asyncio
    @patch("app.services.budget_calculator.calculate_available_btc")
    @patch("app.services.budget_calculator.calculate_available_usd")
    @patch("app.services.exchange_service.get_exchange_client_for_account")
    async def test_valid_budget(self, mock_get_exchange, mock_avail_usd, mock_avail_btc, db_session):
        """Happy path: sufficient funds returns (True, '')."""
        mock_exchange = AsyncMock()
        mock_exchange.get_account = AsyncMock(return_value={
            "USD": 10000.0, "USDC": 0.0, "USDT": 0.0, "BTC": 1.0,
        })
        mock_get_exchange.return_value = mock_exchange
        mock_avail_usd.return_value = 8000.0
        mock_avail_btc.return_value = 0.8

        bot = MagicMock()
        bot.account_id = 1
        bot.id = 1

        is_valid, msg = await validate_bidirectional_budget(
            db_session, bot,
            required_usd=5000.0, required_btc=0.5,
            current_btc_price=50000.0,
        )
        assert is_valid is True
        assert msg == ""

    @pytest.mark.asyncio
    @patch("app.services.budget_calculator.calculate_available_btc")
    @patch("app.services.budget_calculator.calculate_available_usd")
    @patch("app.services.exchange_service.get_exchange_client_for_account")
    async def test_insufficient_usd(self, mock_get_exchange, mock_avail_usd, mock_avail_btc, db_session):
        """Failure: insufficient USD for long side."""
        mock_exchange = AsyncMock()
        mock_exchange.get_account = AsyncMock(return_value={
            "USD": 1000.0, "USDC": 0.0, "USDT": 0.0, "BTC": 1.0,
        })
        mock_get_exchange.return_value = mock_exchange
        mock_avail_usd.return_value = 500.0
        mock_avail_btc.return_value = 1.0

        bot = MagicMock()
        bot.account_id = 1
        bot.id = 1

        is_valid, msg = await validate_bidirectional_budget(
            db_session, bot,
            required_usd=5000.0, required_btc=0.1,
            current_btc_price=50000.0,
        )
        assert is_valid is False
        assert "Insufficient USD" in msg

    @pytest.mark.asyncio
    @patch("app.services.budget_calculator.calculate_available_btc")
    @patch("app.services.budget_calculator.calculate_available_usd")
    @patch("app.services.exchange_service.get_exchange_client_for_account")
    async def test_insufficient_btc(self, mock_get_exchange, mock_avail_usd, mock_avail_btc, db_session):
        """Failure: insufficient BTC for short side."""
        mock_exchange = AsyncMock()
        mock_exchange.get_account = AsyncMock(return_value={
            "USD": 10000.0, "USDC": 0.0, "USDT": 0.0, "BTC": 0.01,
        })
        mock_get_exchange.return_value = mock_exchange
        mock_avail_usd.return_value = 10000.0
        mock_avail_btc.return_value = 0.01

        bot = MagicMock()
        bot.account_id = 1
        bot.id = 1

        is_valid, msg = await validate_bidirectional_budget(
            db_session, bot,
            required_usd=1000.0, required_btc=0.5,
            current_btc_price=50000.0,
        )
        assert is_valid is False
        assert "Insufficient BTC" in msg

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.get_exchange_client_for_account")
    async def test_no_exchange_client(self, mock_get_exchange, db_session):
        """Failure: no exchange client returns (False, error)."""
        mock_get_exchange.return_value = None

        bot = MagicMock()
        bot.account_id = 1
        bot.id = 1

        is_valid, msg = await validate_bidirectional_budget(
            db_session, bot,
            required_usd=1000.0, required_btc=0.1,
            current_btc_price=50000.0,
        )
        assert is_valid is False
        assert "No exchange client" in msg

    @pytest.mark.asyncio
    @patch("app.services.exchange_service.get_exchange_client_for_account")
    async def test_exchange_connection_error(self, mock_get_exchange, db_session):
        """Failure: exchange connection error returns (False, error)."""
        mock_get_exchange.side_effect = Exception("Connection refused")

        bot = MagicMock()
        bot.account_id = 1
        bot.id = 1

        is_valid, msg = await validate_bidirectional_budget(
            db_session, bot,
            required_usd=1000.0, required_btc=0.1,
            current_btc_price=50000.0,
        )
        assert is_valid is False
        assert "Failed to connect" in msg
