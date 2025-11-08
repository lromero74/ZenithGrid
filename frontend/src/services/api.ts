import axios from 'axios';
import type {
  Position,
  Trade,
  Signal,
  MarketData,
  DashboardStats,
  Settings,
  Balances,
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
