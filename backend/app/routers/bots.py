"""
Bot Management Router (Refactored)

Aggregates all bot-related endpoints from modular routers.
Maintains backward compatibility by preserving the same API routes.
"""

from fastapi import APIRouter

from app.bot_routers import bot_crud_router
from app.bot_routers import bot_control_router
from app.bot_routers import bot_ai_logs_router
from app.bot_routers import bot_scanner_logs_router
from app.bot_routers import bot_validation_router

router = APIRouter(prefix="/api/bots", tags=["bots"])

# Include all sub-routers
router.include_router(bot_crud_router.router)
router.include_router(bot_control_router.router)
router.include_router(bot_ai_logs_router.router)
router.include_router(bot_scanner_logs_router.router)
router.include_router(bot_validation_router.router)
