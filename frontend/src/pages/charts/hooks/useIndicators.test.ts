/**
 * Tests for useIndicators hook
 *
 * Verifies indicator state management: add/remove/toggle/update indicators,
 * localStorage persistence, default config, modal state, and search filtering.
 * The heavy charting/rendering logic is mocked since it depends on DOM/canvas.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useIndicators } from './useIndicators'

// Mock lightweight-charts
vi.mock('lightweight-charts', () => ({
  createChart: vi.fn(),
  ColorType: { Solid: 'Solid' },
}))

// Mock helpers
vi.mock('../helpers', () => ({
  getPriceFormat: vi.fn(() => ({ type: 'price', precision: 2, minMove: 0.01 })),
}))

// Mock indicators utilities -- provide real AVAILABLE_INDICATORS for testing
vi.mock('../../../utils/indicators', () => ({
  calculateSMA: vi.fn(() => []),
  calculateEMA: vi.fn(() => []),
  calculateRSI: vi.fn(() => []),
  calculateMACD: vi.fn(() => ({ macd: [], signal: [], histogram: [] })),
  calculateBollingerBands: vi.fn(() => ({ upper: [], middle: [], lower: [] })),
  calculateStochastic: vi.fn(() => ({ k: [], d: [] })),
  AVAILABLE_INDICATORS: [
    {
      id: 'sma',
      name: 'Simple Moving Average (SMA)',
      category: 'Moving Averages',
      defaultSettings: { period: 20, color: '#FF9800' },
    },
    {
      id: 'ema',
      name: 'Exponential Moving Average (EMA)',
      category: 'Moving Averages',
      defaultSettings: { period: 12, color: '#9C27B0' },
    },
    {
      id: 'rsi',
      name: 'Relative Strength Index (RSI)',
      category: 'Oscillators',
      defaultSettings: { period: 14, overbought: 70, oversold: 30, color: '#2196F3' },
    },
    {
      id: 'macd',
      name: 'MACD',
      category: 'Oscillators',
      defaultSettings: { fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 },
    },
    {
      id: 'bollinger',
      name: 'Bollinger Bands',
      category: 'Volatility',
      defaultSettings: { period: 20, stdDev: 2 },
    },
  ],
}))

// Mock charts/IndicatorSettingsModal type
vi.mock('../../../components/charts', () => ({}))

function createDefaultProps() {
  return {
    chartRef: { current: null } as any,
    selectedPair: 'BTC-USD',
    indicatorChartsRef: { current: new Map() } as any,
    syncAllChartsToRange: vi.fn(),
    syncCallbacksRef: { current: new Map() } as any,
  }
}

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useIndicators initial state', () => {
  test('starts with empty indicators when localStorage is empty', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    expect(result.current.indicators).toEqual([])
  })

  test('starts with showIndicatorModal false', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    expect(result.current.showIndicatorModal).toBe(false)
  })

  test('starts with empty indicatorSearch', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    expect(result.current.indicatorSearch).toBe('')
  })

  test('starts with editingIndicator as null', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    expect(result.current.editingIndicator).toBeNull()
  })
})

describe('useIndicators localStorage persistence', () => {
  test('restores indicators from localStorage', () => {
    const savedIndicators = [
      { id: 'sma-123', name: 'SMA', type: 'sma', enabled: true, settings: { period: 20 }, series: [] },
    ]
    localStorage.setItem('chart-indicators', JSON.stringify(savedIndicators))

    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    expect(result.current.indicators).toHaveLength(1)
    expect(result.current.indicators[0].type).toBe('sma')
  })

  test('saves indicators to localStorage when changed', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => { result.current.addIndicator('sma') })

    const saved = JSON.parse(localStorage.getItem('chart-indicators') || '[]')
    expect(saved).toHaveLength(1)
    expect(saved[0].type).toBe('sma')
  })

  test('handles corrupt localStorage data gracefully', () => {
    localStorage.setItem('chart-indicators', 'not-valid-json')
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    expect(result.current.indicators).toEqual([])
    consoleSpy.mockRestore()
  })
})

describe('useIndicators addIndicator', () => {
  test('adds an SMA indicator with default settings', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => { result.current.addIndicator('sma') })

    expect(result.current.indicators).toHaveLength(1)
    const added = result.current.indicators[0]
    expect(added.type).toBe('sma')
    expect(added.name).toBe('Simple Moving Average (SMA)')
    expect(added.enabled).toBe(true)
    expect(added.settings.period).toBe(20)
    expect(added.settings.color).toBe('#FF9800')
    expect(added.id).toMatch(/^sma-/)
  })

  test('adds multiple indicators', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => { result.current.addIndicator('sma') })
    act(() => { result.current.addIndicator('ema') })

    expect(result.current.indicators).toHaveLength(2)
    expect(result.current.indicators[0].type).toBe('sma')
    expect(result.current.indicators[1].type).toBe('ema')
  })

  test('does nothing for unknown indicator type', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => { result.current.addIndicator('nonexistent') })

    expect(result.current.indicators).toHaveLength(0)
  })

  test('closes indicator modal after adding', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => { result.current.setShowIndicatorModal(true) })
    expect(result.current.showIndicatorModal).toBe(true)

    act(() => { result.current.addIndicator('sma') })
    expect(result.current.showIndicatorModal).toBe(false)
  })

  test('each added indicator gets a unique id', () => {
    // Use fake timers so Date.now() can be controlled
    vi.useFakeTimers()

    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => {
      vi.setSystemTime(new Date(1000))
      result.current.addIndicator('sma')
    })
    act(() => {
      vi.setSystemTime(new Date(2000))
      result.current.addIndicator('sma')
    })

    expect(result.current.indicators[0].id).not.toBe(result.current.indicators[1].id)

    vi.useRealTimers()
  })
})

describe('useIndicators removeIndicator', () => {
  test('removes an indicator by id', () => {
    const savedIndicators = [
      { id: 'sma-100', name: 'SMA', type: 'sma', enabled: true, settings: { period: 20 }, series: [] },
      { id: 'ema-200', name: 'EMA', type: 'ema', enabled: true, settings: { period: 12 }, series: [] },
    ]
    localStorage.setItem('chart-indicators', JSON.stringify(savedIndicators))

    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    expect(result.current.indicators).toHaveLength(2)

    act(() => { result.current.removeIndicator('sma-100') })

    expect(result.current.indicators).toHaveLength(1)
    expect(result.current.indicators[0].id).toBe('ema-200')
  })

  test('does nothing when removing non-existent id', () => {
    const savedIndicators = [
      { id: 'sma-100', name: 'SMA', type: 'sma', enabled: true, settings: {}, series: [] },
    ]
    localStorage.setItem('chart-indicators', JSON.stringify(savedIndicators))

    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => { result.current.removeIndicator('nonexistent') })

    expect(result.current.indicators).toHaveLength(1)
  })

  test('removes indicator chart from indicatorChartsRef for oscillators', () => {
    const mockChart = {
      remove: vi.fn(),
      timeScale: vi.fn(() => ({
        unsubscribeVisibleTimeRangeChange: vi.fn(),
      })),
    }
    const indicatorChartsRef = { current: new Map([['rsi-100', mockChart as any]]) }

    const savedIndicators = [
      { id: 'rsi-100', name: 'RSI', type: 'rsi', enabled: true, settings: { period: 14 }, series: [] },
    ]
    localStorage.setItem('chart-indicators', JSON.stringify(savedIndicators))

    const props = { ...createDefaultProps(), indicatorChartsRef: indicatorChartsRef as any }
    const { result } = renderHook(() => useIndicators(props))

    act(() => { result.current.removeIndicator('rsi-100') })

    expect(mockChart.remove).toHaveBeenCalled()
    expect(indicatorChartsRef.current.has('rsi-100')).toBe(false)
  })
})

describe('useIndicators updateIndicatorSettings', () => {
  test('updates settings for a specific indicator', () => {
    const savedIndicators = [
      { id: 'sma-100', name: 'SMA', type: 'sma', enabled: true, settings: { period: 20, color: '#FF9800' }, series: [] },
    ]
    localStorage.setItem('chart-indicators', JSON.stringify(savedIndicators))

    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => {
      result.current.updateIndicatorSettings('sma-100', { period: 50, color: '#00FF00' })
    })

    expect(result.current.indicators[0].settings.period).toBe(50)
    expect(result.current.indicators[0].settings.color).toBe('#00FF00')
  })

  test('merges new settings with existing settings', () => {
    const savedIndicators = [
      { id: 'sma-100', name: 'SMA', type: 'sma', enabled: true, settings: { period: 20, color: '#FF9800' }, series: [] },
    ]
    localStorage.setItem('chart-indicators', JSON.stringify(savedIndicators))

    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => {
      result.current.updateIndicatorSettings('sma-100', { period: 50 })
    })

    expect(result.current.indicators[0].settings.period).toBe(50)
    expect(result.current.indicators[0].settings.color).toBe('#FF9800') // unchanged
  })

  test('clears editingIndicator after update', () => {
    const savedIndicators = [
      { id: 'sma-100', name: 'SMA', type: 'sma', enabled: true, settings: { period: 20 }, series: [] },
    ]
    localStorage.setItem('chart-indicators', JSON.stringify(savedIndicators))

    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => {
      result.current.setEditingIndicator(result.current.indicators[0])
    })
    expect(result.current.editingIndicator).not.toBeNull()

    act(() => {
      result.current.updateIndicatorSettings('sma-100', { period: 50 })
    })
    expect(result.current.editingIndicator).toBeNull()
  })

  test('does not modify other indicators', () => {
    const savedIndicators = [
      { id: 'sma-100', name: 'SMA', type: 'sma', enabled: true, settings: { period: 20 }, series: [] },
      { id: 'ema-200', name: 'EMA', type: 'ema', enabled: true, settings: { period: 12 }, series: [] },
    ]
    localStorage.setItem('chart-indicators', JSON.stringify(savedIndicators))

    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => {
      result.current.updateIndicatorSettings('sma-100', { period: 50 })
    })

    expect(result.current.indicators[1].settings.period).toBe(12)
  })
})

describe('useIndicators modal and search state', () => {
  test('toggles showIndicatorModal', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => { result.current.setShowIndicatorModal(true) })
    expect(result.current.showIndicatorModal).toBe(true)

    act(() => { result.current.setShowIndicatorModal(false) })
    expect(result.current.showIndicatorModal).toBe(false)
  })

  test('updates indicatorSearch', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    act(() => { result.current.setIndicatorSearch('RSI') })
    expect(result.current.indicatorSearch).toBe('RSI')
  })

  test('sets and clears editingIndicator', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    const mockIndicator = { id: 'sma-1', name: 'SMA', type: 'sma', enabled: true, settings: {}, series: [] as any[] }

    act(() => { result.current.setEditingIndicator(mockIndicator) })
    expect(result.current.editingIndicator).toEqual(mockIndicator)

    act(() => { result.current.setEditingIndicator(null) })
    expect(result.current.editingIndicator).toBeNull()
  })
})

describe('useIndicators renderIndicators', () => {
  test('renderIndicators is a function', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    expect(typeof result.current.renderIndicators).toBe('function')
  })

  test('renderIndicators does not throw with empty candles', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    expect(() => {
      result.current.renderIndicators([])
    }).not.toThrow()
  })

  test('renderIndicators does not throw when chartRef is null', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    // chartRef.current is null by default
    expect(() => {
      result.current.renderIndicators([
        { time: 1700000000 as any, open: 100, high: 110, low: 90, close: 105, volume: 1000 },
      ])
    }).not.toThrow()
  })
})

describe('useIndicators return shape', () => {
  test('returns all expected properties', () => {
    const { result } = renderHook(() => useIndicators(createDefaultProps()))

    expect(result.current).toHaveProperty('indicators')
    expect(result.current).toHaveProperty('showIndicatorModal')
    expect(result.current).toHaveProperty('setShowIndicatorModal')
    expect(result.current).toHaveProperty('indicatorSearch')
    expect(result.current).toHaveProperty('setIndicatorSearch')
    expect(result.current).toHaveProperty('editingIndicator')
    expect(result.current).toHaveProperty('setEditingIndicator')
    expect(result.current).toHaveProperty('addIndicator')
    expect(result.current).toHaveProperty('removeIndicator')
    expect(result.current).toHaveProperty('updateIndicatorSettings')
    expect(result.current).toHaveProperty('renderIndicators')
  })
})
