"""Tests for app/strategies/condition_mirror.py"""

from app.strategies.condition_mirror import ConditionMirror


class TestMirrorCondition:
    def test_rsi_crossing_above_30_mirrors_to_crossing_below_70(self):
        long = {"type": "rsi", "operator": "crossing_above", "value": 30}
        short = ConditionMirror.mirror_condition(long)
        assert short["operator"] == "crossing_below"
        assert short["value"] == 70
        assert short["direction"] == "short"

    def test_rsi_crossing_below_70_mirrors_to_crossing_above_30(self):
        long = {"type": "rsi", "operator": "crossing_below", "value": 70}
        short = ConditionMirror.mirror_condition(long)
        assert short["operator"] == "crossing_above"
        assert short["value"] == 30

    def test_stochastic_mirrors_around_50(self):
        long = {"type": "stochastic", "operator": "less_than", "value": 20}
        short = ConditionMirror.mirror_condition(long)
        assert short["operator"] == "greater_than"
        assert short["value"] == 80

    def test_bb_percent_mirrors_around_50(self):
        long = {"type": "bb_percent", "operator": "less_than", "value": 10}
        short = ConditionMirror.mirror_condition(long)
        assert short["operator"] == "greater_than"
        assert short["value"] == 90

    def test_macd_flips_sign(self):
        long = {"type": "macd", "operator": "greater_than", "value": 0}
        short = ConditionMirror.mirror_condition(long)
        assert short["operator"] == "less_than"
        assert short["value"] == 0

    def test_macd_histogram_flips_positive_to_negative(self):
        long = {"type": "macd_histogram", "operator": "greater_than", "value": 5}
        short = ConditionMirror.mirror_condition(long)
        assert short["value"] == -5

    def test_unknown_indicator_keeps_value(self):
        """For unknown indicators, only operator is mirrored."""
        long = {"type": "volume", "operator": "greater_than", "value": 1000}
        short = ConditionMirror.mirror_condition(long)
        assert short["operator"] == "less_than"
        assert short["value"] == 1000  # Value unchanged

    def test_unknown_operator_kept_unchanged(self):
        long = {"type": "rsi", "operator": "custom_op", "value": 30}
        short = ConditionMirror.mirror_condition(long)
        assert short["operator"] == "custom_op"  # Not in mirror map

    def test_does_not_mutate_original(self):
        long = {"type": "rsi", "operator": "crossing_above", "value": 30}
        ConditionMirror.mirror_condition(long)
        assert long["operator"] == "crossing_above"
        assert long["value"] == 30
        assert "direction" not in long

    def test_greater_than_or_equal_mirrors(self):
        long = {"type": "rsi", "operator": "greater_than_or_equal", "value": 50}
        short = ConditionMirror.mirror_condition(long)
        assert short["operator"] == "less_than_or_equal"


class TestMirrorConditionGroup:
    def test_mirrors_list_of_conditions(self):
        long_group = [
            {"type": "rsi", "operator": "crossing_above", "value": 30},
            {"type": "macd", "operator": "greater_than", "value": 0},
        ]
        short_group = ConditionMirror.mirror_condition_group(long_group)
        assert len(short_group) == 2
        assert short_group[0]["value"] == 70
        assert short_group[1]["value"] == 0

    def test_empty_group(self):
        assert ConditionMirror.mirror_condition_group([]) == []


class TestGetBidirectionalConditions:
    def test_auto_mirror_creates_short_from_long(self):
        config = {
            "base_order_conditions": [
                {"type": "rsi", "operator": "crossing_above", "value": 30}
            ],
            "take_profit_conditions": [
                {"type": "rsi", "operator": "crossing_below", "value": 70}
            ],
        }
        result = ConditionMirror.get_bidirectional_conditions(config, auto_mirror=True)
        assert len(result["long"]["base_order_conditions"]) == 1
        assert len(result["short"]["base_order_conditions"]) == 1
        assert result["short"]["base_order_conditions"][0]["value"] == 70

    def test_manual_mode_uses_configured_short(self):
        config = {
            "base_order_conditions": [
                {"type": "rsi", "operator": "crossing_above", "value": 30}
            ],
            "take_profit_conditions": [],
            "short_base_order_conditions": [
                {"type": "volume", "operator": "less_than", "value": 500}
            ],
            "short_take_profit_conditions": [],
        }
        result = ConditionMirror.get_bidirectional_conditions(config, auto_mirror=False)
        assert result["short"]["base_order_conditions"][0]["type"] == "volume"

    def test_missing_conditions_default_to_empty(self):
        config = {}
        result = ConditionMirror.get_bidirectional_conditions(config, auto_mirror=True)
        assert result["long"]["base_order_conditions"] == []
        assert result["short"]["base_order_conditions"] == []
