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
  getStats: (id: number) =>
    api.get<BotStats>(`/bots/${id}/stats`).then((res) => res.data),
};
