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

export const dashboardApi = {
  getStats: () => api.get<DashboardStats>('/dashboard').then((res) => res.data),
};

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
    api.post<{ message: string; profit_btc: number; profit_percentage: number }>(`/positions/${id}/force-close`)
      .then((res) => res.data),
  addFunds: (id: number, btcAmount: number) =>
    api.post<{ message: string; trade_id: number; price: number; eth_acquired: number }>(`/positions/${id}/add-funds`, { btc_amount: btcAmount })
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
