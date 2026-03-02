"""
Tests for backend/app/bot_routers/bot_crud_router.py

Covers bot CRUD operations: create, read, update, delete, clone,
copy-to-account, stats, and strategy listing endpoints.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Account, Bot, Position, User


# =============================================================================
# Helpers
# =============================================================================


def _make_user(db_session, email="crud@example.com"):
    """Create and flush a test user."""
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=datetime.utcnow(),
    )
    return user


async def _make_bot(db_session, user, name="TestBot", strategy_type="grid_trading",
                    product_id="ETH-BTC", is_active=False, strategy_config=None):
    """Create, flush, and return a test bot."""
    bot = Bot(
        user_id=user.id,
        name=name,
        strategy_type=strategy_type,
        strategy_config=strategy_config or {"upper_price": 1.0, "lower_price": 0.5, "grid_levels": 5},
        product_id=product_id,
        product_ids=[product_id],
        is_active=is_active,
        budget_percentage=5.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


# =============================================================================
# GET /bots/strategies
# =============================================================================


class TestListStrategies:
    """Tests for GET /bots/strategies"""

    @pytest.mark.asyncio
    async def test_list_strategies_returns_list(self):
        """Happy path: returns a list of registered strategies."""
        from app.bot_routers.bot_crud_router import list_strategies

        user = MagicMock(spec=User)
        result = await list_strategies(current_user=user)
        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_list_strategies_contains_grid_trading(self):
        """Happy path: grid_trading strategy is registered."""
        from app.bot_routers.bot_crud_router import list_strategies

        user = MagicMock(spec=User)
        result = await list_strategies(current_user=user)
        ids = [s.id for s in result]
        assert "grid_trading" in ids


class TestGetStrategyDefinition:
    """Tests for GET /bots/strategies/{strategy_id}"""

    @pytest.mark.asyncio
    async def test_get_existing_strategy(self):
        """Happy path: returns strategy definition for known strategy."""
        from app.bot_routers.bot_crud_router import get_strategy_definition

        user = MagicMock(spec=User)
        result = await get_strategy_definition(strategy_id="grid_trading", current_user=user)
        assert result.id == "grid_trading"
        assert result.name is not None

    @pytest.mark.asyncio
    async def test_get_unknown_strategy_returns_404(self):
        """Failure: unknown strategy_id raises 404."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import get_strategy_definition

        user = MagicMock(spec=User)
        with pytest.raises(HTTPException) as exc_info:
            await get_strategy_definition(strategy_id="nonexistent_strategy", current_user=user)
        assert exc_info.value.status_code == 404


# =============================================================================
# POST /bots/ (create)
# =============================================================================


class TestCreateBot:
    """Tests for POST /bots/"""

    @pytest.mark.asyncio
    @patch("app.strategies.StrategyRegistry.get_strategy")
    @patch("app.services.bot_validation_service.validate_bidirectional_budget_config", new_callable=AsyncMock)
    @patch("app.services.bot_validation_service.auto_correct_market_focus")
    @patch("app.services.bot_validation_service.validate_quote_currency", return_value="BTC")
    async def test_create_bot_success(
        self, mock_validate_quote, mock_auto_correct, mock_bidir, mock_get_strategy, db_session
    ):
        """Happy path: creates a new bot with valid data."""
        from app.bot_routers.bot_crud_router import create_bot
        from app.bot_routers.schemas import BotCreate

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        bot_data = BotCreate(
            name="My New Bot",
            strategy_type="grid_trading",
            strategy_config={"upper_limit": 1.0, "lower_limit": 0.5, "grid_levels": 5},
            product_id="ETH-BTC",
            product_ids=["ETH-BTC"],
        )

        result = await create_bot(bot_data=bot_data, db=db_session, current_user=user)
        assert result.name == "My New Bot"
        assert result.strategy_type == "grid_trading"
        assert result.is_active is False
        assert result.open_positions_count == 0

    @pytest.mark.asyncio
    async def test_create_bot_unknown_strategy_returns_400(self, db_session):
        """Failure: unknown strategy_type returns 400."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import create_bot
        from app.bot_routers.schemas import BotCreate

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        bot_data = BotCreate(
            name="Bad Strategy Bot",
            strategy_type="totally_fake_strategy",
            strategy_config={},
            product_id="ETH-BTC",
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_bot(bot_data=bot_data, db=db_session, current_user=user)
        assert exc_info.value.status_code == 400
        assert "Unknown strategy" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.strategies.StrategyRegistry.get_strategy")
    @patch("app.services.bot_validation_service.validate_bidirectional_budget_config", new_callable=AsyncMock)
    @patch("app.services.bot_validation_service.auto_correct_market_focus")
    @patch("app.services.bot_validation_service.validate_quote_currency", return_value="BTC")
    async def test_create_bot_duplicate_name_returns_400(
        self, mock_validate_quote, mock_auto_correct, mock_bidir, mock_get_strategy, db_session
    ):
        """Failure: duplicate bot name for same user returns 400."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import create_bot
        from app.bot_routers.schemas import BotCreate

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        # Create first bot
        bot = Bot(
            user_id=user.id,
            name="Duplicate Name",
            strategy_type="grid_trading",
            strategy_config={"upper_limit": 1.0, "lower_limit": 0.5, "grid_levels": 5},
            product_id="ETH-BTC",
            product_ids=["ETH-BTC"],
            is_active=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(bot)
        await db_session.flush()

        bot_data = BotCreate(
            name="Duplicate Name",
            strategy_type="grid_trading",
            strategy_config={"upper_limit": 1.0, "lower_limit": 0.5, "grid_levels": 5},
            product_id="ETH-BTC",
            product_ids=["ETH-BTC"],
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_bot(bot_data=bot_data, db=db_session, current_user=user)
        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.detail


# =============================================================================
# GET /bots/{bot_id}
# =============================================================================


class TestGetBot:
    """Tests for GET /bots/{bot_id}"""

    @pytest.mark.asyncio
    async def test_get_existing_bot(self, db_session):
        """Happy path: returns bot details for valid bot_id."""
        from app.bot_routers.bot_crud_router import get_bot

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()
        bot = await _make_bot(db_session, user)

        result = await get_bot(bot_id=bot.id, db=db_session, current_user=user)
        assert result.id == bot.id
        assert result.name == "TestBot"

    @pytest.mark.asyncio
    async def test_get_nonexistent_bot_returns_404(self, db_session):
        """Failure: non-existent bot_id returns 404."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import get_bot

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_bot(bot_id=99999, db=db_session, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_bot_belonging_to_other_user_returns_404(self, db_session):
        """Security: user cannot see another user's bot."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import get_bot

        user1 = _make_user(db_session, email="user1@example.com")
        user2 = _make_user(db_session, email="user2@example.com")
        db_session.add_all([user1, user2])
        await db_session.flush()

        bot = await _make_bot(db_session, user1, name="User1Bot")

        with pytest.raises(HTTPException) as exc_info:
            await get_bot(bot_id=bot.id, db=db_session, current_user=user2)
        assert exc_info.value.status_code == 404


# =============================================================================
# GET /bots/ (list)
# =============================================================================


class TestListBots:
    """Tests for GET /bots/"""

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_crud_router.get_coinbase_from_db", new_callable=AsyncMock, return_value=None)
    async def test_list_bots_empty(self, mock_coinbase, db_session):
        """Happy path: returns empty list when user has no bots."""
        from app.bot_routers.bot_crud_router import list_bots

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        result = await list_bots(db=db_session, current_user=user)
        assert result == []

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_crud_router.get_coinbase_from_db", new_callable=AsyncMock, return_value=None)
    async def test_list_bots_returns_user_bots(self, mock_coinbase, db_session):
        """Happy path: returns bots for current user only."""
        from app.bot_routers.bot_crud_router import list_bots

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        await _make_bot(db_session, user, name="Bot1")
        await _make_bot(db_session, user, name="Bot2")

        result = await list_bots(db=db_session, current_user=user)
        assert len(result) == 2

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_crud_router.get_coinbase_from_db", new_callable=AsyncMock, return_value=None)
    async def test_list_bots_active_only_filter(self, mock_coinbase, db_session):
        """Edge case: active_only=True filters inactive bots."""
        from app.bot_routers.bot_crud_router import list_bots

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        await _make_bot(db_session, user, name="ActiveBot", is_active=True)
        await _make_bot(db_session, user, name="InactiveBot", is_active=False)

        result = await list_bots(active_only=True, db=db_session, current_user=user)
        assert len(result) == 1
        assert result[0].name == "ActiveBot"

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_crud_router.get_coinbase_from_db", new_callable=AsyncMock, return_value=None)
    async def test_list_bots_does_not_leak_other_user_bots(self, mock_coinbase, db_session):
        """Security: user does not see other users' bots."""
        from app.bot_routers.bot_crud_router import list_bots

        user1 = _make_user(db_session, email="listuser1@example.com")
        user2 = _make_user(db_session, email="listuser2@example.com")
        db_session.add_all([user1, user2])
        await db_session.flush()

        await _make_bot(db_session, user1, name="User1OnlyBot")

        result = await list_bots(db=db_session, current_user=user2)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_bots_paper_only_user_gets_stats(self, db_session):
        """Happy path: paper-only user (no real CEX) gets PnL/win rate stats."""
        from app.bot_routers.bot_crud_router import list_bots
        from app.exceptions import ExchangeUnavailableError

        user = _make_user(db_session, email="demo_paper@example.com")
        db_session.add(user)
        await db_session.flush()

        # Create paper trading account
        paper_account = Account(
            user_id=user.id, name="Paper Account", type="cex",
            is_active=True, is_paper_trading=True,
        )
        db_session.add(paper_account)
        await db_session.flush()

        bot = await _make_bot(db_session, user, name="PaperBot")
        bot.account_id = paper_account.id
        await db_session.flush()

        # Add closed positions with profit data
        pos1 = Position(
            bot_id=bot.id, user_id=user.id, product_id="ETH-BTC",
            account_id=paper_account.id, status="closed",
            profit_quote=0.02, profit_usd=2000.0,
            initial_quote_balance=1.0, max_quote_allowed=0.25,
        )
        pos2 = Position(
            bot_id=bot.id, user_id=user.id, product_id="ETH-BTC",
            account_id=paper_account.id, status="closed",
            profit_quote=-0.005, profit_usd=-500.0,
            initial_quote_balance=1.0, max_quote_allowed=0.25,
        )
        db_session.add_all([pos1, pos2])
        await db_session.flush()

        # Mock: get_coinbase_from_db raises (no real CEX account)
        # Mock: get_exchange_client_for_account returns a mock paper client
        mock_paper_client = AsyncMock()
        mock_paper_client.calculate_aggregate_btc_value = AsyncMock(return_value=0.5)
        mock_paper_client.calculate_aggregate_usd_value = AsyncMock(return_value=50000.0)
        mock_paper_client.get_current_price = AsyncMock(return_value=0.04)

        with patch(
            "app.bot_routers.bot_crud_router.get_coinbase_from_db",
            new_callable=AsyncMock, side_effect=ExchangeUnavailableError("No CEX")
        ), patch(
            "app.bot_routers.bot_crud_router.get_exchange_client_for_account",
            new_callable=AsyncMock, return_value=mock_paper_client
        ):
            result = await list_bots(db=db_session, current_user=user)

        assert len(result) == 1
        bot_resp = result[0]
        # Stats should be populated, not zero
        assert bot_resp.win_rate == pytest.approx(50.0)
        assert bot_resp.total_pnl_btc == pytest.approx(0.015)
        assert bot_resp.closed_positions_count == 2

    @pytest.mark.asyncio
    async def test_list_bots_no_accounts_at_all_returns_basic_response(self, db_session):
        """Edge case: user with no accounts at all still gets position counts."""
        from app.bot_routers.bot_crud_router import list_bots
        from app.exceptions import ExchangeUnavailableError

        user = _make_user(db_session, email="no_accounts@example.com")
        db_session.add(user)
        await db_session.flush()

        await _make_bot(db_session, user, name="OrphanBot")

        with patch(
            "app.bot_routers.bot_crud_router.get_coinbase_from_db",
            new_callable=AsyncMock, side_effect=ExchangeUnavailableError("No CEX")
        ), patch(
            "app.bot_routers.bot_crud_router.get_exchange_client_for_account",
            new_callable=AsyncMock, return_value=None
        ):
            result = await list_bots(db=db_session, current_user=user)

        assert len(result) == 1
        assert result[0].open_positions_count == 0
        assert result[0].total_positions_count == 0


# =============================================================================
# PUT /bots/{bot_id}
# =============================================================================


class TestUpdateBot:
    """Tests for PUT /bots/{bot_id}"""

    @pytest.mark.asyncio
    @patch("app.services.bot_validation_service.validate_bidirectional_budget_config", new_callable=AsyncMock)
    @patch("app.services.bot_validation_service.auto_correct_market_focus")
    @patch("app.services.bot_validation_service.validate_quote_currency", return_value="BTC")
    async def test_update_bot_name(
        self, mock_validate_quote, mock_auto_correct, mock_bidir, db_session
    ):
        """Happy path: bot name is updated."""
        from app.bot_routers.bot_crud_router import update_bot
        from app.bot_routers.schemas import BotUpdate

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()
        bot = await _make_bot(db_session, user)

        update_data = BotUpdate(name="Renamed Bot")
        result = await update_bot(
            bot_id=bot.id, bot_update=update_data, db=db_session, current_user=user
        )
        assert result.name == "Renamed Bot"

    @pytest.mark.asyncio
    async def test_update_nonexistent_bot_returns_404(self, db_session):
        """Failure: updating non-existent bot returns 404."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import update_bot
        from app.bot_routers.schemas import BotUpdate

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await update_bot(
                bot_id=99999, bot_update=BotUpdate(name="X"),
                db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.services.bot_validation_service.validate_bidirectional_budget_config", new_callable=AsyncMock)
    @patch("app.services.bot_validation_service.auto_correct_market_focus")
    @patch("app.services.bot_validation_service.validate_quote_currency", return_value="BTC")
    async def test_update_bot_duplicate_name_returns_400(
        self, mock_validate_quote, mock_auto_correct, mock_bidir, db_session
    ):
        """Failure: renaming bot to existing name returns 400."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import update_bot
        from app.bot_routers.schemas import BotUpdate

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        await _make_bot(db_session, user, name="ExistingName")
        bot2 = await _make_bot(db_session, user, name="OtherBot")

        with pytest.raises(HTTPException) as exc_info:
            await update_bot(
                bot_id=bot2.id, bot_update=BotUpdate(name="ExistingName"),
                db=db_session, current_user=user
            )
        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.services.bot_validation_service.validate_bidirectional_budget_config", new_callable=AsyncMock)
    @patch("app.services.bot_validation_service.auto_correct_market_focus")
    @patch("app.services.bot_validation_service.validate_quote_currency", return_value="BTC")
    async def test_update_bot_invalid_strategy_config_returns_400(
        self, mock_validate_quote, mock_auto_correct, mock_bidir, db_session
    ):
        """Failure: invalid strategy config returns 400."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import update_bot
        from app.bot_routers.schemas import BotUpdate

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()
        bot = await _make_bot(db_session, user)

        # grid_trading validates config; pass something that triggers ValueError
        with patch(
            "app.bot_routers.bot_crud_router.StrategyRegistry.get_strategy",
            side_effect=ValueError("bad config"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_bot(
                    bot_id=bot.id,
                    bot_update=BotUpdate(strategy_config={"bad": True}),
                    db=db_session, current_user=user,
                )
            assert exc_info.value.status_code == 400


# =============================================================================
# DELETE /bots/{bot_id}
# =============================================================================


class TestDeleteBot:
    """Tests for DELETE /bots/{bot_id}"""

    @pytest.mark.asyncio
    async def test_delete_bot_success(self, db_session):
        """Happy path: deletes a bot with no open positions."""
        from app.bot_routers.bot_crud_router import delete_bot

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()
        bot = await _make_bot(db_session, user)

        result = await delete_bot(bot_id=bot.id, db=db_session, current_user=user)
        assert "deleted successfully" in result["message"]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_bot_returns_404(self, db_session):
        """Failure: deleting non-existent bot returns 404."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import delete_bot

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await delete_bot(bot_id=99999, db=db_session, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_bot_with_open_positions_returns_400(self, db_session):
        """Failure: cannot delete bot that has open positions."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import delete_bot

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()
        bot = await _make_bot(db_session, user)

        # Add an open position
        position = Position(
            bot_id=bot.id,
            user_id=user.id,
            product_id="ETH-BTC",
            status="open",
            initial_quote_balance=1.0,
            max_quote_allowed=0.25,
        )
        db_session.add(position)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await delete_bot(bot_id=bot.id, db=db_session, current_user=user)
        assert exc_info.value.status_code == 400
        assert "open positions" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_delete_bot_other_user_returns_404(self, db_session):
        """Security: user cannot delete another user's bot."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import delete_bot

        user1 = _make_user(db_session, email="deluser1@example.com")
        user2 = _make_user(db_session, email="deluser2@example.com")
        db_session.add_all([user1, user2])
        await db_session.flush()
        bot = await _make_bot(db_session, user1, name="User1Bot")

        with pytest.raises(HTTPException) as exc_info:
            await delete_bot(bot_id=bot.id, db=db_session, current_user=user2)
        assert exc_info.value.status_code == 404


# =============================================================================
# POST /bots/{bot_id}/clone
# =============================================================================


class TestCloneBot:
    """Tests for POST /bots/{bot_id}/clone"""

    @pytest.mark.asyncio
    async def test_clone_bot_success(self, db_session):
        """Happy path: clones bot with (Copy) suffix."""
        from app.bot_routers.bot_crud_router import clone_bot

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()
        bot = await _make_bot(db_session, user, name="Original Bot")

        result = await clone_bot(bot_id=bot.id, db=db_session, current_user=user)
        assert result.name == "Original Bot (Copy)"
        assert result.is_active is False
        assert result.strategy_type == bot.strategy_type

    @pytest.mark.asyncio
    async def test_clone_nonexistent_bot_returns_404(self, db_session):
        """Failure: cloning non-existent bot returns 404."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import clone_bot

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await clone_bot(bot_id=99999, db=db_session, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_clone_already_copied_bot_increments_number(self, db_session):
        """Edge case: cloning a (Copy) bot produces (Copy 2)."""
        from app.bot_routers.bot_crud_router import clone_bot

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()
        bot = await _make_bot(db_session, user, name="My Bot (Copy)")

        result = await clone_bot(bot_id=bot.id, db=db_session, current_user=user)
        assert result.name == "My Bot (Copy 2)"


# =============================================================================
# POST /bots/{bot_id}/copy-to-account
# =============================================================================


class TestCopyBotToAccount:
    """Tests for POST /bots/{bot_id}/copy-to-account"""

    @pytest.mark.asyncio
    async def test_copy_to_paper_account(self, db_session):
        """Happy path: copies bot to paper trading account with (Paper) suffix."""
        from app.bot_routers.bot_crud_router import copy_bot_to_account

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        source_account = Account(
            user_id=user.id, name="Live", type="cex", is_active=True,
            is_paper_trading=False,
        )
        paper_account = Account(
            user_id=user.id, name="Paper", type="cex", is_active=True,
            is_paper_trading=True,
        )
        db_session.add_all([source_account, paper_account])
        await db_session.flush()

        bot = await _make_bot(db_session, user, name="Live Bot")
        bot.account_id = source_account.id
        await db_session.flush()

        result = await copy_bot_to_account(
            bot_id=bot.id, target_account_id=paper_account.id,
            db=db_session, current_user=user,
        )
        assert "(Paper)" in result.name
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_copy_to_nonexistent_account_returns_404(self, db_session):
        """Failure: copying to non-existent account returns 404."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import copy_bot_to_account

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()
        bot = await _make_bot(db_session, user)

        with pytest.raises(HTTPException) as exc_info:
            await copy_bot_to_account(
                bot_id=bot.id, target_account_id=99999,
                db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_copy_nonexistent_bot_returns_404(self, db_session):
        """Failure: copying non-existent bot returns 404."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import copy_bot_to_account

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id, name="Paper", type="cex", is_active=True,
            is_paper_trading=True,
        )
        db_session.add(account)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await copy_bot_to_account(
                bot_id=99999, target_account_id=account.id,
                db=db_session, current_user=user,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# GET /bots/{bot_id}/stats
# =============================================================================


class TestGetBotStats:
    """Tests for GET /bots/{bot_id}/stats"""

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_crud_router.get_coinbase_from_db", new_callable=AsyncMock, return_value=None)
    async def test_get_stats_no_positions(self, mock_coinbase, db_session):
        """Happy path: returns zeroed stats for bot with no positions."""
        from app.bot_routers.bot_crud_router import get_bot_stats

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()
        bot = await _make_bot(db_session, user)

        result = await get_bot_stats(bot_id=bot.id, db=db_session, current_user=user)
        assert result.total_positions == 0
        assert result.open_positions == 0
        assert result.closed_positions == 0
        assert result.win_rate == 0.0

    @pytest.mark.asyncio
    async def test_get_stats_nonexistent_bot_returns_404(self, db_session):
        """Failure: stats for non-existent bot returns 404."""
        from fastapi import HTTPException
        from app.bot_routers.bot_crud_router import get_bot_stats

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_bot_stats(bot_id=99999, db=db_session, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.bot_routers.bot_crud_router.get_coinbase_from_db", new_callable=AsyncMock, return_value=None)
    async def test_get_stats_with_closed_positions(self, mock_coinbase, db_session):
        """Edge case: stats include profit and win rate from closed positions."""
        from app.bot_routers.bot_crud_router import get_bot_stats

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()
        bot = await _make_bot(db_session, user)

        # Add closed winning position
        pos1 = Position(
            bot_id=bot.id, user_id=user.id, product_id="ETH-BTC",
            status="closed", profit_quote=0.01,
            initial_quote_balance=1.0, max_quote_allowed=0.25,
        )
        # Add closed losing position
        pos2 = Position(
            bot_id=bot.id, user_id=user.id, product_id="ETH-BTC",
            status="closed", profit_quote=-0.005,
            initial_quote_balance=1.0, max_quote_allowed=0.25,
        )
        db_session.add_all([pos1, pos2])
        await db_session.flush()

        result = await get_bot_stats(bot_id=bot.id, db=db_session, current_user=user)
        assert result.closed_positions == 2
        assert result.win_rate == pytest.approx(50.0)
        assert result.total_profit_quote == pytest.approx(0.005)


# =============================================================================
# get_coinbase_from_db helper
# =============================================================================


class TestGetCoinbaseFromDb:
    """Tests for get_coinbase_from_db() — now imported from portfolio_service"""

    @pytest.mark.asyncio
    async def test_no_account_raises_exchange_unavailable(self, db_session):
        """Failure: no active CEX account raises ExchangeUnavailableError."""
        from app.bot_routers.bot_crud_router import get_coinbase_from_db
        from app.exceptions import ExchangeUnavailableError

        with pytest.raises(ExchangeUnavailableError):
            await get_coinbase_from_db(db_session, user_id=99999)

    @pytest.mark.asyncio
    async def test_account_without_credentials_raises_exchange_unavailable(self, db_session):
        """Failure: account without API credentials raises ExchangeUnavailableError."""
        from app.bot_routers.bot_crud_router import get_coinbase_from_db
        from app.exceptions import ExchangeUnavailableError

        user = _make_user(db_session)
        db_session.add(user)
        await db_session.flush()

        account = Account(
            user_id=user.id, name="No Creds", type="cex",
            exchange="coinbase", is_active=True, is_paper_trading=False,
            api_key_name=None, api_private_key=None,
        )
        db_session.add(account)
        await db_session.flush()

        with pytest.raises(ExchangeUnavailableError):
            await get_coinbase_from_db(db_session, user_id=user.id)
