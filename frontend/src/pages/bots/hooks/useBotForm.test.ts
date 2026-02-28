/**
 * Tests for useBotForm hook.
 *
 * Verifies template loading, strategy change handling, parameter change
 * logic (including max_concurrent_deals / max_simultaneous_same_pair capping),
 * form submission (create + update), and coin category fetching.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useBotForm } from './useBotForm'
import type { BotFormData, ValidationError } from '../../../components/bots'
import type { Bot } from '../../../types'

// ---------- Mocks ----------

const mockAddToast = vi.fn()
vi.mock('../../../contexts/NotificationContext', () => ({
  useNotifications: () => ({ addToast: mockAddToast }),
}))

vi.mock('../../../services/api', () => ({
  blacklistApi: {
    getAll: vi.fn(),
  },
}))

import { blacklistApi } from '../../../services/api'

// ---------- Helpers ----------

function createFormData(overrides: Partial<BotFormData> = {}): BotFormData {
  return {
    name: '',
    description: '',
    market_type: 'spot',
    strategy_type: '',
    product_id: 'ETH-BTC',
    product_ids: [],
    split_budget_across_pairs: false,
    reserved_btc_balance: 0,
    reserved_usd_balance: 0,
    budget_percentage: 0,
    check_interval_seconds: 300,
    strategy_config: {},
    exchange_type: 'cex',
    ...overrides,
  }
}

function createDefaultProps(overrides: Record<string, any> = {}) {
  return {
    showModal: false,
    formData: createFormData(),
    setFormData: vi.fn(),
    editingBot: null as Bot | null,
    templates: [] as any[],
    strategies: [] as any[],
    validationErrors: [] as ValidationError[],
    selectedAccount: { id: 1, name: 'Test Account' },
    createBot: { mutate: vi.fn() },
    updateBot: { mutate: vi.fn() },
    ...overrides,
  }
}

// ---------- Suite ----------

describe('useBotForm', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockAddToast.mockClear()
    vi.mocked(blacklistApi.getAll).mockReset()
    vi.mocked(blacklistApi.getAll).mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ---- Coin category fetching ----

  test('fetches coin categories when modal is shown', async () => {
    vi.mocked(blacklistApi.getAll).mockResolvedValue([
      { id: 1, symbol: 'DOGE', reason: '[MEME] Meme coin', created_at: '2025-01-01', user_override_category: null },
      { id: 2, symbol: 'ETH', reason: '[APPROVED] Top crypto', created_at: '2025-01-01', user_override_category: null },
    ])

    const props = createDefaultProps({ showModal: true })
    const { result } = renderHook(() => useBotForm(props))

    await waitFor(() => {
      expect(result.current.coinCategoryData.coinCategories).toEqual(
        expect.objectContaining({
          DOGE: 'MEME',
          ETH: 'APPROVED',
        }),
      )
    })
  })

  test('does not fetch categories when modal is hidden', () => {
    const props = createDefaultProps({ showModal: false })
    renderHook(() => useBotForm(props))

    expect(blacklistApi.getAll).not.toHaveBeenCalled()
  })

  test('respects user_override_category over parsed category', async () => {
    vi.mocked(blacklistApi.getAll).mockResolvedValue([
      { id: 1, symbol: 'DOGE', reason: '[MEME] Meme coin', created_at: '2025-01-01', user_override_category: 'APPROVED' },
    ])

    const props = createDefaultProps({ showModal: true })
    const { result } = renderHook(() => useBotForm(props))

    await waitFor(() => {
      expect(result.current.coinCategoryData.coinCategories.DOGE).toBe('APPROVED')
      expect(result.current.coinCategoryData.overriddenCoins.has('DOGE')).toBe(true)
    })
  })

  test('categorizes entries without category prefix as BLACKLISTED', async () => {
    vi.mocked(blacklistApi.getAll).mockResolvedValue([
      { id: 1, symbol: 'SCAM', reason: 'Scam token', created_at: '2025-01-01', user_override_category: null },
    ])

    const props = createDefaultProps({ showModal: true })
    const { result } = renderHook(() => useBotForm(props))

    await waitFor(() => {
      expect(result.current.coinCategoryData.coinCategories.SCAM).toBe('BLACKLISTED')
    })
  })

  // ---- loadTemplate ----

  test('loadTemplate populates form with template data', () => {
    const setFormData = vi.fn()
    const template = {
      id: 1,
      name: 'Aggressive DCA',
      description: 'High frequency DCA',
      market_type: 'spot',
      strategy_type: 'dca_bot_v2',
      product_ids: ['ETH-BTC', 'SOL-BTC'],
      split_budget_across_pairs: true,
      reserved_btc_balance: 0.1,
      reserved_usd_balance: 500,
      budget_percentage: 10,
      check_interval_seconds: 120,
      strategy_config: { base_order_percentage: 5 },
      exchange_type: 'cex',
    }

    const props = createDefaultProps({ templates: [template], setFormData })
    const { result } = renderHook(() => useBotForm(props))

    act(() => {
      result.current.loadTemplate(1)
    })

    expect(setFormData).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Aggressive DCA (Copy)',
        strategy_type: 'dca_bot_v2',
        product_ids: ['ETH-BTC', 'SOL-BTC'],
        split_budget_across_pairs: true,
      }),
    )
  })

  test('loadTemplate does nothing for non-existent template', () => {
    const setFormData = vi.fn()
    const props = createDefaultProps({ templates: [], setFormData })
    const { result } = renderHook(() => useBotForm(props))

    act(() => {
      result.current.loadTemplate(999)
    })

    expect(setFormData).not.toHaveBeenCalled()
  })

  // ---- handleStrategyChange ----

  test('handleStrategyChange updates strategy_type and fills default config', () => {
    const setFormData = vi.fn()
    const strategies = [
      {
        id: 'dca_bot_v2',
        name: 'DCA Bot V2',
        description: 'Dollar cost averaging',
        parameters: [
          { name: 'base_order_percentage', default: 5 },
          { name: 'max_concurrent_deals', default: 3 },
        ],
      },
    ]

    const formData = createFormData()
    const props = createDefaultProps({ strategies, setFormData, formData })
    const { result } = renderHook(() => useBotForm(props))

    act(() => {
      result.current.handleStrategyChange('dca_bot_v2')
    })

    expect(setFormData).toHaveBeenCalledWith(
      expect.objectContaining({
        strategy_type: 'dca_bot_v2',
        strategy_config: {
          base_order_percentage: 5,
          max_concurrent_deals: 3,
        },
      }),
    )
  })

  test('handleStrategyChange does nothing for unknown strategy', () => {
    const setFormData = vi.fn()
    const props = createDefaultProps({ strategies: [], setFormData })
    const { result } = renderHook(() => useBotForm(props))

    act(() => {
      result.current.handleStrategyChange('nonexistent')
    })

    expect(setFormData).not.toHaveBeenCalled()
  })

  // ---- handleParamChange ----

  test('handleParamChange updates a simple parameter', () => {
    const setFormData = vi.fn()
    const formData = createFormData({
      strategy_config: { base_order_percentage: 5, max_concurrent_deals: 3 },
    })
    const props = createDefaultProps({ setFormData, formData })
    const { result } = renderHook(() => useBotForm(props))

    act(() => {
      result.current.handleParamChange('base_order_percentage', 10)
    })

    expect(setFormData).toHaveBeenCalledWith(
      expect.objectContaining({
        strategy_config: expect.objectContaining({
          base_order_percentage: 10,
          max_concurrent_deals: 3,
        }),
      }),
    )
  })

  test('handleParamChange caps max_simultaneous_same_pair when max_concurrent_deals decreases', () => {
    const setFormData = vi.fn()
    const formData = createFormData({
      strategy_config: {
        max_concurrent_deals: 5,
        max_simultaneous_same_pair: 4,
      },
    })
    const props = createDefaultProps({ setFormData, formData })
    const { result } = renderHook(() => useBotForm(props))

    act(() => {
      // Decrease max_concurrent_deals to 2, which is below max_simultaneous_same_pair (4)
      result.current.handleParamChange('max_concurrent_deals', 2)
    })

    expect(setFormData).toHaveBeenCalledWith(
      expect.objectContaining({
        strategy_config: expect.objectContaining({
          max_concurrent_deals: 2,
          max_simultaneous_same_pair: 2,
        }),
      }),
    )
  })

  test('handleParamChange caps max_simultaneous_same_pair at max_concurrent_deals', () => {
    const setFormData = vi.fn()
    const formData = createFormData({
      strategy_config: {
        max_concurrent_deals: 3,
        max_simultaneous_same_pair: 1,
      },
    })
    const props = createDefaultProps({ setFormData, formData })
    const { result } = renderHook(() => useBotForm(props))

    act(() => {
      // Try to set max_simultaneous_same_pair to 5, should cap at max_concurrent_deals (3)
      result.current.handleParamChange('max_simultaneous_same_pair', 5)
    })

    expect(setFormData).toHaveBeenCalledWith(
      expect.objectContaining({
        strategy_config: expect.objectContaining({
          max_concurrent_deals: 3,
          max_simultaneous_same_pair: 3,
        }),
      }),
    )
  })

  // ---- handleSubmit ----

  test('handleSubmit calls createBot.mutate for new bot', () => {
    const createBot = { mutate: vi.fn() }
    const formData = createFormData({
      name: 'My Bot',
      product_ids: ['ETH-BTC'],
      strategy_type: 'dca_bot_v2',
      strategy_config: { base_order_percentage: 5 },
    })
    const props = createDefaultProps({ createBot, formData })
    const { result } = renderHook(() => useBotForm(props))

    const mockEvent = { preventDefault: vi.fn() } as unknown as React.FormEvent

    act(() => {
      result.current.handleSubmit(mockEvent)
    })

    expect(mockEvent.preventDefault).toHaveBeenCalled()
    expect(createBot.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'My Bot',
        product_ids: ['ETH-BTC'],
        strategy_type: 'dca_bot_v2',
        account_id: 1,
      }),
    )
  })

  test('handleSubmit calls updateBot.mutate when editing', () => {
    const updateBot = { mutate: vi.fn() }
    const editingBot = { id: 42, account_id: 1 } as Bot
    const formData = createFormData({
      name: 'Updated Bot',
      product_ids: ['SOL-BTC'],
      strategy_type: 'dca_bot_v2',
      strategy_config: { base_order_percentage: 3 },
    })
    const props = createDefaultProps({ updateBot, editingBot, formData })
    const { result } = renderHook(() => useBotForm(props))

    const mockEvent = { preventDefault: vi.fn() } as unknown as React.FormEvent

    act(() => {
      result.current.handleSubmit(mockEvent)
    })

    expect(updateBot.mutate).toHaveBeenCalledWith({
      id: 42,
      data: expect.objectContaining({
        name: 'Updated Bot',
        product_ids: ['SOL-BTC'],
      }),
    })
  })

  test('handleSubmit shows toast and returns when validation errors exist', () => {
    const createBot = { mutate: vi.fn() }
    const validationErrors: ValidationError[] = [
      { field: 'base_order_value', message: 'Too low', calculated_value: 0.00001, minimum_required: 0.0001 },
    ]
    const formData = createFormData({ product_ids: ['ETH-BTC'] })
    const props = createDefaultProps({ createBot, formData, validationErrors })
    const { result } = renderHook(() => useBotForm(props))

    const mockEvent = { preventDefault: vi.fn() } as unknown as React.FormEvent

    act(() => {
      result.current.handleSubmit(mockEvent)
    })

    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', title: 'Validation Error' }),
    )
    expect(createBot.mutate).not.toHaveBeenCalled()
  })

  test('handleSubmit shows toast when no account selected and not editing', () => {
    const createBot = { mutate: vi.fn() }
    const formData = createFormData({ product_ids: ['ETH-BTC'] })
    const props = createDefaultProps({ createBot, formData, selectedAccount: null })
    const { result } = renderHook(() => useBotForm(props))

    const mockEvent = { preventDefault: vi.fn() } as unknown as React.FormEvent

    act(() => {
      result.current.handleSubmit(mockEvent)
    })

    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', title: 'No Account' }),
    )
    expect(createBot.mutate).not.toHaveBeenCalled()
  })

  test('handleSubmit shows toast when no trading pairs selected', () => {
    const createBot = { mutate: vi.fn() }
    const formData = createFormData({ product_ids: [] })
    const props = createDefaultProps({ createBot, formData })
    const { result } = renderHook(() => useBotForm(props))

    const mockEvent = { preventDefault: vi.fn() } as unknown as React.FormEvent

    act(() => {
      result.current.handleSubmit(mockEvent)
    })

    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', title: 'No Pair Selected' }),
    )
    expect(createBot.mutate).not.toHaveBeenCalled()
  })
})
