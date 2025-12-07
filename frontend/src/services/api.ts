import axios from 'axios';
import type {
  Position,
  Trade,
  Signal,
  MarketData,
  DashboardStats,
  Settings,
  Balances,
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
  get: () => api.get<Settings>('/settings').then((res) => res.data),
  update: (settings: Partial<Settings>) =>
    api.post<{ message: string }>('/settings', settings).then((res) => res.data),
};

export const monitorApi = {
  start: () => api.post<{ message: string }>('/monitor/start').then((res) => res.data),
  stop: () => api.post<{ message: string }>('/monitor/stop').then((res) => res.data),
};

export const accountApi = {
  getBalances: () => api.get<Balances>('/account/balances').then((res) => res.data),
};

export const statusApi = {
  get: () =>
    api.get<{ api_connected: boolean; monitor: any; timestamp: string }>('/status')
      .then((res) => res.data),
};

export const botsApi = {
  getStrategies: () =>
    api.get<StrategyDefinition[]>('/bots/strategies').then((res) => res.data),
  getStrategy: (strategyId: string) =>
    api.get<StrategyDefinition>(`/bots/strategies/${strategyId}`).then((res) => res.data),
  getAll: () =>
    api.get<Bot[]>('/bots').then((res) => res.data),
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
  getAll: (botId?: number, status?: string, limit = 100, offset = 0) => {
    const params: any = { limit, offset };
    if (botId !== undefined) params.bot_id = botId;
    if (status) params.status = status;
    return api.get<OrderHistory[]>('/order-history', { params }).then((res) => res.data);
  },
  getFailed: (botId?: number, limit = 50) =>
    api.get<OrderHistory[]>('/order-history/failed', {
      params: { bot_id: botId, limit }
    }).then((res) => res.data),
  getFailedPaginated: (page = 1, pageSize = 25, botId?: number) =>
    api.get<PaginatedResponse<OrderHistory>>('/order-history/failed/paginated', {
      params: { page, page_size: pageSize, bot_id: botId }
    }).then((res) => res.data),
  getStats: (botId?: number) =>
    api.get<{
      total_orders: number;
      successful_orders: number;
      failed_orders: number;
      canceled_orders: number;
      success_rate: number;
      failure_rate: number;
    }>('/order-history/stats', {
      params: botId !== undefined ? { bot_id: botId } : undefined
    }).then((res) => res.data),
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
};

// AI Provider Credentials
export interface AIProviderStatus {
  provider: string;
  has_user_key: boolean;
  has_system_key: boolean;
  key_preview: string | null;
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
