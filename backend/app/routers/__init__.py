"""
API Routers

This package contains modularized FastAPI routers to keep files under 500 lines.
"""

from app.routers.bots import router as bots_router
from app.routers.order_history import router as order_history_router
from app.routers.templates import router as templates_router
# NOTE: positions_router is NOT imported here to avoid circular imports.
# It imports from position_routers, which imports auth_dependencies from this
# package, creating a cycle. Import positions_router directly in main.py instead.
from app.routers import account_router
from app.routers import accounts_router  # Multi-account management (CEX + DEX)
from app.routers import market_data_router
from app.routers import settings_router
from app.routers import system_router
from app.routers import strategies_router

__all__ = [
    "bots_router",
    "order_history_router",
    "templates_router",
    "account_router",
    "accounts_router",
    "market_data_router",
    "settings_router",
    "system_router",
    "strategies_router",
]
