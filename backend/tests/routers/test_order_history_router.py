"""
Tests for backend/app/routers/order_history.py

Covers:
- GET /api/order-history/ — list with filters
- GET /api/order-history/failed — recent failed orders
- GET /api/order-history/failed/paginated — paginated failed orders
- GET /api/order-history/stats — order statistics
"""

import pytest
from datetime import datetime

from app.models import Account, Bot, OrderHistory, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def order_setup(db_session):
    """Create user, account, bot, and order history records."""
    user = User(
        email="orderhistory_test@example.com",
        hashed_password="hashed",
        display_name="Order Tester",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    account = Account(
        user_id=user.id,
        name="Test Account",
        type="cex",
        exchange="coinbase",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    bot = Bot(
        user_id=user.id,
        account_id=account.id,
        name="Test Bot",
        strategy_type="macd_dca",
        product_id="ETH-BTC",
        is_active=True,
    )
    db_session.add(bot)
    await db_session.flush()

    # Create mixed orders: 3 success, 2 failed, 1 canceled
    orders = []
    for i in range(3):
        o = OrderHistory(
            bot_id=bot.id,
            product_id="ETH-BTC",
            side="BUY",
            order_type="MARKET",
            trade_type="initial",
            quote_amount=100.0,
            base_amount=0.002,
            price=50000.0,
            status="success",
            order_id=f"order-success-{i}",
            timestamp=datetime(2026, 1, 10 + i),
        )
        orders.append(o)

    for i in range(2):
        o = OrderHistory(
            bot_id=bot.id,
            product_id="ETH-BTC",
            side="BUY",
            order_type="MARKET",
            trade_type="dca",
            quote_amount=50.0,
            status="failed",
            error_message=f"Insufficient funds #{i}",
            timestamp=datetime(2026, 1, 15 + i),
        )
        orders.append(o)

    canceled = OrderHistory(
        bot_id=bot.id,
        product_id="ETH-BTC",
        side="SELL",
        order_type="LIMIT",
        trade_type="take_profit",
        quote_amount=200.0,
        status="canceled",
        timestamp=datetime(2026, 1, 20),
    )
    orders.append(canceled)

    db_session.add_all(orders)
    await db_session.flush()

    return user, account, bot, orders


@pytest.fixture
async def multi_user_order_setup(db_session, order_setup):
    """Add a second user with their own bot and orders."""
    user1, account1, bot1, orders1 = order_setup

    user2 = User(
        email="other_orderhistory@example.com",
        hashed_password="hashed",
        display_name="Other User",
        is_active=True,
    )
    db_session.add(user2)
    await db_session.flush()

    account2 = Account(
        user_id=user2.id,
        name="Other Account",
        type="cex",
        is_active=True,
    )
    db_session.add(account2)
    await db_session.flush()

    bot2 = Bot(
        user_id=user2.id,
        account_id=account2.id,
        name="Other Bot",
        strategy_type="rsi",
        product_id="SOL-USD",
        is_active=True,
    )
    db_session.add(bot2)
    await db_session.flush()

    other_order = OrderHistory(
        bot_id=bot2.id,
        product_id="SOL-USD",
        side="BUY",
        order_type="MARKET",
        trade_type="initial",
        quote_amount=500.0,
        base_amount=10.0,
        price=50.0,
        status="success",
        order_id="other-order-1",
        timestamp=datetime(2026, 1, 18),
    )
    db_session.add(other_order)
    await db_session.flush()

    return user1, user2, bot1, bot2


# =============================================================================
# GET /api/order-history/
# =============================================================================


class TestGetOrderHistory:
    """Tests for GET /api/order-history/"""

    @pytest.mark.asyncio
    async def test_returns_all_user_orders(self, db_session, order_setup):
        """Happy path: returns all orders for the user."""
        from app.routers.order_history import get_order_history

        user, _, _, orders = order_setup
        result = await get_order_history(
            db=db_session, current_user=user,
            bot_id=None, account_id=None, status=None,
            limit=100, offset=0,
        )
        assert len(result) == 6

    @pytest.mark.asyncio
    async def test_filter_by_status(self, db_session, order_setup):
        """Edge case: filter by status narrows results."""
        from app.routers.order_history import get_order_history

        user, _, _, _ = order_setup
        result = await get_order_history(
            db=db_session, current_user=user,
            bot_id=None, account_id=None, status="failed",
            limit=100, offset=0,
        )
        assert len(result) == 2
        for order in result:
            assert order.status == "failed"

    @pytest.mark.asyncio
    async def test_filter_by_bot_id(self, db_session, order_setup):
        """Edge case: filter by bot_id."""
        from app.routers.order_history import get_order_history

        user, _, bot, _ = order_setup
        result = await get_order_history(
            db=db_session, current_user=user,
            bot_id=bot.id, account_id=None, status=None,
            limit=100, offset=0,
        )
        assert len(result) == 6

    @pytest.mark.asyncio
    async def test_filter_by_account_id(self, db_session, order_setup):
        """Edge case: filter by account_id."""
        from app.routers.order_history import get_order_history

        user, account, _, _ = order_setup
        result = await get_order_history(
            db=db_session, current_user=user,
            bot_id=None, account_id=account.id, status=None,
            limit=100, offset=0,
        )
        assert len(result) == 6

    @pytest.mark.asyncio
    async def test_pagination_limit(self, db_session, order_setup):
        """Edge case: limit restricts returned results."""
        from app.routers.order_history import get_order_history

        user, _, _, _ = order_setup
        result = await get_order_history(
            db=db_session, current_user=user,
            bot_id=None, account_id=None, status=None,
            limit=3, offset=0,
        )
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_pagination_offset(self, db_session, order_setup):
        """Edge case: offset skips records."""
        from app.routers.order_history import get_order_history

        user, _, _, _ = order_setup
        result = await get_order_history(
            db=db_session, current_user=user,
            bot_id=None, account_id=None, status=None,
            limit=100, offset=4,
        )
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_user_isolation(self, db_session, multi_user_order_setup):
        """Security: user cannot see other user's orders."""
        from app.routers.order_history import get_order_history

        _, user2, _, _ = multi_user_order_setup
        result = await get_order_history(
            db=db_session, current_user=user2,
            bot_id=None, account_id=None, status=None,
            limit=100, offset=0,
        )
        # user2 has only 1 order
        assert len(result) == 1
        assert result[0].product_id == "SOL-USD"

    @pytest.mark.asyncio
    async def test_empty_result(self, db_session):
        """Edge case: user with no orders gets empty list."""
        from app.routers.order_history import get_order_history

        user = User(
            email="empty_orders@example.com",
            hashed_password="hashed",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_order_history(
            db=db_session, current_user=user,
            bot_id=None, account_id=None, status=None,
            limit=100, offset=0,
        )
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_order_history_response_fields(self, db_session, order_setup):
        """Happy path: response includes all expected fields."""
        from app.routers.order_history import get_order_history

        user, _, bot, _ = order_setup
        result = await get_order_history(
            db=db_session, current_user=user,
            bot_id=None, account_id=None, status="success",
            limit=1, offset=0,
        )
        assert len(result) == 1
        order = result[0]
        assert order.bot_id == bot.id
        assert order.bot_name == "Test Bot"
        assert order.product_id == "ETH-BTC"
        assert order.side == "BUY"
        assert order.order_type == "MARKET"
        assert order.trade_type == "initial"
        assert order.quote_amount == 100.0
        assert order.base_amount == 0.002
        assert order.status == "success"


# =============================================================================
# GET /api/order-history/failed
# =============================================================================


class TestGetFailedOrders:
    """Tests for GET /api/order-history/failed"""

    @pytest.mark.asyncio
    async def test_returns_only_failed(self, db_session, order_setup):
        """Happy path: returns only failed orders."""
        from app.routers.order_history import get_failed_orders

        user, _, _, _ = order_setup
        result = await get_failed_orders(
            db=db_session, current_user=user,
            bot_id=None, account_id=None, limit=50,
        )
        assert len(result) == 2
        for order in result:
            assert order.status == "failed"

    @pytest.mark.asyncio
    async def test_no_failed_orders(self, db_session):
        """Edge case: no failed orders returns empty list."""
        from app.routers.order_history import get_failed_orders

        user = User(
            email="no_fails@example.com",
            hashed_password="hashed",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_failed_orders(
            db=db_session, current_user=user,
            bot_id=None, account_id=None, limit=50,
        )
        assert len(result) == 0


# =============================================================================
# GET /api/order-history/failed/paginated
# =============================================================================


class TestGetFailedOrdersPaginated:
    """Tests for GET /api/order-history/failed/paginated"""

    @pytest.mark.asyncio
    async def test_paginated_response_shape(self, db_session, order_setup):
        """Happy path: returns correct pagination metadata."""
        from app.routers.order_history import get_failed_orders_paginated

        user, _, _, _ = order_setup
        result = await get_failed_orders_paginated(
            db=db_session, current_user=user,
            bot_id=None, account_id=None,
            page=1, page_size=25,
        )
        assert result["total"] == 2
        assert result["page"] == 1
        assert result["page_size"] == 25
        assert result["total_pages"] == 1
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_paginated_small_page_size(self, db_session, order_setup):
        """Edge case: page_size=1 returns one item with correct total_pages."""
        from app.routers.order_history import get_failed_orders_paginated

        user, _, _, _ = order_setup
        result = await get_failed_orders_paginated(
            db=db_session, current_user=user,
            bot_id=None, account_id=None,
            page=1, page_size=1,
        )
        assert result["total"] == 2
        assert result["total_pages"] == 2
        assert len(result["items"]) == 1

    @pytest.mark.asyncio
    async def test_paginated_page_2(self, db_session, order_setup):
        """Edge case: second page returns remaining items."""
        from app.routers.order_history import get_failed_orders_paginated

        user, _, _, _ = order_setup
        result = await get_failed_orders_paginated(
            db=db_session, current_user=user,
            bot_id=None, account_id=None,
            page=2, page_size=1,
        )
        assert len(result["items"]) == 1

    @pytest.mark.asyncio
    async def test_paginated_empty(self, db_session):
        """Edge case: no failed orders returns empty page."""
        from app.routers.order_history import get_failed_orders_paginated

        user = User(
            email="empty_paginated@example.com",
            hashed_password="hashed",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_failed_orders_paginated(
            db=db_session, current_user=user,
            bot_id=None, account_id=None,
            page=1, page_size=25,
        )
        assert result["total"] == 0
        assert result["total_pages"] == 1
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_paginated_user_isolation(self, db_session, multi_user_order_setup):
        """Security: user2 sees only their own failed orders (none)."""
        from app.routers.order_history import get_failed_orders_paginated

        _, user2, _, _ = multi_user_order_setup
        result = await get_failed_orders_paginated(
            db=db_session, current_user=user2,
            bot_id=None, account_id=None,
            page=1, page_size=25,
        )
        assert result["total"] == 0


# =============================================================================
# GET /api/order-history/stats
# =============================================================================


class TestGetOrderStats:
    """Tests for GET /api/order-history/stats"""

    @pytest.mark.asyncio
    async def test_stats_happy_path(self, db_session, order_setup):
        """Happy path: correct stats for mixed orders."""
        from app.routers.order_history import get_order_stats

        user, _, _, _ = order_setup
        result = await get_order_stats(
            db=db_session, current_user=user,
            bot_id=None, account_id=None,
        )
        assert result["total_orders"] == 6
        assert result["successful_orders"] == 3
        assert result["failed_orders"] == 2
        assert result["canceled_orders"] == 1
        assert result["success_rate"] == pytest.approx(50.0)
        assert result["failure_rate"] == pytest.approx(100.0 / 3)

    @pytest.mark.asyncio
    async def test_stats_empty(self, db_session):
        """Edge case: no orders returns all zeros."""
        from app.routers.order_history import get_order_stats

        user = User(
            email="empty_stats@example.com",
            hashed_password="hashed",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_order_stats(
            db=db_session, current_user=user,
            bot_id=None, account_id=None,
        )
        assert result["total_orders"] == 0
        assert result["success_rate"] == 0
        assert result["failure_rate"] == 0

    @pytest.mark.asyncio
    async def test_stats_filter_by_bot(self, db_session, order_setup):
        """Edge case: bot_id filter restricts stats."""
        from app.routers.order_history import get_order_stats

        user, _, bot, _ = order_setup
        result = await get_order_stats(
            db=db_session, current_user=user,
            bot_id=bot.id, account_id=None,
        )
        assert result["total_orders"] == 6

    @pytest.mark.asyncio
    async def test_stats_user_isolation(self, db_session, multi_user_order_setup):
        """Security: stats are scoped to the current user."""
        from app.routers.order_history import get_order_stats

        _, user2, _, _ = multi_user_order_setup
        result = await get_order_stats(
            db=db_session, current_user=user2,
            bot_id=None, account_id=None,
        )
        assert result["total_orders"] == 1
        assert result["successful_orders"] == 1
        assert result["success_rate"] == 100.0
