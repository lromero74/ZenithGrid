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

export const api = axios.create({
  baseURL: '/api',
  timeout: 45000,
});

// Token refresh mutex — prevents multiple concurrent refresh attempts
let isRefreshing = false;
let refreshSubscribers: ((token: string | null) => void)[] = [];

function subscribeToRefresh(callback: (token: string | null) => void) {
  refreshSubscribers.push(callback);
}

function onRefreshComplete(token: string | null) {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
}

function forceLogout() {
  localStorage.removeItem('auth_access_token');
  localStorage.removeItem('auth_refresh_token');
  localStorage.removeItem('auth_token_expiry');
  localStorage.removeItem('auth_user');
  window.dispatchEvent(new Event('auth-logout'));
}

/**
 * Attempt to refresh the access token using the stored refresh token.
 * Returns the new access token on success, null on failure.
 */
async function tryRefreshToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem('auth_refresh_token');
  if (!refreshToken) return null;

  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) return null;

    const data = await response.json();
    const expiryTime = Date.now() + data.expires_in * 1000;
    localStorage.setItem('auth_access_token', data.access_token);
    localStorage.setItem('auth_refresh_token', data.refresh_token);
    localStorage.setItem('auth_token_expiry', expiryTime.toString());
    localStorage.setItem('auth_user', JSON.stringify(data.user));
    return data.access_token;
  } catch {
    return null;
  }
}

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

// Add response interceptor: on 401, try token refresh before logging out
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Only handle 401, and don't retry if already retried or if this IS the refresh request
    if (error.response?.status === 401 && !originalRequest._retry && !originalRequest.url?.includes('/auth/refresh')) {
      originalRequest._retry = true;

      if (isRefreshing) {
        // Another request is already refreshing — wait for it
        return new Promise((resolve, reject) => {
          subscribeToRefresh((token) => {
            if (token) {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(api(originalRequest));
            } else {
              reject(error);
            }
          });
        });
      }

      isRefreshing = true;
      const newToken = await tryRefreshToken();
      isRefreshing = false;
      onRefreshComplete(newToken);

      if (newToken) {
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      }

      // Refresh failed — now logout
      forceLogout();
    }

    return Promise.reject(error);
  }
);

/**
 * Authenticated fetch wrapper - adds Authorization header from localStorage.
 * Use this instead of raw fetch() for any protected API endpoint.
 * On 401, attempts a token refresh before dispatching logout.
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem('auth_access_token');
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      ...headers,
      ...(options.headers as Record<string, string> || {}),
    },
  });

  if (response.status === 401 && !url.includes('/auth/refresh')) {
    // Use the same mutex as the axios interceptor
    if (isRefreshing) {
      return new Promise<Response>((resolve, reject) => {
        subscribeToRefresh((token) => {
          if (token) {
            resolve(fetch(url, {
              ...options,
              headers: {
                ...(options.headers as Record<string, string> || {}),
                'Authorization': `Bearer ${token}`,
              },
            }));
          } else {
            reject(new Error('Token refresh failed'));
          }
        });
      });
    }

    isRefreshing = true;
    const newToken = await tryRefreshToken();
    isRefreshing = false;
    onRefreshComplete(newToken);

    if (newToken) {
      return fetch(url, {
        ...options,
        headers: {
          ...(options.headers as Record<string, string> || {}),
          'Authorization': `Bearer ${newToken}`,
        },
      });
    }
    // Refresh failed — logout
    forceLogout();
  }

  return response;
}

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
    api.get<Position[]>('/positions/', { params: { status, limit } }).then((res) => res.data),
  getById: (id: number) =>
    api.get<Position>(`/positions/${id}`).then((res) => res.data),
  getTrades: (id: number) =>
    api.get<Trade[]>(`/positions/${id}/trades`).then((res) => res.data),
  getAILogs: (id: number, includeBeforeOpen = true) =>
    api.get<AIBotLog[]>(`/positions/${id}/ai-logs`, { params: { include_before_open: includeBeforeOpen } }).then((res) => res.data),
  close: (id: number, skipSlippageGuard = false) =>
    api.post<{
      message?: string; profit_quote?: number; profit_percentage?: number;
      slippage_warning?: string; requires_confirmation?: boolean;
    }>(`/positions/${id}/force-close`, null, {
      params: skipSlippageGuard ? { skip_slippage_guard: true } : undefined,
    }).then((res) => res.data),
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
  resizeAllBudgets: (accountId?: number) =>
    api.post<{ message: string; updated_count: number; total_count: number; results: { id: number; pair: string; old_max: number; new_max: number; skipped?: string }[] }>(
      '/positions/resize-all-budgets', null, { params: accountId ? { account_id: accountId } : {} }
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
      alltime_profit_btc: number;
      alltime_profit_usd: number;
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
    return api.get<Bot[]>(`/bots/${params}`).then((res) => res.data)
  },
  getById: (id: number) =>
    api.get<Bot>(`/bots/${id}`).then((res) => res.data),
  create: (bot: BotCreate) =>
    api.post<Bot>('/bots/', bot).then((res) => res.data),
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
    return api.get<OrderHistory[]>('/order-history/', { params }).then((res) => res.data);
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
  user_override_category?: string | null;
}

export interface UserOverrideResponse {
  symbol: string;
  category: string;
  reason: string | null;
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
  // Per-user category overrides
  getOverrides: () =>
    api.get<UserOverrideResponse[]>('/blacklist/overrides/').then((res) => res.data),
  setOverride: (symbol: string, category: string, reason?: string) =>
    api.put<UserOverrideResponse>(`/blacklist/overrides/${symbol}`, { category, reason }).then((res) => res.data),
  removeOverride: (symbol: string) =>
    api.delete<{ message: string }>(`/blacklist/overrides/${symbol}`).then((res) => res.data),
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

export interface ActivityItem {
  date: string
  line: 'btc' | 'usd'
  category: 'trade_win' | 'trade_loss' | 'deposit' | 'withdrawal'
  amount: number
  count: number
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
  getActivity: (days: number, includePaperTrading: boolean, accountId?: number) =>
    api.get<ActivityItem[]>('/account-value/activity', {
      params: {
        days,
        include_paper_trading: includePaperTrading,
        account_id: accountId
      }
    }).then((res) => res.data),
};

// Reports & Goals
import type {
  ReportGoal, ReportSchedule, ReportSummary,
  ScheduleType, PeriodWindow, LookbackUnit, GoalTrendData,
  ExpenseItem,
} from '../types'

export interface ScheduleCreatePayload {
  name: string
  schedule_type: ScheduleType
  schedule_days?: number[] | null
  quarter_start_month?: number | null
  period_window: PeriodWindow
  lookback_value?: number | null
  lookback_unit?: LookbackUnit | null
  force_standard_days?: number[] | null
  account_id?: number | null
  recipients: string[]
  ai_provider?: string | null
  goal_ids: number[]
  is_enabled?: boolean
}

export const reportsApi = {
  // Goals
  getGoals: (accountId?: number) =>
    api.get<ReportGoal[]>('/reports/goals', {
      params: accountId ? { account_id: accountId } : {}
    }).then(r => r.data),
  createGoal: (data: Omit<ReportGoal, 'id' | 'start_date' | 'target_date' | 'is_active' | 'achieved_at' | 'created_at'>) =>
    api.post<ReportGoal>('/reports/goals', data).then(r => r.data),
  updateGoal: (id: number, data: Partial<ReportGoal>) =>
    api.put<ReportGoal>(`/reports/goals/${id}`, data).then(r => r.data),
  deleteGoal: (id: number) => api.delete(`/reports/goals/${id}`).then(r => r.data),
  getGoalTrend: (goalId: number, fromDate?: string, toDate?: string) => {
    const params: Record<string, string> = {}
    if (fromDate) params.from_date = fromDate
    if (toDate) params.to_date = toDate
    return api.get<GoalTrendData>(`/reports/goals/${goalId}/trend`, { params }).then(r => r.data)
  },

  // Expense Items
  getExpenseItems: (goalId: number) =>
    api.get<ExpenseItem[]>(`/reports/goals/${goalId}/expenses`).then(r => r.data),
  createExpenseItem: (goalId: number, data: Omit<ExpenseItem, 'id' | 'goal_id' | 'is_active' | 'normalized_amount' | 'created_at'>) =>
    api.post<ExpenseItem>(`/reports/goals/${goalId}/expenses`, data).then(r => r.data),
  updateExpenseItem: (goalId: number, itemId: number, data: Partial<ExpenseItem>) =>
    api.put<ExpenseItem>(`/reports/goals/${goalId}/expenses/${itemId}`, data).then(r => r.data),
  deleteExpenseItem: (goalId: number, itemId: number) =>
    api.delete(`/reports/goals/${goalId}/expenses/${itemId}`).then(r => r.data),
  reorderExpenseItems: (goalId: number, itemIds: number[]) =>
    api.put(`/reports/goals/${goalId}/expenses/reorder`, { item_ids: itemIds }).then(r => r.data),
  getExpenseCategories: () =>
    api.get<string[]>('/reports/expense-categories').then(r => r.data),

  // Schedules
  getSchedules: (accountId?: number) =>
    api.get<ReportSchedule[]>('/reports/schedules', {
      params: accountId ? { account_id: accountId } : {}
    }).then(r => r.data),
  createSchedule: (data: ScheduleCreatePayload) =>
    api.post<ReportSchedule>('/reports/schedules', data).then(r => r.data),
  updateSchedule: (id: number, data: Record<string, unknown>) =>
    api.put<ReportSchedule>(`/reports/schedules/${id}`, data).then(r => r.data),
  deleteSchedule: (id: number) => api.delete(`/reports/schedules/${id}`).then(r => r.data),

  // Reports
  getHistory: (limit: number = 20, offset: number = 0, scheduleId?: number, accountId?: number) =>
    api.get<{ total: number; reports: ReportSummary[] }>('/reports/history', {
      params: {
        limit, offset,
        ...(scheduleId ? { schedule_id: scheduleId } : {}),
        ...(accountId ? { account_id: accountId } : {}),
      }
    }).then(r => r.data),
  getReport: (id: number) => api.get<ReportSummary>(`/reports/${id}`).then(r => r.data),
  downloadPdf: (id: number) => api.get(`/reports/${id}/pdf`, { responseType: 'blob' }).then(r => r.data),
  generateReport: (scheduleId: number) =>
    api.post<ReportSummary>('/reports/generate', { schedule_id: scheduleId }).then(r => r.data),
  previewReport: (scheduleId: number) =>
    api.post<ReportSummary>('/reports/preview', { schedule_id: scheduleId }).then(r => r.data),
  deleteReport: (id: number) =>
    api.delete<{ detail: string }>(`/reports/${id}`).then(r => r.data),
  bulkDeleteReports: (ids: number[]) =>
    api.post<{ deleted: number }>('/reports/bulk-delete', { report_ids: ids }).then(r => r.data),
};

// Transfers (deposit/withdrawal tracking)
export interface TransferItem {
  occurred_at: string
  type: string
  amount_usd: number | null
  currency: string
  amount: number
}

export interface TransferRecentSummary {
  last_30d_net_deposits_usd: number
  last_30d_deposit_count: number
  last_30d_withdrawal_count: number
  transfers: TransferItem[]
}

export const transfersApi = {
  sync: () => api.post<{ status: string; new_transfers: number }>('/transfers/sync').then(r => r.data),
  list: (params?: { start?: string; end?: string; account_id?: number; limit?: number; offset?: number }) =>
    api.get<{ total: number; transfers: any[] }>('/transfers', { params }).then(r => r.data),
  create: (data: { account_id: number; transfer_type: string; amount: number; currency: string; amount_usd?: number; occurred_at: string }) =>
    api.post<any>('/transfers', data).then(r => r.data),
  delete: (id: number) => api.delete<{ detail: string }>(`/transfers/${id}`).then(r => r.data),
  getSummary: (params?: { start?: string; end?: string; account_id?: number }) =>
    api.get<{ net_deposits_usd: number; total_deposits_usd: number; total_withdrawals_usd: number; deposit_count: number; withdrawal_count: number }>('/transfers/summary', { params }).then(r => r.data),
  getRecentSummary: () =>
    api.get<TransferRecentSummary>('/transfers/recent-summary').then(r => r.data),
};
