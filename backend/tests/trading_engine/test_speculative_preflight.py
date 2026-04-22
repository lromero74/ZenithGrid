"""
Tests for the speculative-bucket preflight guard in
backend/app/trading_engine/signal_processor/buy_decision.py::_run_new_position_preflight.

These exercise the speculative-tagged branch added in
PRPs/high-risk-doubling-preset.md §Recommended Design §6. We mock
validate_speculative_entry to isolate the branch logic from the bucket
math (which has its own tests in tests/services/test_speculative_bucket_service.py).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.trading_engine.signal_processor.buy_decision import _run_new_position_preflight
from app.trading_engine.trade_context import TradeContext


# ---------------------------------------------------------------------------
# Minimal factory helpers
# ---------------------------------------------------------------------------


def _make_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    scalars.first.return_value = None
    result = MagicMock()
    result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result)
    return db


def _make_bot(strategy_config=None):
    bot = MagicMock()
    bot.id = 1
    bot.account_id = 7
    bot.strategy_config = strategy_config if strategy_config is not None else {}
    bot.soft_ceiling_effective_max = None
    return bot


def _make_strategy(config=None):
    strategy = MagicMock()
    strategy.config = config if config is not None else {"base_order_size": 25.0}
    return strategy


def _make_ctx(bot, strategy):
    return TradeContext(
        db=_make_db(),
        exchange=MagicMock(),
        trading_client=MagicMock(),
        bot=bot,
        product_id="HYPE-USD",
        current_price=1.0,
        strategy=strategy,
    )


# ---------------------------------------------------------------------------
# Patches used across tests
# ---------------------------------------------------------------------------


def _patch_preflight_baseline(enter_stack):
    """Patch the non-speculative preflight prerequisites so tests can focus
    on the speculative branch without fighting stable-pair / soft-ceiling
    side effects.

    Returns the ExitStack-managed mocks keyed by name.
    """
    patches = {
        "is_stable_pair": patch(
            "app.services.delisted_pair_monitor.is_stable_pair",
            return_value=False,
        ),
        "get_open_positions_count": patch(
            "app.trading_engine.signal_processor.buy_decision.get_open_positions_count",
            new_callable=AsyncMock,
            return_value=0,
        ),
        "calculate_soft_ceiling": patch(
            "app.trading_engine.signal_processor.buy_decision.calculate_soft_ceiling",
            new_callable=AsyncMock,
            return_value=10,
        ),
    }
    return {name: enter_stack.enter_context(p) for name, p in patches.items()}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSpeculativePreflight:
    """The speculative-bucket check fires only when the bot is tagged
    `is_speculative: "true"` in strategy_config. Everything else stays
    on the non-speculative path."""

    @pytest.mark.asyncio
    async def test_non_speculative_bot_skips_bucket_check(self):
        """Regression guard: plain bots must not invoke the bucket validator."""
        bot = _make_bot(strategy_config={"max_concurrent_deals": 5})
        ctx = _make_ctx(bot, _make_strategy())

        from contextlib import ExitStack
        with ExitStack() as stack:
            _patch_preflight_baseline(stack)
            spec_validator = stack.enter_context(
                patch(
                    "app.services.speculative_bucket_service.validate_speculative_entry",
                    new_callable=AsyncMock,
                    return_value=(True, ""),
                )
            )
            blocked, reason, _ = await _run_new_position_preflight(
                ctx, aggregate_value=10_000.0, open_positions_count=None,
            )

        assert blocked is False
        assert reason == ""
        spec_validator.assert_not_called()

    @pytest.mark.asyncio
    async def test_speculative_bot_allowed_when_bucket_has_room(self):
        bot = _make_bot(strategy_config={
            "is_speculative": "true",
            "max_concurrent_deals": 5,
        })
        ctx = _make_ctx(bot, _make_strategy(config={"base_order_size": 25.0}))

        from contextlib import ExitStack
        with ExitStack() as stack:
            _patch_preflight_baseline(stack)
            spec_validator = stack.enter_context(
                patch(
                    "app.services.speculative_bucket_service.validate_speculative_entry",
                    new_callable=AsyncMock,
                    return_value=(True, ""),
                )
            )
            blocked, reason, _ = await _run_new_position_preflight(
                ctx, aggregate_value=10_000.0, open_positions_count=None,
            )

        assert blocked is False
        assert reason == ""
        spec_validator.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_speculative_bot_blocked_when_bucket_full(self):
        bot = _make_bot(strategy_config={
            "is_speculative": "true",
            "max_concurrent_deals": 5,
        })
        ctx = _make_ctx(bot, _make_strategy(config={"base_order_size": 100.0}))

        from contextlib import ExitStack
        with ExitStack() as stack:
            _patch_preflight_baseline(stack)
            stack.enter_context(
                patch(
                    "app.services.speculative_bucket_service.validate_speculative_entry",
                    new_callable=AsyncMock,
                    return_value=(False, "Speculative bucket full: need $100 but only $20 available"),
                )
            )
            blocked, reason, _ = await _run_new_position_preflight(
                ctx, aggregate_value=10_000.0, open_positions_count=None,
            )

        assert blocked is True
        assert "Speculative bucket full" in reason

    @pytest.mark.asyncio
    async def test_speculative_bot_blocked_when_no_bucket_configured(self):
        bot = _make_bot(strategy_config={
            "is_speculative": "true",
            "max_concurrent_deals": 5,
        })
        ctx = _make_ctx(bot, _make_strategy(config={"base_order_size": 25.0}))

        from contextlib import ExitStack
        with ExitStack() as stack:
            _patch_preflight_baseline(stack)
            stack.enter_context(
                patch(
                    "app.services.speculative_bucket_service.validate_speculative_entry",
                    new_callable=AsyncMock,
                    return_value=(False, "Speculative bucket not configured for this account"),
                )
            )
            blocked, reason, _ = await _run_new_position_preflight(
                ctx, aggregate_value=10_000.0, open_positions_count=None,
            )

        assert blocked is True
        assert "not configured" in reason.lower()

    @pytest.mark.asyncio
    async def test_preflight_passes_base_order_size_as_cost_basis(self):
        """The preflight must pass strategy.config['base_order_size'] into the
        bucket validator — that's the cost basis the first trade will deploy."""
        bot = _make_bot(strategy_config={"is_speculative": "true"})
        ctx = _make_ctx(bot, _make_strategy(config={"base_order_size": 37.5}))

        from contextlib import ExitStack
        with ExitStack() as stack:
            _patch_preflight_baseline(stack)
            spec_validator = stack.enter_context(
                patch(
                    "app.services.speculative_bucket_service.validate_speculative_entry",
                    new_callable=AsyncMock,
                    return_value=(True, ""),
                )
            )
            await _run_new_position_preflight(
                ctx, aggregate_value=10_000.0, open_positions_count=None,
            )

        # Confirm the validator received the right cost basis
        call = spec_validator.await_args
        assert call.kwargs.get("intended_cost_basis_usd") == 37.5
        assert call.kwargs.get("aggregate_usd_value") == 10_000.0
