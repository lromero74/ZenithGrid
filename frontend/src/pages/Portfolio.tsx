import { useState, useEffect, useRef } from 'react'
import { Wallet, TrendingUp, DollarSign, Bitcoin, ArrowUpDown, ArrowUp, ArrowDown, BarChart3, X, RefreshCw, Building2 } from 'lucide-react'
import { createChart, ColorType, IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { API_BASE_URL } from '../config/api'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { useAccount, getChainName } from '../contexts/AccountContext'

interface CandleData {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface Holding {
  asset: string
  total_balance: number
  available: number
  hold: number
  current_price_usd: number
  usd_value: number
  btc_value: number
  percentage: number
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

  // Use React Query with account-specific key
  const { data: portfolio, isLoading: loading, error, refetch, isFetching } = useQuery({
    queryKey: ['account-portfolio', selectedAccount?.id],
    queryFn: async () => {
      // If we have a selected account, use the account-specific endpoint
      if (selectedAccount) {
        const response = await fetch(`/api/accounts/${selectedAccount.id}/portfolio`)
        if (!response.ok) throw new Error('Failed to fetch portfolio')
        return response.json() as Promise<PortfolioData>
      }
      // Fallback to legacy endpoint
      const response = await fetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json() as Promise<PortfolioData>
    },
    refetchInterval: 60000, // Update prices every 60 seconds
    staleTime: 30000, // Consider data fresh for 30 seconds
    refetchOnMount: false, // Don't refetch on page refresh - use cache
    refetchOnWindowFocus: false, // Don't refetch when window regains focus
    enabled: true, // Always enabled, will use fallback if no account selected
  })

  const [sortColumn, setSortColumn] = useState<SortColumn>('usd_value')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [chartModalAsset, setChartModalAsset] = useState<string | null>(null)
  const [chartPairType, setChartPairType] = useState<'USD' | 'BTC'>('USD')
  const [chartTimeframe, setChartTimeframe] = useState('FIFTEEN_MINUTE')
  const [chartLoading, setChartLoading] = useState(false)
  const [chartError, setChartError] = useState<string | null>(null)

  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const mainSeriesRef = useRef<ISeriesApi<any> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)
  }

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

  const sortedHoldings = portfolio?.holdings.slice().sort((a, b) => {
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
        compareValue = ((a as any).unrealized_pnl_usd || 0) - ((b as any).unrealized_pnl_usd || 0)
        break
    }

    return sortDirection === 'asc' ? compareValue : -compareValue
  }) || []

  const openChartModal = (asset: string) => {
    setChartModalAsset(asset)
    setChartPairType('USD')
    setChartTimeframe('FIFTEEN_MINUTE')
  }

  const closeChartModal = () => {
    setChartModalAsset(null)
    if (chartRef.current) {
      chartRef.current.remove()
      chartRef.current = null
    }
    mainSeriesRef.current = null
    volumeSeriesRef.current = null
  }

  // Initialize chart when modal opens
  useEffect(() => {
    if (!chartModalAsset || !chartContainerRef.current) return

    // Create chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1e293b' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#334155' },
        horzLines: { color: '#334155' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 400,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        visible: true,
        borderVisible: true,
        borderColor: '#334155',
        autoScale: true,
        scaleMargins: {
          top: 0.1,
          bottom: 0.2,
        },
      },
    })

    chartRef.current = chart

    // Determine price format based on pair type
    const isBTCPair = chartPairType === 'BTC'
    const priceFormat = isBTCPair
      ? { type: 'price' as const, precision: 8, minMove: 0.00000001 }
      : { type: 'price' as const, precision: 2, minMove: 0.01 }

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceScaleId: 'right',
      priceFormat: priceFormat,
    })

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'volume',
    })

    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.85,
        bottom: 0,
      },
    })

    mainSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    return () => {
      chart.remove()
    }
  }, [chartModalAsset, chartPairType])

  // Fetch chart data
  useEffect(() => {
    if (!chartModalAsset || !mainSeriesRef.current || !volumeSeriesRef.current) return

    const fetchChartData = async () => {
      setChartLoading(true)
      setChartError(null)

      try {
        const productId = `${chartModalAsset}-${chartPairType}`
        const response = await axios.get<{ candles: CandleData[] }>(
          `${API_BASE_URL}/api/candles`,
          {
            params: {
              product_id: productId,
              granularity: chartTimeframe,
              limit: 200,
            },
          }
        )

        const { candles } = response.data

        if (!candles || candles.length === 0) {
          setChartError(`No data available for ${productId}`)
          return
        }

        const priceData = candles.map((c) => ({
          time: c.time as Time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }))

        const volumeData = candles.map((c) => ({
          time: c.time as Time,
          value: c.volume,
          color: c.close >= c.open ? '#10b98180' : '#ef444480',
        }))

        if (mainSeriesRef.current && volumeSeriesRef.current) {
          mainSeriesRef.current.setData(priceData)
          volumeSeriesRef.current.setData(volumeData)
          if (chartRef.current) {
            chartRef.current.timeScale().fitContent()
          }
        }
      } catch (err: any) {
        console.error('Error fetching chart data:', err)
        setChartError(err.response?.data?.detail || 'Failed to load chart data')
      } finally {
        setChartLoading(false)
      }
    }

    fetchChartData()
  }, [chartModalAsset, chartPairType, chartTimeframe])

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
            onClick={() => refetch()}
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

        {/* PnL Stats & Balance - Organized by Currency */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {/* BTC Column */}
          <div className="space-y-4">
            {/* Today PnL (BTC) */}
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp size={20} className={portfolio.pnl?.today?.btc >= 0 ? "text-green-400" : "text-red-400"} />
                <p className="text-slate-400 text-sm font-medium">Today PnL (BTC)</p>
              </div>
              <p className={`text-3xl font-bold ${portfolio.pnl?.today?.btc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {portfolio.pnl?.today?.btc >= 0 ? '+' : ''}{formatCrypto(portfolio.pnl?.today?.btc || 0)} BTC
              </p>
              <p className="text-sm text-slate-400 mt-1">
                ({portfolio.pnl?.today?.btc >= 0 ? '+' : ''}{formatCurrency((portfolio.pnl?.today?.btc || 0) * portfolio.btc_usd_price)})
              </p>
            </div>

            {/* All-Time PnL (BTC) */}
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp size={20} className={portfolio.pnl?.all_time?.btc >= 0 ? "text-green-400" : "text-red-400"} />
                <p className="text-slate-400 text-sm font-medium">All-Time PnL (BTC)</p>
              </div>
              <p className={`text-3xl font-bold ${portfolio.pnl?.all_time?.btc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {portfolio.pnl?.all_time?.btc >= 0 ? '+' : ''}{formatCrypto(portfolio.pnl?.all_time?.btc || 0)} BTC
              </p>
              <p className="text-sm text-slate-400 mt-1">
                ({portfolio.pnl?.all_time?.btc >= 0 ? '+' : ''}{formatCurrency((portfolio.pnl?.all_time?.btc || 0) * portfolio.btc_usd_price)})
              </p>
            </div>

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
            {/* Today PnL (USD) */}
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp size={20} className={portfolio.pnl?.today?.usd >= 0 ? "text-green-400" : "text-red-400"} />
                <p className="text-slate-400 text-sm font-medium">Today PnL (USD)</p>
              </div>
              <p className={`text-3xl font-bold ${portfolio.pnl?.today?.usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {portfolio.pnl?.today?.usd >= 0 ? '+' : ''}{formatCurrency(portfolio.pnl?.today?.usd || 0)}
              </p>
              <p className="text-sm text-slate-400 mt-1">
                ({portfolio.pnl?.today?.usd >= 0 ? '+' : ''}{formatCrypto((portfolio.pnl?.today?.usd || 0) / portfolio.btc_usd_price)} BTC)
              </p>
            </div>

            {/* All-Time PnL (USD) */}
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp size={20} className={portfolio.pnl?.all_time?.usd >= 0 ? "text-green-400" : "text-red-400"} />
                <p className="text-slate-400 text-sm font-medium">All-Time PnL (USD)</p>
              </div>
              <p className={`text-3xl font-bold ${portfolio.pnl?.all_time?.usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {portfolio.pnl?.all_time?.usd >= 0 ? '+' : ''}{formatCurrency(portfolio.pnl?.all_time?.usd || 0)}
              </p>
              <p className="text-sm text-slate-400 mt-1">
                ({portfolio.pnl?.all_time?.usd >= 0 ? '+' : ''}{formatCrypto((portfolio.pnl?.all_time?.usd || 0) / portfolio.btc_usd_price)} BTC)
              </p>
            </div>

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
            {/* Today PnL (USDC) */}
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp size={20} className={portfolio.pnl?.today?.usdc >= 0 ? "text-green-400" : "text-red-400"} />
                <p className="text-slate-400 text-sm font-medium">Today PnL (USDC)</p>
              </div>
              <p className={`text-3xl font-bold ${portfolio.pnl?.today?.usdc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {portfolio.pnl?.today?.usdc >= 0 ? '+' : ''}{formatCurrency(portfolio.pnl?.today?.usdc || 0)}
              </p>
              <p className="text-sm text-slate-400 mt-1">
                ({portfolio.pnl?.today?.usdc >= 0 ? '+' : ''}{formatCrypto((portfolio.pnl?.today?.usdc || 0) / portfolio.btc_usd_price)} BTC)
              </p>
            </div>

            {/* All-Time PnL (USDC) */}
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp size={20} className={portfolio.pnl?.all_time?.usdc >= 0 ? "text-green-400" : "text-red-400"} />
                <p className="text-slate-400 text-sm font-medium">All-Time PnL (USDC)</p>
              </div>
              <p className={`text-3xl font-bold ${portfolio.pnl?.all_time?.usdc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {portfolio.pnl?.all_time?.usdc >= 0 ? '+' : ''}{formatCurrency(portfolio.pnl?.all_time?.usdc || 0)}
              </p>
              <p className="text-sm text-slate-400 mt-1">
                ({portfolio.pnl?.all_time?.usdc >= 0 ? '+' : ''}{formatCrypto((portfolio.pnl?.all_time?.usdc || 0) / portfolio.btc_usd_price)} BTC)
              </p>
            </div>

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
          <div className="p-4 border-b border-slate-700">
            <h2 className="text-xl font-semibold text-white">
              Holdings ({portfolio.holdings_count})
            </h2>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-900">
                <tr>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('asset')}
                  >
                    <div className="flex items-center gap-2">
                      <span>Asset</span>
                      {getSortIcon('asset')}
                    </div>
                  </th>
                  <th
                    className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('total_balance')}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <span>Total Balance</span>
                      {getSortIcon('total_balance')}
                    </div>
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Available
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Hold
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">
                    Price (USD)
                  </th>
                  <th
                    className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('usd_value')}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <span>USD Value</span>
                      {getSortIcon('usd_value')}
                    </div>
                  </th>
                  <th
                    className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('btc_value')}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <span>BTC Value</span>
                      {getSortIcon('btc_value')}
                    </div>
                  </th>
                  <th
                    className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('percentage')}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <span>% of Portfolio</span>
                      {getSortIcon('percentage')}
                    </div>
                  </th>
                  <th
                    className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200 transition-colors"
                    onClick={() => handleSort('unrealized_pnl_usd')}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <span>Unrealized PnL</span>
                      {getSortIcon('unrealized_pnl_usd')}
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {sortedHoldings.map((holding) => (
                  <tr
                    key={holding.asset}
                    className="hover:bg-slate-750 transition-colors"
                  >
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-3">
                        <span className="font-semibold text-white">{holding.asset}</span>
                        <button
                          onClick={() => openChartModal(holding.asset)}
                          className="text-slate-400 hover:text-blue-400 transition-colors"
                          title="View Chart"
                        >
                          <BarChart3 size={16} />
                        </button>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-right text-white font-mono">
                      {formatCrypto(holding.total_balance)}
                    </td>
                    <td className="px-4 py-4 text-right text-green-400 font-mono">
                      {formatCrypto(holding.available)}
                    </td>
                    <td className="px-4 py-4 text-right text-orange-400 font-mono">
                      {holding.hold > 0 ? formatCrypto(holding.hold) : '-'}
                    </td>
                    <td className="px-4 py-4 text-right text-slate-300 font-mono">
                      {holding.current_price_usd > 0
                        ? formatCurrency(holding.current_price_usd)
                        : '-'}
                    </td>
                    <td className="px-4 py-4 text-right text-white font-semibold">
                      {formatCurrency(holding.usd_value)}
                    </td>
                    <td className="px-4 py-4 text-right text-orange-400 font-mono">
                      {formatCrypto(holding.btc_value, 6)}
                    </td>
                    <td className="px-4 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <span className="text-white font-medium">
                          {holding.percentage.toFixed(2)}%
                        </span>
                        <div className="w-20 bg-slate-700 rounded-full h-2">
                          <div
                            className="bg-blue-500 h-2 rounded-full"
                            style={{ width: `${Math.min(holding.percentage, 100)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-right">
                      {(() => {
                        const pnl = (holding as any).unrealized_pnl_usd || 0
                        const pnlPct = (holding as any).unrealized_pnl_percentage || 0
                        const isPositive = pnl > 0
                        const isNegative = pnl < 0
                        const colorClass = isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'

                        if (Math.abs(pnl) < 0.01) {
                          return <span className="text-slate-500">—</span>
                        }

                        return (
                          <div className="flex flex-col items-end">
                            <span className={`font-medium ${colorClass}`}>
                              {isPositive ? '+' : ''}{formatCurrency(pnl)}
                            </span>
                            <span className={`text-xs ${colorClass}`}>
                              {isPositive ? '+' : ''}{pnlPct.toFixed(2)}%
                            </span>
                          </div>
                        )
                      })()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {sortedHoldings.length === 0 && (
            <div className="p-8 text-center text-slate-400">
              No holdings found in your portfolio
            </div>
          )}
        </div>
      </div>

      {/* Chart Modal */}
      {chartModalAsset && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg w-full max-w-4xl max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-slate-800 border-b border-slate-700 p-4 flex items-center justify-between z-10">
              <div>
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <BarChart3 size={24} className="text-blue-400" />
                  {chartModalAsset} Chart
                </h2>
              </div>
              <button
                onClick={closeChartModal}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X size={24} />
              </button>
            </div>

            <div className="p-4 space-y-4">
              {/* Pair Type Selector */}
              <div className="flex items-center gap-3 flex-wrap">
                <div className="flex gap-1">
                  <button
                    onClick={() => setChartPairType('USD')}
                    className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                      chartPairType === 'USD'
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    {chartModalAsset}/USD
                  </button>
                  <button
                    onClick={() => setChartPairType('BTC')}
                    className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                      chartPairType === 'BTC'
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    {chartModalAsset}/BTC
                  </button>
                </div>

                <div className="w-px h-6 bg-slate-600" />

                {/* Timeframe Selector */}
                <div className="flex gap-1">
                  {['FIVE_MINUTE', 'FIFTEEN_MINUTE', 'THIRTY_MINUTE', 'ONE_HOUR', 'ONE_DAY'].map((tf) => {
                    const label = {
                      'FIVE_MINUTE': '5m',
                      'FIFTEEN_MINUTE': '15m',
                      'THIRTY_MINUTE': '30m',
                      'ONE_HOUR': '1h',
                      'ONE_DAY': '1d'
                    }[tf]
                    return (
                      <button
                        key={tf}
                        onClick={() => setChartTimeframe(tf)}
                        className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                          chartTimeframe === tf
                            ? 'bg-blue-600 text-white'
                            : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                        }`}
                      >
                        {label}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Chart */}
              <div className="bg-slate-900 rounded-lg p-4">
                {chartLoading && (
                  <div className="text-center py-8">
                    <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-500 border-r-transparent"></div>
                    <p className="mt-2 text-slate-400">Loading chart data...</p>
                  </div>
                )}

                {chartError && (
                  <div className="bg-red-500/10 border border-red-500 rounded p-4 text-red-400">
                    {chartError}
                  </div>
                )}

                <div
                  ref={chartContainerRef}
                  className={chartLoading || chartError ? 'hidden' : ''}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Portfolio
