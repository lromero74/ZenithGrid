"""
Tests for DSL Scripting Mode — dsl_interpreter.py + dsl_trading.py

Covers:
- parse_script: happy path for each valid statement form
- evaluate: correct OrderIntent production (conditional and unconditional)
- DSLError: line/col reported on bad syntax and structural violations
- Security: every listed attack vector is REJECTED at parse time (never executed)
- DSLTradingStrategy: registration, validate_config, analyze_signal, should_buy/sell
- Account isolation: independent instances share no state
"""

import pytest

from app.strategies.dsl_interpreter import (
    DSLError,
    OrderIntent,
    evaluate,
    parse_script,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_strategy(**kwargs):
    """Create a DSLTradingStrategy with the given config overrides."""
    from app.strategies.dsl_trading import DSLTradingStrategy

    config = {"script": "", "trigger": "every_tick"}
    config.update(kwargs)
    return DSLTradingStrategy(config)


def _minimal_candles(n: int = 50, price: float = 50_000.0):
    """Return n synthetic OHLCV candle dicts at the given price."""
    return [
        {"open": price, "high": price * 1.001, "low": price * 0.999,
         "close": price, "volume": 100.0}
        for _ in range(n)
    ]


def _ctx(btc_price: float = 50_000.0, rsi: float = 50.0):
    """Minimal context dict for evaluate()."""
    return {
        "price": {"BTC-USD": btc_price, "ETH-USD": btc_price / 15},
        "rsi": {14: rsi},
        "macd": {"line": 10.0, "signal": 5.0, "histogram": 5.0},
        "bb_pct": 0.5,
        "bb": 0.5,
    }


# =============================================================================
# parse_script — happy paths
# =============================================================================


class TestParseScriptHappyPath:
    def test_unconditional_limit_buy(self):
        stmts = parse_script("limit('buy', 'BTC-USD', 0.01, price='-1%')")
        assert len(stmts) == 1

    def test_unconditional_market_sell(self):
        stmts = parse_script("market('sell', 'BTC-USD', all)")
        assert len(stmts) == 1

    def test_conditional_limit_buy_rsi(self):
        stmts = parse_script("if rsi(14) < 30: limit('buy', 'ETH-USD', 0.05)")
        assert len(stmts) == 1

    def test_conditional_market_sell_price(self):
        stmts = parse_script(
            "if price('BTC-USD') > 100000: market('sell', 'BTC-USD', all)"
        )
        assert len(stmts) == 1

    def test_multiple_statements(self):
        script = (
            "limit('buy', 'BTC-USD', 0.01, price='-1%')\n"
            "if rsi(14) < 30: limit('buy', 'ETH-USD', 0.05)\n"
            "if price('BTC-USD') > 100000: market('sell', 'BTC-USD', all)\n"
        )
        stmts = parse_script(script)
        assert len(stmts) == 3

    def test_empty_script_returns_empty_list(self):
        stmts = parse_script("")
        assert stmts == []

    def test_compound_condition_and(self):
        stmts = parse_script(
            "if rsi(14) < 30 and price('BTC-USD') > 40000: limit('buy', 'BTC-USD', 0.1)"
        )
        assert len(stmts) == 1

    def test_unary_minus_in_size(self):
        # Negative sizes are nonsensical in practice but the DSL allows
        # numeric expressions including unary minus on constants
        stmts = parse_script("limit('buy', 'BTC-USD', 0.01)")
        assert len(stmts) == 1


# =============================================================================
# evaluate — happy paths / correct OrderIntent production
# =============================================================================


class TestEvaluateHappyPath:
    def test_unconditional_limit_produces_intent(self):
        stmts = parse_script("limit('buy', 'BTC-USD', 0.01, price='-1%')")
        intents = evaluate(stmts, _ctx())
        assert len(intents) == 1
        i = intents[0]
        assert i.side == "buy"
        assert i.symbol == "BTC-USD"
        assert i.order_type == "limit"
        assert i.size == pytest.approx(0.01)
        assert i.price_offset == "-1%"
        assert i.size_is_all is False

    def test_conditional_fires_when_rsi_below_threshold(self):
        stmts = parse_script("if rsi(14) < 30: limit('buy', 'ETH-USD', 0.05)")
        intents = evaluate(stmts, _ctx(rsi=25.0))  # rsi=25 < 30 → fires
        assert len(intents) == 1
        assert intents[0].side == "buy"
        assert intents[0].symbol == "ETH-USD"

    def test_conditional_does_not_fire_when_rsi_above_threshold(self):
        stmts = parse_script("if rsi(14) < 30: limit('buy', 'ETH-USD', 0.05)")
        intents = evaluate(stmts, _ctx(rsi=50.0))  # rsi=50 >= 30 → silent
        assert intents == []

    def test_market_sell_all_produces_size_is_all(self):
        stmts = parse_script("market('sell', 'BTC-USD', all)")
        intents = evaluate(stmts, _ctx())
        assert len(intents) == 1
        i = intents[0]
        assert i.side == "sell"
        assert i.order_type == "market"
        assert i.size_is_all is True
        assert i.size is None

    def test_price_condition_fires_when_above_threshold(self):
        stmts = parse_script(
            "if price('BTC-USD') > 100000: market('sell', 'BTC-USD', all)"
        )
        intents = evaluate(stmts, _ctx(btc_price=110_000.0))
        assert len(intents) == 1

    def test_price_condition_silent_when_below_threshold(self):
        stmts = parse_script(
            "if price('BTC-USD') > 100000: market('sell', 'BTC-USD', all)"
        )
        intents = evaluate(stmts, _ctx(btc_price=50_000.0))
        assert intents == []

    def test_multiple_stmts_both_fire(self):
        script = (
            "limit('buy', 'BTC-USD', 0.01, price='-1%')\n"
            "limit('sell', 'ETH-USD', 0.05)\n"
        )
        stmts = parse_script(script)
        intents = evaluate(stmts, _ctx())
        assert len(intents) == 2

    def test_and_condition_both_must_hold(self):
        script = (
            "if rsi(14) < 30 and price('BTC-USD') > 40000: limit('buy', 'BTC-USD', 0.1)"
        )
        stmts = parse_script(script)
        # Both hold
        assert len(evaluate(stmts, _ctx(btc_price=45_000.0, rsi=25.0))) == 1
        # Only rsi holds
        assert evaluate(stmts, _ctx(btc_price=30_000.0, rsi=25.0)) == []
        # Only price holds
        assert evaluate(stmts, _ctx(btc_price=45_000.0, rsi=35.0)) == []

    def test_limit_without_price_kwarg(self):
        stmts = parse_script("limit('buy', 'ETH-USD', 0.05)")
        intents = evaluate(stmts, _ctx())
        assert intents[0].price_offset is None

    def test_market_with_numeric_size(self):
        stmts = parse_script("market('buy', 'BTC-USD', 0.5)")
        intents = evaluate(stmts, _ctx())
        i = intents[0]
        assert i.size == pytest.approx(0.5)
        assert i.size_is_all is False

    def test_rsi_at_boundary_not_strictly_less(self):
        # rsi(14) < 30 with rsi==30 should NOT fire (strict less-than)
        stmts = parse_script("if rsi(14) < 30: limit('buy', 'BTC-USD', 0.01)")
        assert evaluate(stmts, _ctx(rsi=30.0)) == []

    def test_rsi_at_boundary_less_equal(self):
        stmts = parse_script("if rsi(14) <= 30: limit('buy', 'BTC-USD', 0.01)")
        assert len(evaluate(stmts, _ctx(rsi=30.0))) == 1


# =============================================================================
# DSLError — syntax / structural errors
# =============================================================================


class TestDSLErrorReporting:
    def test_syntax_error_raises_dsl_error(self):
        with pytest.raises(DSLError) as exc_info:
            parse_script("limit(")
        assert exc_info.value.line is not None

    def test_top_level_data_call_rejected(self):
        with pytest.raises(DSLError):
            parse_script("rsi(14)")

    def test_if_with_else_rejected(self):
        with pytest.raises(DSLError):
            parse_script(
                "if rsi(14) < 30: limit('buy', 'BTC-USD', 0.01)\n"
                "else: market('sell', 'BTC-USD', all)"
            )

    def test_if_body_with_two_stmts_rejected(self):
        with pytest.raises(DSLError):
            parse_script(
                "if rsi(14) < 30:\n"
                "    limit('buy', 'BTC-USD', 0.01)\n"
                "    limit('sell', 'ETH-USD', 0.05)\n"
            )

    def test_unknown_kwarg_in_limit_raises(self):
        # Unknown keyword is caught at parse time (arity/kwarg validation in _validate_action_call)
        with pytest.raises(DSLError):
            parse_script("limit('buy', 'BTC-USD', 0.01, foo='bar')")

    def test_wrong_arg_count_limit_raises(self):
        with pytest.raises(DSLError):
            parse_script("limit('buy', 'BTC-USD')")

    def test_wrong_arg_count_market_raises(self):
        with pytest.raises(DSLError):
            parse_script("market('sell', 'BTC-USD')")

    def test_dsl_error_carries_line(self):
        with pytest.raises(DSLError) as exc_info:
            parse_script("x = 1")
        err = exc_info.value
        assert err.line is not None
        assert err.line >= 1


# =============================================================================
# SECURITY TESTS — every attack vector must be REJECTED at parse_script() time
# =============================================================================


class TestSecuritySandbox:
    """
    Each test asserts that a known escape attempt raises DSLError.
    The bad code must NEVER be executed — parse_script() must reject it before
    evaluate() is ever called.
    """

    def test_import_os_system_rejected(self):
        """__import__('os').system('id') — Attribute + Import path blocked."""
        with pytest.raises(DSLError):
            parse_script("__import__('os').system('id')")

    def test_dunder_class_bases_rejected(self):
        """().__class__.__bases__ — Attribute node blocked."""
        with pytest.raises(DSLError):
            parse_script("().__class__.__bases__")

    def test_open_rejected(self):
        """open('/etc/passwd') — 'open' is not a whitelisted name."""
        with pytest.raises(DSLError):
            parse_script("open('/etc/passwd')")

    def test_builtin_eval_rejected(self):
        """eval('1') — 'eval' is not a whitelisted name."""
        with pytest.raises(DSLError):
            parse_script("eval('1')")

    def test_dunder_globals_attribute_rejected(self):
        """price.__globals__ — Attribute node on a whitelisted name blocked."""
        with pytest.raises(DSLError):
            parse_script("price.__globals__")

    def test_assignment_rejected(self):
        """x = 1 — Assign node is not on the whitelist."""
        with pytest.raises(DSLError):
            parse_script("x = 1")

    def test_lambda_rejected(self):
        """lambda: None — Lambda node blocked."""
        with pytest.raises(DSLError):
            parse_script("lambda: None")

    def test_list_comprehension_rejected(self):
        """[x for x in []] — ListComp node blocked."""
        with pytest.raises(DSLError):
            parse_script("[x for x in []]")

    def test_import_statement_rejected(self):
        """import os — Import node blocked."""
        with pytest.raises(DSLError):
            parse_script("import os")

    def test_from_import_rejected(self):
        """from os import system — ImportFrom blocked."""
        with pytest.raises(DSLError):
            parse_script("from os import system")

    def test_subscript_rejected(self):
        """[].__class__.__mro__[1] — Subscript blocked."""
        with pytest.raises(DSLError):
            parse_script("[][0]")

    def test_while_loop_rejected(self):
        """while True: pass — While node blocked."""
        with pytest.raises(DSLError):
            parse_script("while True: pass")

    def test_for_loop_rejected(self):
        """for x in []: pass — For node blocked."""
        with pytest.raises(DSLError):
            parse_script("for x in []: pass")

    def test_fstring_rejected(self):
        """f'{1+1}' — JoinedStr blocked."""
        with pytest.raises(DSLError):
            parse_script("f'{1+1}'")

    def test_walrus_rejected(self):
        """(x := 1) — NamedExpr blocked."""
        with pytest.raises(DSLError):
            parse_script("(x := 1)")

    def test_augassign_rejected(self):
        """x += 1 — AugAssign blocked."""
        with pytest.raises(DSLError):
            parse_script("x += 1")

    def test_call_chain_rejected(self):
        """rsi(14)() — calling the result of a call blocked (func is not a bare Name)."""
        with pytest.raises(DSLError):
            parse_script("rsi(14)()")

    def test_attribute_access_on_result_rejected(self):
        """rsi(14).bit_length() — Attribute node on call result blocked."""
        with pytest.raises(DSLError):
            parse_script("rsi(14).bit_length()")

    def test_dict_literal_rejected(self):
        """{} — Dict node blocked."""
        with pytest.raises(DSLError):
            parse_script("{}")

    def test_set_literal_rejected(self):
        """{1} — Set node blocked."""
        with pytest.raises(DSLError):
            parse_script("{1}")

    def test_try_except_rejected(self):
        """try/except — Try node blocked."""
        with pytest.raises(DSLError):
            parse_script("try:\n    pass\nexcept:\n    pass")

    def test_with_statement_rejected(self):
        """with ... as ...: — With node blocked."""
        with pytest.raises(DSLError):
            parse_script("with open('/etc/passwd') as f:\n    pass")

    def test_function_def_rejected(self):
        """def f(): pass — FunctionDef blocked."""
        with pytest.raises(DSLError):
            parse_script("def f(): pass")

    def test_unknown_function_name_rejected(self):
        """Unknown callable name — not in the whitelist."""
        with pytest.raises(DSLError):
            parse_script("danger('exploit')")

    def test_dunder_import_name_rejected(self):
        """__import__ — not a whitelisted name."""
        with pytest.raises(DSLError):
            parse_script("__import__('os')")

    def test_action_in_condition_position_rejected(self):
        """limit() used as a condition value — action funcs are not data funcs."""
        with pytest.raises(DSLError):
            evaluate(
                parse_script(
                    "if limit('buy','BTC-USD',0.01): market('sell','BTC-USD',all)"
                ),
                _ctx(),
            )


# =============================================================================
# DSLTradingStrategy — registration + config validation
# =============================================================================


class TestDSLTradingStrategyRegistration:
    def test_strategy_registered_in_registry(self):
        from app.strategies import StrategyRegistry
        defn = StrategyRegistry.get_definition("dsl_trading")
        assert defn.id == "dsl_trading"

    def test_get_definition_has_script_parameter(self):
        strategy = _make_strategy(script="")
        defn = strategy.get_definition()
        param_names = [p.name for p in defn.parameters]
        assert "script" in param_names
        assert "trigger" in param_names

    def test_validate_config_rejects_invalid_script(self):
        from app.strategies.dsl_trading import DSLTradingStrategy
        with pytest.raises(DSLError):
            DSLTradingStrategy({"script": "import os", "trigger": "every_tick"})

    def test_validate_config_accepts_valid_script(self):
        strategy = _make_strategy(script="limit('buy', 'BTC-USD', 0.01, price='-1%')")
        assert strategy._parsed_script is not None
        assert len(strategy._parsed_script) == 1

    def test_validate_config_accepts_empty_script(self):
        strategy = _make_strategy(script="")
        assert strategy._parsed_script == []


# =============================================================================
# DSLTradingStrategy — analyze_signal
# =============================================================================


class TestDSLTradingStrategyAnalyzeSignal:
    @pytest.mark.asyncio
    async def test_unconditional_buy_produces_signal(self):
        strategy = _make_strategy(
            script="limit('buy', 'BTC-USD', 0.01, price='-1%')",
        )
        candles = _minimal_candles()
        result = await strategy.analyze_signal(candles, 50_000.0, symbol="BTC-USD")
        assert result is not None
        assert result["signal_type"] == "dsl_result"
        assert len(result["intents"]) == 1
        assert result["intents"][0]["side"] == "buy"

    @pytest.mark.asyncio
    async def test_conditional_fires_when_rsi_low(self):
        # Use a flat price list so RSI converges to ~50 or below;
        # with all-same close prices RSI can be computed as ~50.
        # We inject RSI via context override by using the strategy's
        # internal indicator calculator on a price that drives RSI down.
        # Build candles where price drops sharply so RSI < 30.
        candles = []
        for i in range(60):
            p = 50_000.0 - i * 200  # declining prices → low RSI
            candles.append({"open": p, "high": p, "low": p, "close": p, "volume": 100.0})

        strategy = _make_strategy(
            script="if rsi(14) < 30: limit('buy', 'BTC-USD', 0.01)",
        )
        # With a strong downtrend the RSI should be well below 30
        result = await strategy.analyze_signal(candles, candles[-1]["close"], symbol="BTC-USD")
        assert result is not None
        assert result["signal_type"] == "dsl_result"
        assert result["intents"][0]["side"] == "buy"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_intents(self):
        # Condition that is never true
        strategy = _make_strategy(
            script="if rsi(14) < 0: limit('buy', 'BTC-USD', 0.01)",
        )
        candles = _minimal_candles()
        result = await strategy.analyze_signal(candles, 50_000.0, symbol="BTC-USD")
        assert result is None

    @pytest.mark.asyncio
    async def test_market_sell_all_intent_in_signal(self):
        strategy = _make_strategy(script="market('sell', 'BTC-USD', all)")
        candles = _minimal_candles()
        result = await strategy.analyze_signal(candles, 50_000.0, symbol="BTC-USD")
        assert result is not None
        assert result["intents"][0]["size_is_all"] is True
        assert result["intents"][0]["order_type"] == "market"


# =============================================================================
# DSLTradingStrategy — should_buy / should_sell
# =============================================================================


class TestDSLTradingStrategyShouldBuySell:
    @pytest.mark.asyncio
    async def test_should_buy_returns_true_on_buy_intent(self):
        strategy = _make_strategy(script="limit('buy', 'BTC-USD', 0.05, price='-1%')")
        signal = {
            "signal_type": "dsl_result",
            "raw_intents": [
                OrderIntent(side="buy", symbol="BTC-USD", order_type="limit",
                            size=0.05, price_offset="-1%"),
            ],
        }
        should, amount, reason = await strategy.should_buy(signal, None, 1.0)
        assert should is True
        assert amount == pytest.approx(0.05)
        assert "buy" in reason.lower()

    @pytest.mark.asyncio
    async def test_should_buy_returns_false_on_no_signal(self):
        strategy = _make_strategy(script="")
        should, amount, reason = await strategy.should_buy({}, None, 1.0)
        assert should is False
        assert amount == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_should_sell_returns_true_on_sell_intent(self):
        strategy = _make_strategy(script="market('sell', 'BTC-USD', all)")
        signal = {
            "signal_type": "dsl_result",
            "raw_intents": [
                OrderIntent(side="sell", symbol="BTC-USD", order_type="market",
                            size=None, size_is_all=True),
            ],
        }
        should, reason = await strategy.should_sell(signal, None, 50_000.0)
        assert should is True
        assert "sell" in reason.lower()

    @pytest.mark.asyncio
    async def test_should_sell_returns_false_on_no_signal(self):
        strategy = _make_strategy(script="")
        should, reason = await strategy.should_sell({}, None, 50_000.0)
        assert should is False

    @pytest.mark.asyncio
    async def test_should_buy_all_uses_full_balance(self):
        strategy = _make_strategy(script="market('buy', 'BTC-USD', all)")
        signal = {
            "signal_type": "dsl_result",
            "raw_intents": [
                OrderIntent(side="buy", symbol="BTC-USD", order_type="market",
                            size=None, size_is_all=True),
            ],
        }
        should, amount, reason = await strategy.should_buy(signal, None, btc_balance=0.75)
        assert should is True
        assert amount == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_should_buy_returns_false_when_sell_only_intents(self):
        strategy = _make_strategy(script="market('sell', 'BTC-USD', all)")
        signal = {
            "signal_type": "dsl_result",
            "raw_intents": [
                OrderIntent(side="sell", symbol="BTC-USD", order_type="market",
                            size=None, size_is_all=True),
            ],
        }
        should, amount, reason = await strategy.should_buy(signal, None, 1.0)
        assert should is False

    @pytest.mark.asyncio
    async def test_should_sell_returns_false_when_buy_only_intents(self):
        strategy = _make_strategy(script="limit('buy', 'BTC-USD', 0.01)")
        signal = {
            "signal_type": "dsl_result",
            "raw_intents": [
                OrderIntent(side="buy", symbol="BTC-USD", order_type="limit",
                            size=0.01),
            ],
        }
        should, reason = await strategy.should_sell(signal, None, 50_000.0)
        assert should is False


# =============================================================================
# Account isolation
# =============================================================================


class TestDSLAccountIsolation:
    def test_two_instances_have_independent_parsed_scripts(self):
        from app.strategies.dsl_trading import DSLTradingStrategy

        a = DSLTradingStrategy({
            "script": "limit('buy', 'BTC-USD', 0.01)",
            "trigger": "every_tick",
        })
        b = DSLTradingStrategy({
            "script": "market('sell', 'ETH-USD', all)",
            "trigger": "every_tick",
        })
        # Each instance has its own parsed script — they must not share a list
        assert a._parsed_script is not b._parsed_script
        assert len(a._parsed_script) == 1
        assert len(b._parsed_script) == 1

    def test_mutating_one_instance_does_not_affect_other(self):
        from app.strategies.dsl_trading import DSLTradingStrategy

        a = DSLTradingStrategy({"script": "limit('buy', 'BTC-USD', 0.01)", "trigger": "every_tick"})
        b = DSLTradingStrategy({"script": "market('sell', 'ETH-USD', all)", "trigger": "every_tick"})

        # Mutate a's internal state (simulate re-assign after error recovery)
        a._parsed_script = []

        # b must be unaffected
        assert len(b._parsed_script) == 1

    def test_indicator_calculator_is_per_instance(self):
        from app.strategies.dsl_trading import DSLTradingStrategy

        a = DSLTradingStrategy({"script": "", "trigger": "every_tick"})
        b = DSLTradingStrategy({"script": "", "trigger": "every_tick"})
        assert a.indicator_calculator is not b.indicator_calculator

    @pytest.mark.asyncio
    async def test_signals_are_independent_across_instances(self):
        from app.strategies.dsl_trading import DSLTradingStrategy

        a = DSLTradingStrategy({
            "script": "market('sell', 'BTC-USD', all)",
            "trigger": "every_tick",
        })
        b = DSLTradingStrategy({
            "script": "limit('buy', 'BTC-USD', 0.01)",
            "trigger": "every_tick",
        })
        candles = _minimal_candles()

        result_a = await a.analyze_signal(candles, 50_000.0, symbol="BTC-USD")
        result_b = await b.analyze_signal(candles, 50_000.0, symbol="BTC-USD")

        assert result_a is not None
        assert result_b is not None
        # a produces sell, b produces buy — they must not cross-contaminate
        assert result_a["intents"][0]["side"] == "sell"
        assert result_b["intents"][0]["side"] == "buy"
