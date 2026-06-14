import { useState, useEffect, useMemo, lazy, Suspense } from 'react'
import { Wallet, TrendingUp, DollarSign, Bitcoin, ArrowUpDown, ArrowUp, ArrowDown, BarChart3, RefreshCw, Building2 } from 'lucide-react'
import { useConfirm } from '../contexts/ConfirmContext'
import { useNotifications } from '../contexts/NotificationContext'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import { usePermission } from '../hooks/usePermission'
import { useAccountPortfolio } from '../hooks/useAccountPortfolio'
import { LoadingSpinner } from '../components/shared/LoadingSpinner'
import { useAccount, getChainName } from '../contexts/AccountContext'
import { formatUsd } from '../utils/numberFormat'

// Loaded lazily so lightweight-charts is only fetched when a chart is opened
const PortfolioChartModal = lazy(() => import('./portfolio/PortfolioChartModal'))

interface Holding {
  asset: string
  total_balance: number
  available: number
  in_positions?: number
  hold: number
  current_price_usd: number
  usd_value: number
  btc_value: number
  percentage: number
  unrealized_pnl_usd?: number
  unrealized_pnl_percentage?: number
}

interface BalanceBreakdown {
  total: number
  reserved_by_bots: number
  in_open_positions: number
  free: number
}

interface PortfolioData {
  total_usd_value: number
  total_btc_value: number
  btc_usd_price: number
  holdings: Holding[]
  holdings_count: number
  balance_breakdown?: {
    btc?: BalanceBreakdown
    usd?: BalanceBreakdown
    usdc?: BalanceBreakdown
    eth?: BalanceBreakdown
  }
  pnl?: {
    today: { usd: number; btc: number; usdc?: number; eth?: number }
    all_time: { usd: number; btc: number; usdc?: number; eth?: number }
  }
  // DEX-specific fields
  is_dex?: boolean
  account_type?: 'cex' | 'dex'
  account_id?: number
  account_name?: string
  chain_id?: number
  wallet_address?: string
}

type SortColumn = 'asset' | 'total_balance' | 'usd_value' | 'btc_value' | 'percentage' | 'unrealized_pnl_usd'
type SortDirection = 'asc' | 'desc'

function Portfolio() {
  const { selectedAccount } = useAccount()
  const queryClient = useQueryClient()
  const confirm = useConfirm()
  const { addToast } = useNotifications()
  const isObserver = selectedAccount?.membership_role === 'shadow'
  const canWriteAccounts = usePermission('accounts', 'write') && !isObserver

  // Shared portfolio query (live flavor: force_fresh so the backend bypasses
  // its cache and fetches live exchange data on this page).
  const {
    data: portfolio, isLoading: loading, error, isFetching, refetch: refetchPortfolio,
  } = useAccountPortfolio<PortfolioData>(selectedAccount?.id, { live: true })

  // Refresh portfolio after any completed trade (buy or sell) from any page
  useEffect(() => {
    const handler = () => { void refetchPortfolio() }
    window.addEventListener('portfolio:trade-completed', handler)
    return () => window.removeEventListener('portfolio:trade-completed', handler)
  }, [refetchPortfolio])

  // Manual refresh — same as auto-refresh since queryFn always uses force_fresh
  const handleManualRefresh = () => { void refetchPortfolio() }

  // Sell coin mutation
  const sellCoinMutation = useMutation({
    mutationFn: async ({ asset, quoteAsset, size }: { asset: string; quoteAsset: string; size: number }) => {
      const productId = `${asset}-${quoteAsset}`
      const response = await api.post('/trading/market-sell', {
        product_id: productId,
        size: size,
        account_id: selectedAccount?.id || null,
      })
      return response.data
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['account-portfolio'] })
      addToast({ type: 'success', title: 'Sell Complete', message: `Sold ${variables.size} ${variables.asset} to ${variables.quoteAsset}. Received: ${data.filled_value || 'N/A'} ${variables.quoteAsset}` })
    },
    onError: (error: unknown, variables) => {
      const e = error as { response?: { data?: { detail?: string } }; message?: string }
      const errorMsg = e.response?.data?.detail || e.message || 'Unknown error'
      addToast({ type: 'error', title: 'Sell Failed', message: `Failed to sell ${variables.asset} to ${variables.quoteAsset}: ${errorMsg}` })
    }
  })

  // Helper: Check if sell to USD is available for this asset
  const canSellToUSD = (asset: string) => {
    // Can't sell USD, USDC, USDT to USD (they are quote currencies)
    if (['USD', 'USDC', 'USDT'].includes(asset)) return false
    return true
  }

  // Helper: Check if sell to BTC is available for this asset
  const canSellToBTC = (asset: string) => {
    // Can't sell BTC to BTC
    if (asset === 'BTC') return false
    // Can't sell USD/stablecoins to BTC (no such market on most exchanges)
    if (['USD', 'USDC', 'USDT'].includes(asset)) return false
    return true
  }

  // Handle sell action
  const handleSell = async (asset: string, quoteAsset: 'USD' | 'BTC', available: number) => {
    if (available <= 0) {
      addToast({ type: 'error', title: 'No Balance', message: `No ${asset} available to sell` })
      return
    }

    const confirmed = await confirm({
      title: `Sell ${asset}`,
      message: `Sell all ${available.toFixed(8)} ${asset} to ${quoteAsset}?\n\nThis will execute a market sell order.`,
      variant: 'warning',
      confirmLabel: 'Sell',
    })

    if (confirmed) {
      sellCoinMutation.mutate({ asset, quoteAsset, size: available })
    }
  }

  const [hideDust, setHideDust] = useState<boolean>(() => {
    const stored = localStorage.getItem('portfolio:hideDust')
    return stored === null ? true : stored === 'true'
  })

  const toggleHideDust = () => {
    setHideDust(prev => {
      const next = !prev
      localStorage.setItem('portfolio:hideDust', String(next))
      return next
    })
  }

  const [sortColumn, setSortColumn] = useState<SortColumn>('usd_value')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [chartModalAsset, setChartModalAsset] = useState<string | null>(null)

  const formatCurrency = formatUsd

  const formatCrypto = (value: number, decimals: number = 8) => {
    return value.toFixed(decimals)
  }

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      // Toggle direction if clicking same column
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      // Default to descending for new column (except asset name)
      setSortColumn(column)
      setSortDirection(column === 'asset' ? 'asc' : 'desc')
    }
  }

  const getSortIcon = (column: SortColumn) => {
    if (sortColumn !== column) {
      return <ArrowUpDown size={14} className="text-slate-500" />
    }
    return sortDirection === 'asc'
      ? <ArrowUp size={14} className="text-blue-400" />
      : <ArrowDown size={14} className="text-blue-400" />
  }

  const DUST_THRESHOLD_USD = 1.0

  const sortedHoldings = useMemo(() => {
    const all = portfolio?.holdings ?? []
    const filtered = hideDust ? all.filter((h: Holding) => h.usd_value >= DUST_THRESHOLD_USD) : all
    return filtered.slice().sort((a: Holding, b: Holding) => {
      let compareValue = 0
      switch (sortColumn) {
        case 'asset':
          compareValue = a.asset.localeCompare(b.asset)
          break
        case 'total_balance':
          compareValue = a.total_balance - b.total_balance
          break
        case 'usd_value':
          compareValue = a.usd_value - b.usd_value
          break
        case 'btc_value':
          compareValue = a.btc_value - b.btc_value
          break
        case 'percentage':
          compareValue = a.percentage - b.percentage
          break
        case 'unrealized_pnl_usd':
          compareValue = (a.unrealized_pnl_usd || 0) - (b.unrealized_pnl_usd || 0)
          break
      }
      return sortDirection === 'asc' ? compareValue : -compareValue
    })
  }, [portfolio?.holdings, sortColumn, sortDirection, hideDust])

  const dustCount = useMemo(() => {
    const all = portfolio?.holdings ?? []
    return all.filter((h: Holding) => h.usd_value < DUST_THRESHOLD_USD).length
  }, [portfolio?.holdings])

  const openChartModal = (asset: string) => {
    setChartModalAsset(asset)
  }

  const closeChartModal = () => {
    setChartModalAsset(null)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <LoadingSpinner size="lg" text="Loading portfolio data..." />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-red-400">
          Error: {error instanceof Error ? error.message : 'Unknown error'}
        </div>
      </div>
    )
  }

  if (!portfolio) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-slate-400">No portfolio data available</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-900 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            {selectedAccount?.type === 'dex' ? (
              <Wallet className="text-orange-400" size={32} />
            ) : (
              <Building2 className="text-blue-400" size={32} />
            )}
            <div>
              <h1 className="text-3xl font-bold text-white">Portfolio</h1>
              {selectedAccount && (
                <p className="text-sm text-slate-400">
                  {selectedAccount.name}
                  {selectedAccount.type === 'dex' && selectedAccount.chain_id && (
                    <span className="text-slate-500"> ({getChainName(selectedAccount.chain_id)})</span>
                  )}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={() => handleManualRefresh()}
            disabled={isFetching}
            className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 text-slate-300 px-4 py-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Refresh Portfolio"
          >
            <RefreshCw size={18} className={isFetching ? 'animate-spin' : ''} />
            <span className="text-sm font-medium">{isFetching ? 'Refreshing...' : 'Refresh'}</span>
          </button>
        </div>

        {/* Total Value Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <div className="flex items-center gap-2 mb-2">
              <DollarSign size={20} className="text-green-400" />
              <p className="text-slate-400 text-sm font-medium">Total USD Value</p>
            </div>
            <p className="text-3xl font-bold text-white">
              {formatCurrency(portfolio.total_usd_value)}
            </p>
          </div>

          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <div className="flex items-center gap-2 mb-2">
              <Bitcoin size={20} className="text-orange-400" />
              <p className="text-slate-400 text-sm font-medium">Total BTC Value</p>
            </div>
            <p className="text-3xl font-bold text-white">
              {formatCrypto(portfolio.total_btc_value)} BTC
            </p>
          </div>

          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp size={20} className="text-blue-400" />
              <p className="text-slate-400 text-sm font-medium">BTC Price</p>
            </div>
            <p className="text-3xl font-bold text-white">
              {formatCurrency(portfolio.btc_usd_price)}
            </p>
          </div>
        </div>

        {/* Balance Breakdowns - Organized by Currency */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {/* BTC Column */}
          <div className="space-y-4">
            {/* BTC Balance Breakdown (CEX only) */}
            {portfolio.balance_breakdown?.btc && (
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <div className="flex items-center gap-2 mb-4">
                  <Bitcoin size={20} className="text-orange-400" />
                  <p className="text-slate-300 text-sm font-semibold">BTC Balance Breakdown</p>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">Total:</span>
                    <span className="text-white font-mono text-sm">{formatCrypto(portfolio.balance_breakdown.btc.total)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">Reserved by Bots:</span>
                    <span className="text-orange-400 font-mono text-sm">{formatCrypto(portfolio.balance_breakdown.btc.reserved_by_bots)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">In Open Positions:</span>
                    <span className="text-yellow-400 font-mono text-sm">{formatCrypto(portfolio.balance_breakdown.btc.in_open_positions)}</span>
                  </div>
                  <div className="pt-2 border-t border-slate-700 flex justify-between items-center">
                    <span className="text-slate-300 text-sm font-semibold">Free (Available):</span>
                    <span className="text-green-400 font-mono text-lg font-bold">{formatCrypto(portfolio.balance_breakdown.btc.free)}</span>
                  </div>
                </div>
              </div>
            )}

            {/* ETH Balance Breakdown (DEX only) */}
            {portfolio.balance_breakdown?.eth && (
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <div className="flex items-center gap-2 mb-4">
                  <Wallet size={20} className="text-blue-400" />
                  <p className="text-slate-300 text-sm font-semibold">ETH Balance Breakdown</p>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">Total:</span>
                    <span className="text-white font-mono text-sm">{formatCrypto(portfolio.balance_breakdown.eth.total)} ETH</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">Reserved by Bots:</span>
                    <span className="text-orange-400 font-mono text-sm">{formatCrypto(portfolio.balance_breakdown.eth.reserved_by_bots)} ETH</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">In Open Positions:</span>
                    <span className="text-yellow-400 font-mono text-sm">{formatCrypto(portfolio.balance_breakdown.eth.in_open_positions)} ETH</span>
                  </div>
                  <div className="pt-2 border-t border-slate-700 flex justify-between items-center">
                    <span className="text-slate-300 text-sm font-semibold">Free (Available):</span>
                    <span className="text-green-400 font-mono text-lg font-bold">{formatCrypto(portfolio.balance_breakdown.eth.free)} ETH</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* USD Column */}
          <div className="space-y-4">
            {/* USD Balance Breakdown (CEX only) */}
            {portfolio.balance_breakdown?.usd && (
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <div className="flex items-center gap-2 mb-4">
                  <DollarSign size={20} className="text-green-400" />
                  <p className="text-slate-300 text-sm font-semibold">USD Balance Breakdown</p>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">Total:</span>
                    <span className="text-white font-mono text-sm">{formatCurrency(portfolio.balance_breakdown.usd.total)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">Reserved by Bots:</span>
                    <span className="text-orange-400 font-mono text-sm">{formatCurrency(portfolio.balance_breakdown.usd.reserved_by_bots)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">In Open Positions:</span>
                    <span className="text-yellow-400 font-mono text-sm">{formatCurrency(portfolio.balance_breakdown.usd.in_open_positions)}</span>
                  </div>
                  <div className="pt-2 border-t border-slate-700 flex justify-between items-center">
                    <span className="text-slate-300 text-sm font-semibold">Free (Available):</span>
                    <span className="text-green-400 font-mono text-lg font-bold">{formatCurrency(portfolio.balance_breakdown.usd.free)}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* USDC Column */}
          <div className="space-y-4">
            {/* USDC Balance Breakdown */}
            {portfolio.balance_breakdown && portfolio.balance_breakdown.usdc && (
              <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
                <div className="flex items-center gap-2 mb-4">
                  <DollarSign size={20} className="text-blue-400" />
                  <p className="text-slate-300 text-sm font-semibold">USDC Balance Breakdown</p>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">Total:</span>
                    <span className="text-white font-mono text-sm">{formatCurrency(portfolio.balance_breakdown.usdc.total)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">Reserved by Bots:</span>
                    <span className="text-orange-400 font-mono text-sm">{formatCurrency(portfolio.balance_breakdown.usdc.reserved_by_bots)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400 text-sm">In Open Positions:</span>
                    <span className="text-yellow-400 font-mono text-sm">{formatCurrency(portfolio.balance_breakdown.usdc.in_open_positions)}</span>
                  </div>
                  <div className="pt-2 border-t border-slate-700 flex justify-between items-center">
                    <span className="text-slate-300 text-sm font-semibold">Free (Available):</span>
                    <span className="text-green-400 font-mono text-lg font-bold">{formatCurrency(portfolio.balance_breakdown.usdc.free)}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Holdings Table */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <div className="p-4 border-b border-slate-700 flex items-center justify-between">
            <h2 className="text-xl font-semibold text-white">
              Holdings ({sortedHoldings.length}{hideDust && dustCount > 0 ? ` of ${portfolio.holdings_count}` : ''})
            </h2>
            <button
              onClick={toggleHideDust}
              className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                hideDust
                  ? 'bg-slate-700 border-slate-600 text-slate-300 hover:bg-slate-600'
                  : 'bg-amber-900/30 border-amber-700 text-amber-400 hover:bg-amber-900/50'
              }`}
              title={hideDust ? `Showing holdings ≥$1. Click to show all (${dustCount} dust hidden)` : 'Showing all holdings including dust (< $1)'}
            >
              {hideDust ? `Dust hidden${dustCount > 0 ? ` (${dustCount})` : ''}` : 'Show all'}
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-900">
                <tr>
                  <th
                    className="px-3 py-3 text-left text-sm font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('asset')}
                  >
                    <div className="flex items-center gap-2">
                      <span>Asset</span>
                      {getSortIcon('asset')}
                    </div>
                  </th>
                  <th
                    className="hidden sm:table-cell px-3 py-3 text-right text-sm font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('total_balance')}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <span>Balance</span>
                      {getSortIcon('total_balance')}
                    </div>
                  </th>
                  <th className="hidden md:table-cell px-3 py-3 text-right text-sm font-medium text-slate-400 uppercase tracking-wider">
                    Free
                  </th>
                  <th className="hidden md:table-cell px-3 py-3 text-right text-sm font-medium text-slate-400 uppercase tracking-wider">
                    In Deals
                  </th>
                  <th className="hidden sm:table-cell px-3 py-3 text-right text-sm font-medium text-slate-400 uppercase tracking-wider">
                    Price
                  </th>
                  <th
                    className="px-3 py-3 text-right text-sm font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('usd_value')}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <span>USD Value</span>
                      {getSortIcon('usd_value')}
                    </div>
                  </th>
                  <th
                    className="hidden sm:table-cell px-3 py-3 text-right text-sm font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('btc_value')}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <span>BTC Value</span>
                      {getSortIcon('btc_value')}
                    </div>
                  </th>
                  <th
                    className="hidden sm:table-cell px-3 py-3 text-right text-sm font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('percentage')}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <span>% Port</span>
                      {getSortIcon('percentage')}
                    </div>
                  </th>
                  <th
                    className="px-3 py-3 text-right text-sm font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('unrealized_pnl_usd')}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <span>uPnL</span>
                      {getSortIcon('unrealized_pnl_usd')}
                    </div>
                  </th>
                  <th className="px-2 py-3 text-center text-sm font-medium text-slate-400 uppercase tracking-wider">
                    Sell
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {sortedHoldings.map((holding) => (
                  <tr
                    key={holding.asset}
                    className="hover:bg-slate-750 transition-colors"
                  >
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-white text-sm">{holding.asset}</span>
                        <button
                          onClick={() => openChartModal(holding.asset)}
                          className="text-slate-400 hover:text-blue-400 transition-colors"
                          title="View Chart"
                        >
                          <BarChart3 size={14} />
                        </button>
                      </div>
                    </td>
                    <td className="hidden sm:table-cell px-3 py-3 text-right text-white font-mono text-sm">
                      {formatCrypto(holding.total_balance)}
                    </td>
                    <td className="hidden md:table-cell px-3 py-3 text-right text-green-400 font-mono text-sm">
                      {formatCrypto(holding.available)}
                    </td>
                    <td className="hidden md:table-cell px-3 py-3 text-right text-yellow-400 font-mono text-sm">
                      {(holding.in_positions ?? 0) > 0 ? formatCrypto(holding.in_positions!) : '-'}
                    </td>
                    <td className="hidden sm:table-cell px-3 py-3 text-right text-slate-300 font-mono text-sm">
                      {holding.current_price_usd > 0
                        ? formatCurrency(holding.current_price_usd)
                        : '-'}
                    </td>
                    <td className="px-3 py-3 text-right text-white font-semibold text-sm">
                      {formatCurrency(holding.usd_value)}
                    </td>
                    <td className="hidden sm:table-cell px-3 py-3 text-right text-orange-400 font-mono text-sm">
                      {formatCrypto(holding.btc_value, 6)}
                    </td>
                    <td className="hidden sm:table-cell px-3 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <span className="text-white font-medium text-sm">
                          {holding.percentage.toFixed(1)}%
                        </span>
                        <div className="w-16 bg-slate-700 rounded-full h-1.5">
                          <div
                            className="bg-blue-500 h-1.5 rounded-full"
                            style={{ width: `${Math.min(holding.percentage, 100)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-right">
                      {(() => {
                        const pnl = holding.unrealized_pnl_usd || 0
                        const pnlPct = holding.unrealized_pnl_percentage || 0
                        const isPositive = pnl > 0
                        const isNegative = pnl < 0
                        const colorClass = isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'

                        if (Math.abs(pnl) < 0.01) {
                          return <span className="text-slate-500 text-sm">—</span>
                        }

                        return (
                          <div className="flex flex-col items-end">
                            <span className={`font-medium text-sm ${colorClass}`}>
                              {isPositive ? '+' : ''}{formatCurrency(pnl)}
                            </span>
                            <span className={`text-xs ${colorClass}`}>
                              {isPositive ? '+' : ''}{pnlPct.toFixed(1)}%
                            </span>
                          </div>
                        )
                      })()}
                    </td>
                    <td className="px-2 py-3">
                      <div className="flex items-center justify-center gap-1">
                        {!isObserver && canSellToUSD(holding.asset) && (
                          <button
                            onClick={canWriteAccounts ? () => handleSell(holding.asset, 'USD', holding.available) : undefined}
                            disabled={!canWriteAccounts || holding.available <= 0 || holding.hold > 0 || sellCoinMutation.isPending}
                            className="p-1.5 rounded bg-green-600 hover:bg-green-700 text-white disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed transition-colors"
                            title={
                              holding.hold > 0
                                ? `Cannot sell - ${holding.asset} has open positions (${formatCrypto(holding.hold)} held)`
                                : holding.available <= 0
                                ? `No ${holding.asset} available to sell`
                                : `Sell ${holding.asset} to USD`
                            }
                          >
                            <DollarSign size={14} />
                          </button>
                        )}
                        {!isObserver && canSellToBTC(holding.asset) && (
                          <button
                            onClick={canWriteAccounts ? () => handleSell(holding.asset, 'BTC', holding.available) : undefined}
                            disabled={!canWriteAccounts || holding.available <= 0 || holding.hold > 0 || sellCoinMutation.isPending}
                            className="p-1.5 rounded bg-orange-600 hover:bg-orange-700 text-white disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed transition-colors"
                            title={
                              holding.hold > 0
                                ? `Cannot sell - ${holding.asset} has open positions (${formatCrypto(holding.hold)} held)`
                                : holding.available <= 0
                                ? `No ${holding.asset} available to sell`
                                : `Sell ${holding.asset} to BTC`
                            }
                          >
                            <Bitcoin size={14} />
                          </button>
                        )}
                        {(isObserver || (!canSellToUSD(holding.asset) && !canSellToBTC(holding.asset))) && (
                          <span className="text-xs text-slate-500">—</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {sortedHoldings.length === 0 && (
            <div className="p-8 text-center text-slate-400">
              {hideDust && dustCount > 0
                ? `All ${dustCount} holding${dustCount === 1 ? '' : 's'} are dust (< $1). `
                : 'No holdings found in your portfolio'}
              {hideDust && dustCount > 0 && (
                <button className="text-blue-400 hover:underline" onClick={toggleHideDust}>
                  Show all
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Chart Modal (lazy — pulls in lightweight-charts on demand) */}
      {chartModalAsset && (
        <Suspense
          fallback={
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
              <LoadingSpinner size="lg" text="Loading chart..." />
            </div>
          }
        >
          <PortfolioChartModal asset={chartModalAsset} onClose={closeChartModal} />
        </Suspense>
      )}
    </div>
  )
}

export default Portfolio
