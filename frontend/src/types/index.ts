export interface Position {
  id: number;
  bot_id?: number | null;
  product_id?: string;
  status: string;
  opened_at: string;
  closed_at: string | null;
  initial_quote_balance: number;  // BTC or USD
  max_quote_allowed: number;      // BTC or USD
  total_quote_spent: number;      // BTC or USD
  total_base_acquired: number;    // ETH, ADA, etc.
  average_buy_price: number;
  sell_price: number | null;
  total_quote_received: number | null;  // BTC or USD
  profit_quote: number | null;    // BTC or USD
  profit_percentage: number | null;
  trade_count: number;
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

export interface Balances {
  btc: number;
  eth: number;
  eth_value_in_btc: number;
  total_btc_value: number;
  current_eth_btc_price: number;
  btc_usd_price: number;
  total_usd_value: number;
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
