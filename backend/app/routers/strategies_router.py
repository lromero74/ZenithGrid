"""
Strategies Router

Exposes available trading strategies and their parameter definitions to the frontend.
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.models import User
from app.routers.auth_dependencies import get_current_user
from app.strategies import StrategyRegistry, StrategyDefinition

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class StrategyResponse(BaseModel):
    """Strategy definition response model"""
    id: str
    name: str
    description: str
    parameters: List[Dict[str, Any]]

    class Config:
        from_attributes = True


@router.get("/", response_model=List[StrategyResponse])
async def list_strategies(current_user: User = Depends(get_current_user)):
    """
    Get all available trading strategies with their parameter definitions.

    Returns list of strategies that can be used when creating bots.
    Includes parameter schemas for dynamic form generation.
    """
    try:
        # Get all registered strategy definitions
        definitions = StrategyRegistry.list_strategies()

        strategies = []
        for definition in definitions:
            # Convert to response format
            strategies.append(StrategyResponse(
                id=definition.id,
                name=definition.name,
                description=definition.description,
                parameters=[
                    {
                        "name": param.name,
                        "label": param.display_name,  # Note: using display_name from StrategyParameter
                        "type": param.type,
                        "default": param.default,
                        "description": param.description,
                        "required": param.required,
                        "min": param.min_value,
                        "max": param.max_value,
                        "options": param.options,
                        "group": param.group,
                        "conditions": param.visible_when,
                    }
                    for param in definition.parameters
                ]
            ))

        return strategies

    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: str, current_user: User = Depends(get_current_user)):
    """
    Get a specific strategy's definition by ID.

    Args:
        strategy_id: Strategy identifier (e.g., "grid_trading", "indicator_based")

    Returns:
        Strategy definition with parameters
    """
    try:
        # Get strategy definition
        definition = StrategyRegistry.get_definition(strategy_id)

        # Convert to response format
        return StrategyResponse(
            id=definition.id,
            name=definition.name,
            description=definition.description,
            parameters=[
                {
                    "name": param.name,
                    "label": param.display_name,
                    "type": param.type,
                    "default": param.default,
                    "description": param.description,
                    "required": param.required,
                    "min": param.min_value,
                    "max": param.max_value,
                    "options": param.options,
                    "group": param.group,
                    "conditions": param.visible_when,
                }
                for param in definition.parameters
            ]
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred")
