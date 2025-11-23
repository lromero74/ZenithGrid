"""
Position Management Router (Refactored)

Aggregates all position-related endpoints from modular routers.
Maintains backward compatibility by preserving the same API routes.

Handles all position-related endpoints:
- List positions
- Position details
- Position trades and AI logs
- Position actions (cancel, force-close, limit-close, add-funds, notes)
- P&L time series data
"""

from fastapi import APIRouter

from app.position_routers import position_query_router
from app.position_routers import position_actions_router
from app.position_routers import position_limit_orders_router
from app.position_routers import position_manual_ops_router

router = APIRouter(prefix="/api/positions", tags=["positions"])

# Include all sub-routers
router.include_router(position_query_router.router)
router.include_router(position_actions_router.router)
router.include_router(position_limit_orders_router.router)
router.include_router(position_manual_ops_router.router)
