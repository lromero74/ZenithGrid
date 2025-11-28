"""
API Routers

This package contains modularized FastAPI routers to keep files under 500 lines.
"""

from app.routers.bots import router as bots_router
from app.routers.order_history import router as order_history_router
from app.routers.templates import router as templates_router
from app.routers import positions_router
from app.routers import account_router
from app.routers import accounts_router  # Multi-account management (CEX + DEX)
from app.routers import market_data_router
from app.routers import settings_router
from app.routers import system_router

__all__ = [
    "bots_router",
    "order_history_router",
    "templates_router",
    "positions_router",
    "account_router",
    "accounts_router",
    "market_data_router",
    "settings_router",
    "system_router",
]
