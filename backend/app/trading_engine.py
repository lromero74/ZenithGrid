from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Position, Trade, Signal, MarketData
from app.coinbase_client import CoinbaseClient
from app.indicators import MACDCalculator
from app.config import settings
import asyncio


class TradingEngine:
    """Core trading logic with DCA strategy"""

    def __init__(
        self,
        db: AsyncSession,
        coinbase: CoinbaseClient,
        product_id: str = "ETH-BTC"  # Coinbase format for ETH/BTC
    ):
        self.db = db
        self.coinbase = coinbase
        self.product_id = product_id
        self.macd = MACDCalculator()

        # Trading parameters (can be overridden by settings)
        self.initial_btc_percentage = settings.initial_btc_percentage
        self.dca_percentage = settings.dca_percentage
        self.max_btc_usage_percentage = settings.max_btc_usage_percentage
        self.min_profit_percentage = settings.min_profit_percentage

    async def get_current_btc_balance(self) -> float:
        """Get current BTC balance from Coinbase"""
        return await self.coinbase.get_btc_balance()

    async def get_current_eth_balance(self) -> float:
        """Get current ETH balance from Coinbase"""
        return await self.coinbase.get_eth_balance()

    async def get_active_position(self) -> Optional[Position]:
        """Get currently active position"""
        query = select(Position).where(Position.status == "open").order_by(desc(Position.opened_at))
        result = await self.db.execute(query)
        return result.scalars().first()

    async def create_position(self, btc_balance: float) -> Position:
        """Create a new position"""
        max_btc = btc_balance * (self.max_btc_usage_percentage / 100.0)

        # Get BTC/USD price for tracking
        try:
            btc_usd_price = await self.coinbase.get_btc_usd_price()
        except:
            btc_usd_price = None

        position = Position(
            status="open",
            opened_at=datetime.utcnow(),
            initial_btc_balance=btc_balance,
            max_btc_allowed=max_btc,
            total_btc_spent=0.0,
            total_eth_acquired=0.0,
            average_buy_price=0.0,
            btc_usd_price_at_open=btc_usd_price
        )

        self.db.add(position)
        await self.db.commit()
        await self.db.refresh(position)

        return position

    async def execute_buy(
        self,
        position: Position,
        btc_amount: float,
        current_price: float,
        trade_type: str,
        macd_data: Optional[MarketData] = None
    ) -> Trade:
        """
        Execute a buy order

        Args:
            position: Current position
            btc_amount: Amount of BTC to spend
            current_price: Current ETH/BTC price
            trade_type: 'initial' or 'dca'
            macd_data: Optional MACD data at time of trade
        """
        # Calculate ETH amount
        eth_amount = btc_amount / current_price

        # Execute order via Coinbase
        try:
            order_response = await self.coinbase.buy_eth_with_btc(
                btc_amount=btc_amount,
                product_id=self.product_id
            )
            # Get actual filled amounts from order response
            success_response = order_response.get("success_response", {})
            order_id = success_response.get("order_id", "")

            # Update with actual filled amounts if available
            # (In real scenario, might need to wait for order fill)
        except Exception as e:
            print(f"Error executing buy order: {e}")
            order_id = None

        # Record trade
        trade = Trade(
            position_id=position.id,
            timestamp=datetime.utcnow(),
            side="buy",
            btc_amount=btc_amount,
            eth_amount=eth_amount,
            price=current_price,
            trade_type=trade_type,
            order_id=order_id,
            macd_value=macd_data.macd_value if macd_data else None,
            macd_signal=macd_data.macd_signal if macd_data else None,
            macd_histogram=macd_data.macd_histogram if macd_data else None
        )

        self.db.add(trade)

        # Update position
        position.total_btc_spent += btc_amount
        position.total_eth_acquired += eth_amount
        position.update_averages()

        await self.db.commit()
        await self.db.refresh(trade)

        return trade

    async def execute_sell(
        self,
        position: Position,
        current_price: float,
        macd_data: Optional[MarketData] = None
    ) -> Tuple[Trade, float, float]:
        """
        Execute a sell order for entire position

        Returns:
            Tuple of (trade, profit_btc, profit_percentage)
        """
        eth_amount = position.total_eth_acquired

        # Calculate BTC received
        btc_received = eth_amount * current_price

        # Execute order via Coinbase
        try:
            order_response = await self.coinbase.sell_eth_for_btc(
                eth_amount=eth_amount,
                product_id=self.product_id
            )
            success_response = order_response.get("success_response", {})
            order_id = success_response.get("order_id", "")
        except Exception as e:
            print(f"Error executing sell order: {e}")
            order_id = None

        # Calculate profit
        profit_btc = btc_received - position.total_btc_spent
        profit_percentage = (profit_btc / position.total_btc_spent) * 100

        # Get BTC/USD price for USD profit tracking
        try:
            btc_usd_price_at_close = await self.coinbase.get_btc_usd_price()
            profit_usd = profit_btc * btc_usd_price_at_close
        except:
            btc_usd_price_at_close = None
            profit_usd = None

        # Record trade
        trade = Trade(
            position_id=position.id,
            timestamp=datetime.utcnow(),
            side="sell",
            btc_amount=btc_received,
            eth_amount=eth_amount,
            price=current_price,
            trade_type="sell",
            order_id=order_id,
            macd_value=macd_data.macd_value if macd_data else None,
            macd_signal=macd_data.macd_signal if macd_data else None,
            macd_histogram=macd_data.macd_histogram if macd_data else None
        )

        self.db.add(trade)

        # Close position
        position.status = "closed"
        position.closed_at = datetime.utcnow()
        position.sell_price = current_price
        position.total_btc_received = btc_received
        position.profit_btc = profit_btc
        position.profit_percentage = profit_percentage
        position.btc_usd_price_at_close = btc_usd_price_at_close
        position.profit_usd = profit_usd

        await self.db.commit()
        await self.db.refresh(trade)

        return trade, profit_btc, profit_percentage

    async def handle_macd_cross_up(
        self,
        signal_data: MarketData
    ) -> Dict[str, Any]:
        """
        Handle MACD cross up signal (bullish)

        Logic:
        - If no position: Create new position and buy initial amount
        - If position exists: DCA buy (if within max BTC limit)
        """
        current_price = signal_data.price
        btc_balance = await self.get_current_btc_balance()
        position = await self.get_active_position()

        action_taken = "none"
        reason = ""
        trade = None

        if position is None:
            # Create new position and execute initial buy
            position = await self.create_position(btc_balance)

            btc_to_spend = btc_balance * (self.initial_btc_percentage / 100.0)

            if btc_to_spend > 0:
                trade = await self.execute_buy(
                    position=position,
                    btc_amount=btc_to_spend,
                    current_price=current_price,
                    trade_type="initial",
                    macd_data=signal_data
                )
                action_taken = "buy"
                reason = f"Initial position opened with {self.initial_btc_percentage}% of BTC balance"
            else:
                reason = "Insufficient BTC balance"

        else:
            # DCA: Buy more if within limits
            btc_to_spend = position.initial_btc_balance * (self.dca_percentage / 100.0)
            new_total = position.total_btc_spent + btc_to_spend

            if new_total <= position.max_btc_allowed:
                trade = await self.execute_buy(
                    position=position,
                    btc_amount=btc_to_spend,
                    current_price=current_price,
                    trade_type="dca",
                    macd_data=signal_data
                )
                action_taken = "buy"
                reason = f"DCA buy with {self.dca_percentage}% (total: {new_total:.8f} BTC)"
            else:
                action_taken = "hold"
                reason = f"Max BTC limit reached ({position.max_btc_allowed:.8f} BTC)"

        # Record signal
        signal = Signal(
            position_id=position.id if position else None,
            timestamp=datetime.utcnow(),
            signal_type="macd_cross_up",
            macd_value=signal_data.macd_value,
            macd_signal=signal_data.macd_signal,
            macd_histogram=signal_data.macd_histogram,
            price=signal_data.price,
            action_taken=action_taken,
            reason=reason
        )
        self.db.add(signal)
        await self.db.commit()

        return {
            "signal": "macd_cross_up",
            "action": action_taken,
            "reason": reason,
            "trade": trade,
            "position": position
        }

    async def handle_macd_cross_down(
        self,
        signal_data: MarketData
    ) -> Dict[str, Any]:
        """
        Handle MACD cross down signal (bearish)

        Logic:
        - If position exists with 1%+ profit: Sell entire position
        - Otherwise: Hold
        """
        current_price = signal_data.price
        position = await self.get_active_position()

        action_taken = "none"
        reason = ""
        trade = None
        profit_btc = None
        profit_percentage = None

        if position is None:
            action_taken = "none"
            reason = "No active position"
        else:
            # Calculate current profit
            eth_value = position.total_eth_acquired * current_price
            current_profit_btc = eth_value - position.total_btc_spent
            current_profit_pct = (current_profit_btc / position.total_btc_spent) * 100

            if current_profit_pct >= self.min_profit_percentage:
                # Sell position
                trade, profit_btc, profit_percentage = await self.execute_sell(
                    position=position,
                    current_price=current_price,
                    macd_data=signal_data
                )
                action_taken = "sell"
                reason = f"Position closed with {profit_percentage:.2f}% profit ({profit_btc:.8f} BTC)"
            else:
                action_taken = "hold"
                reason = f"Profit {current_profit_pct:.2f}% below minimum {self.min_profit_percentage}%"

        # Record signal
        signal = Signal(
            position_id=position.id if position else None,
            timestamp=datetime.utcnow(),
            signal_type="macd_cross_down",
            macd_value=signal_data.macd_value,
            macd_signal=signal_data.macd_signal,
            macd_histogram=signal_data.macd_histogram,
            price=signal_data.price,
            action_taken=action_taken,
            reason=reason
        )
        self.db.add(signal)
        await self.db.commit()

        return {
            "signal": "macd_cross_down",
            "action": action_taken,
            "reason": reason,
            "trade": trade,
            "position": position,
            "profit_btc": profit_btc,
            "profit_percentage": profit_percentage
        }

    async def process_signal(
        self,
        signal_type: str,
        signal_data: MarketData
    ) -> Dict[str, Any]:
        """Process a MACD signal"""
        if signal_type == "cross_up":
            return await self.handle_macd_cross_up(signal_data)
        elif signal_type == "cross_down":
            return await self.handle_macd_cross_down(signal_data)
        else:
            raise ValueError(f"Unknown signal type: {signal_type}")
