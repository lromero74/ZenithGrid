/**
 * Tests for useChartManagement hook
 *
 * Verifies chart initialization, chart type switching, time range syncing,
 * resize handling, and cleanup. The lightweight-charts library is fully mocked.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act, render, waitFor } from '@testing-library/react'
import { createElement, type MutableRefObject } from 'react'
import type { IChartApi, Time } from 'lightweight-charts'

// Build a mock chart factory
function createMockSeries() {
  return {
    setData: vi.fn(),
    applyOptions: vi.fn(),
  }
}

function createMockTimeScale() {
  type Callback = (...args: unknown[]) => void
  const callbacks = new Map<string, Callback>()
  return {
    subscribeVisibleTimeRangeChange: vi.fn((cb: Callback) => { callbacks.set('range', cb) }),
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
  createChart: vi.fn((_container: unknown, _options: unknown) => {
    lastCreatedChart = createMockChart()
    return lastCreatedChart
  }),
  ColorType: { Solid: 'Solid' },
}))

// Controllable deferred for the lazy chart-lib loader so tests decide
// exactly when the "dynamic import" resolves.
let libDeferred: { promise: Promise<unknown>; resolve: (v: unknown) => void }
function makeLibDeferred() {
  let resolve!: (v: unknown) => void
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

vi.mock('../../../utils/chartLib', () => ({
  loadChartLib: () => libDeferred.promise,
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
  lastCreatedChart = undefined as unknown as ReturnType<typeof createMockChart>
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useChartManagement initialization', () => {
  test('returns all expected ref objects', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
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
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
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
      current: new Map([['rsi-123', mockIndicatorChart as unknown as IChartApi]]),
    }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
    )

    const timeRange = { from: 1700000000 as Time, to: 1700100000 as Time }

    act(() => {
      result.current.syncAllChartsToRange('main', timeRange)
    })

    expect(mockIndicatorChart.timeScale().setVisibleRange).toHaveBeenCalledWith(timeRange)
  })

  test('does not sync when timeRange is null', () => {
    const mockIndicatorChart = createMockChart()
    const indicatorChartsRef = {
      current: new Map([['rsi-123', mockIndicatorChart as unknown as IChartApi]]),
    }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
    )

    act(() => {
      result.current.syncAllChartsToRange('main', null)
    })

    expect(mockIndicatorChart.timeScale().setVisibleRange).not.toHaveBeenCalled()
  })

  test('does not sync the source chart to itself', () => {
    const mockIndicatorChart = createMockChart()
    const indicatorChartsRef = {
      current: new Map([['rsi-123', mockIndicatorChart as unknown as IChartApi]]),
    }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
    )

    const timeRange = { from: 1700000000 as Time, to: 1700100000 as Time }

    act(() => {
      result.current.syncAllChartsToRange('rsi-123', timeRange)
    })

    // The indicator chart should NOT sync itself
    expect(mockIndicatorChart.timeScale().setVisibleRange).not.toHaveBeenCalled()
  })

  test('syncs main chart when source is an indicator', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
    )

    // Manually assign a mock chart to chartRef to simulate initialization
    const mockMainChart = createMockChart()
    ;(result.current.chartRef as MutableRefObject<IChartApi | null>).current = mockMainChart

    const timeRange = { from: 1700000000 as Time, to: 1700100000 as Time }

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
      current: new Map([['rsi-123', mockIndicatorChart as unknown as IChartApi]]),
    }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
    )

    const timeRange = { from: 1700000000 as Time, to: 1700100000 as Time }

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
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
    )

    // Since container ref is null, chart is not created
    expect(result.current.chartRef.current).toBeNull()
  })

  test('mainSeriesRef starts as null', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
    )

    expect(result.current.mainSeriesRef.current).toBeNull()
  })

  test('volumeSeriesRef starts as null', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
    )

    expect(result.current.volumeSeriesRef.current).toBeNull()
  })

  test('isCleanedUpRef starts as false', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
    )

    expect(result.current.isCleanedUpRef.current).toBe(false)
  })

  test('syncCallbacksRef starts as empty map', () => {
    const indicatorChartsRef = { current: new Map() }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
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
        ['ind-1', mockChart1 as unknown as IChartApi],
        ['ind-2', mockChart2 as unknown as IChartApi],
      ]),
    }

    const { result } = renderHook(() =>
      useChartManagement('candlestick', 'BTC-USD', indicatorChartsRef as unknown as MutableRefObject<Map<string, IChartApi>>)
    )

    const timeRange = { from: 1700000000 as Time, to: 1700100000 as Time }

    act(() => {
      result.current.syncAllChartsToRange('main', timeRange)
    })

    // Both indicator charts should have been synced
    expect(mockChart1.timeScale().setVisibleRange).toHaveBeenCalledTimes(1)
    expect(mockChart2.timeScale().setVisibleRange).toHaveBeenCalledTimes(1)
  })
})

describe('useChartManagement async chart creation (lazy lightweight-charts)', () => {
  beforeEach(() => {
    libDeferred = makeLibDeferred()
    // vi.restoreAllMocks() does not clear module-factory vi.fn()s — call
    // counts accumulate across tests unless cleared here. Also reinstate the
    // implementation so created charts are tracked.
    vi.mocked(createChart).mockClear()
    vi.mocked(createChart).mockImplementation(((_container: unknown, _options: unknown) => {
      lastCreatedChart = createMockChart()
      return lastCreatedChart
    }) as never)
  })

  function resolveLib() {
    libDeferred.resolve({ createChart, ColorType: { Solid: 'Solid' } })
  }

  // Harness that actually attaches the container ref so the mount effect
  // proceeds past the null-container guard.
  function makeHarness() {
    const states: boolean[] = []
    let latest: ReturnType<typeof useChartManagement> | null = null
    function Harness() {
      const api = useChartManagement('candlestick', 'BTC-USD', { current: new Map() } as unknown as MutableRefObject<Map<string, IChartApi>>)
      states.push(api.chartReady)
      latest = api
      return createElement('div', { ref: api.chartContainerRef })
    }
    return { Harness, states, getLatest: () => latest! }
  }

  test('chartReady starts false and flips true after the library loads', async () => {
    const { Harness, states, getLatest } = makeHarness()
    render(createElement(Harness))

    expect(states[0]).toBe(false)
    expect(getLatest().chartReady).toBe(false)

    await act(async () => { resolveLib() })
    await waitFor(() => expect(getLatest().chartReady).toBe(true))
    expect(createChart).toHaveBeenCalled()
  })

  test('creates main + volume series once the chart is ready', async () => {
    const { Harness, getLatest } = makeHarness()
    render(createElement(Harness))

    await act(async () => { resolveLib() })
    await waitFor(() => expect(getLatest().chartReady).toBe(true))
    expect(lastCreatedChart.addCandlestickSeries).toHaveBeenCalledTimes(1)
    expect(lastCreatedChart.addHistogramSeries).toHaveBeenCalledTimes(1)
    expect(getLatest().mainSeriesRef.current).not.toBeNull()
    expect(getLatest().volumeSeriesRef.current).not.toBeNull()
  })

  test('skips chart creation when unmounted before the library resolves', async () => {
    const { Harness } = makeHarness()
    const { unmount } = render(createElement(Harness))
    unmount() // library has not resolved yet

    await act(async () => { resolveLib() })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(createChart).not.toHaveBeenCalled()
  })
})
