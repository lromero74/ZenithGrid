# Arbitrage Platform - Complete Implementation Handoff Document

**Created**: 2025-11-28
**Status**: Active Development
**Branch**: feature/dex-integration (→ will create feature/arbitrage-platform)

---

## Executive Summary

This document outlines the complete implementation plan for transforming the Zenith Grid trading platform into a full-featured multi-exchange arbitrage system with account-based context switching.

### Core Features
1. **Multi-Account Management** - Switch between CEX (Coinbase) and DEX (MetaMask) accounts
2. **Spatial Arbitrage** - Cross-exchange price discrepancy exploitation
3. **Triangular Arbitrage** - Same-exchange cyclic trading paths
4. **Statistical Arbitrage** - Correlation-based mean reversion trading

---

## Current State (Completed)

### Phase 1-4: DEX Integration Foundation ✅
- [x] Exchange abstraction layer (`ExchangeClient` base class)
- [x] Coinbase adapter implementing `ExchangeClient`
- [x] DEX client skeleton for Ethereum + Uniswap V3
- [x] Database schema updates (exchange_type, chain_id, dex_router, wallet fields)
- [x] Frontend DEX configuration UI (`DexConfigSection.tsx`)
- [x] web3.py v6+ compatibility fixes

### Files Modified/Created in Phases 1-4
```
backend/app/exchange_clients/
├── __init__.py
├── base.py                    # ExchangeClient abstract base class
├── coinbase_adapter.py        # Coinbase implementation
├── dex_client.py             # DEX/Uniswap V3 implementation
└── factory.py                # Client factory pattern

backend/app/models.py          # Added DEX fields to Bot model

frontend/src/components/
└── DexConfigSection.tsx       # DEX configuration UI component

frontend/src/pages/
└── Bots.tsx                   # Updated with DEX integration
```

---

## Phase 5: Account Management & Context Switching

### 5.1 Database Schema

**New Table: `accounts`**
```sql
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('cex', 'dex')),
    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,

    -- CEX-specific fields (Coinbase)
    exchange TEXT,                          -- 'coinbase'
    api_key_name TEXT,
    api_private_key TEXT,                   -- Encrypted

    -- DEX-specific fields
    chain_id INTEGER,                       -- 1=Ethereum, 56=BSC, 137=Polygon, 42161=Arbitrum
    wallet_address TEXT,
    wallet_private_key TEXT,                -- Encrypted (optional - for bot trading)
    rpc_url TEXT,
    wallet_type TEXT,                       -- 'metamask', 'walletconnect', 'private_key'

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);

-- Link bots to accounts
ALTER TABLE bots ADD COLUMN account_id INTEGER REFERENCES accounts(id);

-- Link positions to accounts
ALTER TABLE positions ADD COLUMN account_id INTEGER REFERENCES accounts(id);
```

### 5.2 Backend Files to Create

**`backend/app/models.py`** - Add Account model
```python
class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # 'cex' or 'dex'
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # CEX fields
    exchange = Column(String, nullable=True)
    api_key_name = Column(String, nullable=True)
    api_private_key = Column(String, nullable=True)

    # DEX fields
    chain_id = Column(Integer, nullable=True)
    wallet_address = Column(String, nullable=True)
    wallet_private_key = Column(String, nullable=True)
    rpc_url = Column(String, nullable=True)
    wallet_type = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    # Relationships
    bots = relationship("Bot", back_populates="account")
```

**`backend/app/routers/accounts.py`** - Account CRUD API
```python
# Endpoints:
# GET    /api/accounts              - List all accounts
# GET    /api/accounts/{id}         - Get account details
# POST   /api/accounts              - Create new account
# PUT    /api/accounts/{id}         - Update account
# DELETE /api/accounts/{id}         - Delete account
# POST   /api/accounts/{id}/default - Set as default account
# GET    /api/accounts/{id}/balance - Get account balance
```

### 5.3 Frontend Files to Create

**`frontend/src/contexts/AccountContext.tsx`**
```typescript
interface Account {
  id: number
  name: string
  type: 'cex' | 'dex'
  is_default: boolean

  // CEX
  exchange?: string

  // DEX
  chain_id?: number
  wallet_address?: string
  wallet_type?: string
}

interface AccountContextType {
  accounts: Account[]
  selectedAccount: Account | null
  selectAccount: (id: number) => void
  addAccount: (account: CreateAccountDto) => Promise<Account>
  updateAccount: (id: number, data: UpdateAccountDto) => Promise<Account>
  deleteAccount: (id: number) => Promise<void>
  refreshAccounts: () => Promise<void>
}
```

**`frontend/src/components/AccountSwitcher.tsx`**
- Dropdown in header showing current account
- List of available accounts with balances
- "Add Account" option
- Visual indicators for CEX vs DEX accounts

**`frontend/src/types/accounts.ts`**
- TypeScript interfaces for account types
- Chain configurations (name, icon, RPC defaults)
- Exchange configurations

### 5.4 Implementation Steps

1. Create Account model in `models.py`
2. Create database migration for `accounts` table
3. Add `account_id` foreign key to `bots` and `positions` tables
4. Create `accounts.py` router with CRUD endpoints
5. Create `AccountContext.tsx` for frontend state management
6. Create `AccountSwitcher.tsx` component
7. Integrate AccountSwitcher into App.tsx header
8. Update all pages to filter by selected account
9. Update bot creation to require account selection

---

## Phase 6: Spatial Arbitrage (Cross-Exchange)

### 6.1 Concept
Buy an asset on exchange A (lower price), simultaneously sell on exchange B (higher price). Profit = price difference - fees.

### 6.2 Backend Files to Create

**`backend/app/price_feeds/__init__.py`**
**`backend/app/price_feeds/base.py`**
```python
class PriceFeed(ABC):
    @abstractmethod
    async def get_price(self, base: str, quote: str) -> PriceQuote:
        pass

    @abstractmethod
    async def get_orderbook(self, base: str, quote: str, depth: int) -> OrderBook:
        pass
```

**`backend/app/price_feeds/coinbase_feed.py`**
```python
class CoinbasePriceFeed(PriceFeed):
    async def get_price(self, base: str, quote: str) -> PriceQuote:
        # Use existing Coinbase client to get real-time prices
        pass
```

**`backend/app/price_feeds/dex_feed.py`**
```python
class DEXPriceFeed(PriceFeed):
    async def get_price(self, base: str, quote: str) -> PriceQuote:
        # Use Uniswap V3 Quoter contract
        pass
```

**`backend/app/price_feeds/aggregator.py`**
```python
class PriceAggregator:
    def __init__(self, feeds: List[PriceFeed]):
        self.feeds = feeds

    async def get_best_prices(self, base: str, quote: str) -> AggregatedPrice:
        """
        Returns best buy/sell prices across all exchanges
        """
        prices = await asyncio.gather(*[
            feed.get_price(base, quote) for feed in self.feeds
        ])

        return AggregatedPrice(
            best_buy=min(prices, key=lambda p: p.ask),
            best_sell=max(prices, key=lambda p: p.bid),
            spread=best_sell.bid - best_buy.ask,
            spread_pct=(spread / best_buy.ask) * 100
        )
```

**`backend/app/strategies/spatial_arbitrage.py`**
```python
class SpatialArbitrageStrategy(TradingStrategy):
    """
    Cross-exchange arbitrage strategy.

    Parameters:
    - min_profit_pct: Minimum profit percentage to trigger (default: 0.3%)
    - max_position_size_usd: Maximum trade size in USD
    - buy_exchange: Exchange to buy from (or 'auto')
    - sell_exchange: Exchange to sell on (or 'auto')
    - slippage_tolerance: Maximum acceptable slippage (default: 0.1%)
    - include_gas_in_calc: Include estimated gas fees (DEX)
    """

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="spatial_arbitrage",
            name="Spatial Arbitrage (Cross-Exchange)",
            description="Exploit price differences between CEX and DEX exchanges",
            parameters=[
                StrategyParameter(
                    name="min_profit_pct",
                    display_name="Minimum Profit %",
                    description="Minimum profit percentage after fees to execute",
                    type="float",
                    default=0.3,
                    min_value=0.1,
                    max_value=5.0
                ),
                StrategyParameter(
                    name="max_position_size_usd",
                    display_name="Max Position Size (USD)",
                    description="Maximum trade size in USD equivalent",
                    type="float",
                    default=1000,
                    min_value=100,
                    max_value=100000
                ),
                # ... more parameters
            ]
        )

    async def analyze_signal(self, candles, current_price, **kwargs):
        aggregator = kwargs.get('price_aggregator')
        prices = await aggregator.get_best_prices(self.base, self.quote)

        # Calculate net profit after fees
        buy_cost = prices.best_buy.ask * (1 + self.buy_fee)
        sell_revenue = prices.best_sell.bid * (1 - self.sell_fee)

        if prices.best_sell.exchange_type == 'dex':
            sell_revenue -= self.estimate_gas_cost()

        net_profit_pct = ((sell_revenue - buy_cost) / buy_cost) * 100

        if net_profit_pct >= self.config['min_profit_pct']:
            return {
                'signal': 'arbitrage',
                'buy_exchange': prices.best_buy.exchange,
                'sell_exchange': prices.best_sell.exchange,
                'buy_price': prices.best_buy.ask,
                'sell_price': prices.best_sell.bid,
                'expected_profit_pct': net_profit_pct
            }

        return None
```

### 6.3 Execution Flow
1. Monitor prices on both exchanges (CEX + DEX) every few seconds
2. Calculate net profit after ALL fees:
   - CEX maker/taker fees
   - DEX swap fees (0.3% for Uniswap V3)
   - Gas fees (for DEX transactions)
   - Slippage estimate
3. When profitable opportunity found:
   - Verify sufficient balance on both exchanges
   - Execute buy order on cheaper exchange
   - Execute sell order on expensive exchange (simultaneously if possible)
4. Track execution and actual profit
5. Handle partial fills and failed transactions

### 6.4 Risk Management
- Maximum position size limits
- Minimum liquidity requirements
- Execution timeout (don't hold positions if one side fails)
- Balance rebalancing when funds accumulate on one side

---

## Phase 7: Triangular Arbitrage (Same Exchange)

### 7.1 Concept
Exploit pricing inefficiencies within a single exchange by trading through a cycle:
- Start: 1 ETH
- Trade 1: ETH → BTC (get 0.05 BTC)
- Trade 2: BTC → USDT (get 3,510 USDT)
- Trade 3: USDT → ETH (get 1.003 ETH)
- Profit: 0.003 ETH (0.3%)

### 7.2 Backend Files to Create

**`backend/app/arbitrage/__init__.py`**

**`backend/app/arbitrage/triangular_detector.py`**
```python
class TriangularPathDetector:
    def __init__(self, exchange_client: ExchangeClient):
        self.client = exchange_client
        self.graph = {}  # Currency graph

    async def build_currency_graph(self):
        """Build graph of all tradable pairs"""
        products = await self.client.get_products()

        for product in products:
            base, quote = product.split('-')
            if base not in self.graph:
                self.graph[base] = {}
            if quote not in self.graph:
                self.graph[quote] = {}

            self.graph[base][quote] = product
            self.graph[quote][base] = product  # Reverse direction

    def find_triangular_paths(self, start_currency: str) -> List[TriangularPath]:
        """
        Find all 3-hop paths that return to start currency

        Example paths from ETH:
        - ETH → BTC → USDT → ETH
        - ETH → USDC → BTC → ETH
        """
        paths = []

        for mid1 in self.graph.get(start_currency, {}):
            for mid2 in self.graph.get(mid1, {}):
                if mid2 != start_currency and start_currency in self.graph.get(mid2, {}):
                    paths.append(TriangularPath(
                        currencies=[start_currency, mid1, mid2, start_currency],
                        pairs=[
                            self.graph[start_currency][mid1],
                            self.graph[mid1][mid2],
                            self.graph[mid2][start_currency]
                        ]
                    ))

        return paths

    async def calculate_path_profit(self, path: TriangularPath, amount: float) -> PathProfit:
        """Calculate expected profit for a path"""
        current_amount = amount

        for i, pair in enumerate(path.pairs):
            price = await self.get_execution_price(pair, current_amount, path.directions[i])
            fee = self.get_fee_rate(pair)

            if path.directions[i] == 'buy':
                current_amount = (current_amount / price) * (1 - fee)
            else:
                current_amount = (current_amount * price) * (1 - fee)

        profit = current_amount - amount
        profit_pct = (profit / amount) * 100

        return PathProfit(
            path=path,
            start_amount=amount,
            end_amount=current_amount,
            profit=profit,
            profit_pct=profit_pct
        )
```

**`backend/app/strategies/triangular_arbitrage.py`**
```python
class TriangularArbitrageStrategy(TradingStrategy):
    """
    Triangular arbitrage within a single exchange.

    Parameters:
    - base_currency: Starting/ending currency (ETH, BTC, USDT)
    - min_profit_pct: Minimum profit to execute (default: 0.1%)
    - trade_amount: Amount to trade in base currency
    - scan_interval_ms: How often to scan for opportunities
    - max_paths_to_check: Limit paths checked per scan
    """

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="triangular_arbitrage",
            name="Triangular Arbitrage",
            description="Exploit price inefficiencies through 3-way currency cycles",
            parameters=[
                StrategyParameter(
                    name="base_currency",
                    display_name="Base Currency",
                    description="Currency to start and end with",
                    type="string",
                    default="ETH",
                    options=["ETH", "BTC", "USDT", "USDC"]
                ),
                StrategyParameter(
                    name="min_profit_pct",
                    display_name="Minimum Profit %",
                    description="Minimum profit percentage to execute",
                    type="float",
                    default=0.1,
                    min_value=0.01,
                    max_value=1.0
                ),
                StrategyParameter(
                    name="trade_amount",
                    display_name="Trade Amount",
                    description="Amount to trade in base currency",
                    type="float",
                    default=0.1
                ),
                StrategyParameter(
                    name="scan_interval_ms",
                    display_name="Scan Interval (ms)",
                    description="How often to scan for opportunities",
                    type="int",
                    default=1000,
                    min_value=100,
                    max_value=10000
                )
            ]
        )

    async def analyze_signal(self, candles, current_price, **kwargs):
        detector = self.get_path_detector()
        paths = detector.find_triangular_paths(self.config['base_currency'])

        # Check each path for profitability
        profitable_paths = []
        for path in paths[:self.config.get('max_paths_to_check', 20)]:
            profit = await detector.calculate_path_profit(
                path,
                self.config['trade_amount']
            )

            if profit.profit_pct >= self.config['min_profit_pct']:
                profitable_paths.append(profit)

        if profitable_paths:
            best_path = max(profitable_paths, key=lambda p: p.profit_pct)
            return {
                'signal': 'triangular_arbitrage',
                'path': best_path.path.currencies,
                'pairs': best_path.path.pairs,
                'expected_profit_pct': best_path.profit_pct,
                'trade_amount': self.config['trade_amount']
            }

        return None
```

### 7.3 Execution Considerations
- **Atomicity**: All 3 trades must succeed or none should
- **Speed**: Opportunities are fleeting (milliseconds)
- **Slippage**: Each trade affects the next trade's price
- **Order sizing**: Must account for minimum order sizes on each pair

---

## Phase 8: Statistical Arbitrage

### 8.1 Concept
Trade based on historical price correlations. When two normally-correlated assets diverge, bet on convergence:
- ETH-USD and ETH-BTC usually move together
- If ETH-BTC drops while ETH-USD stays flat, ETH-BTC is "undervalued"
- Buy ETH-BTC, short/sell ETH-USD
- Profit when they converge back to normal relationship

### 8.2 Backend Files to Create

**`backend/app/arbitrage/stat_arb_analyzer.py`**
```python
import numpy as np
from scipy import stats

class StatArbAnalyzer:
    def __init__(self, lookback_days: int = 30):
        self.lookback_days = lookback_days
        self.price_history = {}

    async def update_price_history(self, pair: str, price: float, timestamp: datetime):
        """Store price data for analysis"""
        if pair not in self.price_history:
            self.price_history[pair] = []

        self.price_history[pair].append({
            'price': price,
            'timestamp': timestamp
        })

        # Trim old data
        cutoff = datetime.utcnow() - timedelta(days=self.lookback_days)
        self.price_history[pair] = [
            p for p in self.price_history[pair]
            if p['timestamp'] > cutoff
        ]

    def calculate_correlation(self, pair1: str, pair2: str) -> float:
        """Calculate Pearson correlation between two pairs"""
        prices1 = [p['price'] for p in self.price_history.get(pair1, [])]
        prices2 = [p['price'] for p in self.price_history.get(pair2, [])]

        if len(prices1) < 100 or len(prices2) < 100:
            return None

        # Align timestamps and calculate correlation
        aligned = self._align_prices(prices1, prices2)
        correlation, _ = stats.pearsonr(aligned[0], aligned[1])

        return correlation

    def calculate_z_score(self, pair1: str, pair2: str) -> float:
        """
        Calculate z-score of current spread vs historical spread

        Z-score > 2: Pair 1 is overvalued relative to Pair 2
        Z-score < -2: Pair 1 is undervalued relative to Pair 2
        """
        prices1 = np.array([p['price'] for p in self.price_history.get(pair1, [])])
        prices2 = np.array([p['price'] for p in self.price_history.get(pair2, [])])

        # Calculate spread (ratio)
        spread = prices1 / prices2

        # Calculate z-score of current spread
        current_spread = spread[-1]
        mean_spread = np.mean(spread)
        std_spread = np.std(spread)

        z_score = (current_spread - mean_spread) / std_spread

        return z_score

    def calculate_hedge_ratio(self, pair1: str, pair2: str) -> float:
        """
        Calculate optimal hedge ratio using linear regression

        For $1 of pair1, how much pair2 to hold for market-neutral position
        """
        prices1 = np.array([p['price'] for p in self.price_history.get(pair1, [])])
        prices2 = np.array([p['price'] for p in self.price_history.get(pair2, [])])

        # Linear regression: pair1 = beta * pair2 + alpha
        slope, intercept, r_value, p_value, std_err = stats.linregress(prices2, prices1)

        return slope  # This is the hedge ratio
```

**`backend/app/strategies/statistical_arbitrage.py`**
```python
class StatisticalArbitrageStrategy(TradingStrategy):
    """
    Mean-reversion strategy based on price correlations.

    Parameters:
    - pair_1: First trading pair (e.g., ETH-USD)
    - pair_2: Second trading pair (e.g., ETH-BTC)
    - lookback_period: Days of historical data (default: 30)
    - z_score_entry: Z-score threshold to enter (default: 2.0)
    - z_score_exit: Z-score threshold to exit (default: 0.5)
    - position_size_usd: Size of each leg in USD
    - max_holding_period: Maximum days to hold position
    """

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="statistical_arbitrage",
            name="Statistical Arbitrage",
            description="Trade mean-reversion between correlated pairs",
            parameters=[
                StrategyParameter(
                    name="pair_1",
                    display_name="Pair 1",
                    description="First trading pair",
                    type="string",
                    default="ETH-USD"
                ),
                StrategyParameter(
                    name="pair_2",
                    display_name="Pair 2",
                    description="Second trading pair (should be correlated)",
                    type="string",
                    default="ETH-BTC"
                ),
                StrategyParameter(
                    name="lookback_period",
                    display_name="Lookback Period (days)",
                    description="Historical data window for correlation",
                    type="int",
                    default=30,
                    min_value=7,
                    max_value=90
                ),
                StrategyParameter(
                    name="z_score_entry",
                    display_name="Z-Score Entry Threshold",
                    description="Enter when z-score exceeds this (typically 2.0)",
                    type="float",
                    default=2.0,
                    min_value=1.0,
                    max_value=4.0
                ),
                StrategyParameter(
                    name="z_score_exit",
                    display_name="Z-Score Exit Threshold",
                    description="Exit when z-score falls below this (typically 0.5)",
                    type="float",
                    default=0.5,
                    min_value=0.0,
                    max_value=1.5
                ),
                StrategyParameter(
                    name="position_size_usd",
                    display_name="Position Size (USD)",
                    description="Size of each leg in USD",
                    type="float",
                    default=500,
                    min_value=100,
                    max_value=50000
                ),
                StrategyParameter(
                    name="min_correlation",
                    display_name="Minimum Correlation",
                    description="Minimum required correlation to trade",
                    type="float",
                    default=0.7,
                    min_value=0.5,
                    max_value=0.95
                )
            ]
        )

    async def analyze_signal(self, candles, current_price, **kwargs):
        analyzer = self.get_stat_analyzer()

        pair1 = self.config['pair_1']
        pair2 = self.config['pair_2']

        # Check correlation is sufficient
        correlation = analyzer.calculate_correlation(pair1, pair2)
        if correlation < self.config['min_correlation']:
            return None

        # Calculate current z-score
        z_score = analyzer.calculate_z_score(pair1, pair2)
        hedge_ratio = analyzer.calculate_hedge_ratio(pair1, pair2)

        # Entry signals
        if abs(z_score) >= self.config['z_score_entry']:
            if z_score > 0:
                # Pair 1 overvalued: Short pair 1, Long pair 2
                return {
                    'signal': 'stat_arb_entry',
                    'direction': 'short_spread',
                    'pair_1_action': 'sell',
                    'pair_2_action': 'buy',
                    'z_score': z_score,
                    'hedge_ratio': hedge_ratio,
                    'correlation': correlation
                }
            else:
                # Pair 1 undervalued: Long pair 1, Short pair 2
                return {
                    'signal': 'stat_arb_entry',
                    'direction': 'long_spread',
                    'pair_1_action': 'buy',
                    'pair_2_action': 'sell',
                    'z_score': z_score,
                    'hedge_ratio': hedge_ratio,
                    'correlation': correlation
                }

        # Exit signals (if position exists)
        if kwargs.get('has_position') and abs(z_score) <= self.config['z_score_exit']:
            return {
                'signal': 'stat_arb_exit',
                'z_score': z_score,
                'reason': 'z_score_convergence'
            }

        return None
```

---

## Phase 9: UI Account Switching

### 9.1 Header Account Selector

**Location**: `frontend/src/App.tsx` - Add to header section

```tsx
// New component: AccountSwitcher
<div className="flex items-center space-x-4">
  <AccountSwitcher />
  <PortfolioValue />
</div>
```

**`frontend/src/components/AccountSwitcher.tsx`**
```tsx
import { useState } from 'react'
import { ChevronDown, Plus, Wallet, Building2 } from 'lucide-react'
import { useAccount } from '../contexts/AccountContext'

export function AccountSwitcher() {
  const { accounts, selectedAccount, selectAccount } = useAccount()
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center space-x-2 px-3 py-2 bg-slate-700 rounded-lg hover:bg-slate-600"
      >
        {selectedAccount?.type === 'cex' ? (
          <Building2 className="w-4 h-4 text-blue-400" />
        ) : (
          <Wallet className="w-4 h-4 text-orange-400" />
        )}
        <span className="text-sm font-medium">
          {selectedAccount?.name || 'Select Account'}
        </span>
        <ChevronDown className="w-4 h-4" />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-64 bg-slate-800 rounded-lg shadow-xl border border-slate-700 z-50">
          <div className="p-2">
            <div className="text-xs text-slate-400 px-2 py-1">CEX Accounts</div>
            {accounts.filter(a => a.type === 'cex').map(account => (
              <AccountOption
                key={account.id}
                account={account}
                isSelected={selectedAccount?.id === account.id}
                onSelect={() => {
                  selectAccount(account.id)
                  setIsOpen(false)
                }}
              />
            ))}

            <div className="text-xs text-slate-400 px-2 py-1 mt-2">DEX Wallets</div>
            {accounts.filter(a => a.type === 'dex').map(account => (
              <AccountOption
                key={account.id}
                account={account}
                isSelected={selectedAccount?.id === account.id}
                onSelect={() => {
                  selectAccount(account.id)
                  setIsOpen(false)
                }}
              />
            ))}

            <div className="border-t border-slate-700 mt-2 pt-2">
              <button className="flex items-center space-x-2 w-full px-2 py-2 text-sm text-slate-300 hover:bg-slate-700 rounded">
                <Plus className="w-4 h-4" />
                <span>Add Account</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

### 9.2 Page Adaptations

Each page receives `selectedAccount` from context and filters data accordingly:

**Dashboard.tsx**
```tsx
const { selectedAccount } = useAccount()

const { data: bots } = useQuery({
  queryKey: ['bots', selectedAccount?.id],
  queryFn: () => botsApi.getByAccount(selectedAccount?.id),
  enabled: !!selectedAccount
})

// Show account-specific metrics
const accountType = selectedAccount?.type
const showGasFees = accountType === 'dex'
const showMakerTakerFees = accountType === 'cex'
```

**Bots.tsx**
- Filter bot list by account
- Show CEX or DEX config section based on account type
- Pre-fill exchange_type based on selected account

**Positions.tsx**
- Filter positions by account
- Show transaction links (Etherscan for DEX, Coinbase for CEX)
- Display gas fees for DEX transactions

**Portfolio.tsx**
- Fetch balances from selected account's exchange/wallet
- Show chain-specific tokens for DEX accounts
- Show USD/BTC balances for CEX accounts

---

## Migration Strategy

### Database Migration Script
```python
# backend/alembic/versions/add_accounts_table.py

def upgrade():
    # Create accounts table
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('exchange', sa.String(), nullable=True),
        sa.Column('api_key_name', sa.String(), nullable=True),
        sa.Column('api_private_key', sa.String(), nullable=True),
        sa.Column('chain_id', sa.Integer(), nullable=True),
        sa.Column('wallet_address', sa.String(), nullable=True),
        sa.Column('wallet_private_key', sa.String(), nullable=True),
        sa.Column('rpc_url', sa.String(), nullable=True),
        sa.Column('wallet_type', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
    )

    # Add account_id to bots
    op.add_column('bots', sa.Column('account_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_bots_account', 'bots', 'accounts', ['account_id'], ['id'])

    # Add account_id to positions
    op.add_column('positions', sa.Column('account_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_positions_account', 'positions', 'accounts', ['account_id'], ['id'])

    # Create default Coinbase account from existing credentials
    # (This will be done via data migration script)

def downgrade():
    op.drop_constraint('fk_positions_account', 'positions')
    op.drop_column('positions', 'account_id')
    op.drop_constraint('fk_bots_account', 'bots')
    op.drop_column('bots', 'account_id')
    op.drop_table('accounts')
```

---

## Testing Strategy

### Unit Tests
- Account CRUD operations
- Price feed aggregation
- Triangular path detection
- Z-score calculations
- Profit calculations (with fees)

### Integration Tests
- End-to-end spatial arbitrage execution
- Triangular arbitrage multi-leg execution
- Account switching and data filtering

### Paper Trading
- Run strategies with simulated execution
- Verify profit calculations match expectations
- Test edge cases (partial fills, timeouts)

---

## Security Considerations

1. **Private Key Storage**: All private keys encrypted at rest
2. **API Key Rotation**: Support for key rotation without bot downtime
3. **Rate Limiting**: Respect exchange rate limits
4. **Position Limits**: Hard caps on position sizes
5. **Kill Switch**: Emergency stop for all bots
6. **Audit Logging**: Track all trades and account actions

---

## File Structure After Implementation

```
backend/
├── app/
│   ├── arbitrage/
│   │   ├── __init__.py
│   │   ├── triangular_detector.py
│   │   └── stat_arb_analyzer.py
│   ├── price_feeds/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── coinbase_feed.py
│   │   ├── dex_feed.py
│   │   └── aggregator.py
│   ├── strategies/
│   │   ├── spatial_arbitrage.py      # NEW
│   │   ├── triangular_arbitrage.py   # NEW
│   │   └── statistical_arbitrage.py  # NEW
│   ├── routers/
│   │   └── accounts.py               # NEW
│   └── models.py                      # Updated with Account model

frontend/
├── src/
│   ├── contexts/
│   │   └── AccountContext.tsx        # NEW
│   ├── components/
│   │   ├── AccountSwitcher.tsx       # NEW
│   │   └── AddAccountModal.tsx       # NEW
│   ├── types/
│   │   └── accounts.ts               # NEW
│   └── pages/
│       └── Accounts.tsx              # NEW (optional settings page)
```

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-28 | 1.0 | Initial document creation |

