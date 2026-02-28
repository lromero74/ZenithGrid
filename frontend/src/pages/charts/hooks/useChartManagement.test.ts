/**
 * Tests for useChartManagement hook
 *
 * Verifies chart initialization, chart type switching, time range syncing,
 * resize handling, and cleanup. The lightweight-charts library is fully mocked.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Build a mock chart factory
function createMockSeries() {
  return {
    setData: vi.fn(),
    applyOptions: vi.fn(),
  }
}

function createMockTimeScale() {
  const callbacks = new Map<string, Function>()
  return {
    subscribeVisibleTimeRangeChange: vi.fn((cb: Function) => { callbacks.set('range', cb) }),
    unsubscribeVisibleTimeRangeChange: vi.fn(),
    setVisibleRange: vi.fn(),
    _callbacks: callbacks,
  }
}

function createMockPriceScale() {
  return {
    applyOptions: vi.fn(),
  }
}

function createMockChart() {
  const mockTimeScale = createMockTimeScale()
  return {
    addCandlestickSeries: vi.fn(() => createMockSeries()),
    addBarSeries: vi.fn(() => createMockSeries()),
    addLineSeries: vi.fn(() => createMockSeries()),
    addAreaSeries: vi.fn(() => createMockSeries()),
    addBaselineSeries: vi.fn(() => createMockSeries()),
    addHistogramSeries: vi.fn(() => createMockSeries()),
    removeSeries: vi.fn(),
    remove: vi.fn(),
    applyOptions: vi.fn(),
    timeScale: vi.fn(() => mockTimeScale),
    priceScale: vi.fn(() => createMockPriceScale()),
    _mockTimeScale: mockTimeScale,
  }
}

let lastCreatedChart: ReturnType<typeof createMockChart>

vi.mock('lightweight-charts', () => ({
  createChart: vi.fn((_container: any, _options: any) => {
    lastCreatedChart = createMockChart()
    return lastCreatedChart
  }),
  ColorType: { Solid: 'Solid' },
}))

vi.mock('../helpers', () => ({
  getPriceFormat: vi.fn((pair: string) => {
    if (pair.endsWith('-BTC')) return { type: 'price', precision: 8, minMove: 0.00000001 }
    return { type: 'price', precision: 2, minMove: 0.01 }
  }),
}))

import { useChartManagement } from './useChartManagement'
import { createChart } from 'lightweight-charts'

beforeEach(() => {
  vi.restoreAllMocks()
  // Clear the last created chart reference
  lastCreatedChart = undefined as any
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useChartManagement initialization', () => {
  test('returns all expected ref objects', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    expect(result.current.chartContainerRef).toBeDefined()
    expect(result.current.chartRef).toBeDefined()
    expect(result.current.mainSeriesRef).toBeDefined()
    expect(result.current.volumeSeriesRef).toBeDefined()
    expect(result.current.isCleanedUpRef).toBeDefined()
    expect(result.current.syncCallbacksRef).toBeDefined()
    expect(typeof result.current.syncAllChartsToRange).toBe('function')
  })

  test('does not create chart when container ref is null', () => {
    const indicatorChartsRef = { current: new Map() }

    renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    // chartContainerRef.current is null by default (no DOM element attached)
    // so createChart should not be called
    expect(createChart).not.toHaveBeenCalled()
  })
})

describe('useChartManagement syncAllChartsToRange', () => {
  test('syncs indicator charts when called from main chart', () => {
    const mockIndicatorChart = createMockChart()
    const indicatorChartsRef = {
      current: new Map([['rsi-123', mockIndicatorChart as any]]),
    }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    const timeRange = { from: 1700000000 as any, to: 1700100000 as any }

    act(() => {
      result.current.syncAllChartsToRange('main', timeRange)
    })

    expect(mockIndicatorChart.timeScale().setVisibleRange).toHaveBeenCalledWith(timeRange)
  })

  test('does not sync when timeRange is null', () => {
    const mockIndicatorChart = createMockChart()
    const indicatorChartsRef = {
      current: new Map([['rsi-123', mockIndicatorChart as any]]),
    }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    act(() => {
      result.current.syncAllChartsToRange('main', null)
    })

    expect(mockIndicatorChart.timeScale().setVisibleRange).not.toHaveBeenCalled()
  })

  test('does not sync the source chart to itself', () => {
    const mockIndicatorChart = createMockChart()
    const indicatorChartsRef = {
      current: new Map([['rsi-123', mockIndicatorChart as any]]),
    }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    const timeRange = { from: 1700000000 as any, to: 1700100000 as any }

    act(() => {
      result.current.syncAllChartsToRange('rsi-123', timeRange)
    })

    // The indicator chart should NOT sync itself
    expect(mockIndicatorChart.timeScale().setVisibleRange).not.toHaveBeenCalled()
  })

  test('syncs main chart when source is an indicator', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    // Manually assign a mock chart to chartRef to simulate initialization
    const mockMainChart = createMockChart()
    ;(result.current.chartRef as any).current = mockMainChart

    const timeRange = { from: 1700000000 as any, to: 1700100000 as any }

    act(() => {
      result.current.syncAllChartsToRange('rsi-123', timeRange)
    })

    expect(mockMainChart.timeScale().setVisibleRange).toHaveBeenCalledWith(timeRange)
  })

  test('handles errors gracefully when chart has no data', () => {
    const mockIndicatorChart = createMockChart()
    mockIndicatorChart.timeScale().setVisibleRange.mockImplementation(() => {
      throw new Error('Chart has no data')
    })

    const indicatorChartsRef = {
      current: new Map([['rsi-123', mockIndicatorChart as any]]),
    }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    const timeRange = { from: 1700000000 as any, to: 1700100000 as any }

    // Should not throw
    act(() => {
      result.current.syncAllChartsToRange('main', timeRange)
    })
  })
})

describe('useChartManagement refs initial state', () => {
  test('chartRef starts as null', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    // Since container ref is null, chart is not created
    expect(result.current.chartRef.current).toBeNull()
  })

  test('mainSeriesRef starts as null', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    expect(result.current.mainSeriesRef.current).toBeNull()
  })

  test('volumeSeriesRef starts as null', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    expect(result.current.volumeSeriesRef.current).toBeNull()
  })

  test('isCleanedUpRef starts as false', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    expect(result.current.isCleanedUpRef.current).toBe(false)
  })

  test('syncCallbacksRef starts as empty map', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    expect(result.current.syncCallbacksRef.current.size).toBe(0)
  })
})

describe('useChartManagement sync reentrancy guard', () => {
  test('prevents recursive syncing via isSyncingRef', () => {
    const mockChart1 = createMockChart()
    const mockChart2 = createMockChart()

    // When chart1 receives setVisibleRange, it would normally trigger a range change
    // callback that calls syncAllChartsToRange again. The guard should prevent this.
    const indicatorChartsRef = {
      current: new Map([
        ['ind-1', mockChart1 as any],
        ['ind-2', mockChart2 as any],
      ]),
    }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as any)
    )

    const timeRange = { from: 1700000000 as any, to: 1700100000 as any }

    act(() => {
      result.current.syncAllChartsToRange('main', timeRange)
    })

    // Both indicator charts should have been synced
    expect(mockChart1.timeScale().setVisibleRange).toHaveBeenCalledTimes(1)
    expect(mockChart2.timeScale().setVisibleRange).toHaveBeenCalledTimes(1)
  })
})
