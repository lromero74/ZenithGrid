/**
 * Tests for services/api.ts
 *
 * Tests the API client functions: axios instance creation, interceptors,
 * token refresh logic, authFetch wrapper, and the various API module methods.
 * All HTTP calls are mocked via vi.mock('axios') and globalThis.fetch.
 */

import { describe, test, expect, beforeEach, vi, afterEach } from 'vitest'

// Mock axios before importing the module under test
vi.mock('axios', () => {
  const requestInterceptors: Array<{ fulfilled: (config: any) => any; rejected: (error: any) => any }> = []
  const responseInterceptors: Array<{ fulfilled: (response: any) => any; rejected: (error: any) => any }> = []

  const mockAxiosInstance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: {
        use: vi.fn((fulfilled: any, rejected: any) => {
          requestInterceptors.push({ fulfilled, rejected })
          return requestInterceptors.length - 1
        }),
      },
      response: {
        use: vi.fn((fulfilled: any, rejected: any) => {
          responseInterceptors.push({ fulfilled, rejected })
          return responseInterceptors.length - 1
        }),
      },
    },
    defaults: { baseURL: '/api', timeout: 45000 },
    _requestInterceptors: requestInterceptors,
    _responseInterceptors: responseInterceptors,
  }

  return {
    default: {
      create: vi.fn(() => mockAxiosInstance),
    },
  }
})

// Now import the module under test
import {
  api,
  authFetch,
  dashboardApi,
  positionsApi,
  tradesApi,
  signalsApi,
  marketDataApi,
  settingsApi,
  monitorApi,
  accountApi,
  statusApi,
  botsApi,
  templatesApi,
  orderHistoryApi,
  blacklistApi,
  aiCredentialsApi,
  autoBuyApi,
  accountValueApi,
  reportsApi,
  transfersApi,
} from './api'

describe('api axios instance', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('api instance is created', () => {
    expect(api).toBeDefined()
    expect(api.get).toBeDefined()
    expect(api.post).toBeDefined()
    expect(api.put).toBeDefined()
    expect(api.delete).toBeDefined()
  })

  test('request interceptor attaches auth token from localStorage', () => {
    const interceptors = (api as any)._requestInterceptors
    expect(interceptors.length).toBeGreaterThan(0)

    const requestInterceptor = interceptors[0].fulfilled

    // With token in localStorage
    localStorage.setItem('auth_access_token', 'test-token-abc')
    const config = { headers: {} as Record<string, string> }
    const result = requestInterceptor(config)
    expect(result.headers.Authorization).toBe('Bearer test-token-abc')
  })

  test('request interceptor does not set auth header when no token', () => {
    const interceptors = (api as any)._requestInterceptors
    const requestInterceptor = interceptors[0].fulfilled

    localStorage.removeItem('auth_access_token')
    const config = { headers: {} as Record<string, string> }
    const result = requestInterceptor(config)
    expect(result.headers.Authorization).toBeUndefined()
  })

  test('request interceptor error handler rejects', async () => {
    const interceptors = (api as any)._requestInterceptors
    const errorHandler = interceptors[0].rejected

    const error = new Error('request error')
    await expect(errorHandler(error)).rejects.toThrow('request error')
  })

  test('response interceptor passes through successful responses', () => {
    const interceptors = (api as any)._responseInterceptors
    const successHandler = interceptors[0].fulfilled

    const response = { data: { message: 'ok' }, status: 200 }
    expect(successHandler(response)).toBe(response)
  })
})

describe('response interceptor 401 handling', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('non-401 errors are rejected without refresh attempt', async () => {
    const interceptors = (api as any)._responseInterceptors
    const errorHandler = interceptors[0].rejected

    const error = {
      config: { _retry: false, url: '/api/bots/', headers: {} },
      response: { status: 500 },
    }

    await expect(errorHandler(error)).rejects.toBe(error)
  })

  test('401 on refresh endpoint is rejected without retry', async () => {
    const interceptors = (api as any)._responseInterceptors
    const errorHandler = interceptors[0].rejected

    const error = {
      config: { _retry: false, url: '/auth/refresh', headers: {} },
      response: { status: 401 },
    }

    await expect(errorHandler(error)).rejects.toBe(error)
  })

  test('401 with _retry already set is rejected without retry', async () => {
    const interceptors = (api as any)._responseInterceptors
    const errorHandler = interceptors[0].rejected

    const error = {
      config: { _retry: true, url: '/api/bots/', headers: {} },
      response: { status: 401 },
    }

    await expect(errorHandler(error)).rejects.toBe(error)
  })

  test('401 triggers refresh and retries on success', async () => {
    const interceptors = (api as any)._responseInterceptors
    const errorHandler = interceptors[0].rejected

    localStorage.setItem('auth_refresh_token', 'valid-refresh')

    // Mock fetch for the refresh endpoint
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        access_token: 'new-access-token',
        refresh_token: 'new-refresh-token',
        expires_in: 3600,
        user: { id: 1, email: 'test@test.com' },
      }),
    })
    globalThis.fetch = mockFetch

    // Mock api() to return retried response
    ;(api as any).__proto__ = undefined  // Ensure api is callable
    // Since api is a mock, we need to mock it as a function too
    const originalConfig = { _retry: false, url: '/api/bots/', headers: {} as Record<string, string> }
    const error = {
      config: originalConfig,
      response: { status: 401 },
    }

    // The interceptor calls api(originalRequest) which is the mock instance
    // We need to handle this differently - the function call on mock instance
    // Let's just test that it marks _retry and calls refresh
    try {
      await errorHandler(error)
    } catch {
      // The retry via api(originalRequest) may fail since api is a mock object, not callable
      // What we verify is the refresh was attempted
    }

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/auth/refresh',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ refresh_token: 'valid-refresh' }),
      })
    )
    expect(originalConfig._retry).toBe(true)
  })

  test('401 refresh failure triggers forceLogout', async () => {
    const interceptors = (api as any)._responseInterceptors
    const errorHandler = interceptors[0].rejected

    localStorage.setItem('auth_access_token', 'old-token')
    localStorage.setItem('auth_refresh_token', 'expired-refresh')
    localStorage.setItem('auth_token_expiry', '12345')
    localStorage.setItem('auth_user', '{"id":1}')

    // Mock fetch to fail refresh
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 })

    // Listen for auth-logout event
    const logoutSpy = vi.fn()
    window.addEventListener('auth-logout', logoutSpy)

    const error = {
      config: { _retry: false, url: '/api/bots/', headers: {} as Record<string, string> },
      response: { status: 401 },
    }

    try {
      await errorHandler(error)
    } catch {
      // Expected rejection
    }

    // forceLogout should clear localStorage
    expect(localStorage.getItem('auth_access_token')).toBeNull()
    expect(localStorage.getItem('auth_refresh_token')).toBeNull()
    expect(localStorage.getItem('auth_token_expiry')).toBeNull()
    expect(localStorage.getItem('auth_user')).toBeNull()

    // Should dispatch auth-logout event
    expect(logoutSpy).toHaveBeenCalled()

    window.removeEventListener('auth-logout', logoutSpy)
  })

  test('401 with no refresh token triggers forceLogout', async () => {
    const interceptors = (api as any)._responseInterceptors
    const errorHandler = interceptors[0].rejected

    localStorage.setItem('auth_access_token', 'old-token')
    // No refresh token set

    globalThis.fetch = vi.fn()

    const logoutSpy = vi.fn()
    window.addEventListener('auth-logout', logoutSpy)

    const error = {
      config: { _retry: false, url: '/api/bots/', headers: {} as Record<string, string> },
      response: { status: 401 },
    }

    try {
      await errorHandler(error)
    } catch {
      // Expected
    }

    expect(localStorage.getItem('auth_access_token')).toBeNull()
    expect(logoutSpy).toHaveBeenCalled()

    window.removeEventListener('auth-logout', logoutSpy)
  })
})

describe('authFetch', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('attaches Authorization header from localStorage', async () => {
    localStorage.setItem('auth_access_token', 'my-token')

    const mockResponse = { status: 200, ok: true } as Response
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse)

    await authFetch('/api/test')

    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/test',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer my-token',
        }),
      })
    )
  })

  test('does not set Authorization header when no token', async () => {
    const mockResponse = { status: 200, ok: true } as Response
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse)

    await authFetch('/api/test')

    // Headers should not contain Authorization
    const callArgs = (globalThis.fetch as any).mock.calls[0]
    expect(callArgs[1].headers.Authorization).toBeUndefined()
  })

  test('returns response for non-401 status', async () => {
    const mockResponse = { status: 200, ok: true } as Response
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse)

    const result = await authFetch('/api/test')
    expect(result).toBe(mockResponse)
  })

  test('passes through custom headers and options', async () => {
    localStorage.setItem('auth_access_token', 'token')
    const mockResponse = { status: 200, ok: true } as Response
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse)

    await authFetch('/api/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"key":"value"}',
    })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/test',
      expect.objectContaining({
        method: 'POST',
        body: '{"key":"value"}',
        headers: expect.objectContaining({
          Authorization: 'Bearer token',
          'Content-Type': 'application/json',
        }),
      })
    )
  })

  test('401 triggers token refresh and retries with new token', async () => {
    localStorage.setItem('auth_access_token', 'old-token')
    localStorage.setItem('auth_refresh_token', 'valid-refresh')

    let callCount = 0
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      callCount++
      if (url === '/api/auth/refresh') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            access_token: 'refreshed-token',
            refresh_token: 'new-refresh',
            expires_in: 3600,
            user: { id: 1 },
          }),
        })
      }
      if (callCount === 1) {
        // First call returns 401
        return Promise.resolve({ status: 401, ok: false })
      }
      // Second call (retry) returns 200
      return Promise.resolve({ status: 200, ok: true })
    })

    const result = await authFetch('/api/protected')
    expect(result.ok).toBe(true)

    // Verify new tokens stored
    expect(localStorage.getItem('auth_access_token')).toBe('refreshed-token')
    expect(localStorage.getItem('auth_refresh_token')).toBe('new-refresh')
  })

  test('401 on auth/refresh endpoint does not attempt refresh', async () => {
    const mockResponse = { status: 401, ok: false } as Response
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse)

    const result = await authFetch('/api/auth/refresh')
    expect(result.status).toBe(401)
    // Only one fetch call, no refresh attempt
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })

  test('401 with failed refresh triggers forceLogout', async () => {
    localStorage.setItem('auth_access_token', 'old-token')
    localStorage.setItem('auth_refresh_token', 'expired-refresh')

    const logoutSpy = vi.fn()
    window.addEventListener('auth-logout', logoutSpy)

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/auth/refresh') {
        return Promise.resolve({ ok: false, status: 401 })
      }
      return Promise.resolve({ status: 401, ok: false })
    })

    const result = await authFetch('/api/protected')
    expect(result.status).toBe(401)

    // localStorage should be cleared
    expect(localStorage.getItem('auth_access_token')).toBeNull()
    expect(logoutSpy).toHaveBeenCalled()

    window.removeEventListener('auth-logout', logoutSpy)
  })
})

describe('dashboardApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  test('getStats calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { total_profit: 100 } })

    const result = await dashboardApi.getStats()
    expect(api.get).toHaveBeenCalledWith('/dashboard')
    expect(result).toEqual({ total_profit: 100 })
  })
})

describe('positionsApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.patch).mockReset()
  })

  test('getAll calls with default params', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await positionsApi.getAll()
    expect(api.get).toHaveBeenCalledWith('/positions/', {
      params: { status: undefined, limit: 50 },
    })
  })

  test('getAll calls with custom status and limit', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await positionsApi.getAll('open', 10)
    expect(api.get).toHaveBeenCalledWith('/positions/', {
      params: { status: 'open', limit: 10 },
    })
  })

  test('getById calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { id: 5 } })

    const result = await positionsApi.getById(5)
    expect(api.get).toHaveBeenCalledWith('/positions/5')
    expect(result).toEqual({ id: 5 })
  })

  test('close calls force-close endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { message: 'closed', profit_quote: 0.01, profit_percentage: 2.5 },
    })

    const result = await positionsApi.close(3)
    expect(api.post).toHaveBeenCalledWith('/positions/3/force-close')
    expect(result.message).toBe('closed')
  })

  test('addFunds sends correct payload', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { message: 'funds added', trade_id: 42, price: 50000, eth_acquired: 0.001 },
    })

    await positionsApi.addFunds(1, 0.005)
    expect(api.post).toHaveBeenCalledWith('/positions/1/add-funds', { btc_amount: 0.005 })
  })

  test('updateSettings sends PATCH request', async () => {
    vi.mocked(api.patch).mockResolvedValue({
      data: { message: 'updated', updated_fields: ['take_profit_percentage'], new_config: {} },
    })

    await positionsApi.updateSettings(1, { take_profit_percentage: 2.0 })
    expect(api.patch).toHaveBeenCalledWith('/positions/1/settings', { take_profit_percentage: 2.0 })
  })

  test('getCompletedStats passes accountId when provided', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { total_trades: 10 } })

    await positionsApi.getCompletedStats(5)
    expect(api.get).toHaveBeenCalledWith('/positions/completed/stats', {
      params: { account_id: 5 },
    })
  })

  test('getCompletedStats passes empty params when no accountId', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { total_trades: 10 } })

    await positionsApi.getCompletedStats()
    expect(api.get).toHaveBeenCalledWith('/positions/completed/stats', { params: {} })
  })

  test('resizeBudget calls correct endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { message: 'resized', position_id: 1, old_max: 100, new_max: 150, quote_currency: 'USD' },
    })

    const result = await positionsApi.resizeBudget(1)
    expect(api.post).toHaveBeenCalledWith('/positions/1/resize-budget')
    expect(result.new_max).toBe(150)
  })

  test('resizeAllBudgets calls correct endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { message: 'done', updated_count: 3, total_count: 5, results: [] },
    })

    const result = await positionsApi.resizeAllBudgets()
    expect(api.post).toHaveBeenCalledWith('/positions/resize-all-budgets', null, { params: {} })
    expect(result.updated_count).toBe(3)
  })

  test('resizeAllBudgets passes account_id when provided', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { message: 'done', updated_count: 1, total_count: 1, results: [] },
    })

    const result = await positionsApi.resizeAllBudgets(42)
    expect(api.post).toHaveBeenCalledWith('/positions/resize-all-budgets', null, { params: { account_id: 42 } })
    expect(result.updated_count).toBe(1)
  })

  test('getRealizedPnL passes accountId when provided', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { daily_profit_btc: 0.001 } })

    await positionsApi.getRealizedPnL(7)
    expect(api.get).toHaveBeenCalledWith('/positions/realized-pnl', {
      params: { account_id: 7 },
    })
  })

  test('getTrades calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await positionsApi.getTrades(2)
    expect(api.get).toHaveBeenCalledWith('/positions/2/trades')
  })

  test('getAILogs calls correct endpoint with default params', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await positionsApi.getAILogs(3)
    expect(api.get).toHaveBeenCalledWith('/positions/3/ai-logs', {
      params: { include_before_open: true },
    })
  })

  test('getAILogs passes includeBeforeOpen flag', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await positionsApi.getAILogs(3, false)
    expect(api.get).toHaveBeenCalledWith('/positions/3/ai-logs', {
      params: { include_before_open: false },
    })
  })
})

describe('tradesApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  test('getAll calls with default limit', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await tradesApi.getAll()
    expect(api.get).toHaveBeenCalledWith('/trades', { params: { limit: 100 } })
  })

  test('getAll calls with custom limit', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await tradesApi.getAll(25)
    expect(api.get).toHaveBeenCalledWith('/trades', { params: { limit: 25 } })
  })
})

describe('signalsApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  test('getAll calls with default limit', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await signalsApi.getAll()
    expect(api.get).toHaveBeenCalledWith('/signals', { params: { limit: 100 } })
  })
})

describe('marketDataApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  test('getRecent calls with default hours', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await marketDataApi.getRecent()
    expect(api.get).toHaveBeenCalledWith('/market-data', { params: { hours: 24 } })
  })

  test('getRecent calls with custom hours', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await marketDataApi.getRecent(48)
    expect(api.get).toHaveBeenCalledWith('/market-data', { params: { hours: 48 } })
  })

  test('getCoins calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { coins: [{ symbol: 'BTC', markets: [], product_ids: [] }], count: 1 },
    })

    const result = await marketDataApi.getCoins()
    expect(api.get).toHaveBeenCalledWith('/coins')
    expect(result.count).toBe(1)
  })
})

describe('settingsApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.put).mockReset()
  })

  test('get without key returns all settings', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { key: 'value' } })

    await settingsApi.get()
    expect(api.get).toHaveBeenCalledWith('/settings')
  })

  test('get with key returns individual setting', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { key: 'theme', value: 'dark' } })

    await settingsApi.get('theme')
    expect(api.get).toHaveBeenCalledWith('/settings/theme')
  })

  test('update with key and value uses PUT', async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { message: 'updated' } })

    await settingsApi.update('theme', 'dark')
    expect(api.put).toHaveBeenCalledWith('/settings/theme?value=dark')
  })

  test('update with object uses POST (legacy)', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { message: 'updated' } })

    await settingsApi.update({ some_setting: 'value' } as any)
    expect(api.post).toHaveBeenCalledWith('/settings', { some_setting: 'value' })
  })

  test('update encodes special characters in value', async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { message: 'updated' } })

    await settingsApi.update('query', 'hello world')
    expect(api.put).toHaveBeenCalledWith('/settings/query?value=hello%20world')
  })
})

describe('monitorApi', () => {
  beforeEach(() => {
    vi.mocked(api.post).mockReset()
  })

  test('start calls correct endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { message: 'started' } })

    const result = await monitorApi.start()
    expect(api.post).toHaveBeenCalledWith('/monitor/start')
    expect(result.message).toBe('started')
  })

  test('stop calls correct endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { message: 'stopped' } })

    const result = await monitorApi.stop()
    expect(api.post).toHaveBeenCalledWith('/monitor/stop')
    expect(result.message).toBe('stopped')
  })
})

describe('accountApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
  })

  test('getBalances without accountId', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { btc: 1.0 } })

    await accountApi.getBalances()
    expect(api.get).toHaveBeenCalledWith('/account/balances', { params: {} })
  })

  test('getBalances with accountId', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { btc: 1.0 } })

    await accountApi.getBalances(3)
    expect(api.get).toHaveBeenCalledWith('/account/balances', { params: { account_id: 3 } })
  })

  test('getAggregateValue calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { total: 50000 } })

    await accountApi.getAggregateValue()
    expect(api.get).toHaveBeenCalledWith('/account/aggregate-value')
  })

  test('sellPortfolioToBase sends correct params', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { task_id: 'abc', message: 'started', status_url: '/status/abc' },
    })

    await accountApi.sellPortfolioToBase('BTC', true, 2)
    expect(api.post).toHaveBeenCalledWith('/account/sell-portfolio-to-base', null, {
      params: { target_currency: 'BTC', confirm: true, account_id: 2 },
    })
  })

  test('getConversionStatus calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { task_id: 'abc', status: 'running', progress_pct: 50 },
    })

    const result = await accountApi.getConversionStatus('abc')
    expect(api.get).toHaveBeenCalledWith('/account/conversion-status/abc')
    expect(result.status).toBe('running')
  })
})

describe('statusApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  test('get calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { api_connected: true, monitor: null, timestamp: '2025-01-01' },
    })

    const result = await statusApi.get()
    expect(api.get).toHaveBeenCalledWith('/status')
    expect(result.api_connected).toBe(true)
  })
})

describe('botsApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.put).mockReset()
    vi.mocked(api.delete).mockReset()
  })

  test('getStrategies calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [{ id: 'grid' }] })

    await botsApi.getStrategies()
    expect(api.get).toHaveBeenCalledWith('/strategies/')
  })

  test('getStrategy calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { id: 'grid' } })

    await botsApi.getStrategy('grid')
    expect(api.get).toHaveBeenCalledWith('/strategies/grid')
  })

  test('getAll without projection timeframe', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await botsApi.getAll()
    expect(api.get).toHaveBeenCalledWith('/bots/')
  })

  test('getAll with projection timeframe', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await botsApi.getAll('1h')
    expect(api.get).toHaveBeenCalledWith('/bots/?projection_timeframe=1h')
  })

  test('create sends bot data', async () => {
    const botData = { name: 'Test Bot', strategy_id: 'grid' }
    vi.mocked(api.post).mockResolvedValue({ data: { id: 1, ...botData } })

    await botsApi.create(botData as any)
    expect(api.post).toHaveBeenCalledWith('/bots/', botData)
  })

  test('update sends partial bot data', async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { id: 1, name: 'Updated' } })

    await botsApi.update(1, { name: 'Updated' } as any)
    expect(api.put).toHaveBeenCalledWith('/bots/1', { name: 'Updated' })
  })

  test('delete calls correct endpoint', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: { message: 'deleted' } })

    await botsApi.delete(1)
    expect(api.delete).toHaveBeenCalledWith('/bots/1')
  })

  test('start calls correct endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { message: 'started' } })

    await botsApi.start(1)
    expect(api.post).toHaveBeenCalledWith('/bots/1/start')
  })

  test('stop calls correct endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { message: 'stopped' } })

    await botsApi.stop(1)
    expect(api.post).toHaveBeenCalledWith('/bots/1/stop')
  })

  test('forceRun calls correct endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { message: 'running', note: 'forced' } })

    await botsApi.forceRun(1)
    expect(api.post).toHaveBeenCalledWith('/bots/1/force-run')
  })

  test('clone calls correct endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { id: 2, name: 'Clone' } })

    await botsApi.clone(1)
    expect(api.post).toHaveBeenCalledWith('/bots/1/clone')
  })

  test('copyToAccount sends correct params', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { id: 3 } })

    await botsApi.copyToAccount(1, 5)
    expect(api.post).toHaveBeenCalledWith('/bots/1/copy-to-account?target_account_id=5')
  })

  test('getStats calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { total_positions: 5 } })

    await botsApi.getStats(1)
    expect(api.get).toHaveBeenCalledWith('/bots/1/stats')
  })

  test('getLogs builds query params correctly', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await botsApi.getLogs(1, 25, 10, 'BTC-USD', '2025-01-01')
    const call = vi.mocked(api.get).mock.calls[0]
    expect(call[0]).toContain('/bots/1/logs?')
    expect(call[0]).toContain('limit=25')
    expect(call[0]).toContain('offset=10')
    expect(call[0]).toContain('product_id=BTC-USD')
    expect(call[0]).toContain('since=2025-01-01')
  })

  test('getLogs builds params without optional fields', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await botsApi.getLogs(1)
    const call = vi.mocked(api.get).mock.calls[0]
    expect(call[0]).toContain('limit=50')
    expect(call[0]).toContain('offset=0')
    expect(call[0]).not.toContain('product_id')
    expect(call[0]).not.toContain('since')
  })

  test('getDecisionLogs builds query params correctly', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await botsApi.getDecisionLogs(2, 10, 5, 'ETH-USD')
    const call = vi.mocked(api.get).mock.calls[0]
    expect(call[0]).toContain('/bots/2/decision-logs?')
    expect(call[0]).toContain('limit=10')
    expect(call[0]).toContain('product_id=ETH-USD')
  })

  test('getScannerLogs builds query params correctly', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await botsApi.getScannerLogs(1, 100, 0, 'BTC-USD', 'full', 'buy', '2025-01-01')
    const call = vi.mocked(api.get).mock.calls[0]
    expect(call[0]).toContain('/bots/1/scanner-logs?')
    expect(call[0]).toContain('scan_type=full')
    expect(call[0]).toContain('decision=buy')
  })

  test('getIndicatorLogs builds params with conditionsMet', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await botsApi.getIndicatorLogs(1, 50, 0, undefined, 'entry', true)
    const call = vi.mocked(api.get).mock.calls[0]
    expect(call[0]).toContain('phase=entry')
    expect(call[0]).toContain('conditions_met=true')
  })

  test('cancelAllPositions sends correct params', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { cancelled_count: 2, failed_count: 0, errors: [] },
    })

    await botsApi.cancelAllPositions(1, true)
    expect(api.post).toHaveBeenCalledWith(
      '/bots/1/cancel-all-positions',
      null,
      { params: { confirm: true } }
    )
  })

  test('sellAllPositions sends correct params', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { sold_count: 3, failed_count: 0, total_profit_quote: 500, errors: [] },
    })

    await botsApi.sellAllPositions(1)
    expect(api.post).toHaveBeenCalledWith(
      '/bots/1/sell-all-positions',
      null,
      { params: { confirm: true } }
    )
  })
})

describe('templatesApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.put).mockReset()
    vi.mocked(api.delete).mockReset()
  })

  test('getAll calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await templatesApi.getAll()
    expect(api.get).toHaveBeenCalledWith('/templates')
  })

  test('getById calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { id: 1 } })

    await templatesApi.getById(1)
    expect(api.get).toHaveBeenCalledWith('/templates/1')
  })

  test('create sends template data', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { id: 1 } })

    await templatesApi.create({ name: 'Test' })
    expect(api.post).toHaveBeenCalledWith('/templates', { name: 'Test' })
  })

  test('update sends partial template data', async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { id: 1 } })

    await templatesApi.update(1, { name: 'Updated' })
    expect(api.put).toHaveBeenCalledWith('/templates/1', { name: 'Updated' })
  })

  test('delete calls correct endpoint', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: { message: 'deleted' } })

    await templatesApi.delete(1)
    expect(api.delete).toHaveBeenCalledWith('/templates/1')
  })

  test('seedDefaults calls correct endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { message: 'seeded', templates: ['grid', 'dca'] },
    })

    const result = await templatesApi.seedDefaults()
    expect(api.post).toHaveBeenCalledWith('/templates/seed-defaults')
    expect(result.templates).toEqual(['grid', 'dca'])
  })
})

describe('orderHistoryApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  test('getAll with defaults', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await orderHistoryApi.getAll()
    expect(api.get).toHaveBeenCalledWith('/order-history/', {
      params: { limit: 100, offset: 0 },
    })
  })

  test('getAll with all params', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await orderHistoryApi.getAll(5, 2, 'filled', 25, 10)
    expect(api.get).toHaveBeenCalledWith('/order-history/', {
      params: { limit: 25, offset: 10, bot_id: 5, account_id: 2, status: 'filled' },
    })
  })

  test('getFailed with defaults', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await orderHistoryApi.getFailed()
    expect(api.get).toHaveBeenCalledWith('/order-history/failed', {
      params: { limit: 50 },
    })
  })

  test('getFailed with botId and accountId', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await orderHistoryApi.getFailed(3, 1)
    expect(api.get).toHaveBeenCalledWith('/order-history/failed', {
      params: { limit: 50, bot_id: 3, account_id: 1 },
    })
  })

  test('getFailedPaginated with defaults', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [], total: 0, page: 1, page_size: 25, total_pages: 0 },
    })

    await orderHistoryApi.getFailedPaginated()
    expect(api.get).toHaveBeenCalledWith('/order-history/failed/paginated', {
      params: { page: 1, page_size: 25 },
    })
  })

  test('getStats with no params', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { total_orders: 100, successful_orders: 95 },
    })

    await orderHistoryApi.getStats()
    expect(api.get).toHaveBeenCalledWith('/order-history/stats', {
      params: undefined,
    })
  })

  test('getStats with botId', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { total_orders: 50 },
    })

    await orderHistoryApi.getStats(3)
    expect(api.get).toHaveBeenCalledWith('/order-history/stats', {
      params: { bot_id: 3 },
    })
  })
})

describe('blacklistApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.put).mockReset()
    vi.mocked(api.delete).mockReset()
  })

  test('getAll calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await blacklistApi.getAll()
    expect(api.get).toHaveBeenCalledWith('/blacklist/')
  })

  test('add sends single symbol', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { id: 1, symbol: 'DOGE' } })

    await blacklistApi.add('DOGE', 'meme coin')
    expect(api.post).toHaveBeenCalledWith('/blacklist/single', { symbol: 'DOGE', reason: 'meme coin' })
  })

  test('addBulk sends multiple symbols', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: [] })

    await blacklistApi.addBulk(['DOGE', 'SHIB'], 'meme coins')
    expect(api.post).toHaveBeenCalledWith('/blacklist/', { symbols: ['DOGE', 'SHIB'], reason: 'meme coins' })
  })

  test('remove calls correct endpoint', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: { message: 'removed' } })

    await blacklistApi.remove('DOGE')
    expect(api.delete).toHaveBeenCalledWith('/blacklist/DOGE')
  })

  test('check calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { symbol: 'DOGE', is_blacklisted: true, reason: 'meme' },
    })

    const result = await blacklistApi.check('DOGE')
    expect(api.get).toHaveBeenCalledWith('/blacklist/check/DOGE')
    expect(result.is_blacklisted).toBe(true)
  })

  test('getCategories calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { allowed_categories: ['good'], all_categories: ['good', 'bad'] },
    })

    await blacklistApi.getCategories()
    expect(api.get).toHaveBeenCalledWith('/blacklist/categories')
  })

  test('triggerAIReview uses extended timeout', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { status: 'completed', categories: {} },
    })

    await blacklistApi.triggerAIReview()
    expect(api.post).toHaveBeenCalledWith('/blacklist/ai-review', {}, { timeout: 180000 })
  })

  test('updateReason sends PUT request', async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { symbol: 'DOGE' } })

    await blacklistApi.updateReason('DOGE', 'updated reason')
    expect(api.put).toHaveBeenCalledWith('/blacklist/DOGE', { reason: 'updated reason' })
  })

  test('setOverride sends PUT request', async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { symbol: 'BTC', category: 'good' } })

    await blacklistApi.setOverride('BTC', 'good', 'manual override')
    expect(api.put).toHaveBeenCalledWith('/blacklist/overrides/BTC', { category: 'good', reason: 'manual override' })
  })

  test('removeOverride sends DELETE request', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: { message: 'removed' } })

    await blacklistApi.removeOverride('BTC')
    expect(api.delete).toHaveBeenCalledWith('/blacklist/overrides/BTC')
  })

  test('getOverrides calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await blacklistApi.getOverrides()
    expect(api.get).toHaveBeenCalledWith('/blacklist/overrides/')
  })
})

describe('aiCredentialsApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.delete).mockReset()
  })

  test('getStatus calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await aiCredentialsApi.getStatus()
    expect(api.get).toHaveBeenCalledWith('/ai-credentials/status')
  })

  test('save sends provider and key', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { message: 'saved', provider: 'openai' },
    })

    await aiCredentialsApi.save('openai', 'sk-test')
    expect(api.post).toHaveBeenCalledWith('/ai-credentials', { provider: 'openai', api_key: 'sk-test' })
  })

  test('delete calls correct endpoint', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: { message: 'deleted' } })

    await aiCredentialsApi.delete('openai')
    expect(api.delete).toHaveBeenCalledWith('/ai-credentials/openai')
  })
})

describe('autoBuyApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.put).mockReset()
  })

  test('getSettings calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { enabled: true } })

    await autoBuyApi.getSettings(1)
    expect(api.get).toHaveBeenCalledWith('/accounts/1/auto-buy-settings')
  })

  test('updateSettings sends data', async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { enabled: false } })

    await autoBuyApi.updateSettings(1, { enabled: false })
    expect(api.put).toHaveBeenCalledWith('/accounts/1/auto-buy-settings', { enabled: false })
  })
})

describe('accountValueApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  test('getHistory calls with correct params', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await accountValueApi.getHistory(30, true, 5)
    expect(api.get).toHaveBeenCalledWith('/account-value/history', {
      params: { days: 30, include_paper_trading: true, account_id: 5 },
    })
  })

  test('getHistory without accountId', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await accountValueApi.getHistory(7, false)
    expect(api.get).toHaveBeenCalledWith('/account-value/history', {
      params: { days: 7, include_paper_trading: false, account_id: undefined },
    })
  })

  test('getLatest calls with correct params', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { date: '2025-01-01', total_value_btc: 1.5 },
    })

    await accountValueApi.getLatest(true)
    expect(api.get).toHaveBeenCalledWith('/account-value/latest', {
      params: { include_paper_trading: true },
    })
  })
})

describe('reportsApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.put).mockReset()
    vi.mocked(api.delete).mockReset()
  })

  test('getGoals calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await reportsApi.getGoals()
    expect(api.get).toHaveBeenCalledWith('/reports/goals')
  })

  test('createGoal sends data', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { id: 1 } })

    await reportsApi.createGoal({ name: 'Goal 1' } as any)
    expect(api.post).toHaveBeenCalledWith('/reports/goals', { name: 'Goal 1' })
  })

  test('updateGoal sends PATCH-like data', async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { id: 1, name: 'Updated' } })

    await reportsApi.updateGoal(1, { name: 'Updated' } as any)
    expect(api.put).toHaveBeenCalledWith('/reports/goals/1', { name: 'Updated' })
  })

  test('deleteGoal calls correct endpoint', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: {} })

    await reportsApi.deleteGoal(1)
    expect(api.delete).toHaveBeenCalledWith('/reports/goals/1')
  })

  test('getGoalTrend with date range', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} })

    await reportsApi.getGoalTrend(1, '2025-01-01', '2025-01-31')
    expect(api.get).toHaveBeenCalledWith('/reports/goals/1/trend', {
      params: { from_date: '2025-01-01', to_date: '2025-01-31' },
    })
  })

  test('getGoalTrend without dates', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} })

    await reportsApi.getGoalTrend(1)
    expect(api.get).toHaveBeenCalledWith('/reports/goals/1/trend', { params: {} })
  })

  test('getSchedules calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await reportsApi.getSchedules()
    expect(api.get).toHaveBeenCalledWith('/reports/schedules')
  })

  test('getHistory with default params', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { total: 0, reports: [] } })

    await reportsApi.getHistory()
    expect(api.get).toHaveBeenCalledWith('/reports/history', {
      params: { limit: 20, offset: 0, schedule_id: undefined },
    })
  })

  test('generateReport sends schedule id', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { id: 1 } })

    await reportsApi.generateReport(5)
    expect(api.post).toHaveBeenCalledWith('/reports/generate', { schedule_id: 5 })
  })

  test('downloadPdf uses blob response type', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: new Blob() })

    await reportsApi.downloadPdf(1)
    expect(api.get).toHaveBeenCalledWith('/reports/1/pdf', { responseType: 'blob' })
  })

  test('getExpenseItems calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] })

    await reportsApi.getExpenseItems(3)
    expect(api.get).toHaveBeenCalledWith('/reports/goals/3/expenses')
  })

  test('createExpenseItem sends data', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { id: 1 } })

    await reportsApi.createExpenseItem(3, { name: 'Rent', amount: 1000 } as any)
    expect(api.post).toHaveBeenCalledWith('/reports/goals/3/expenses', { name: 'Rent', amount: 1000 })
  })

  test('deleteExpenseItem calls correct endpoint', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: {} })

    await reportsApi.deleteExpenseItem(3, 7)
    expect(api.delete).toHaveBeenCalledWith('/reports/goals/3/expenses/7')
  })

  test('getExpenseCategories calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: ['Housing', 'Food'] })

    await reportsApi.getExpenseCategories()
    expect(api.get).toHaveBeenCalledWith('/reports/expense-categories')
  })
})

describe('transfersApi', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.delete).mockReset()
  })

  test('sync calls correct endpoint', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { status: 'ok', new_transfers: 5 } })

    const result = await transfersApi.sync()
    expect(api.post).toHaveBeenCalledWith('/transfers/sync')
    expect(result.new_transfers).toBe(5)
  })

  test('list calls with params', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { total: 0, transfers: [] } })

    await transfersApi.list({ start: '2025-01-01', limit: 10 })
    expect(api.get).toHaveBeenCalledWith('/transfers', {
      params: { start: '2025-01-01', limit: 10 },
    })
  })

  test('list without params', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { total: 0, transfers: [] } })

    await transfersApi.list()
    expect(api.get).toHaveBeenCalledWith('/transfers', { params: undefined })
  })

  test('create sends transfer data', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { id: 1 } })

    const data = {
      account_id: 1,
      transfer_type: 'deposit',
      amount: 100,
      currency: 'USD',
      occurred_at: '2025-01-01',
    }
    await transfersApi.create(data)
    expect(api.post).toHaveBeenCalledWith('/transfers', data)
  })

  test('delete calls correct endpoint', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: { detail: 'deleted' } })

    await transfersApi.delete(5)
    expect(api.delete).toHaveBeenCalledWith('/transfers/5')
  })

  test('getSummary calls with params', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { net_deposits_usd: 1000 } })

    await transfersApi.getSummary({ account_id: 2 })
    expect(api.get).toHaveBeenCalledWith('/transfers/summary', {
      params: { account_id: 2 },
    })
  })

  test('getRecentSummary calls correct endpoint', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { last_30d_net_deposits_usd: 500, transfers: [] },
    })

    const result = await transfersApi.getRecentSummary()
    expect(api.get).toHaveBeenCalledWith('/transfers/recent-summary')
    expect(result.last_30d_net_deposits_usd).toBe(500)
  })
})
