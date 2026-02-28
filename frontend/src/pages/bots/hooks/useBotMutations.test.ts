/**
 * Tests for useBotMutations hook.
 *
 * Verifies create, update, delete, start, stop, clone, copyToAccount,
 * forceRun, cancelAllPositions, and sellAllPositions mutations including
 * optimistic updates and error handling.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useBotMutations } from './useBotMutations'
import type { Bot } from '../../../types'

// ---------- Mocks ----------

const mockAddToast = vi.fn()
vi.mock('../../../contexts/NotificationContext', () => ({
  useNotifications: () => ({ addToast: mockAddToast }),
}))

vi.mock('../../../services/api', () => ({
  botsApi: {
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    clone: vi.fn(),
    copyToAccount: vi.fn(),
    forceRun: vi.fn(),
    cancelAllPositions: vi.fn(),
    sellAllPositions: vi.fn(),
  },
}))

import { botsApi } from '../../../services/api'

// ---------- Helpers ----------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

function createDefaultProps(overrides: Record<string, any> = {}) {
  return {
    selectedAccount: { id: 1 },
    bots: [
      { id: 1, name: 'Bot Alpha', is_active: true } as Bot,
      { id: 2, name: 'Bot Beta', is_active: false } as Bot,
    ],
    setShowModal: vi.fn(),
    resetForm: vi.fn(),
    onCloneSuccess: vi.fn(),
    projectionTimeframe: '30d' as const,
    ...overrides,
  }
}

// ---------- Suite ----------

describe('useBotMutations', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockAddToast.mockClear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ---- createBot ----

  test('createBot calls botsApi.create and resets form on success', async () => {
    const botData = { name: 'New Bot', strategy_type: 'dca_bot_v2', strategy_config: {}, product_id: 'ETH-BTC' }
    vi.mocked(botsApi.create).mockResolvedValue({ id: 3, ...botData } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.createBot.mutate(botData as any)
    })

    await waitFor(() => {
      expect(result.current.createBot.isSuccess).toBe(true)
    })

    expect(botsApi.create).toHaveBeenCalledWith(botData)
    expect(props.setShowModal).toHaveBeenCalledWith(false)
    expect(props.resetForm).toHaveBeenCalled()
  })

  test('createBot shows error toast with string detail on failure', async () => {
    const error = Object.assign(new Error('Server Error'), {
      response: { data: { detail: 'Bot name already exists' } },
    })
    vi.mocked(botsApi.create).mockRejectedValue(error)
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.createBot.mutate({ name: 'Dup' } as any)
    })

    await waitFor(() => {
      expect(result.current.createBot.isError).toBe(true)
    })

    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'error',
        title: 'Create Bot Failed',
        message: 'Bot name already exists',
      }),
    )
  })

  test('createBot shows error toast with array detail on validation failure', async () => {
    const error = Object.assign(new Error('Validation'), {
      response: {
        data: {
          detail: [
            { msg: 'field required', loc: ['body', 'name'] },
          ],
        },
      },
    })
    vi.mocked(botsApi.create).mockRejectedValue(error)
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.createBot.mutate({} as any)
    })

    await waitFor(() => {
      expect(result.current.createBot.isError).toBe(true)
    })

    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'body.name: field required',
      }),
    )
  })

  // ---- updateBot ----

  test('updateBot calls botsApi.update and resets form on success', async () => {
    vi.mocked(botsApi.update).mockResolvedValue({ id: 1, name: 'Updated' } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.updateBot.mutate({ id: 1, data: { name: 'Updated' } })
    })

    await waitFor(() => {
      expect(result.current.updateBot.isSuccess).toBe(true)
    })

    expect(botsApi.update).toHaveBeenCalledWith(1, { name: 'Updated' })
    expect(props.setShowModal).toHaveBeenCalledWith(false)
    expect(props.resetForm).toHaveBeenCalled()
  })

  // ---- deleteBot ----

  test('deleteBot calls botsApi.delete', async () => {
    vi.mocked(botsApi.delete).mockResolvedValue({ message: 'Deleted' } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.deleteBot.mutate(1)
    })

    await waitFor(() => {
      expect(result.current.deleteBot.isSuccess).toBe(true)
    })

    expect(botsApi.delete).toHaveBeenCalledWith(1)
  })

  // ---- startBot ----

  test('startBot calls botsApi.start', async () => {
    vi.mocked(botsApi.start).mockResolvedValue({ message: 'Started' } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.startBot.mutate(1)
    })

    await waitFor(() => {
      expect(result.current.startBot.isSuccess).toBe(true)
    })

    expect(botsApi.start).toHaveBeenCalledWith(1)
  })

  // ---- stopBot ----

  test('stopBot calls botsApi.stop', async () => {
    vi.mocked(botsApi.stop).mockResolvedValue({ message: 'Stopped' } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.stopBot.mutate(2)
    })

    await waitFor(() => {
      expect(result.current.stopBot.isSuccess).toBe(true)
    })

    expect(botsApi.stop).toHaveBeenCalledWith(2)
  })

  // ---- cloneBot ----

  test('cloneBot calls botsApi.clone and triggers onCloneSuccess callback', async () => {
    const clonedBot = { id: 10, name: 'Bot Alpha (Clone)' } as Bot
    vi.mocked(botsApi.clone).mockResolvedValue(clonedBot as any)

    const onCloneSuccess = vi.fn()
    const props = createDefaultProps({ onCloneSuccess })
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.cloneBot.mutate(1)
    })

    await waitFor(() => {
      expect(result.current.cloneBot.isSuccess).toBe(true)
    })

    expect(botsApi.clone).toHaveBeenCalledWith(1)
    expect(onCloneSuccess).toHaveBeenCalledWith(clonedBot)
  })

  // ---- copyToAccount ----

  test('copyToAccount calls botsApi.copyToAccount', async () => {
    vi.mocked(botsApi.copyToAccount).mockResolvedValue({ id: 11 } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.copyToAccount.mutate({ id: 1, targetAccountId: 2 })
    })

    await waitFor(() => {
      expect(result.current.copyToAccount.isSuccess).toBe(true)
    })

    expect(botsApi.copyToAccount).toHaveBeenCalledWith(1, 2)
  })

  // ---- forceRunBot ----

  test('forceRunBot calls botsApi.forceRun', async () => {
    vi.mocked(botsApi.forceRun).mockResolvedValue({ message: 'Running', note: '' } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.forceRunBot.mutate(1)
    })

    await waitFor(() => {
      expect(result.current.forceRunBot.isSuccess).toBe(true)
    })

    expect(botsApi.forceRun).toHaveBeenCalledWith(1)
  })

  // ---- cancelAllPositions ----

  test('cancelAllPositions shows success toast on full cancellation', async () => {
    vi.mocked(botsApi.cancelAllPositions).mockResolvedValue({
      cancelled_count: 5,
      failed_count: 0,
      errors: [],
    } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.cancelAllPositions.mutate(1)
    })

    await waitFor(() => {
      expect(result.current.cancelAllPositions.isSuccess).toBe(true)
    })

    expect(botsApi.cancelAllPositions).toHaveBeenCalledWith(1, true)
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'success',
        title: 'Positions Cancelled',
        message: expect.stringContaining('5'),
      }),
    )
  })

  test('cancelAllPositions shows error toast on partial cancellation', async () => {
    vi.mocked(botsApi.cancelAllPositions).mockResolvedValue({
      cancelled_count: 3,
      failed_count: 2,
      errors: ['Order not found'],
    } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.cancelAllPositions.mutate(1)
    })

    await waitFor(() => {
      expect(result.current.cancelAllPositions.isSuccess).toBe(true)
    })

    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'error',
        title: 'Partial Cancellation',
      }),
    )
  })

  // ---- sellAllPositions ----

  test('sellAllPositions shows success toast on full sale', async () => {
    vi.mocked(botsApi.sellAllPositions).mockResolvedValue({
      sold_count: 4,
      failed_count: 0,
      total_profit_quote: 0.00123456,
      errors: [],
    } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.sellAllPositions.mutate(1)
    })

    await waitFor(() => {
      expect(result.current.sellAllPositions.isSuccess).toBe(true)
    })

    expect(botsApi.sellAllPositions).toHaveBeenCalledWith(1, true)
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'success',
        title: 'All Positions Sold',
      }),
    )
  })

  test('sellAllPositions shows error toast on partial sale', async () => {
    vi.mocked(botsApi.sellAllPositions).mockResolvedValue({
      sold_count: 2,
      failed_count: 1,
      total_profit_quote: 0.001,
      errors: ['Insufficient liquidity'],
    } as any)

    const props = createDefaultProps()
    const { result } = renderHook(() => useBotMutations(props), { wrapper: createWrapper() })

    await act(async () => {
      result.current.sellAllPositions.mutate(2)
    })

    await waitFor(() => {
      expect(result.current.sellAllPositions.isSuccess).toBe(true)
    })

    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'error',
        title: 'Partial Sell',
      }),
    )
  })
})
