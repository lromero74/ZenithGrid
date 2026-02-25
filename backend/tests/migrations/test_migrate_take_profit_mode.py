"""
Tests for backend/migrations/migrate_take_profit_mode.py

Covers:
- migrate_config: all mode inference paths (fixed, trailing, minimum)
- migrate_config: legacy field removal and defaults
- migrate_config: idempotency (already-migrated configs unchanged)
"""

import os
import sys

# Add migrations directory to path so we can import the migration module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
from migrate_take_profit_mode import migrate_config, has_conditions  # noqa: E402


class TestHasConditions:
    """Tests for the has_conditions helper."""

    def test_none_returns_false(self):
        assert has_conditions({"take_profit_conditions": None}) is False

    def test_missing_key_returns_false(self):
        assert has_conditions({}) is False

    def test_empty_list_returns_false(self):
        assert has_conditions({"take_profit_conditions": []}) is False

    def test_non_empty_list_returns_true(self):
        assert has_conditions({"take_profit_conditions": [{"type": "rsi"}]}) is True

    def test_dict_with_empty_groups_returns_false(self):
        assert has_conditions({"take_profit_conditions": {"groups": []}}) is False

    def test_dict_with_populated_groups_returns_true(self):
        conds = {"groups": [{"conditions": [{"type": "rsi"}]}]}
        assert has_conditions({"take_profit_conditions": conds}) is True


class TestMigrateConfig:
    """Tests for migrate_config()."""

    def test_already_migrated_unchanged(self):
        """Config with take_profit_mode already set is not changed."""
        config = {"take_profit_mode": "fixed", "take_profit_percentage": 3.0}
        new_config, changed = migrate_config(config)
        assert changed is False
        assert new_config["take_profit_mode"] == "fixed"

    def test_trailing_take_profit_true_sets_trailing_mode(self):
        """Legacy trailing_take_profit=True => mode='trailing'."""
        config = {
            "trailing_take_profit": True,
            "take_profit_percentage": 3.0,
            "take_profit_order_type": "limit",
        }
        new_config, changed = migrate_config(config)
        assert changed is True
        assert new_config["take_profit_mode"] == "trailing"
        assert "trailing_take_profit" not in new_config

    def test_min_profit_for_conditions_sets_minimum_mode(self):
        """Legacy min_profit_for_conditions set => mode='minimum'."""
        config = {
            "min_profit_for_conditions": 2.0,
            "take_profit_percentage": 5.0,
            "take_profit_order_type": "limit",
        }
        new_config, changed = migrate_config(config)
        assert changed is True
        assert new_config["take_profit_mode"] == "minimum"
        assert "min_profit_for_conditions" not in new_config
        # TP% should be set to min_profit value since they differ
        assert new_config["take_profit_percentage"] == 2.0

    def test_conditions_present_sets_minimum_mode(self):
        """Config with take_profit_conditions but no min_profit => minimum mode."""
        config = {
            "take_profit_percentage": 3.0,
            "take_profit_conditions": [{"type": "rsi"}],
            "take_profit_order_type": "limit",
        }
        new_config, changed = migrate_config(config)
        assert changed is True
        assert new_config["take_profit_mode"] == "minimum"

    def test_no_legacy_fields_sets_fixed_mode(self):
        """Config with no trailing/min_profit/conditions => fixed mode."""
        config = {
            "take_profit_percentage": 3.0,
            "take_profit_order_type": "limit",
        }
        new_config, changed = migrate_config(config)
        assert changed is True
        assert new_config["take_profit_mode"] == "fixed"

    def test_limit_order_type_changed_to_market(self):
        """take_profit_order_type 'limit' is changed to 'market'."""
        config = {
            "take_profit_percentage": 3.0,
            "take_profit_order_type": "limit",
        }
        new_config, changed = migrate_config(config)
        assert new_config["take_profit_order_type"] == "market"

    def test_market_order_type_unchanged(self):
        """take_profit_order_type 'market' stays 'market'."""
        config = {
            "take_profit_percentage": 3.0,
            "take_profit_order_type": "market",
        }
        new_config, changed = migrate_config(config)
        assert new_config["take_profit_order_type"] == "market"

    def test_execution_types_added_when_missing(self):
        """base_execution_type and dca_execution_type added as 'market'."""
        config = {"take_profit_percentage": 3.0}
        new_config, changed = migrate_config(config)
        assert changed is True
        assert new_config["base_execution_type"] == "market"
        assert new_config["dca_execution_type"] == "market"

    def test_execution_types_preserved_when_present(self):
        """Existing execution types are not overwritten."""
        config = {
            "take_profit_percentage": 3.0,
            "base_execution_type": "limit",
            "dca_execution_type": "limit",
        }
        new_config, changed = migrate_config(config)
        assert new_config["base_execution_type"] == "limit"
        assert new_config["dca_execution_type"] == "limit"

    def test_non_dict_returns_unchanged(self):
        """Non-dict config returns as-is with changed=False."""
        result, changed = migrate_config("not a dict")
        assert changed is False
        assert result == "not a dict"

    def test_min_profit_same_as_tp_does_not_change_tp(self):
        """When min_profit equals TP%, TP% is not changed."""
        config = {
            "min_profit_for_conditions": 3.0,
            "take_profit_percentage": 3.0,
        }
        new_config, changed = migrate_config(config)
        assert new_config["take_profit_percentage"] == 3.0
