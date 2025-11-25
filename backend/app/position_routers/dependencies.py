"""
Position Router Dependencies

Shared dependency functions for all position router modules.
"""

from app.coinbase_unified_client import CoinbaseClient


# Dependency - these will be injected from main.py
def get_coinbase() -> CoinbaseClient:
    """Get coinbase client - will be overridden in main.py"""
    raise NotImplementedError("Must override coinbase dependency")
