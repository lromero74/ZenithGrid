"""
Tests for backend/app/routers/strategies_router.py

Covers strategy listing and individual strategy retrieval endpoints.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.models import User
from app.strategies import StrategyDefinition, StrategyParameter, StrategyRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_user():
    """Create a mock User for dependency injection."""
    user = MagicMock(spec=User)
    user.id = 1
    user.is_superuser = False
    return user


def _make_definition(strategy_id="test_strat", name="Test Strategy",
                     description="A test strategy", params=None):
    """Build a StrategyDefinition for mocking."""
    if params is None:
        params = [
            StrategyParameter(
                name="take_profit",
                display_name="Take Profit %",
                description="Profit target",
                type="float",
                default=2.0,
                min_value=0.1,
                max_value=100.0,
                group="profit",
                required=True,
            ),
        ]
    return StrategyDefinition(
        id=strategy_id,
        name=name,
        description=description,
        parameters=params,
    )


# ---------------------------------------------------------------------------
# LIST strategies
# ---------------------------------------------------------------------------

class TestListStrategies:
    """Tests for GET /api/strategies/"""

    @pytest.mark.asyncio
    async def test_list_strategies_returns_all(self):
        """Happy path: returns all registered strategies."""
        from app.routers.strategies_router import list_strategies

        user = _mock_user()
        result = await list_strategies(current_user=user)

        # Should return at least the known registered strategies
        assert isinstance(result, list)
        assert len(result) >= 1
        # Each result should have the expected fields
        first = result[0]
        assert hasattr(first, "id")
        assert hasattr(first, "name")
        assert hasattr(first, "parameters")

    @pytest.mark.asyncio
    async def test_list_strategies_parameter_fields(self):
        """Happy path: each parameter has all expected fields."""
        from app.routers.strategies_router import list_strategies

        user = _mock_user()
        defs = [_make_definition()]

        with patch.object(StrategyRegistry, "list_strategies", return_value=defs):
            result = await list_strategies(current_user=user)

        assert len(result) == 1
        params = result[0].parameters
        assert len(params) == 1
        p = params[0]
        assert p["name"] == "take_profit"
        assert p["label"] == "Take Profit %"
        assert p["type"] == "float"
        assert p["default"] == 2.0
        assert p["min"] == 0.1
        assert p["max"] == 100.0
        assert p["group"] == "profit"
        assert p["required"] is True

    @pytest.mark.asyncio
    async def test_list_strategies_optional_parameter_fields(self):
        """Edge case: optional parameter fields (options, conditions) are None when unset."""
        from app.routers.strategies_router import list_strategies

        user = _mock_user()
        defs = [_make_definition()]

        with patch.object(StrategyRegistry, "list_strategies", return_value=defs):
            result = await list_strategies(current_user=user)

        p = result[0].parameters[0]
        assert p["options"] is None
        assert p["conditions"] is None

    @pytest.mark.asyncio
    async def test_list_strategies_empty_registry(self):
        """Edge case: returns empty list when no strategies registered."""
        from app.routers.strategies_router import list_strategies

        user = _mock_user()

        with patch.object(StrategyRegistry, "list_strategies", return_value=[]):
            result = await list_strategies(current_user=user)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_strategies_exception_raises_500(self):
        """Failure: internal error raises HTTPException 500."""
        from fastapi import HTTPException
        from app.routers.strategies_router import list_strategies

        user = _mock_user()

        with patch.object(StrategyRegistry, "list_strategies", side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc_info:
                await list_strategies(current_user=user)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_list_strategies_multiple_strategies(self):
        """Happy path: returns multiple strategies in correct order."""
        from app.routers.strategies_router import list_strategies

        user = _mock_user()
        defs = [
            _make_definition("strat_a", "Strategy A"),
            _make_definition("strat_b", "Strategy B"),
        ]

        with patch.object(StrategyRegistry, "list_strategies", return_value=defs):
            result = await list_strategies(current_user=user)

        assert len(result) == 2
        assert result[0].id == "strat_a"
        assert result[1].id == "strat_b"


# ---------------------------------------------------------------------------
# GET strategy by ID
# ---------------------------------------------------------------------------

class TestGetStrategy:
    """Tests for GET /api/strategies/{strategy_id}"""

    @pytest.mark.asyncio
    async def test_get_strategy_happy_path(self):
        """Happy path: returns specific strategy by ID."""
        from app.routers.strategies_router import get_strategy

        user = _mock_user()
        definition = _make_definition("my_strat", "My Strategy")

        with patch.object(StrategyRegistry, "get_definition", return_value=definition):
            result = await get_strategy("my_strat", current_user=user)

        assert result.id == "my_strat"
        assert result.name == "My Strategy"

    @pytest.mark.asyncio
    async def test_get_strategy_not_found_raises_404(self):
        """Failure: unknown strategy ID raises HTTPException 404."""
        from fastapi import HTTPException
        from app.routers.strategies_router import get_strategy

        user = _mock_user()

        with patch.object(StrategyRegistry, "get_definition", side_effect=ValueError("Unknown")):
            with pytest.raises(HTTPException) as exc_info:
                await get_strategy("nonexistent", current_user=user)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_strategy_internal_error_raises_500(self):
        """Failure: internal error raises HTTPException 500."""
        from fastapi import HTTPException
        from app.routers.strategies_router import get_strategy

        user = _mock_user()

        with patch.object(StrategyRegistry, "get_definition", side_effect=RuntimeError("internal")):
            with pytest.raises(HTTPException) as exc_info:
                await get_strategy("bad_id", current_user=user)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_get_strategy_includes_parameters(self):
        """Happy path: returned strategy includes full parameter definitions."""
        from app.routers.strategies_router import get_strategy

        user = _mock_user()
        params = [
            StrategyParameter(
                name="param_a",
                display_name="Param A",
                description="First param",
                type="float",
                default=1.0,
                options=["opt1", "opt2"],
                visible_when={"mode": "advanced"},
            ),
            StrategyParameter(
                name="param_b",
                display_name="Param B",
                description="Second param",
                type="bool",
                default=True,
                required=False,
            ),
        ]
        definition = _make_definition("multi_param", "Multi Param", params=params)

        with patch.object(StrategyRegistry, "get_definition", return_value=definition):
            result = await get_strategy("multi_param", current_user=user)

        assert len(result.parameters) == 2
        assert result.parameters[0]["options"] == ["opt1", "opt2"]
        assert result.parameters[0]["conditions"] == {"mode": "advanced"}
        assert result.parameters[1]["required"] is False

    @pytest.mark.asyncio
    async def test_get_strategy_with_real_registry(self):
        """Integration: fetch a real registered strategy (indicator_based)."""
        from app.routers.strategies_router import get_strategy

        user = _mock_user()
        result = await get_strategy("indicator_based", current_user=user)

        assert result.id == "indicator_based"
        assert isinstance(result.parameters, list)
        assert len(result.parameters) > 0
