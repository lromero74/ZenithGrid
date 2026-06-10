import { describe, test, expect, beforeEach, vi } from 'vitest'
import { render } from '@testing-library/react'
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import Positions from './Positions'

vi.mock('../contexts/AccountContext', () => ({
  useAccount: vi.fn(() => ({
    selectedAccount: {
      id: 7,
      name: 'Paper',
      type: 'cex',
      membership_role: 'owner',
    },
  })),
  getChainName: vi.fn(() => 'Ethereum'),
}))

vi.mock('../contexts/ConfirmContext', () => ({
  useConfirm: vi.fn(() => vi.fn()),
}))

vi.mock('../contexts/NotificationContext', () => ({
  useNotifications: vi.fn(() => ({
    addToast: vi.fn(),
  })),
}))

vi.mock('../hooks/usePermission', () => ({
  usePermission: vi.fn(() => true),
}))

vi.mock('./positions/hooks/usePositionsData', () => ({
  usePositionsData: vi.fn(() => ({
    allPositions: [],
    positionsWithPnL: [],
    bots: [],
    btcUsdPrice: 0,
    currentPrices: {},
    refetchPositions: vi.fn(),
  })),
}))

vi.mock('./positions/hooks/usePositionMutations', () => ({
  usePositionMutations: vi.fn(() => ({
    isProcessing: false,
    handleClosePosition: vi.fn(),
    handleAddFundsSuccess: vi.fn(),
    handleSaveNotes: vi.fn(),
  })),
}))

vi.mock('./positions/hooks/usePositionFilters', () => ({
  usePositionFilters: vi.fn(() => ({
    filterBot: 'all',
    setFilterBot: vi.fn(),
    filterMarket: 'all',
    setFilterMarket: vi.fn(),
    filterPair: 'all',
    setFilterPair: vi.fn(),
    filterCategory: 'all',
    setFilterCategory: vi.fn(),
    groupBy: 'none',
    setGroupBy: vi.fn(),
    sortBy: 'opened_at',
    setSortBy: vi.fn(),
    sortOrder: 'desc',
    setSortOrder: vi.fn(),
    pageSize: 10,
    setPageSize: vi.fn(),
    currentPage: 1,
    setCurrentPage: vi.fn(),
    totalCount: 0,
    totalPages: 1,
    openPositions: [],
    filteredPositions: [],
    uniqueMarkets: [],
    uniqueBots: [],
    uniquePairs: [],
    uniqueCategories: [],
    getGroupKey: vi.fn(() => 'all'),
    clearFilters: vi.fn(),
  })),
}))

vi.mock('./positions/hooks/usePositionTrades', () => ({
  usePositionTrades: vi.fn(() => ({
    trades: [],
    tradeHistory: [],
    isLoadingTradeHistory: false,
  })),
}))

vi.mock('./positions/helpers', () => ({
  calculateOverallStats: vi.fn(() => ({
    totalPnL: 0,
    totalValue: 0,
    avgProfit: 0,
    avgProfitPct: 0,
    totalPositions: 0,
  })),
  checkSlippageBeforeMarketClose: vi.fn(),
}))

vi.mock('./positions/components', () => ({
  OverallStatsPanel: () => React.createElement('div', null, 'Overall Stats'),
  FilterPanel: () => React.createElement('div', null, 'Filter Panel'),
  PositionCard: () => React.createElement('div', null, 'Position Card'),
  VirtualizedPositionList: ({ items, renderItem }: { items: unknown[]; renderItem: (item: unknown, i: number) => React.ReactNode }) =>
    React.createElement('div', null, items.map((item, i) => React.createElement('div', { key: i }, renderItem(item, i)))),
  CloseConfirmModal: () => null,
  NotesModal: () => null,
  TradeHistoryModal: () => null,
}))

vi.mock('../components/positions/PositionLogsModal', () => ({
  default: () => null,
}))

vi.mock('../components/trading/TradingViewChartModal', () => ({
  default: () => null,
}))

vi.mock('../components/trading/LightweightChartModal', () => ({
  default: () => null,
}))

vi.mock('../components/positions/LimitCloseModal', () => ({
  LimitCloseModal: () => null,
}))

vi.mock('../components/positions/SlippageWarningModal', () => ({
  SlippageWarningModal: () => null,
}))

vi.mock('../components/positions/EditPositionSettingsModal', () => ({
  EditPositionSettingsModal: () => null,
}))

vi.mock('../components/positions/AddFundsModal', () => ({
  AddFundsModal: () => null,
}))

vi.mock('../components/positions/PanicSellModal', () => ({
  PanicSellModal: () => null,
}))

vi.mock('../services/api', () => ({
  positionsApi: {
    getCompletedStats: vi.fn().mockResolvedValue({}),
    getRealizedPnL: vi.fn().mockResolvedValue({}),
  },
  accountApi: {
    getBalances: vi.fn().mockResolvedValue([]),
  },
}))

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })

  render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <Positions />
      </QueryClientProvider>
    </MemoryRouter>
  )

  return queryClient
}

describe('Positions polling policy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('background refresh queries stop polling in hidden tabs and on window focus', () => {
    const queryClient = renderPage()
    const queries = queryClient.getQueryCache().getAll()

    const targetKeys = [
      JSON.stringify(['completed-trades-stats', 7]),
      JSON.stringify(['realized-pnl', 7]),
      JSON.stringify(['account-balances', 7]),
    ]

    const observerOptions = queries
      .filter((query) => targetKeys.includes(JSON.stringify(query.queryKey)))
      .flatMap((query) => query.observers.map((observer: any) => observer.options))

    expect(observerOptions).toHaveLength(3)
    observerOptions.forEach((options: any) => {
      expect(options.refetchInterval).toBe(120000)
      expect(options.refetchIntervalInBackground).toBe(false)
      expect(options.refetchOnWindowFocus).toBe(false)
    })
  })
})
