export interface Position {
  id: number;
  user_id?: number | null;  // Owner (for user-specific deal numbers)
  user_deal_number?: number | null;  // User-specific sequential deal number
  bot_id?: number | null;
  product_id?: string;
  status: string;
  account_id?: number | null;  // For multi-account support
  bot_config?: Record<string, any>;  // Snapshot of bot config at position open
  opened_at: string;
  closed_at: string | null;

  // Bidirectional DCA Grid Bot - Direction
  direction?: string;  // "long" or "short" (default: "long")

  initial_quote_balance: number;  // BTC or USD
  max_quote_allowed: number;      // BTC or USD
  total_quote_spent: number;      // BTC or USD
  total_base_acquired: number;    // ETH, ADA, etc.
  average_buy_price: number;

  // Bidirectional DCA Grid Bot - Short Position Tracking
  entry_price?: number | null;  // Initial entry price (for both long and short)
  short_entry_price?: number | null;  // Price at first short
  short_average_sell_price?: number | null;  // Average price of all short sells
  short_total_sold_quote?: number | null;  // Total USD received from selling
  short_total_sold_base?: number | null;  // Total BTC sold

  sell_price: number | null;
  total_quote_received: number | null;  // BTC or USD
  profit_quote: number | null;    // BTC or USD
  profit_percentage: number | null;
  trade_count: number;
  first_buy_price?: number | null;  // Price of first (base order) buy trade
  last_buy_price?: number | null;   // Price of most recent buy trade
  btc_usd_price_at_open?: number;
  btc_usd_price_at_close?: number;
  profit_usd?: number;
  strategy_config_snapshot?: Record<string, any>;  // Snapshot of bot config when position opened
  pending_orders_count?: number;  // Count of unfilled limit orders (for Active orders display)
  last_error_message?: string | null;  // Last error message (like 3Commas - for UI display)
  last_error_timestamp?: string | null;  // When the error occurred
  notes?: string | null;  // User notes for position (like 3Commas)
  closing_via_limit?: boolean;  // Whether position is closing via limit order
  limit_close_order_id?: string | null;  // Coinbase order ID for limit close
  limit_order_details?: LimitOrderDetails | null;  // Details of the limit close order
  is_blacklisted?: boolean;  // Whether the coin is on the blacklist
  blacklist_reason?: string | null;  // Reason the coin is blacklisted
}

export interface LimitOrderDetails {
  limit_price: number;
  remaining_amount: number;
  filled_amount: number;
  fill_percentage: number;
  fills: LimitOrderFill[];
  status: string;  // "pending", "partially_filled", "filled", "canceled"
}

export interface LimitOrderFill {
  price: number;
  base_amount: number;
  quote_amount: number;
  timestamp: string;
}

export interface Trade {
  id: number;
  position_id: number;
  timestamp: string;
  side: string;
  quote_amount: number;  // BTC or USD
  base_amount: number;   // ETH, ADA, etc.
  price: number;
  trade_type: string;
  order_id: string | null;
}

export interface Signal {
  id: number;
  timestamp: string;
  signal_type: string;
  macd_value: number;
  macd_signal: number;
  macd_histogram: number;
  price: number;
  action_taken: string | null;
  reason: string | null;
}

export interface AIBotLog {
  id: number;
  bot_id: number;
  position_id: number | null;
  timestamp: string;
  thinking: string;
  decision: string;
  confidence: number | null;
  current_price: number | null;
  position_status: string | null;
  product_id: string | null;
  context: any;
}

export interface MarketData {
  id: number;
  timestamp: string;
  price: number;
  macd_value: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
}

export interface DashboardStats {
  current_position: Position | null;
  total_positions: number;
  total_profit_quote: number;  // Total profit in quote currency
  win_rate: number;
  current_price: number;
  btc_balance: number;
  eth_balance: number;
  monitor_running: boolean;
}

export interface Settings {
  coinbase_api_key?: string;
  coinbase_api_secret?: string;
  initial_btc_percentage: number;
  dca_percentage: number;
  max_btc_usage_percentage: number;
  min_profit_percentage: number;
  macd_fast_period: number;
  macd_slow_period: number;
  macd_signal_period: number;
  candle_interval: string;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ReservedBalances {
  BTC: number;
  ETH: number;
  USD: number;
  USDC: number;
  USDT: number;
}

export interface Balances {
  btc: number;
  eth: number;
  eth_value_in_btc: number;
  total_btc_value: number;
  current_eth_btc_price: number;
  btc_usd_price: number;
  total_usd_value: number;

  // Multi-currency support
  usd: number;
  usdc: number;
  usdt: number;

  // Capital reservation tracking (matches backend structure)
  reserved_in_positions: ReservedBalances;
  reserved_in_pending_orders: ReservedBalances;

  // Available balances for new bots
  available_btc: number;
  available_usd: number;
  available_eth: number;
  available_usdc: number;
  available_usdt: number;
}

export interface AggregateValue {
  aggregate_btc_value: number;
  aggregate_usd_value: number;
  btc_usd_price: number;
}

export interface StrategyParameter {
  name: string;
  display_name?: string;
  description: string;
  default: number | string | boolean | null;
  min_value?: number;
  max_value?: number;
  type: 'float' | 'int' | 'string' | 'bool' | 'text';
  options?: string[];
  required?: boolean;
  group?: string;
  visible_when?: Record<string, any>;
}

export interface StrategyDefinition {
  id: string;
  name: string;
  description: string;
  parameters: StrategyParameter[];
}

export interface Bot {
  id: number;
  name: string;
  description: string | null;
  strategy_type: string;
  strategy_config: Record<string, any>;
  product_id: string;
  product_ids?: string[];  // Multi-pair support
  split_budget_across_pairs?: boolean;
  reserved_btc_balance: number;
  reserved_usd_balance: number;
  budget_percentage: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_signal_check: string | null;
  insufficient_funds?: boolean;
  budget_utilization_percentage?: number;
  account_id?: number | null;  // For multi-account support
  exchange_type?: 'cex' | 'dex';  // Exchange type
  open_positions_count?: number;  // Number of open positions for this bot
}

export interface BotCreate {
  name: string;
  description?: string;
  strategy_type: string;
  strategy_config: Record<string, any>;
  product_id: string;
  reserved_btc_balance?: number;
  reserved_usd_balance?: number;
  budget_percentage?: number;
}

export interface BotStats {
  bot: Bot;
  total_positions: number;
  open_positions: number;
  closed_positions: number;
  max_concurrent_deals: number;  // Max deals allowed simultaneously
  total_profit_quote: number;  // Total profit in quote currency
  total_profit_usd: number;
  win_rate: number;
  avg_profit_per_position: number;
  insufficient_funds: boolean;
  budget_utilization_percentage?: number;  // % of allocated budget in open positions
}

export interface OrderHistory {
  id: number;
  timestamp: string;
  bot_id: number;
  bot_name: string;
  position_id: number | null;
  product_id: string;
  side: string;
  order_type: string;
  trade_type: string;
  quote_amount: number;
  base_amount: number | null;
  price: number | null;
  status: string;
  order_id: string | null;
  error_message: string | null;
}

// Market Sentiment Types
export interface FearGreedData {
  value: number
  value_classification: string
  timestamp: string
  time_until_update: string | null
}

export interface FearGreedResponse {
  data: FearGreedData
  cached_at: string
  cache_expires_at: string
}

export interface BlockHeightResponse {
  height: number
  timestamp: string
}

export interface USDebtResponse {
  total_debt: number
  debt_per_second: number
  gdp: number
  debt_to_gdp_ratio: number
  record_date: string
  cached_at: string
  cache_expires_at: string
  // Debt ceiling info
  debt_ceiling: number | null
  debt_ceiling_suspended: boolean
  debt_ceiling_note: string | null
  headroom: number | null
}

export interface HalvingCountdown {
  blocksRemaining: number
  estimatedDate: Date
  daysRemaining: number
  hoursRemaining: number
  minutesRemaining: number
  percentComplete: number
}

// Market Metrics Types
export interface BTCDominanceResponse {
  btc_dominance: number
  eth_dominance: number
  others_dominance: number
  total_market_cap: number
  cached_at: string
}

export interface AltseasonIndexResponse {
  altseason_index: number
  season: 'Altcoin Season' | 'Bitcoin Season' | 'Neutral'
  outperformers: number
  total_altcoins: number
  btc_30d_change: number
  cached_at: string
}

export interface FundingRatesResponse {
  btc_funding_rate: number
  eth_funding_rate: number
  sentiment: string
  cached_at: string
}

export interface StablecoinMcapResponse {
  total_stablecoin_mcap: number
  usdt_mcap: number
  usdc_mcap: number
  dai_mcap: number
  others_mcap: number
  cached_at: string
}

export interface TotalMarketCapResponse {
  total_market_cap: number
  cached_at: string
}

export interface BTCSupplyResponse {
  circulating: number
  max_supply: number
  remaining: number
  percent_mined: number
  current_block: number
  cached_at: string
}

export interface MempoolResponse {
  tx_count: number
  vsize: number
  total_fee: number
  fee_fastest: number
  fee_half_hour: number
  fee_hour: number
  fee_economy: number
  congestion: 'High' | 'Medium' | 'Low'
  cached_at: string
}

export interface HashRateResponse {
  hash_rate_eh: number
  difficulty: number
  difficulty_t: number
  cached_at: string
}

export interface LightningResponse {
  channel_count: number
  node_count: number
  total_capacity_btc: number
  avg_capacity_sats: number
  avg_fee_rate: number
  cached_at: string
}

export interface ATHResponse {
  current_price: number
  ath: number
  ath_date: string
  days_since_ath: number
  drawdown_pct: number
  recovery_pct: number
  cached_at: string
}

export interface DebtCeilingEvent {
  date: string
  amount_trillion: number | null
  suspended: boolean
  suspension_end: string | null
  note: string
  legislation: string | null
  political_context: string | null
  source_url: string | null
}

export interface DebtCeilingHistoryResponse {
  events: DebtCeilingEvent[]
  total_events: number
  last_updated: string
}

export interface MetricHistoryPoint {
  value: number
  recorded_at: string
}

export interface MetricHistoryResponse {
  metric_name: string
  data: MetricHistoryPoint[]
}
