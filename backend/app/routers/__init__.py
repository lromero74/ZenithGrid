"""
API Routers

This package contains modularized FastAPI routers to keep files under 500 lines.
"""

from app.routers.bots import router as bots_router
from app.routers.templates import router as templates_router

__all__ = ["bots_router", "templates_router"]
