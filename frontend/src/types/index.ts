export interface Position {
  id: number;
  bot_id?: number | null;
  product_id?: string;
  status: string;
  opened_at: string;
  closed_at: string | null;
  initial_btc_balance: number;
  max_btc_allowed: number;
  total_btc_spent: number;
  total_eth_acquired: number;
  average_buy_price: number;
  sell_price: number | null;
  total_btc_received: number | null;
  profit_btc: number | null;
  profit_percentage: number | null;
  trade_count: number;
  btc_usd_price_at_open?: number;
  btc_usd_price_at_close?: number;
  profit_usd?: number;
}

export interface Trade {
  id: number;
  position_id: number;
  timestamp: string;
  side: string;
  btc_amount: number;
  eth_amount: number;
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
  total_profit_btc: number;
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
  description: string;
  default: number | string | boolean;
  min_value?: number;
  max_value?: number;
  type: 'float' | 'int' | 'string' | 'bool';
  options?: string[];
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
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_signal_check: string | null;
}

export interface BotCreate {
  name: string;
  description?: string;
  strategy_type: string;
  strategy_config: Record<string, any>;
  product_id: string;
}

export interface BotStats {
  bot: Bot;
  total_positions: number;
  open_positions: number;
  closed_positions: number;
  total_profit_btc: number;
  total_profit_usd: number;
  win_rate: number;
  avg_profit_per_position: number;
}
