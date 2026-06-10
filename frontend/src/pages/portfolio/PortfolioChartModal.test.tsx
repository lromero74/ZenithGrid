/**
 * Tests for PortfolioChartModal — the candlestick chart modal extracted from
 * Portfolio.tsx so lightweight-charts can be lazy-loaded behind it.
 *
 * The lightweight-charts library and the API client are fully mocked.
 */

import { describe, test, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'

function createMockSeries() {
  return { setData: vi.fn(), applyOptions: vi.fn() }
}

function createMockChart() {
  return {
    addCandlestickSeries: vi.fn(() => createMockSeries()),
    addHistogramSeries: vi.fn(() => createMockSeries()),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    applyOptions: vi.fn(),
    remove: vi.fn(),
  }
}

let lastCreatedChart: ReturnType<typeof createMockChart>

vi.mock('lightweight-charts', () => ({
  createChart: vi.fn(() => {
    lastCreatedChart = createMockChart()
    return lastCreatedChart
  }),
  ColorType: { Solid: 'Solid' },
}))

const mockGet = vi.fn()
vi.mock('../../services/api', () => ({
  api: { get: (...args: unknown[]) => mockGet(...args) },
}))

import { createChart } from 'lightweight-charts'
import PortfolioChartModal from './PortfolioChartModal'

const CANDLES = [
  { time: 1700000000, open: 100, high: 110, low: 95, close: 105, volume: 12 },
  { time: 1700000900, open: 105, high: 115, low: 100, close: 95, volume: 8 },
]

beforeEach(() => {
  vi.clearAllMocks()
  mockGet.mockResolvedValue({ data: { candles: CANDLES } })
})

describe('PortfolioChartModal', () => {
  test('renders the asset chart title and pair/timeframe controls', async () => {
    render(<PortfolioChartModal asset="ETH" onClose={() => {}} />)

    expect(screen.getByText('ETH Chart')).toBeTruthy()
    expect(screen.getByText('ETH/USD')).toBeTruthy()
    expect(screen.getByText('ETH/BTC')).toBeTruthy()
    expect(screen.getByText('15m')).toBeTruthy()
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
  })

  test('creates a chart and fetches USD 15m candles on mount', async () => {
    render(<PortfolioChartModal asset="ETH" onClose={() => {}} />)

    await waitFor(() => expect(createChart).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/candles', {
      params: { product_id: 'ETH-USD', granularity: 'FIFTEEN_MINUTE', limit: 200 },
    }))
  })

  test('switching to BTC pair refetches candles for the BTC product', async () => {
    render(<PortfolioChartModal asset="ETH" onClose={() => {}} />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())

    fireEvent.click(screen.getByText('ETH/BTC'))

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/candles', {
      params: { product_id: 'ETH-BTC', granularity: 'FIFTEEN_MINUTE', limit: 200 },
    }))
  })

  test('shows an error message when no candle data is available', async () => {
    mockGet.mockResolvedValue({ data: { candles: [] } })
    render(<PortfolioChartModal asset="OBSCURE" onClose={() => {}} />)

    await waitFor(() => expect(screen.getByText(/No data available for OBSCURE-USD/)).toBeTruthy())
  })

  test('close button and Escape key call onClose', async () => {
    const onClose = vi.fn()
    render(<PortfolioChartModal asset="ETH" onClose={onClose} />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())

    fireEvent.click(screen.getByLabelText('Close chart'))
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
