"""
Tests for backend/app/routers/webhook_router.py

Covers TradingView webhook integration:
- Valid webhook triggers process_signal
- Invalid token returns 404
- Rate limiting enforcement
- Stopped bot rejection
- Symbol not in bot's pairs rejection
- Token generation + revocation endpoints
"""

import pytest
from app.utils.timeutil import utcnow
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models import Account, Bot, BotProduct, User


# =============================================================================
# Helpers
# =============================================================================


def _make_user():
    return User(
        email="webhook@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=utcnow(),
    )


async def _make_account(db_session, user):
    account = Account(
        user_id=user.id,
        name="Test CEX",
        type="cex",
        exchange="coinbase",
        is_default=True,
        is_active=True,
        api_key_name="test-key-name",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db_session.add(account)
    await db_session.flush()
    return account


async def _make_bot(
    db_session, user, account,
    name="WebhookBot",
    is_active=True,
    webhook_token="test-webhook-token-abc123",
    product_id="BTC-USD",
    strategy_type="indicator_based",
):
    bot = Bot(
        user_id=user.id,
        account_id=account.id,
        name=name,
        strategy_type=strategy_type,
        strategy_config={
            "base_order_size": 10.0,
            "max_concurrent_deals": 1,
            "base_order_percentage": 5.0,
        },
        product_id=product_id,
        product_ids=[product_id],
        is_active=is_active,
        webhook_token=webhook_token,
        check_interval_seconds=300,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db_session.add(bot)
    await db_session.flush()
    # Add bot product
    db_session.add(BotProduct(bot_id=bot.id, product_id=product_id))
    await db_session.flush()
    return bot


# =============================================================================
# Rate limiter tests
# =============================================================================


def test_rate_limit_allows_under_limit():
    """Requests under the limit are allowed."""
    from app.routers.webhook_router import _check_rate_limit, _rate_limit_store
    _rate_limit_store.clear()
    token = "rate-test-token"
    for i in range(10):
        assert _check_rate_limit(token) is True


def test_rate_limit_blocks_over_limit():
    """The 11th request within a minute is blocked."""
    from app.routers.webhook_router import _check_rate_limit, _rate_limit_store
    _rate_limit_store.clear()
    token = "rate-test-token-2"
    for i in range(10):
        assert _check_rate_limit(token) is True
    # 11th should be blocked
    assert _check_rate_limit(token) is False


def test_rate_limit_independent_tokens():
    """Different tokens have independent rate limits."""
    from app.routers.webhook_router import _check_rate_limit, _rate_limit_store
    _rate_limit_store.clear()
    token_a = "token-a"
    token_b = "token-b"
    for i in range(10):
        assert _check_rate_limit(token_a) is True
    # token_b should still be allowed
    assert _check_rate_limit(token_b) is True


# =============================================================================
# Webhook endpoint tests
# =============================================================================


@pytest.fixture
async def webhook_setup(db_session):
    """Create user, account, and bot for webhook tests."""
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    account = await _make_account(db_session, user)
    bot = await _make_bot(db_session, user, account)

    return user, account, bot


async def test_invalid_token_returns_404(webhook_setup, db_session):
    """Webhook with unknown token returns 404."""
    from app.routers.webhook_router import tradingview_webhook, TradingViewAlert

    # Clear rate limit store
    from app.routers.webhook_router import _rate_limit_store
    _rate_limit_store.clear()

    alert = TradingViewAlert(
        token="nonexistent-token",
        side="buy",
        symbol="BTC-USD",
    )

    with pytest.raises(HTTPException) as exc_info:
        await tradingview_webhook(alert, db=db_session)

    assert exc_info.value.status_code == 404


async def test_stopped_bot_rejected(webhook_setup, db_session):
    """Webhook for a stopped bot returns rejection, not an error."""
    from app.routers.webhook_router import tradingview_webhook, TradingViewAlert, _rate_limit_store
    _rate_limit_store.clear()

    user, account, bot = webhook_setup

    # Make bot inactive
    bot.is_active = False
    await db_session.flush()

    alert = TradingViewAlert(
        token=bot.webhook_token,
        side="buy",
        symbol="BTC-USD",
    )

    response = await tradingview_webhook(alert, db=db_session)
    assert response.status == "rejected"
    assert "not active" in response.reason.lower()


async def test_symbol_not_in_bot_pairs_rejected(webhook_setup, db_session):
    """Webhook for a symbol not configured on the bot is rejected."""
    from app.routers.webhook_router import tradingview_webhook, TradingViewAlert, _rate_limit_store
    _rate_limit_store.clear()

    user, account, bot = webhook_setup

    alert = TradingViewAlert(
        token=bot.webhook_token,
        side="buy",
        symbol="ETH-USD",  # Not in bot's pairs (bot has BTC-USD)
    )

    response = await tradingview_webhook(alert, db=db_session)
    assert response.status == "rejected"
    assert "not configured" in response.reason.lower()


async def test_valid_webhook_calls_process_signal(webhook_setup, db_session):
    """A valid webhook with correct token and symbol triggers process_signal."""
    from app.routers.webhook_router import tradingview_webhook, TradingViewAlert, _rate_limit_store
    _rate_limit_store.clear()

    user, account, bot = webhook_setup

    alert = TradingViewAlert(
        token=bot.webhook_token,
        side="buy",
        symbol="BTC-USD",
    )

    # Mock the exchange client and process_signal
    mock_exchange = MagicMock()
    mock_exchange.get_current_price = AsyncMock(return_value=100000.0)
    mock_exchange.get_candles = AsyncMock(return_value=[])

    mock_result = {"action": "buy", "reason": "Webhook signal executed"}

    with patch(
        "app.services.exchange_service.get_exchange_client_for_account",
        new_callable=AsyncMock,
        return_value=mock_exchange,
    ), patch(
        "app.strategies.StrategyRegistry.get_strategy",
        return_value=MagicMock(),
    ), patch(
        "app.trading_engine_v2.StrategyTradingEngine"
    ) as MockEngine:
        mock_engine_instance = MockEngine.return_value
        mock_engine_instance.process_signal = AsyncMock(return_value=mock_result)

        response = await tradingview_webhook(alert, db=db_session)

    assert response.status == "ok"
    assert response.action == "buy"
    assert "Webhook signal executed" in response.reason
    # Verify process_signal was called
    mock_engine_instance.process_signal.assert_called_once()


async def test_rate_limit_exceeded_returns_429(webhook_setup, db_session):
    """After 10 requests, the 11th returns 429."""
    from app.routers.webhook_router import tradingview_webhook, TradingViewAlert, _rate_limit_store
    _rate_limit_store.clear()

    user, account, bot = webhook_setup

    # Make bot inactive so we don't need exchange mocks (fast rejection path)
    bot.is_active = False
    await db_session.flush()

    alert = TradingViewAlert(
        token=bot.webhook_token,
        side="buy",
        symbol="BTC-USD",
    )

    # Send 10 requests (all rejected because bot is stopped, but they pass rate limit)
    for i in range(10):
        await tradingview_webhook(alert, db=db_session)

    # 11th should hit rate limit
    with pytest.raises(HTTPException) as exc_info:
        await tradingview_webhook(alert, db=db_session)

    assert exc_info.value.status_code == 429


# =============================================================================
# Webhook token management endpoint tests
# =============================================================================


async def test_regenerate_webhook_token(webhook_setup, db_session):
    """POST /{bot_id}/webhook-token generates a new token."""
    from app.bot_routers.bot_crud_router import regenerate_webhook_token

    user, account, bot = webhook_setup
    original_token = bot.webhook_token

    # Need to mock the permission dependency
    with patch(
        "app.bot_routers.bot_crud_router.require_permission",
        return_value=lambda *a, **kw: AsyncMock(return_value=user)(),
    ):
        response = await regenerate_webhook_token(bot.id, db=db_session, current_user=user)

    assert response.webhook_token is not None
    assert response.webhook_token != original_token
    # Token should be URL-safe base64 (43+ chars)
    assert len(response.webhook_token) >= 32


async def test_revoke_webhook_token(webhook_setup, db_session):
    """DELETE /{bot_id}/webhook-token removes the token."""
    from app.bot_routers.bot_crud_router import revoke_webhook_token

    user, account, bot = webhook_setup
    assert bot.webhook_token is not None

    with patch(
        "app.bot_routers.bot_crud_router.require_permission",
        return_value=lambda *a, **kw: AsyncMock(return_value=user)(),
    ):
        response = await revoke_webhook_token(bot.id, db=db_session, current_user=user)

    assert response.webhook_token is None


async def test_regenerate_token_bot_not_found(db_session, webhook_setup):
    """Regenerating token for nonexistent bot returns 404."""
    from app.bot_routers.bot_crud_router import regenerate_webhook_token

    user, account, bot = webhook_setup

    with pytest.raises(HTTPException) as exc_info:
        await regenerate_webhook_token(99999, db=db_session, current_user=user)

    assert exc_info.value.status_code == 404


# =============================================================================
# Bot creation with webhook_enabled
# =============================================================================


async def test_create_bot_with_webhook_enabled_generates_token(db_session):
    """Creating a bot with webhook_enabled=True generates a webhook token."""
    from app.bot_routers.schemas import BotCreate
    from app.bot_routers.bot_crud_router import create_bot

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    account = await _make_account(db_session, user)

    bot_data = BotCreate(
        name="WebhookEnabledBot",
        strategy_type="indicator_based",
        strategy_config={
            "base_order_size": 10.0,
            "max_concurrent_deals": 1,
            "base_order_percentage": 5.0,
        },
        product_id="BTC-USD",
        product_ids=["BTC-USD"],
        account_id=account.id,
        webhook_enabled=True,
    )

    with patch(
        "app.bot_routers.bot_crud_router.require_permission",
        return_value=lambda *a, **kw: AsyncMock(return_value=user)(),
    ), patch(
        "app.services.bot_validation_service.validate_quote_currency",
        return_value="USD",
    ), patch(
        "app.services.bot_validation_service.auto_correct_market_focus",
    ), patch(
        "app.services.bot_validation_service.validate_bidirectional_budget_config",
        new_callable=AsyncMock,
        return_value=(0.0, 0.0),
    ):
        response = await create_bot(bot_data, db=db_session, current_user=user)

    assert response.webhook_token is not None
    assert len(response.webhook_token) >= 32


async def test_create_bot_without_webhook_has_no_token(db_session):
    """Creating a bot without webhook_enabled does NOT generate a token."""
    from app.bot_routers.schemas import BotCreate
    from app.bot_routers.bot_crud_router import create_bot

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    account = await _make_account(db_session, user)

    bot_data = BotCreate(
        name="NoWebhookBot",
        strategy_type="indicator_based",
        strategy_config={
            "base_order_size": 10.0,
            "max_concurrent_deals": 1,
            "base_order_percentage": 5.0,
        },
        product_id="BTC-USD",
        product_ids=["BTC-USD"],
        account_id=account.id,
        webhook_enabled=False,
    )

    with patch(
        "app.bot_routers.bot_crud_router.require_permission",
        return_value=lambda *a, **kw: AsyncMock(return_value=user)(),
    ), patch(
        "app.services.bot_validation_service.validate_quote_currency",
        return_value="USD",
    ), patch(
        "app.services.bot_validation_service.auto_correct_market_focus",
    ), patch(
        "app.services.bot_validation_service.validate_bidirectional_budget_config",
        new_callable=AsyncMock,
        return_value=(0.0, 0.0),
    ):
        response = await create_bot(bot_data, db=db_session, current_user=user)

    assert response.webhook_token is None