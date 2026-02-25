"""
Tests for backend/app/trading_engine_v2.py

StrategyTradingEngine is a wrapper that delegates to focused trading engine
modules (position_manager, order_logger, buy_executor, sell_executor,
signal_processor). Tests verify correct initialization and delegation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.trading_engine_v2 import StrategyTradingEngine
from app.trading_client import TradingClient
from app.trading_engine import signal_processor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock async DB session."""
    return AsyncMock()


@pytest.fixture
def mock_exchange():
    """Create a mock ExchangeClient."""
    exchange = MagicMock()
    exchange.get_btc_balance = AsyncMock(return_value=1.0)
    exchange.get_usd_balance = AsyncMock(return_value=5000.0)
    return exchange


@pytest.fixture
def mock_bot():
    """Create a mock Bot with trading pair configuration."""
    bot = MagicMock()
    bot.id = 42
    bot.product_id = "ETH-BTC"
    bot.get_trading_pairs = MagicMock(return_value=["ETH-BTC", "SOL-BTC"])
    return bot


@pytest.fixture
def mock_strategy():
    """Create a mock TradingStrategy."""
    return MagicMock()


@pytest.fixture
def engine(mock_db, mock_exchange, mock_bot, mock_strategy):
    """Create a StrategyTradingEngine with default product_id (from bot)."""
    return StrategyTradingEngine(
        db=mock_db,
        exchange=mock_exchange,
        bot=mock_bot,
        strategy=mock_strategy,
    )


@pytest.fixture
def engine_explicit_pair(mock_db, mock_exchange, mock_bot, mock_strategy):
    """Create a StrategyTradingEngine with an explicit product_id."""
    return StrategyTradingEngine(
        db=mock_db,
        exchange=mock_exchange,
        bot=mock_bot,
        strategy=mock_strategy,
        product_id="ADA-USD",
    )


# ===========================================================================
# Initialization
# ===========================================================================


class TestStrategyTradingEngineInit:
    """Tests for StrategyTradingEngine.__init__()"""

    def test_init_stores_all_attributes(self, mock_db, mock_exchange, mock_bot, mock_strategy):
        """Happy path: all init args are stored as attributes."""
        eng = StrategyTradingEngine(mock_db, mock_exchange, mock_bot, mock_strategy)
        assert eng.db is mock_db
        assert eng.exchange is mock_exchange
        assert eng.bot is mock_bot
        assert eng.strategy is mock_strategy

    def test_init_creates_trading_client(self, engine, mock_exchange):
        """Happy path: a TradingClient is created wrapping the exchange."""
        assert isinstance(engine.trading_client, TradingClient)
        assert engine.trading_client.exchange is mock_exchange

    def test_init_uses_first_trading_pair_when_no_product_id(self, engine):
        """Happy path: product_id defaults to bot's first trading pair."""
        assert engine.product_id == "ETH-BTC"

    def test_init_uses_explicit_product_id(self, engine_explicit_pair):
        """Edge case: explicit product_id overrides bot's pairs."""
        assert engine_explicit_pair.product_id == "ADA-USD"

    def test_init_quote_currency_from_product_id(self, engine):
        """Happy path: quote_currency derived from product_id."""
        assert engine.quote_currency == "BTC"

    def test_init_quote_currency_usd_pair(self, engine_explicit_pair):
        """Edge case: USD quote currency extracted correctly."""
        assert engine_explicit_pair.quote_currency == "USD"

    def test_init_fallback_to_product_id_attr(self, mock_db, mock_exchange, mock_strategy):
        """Edge case: bot without get_trading_pairs falls back to product_id attr."""
        bot = MagicMock(spec=[])  # empty spec — no get_trading_pairs
        bot.product_id = "SOL-USD"
        # hasattr(bot, 'get_trading_pairs') will be False with spec=[]
        eng = StrategyTradingEngine(mock_db, mock_exchange, bot, mock_strategy)
        assert eng.product_id == "SOL-USD"


# ===========================================================================
# Delegation: save_ai_log
# ===========================================================================


class TestSaveAiLog:
    """Tests for StrategyTradingEngine.save_ai_log()"""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.order_logger")
    async def test_save_ai_log_delegates_correctly(self, mock_logger_mod, engine):
        """Happy path: save_ai_log delegates to order_logger module."""
        mock_logger_mod.save_ai_log = AsyncMock()
        signal_data = {"action": "buy", "confidence": 0.8}
        mock_position = MagicMock()

        await engine.save_ai_log(signal_data, "buy", 50000.0, mock_position)

        mock_logger_mod.save_ai_log.assert_awaited_once_with(
            engine.db, engine.bot, engine.product_id,
            signal_data, "buy", 50000.0, mock_position
        )

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.order_logger")
    async def test_save_ai_log_with_none_position(self, mock_logger_mod, engine):
        """Edge case: position can be None (no active position)."""
        mock_logger_mod.save_ai_log = AsyncMock()

        await engine.save_ai_log({"action": "hold"}, "hold", 45000.0, None)

        mock_logger_mod.save_ai_log.assert_awaited_once_with(
            engine.db, engine.bot, engine.product_id,
            {"action": "hold"}, "hold", 45000.0, None
        )


# ===========================================================================
# Delegation: get_active_position
# ===========================================================================


class TestGetActivePosition:
    """Tests for StrategyTradingEngine.get_active_position()"""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.position_manager")
    async def test_get_active_position_delegates(self, mock_pm, engine):
        """Happy path: delegates to position_manager and returns result."""
        mock_position = MagicMock()
        mock_pm.get_active_position = AsyncMock(return_value=mock_position)

        result = await engine.get_active_position()

        assert result is mock_position
        mock_pm.get_active_position.assert_awaited_once_with(engine.db, engine.bot, engine.product_id)

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.position_manager")
    async def test_get_active_position_returns_none(self, mock_pm, engine):
        """Edge case: no active position returns None."""
        mock_pm.get_active_position = AsyncMock(return_value=None)

        result = await engine.get_active_position()
        assert result is None


# ===========================================================================
# Delegation: get_open_positions_count
# ===========================================================================


class TestGetOpenPositionsCount:
    """Tests for StrategyTradingEngine.get_open_positions_count()"""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.position_manager")
    async def test_get_open_positions_count_delegates(self, mock_pm, engine):
        """Happy path: returns count from position_manager."""
        mock_pm.get_open_positions_count = AsyncMock(return_value=3)

        result = await engine.get_open_positions_count()

        assert result == 3
        mock_pm.get_open_positions_count.assert_awaited_once_with(engine.db, engine.bot)

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.position_manager")
    async def test_get_open_positions_count_zero(self, mock_pm, engine):
        """Edge case: zero open positions."""
        mock_pm.get_open_positions_count = AsyncMock(return_value=0)

        result = await engine.get_open_positions_count()
        assert result == 0


# ===========================================================================
# Delegation: create_position
# ===========================================================================


class TestCreatePosition:
    """Tests for StrategyTradingEngine.create_position()"""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.position_manager")
    async def test_create_position_delegates(self, mock_pm, engine):
        """Happy path: creates position via position_manager."""
        mock_pos = MagicMock()
        mock_pm.create_position = AsyncMock(return_value=mock_pos)

        result = await engine.create_position(quote_balance=1.0, quote_amount=0.1)

        assert result is mock_pos
        mock_pm.create_position.assert_awaited_once_with(
            engine.db, engine.exchange, engine.bot, engine.product_id,
            1.0, 0.1, pattern_data=None
        )

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.position_manager")
    async def test_create_position_with_pattern_data(self, mock_pm, engine):
        """Edge case: pattern_data is forwarded correctly."""
        mock_pm.create_position = AsyncMock(return_value=MagicMock())
        pattern = {"pattern": "double_bottom", "confidence": 0.9}

        await engine.create_position(quote_balance=2.0, quote_amount=0.5, pattern_data=pattern)

        call_kwargs = mock_pm.create_position.call_args
        assert call_kwargs.kwargs["pattern_data"] == pattern


# ===========================================================================
# Delegation: log_order_to_history
# ===========================================================================


class TestLogOrderToHistory:
    """Tests for StrategyTradingEngine.log_order_to_history()"""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.order_logger")
    async def test_log_order_to_history_delegates(self, mock_ol, engine):
        """Happy path: log_order_to_history delegates all args."""
        mock_ol.log_order_to_history = AsyncMock()
        mock_position = MagicMock()

        await engine.log_order_to_history(
            position=mock_position,
            side="BUY",
            order_type="market",
            trade_type="base_order",
            quote_amount=0.01,
            price=0.035,
            status="filled",
        )

        mock_ol.log_order_to_history.assert_awaited_once_with(
            engine.db, engine.bot, engine.product_id,
            mock_position, "BUY", "market", "base_order",
            0.01, 0.035, "filled",
        )

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.order_logger")
    async def test_log_order_to_history_with_kwargs(self, mock_ol, engine):
        """Edge case: extra kwargs are forwarded."""
        mock_ol.log_order_to_history = AsyncMock()

        await engine.log_order_to_history(
            position=None,
            side="SELL",
            order_type="limit",
            trade_type="take_profit",
            quote_amount=100.0,
            price=65000.0,
            status="pending",
            order_id="extra-123",
        )

        call_kwargs = mock_ol.log_order_to_history.call_args
        assert call_kwargs.kwargs.get("order_id") == "extra-123"


# ===========================================================================
# Delegation: execute_buy
# ===========================================================================


class TestExecuteBuy:
    """Tests for StrategyTradingEngine.execute_buy()"""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.buy_executor")
    async def test_execute_buy_delegates(self, mock_be, engine):
        """Happy path: execute_buy delegates to buy_executor module."""
        mock_trade = MagicMock()
        mock_be.execute_buy = AsyncMock(return_value=mock_trade)
        mock_position = MagicMock()

        result = await engine.execute_buy(
            position=mock_position,
            quote_amount=0.01,
            current_price=0.035,
            trade_type="base_order",
        )

        assert result is mock_trade
        mock_be.execute_buy.assert_awaited_once_with(
            engine.db, engine.exchange, engine.trading_client,
            engine.bot, engine.product_id,
            mock_position, 0.01, 0.035, "base_order",
            None,   # signal_data default
            True,   # commit_on_error default
        )

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.buy_executor")
    async def test_execute_buy_with_signal_data(self, mock_be, engine):
        """Edge case: signal_data and commit_on_error are forwarded."""
        mock_be.execute_buy = AsyncMock(return_value=None)
        signal = {"action": "buy", "score": 0.85}

        await engine.execute_buy(
            position=MagicMock(),
            quote_amount=0.02,
            current_price=0.04,
            trade_type="dca",
            signal_data=signal,
            commit_on_error=False,
        )

        call_args = mock_be.execute_buy.call_args[0]
        assert call_args[9] == signal        # signal_data
        assert call_args[10] is False        # commit_on_error


# ===========================================================================
# Delegation: execute_limit_buy
# ===========================================================================


class TestExecuteLimitBuy:
    """Tests for StrategyTradingEngine.execute_limit_buy()"""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.buy_executor")
    async def test_execute_limit_buy_delegates(self, mock_be, engine):
        """Happy path: execute_limit_buy delegates to buy_executor module."""
        mock_pending = MagicMock()
        mock_be.execute_limit_buy = AsyncMock(return_value=mock_pending)

        result = await engine.execute_limit_buy(
            position=MagicMock(),
            quote_amount=0.01,
            limit_price=0.033,
            trade_type="base_order",
        )

        assert result is mock_pending
        mock_be.execute_limit_buy.assert_awaited_once()


# ===========================================================================
# Delegation: execute_sell
# ===========================================================================


class TestExecuteSell:
    """Tests for StrategyTradingEngine.execute_sell()"""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.sell_executor")
    async def test_execute_sell_delegates(self, mock_se, engine):
        """Happy path: execute_sell delegates and returns tuple."""
        mock_trade = MagicMock()
        mock_se.execute_sell = AsyncMock(return_value=(mock_trade, 0.05, 10.0))

        result = await engine.execute_sell(
            position=MagicMock(),
            current_price=0.04,
        )

        assert result == (mock_trade, 0.05, 10.0)
        mock_se.execute_sell.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.sell_executor")
    async def test_execute_sell_with_signal_data(self, mock_se, engine):
        """Edge case: signal_data is forwarded."""
        mock_se.execute_sell = AsyncMock(return_value=(None, 0.0, 0.0))
        signal = {"action": "sell"}

        await engine.execute_sell(
            position=MagicMock(),
            current_price=0.04,
            signal_data=signal,
        )

        call_args = mock_se.execute_sell.call_args[0]
        assert call_args[7] == signal  # signal_data is 8th positional arg


# ===========================================================================
# Delegation: execute_limit_sell
# ===========================================================================


class TestExecuteLimitSell:
    """Tests for StrategyTradingEngine.execute_limit_sell()"""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.sell_executor")
    async def test_execute_limit_sell_delegates(self, mock_se, engine):
        """Happy path: execute_limit_sell delegates to sell_executor module."""
        mock_pending = MagicMock()
        mock_se.execute_limit_sell = AsyncMock(return_value=mock_pending)

        result = await engine.execute_limit_sell(
            position=MagicMock(),
            base_amount=1.5,
            limit_price=0.04,
        )

        assert result is mock_pending
        mock_se.execute_limit_sell.assert_awaited_once()


# ===========================================================================
# Delegation: process_signal
# ===========================================================================


class TestProcessSignal:
    """Tests for StrategyTradingEngine.process_signal()"""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.signal_processor")
    async def test_process_signal_delegates(self, mock_sp, engine):
        """Happy path: process_signal delegates to signal_processor module."""
        mock_sp.process_signal = AsyncMock(return_value={"action": "hold"})
        mock_sp._POSITION_NOT_SET = signal_processor._POSITION_NOT_SET
        candles = [{"close": 0.035}]

        result = await engine.process_signal(candles, current_price=0.035)

        assert result == {"action": "hold"}
        mock_sp.process_signal.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.signal_processor")
    async def test_process_signal_with_pre_analyzed(self, mock_sp, engine):
        """Edge case: pre_analyzed_signal is forwarded."""
        mock_sp.process_signal = AsyncMock(return_value={"action": "buy"})
        mock_sp._POSITION_NOT_SET = signal_processor._POSITION_NOT_SET
        pre_analyzed = {"indicator": "macd", "signal": "bullish"}

        await engine.process_signal(
            candles=[],
            current_price=0.04,
            pre_analyzed_signal=pre_analyzed,
        )

        call_args = mock_sp.process_signal.call_args[0]
        assert call_args[8] == pre_analyzed  # pre_analyzed_signal

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.signal_processor")
    async def test_process_signal_with_position_override(self, mock_sp, engine):
        """Edge case: position_override is forwarded when provided."""
        mock_sp.process_signal = AsyncMock(return_value={"action": "sell"})
        mock_sp._POSITION_NOT_SET = signal_processor._POSITION_NOT_SET
        mock_pos = MagicMock()

        await engine.process_signal(
            candles=[],
            current_price=0.04,
            position_override=mock_pos,
        )

        call_kwargs = mock_sp.process_signal.call_args.kwargs
        assert call_kwargs["position_override"] is mock_pos

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.signal_processor")
    async def test_process_signal_with_candles_by_timeframe(self, mock_sp, engine):
        """Edge case: candles_by_timeframe dict is forwarded."""
        mock_sp.process_signal = AsyncMock(return_value={"action": "hold"})
        mock_sp._POSITION_NOT_SET = signal_processor._POSITION_NOT_SET
        multi_tf = {
            "ONE_HOUR": [{"close": 0.035}],
            "FOUR_HOUR": [{"close": 0.034}],
        }

        await engine.process_signal(
            candles=[],
            current_price=0.035,
            candles_by_timeframe=multi_tf,
        )

        call_args = mock_sp.process_signal.call_args[0]
        assert call_args[9] == multi_tf  # candles_by_timeframe


# ===========================================================================
# Failure / error propagation tests
# ===========================================================================


class TestErrorPropagation:
    """Tests verifying errors from delegate modules propagate through the engine."""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.order_logger")
    async def test_save_ai_log_error_propagates(self, mock_ol, engine):
        """Failure: DB error from save_ai_log propagates."""
        mock_ol.save_ai_log = AsyncMock(side_effect=RuntimeError("DB write failed"))
        with pytest.raises(RuntimeError, match="DB write failed"):
            await engine.save_ai_log({"action": "buy"}, "buy", 50000.0, None)

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.position_manager")
    async def test_get_active_position_error_propagates(self, mock_pm, engine):
        """Failure: DB error from get_active_position propagates."""
        mock_pm.get_active_position = AsyncMock(
            side_effect=Exception("Database connection lost")
        )
        with pytest.raises(Exception, match="Database connection lost"):
            await engine.get_active_position()

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.position_manager")
    async def test_get_open_positions_count_error_propagates(self, mock_pm, engine):
        """Failure: DB error from get_open_positions_count propagates."""
        mock_pm.get_open_positions_count = AsyncMock(
            side_effect=Exception("Query timeout")
        )
        with pytest.raises(Exception, match="Query timeout"):
            await engine.get_open_positions_count()

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.position_manager")
    async def test_create_position_error_propagates(self, mock_pm, engine):
        """Failure: error from create_position propagates."""
        mock_pm.create_position = AsyncMock(
            side_effect=ValueError("Invalid quote amount")
        )
        with pytest.raises(ValueError, match="Invalid quote amount"):
            await engine.create_position(quote_balance=1.0, quote_amount=-0.1)

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.order_logger")
    async def test_log_order_to_history_error_propagates(self, mock_ol, engine):
        """Failure: error from log_order_to_history propagates."""
        mock_ol.log_order_to_history = AsyncMock(
            side_effect=RuntimeError("Logging failed")
        )
        with pytest.raises(RuntimeError, match="Logging failed"):
            await engine.log_order_to_history(
                position=None, side="BUY", order_type="market",
                trade_type="initial", quote_amount=0.01, price=0.035, status="failed",
            )

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.buy_executor")
    async def test_execute_buy_error_propagates(self, mock_be, engine):
        """Failure: exchange error from execute_buy propagates."""
        mock_be.execute_buy = AsyncMock(
            side_effect=ValueError("Insufficient funds")
        )
        with pytest.raises(ValueError, match="Insufficient funds"):
            await engine.execute_buy(
                position=MagicMock(), quote_amount=0.01,
                current_price=0.035, trade_type="initial",
            )

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.buy_executor")
    async def test_execute_limit_buy_error_propagates(self, mock_be, engine):
        """Failure: exchange error from execute_limit_buy propagates."""
        mock_be.execute_limit_buy = AsyncMock(
            side_effect=ValueError("No order_id returned")
        )
        with pytest.raises(ValueError, match="No order_id returned"):
            await engine.execute_limit_buy(
                position=MagicMock(), quote_amount=0.01,
                limit_price=0.033, trade_type="initial",
            )

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.sell_executor")
    async def test_execute_sell_error_propagates(self, mock_se, engine):
        """Failure: exchange error from execute_sell propagates."""
        mock_se.execute_sell = AsyncMock(
            side_effect=RuntimeError("Sell order rejected")
        )
        with pytest.raises(RuntimeError, match="Sell order rejected"):
            await engine.execute_sell(
                position=MagicMock(), current_price=0.04,
            )

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.sell_executor")
    async def test_execute_limit_sell_error_propagates(self, mock_se, engine):
        """Failure: exchange error from execute_limit_sell propagates."""
        mock_se.execute_limit_sell = AsyncMock(
            side_effect=ValueError("PropGuard blocked")
        )
        with pytest.raises(ValueError, match="PropGuard blocked"):
            await engine.execute_limit_sell(
                position=MagicMock(), base_amount=1.0, limit_price=0.04,
            )

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.signal_processor")
    async def test_process_signal_error_propagates(self, mock_sp, engine):
        """Failure: error from signal_processor propagates."""
        mock_sp.process_signal = AsyncMock(
            side_effect=Exception("Strategy calculation error")
        )
        mock_sp._POSITION_NOT_SET = signal_processor._POSITION_NOT_SET
        with pytest.raises(Exception, match="Strategy calculation error"):
            await engine.process_signal(candles=[], current_price=0.035)


# ===========================================================================
# Additional edge cases for delegation methods
# ===========================================================================


class TestAdditionalDelegationEdgeCases:
    """Additional edge case tests for delegation methods."""

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.buy_executor")
    async def test_execute_limit_buy_with_signal_data(self, mock_be, engine):
        """Edge case: signal_data is forwarded to execute_limit_buy."""
        mock_pending = MagicMock()
        mock_be.execute_limit_buy = AsyncMock(return_value=mock_pending)
        signal = {"indicator": "macd", "signal": "bullish"}

        result = await engine.execute_limit_buy(
            position=MagicMock(), quote_amount=0.01,
            limit_price=0.033, trade_type="initial", signal_data=signal,
        )

        assert result is mock_pending
        call_args = mock_be.execute_limit_buy.call_args[0]
        assert call_args[9] == signal  # signal_data is 10th positional arg

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.sell_executor")
    async def test_execute_limit_sell_with_signal_data(self, mock_se, engine):
        """Edge case: signal_data is forwarded to execute_limit_sell."""
        mock_pending = MagicMock()
        mock_se.execute_limit_sell = AsyncMock(return_value=mock_pending)
        signal = {"indicator": "rsi", "signal": "overbought"}

        result = await engine.execute_limit_sell(
            position=MagicMock(), base_amount=1.5,
            limit_price=0.04, signal_data=signal,
        )

        assert result is mock_pending
        call_args = mock_se.execute_limit_sell.call_args[0]
        assert call_args[8] == signal  # signal_data is 9th positional arg

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.buy_executor")
    async def test_execute_buy_returns_none_for_limit_order(self, mock_be, engine):
        """Edge case: execute_buy can return None (when limit order placed)."""
        mock_be.execute_buy = AsyncMock(return_value=None)

        result = await engine.execute_buy(
            position=MagicMock(), quote_amount=0.01,
            current_price=0.035, trade_type="initial",
        )

        assert result is None

    @pytest.mark.asyncio
    @patch("app.trading_engine_v2.sell_executor")
    async def test_execute_sell_returns_none_tuple_for_limit(self, mock_se, engine):
        """Edge case: execute_sell returns (None, 0.0, 0.0) when limit placed."""
        mock_se.execute_sell = AsyncMock(return_value=(None, 0.0, 0.0))

        trade, profit, pct = await engine.execute_sell(
            position=MagicMock(), current_price=0.04,
        )

        assert trade is None
        assert profit == 0.0
        assert pct == 0.0


# ===========================================================================
# Init edge cases
# ===========================================================================


class TestInitEdgeCases:
    """Additional init edge cases."""

    def test_init_with_usd_pair_explicit(self, mock_db, mock_exchange, mock_bot, mock_strategy):
        """Edge case: explicit USD pair sets quote_currency to USD."""
        eng = StrategyTradingEngine(
            mock_db, mock_exchange, mock_bot, mock_strategy,
            product_id="BTC-USDT",
        )
        assert eng.product_id == "BTC-USDT"
        assert eng.quote_currency == "USDT"

    def test_init_trading_client_wraps_same_exchange(
        self, mock_db, mock_exchange, mock_bot, mock_strategy
    ):
        """Happy path: trading_client.exchange is the same instance passed to engine."""
        eng = StrategyTradingEngine(mock_db, mock_exchange, mock_bot, mock_strategy)
        assert eng.trading_client.exchange is mock_exchange
        assert eng.exchange is mock_exchange

    def test_init_with_empty_product_ids_uses_first_pair(
        self, mock_db, mock_exchange, mock_strategy
    ):
        """Edge case: bot with get_trading_pairs returning single pair."""
        bot = MagicMock()
        bot.id = 99
        bot.get_trading_pairs = MagicMock(return_value=["BTC-USD"])
        eng = StrategyTradingEngine(mock_db, mock_exchange, bot, mock_strategy)
        assert eng.product_id == "BTC-USD"
        assert eng.quote_currency == "USD"
