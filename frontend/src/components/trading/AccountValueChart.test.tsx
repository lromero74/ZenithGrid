/**
 * AccountValueChart — chart lifecycle guard.
 *
 * Protects the v3.12.x refactor: the chart must be created ONCE when data first
 * loads and then have its data updated in place. It must NOT be torn down and
 * recreated on every live-value tick / 5-minute refetch (the old behavior, which
 * also reset the user's zoom each time).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const mocks = vi.hoisted(() => {
  const mkSeries = () => ({ setData: vi.fn(), setMarkers: vi.fn(), applyOptions: vi.fn() })
  const btc = mkSeries()
  const usd = mkSeries()
  let seriesIdx = 0
  const chart = {
    addLineSeries: vi.fn(() => (seriesIdx++ === 0 ? btc : usd)),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    applyOptions: vi.fn(),
    remove: vi.fn(),
  }
  const createChart = vi.fn(() => { seriesIdx = 0; return chart })
  return { createChart, chart, btc, usd }
})

vi.mock('lightweight-charts', () => ({
  createChart: mocks.createChart,
  ColorType: { Solid: 'Solid' },
}))

vi.mock('../../contexts/AccountContext', () => ({
  useAccount: () => ({ selectedAccount: { id: 1, is_paper_trading: false } }),
}))

vi.mock('../../services/api', () => ({
  accountValueApi: {
    getHistory: vi.fn(async () => ([
      { date: '2026-06-01', timestamp: '', total_value_btc: 1, total_value_usd: 100 },
      { date: '2026-06-02', timestamp: '', total_value_btc: 1.1, total_value_usd: 110 },
    ])),
    getActivity: vi.fn(async () => ([])),
  },
}))

import { AccountValueChart } from './AccountValueChart'

function renderChart(props: { liveBtcValue?: number | null; liveUsdValue?: number | null }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = (p: typeof props) => (
    <QueryClientProvider client={qc}>
      <AccountValueChart {...p} />
    </QueryClientProvider>
  )
  const utils = render(ui(props))
  return { ...utils, rerenderWith: (p: typeof props) => utils.rerender(ui(p)) }
}

describe('AccountValueChart chart lifecycle', () => {
  beforeEach(() => {
    mocks.createChart.mockClear()
    mocks.btc.setData.mockClear()
    mocks.usd.setData.mockClear()
  })

  it('creates the chart once after data loads and sets series data', async () => {
    renderChart({ liveBtcValue: 1.2, liveUsdValue: 120 })
    await waitFor(() => expect(mocks.createChart).toHaveBeenCalledTimes(1))
    expect(mocks.btc.setData).toHaveBeenCalled()
    expect(mocks.usd.setData).toHaveBeenCalled()
  })

  it('updates data in place when live values change — does NOT recreate the chart', async () => {
    const { rerenderWith } = renderChart({ liveBtcValue: 1.2, liveUsdValue: 120 })
    await waitFor(() => expect(mocks.createChart).toHaveBeenCalledTimes(1))

    mocks.btc.setData.mockClear()
    rerenderWith({ liveBtcValue: 1.3, liveUsdValue: 130 })

    // Data is pushed again...
    await waitFor(() => expect(mocks.btc.setData).toHaveBeenCalled())
    // ...but the chart was never recreated.
    expect(mocks.createChart).toHaveBeenCalledTimes(1)
  })
})
