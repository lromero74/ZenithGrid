import axios from 'axios';
import type {
  Position,
  Trade,
  Signal,
  MarketData,
  DashboardStats,
  Settings,
  Balances,
  AggregateValue,
  Bot,
  BotCreate,
  BotStats,
  StrategyDefinition,
  OrderHistory,
  AIBotLog,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

// Add request interceptor to attach auth token to all requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Add response interceptor to handle 401 errors (redirect to login)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear auth data and let the app redirect to login
      localStorage.removeItem('auth_access_token');
      localStorage.removeItem('auth_refresh_token');
      localStorage.removeItem('auth_token_expiry');
      localStorage.removeItem('auth_user');
      // Trigger a page reload to show login screen
      window.location.reload();
    }
    return Promise.reject(error);
  }
);

export const dashboardApi = {
  getStats: () => api.get<DashboardStats>('/dashboard').then((res) => res.data),
};

export interface UpdatePositionSettingsRequest {
  take_profit_percentage?: number;
  max_safety_orders?: number;
  trailing_take_profit?: boolean;
  trailing_tp_deviation?: number;
  stop_loss_enabled?: boolean;
  stop_loss_percentage?: number;
}

export const positionsApi = {
  getAll: (status?: string, limit = 50) =>
    api.get<Position[]>('/positions', { params: { status, limit } }).then((res) => res.data),
  getById: (id: number) =>
    api.get<Position>(`/positions/${id}`).then((res) => res.data),
  getTrades: (id: number) =>
    api.get<Trade[]>(`/positions/${id}/trades`).then((res) => res.data),
  getAILogs: (id: number, includeBeforeOpen = true) =>
    api.get<AIBotLog[]>(`/positions/${id}/ai-logs`, { params: { include_before_open: includeBeforeOpen } }).then((res) => res.data),
  close: (id: number) =>
    api.post<{ message: string; profit_quote: number; profit_percentage: number }>(`/positions/${id}/force-close`)
      .then((res) => res.data),
  addFunds: (id: number, btcAmount: number) =>
    api.post<{ message: string; trade_id: number; price: number; eth_acquired: number }>(`/positions/${id}/add-funds`, { btc_amount: btcAmount })
      .then((res) => res.data),
  updateSettings: (id: number, settings: UpdatePositionSettingsRequest) =>
    api.patch<{ message: string; updated_fields: string[]; new_config: Record<string, unknown> }>(`/positions/${id}/settings`, settings)
      .then((res) => res.data),
  getCompletedStats: (accountId?: number) =>
    api.get<{
      total_profit_btc: number;
      total_profit_usd: number;
      win_rate: number;
      total_trades: number;
      winning_trades: number;
      losing_trades: number;
      average_profit_usd: number;
    }>('/positions/completed/stats', { params: accountId ? { account_id: accountId } : {} }).then((res) => res.data),
  resizeBudget: (id: number) =>
    api.post<{ message: string; position_id: number; old_max: number; new_max: number; quote_currency: string }>(
      `/positions/${id}/resize-budget`
    ).then((res) => res.data),
  resizeAllBudgets: () =>
    api.post<{ message: string; updated_count: number; total_count: number; results: { id: number; pair: string; old_max: number; new_max: number; skipped?: string }[] }>(
      '/positions/resize-all-budgets'
    ).then((res) => res.data),
  getRealizedPnL: (accountId?: number) =>
    api.get<{
      daily_profit_btc: number;
      daily_profit_usd: number;
      yesterday_profit_btc: number;
      yesterday_profit_usd: number;
      last_week_profit_btc: number;
      last_week_profit_usd: number;
      last_month_profit_btc: number;
      last_month_profit_usd: number;
      last_quarter_profit_btc: number;
      last_quarter_profit_usd: number;
      last_year_profit_btc: number;
      last_year_profit_usd: number;
      wtd_profit_btc: number;
      wtd_profit_usd: number;
      mtd_profit_btc: number;
      mtd_profit_usd: number;
      qtd_profit_btc: number;
      qtd_profit_usd: number;
      ytd_profit_btc: number;
      ytd_profit_usd: number;
    }>('/positions/realized-pnl', { params: accountId ? { account_id: accountId } : {} }).then((res) => res.data),
};

export const tradesApi = {
  getAll: (limit = 100) =>
    api.get<Trade[]>('/trades', { params: { limit } }).then((res) => res.data),
};

export const signalsApi = {
  getAll: (limit = 100) =>
    api.get<Signal[]>('/signals', { params: { limit } }).then((res) => res.data),
};

export const marketDataApi = {
  getRecent: (hours = 24) =>
    api.get<MarketData[]>('/market-data', { params: { hours } }).then((res) => res.data),
  getCoins: () =>
    api.get<{ coins: { symbol: string; markets: string[]; product_ids: string[] }[]; count: number }>('/coins').then((res) => res.data),
};

export const settingsApi = {
  get: (key?: string) => {
    if (key) {
      // Get individual setting by key
      return api.get<{ key: string; value: string; value_type: string; description: string; updated_at: string }>(`/settings/${key}`).then((res) => res.data);
    }
    // Get all app settings (legacy)
    return api.get<Settings>('/settings').then((res) => res.data);
  },
  update: (keyOrSettings: string | Partial<Settings>, value?: string) => {
    if (typeof keyOrSettings === 'string' && value !== undefined) {
      // Update individual setting by key
      return api.put<{ message: string; key: string; value: string; updated_at: string }>(`/settings/${keyOrSettings}?value=${encodeURIComponent(value)}`).then((res) => res.data);
    }
    // Update app settings (legacy)
    return api.post<{ message: string }>('/settings', keyOrSettings).then((res) => res.data);
  },
};

export const monitorApi = {
  start: () => api.post<{ message: string }>('/monitor/start').then((res) => res.data),
  stop: () => api.post<{ message: string }>('/monitor/stop').then((res) => res.data),
};

export const accountApi = {
  getBalances: (accountId?: number) => {
    const params = accountId ? { account_id: accountId } : {}
    return api.get<Balances>('/account/balances', { params }).then((res) => res.data)
  },
  getAggregateValue: () => api.get<AggregateValue>('/account/aggregate-value').then((res) => res.data),
  // Sell entire portfolio to BTC or USD (sells balances, not positions)
  sellPortfolioToBase: (targetCurrency: 'BTC' | 'USD', confirm = true, accountId?: number) =>
    api.post<{
      task_id: string;
      message: string;
      status_url: string;
    }>('/account/sell-portfolio-to-base', null, {
      params: { target_currency: targetCurrency, confirm, account_id: accountId }
    }).then((res) => res.data),

  getConversionStatus: (taskId: string) =>
    api.get<{
      task_id: string;
      status: 'running' | 'completed' | 'failed';
      total: number;
      current: number;
      progress_pct: number;
      sold_count: number;
      failed_count: number;
      errors: string[];
      message: string;
      started_at: string;
      completed_at?: string;
    }>(`/account/conversion-status/${taskId}`).then((res) => res.data),
};

export const statusApi = {
  get: () =>
    api.get<{ api_connected: boolean; monitor: any; timestamp: string }>('/status')
      .then((res) => res.data),
};

export const botsApi = {
  getStrategies: () =>
    api.get<StrategyDefinition[]>('/strategies/').then((res) => res.data),
  getStrategy: (strategyId: string) =>
    api.get<StrategyDefinition>(`/strategies/${strategyId}`).then((res) => res.data),
  getAll: (projectionTimeframe?: string) => {
    const params = projectionTimeframe ? `?projection_timeframe=${projectionTimeframe}` : ''
    return api.get<Bot[]>(`/bots${params}`).then((res) => res.data)
  },
  getById: (id: number) =>
    api.get<Bot>(`/bots/${id}`).then((res) => res.data),
  create: (bot: BotCreate) =>
    api.post<Bot>('/bots', bot).then((res) => res.data),
  update: (id: number, bot: Partial<BotCreate>) =>
    api.put<Bot>(`/bots/${id}`, bot).then((res) => res.data),
  delete: (id: number) =>
    api.delete<{ message: string }>(`/bots/${id}`).then((res) => res.data),
  start: (id: number) =>
    api.post<{ message: string }>(`/bots/${id}/start`).then((res) => res.data),
  stop: (id: number) =>
    api.post<{ message: string }>(`/bots/${id}/stop`).then((res) => res.data),
  forceRun: (id: number) =>
    api.post<{ message: string; note: string }>(`/bots/${id}/force-run`).then((res) => res.data),
  clone: (id: number) =>
    api.post<Bot>(`/bots/${id}/clone`).then((res) => res.data),
  copyToAccount: (id: number, targetAccountId: number) =>
    api.post<Bot>(`/bots/${id}/copy-to-account?target_account_id=${targetAccountId}`).then((res) => res.data),
  getStats: (id: number) =>
    api.get<BotStats>(`/bots/${id}/stats`).then((res) => res.data),
  getLogs: (id: number, limit = 50, offset = 0, productId?: string, since?: string) => {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });
    if (productId) params.append('product_id', productId);
    if (since) params.append('since', since);
    return api.get<any[]>(`/bots/${id}/logs?${params}`).then((res) => res.data);
  },
  getDecisionLogs: (id: number, limit = 50, offset = 0, productId?: string, since?: string) => {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });
    if (productId) params.append('product_id', productId);
    if (since) params.append('since', since);
    return api.get<any[]>(`/bots/${id}/decision-logs?${params}`).then((res) => res.data);
  },
  getScannerLogs: (id: number, limit = 100, offset = 0, productId?: string, scanType?: string, decision?: string, since?: string) => {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });
    if (productId) params.append('product_id', productId);
    if (scanType) params.append('scan_type', scanType);
    if (decision) params.append('decision', decision);
    if (since) params.append('since', since);
    return api.get<any[]>(`/bots/${id}/scanner-logs?${params}`).then((res) => res.data);
  },
  getIndicatorLogs: (id: number, limit = 50, offset = 0, productId?: string, phase?: string, conditionsMet?: boolean, since?: string) => {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });
    if (productId) params.append('product_id', productId);
    if (phase) params.append('phase', phase);
    if (conditionsMet !== undefined) params.append('conditions_met', conditionsMet.toString());
    if (since) params.append('since', since);
    return api.get<any[]>(`/bots/${id}/indicator-logs?${params}`).then((res) => res.data);
  },
  // Cancel all positions for a bot
  cancelAllPositions: (id: number, confirm = true) =>
    api.post<{ cancelled_count: number; failed_count: number; errors: string[] }>(
      `/bots/${id}/cancel-all-positions`,
      null,
      { params: { confirm } }
    ).then((res) => res.data),
  // Sell all positions for a bot at market price
  sellAllPositions: (id: number, confirm = true) =>
    api.post<{ sold_count: number; failed_count: number; total_profit_quote: number; errors: string[] }>(
      `/bots/${id}/sell-all-positions`,
      null,
      { params: { confirm } }
    ).then((res) => res.data),
};

export const templatesApi = {
  getAll: () =>
    api.get<any[]>('/templates').then((res) => res.data),
  getById: (id: number) =>
    api.get<any>(`/templates/${id}`).then((res) => res.data),
  create: (template: any) =>
    api.post<any>('/templates', template).then((res) => res.data),
  update: (id: number, template: Partial<any>) =>
    api.put<any>(`/templates/${id}`, template).then((res) => res.data),
  delete: (id: number) =>
    api.delete<{ message: string }>(`/templates/${id}`).then((res) => res.data),
  seedDefaults: () =>
    api.post<{ message: string; templates: string[] }>('/templates/seed-defaults').then((res) => res.data),
};

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const orderHistoryApi = {
  getAll: (botId?: number, accountId?: number, status?: string, limit = 100, offset = 0) => {
    const params: any = { limit, offset };
    if (botId !== undefined) params.bot_id = botId;
    if (accountId !== undefined) params.account_id = accountId;
    if (status) params.status = status;
    return api.get<OrderHistory[]>('/order-history', { params }).then((res) => res.data);
  },
  getFailed: (botId?: number, accountId?: number, limit = 50) => {
    const params: any = { limit };
    if (botId !== undefined) params.bot_id = botId;
    if (accountId !== undefined) params.account_id = accountId;
    return api.get<OrderHistory[]>('/order-history/failed', { params }).then((res) => res.data);
  },
  getFailedPaginated: (page = 1, pageSize = 25, botId?: number, accountId?: number) => {
    const params: any = { page, page_size: pageSize };
    if (botId !== undefined) params.bot_id = botId;
    if (accountId !== undefined) params.account_id = accountId;
    return api.get<PaginatedResponse<OrderHistory>>('/order-history/failed/paginated', { params }).then((res) => res.data);
  },
  getStats: (botId?: number, accountId?: number) => {
    const params: any = {};
    if (botId !== undefined) params.bot_id = botId;
    if (accountId !== undefined) params.account_id = accountId;
    return api.get<{
      total_orders: number;
      successful_orders: number;
      failed_orders: number;
      canceled_orders: number;
      success_rate: number;
      failure_rate: number;
    }>('/order-history/stats', {
      params: Object.keys(params).length > 0 ? params : undefined
    }).then((res) => res.data);
  },
};

export interface BlacklistEntry {
  id: number;
  symbol: string;
  reason: string | null;
  created_at: string;
}

export interface CategorySettings {
  allowed_categories: string[];
  all_categories: string[];
}

export const blacklistApi = {
  getAll: () =>
    api.get<BlacklistEntry[]>('/blacklist/').then((res) => res.data),
  add: (symbol: string, reason?: string) =>
    api.post<BlacklistEntry>('/blacklist/single', { symbol, reason }).then((res) => res.data),
  addBulk: (symbols: string[], reason?: string) =>
    api.post<BlacklistEntry[]>('/blacklist/', { symbols, reason }).then((res) => res.data),
  remove: (symbol: string) =>
    api.delete<{ message: string }>(`/blacklist/${symbol}`).then((res) => res.data),
  updateReason: (symbol: string, reason: string | null) =>
    api.put<BlacklistEntry>(`/blacklist/${symbol}`, { reason }).then((res) => res.data),
  check: (symbol: string) =>
    api.get<{ symbol: string; is_blacklisted: boolean; reason: string | null }>(`/blacklist/check/${symbol}`).then((res) => res.data),
  // Category trading settings
  getCategories: () =>
    api.get<CategorySettings>('/blacklist/categories').then((res) => res.data),
  updateCategories: (allowedCategories: string[]) =>
    api.put<CategorySettings>('/blacklist/categories', { allowed_categories: allowedCategories }).then((res) => res.data),
  // AI review (uses longer timeout as it processes 300+ coins in batches)
  triggerAIReview: () =>
    api.post<{ status: string; categories: Record<string, number> }>('/blacklist/ai-review', {}, { timeout: 180000 }).then((res) => res.data),
  // AI provider settings for coin review
  getAIProvider: () =>
    api.get<AIProviderSettings>('/blacklist/ai-provider').then((res) => res.data),
  updateAIProvider: (provider: string) =>
    api.put<AIProviderSettings>('/blacklist/ai-provider', { provider }).then((res) => res.data),
};

export interface AIProviderSettings {
  provider: string;
  available_providers: string[];
}

// AI Provider Credentials
export interface AIProviderStatus {
  provider: string;
  name: string;
  billing_url: string | null;
  has_user_key: boolean;
  has_system_key: boolean;
  is_active: boolean;
  free_tier: string | null;
  key_preview?: string | null;
}

export interface AICredentialCreate {
  provider: string;
  api_key: string;
}

export const aiCredentialsApi = {
  getStatus: () =>
    api.get<AIProviderStatus[]>('/ai-credentials/status').then((res) => res.data),
  save: (provider: string, apiKey: string) =>
    api.post<{ message: string; provider: string }>('/ai-credentials', { provider, api_key: apiKey }).then((res) => res.data),
  delete: (provider: string) =>
    api.delete<{ message: string }>(`/ai-credentials/${provider}`).then((res) => res.data),
};

// Auto-Buy BTC Settings
export interface AutoBuySettings {
  enabled: boolean;
  check_interval_minutes: number;
  order_type: string;  // "market" or "limit"
  usd_enabled: boolean;
  usd_min: number;
  usdc_enabled: boolean;
  usdc_min: number;
  usdt_enabled: boolean;
  usdt_min: number;
}

export interface AutoBuySettingsUpdate {
  enabled?: boolean;
  check_interval_minutes?: number;
  order_type?: string;
  usd_enabled?: boolean;
  usd_min?: number;
  usdc_enabled?: boolean;
  usdc_min?: number;
  usdt_enabled?: boolean;
  usdt_min?: number;
}

export const autoBuyApi = {
  getSettings: (accountId: number) =>
    api.get<AutoBuySettings>(`/accounts/${accountId}/auto-buy-settings`).then((res) => res.data),
  updateSettings: (accountId: number, settings: AutoBuySettingsUpdate) =>
    api.put<AutoBuySettings>(`/accounts/${accountId}/auto-buy-settings`, settings).then((res) => res.data),
};

interface AccountValueSnapshot {
  date: string
  timestamp: string
  total_value_btc: number
  total_value_usd: number
}

export const accountValueApi = {
  getHistory: (days: number, includePaperTrading: boolean, accountId?: number) =>
    api.get<AccountValueSnapshot[]>('/account-value/history', {
      params: {
        days,
        include_paper_trading: includePaperTrading,
        account_id: accountId
      }
    }).then((res) => res.data),
  getLatest: (includePaperTrading: boolean) =>
    api.get<AccountValueSnapshot>('/account-value/latest', {
      params: { include_paper_trading: includePaperTrading }
    }).then((res) => res.data),
};
