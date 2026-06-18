import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, test, vi } from 'vitest'

vi.mock('../../services/api', () => ({
  authFetch: vi.fn(),
}))

const setData = vi.fn()
const remove = vi.fn()
const fitContent = vi.fn()

vi.mock('lightweight-charts', () => ({
  ColorType: { Solid: 'Solid' },
  createChart: vi.fn(() => ({
    addLineSeries: vi.fn(() => ({ setData })),
    applyOptions: vi.fn(),
    remove,
    timeScale: vi.fn(() => ({ fitContent })),
  })),
}))

import { authFetch } from '../../services/api'
import { PnLChart } from './PnLChart'

function renderChart() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <PnLChart accountId={1} />
    </QueryClientProvider>,
  )
}

describe('PnLChart layout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        summary: [{
          timestamp: '2026-06-18T05:35:55',
          date: '2026-06-18',
          cumulative_pnl_usd: 0.05,
          cumulative_pnl_btc: 0.0000008,
          profit_usd: 0.05,
          profit_btc: 0.0000008,
          product_id: 'FORTH-USD',
          bot_id: 41,
          bot_name: 'RSI OVERSOLD (USD)',
        }],
        by_day: [{
          date: '2026-06-18',
          daily_pnl_usd: 0.05,
          daily_pnl_btc: 0.0000008,
          cumulative_pnl_usd: 0.05,
          cumulative_pnl_btc: 0.0000008,
        }],
        by_pair: [{
          pair: 'FORTH-USD',
          total_pnl_usd: 0.05,
          total_pnl_btc: 0.0000008,
        }],
        active_trades: 0,
        most_profitable_bot: null,
      }),
    } as Response)
  })

  test('keeps the chart region at a non-collapsible fixed height', async () => {
    renderChart()

    await screen.findByRole('button', { name: 'Summary PnL' })
    const region = screen.getByTestId('pnl-chart-region')

    expect(region).toHaveClass('h-[300px]', 'min-h-[300px]', 'flex-none')
    expect(region).not.toHaveClass('flex-1')
    await waitFor(() => expect(setData).toHaveBeenCalled())
  })
})
