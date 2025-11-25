"""
Trading Engine Components

Core trading execution components:
- SignalProcessor: Evaluates strategy signals and orchestrates buy/sell decisions
- BuyExecutor: Executes buy orders with retry logic and position tracking
- SellExecutor: Executes sell orders and closes positions
- PositionManager: Manages position state and lifecycle
- OrderLogger: Logs order history for audit trail
"""
