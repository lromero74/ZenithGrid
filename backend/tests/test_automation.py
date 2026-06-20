"""
Tests for backend/app/automation/__init__.py

Covers:
- Trigger evaluators: price_threshold, holding_threshold, period_check, profitability_threshold
- Action executors: stop_trading, start_bot, send_notification
- evaluate_rule: disabled rules skipped, trigger+action flow, fire_count increment
- evaluate_all_rules: filtering by account, only enabled rules
- Account scoping: rules only act on their account's bots/positions
"""

import pytest
from app.utils.timeutil import utcnow
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from app.models import Account, AutomationRule, Bot, Position, User


# =============================================================================
# Helpers
# =============================================================================


async def _make_user(db_session):
    user = User(
        email="automation@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        created_at=utcnow(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_account(db_session, user, name="Test Account"):
    account = Account(
        user_id=user.id, name=name, type="cex", exchange="coinbase",
        is_default=True, is_active=True, api_key_name="test-key",
        created_at=utcnow(), updated_at=utcnow(),
    )
    db_session.add(account)
    await db_session.flush()
    return account


async def _make_bot(db_session, user, account, name="AutoBot", is_active=True):
    bot = Bot(
        user_id=user.id, account_id=account.id, name=name,
        strategy_type="indicator_based",
        strategy_config={"base_order_percentage": 5.0},
        product_id="BTC-USD", product_ids=["BTC-USD"],
        is_active=is_active, created_at=utcnow(), updated_at=utcnow(),
    )
    db_session.add(bot)
    await db_session.flush()
    return bot


async def _make_rule(db_session, user, account, **kwargs):
    defaults = dict(
        user_id=user.id, account_id=account.id,
        name="Test Rule",  # noqa: E128
        trigger_type="price_threshold",  # noqa: E128
        trigger_config={"symbol": "BTC-USD", "target_price": 100000, "direction": "above"},  # noqa: E128
        action_type="stop_trading",  # noqa: E128
        action_config=None,  # noqa: E128
        enabled=True,  # noqa: E128
        fire_count=0,
    )
    defaults.update(kwargs)
    rule = AutomationRule(created_at=utcnow(), updated_at=utcnow(), **defaults)
    db_session.add(rule)
    await db_session.flush()
    return rule


# =============================================================================
# Trigger evaluator tests
# =============================================================================


async def test_price_threshold_above_fires(db_session):
    """Price threshold fires when price is above target."""
    from app.automation import evaluate_price_threshold

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    rule = await _make_rule(db_session, user, account,
        trigger_config={"symbol": "BTC-USD", "target_price": 100000, "direction": "above"})  # noqa: E128
    mock_exchange = MagicMock()
    mock_exchange.get_current_price = AsyncMock(return_value=105000.0)

    result = await evaluate_price_threshold(rule, db_session, mock_exchange)
    assert result is True


async def test_price_threshold_below_not_fired(db_session):
    """Price threshold does not fire when price is below the 'above' target."""
    from app.automation import evaluate_price_threshold

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    rule = await _make_rule(db_session, user, account,
        trigger_config={"symbol": "BTC-USD", "target_price": 100000, "direction": "above"})  # noqa: E128
    mock_exchange = MagicMock()
    mock_exchange.get_current_price = AsyncMock(return_value=95000.0)

    result = await evaluate_price_threshold(rule, db_session, mock_exchange)
    assert result is False


async def test_price_threshold_below_direction_fires(db_session):
    """Price threshold with direction='below' fires when price drops below target."""
    from app.automation import evaluate_price_threshold

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    rule = await _make_rule(db_session, user, account,
        trigger_config={"symbol": "BTC-USD", "target_price": 90000, "direction": "below"})  # noqa: E128
    mock_exchange = MagicMock()
    mock_exchange.get_current_price = AsyncMock(return_value=85000.0)

    result = await evaluate_price_threshold(rule, db_session, mock_exchange)
    assert result is True


async def test_holding_threshold_fires(db_session):
    """Holding threshold fires when a position is older than the threshold."""
    from app.automation import evaluate_holding_threshold

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    bot = await _make_bot(db_session, user, account)
    rule = await _make_rule(db_session, user, account,
        trigger_type="holding_threshold",  # noqa: E128
        trigger_config={"hours": 12})  # noqa: E128
    # Create an old position
    old_pos = Position(
        bot_id=bot.id, user_id=user.id, account_id=account.id,
        product_id="BTC-USD", status="open",
        average_buy_price=50000.0, total_quote_spent=100.0,
        total_base_acquired=0.002, opened_at=utcnow() - timedelta(hours=24),
    )
    db_session.add(old_pos)
    await db_session.flush()

    result = await evaluate_holding_threshold(rule, db_session)
    assert result is True


async def test_holding_threshold_not_fired_for_recent_position(db_session):
    """Holding threshold does not fire for recently opened positions."""
    from app.automation import evaluate_holding_threshold

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    bot = await _make_bot(db_session, user, account)
    rule = await _make_rule(db_session, user, account,
        trigger_type="holding_threshold",  # noqa: E128
        trigger_config={"hours": 24})  # noqa: E128
    recent_pos = Position(
        bot_id=bot.id, user_id=user.id, account_id=account.id,
        product_id="BTC-USD", status="open",
        average_buy_price=50000.0, total_quote_spent=100.0,
        total_base_acquired=0.002, opened_at=utcnow() - timedelta(hours=1),
    )
    db_session.add(recent_pos)
    await db_session.flush()

    result = await evaluate_holding_threshold(rule, db_session)
    assert result is False


async def test_period_check_never_fired_fires(db_session):
    """Period check fires immediately if never fired before."""
    from app.automation import evaluate_period_check

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    rule = await _make_rule(db_session, user, account,
        trigger_type="period_check",  # noqa: E128
        trigger_config={"interval_minutes": 60})  # noqa: E128
    result = await evaluate_period_check(rule, db_session)
    assert result is True


async def test_period_check_not_yet_time(db_session):
    """Period check does not fire if interval hasn't elapsed."""
    from app.automation import evaluate_period_check

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    rule = await _make_rule(db_session, user, account,
        trigger_type="period_check",  # noqa: E128
        trigger_config={"interval_minutes": 60},  # noqa: E128
        last_fired_at=utcnow() - timedelta(minutes=10))  # noqa: E128
    result = await evaluate_period_check(rule, db_session)
    assert result is False


async def test_profitability_threshold_negative_fires(db_session):
    """Profitability threshold fires when P&L drops below threshold."""
    from app.automation import evaluate_profitability_threshold

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    bot = await _make_bot(db_session, user, account)
    rule = await _make_rule(db_session, user, account,
        trigger_type="profitability_threshold",  # noqa: E128
        trigger_config={"percent_change": -5.0})  # noqa: E128
    pos = Position(
        bot_id=bot.id, user_id=user.id, account_id=account.id,
        product_id="BTC-USD", status="open",
        average_buy_price=50000.0, total_quote_spent=100.0,
        total_base_acquired=0.002, opened_at=utcnow(),
        profit_percentage=-8.0,
    )
    db_session.add(pos)
    await db_session.flush()

    result = await evaluate_profitability_threshold(rule, db_session)
    assert result is True


# =============================================================================
# Action executor tests
# =============================================================================


async def test_stop_trading_stops_all_bots(db_session):
    """stop_trading stops all active bots on the account."""
    from app.automation import execute_stop_trading

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    await _make_bot(db_session, user, account, name="Bot1", is_active=True)
    await _make_bot(db_session, user, account, name="Bot2", is_active=True)
    rule = await _make_rule(db_session, user, account)

    result = await execute_stop_trading(rule, db_session)
    assert "Stopped 2 bots" in result

    # Verify bots are stopped
    from sqlalchemy import select
    bots_result = await db_session.execute(
        select(Bot).where(Bot.account_id == account.id)
    )
    bots = bots_result.scalars().all()
    assert all(not b.is_active for b in bots)


async def test_start_bot_action(db_session):
    """start_bot action starts the specified bot."""
    from app.automation import execute_start_bot

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    bot = await _make_bot(db_session, user, account, name="TargetBot", is_active=False)
    rule = await _make_rule(db_session, user, account,
        action_type="start_bot",  # noqa: E128
        action_config={"bot_id": bot.id})  # noqa: E128
    result = await execute_start_bot(rule, db_session)
    assert "Started" in result
    assert "TargetBot" in result

    from sqlalchemy import select
    bot_result = await db_session.execute(select(Bot).where(Bot.id == bot.id))
    updated = bot_result.scalars().first()
    assert updated.is_active is True


async def test_start_bot_already_active(db_session):
    """start_bot on an already-active bot returns appropriate message."""
    from app.automation import execute_start_bot

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    bot = await _make_bot(db_session, user, account, is_active=True)
    rule = await _make_rule(db_session, user, account,
        action_type="start_bot",  # noqa: E128
        action_config={"bot_id": bot.id})  # noqa: E128
    result = await execute_start_bot(rule, db_session)
    assert "already active" in result


async def test_start_bot_not_found(db_session):
    """start_bot with non-existent bot returns error."""
    from app.automation import execute_start_bot

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    rule = await _make_rule(db_session, user, account,
        action_type="start_bot",  # noqa: E128
        action_config={"bot_id": 99999})  # noqa: E128
    result = await execute_start_bot(rule, db_session)
    assert "not found" in result


async def test_send_notification_no_telegram(db_session):
    """send_notification returns message when Telegram not configured."""
    from app.automation import execute_send_notification

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    rule = await _make_rule(db_session, user, account,
        action_type="send_notification",  # noqa: E128
        action_config={"message": "Test alert"})  # noqa: E128
    result = await execute_send_notification(rule, db_session)
    assert "No Telegram" in result


# =============================================================================
# evaluate_rule integration tests
# =============================================================================


async def test_disabled_rule_not_evaluated(db_session):
    """A disabled rule is never evaluated."""
    from app.automation import evaluate_rule

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    rule = await _make_rule(db_session, user, account, enabled=False)
    mock_exchange = MagicMock()
    result = await evaluate_rule(rule, db_session, mock_exchange)
    assert result is None


async def test_rule_fires_and_increments_fire_count(db_session):
    """A triggered rule executes its action and increments fire_count."""
    from app.automation import evaluate_rule

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    await _make_bot(db_session, user, account, is_active=True)
    rule = await _make_rule(db_session, user, account,
        trigger_config={"symbol": "BTC-USD", "target_price": 100000, "direction": "above"},  # noqa: E128
        action_type="stop_trading")  # noqa: E128
    mock_exchange = MagicMock()
    mock_exchange.get_current_price = AsyncMock(return_value=105000.0)

    result = await evaluate_rule(rule, db_session, mock_exchange)
    assert result is not None
    assert "Stopped" in result
    assert rule.fire_count == 1
    assert rule.last_fired_at is not None


async def test_rule_not_triggered_returns_none(db_session):
    """A rule whose trigger is not met returns None and doesn't increment fire_count."""
    from app.automation import evaluate_rule

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    rule = await _make_rule(db_session, user, account)

    mock_exchange = MagicMock()
    mock_exchange.get_current_price = AsyncMock(return_value=50000.0)

    result = await evaluate_rule(rule, db_session, mock_exchange)
    assert result is None
    assert rule.fire_count == 0


async def test_evaluate_all_rules_only_enabled(db_session):
    """evaluate_all_rules only evaluates enabled rules."""
    from app.automation import evaluate_all_rules

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)
    await _make_bot(db_session, user, account, is_active=True)

    # One enabled, one disabled
    await _make_rule(db_session, user, account, name="Enabled Rule", enabled=True)
    await _make_rule(db_session, user, account, name="Disabled Rule", enabled=False)

    mock_exchange = MagicMock()
    mock_exchange.get_current_price = AsyncMock(return_value=105000.0)

    fired = await evaluate_all_rules(db_session, mock_exchange, account_id=account.id)
    assert len(fired) == 1
    assert fired[0]["rule_name"] == "Enabled Rule"


# =============================================================================
# Router CRUD tests
# =============================================================================


async def test_create_rule_invalid_trigger_type(db_session):
    """Creating a rule with an invalid trigger type returns 400."""
    from app.routers.automation_router import create_rule, AutomationRuleCreate

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)

    rule_data = AutomationRuleCreate(
        name="Bad Rule",  # noqa: E128
        account_id=account.id,
        trigger_type="invalid_trigger",  # noqa: E128
        trigger_config={},  # noqa: E128
        action_type="stop_trading",  # noqa: E128
    )

    with pytest.raises(Exception) as exc_info:
        await create_rule(rule_data, current_user=user, db=db_session)
    assert "400" in str(exc_info.value) or "Invalid trigger" in str(exc_info.value)


async def test_create_rule_invalid_action_type(db_session):
    """Creating a rule with an invalid action type returns 400."""
    from app.routers.automation_router import create_rule, AutomationRuleCreate

    user = await _make_user(db_session)
    account = await _make_account(db_session, user)

    rule_data = AutomationRuleCreate(
        name="Bad Action Rule",  # noqa: E128
        account_id=account.id,
        trigger_type="period_check",  # noqa: E128
        trigger_config={"interval_minutes": 60},  # noqa: E128
        action_type="invalid_action",  # noqa: E128
    )

    with pytest.raises(Exception) as exc_info:
        await create_rule(rule_data, current_user=user, db=db_session)
    assert "400" in str(exc_info.value) or "Invalid action" in str(exc_info.value)


async def test_delete_rule_not_found(db_session):
    """Deleting a non-existent rule returns 404."""
    from app.routers.automation_router import delete_rule

    user = await _make_user(db_session)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await delete_rule(99999, current_user=user, db=db_session)
    assert exc_info.value.status_code == 404
