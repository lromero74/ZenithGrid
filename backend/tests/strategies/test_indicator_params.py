"""
Tests for backend/app/strategies/indicator_params.py

Validates the INDICATOR_PARAMS data structure:
- All entries can be unpacked into StrategyParameter
- Required fields are present and correctly typed
- Groups are consistent
- Numeric constraints (min < max, defaults in range)
- Conditional visibility references valid params
- Options lists are non-empty where specified
"""

from app.strategies import StrategyParameter
from app.strategies.indicator_params import INDICATOR_PARAMS


class TestIndicatorParamsStructure:
    """Tests for overall INDICATOR_PARAMS list structure."""

    def test_params_is_nonempty_list(self):
        """Happy path: INDICATOR_PARAMS should be a non-empty list of dicts."""
        assert isinstance(INDICATOR_PARAMS, list)
        assert len(INDICATOR_PARAMS) > 0

    def test_all_entries_are_dicts(self):
        """Happy path: every entry should be a dict."""
        for i, entry in enumerate(INDICATOR_PARAMS):
            assert isinstance(entry, dict), f"Entry {i} is {type(entry)}, expected dict"

    def test_no_duplicate_param_names(self):
        """Edge case: no two params should share the same name."""
        names = [p["name"] for p in INDICATOR_PARAMS]
        duplicates = [n for n in names if names.count(n) > 1]
        assert len(duplicates) == 0, f"Duplicate param names found: {set(duplicates)}"

    def test_all_entries_have_required_fields(self):
        """Happy path: every entry must have name, display_name, description, type, default."""
        required = {"name", "display_name", "description", "type", "default"}
        for entry in INDICATOR_PARAMS:
            missing = required - set(entry.keys())
            assert not missing, (
                f"Param '{entry.get('name', '?')}' missing fields: {missing}"
            )


class TestStrategyParameterUnpacking:
    """Tests that each dict can be unpacked into StrategyParameter."""

    def test_all_params_unpack_into_strategy_parameter(self):
        """Happy path: every dict should create a valid StrategyParameter."""
        for entry in INDICATOR_PARAMS:
            # StrategyParameter ignores extra fields (Pydantic v2 default)
            param = StrategyParameter(**entry)
            assert param.name == entry["name"]
            assert param.display_name == entry["display_name"]

    def test_first_param_is_max_concurrent_deals(self):
        """Happy path: first param should be max_concurrent_deals."""
        param = StrategyParameter(**INDICATOR_PARAMS[0])
        assert param.name == "max_concurrent_deals"
        assert param.type == "int"
        assert param.default == 1

    def test_param_with_options_creates_valid_parameter(self):
        """Happy path: params with options should preserve them."""
        options_entries = [p for p in INDICATOR_PARAMS if "options" in p]
        assert len(options_entries) > 0, "Expected at least one param with options"
        for entry in options_entries:
            param = StrategyParameter(**entry)
            assert param.options is not None
            assert len(param.options) > 0

    def test_param_with_visible_when_creates_valid_parameter(self):
        """Happy path: params with visible_when should preserve conditional visibility."""
        visible_entries = [p for p in INDICATOR_PARAMS if "visible_when" in p]
        assert len(visible_entries) > 0, "Expected at least one param with visible_when"
        for entry in visible_entries:
            param = StrategyParameter(**entry)
            assert param.visible_when is not None
            assert isinstance(param.visible_when, dict)


class TestNumericConstraints:
    """Tests for min/max value consistency."""

    def test_min_less_than_or_equal_to_max(self):
        """Edge case: min_value must be <= max_value for all numeric params."""
        for entry in INDICATOR_PARAMS:
            if "min_value" in entry and "max_value" in entry:
                assert entry["min_value"] <= entry["max_value"], (
                    f"Param '{entry['name']}': min_value ({entry['min_value']}) "
                    f"> max_value ({entry['max_value']})"
                )

    def test_default_within_range(self):
        """Edge case: default value must be within [min_value, max_value]."""
        for entry in INDICATOR_PARAMS:
            if "min_value" in entry and "max_value" in entry:
                default = entry["default"]
                assert entry["min_value"] <= default <= entry["max_value"], (
                    f"Param '{entry['name']}': default ({default}) not in "
                    f"[{entry['min_value']}, {entry['max_value']}]"
                )

    def test_int_params_have_integer_defaults(self):
        """Edge case: params with type 'int' should have integer-compatible defaults."""
        for entry in INDICATOR_PARAMS:
            if entry["type"] == "int":
                assert isinstance(entry["default"], int), (
                    f"Param '{entry['name']}' has type 'int' but default "
                    f"{entry['default']} is {type(entry['default']).__name__}"
                )

    def test_float_params_have_numeric_defaults(self):
        """Edge case: params with type 'float' should have numeric defaults."""
        for entry in INDICATOR_PARAMS:
            if entry["type"] == "float":
                assert isinstance(entry["default"], (int, float)), (
                    f"Param '{entry['name']}' has type 'float' but default "
                    f"{entry['default']} is {type(entry['default']).__name__}"
                )

    def test_stop_loss_percentage_is_negative(self):
        """Domain logic: stop loss percentage should have negative range."""
        sl = next(p for p in INDICATOR_PARAMS if p["name"] == "stop_loss_percentage")
        assert sl["default"] < 0
        assert sl["min_value"] < 0
        assert sl["max_value"] < 0


class TestGroups:
    """Tests for parameter grouping."""

    def test_all_params_have_group(self):
        """Happy path: every param should belong to a group."""
        for entry in INDICATOR_PARAMS:
            assert "group" in entry and entry["group"], (
                f"Param '{entry['name']}' has no group"
            )

    def test_expected_groups_present(self):
        """Happy path: key groups should exist."""
        groups = {p["group"] for p in INDICATOR_PARAMS}
        expected = {
            "Deal Management", "Base Order", "Safety Orders",
            "Take Profit", "Stop Loss", "AI Indicators",
        }
        for g in expected:
            assert g in groups, f"Expected group '{g}' not found"

    def test_deal_management_has_multiple_params(self):
        """Happy path: Deal Management should have at least 2 params."""
        dm_params = [p for p in INDICATOR_PARAMS if p["group"] == "Deal Management"]
        assert len(dm_params) >= 2


class TestVisibleWhenReferences:
    """Tests that visible_when references point to valid param names."""

    def test_visible_when_references_existing_params(self):
        """Edge case: visible_when keys must reference existing param names."""
        all_names = {p["name"] for p in INDICATOR_PARAMS}
        for entry in INDICATOR_PARAMS:
            vw = entry.get("visible_when")
            if vw:
                for ref_name in vw:
                    assert ref_name in all_names, (
                        f"Param '{entry['name']}' visible_when references "
                        f"'{ref_name}' which is not a known param"
                    )

    def test_trailing_deviation_visible_when_trailing_mode(self):
        """Domain: trailing_deviation should only show when take_profit_mode is 'trailing'."""
        td = next(p for p in INDICATOR_PARAMS if p["name"] == "trailing_deviation")
        assert td["visible_when"] == {"take_profit_mode": "trailing"}


class TestOptionsValues:
    """Tests for params with options lists."""

    def test_default_in_options_list(self):
        """Edge case: if param has options, default must be one of them."""
        for entry in INDICATOR_PARAMS:
            if "options" in entry:
                assert entry["default"] in entry["options"], (
                    f"Param '{entry['name']}': default '{entry['default']}' "
                    f"not in options {entry['options']}"
                )

    def test_ai_model_options(self):
        """Happy path: AI model should offer claude, gpt, gemini."""
        ai_model = next(p for p in INDICATOR_PARAMS if p["name"] == "ai_model")
        assert "claude" in ai_model["options"]
        assert "gpt" in ai_model["options"]
        assert "gemini" in ai_model["options"]

    def test_base_order_type_options(self):
        """Happy path: base_order_type should have percentage and fixed options."""
        bot = next(p for p in INDICATOR_PARAMS if p["name"] == "base_order_type")
        assert "percentage" in bot["options"]
        assert "fixed_btc" in bot["options"]
        assert "fixed_usd" in bot["options"]


class TestBoolParams:
    """Tests for boolean parameters."""

    def test_bool_params_have_boolean_defaults(self):
        """Edge case: bool-typed params must have bool defaults."""
        for entry in INDICATOR_PARAMS:
            if entry["type"] == "bool":
                assert isinstance(entry["default"], bool), (
                    f"Param '{entry['name']}' has type 'bool' but default "
                    f"is {type(entry['default']).__name__}"
                )

    def test_stop_loss_disabled_by_default(self):
        """Domain: stop loss should be disabled by default."""
        sl = next(p for p in INDICATOR_PARAMS if p["name"] == "stop_loss_enabled")
        assert sl["default"] is False

    def test_slippage_guard_disabled_by_default(self):
        """Domain: slippage guard should be disabled by default."""
        sg = next(p for p in INDICATOR_PARAMS if p["name"] == "slippage_guard")
        assert sg["default"] is False


class TestPaperTradingOnlyField:
    """Tests for the paper_trading_only field on StrategyParameter."""

    def test_paper_trading_only_field_is_preserved(self):
        """The paper_trading_only field is now part of StrategyParameter."""
        sim_slip = next(p for p in INDICATOR_PARAMS if p["name"] == "simulate_slippage")
        assert sim_slip.get("paper_trading_only") is True
        param = StrategyParameter(**sim_slip)
        assert param.name == "simulate_slippage"
        assert param.paper_trading_only is True

    def test_paper_trading_only_defaults_to_none(self):
        """Params without paper_trading_only should default to None."""
        non_paper = next(p for p in INDICATOR_PARAMS if p["name"] != "simulate_slippage")
        param = StrategyParameter(**non_paper)
        assert param.paper_trading_only is None

    def test_param_count_is_expected(self):
        """Sanity check: total param count should match expected range."""
        # As of current code there are exactly 35 params
        assert len(INDICATOR_PARAMS) >= 30, (
            f"Expected at least 30 params, got {len(INDICATOR_PARAMS)}"
        )
