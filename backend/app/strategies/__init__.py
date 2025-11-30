"""
Trading Strategy Framework

This module provides base classes and a registry for trading strategies.
Each strategy implements its own signal detection and decision logic.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class StrategyParameter(BaseModel):
    """Definition of a strategy parameter"""

    name: str
    display_name: str
    description: str
    type: str  # "float", "int", "string", "bool"
    default: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    options: Optional[List[str]] = None  # For dropdown parameters
    group: Optional[str] = None  # For grouping parameters in UI
    visible_when: Optional[Dict[str, Any]] = None  # Conditional visibility
    required: Optional[bool] = True  # Whether parameter is required


class StrategyDefinition(BaseModel):
    """Metadata about a strategy"""

    id: str  # Unique identifier (e.g., "macd_dca")
    name: str  # Display name (e.g., "MACD DCA Strategy")
    description: str
    parameters: List[StrategyParameter]
    supported_products: List[str] = Field(default_factory=lambda: ["ETH-BTC", "BTC-USD", "ETH-USD"])


class TradingStrategy(ABC):
    """
    Base class for all trading strategies.

    Each strategy must implement:
    - get_definition(): Return strategy metadata
    - analyze_signal(): Detect trading signals from market data
    - should_buy(): Determine if we should buy
    - should_sell(): Determine if we should sell
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize strategy with configuration

        Args:
            config: Dictionary of strategy-specific parameters
        """
        self.config = config
        self.validate_config()

    @abstractmethod
    def get_definition(self) -> StrategyDefinition:
        """Return strategy metadata and parameter definitions"""
        pass

    @abstractmethod
    def validate_config(self):
        """Validate configuration parameters"""
        pass

    @abstractmethod
    async def analyze_signal(
        self, candles: List[Dict[str, Any]], current_price: float, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze market data and detect signals

        Args:
            candles: List of recent candle data
            current_price: Current market price
            **kwargs: Additional strategy-specific parameters (e.g., position, action_context)

        Returns:
            Signal data dict or None if no signal
        """
        pass

    @abstractmethod
    async def should_buy(
        self, signal_data: Dict[str, Any], position: Optional[Any], btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should buy and how much

        Args:
            signal_data: Signal information from analyze_signal
            position: Current position (if any)
            btc_balance: Available BTC balance

        Returns:
            Tuple of (should_buy: bool, btc_amount: float, reason: str)
        """
        pass

    @abstractmethod
    async def should_sell(self, signal_data: Dict[str, Any], position: Any, current_price: float) -> Tuple[bool, str]:
        """
        Determine if we should sell

        Args:
            signal_data: Signal information from analyze_signal
            position: Current position
            current_price: Current market price

        Returns:
            Tuple of (should_sell: bool, reason: str)
        """
        pass


class StrategyRegistry:
    """Registry of all available trading strategies"""

    _strategies: Dict[str, type] = {}

    @classmethod
    def register(cls, strategy_class: type):
        """Register a strategy class"""
        # Create temporary instance to get definition
        temp_instance = strategy_class({})
        definition = temp_instance.get_definition()
        cls._strategies[definition.id] = strategy_class
        return strategy_class

    @classmethod
    def get_strategy(cls, strategy_id: str, config: Dict[str, Any]) -> TradingStrategy:
        """Get an instance of a strategy by ID"""
        if strategy_id not in cls._strategies:
            raise ValueError(f"Unknown strategy: {strategy_id}")
        return cls._strategies[strategy_id](config)

    @classmethod
    def list_strategies(cls) -> List[StrategyDefinition]:
        """Get list of all available strategies"""
        definitions = []
        for strategy_class in cls._strategies.values():
            temp_instance = strategy_class({})
            definitions.append(temp_instance.get_definition())
        return definitions

    @classmethod
    def get_definition(cls, strategy_id: str) -> StrategyDefinition:
        """Get definition for a specific strategy"""
        if strategy_id not in cls._strategies:
            raise ValueError(f"Unknown strategy: {strategy_id}")
        temp_instance = cls._strategies[strategy_id]({})
        return temp_instance.get_definition()


# Import all strategy implementations to trigger registration
# Must be after StrategyRegistry class definition for decorators to work
from app.strategies import (  # noqa: E402
    advanced_dca,
    ai_autonomous,
    bollinger,
    bull_flag,
    conditional_dca,
    macd_dca,
    rsi,
    simple_dca,
    # Arbitrage strategies
    spatial_arbitrage,
    triangular_arbitrage,
    statistical_arbitrage,
)

__all__ = [
    "TradingStrategy",
    "StrategyDefinition",
    "StrategyParameter",
    "StrategyRegistry",
    # Strategy implementations (imported for registration)
    "advanced_dca",
    "ai_autonomous",
    "bollinger",
    "bull_flag",
    "conditional_dca",
    "macd_dca",
    "rsi",
    "simple_dca",
    # Arbitrage strategies
    "spatial_arbitrage",
    "triangular_arbitrage",
    "statistical_arbitrage",
]
