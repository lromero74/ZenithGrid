/**
 * PortfolioManagement — cache writeback regression test
 *
 * Guards against the bug where toggling rebalance/auto-buy mode did not write
 * through to the sessionStorage cache, causing the UI to revert to the old
 * enabled state after a page refresh within the 5-minute cache window.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import React from 'react'

// ─── Mock heavy dependencies ─────────────────────────────────────────────────

vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => true,
}))

vi.mock('recharts', () => ({
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: () => null,
  Cell: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

// API mocks — factories must NOT reference hoisted module-level variables.
// All values are literals; per-test behavior is set via mockImplementation.
const mockGetAutoBuySettings = vi.fn()
const mockUpdateAutoBuySettings = vi.fn()
const mockGetRebalanceSettings = vi.fn()
const mockUpdateRebalanceSettings = vi.fn()
const mockGetRebalanceStatus = vi.fn()
const mockGetDustSettings = vi.fn()
const mockBotsApiGetAll = vi.fn()

vi.mock('../../services/api', () => ({
  autoBuyApi: {
    getSettings: (...args: unknown[]) => mockGetAutoBuySettings(...args),
    updateSettings: (...args: unknown[]) => mockUpdateAutoBuySettings(...args),
  },
  rebalanceApi: {
    getSettings: (...args: unknown[]) => mockGetRebalanceSettings(...args),
    updateSettings: (...args: unknown[]) => mockUpdateRebalanceSettings(...args),
    getStatus: (...args: unknown[]) => mockGetRebalanceStatus(...args),
  },
  dustApi: {
    getSettings: (...args: unknown[]) => mockGetDustSettings(...args),
    updateSettings: vi.fn().mockResolvedValue({
      enabled: false,
      threshold_usd: 5,
      last_sweep_at: null,
      dust_positions: [],
    }),
  },
  botsApi: {
    getBots: (...args: unknown[]) => mockBotsApiGetAll(...args),
    getAll: (...args: unknown[]) => mockBotsApiGetAll(...args),
  },
}))

// ─── Import component (after mocks) ──────────────────────────────────────────

import { PortfolioManagement } from './PortfolioManagement'

// ─── Test helpers ─────────────────────────────────────────────────────────────

const CACHE_KEY = 'portfolioMgmtCache'
const ACCOUNT_ID = 1

const makeRebalanceSettings = (enabled: boolean) => ({
  enabled,
  target_usd_pct: 34,
  target_btc_pct: 33,
  target_eth_pct: 33,
  target_usdc_pct: 0,
  target_usdt_pct: 0,
  drift_threshold_pct: 5,
  check_interval_minutes: 60,
  min_trade_pct: 5,
  min_balance_usd: 0,
  min_balance_btc: 0,
  min_balance_eth: 0,
  min_balance_usdc: 0,
  min_balance_usdt: 0,
})

const makeAutoBuySettings = (enabled: boolean) => ({
  enabled,
  check_interval_minutes: 5,
  order_type: 'market',
  usd_enabled: false,
  usd_min: 10,
  usdc_enabled: false,
  usdc_min: 10,
  usdt_enabled: false,
  usdt_min: 10,
})

const makeDustSettings = () => ({
  enabled: false,
  threshold_usd: 5,
  last_sweep_at: null,
  dust_positions: [],
})

const makeRebalanceStatus = (enabled: boolean) => ({
  account_id: ACCOUNT_ID,
  current_usd_pct: 34, current_btc_pct: 33, current_eth_pct: 33,
  current_usdc_pct: 0, current_usdt_pct: 0,
  total_value_usd: 1000,
  target_usd_pct: 34, target_btc_pct: 33, target_eth_pct: 33,
  target_usdc_pct: 0, target_usdt_pct: 0,
  rebalance_enabled: enabled,
  min_balance_usd: 0, min_balance_btc: 0, min_balance_eth: 0,
  min_balance_usdc: 0, min_balance_usdt: 0,
  reserve_value_usd: 0, deployable_value_usd: 1000,
  reserve_usd_pct: 0, reserve_btc_pct: 0, reserve_eth_pct: 0,
  reserve_usdc_pct: 0, reserve_usdt_pct: 0,
})

const testAccount = { id: ACCOUNT_ID, name: 'Test CEX', type: 'cex' }

function readCache() {
  const raw = sessionStorage.getItem(CACHE_KEY)
  return raw ? JSON.parse(raw) : null
}

function writeCache(rebalanceEnabled: boolean, autoBuyEnabled: boolean) {
  const cache = {
    autoBuy: { [ACCOUNT_ID]: makeAutoBuySettings(autoBuyEnabled) },
    rebalance: { [ACCOUNT_ID]: makeRebalanceSettings(rebalanceEnabled) },
    dust: { [ACCOUNT_ID]: makeDustSettings() },
    bots: [],
    timestamp: Date.now(),
  }
  sessionStorage.setItem(CACHE_KEY, JSON.stringify(cache))
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('PortfolioManagement — cache writeback on mode toggle', () => {
  beforeEach(() => {
    sessionStorage.clear()
    mockGetAutoBuySettings.mockResolvedValue(makeAutoBuySettings(false))
    mockUpdateAutoBuySettings.mockResolvedValue(makeAutoBuySettings(false))
    mockGetRebalanceSettings.mockResolvedValue(makeRebalanceSettings(false))
    mockUpdateRebalanceSettings.mockResolvedValue(makeRebalanceSettings(false))
    mockGetRebalanceStatus.mockResolvedValue(makeRebalanceStatus(false))
    mockGetDustSettings.mockResolvedValue(makeDustSettings())
    mockBotsApiGetAll.mockResolvedValue([])
  })

  afterEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  it('writes enabled=false to cache when toggling rebalancing off', async () => {
    // Pre-populate cache with rebalancing ON (simulates a prior page load)
    writeCache(true, false)

    mockUpdateAutoBuySettings.mockResolvedValue(makeAutoBuySettings(false))
    mockUpdateRebalanceSettings.mockResolvedValue(makeRebalanceSettings(false))

    render(<PortfolioManagement accounts={[testAccount]} />)

    // Wait for component to render with cached data
    await waitFor(() => {
      expect(screen.getByText(/rebalancing/i)).toBeInTheDocument()
    })

    // Toggle to off
    const offButton = screen.getByRole('button', { name: /^off$/i })
    fireEvent.click(offButton)

    // Wait for the PUT to complete
    await waitFor(() => {
      expect(mockUpdateRebalanceSettings).toHaveBeenCalledWith(
        ACCOUNT_ID,
        expect.objectContaining({ enabled: false }),
      )
    })

    // Cache must reflect enabled=false so a page refresh within the TTL window
    // shows the correct state
    const cache = readCache()
    expect(cache).not.toBeNull()
    expect(cache.rebalance[ACCOUNT_ID].enabled).toBe(false)
    expect(cache.autoBuy[ACCOUNT_ID].enabled).toBe(false)
  })

  it('writes enabled=true to cache when toggling rebalancing on', async () => {
    writeCache(false, false)

    mockUpdateRebalanceSettings.mockResolvedValue(makeRebalanceSettings(true))
    mockGetRebalanceStatus.mockResolvedValue(makeRebalanceStatus(true))

    render(<PortfolioManagement accounts={[testAccount]} />)

    await waitFor(() => {
      expect(screen.getByText(/rebalancing/i)).toBeInTheDocument()
    })

    // Click the "Rebalancing" option in the mode selector
    const buttons = screen.getAllByRole('button', { name: /rebalancing/i })
    fireEvent.click(buttons[0])

    await waitFor(() => {
      expect(mockUpdateRebalanceSettings).toHaveBeenCalledWith(
        ACCOUNT_ID,
        expect.objectContaining({ enabled: true }),
      )
    })

    const cache = readCache()
    expect(cache).not.toBeNull()
    expect(cache.rebalance[ACCOUNT_ID].enabled).toBe(true)
  })

  it('auto-buy cache entry is also updated when toggling rebalance off', async () => {
    // When switching to "off", BOTH auto-buy and rebalance entries must be written
    // to the cache — otherwise enabling auto-buy after a refresh would show stale data.
    writeCache(true, false)

    mockUpdateAutoBuySettings.mockResolvedValue(makeAutoBuySettings(false))
    mockUpdateRebalanceSettings.mockResolvedValue(makeRebalanceSettings(false))

    render(<PortfolioManagement accounts={[testAccount]} />)

    await waitFor(() => expect(screen.getByRole('button', { name: /^off$/i })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /^off$/i }))

    await waitFor(() => {
      expect(mockUpdateAutoBuySettings).toHaveBeenCalledWith(
        ACCOUNT_ID,
        expect.objectContaining({ enabled: false }),
      )
      expect(mockUpdateRebalanceSettings).toHaveBeenCalledWith(
        ACCOUNT_ID,
        expect.objectContaining({ enabled: false }),
      )
    })

    const cache = readCache()
    expect(cache?.autoBuy[ACCOUNT_ID].enabled).toBe(false)
    expect(cache?.rebalance[ACCOUNT_ID].enabled).toBe(false)
  })
})
