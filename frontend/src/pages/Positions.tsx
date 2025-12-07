import { useQuery } from '@tanstack/react-query'
import { positionsApi, botsApi } from '../services/api'
import { useState, useEffect } from 'react'
import { formatDateTime, formatDateTimeCompact } from '../utils/dateFormat'
import {
  X,
  AlertCircle,
  BarChart3,
  BarChart2,
  Settings,
  Building2,
  Wallet
} from 'lucide-react'
import { useAccount, getChainName } from '../contexts/AccountContext'
import axios from 'axios'
import type { Position } from '../types'
import { API_BASE_URL } from '../config/api'
import PositionLogsModal from '../components/PositionLogsModal'
import TradingViewChartModal from '../components/TradingViewChartModal'
import LightweightChartModal from '../components/LightweightChartModal'
import { LimitCloseModal } from '../components/LimitCloseModal'
import { SlippageWarningModal } from '../components/SlippageWarningModal'
import { EditPositionSettingsModal } from '../components/EditPositionSettingsModal'
import { AddFundsModal } from '../components/AddFundsModal'
import CoinIcon from '../components/CoinIcon'
import {
  getQuoteCurrency,
  formatPrice,
  formatBaseAmount,
  formatQuoteAmount,
  AISentimentIcon,
  DealChart,
} from '../components/positions'


export default function Positions() {
  const { selectedAccount } = useAccount()
  const [selectedPosition, setSelectedPosition] = useState<number | null>(null)
  const [showAddFundsModal, setShowAddFundsModal] = useState(false)
  const [addFundsPosition, setAddFundsPosition] = useState<Position | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({})
  const [showLogsModal, setShowLogsModal] = useState(false)
  const [logsModalPosition, setLogsModalPosition] = useState<Position | null>(null)
  const [showChartModal, setShowChartModal] = useState(false)
  const [chartModalSymbol, setChartModalSymbol] = useState<string>('')
  const [chartModalPosition, setChartModalPosition] = useState<Position | null>(null)
  const [showLightweightChart, setShowLightweightChart] = useState(false)
  const [lightweightChartSymbol, setLightweightChartSymbol] = useState<string>('')
  const [lightweightChartPosition, setLightweightChartPosition] = useState<Position | null>(null)
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)
  const [closeConfirmPositionId, setCloseConfirmPositionId] = useState<number | null>(null)
  const [showLimitCloseModal, setShowLimitCloseModal] = useState(false)
  const [limitClosePosition, setLimitClosePosition] = useState<Position | null>(null)
  const [showSlippageWarning, setShowSlippageWarning] = useState(false)
  const [slippageData, setSlippageData] = useState<any>(null)
  const [pendingMarketClosePositionId, setPendingMarketClosePositionId] = useState<number | null>(null)
  const [showNotesModal, setShowNotesModal] = useState(false)
  const [editingNotesPositionId, setEditingNotesPositionId] = useState<number | null>(null)
  const [notesText, setNotesText] = useState('')
  const [showEditSettingsModal, setShowEditSettingsModal] = useState(false)
  const [editSettingsPosition, setEditSettingsPosition] = useState<Position | null>(null)

  // Filtering and sorting state (like 3Commas)
  const [filterBot, setFilterBot] = useState<number | 'all'>('all')
  const [filterMarket, setFilterMarket] = useState<'all' | 'USD' | 'BTC'>('all')
  const [filterPair, setFilterPair] = useState<string>('all')
  const [sortBy, setSortBy] = useState<'created' | 'pnl' | 'invested' | 'pair' | 'bot'>('created')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  const { data: allPositions, refetch: refetchPositions } = useQuery({
    queryKey: ['positions', selectedAccount?.id],
    queryFn: () => positionsApi.getAll(undefined, 100),
    refetchInterval: 5000, // Update every 5 seconds for active deals
    select: (data) => {
      if (!selectedAccount) return data
      // Filter by account_id
      return data.filter((p: Position) => p.account_id === selectedAccount.id)
    },
  })

  // Fetch all bots to display bot names (filtered by account)
  const { data: bots } = useQuery({
    queryKey: ['bots', selectedAccount?.id],
    queryFn: botsApi.getAll,
    refetchInterval: 10000,
    select: (data) => {
      if (!selectedAccount) return data
      // Filter by account_id
      return data.filter((bot: any) => bot.account_id === selectedAccount.id)
    },
  })

  // Fetch portfolio for BTC/USD price (account-specific)
  const { data: portfolio } = useQuery({
    queryKey: ['account-portfolio', selectedAccount?.id],
    queryFn: async () => {
      if (selectedAccount) {
        const response = await fetch(`/api/accounts/${selectedAccount.id}/portfolio`)
        if (!response.ok) throw new Error('Failed to fetch portfolio')
        return response.json()
      }
      const response = await fetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 120000,
    staleTime: 60000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })

  const totalBtcValue = portfolio?.total_btc_value || 0
  const totalUsdValue = portfolio?.total_usd_value || 0
  const btcUsdPrice = totalBtcValue > 0 ? totalUsdValue / totalBtcValue : 0

  // Fetch real-time prices for all open positions
  useEffect(() => {
    const abortController = new AbortController()

    const fetchPrices = async () => {
      if (!allPositions) return

      const openPositions = allPositions.filter(p => p.status === 'open')
      if (openPositions.length === 0) return

      try {
        // Fetch all prices in a single batch request
        const productIds = openPositions.map(p => p.product_id || 'ETH-BTC').join(',')
        const response = await axios.get(`${API_BASE_URL}/api/prices/batch`, {
          params: { products: productIds },
          signal: abortController.signal
        })

        const priceMap = response.data.prices || {}

        // Fill in fallback prices for positions that didn't get a price
        openPositions.forEach(position => {
          const productId = position.product_id || 'ETH-BTC'
          if (!priceMap[productId]) {
            priceMap[productId] = position.average_buy_price
          }
        })

        setCurrentPrices(priceMap)
      } catch (err) {
        // Ignore abort errors (they're expected when component unmounts)
        if (axios.isCancel(err) || (err as any)?.code === 'ECONNABORTED') {
          return
        }
        console.error('Error fetching batch prices:', err)

        // Fallback to using average buy prices
        const fallbackPrices: Record<string, number> = {}
        openPositions.forEach(position => {
          const productId = position.product_id || 'ETH-BTC'
          fallbackPrices[productId] = position.average_buy_price
        })
        setCurrentPrices(fallbackPrices)
      }
    }

    fetchPrices()
    const interval = setInterval(fetchPrices, 5000) // Update every 5 seconds

    return () => {
      clearInterval(interval)
      abortController.abort() // Cancel any in-flight requests
    }
  }, [allPositions])

  const { data: trades } = useQuery({
    queryKey: ['position-trades', selectedPosition],
    queryFn: () => positionsApi.getTrades(selectedPosition!),
    enabled: selectedPosition !== null,
  })

  // Calculate unrealized P&L for open position (needed for sorting)
  const calculateUnrealizedPnL = (position: Position, currentPrice?: number) => {
    if (position.status !== 'open') return null

    // Use real-time price if available, otherwise fall back to average buy price
    const price = currentPrice || position.average_buy_price
    const currentValue = position.total_base_acquired * price
    const costBasis = position.total_quote_spent
    const unrealizedPnL = currentValue - costBasis

    // Prevent division by zero for new positions with no trades yet
    const unrealizedPnLPercent = costBasis > 0 ? (unrealizedPnL / costBasis) * 100 : 0

    return {
      btc: unrealizedPnL,
      percent: unrealizedPnLPercent,
      usd: unrealizedPnL * (position.btc_usd_price_at_open || 0),
      currentPrice: price
    }
  }

  // Apply filters and sorting (like 3Commas)
  const openPositions = allPositions?.filter(p => {
    if (p.status !== 'open') return false

    // Filter by bot
    if (filterBot !== 'all' && p.bot_id !== filterBot) return false

    // Filter by market (USD-based or BTC-based)
    if (filterMarket !== 'all') {
      const quoteCurrency = (p.product_id || 'ETH-BTC').split('-')[1]
      if (filterMarket === 'USD' && quoteCurrency !== 'USD') return false
      if (filterMarket === 'BTC' && quoteCurrency !== 'BTC') return false
    }

    // Filter by specific pair
    if (filterPair !== 'all' && p.product_id !== filterPair) return false

    return true
  }).sort((a, b) => {
    let aVal: any, bVal: any

    switch (sortBy) {
      case 'created':
        // For closed positions, sort by closed_at (most recent closure first)
        // For open positions, sort by opened_at
        aVal = a.status === 'closed' && a.closed_at
          ? new Date(a.closed_at).getTime()
          : new Date(a.opened_at).getTime()
        bVal = b.status === 'closed' && b.closed_at
          ? new Date(b.closed_at).getTime()
          : new Date(b.opened_at).getTime()
        break
      case 'pnl':
        const aPnl = calculateUnrealizedPnL(a, currentPrices[a.product_id || 'ETH-BTC'])?.percent || 0
        const bPnl = calculateUnrealizedPnL(b, currentPrices[b.product_id || 'ETH-BTC'])?.percent || 0
        aVal = aPnl
        bVal = bPnl
        break
      case 'invested':
        aVal = a.total_quote_spent
        bVal = b.total_quote_spent
        break
      case 'pair':
        aVal = a.product_id || 'ETH-BTC'
        bVal = b.product_id || 'ETH-BTC'
        break
      default:
        aVal = 0
        bVal = 0
    }

    if (sortOrder === 'asc') {
      return aVal > bVal ? 1 : -1
    } else {
      return aVal < bVal ? 1 : -1
    }
  }) || []

  // Get unique pairs for filter dropdown
  const uniquePairs = Array.from(new Set(allPositions?.filter(p => p.status === 'open').map(p => p.product_id || 'ETH-BTC') || []))

  const checkSlippageBeforeMarketClose = async (positionId: number) => {
    try {
      const response = await axios.get(`${import.meta.env.VITE_API_BASE_URL}/api/positions/${positionId}/slippage-check`)
      const slippage = response.data

      if (slippage.show_warning) {
        // Show slippage warning modal
        setSlippageData(slippage)
        setPendingMarketClosePositionId(positionId)
        setShowSlippageWarning(true)
      } else {
        // No significant slippage, proceed directly to close confirmation
        setCloseConfirmPositionId(positionId)
        setShowCloseConfirm(true)
      }
    } catch (err: any) {
      console.error('Error checking slippage:', err)
      // If slippage check fails, still allow closing (fallback)
      setCloseConfirmPositionId(positionId)
      setShowCloseConfirm(true)
    }
  }

  const handleClosePosition = async () => {
    if (!closeConfirmPositionId) return

    setIsProcessing(true)
    try {
      const result = await positionsApi.close(closeConfirmPositionId)
      setShowCloseConfirm(false)
      setCloseConfirmPositionId(null)
      // Refetch positions instead of full page reload
      refetchPositions()
      // Show success notification
      alert(`Position closed successfully!\nProfit: ${result.profit_quote.toFixed(8)} (${result.profit_percentage.toFixed(2)}%)`)
    } catch (err: any) {
      alert(`Error closing position: ${err.response?.data?.detail || err.message}`)
    } finally {
      setIsProcessing(false)
    }
  }

  const openAddFundsModal = (position: Position) => {
    setAddFundsPosition(position)
    setShowAddFundsModal(true)
  }

  const handleAddFundsSuccess = () => {
    refetchPositions()
    setShowAddFundsModal(false)
    setAddFundsPosition(null)
  }

  const openNotesModal = (position: Position) => {
    setEditingNotesPositionId(position.id)
    setNotesText(position.notes || '')
    setShowNotesModal(true)
  }

  const handleSaveNotes = async () => {
    if (!editingNotesPositionId) return

    setIsProcessing(true)
    try {
      await axios.patch(`${API_BASE_URL}/api/positions/${editingNotesPositionId}/notes`, {
        notes: notesText
      })
      setShowNotesModal(false)
      setEditingNotesPositionId(null)
      setNotesText('')
      // Refetch positions to show updated notes
      refetchPositions()
    } catch (err: any) {
      alert(`Error saving notes: ${err.response?.data?.detail || err.message}`)
    } finally {
      setIsProcessing(false)
    }
  }

  const togglePosition = (positionId: number) => {
    if (selectedPosition === positionId) {
      setSelectedPosition(null)
    } else {
      setSelectedPosition(positionId)
    }
  }

  // Calculate overall statistics
  const calculateOverallStats = () => {
    const totalFundsLocked = openPositions.reduce((sum, pos) => sum + pos.total_quote_spent, 0)
    const totalUPnL = openPositions.reduce((sum, pos) => {
      const currentPrice = currentPrices[pos.product_id || 'ETH-BTC']
      const pnl = calculateUnrealizedPnL(pos, currentPrice)
      return sum + (pnl?.btc || 0)
    }, 0)
    const totalUPnLUSD = openPositions.reduce((sum, pos) => {
      const currentPrice = currentPrices[pos.product_id || 'ETH-BTC']
      const pnl = calculateUnrealizedPnL(pos, currentPrice)
      return sum + (pnl?.usd || 0)
    }, 0)

    return {
      activeTrades: openPositions.length,
      fundsLocked: totalFundsLocked,
      uPnL: totalUPnL,
      uPnLUSD: totalUPnLUSD
    }
  }

  const stats = calculateOverallStats()

  return (
    <div className="space-y-6">
      {/* Active Deals Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            {selectedAccount?.type === 'dex' ? (
              <Wallet className="w-8 h-8 text-orange-400" />
            ) : (
              <Building2 className="w-8 h-8 text-blue-400" />
            )}
            <div>
              <h2 className="text-3xl font-bold text-white">Active Deals</h2>
              {selectedAccount && (
                <p className="text-sm text-slate-400">
                  <span className="text-slate-300">{selectedAccount.name}</span>
                  {selectedAccount.type === 'dex' && selectedAccount.chain_id && (
                    <span className="text-slate-500"> ({getChainName(selectedAccount.chain_id)})</span>
                  )}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="bg-green-500/20 text-green-400 px-3 py-1 rounded-full text-sm font-medium">
              {openPositions.length} Active
            </div>
          </div>
        </div>

        {/* Overall Stats Panel - 3Commas Style */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 mb-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Overall Stats */}
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-3">Overall stats</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-400">Active trades:</span>
                  <span className="text-white font-medium">{stats.activeTrades}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Funds locked in DCA bot trades:</span>
                  <span className="text-white font-medium">{stats.fundsLocked.toFixed(8)} BTC</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">uPnL of active Bot trades:</span>
                  <span className={`font-medium ${stats.uPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {stats.uPnL >= 0 ? '+' : ''}{stats.uPnL.toFixed(8)} BTC
                  </span>
                </div>
              </div>
            </div>

            {/* Completed Trades Profit (placeholder for now) */}
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-3">Completed trades profit</h3>
              <div className="space-y-2 text-sm">
                <div className="text-slate-400">Coming soon...</div>
              </div>
            </div>

            {/* Balances */}
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center justify-between">
                Balances
                <button className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
                  🔄 Refresh
                </button>
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between text-slate-400">
                  <span>Reserved</span>
                  <span>Available</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-300">BTC</span>
                  <div className="flex gap-4">
                    <span className="text-white">{stats.fundsLocked.toFixed(8)}</span>
                    <span className="text-white">-</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Filters - 3Commas Style (Account, Bot, Pair) */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 mb-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-300">Filters</h3>
            <button
              onClick={() => {
                setFilterBot('all')
                setFilterMarket('all')
                setFilterPair('all')
              }}
              className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded transition-colors flex items-center gap-2"
            >
              <X className="w-4 h-4" />
              Clear
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Account Filter (Market in our case) */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Account</label>
              <select
                value={filterMarket}
                onChange={(e) => setFilterMarket(e.target.value as 'all' | 'USD' | 'BTC')}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="all">All</option>
                <option value="USD">USD Markets</option>
                <option value="BTC">BTC Markets</option>
              </select>
            </div>

            {/* Bot Filter */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Bot</label>
              <select
                value={filterBot}
                onChange={(e) => setFilterBot(e.target.value === 'all' ? 'all' : parseInt(e.target.value))}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="all">All</option>
                {bots?.map(bot => (
                  <option key={bot.id} value={bot.id}>{bot.name}</option>
                ))}
              </select>
            </div>

            {/* Pair Filter */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Pair</label>
              <select
                value={filterPair}
                onChange={(e) => setFilterPair(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="all">All</option>
                {uniquePairs.map(pair => (
                  <option key={pair} value={pair}>{pair}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {openPositions.length === 0 ? (
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-12 text-center">
            <BarChart3 className="w-16 h-16 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400 text-lg">No active deals</p>
            <p className="text-slate-500 text-sm mt-2">Start a bot to open new positions</p>
          </div>
        ) : (
          <div className="space-y-2">
            {/* Column Headers - 3Commas Style */}
            <div className="bg-slate-800/50 rounded-lg border border-slate-700/50 px-4 py-2">
              <div className="grid grid-cols-12 gap-4 items-center text-xs text-slate-400">
                <div
                  className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'bot') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('bot')
                      setSortOrder('asc')
                    }
                  }}
                >
                  <span>Bot</span>
                  {sortBy === 'bot' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'bot' && <span className="opacity-30">↕</span>}
                </div>
                <div
                  className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'pair') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('pair')
                      setSortOrder('asc')
                    }
                  }}
                >
                  <span>Pair</span>
                  {sortBy === 'pair' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'pair' && <span className="opacity-30">↕</span>}
                </div>
                <div
                  className="col-span-4 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'pnl') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('pnl')
                      setSortOrder('desc')
                    }
                  }}
                >
                  <span className="flex items-center gap-1">
                    <span className="w-4 h-4 rounded-full bg-slate-600 flex items-center justify-center text-[9px]">?</span>
                    uPnL
                  </span>
                  {sortBy === 'pnl' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'pnl' && <span className="opacity-30">↕</span>}
                </div>
                <div
                  className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'invested') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('invested')
                      setSortOrder('desc')
                    }
                  }}
                >
                  <span>Volume</span>
                  {sortBy === 'invested' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'invested' && <span className="opacity-30">↕</span>}
                </div>
                <div className="col-span-1 flex items-center gap-1 text-slate-500">
                  <span>Status</span>
                </div>
                <div
                  className="col-span-1 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'created') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('created')
                      setSortOrder('desc')
                    }
                  }}
                >
                  <span>Created</span>
                  {sortBy === 'created' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'created' && <span className="opacity-30">↕</span>}
                </div>
              </div>
            </div>

            {/* Group positions by bot */}
            {openPositions.map((position) => {
              const currentPrice = currentPrices[position.product_id || 'ETH-BTC']
              const pnl = calculateUnrealizedPnL(position, currentPrice)
              const fundsUsedPercent = (position.total_quote_spent / position.max_quote_allowed) * 100

              const bot = bots?.find(b => b.id === position.bot_id)
              const strategyConfig = position.strategy_config_snapshot || bot?.strategy_config || {}

              return (
                <div key={position.id} className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                  {/* Deal Row - 3Commas Style Horizontal Layout */}
                  <div
                    className="p-4 cursor-pointer hover:bg-slate-750 transition-colors"
                    onClick={() => togglePosition(position.id)}
                  >
                    <div className="grid grid-cols-12 gap-4 items-start text-sm">
                      {/* Column 1: Bot Info + Strategy (2 cols) */}
                      <div className="col-span-2">
                        <div className="text-white font-semibold mb-1">
                          {bot?.name || `Bot #${position.bot_id || 'N/A'}`}
                        </div>
                        <div className="text-[10px] text-slate-400 space-y-0.5">
                          {bot?.strategy_type && (
                            <div>[{bot.strategy_type.toUpperCase()}]</div>
                          )}
                          {strategyConfig.take_profit_percent && (
                            <div>MP: {strategyConfig.take_profit_percent}%</div>
                          )}
                          {strategyConfig.base_order_size && (
                            <div>BO: {strategyConfig.base_order_size}</div>
                          )}
                        </div>
                      </div>

                      {/* Column 2: Pair + Exchange (1.5 cols) */}
                      <div className="col-span-2 flex items-start gap-2">
                        <CoinIcon
                          symbol={position.product_id?.split('-')[0] || 'BTC'}
                          size="sm"
                        />
                        <div className="flex-1">
                          <div className="flex items-center gap-1.5">
                            <span
                              className="text-white font-semibold cursor-pointer hover:opacity-80 transition-opacity"
                              onClick={() => {
                                setChartModalSymbol(position.product_id || 'ETH-BTC')
                                setChartModalPosition(position)
                                setShowChartModal(true)
                              }}
                            >
                              {position.product_id || 'ETH-BTC'}
                            </span>
                            <BarChart2
                              size={14}
                              className="text-slate-400 hover:text-blue-400 cursor-pointer transition-colors"
                              onClick={() => {
                                setLightweightChartSymbol(position.product_id || 'ETH-BTC')
                                setLightweightChartPosition(position)
                                setShowLightweightChart(true)
                              }}
                            />
                            {/* AI Sentiment Indicator */}
                            {position.bot_id && (
                              <AISentimentIcon
                                botId={position.bot_id}
                                productId={position.product_id || 'ETH-BTC'}
                              />
                            )}
                            {/* Error Indicator (like 3Commas) */}
                            {position.last_error_message && (
                              <div
                                className="flex items-center cursor-help"
                                title={`Error: ${position.last_error_message}\n${position.last_error_timestamp ? `Time: ${formatDateTime(position.last_error_timestamp)}` : ''}`}
                              >
                                <AlertCircle size={14} className="text-red-400" />
                              </div>
                            )}
                            {/* Coin Status Badge - different colors by category */}
                            {position.is_blacklisted && (() => {
                              const reason = position.blacklist_reason || '';
                              const isApproved = reason.startsWith('[APPROVED]');
                              const isBorderline = reason.startsWith('[BORDERLINE]');
                              const isQuestionable = reason.startsWith('[QUESTIONABLE]');
                              const displayReason = reason.replace(/^\[(APPROVED|BORDERLINE|QUESTIONABLE)\]\s*/, '');

                              if (isApproved) {
                                return (
                                  <span
                                    className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-600/20 border border-green-600/50 text-green-400 cursor-help"
                                    title={displayReason || 'Approved coin'}
                                  >
                                    APPROVED
                                  </span>
                                );
                              } else if (isBorderline) {
                                return (
                                  <span
                                    className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-yellow-600/20 border border-yellow-600/50 text-yellow-400 cursor-help"
                                    title={displayReason || 'Borderline coin'}
                                  >
                                    BORDERLINE
                                  </span>
                                );
                              } else if (isQuestionable) {
                                return (
                                  <span
                                    className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-orange-600/20 border border-orange-600/50 text-orange-400 cursor-help"
                                    title={displayReason || 'Questionable coin'}
                                  >
                                    QUESTIONABLE
                                  </span>
                                );
                              } else {
                                return (
                                  <span
                                    className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-600/20 border border-red-600/50 text-red-400 cursor-help"
                                    title={reason || 'Blacklisted coin'}
                                  >
                                    BLACKLISTED
                                  </span>
                                );
                              }
                            })()}
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="text-[10px] text-slate-400">My Coinbase Advanced</div>
                            {/* Limit Close Status Badge */}
                            {position.closing_via_limit && position.limit_order_details && (
                              <div className="bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded text-[10px] font-medium">
                                Limit Close {position.limit_order_details.fill_percentage > 0 ? `${position.limit_order_details.fill_percentage.toFixed(0)}%` : 'Pending'}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Column 3: uPnL + Price Bar (4 cols) */}
                      <div className="col-span-4">
                        {pnl && (
                          <div>
                            <div className="mb-1">
                              <span className="text-[10px] text-blue-400">Filled {fundsUsedPercent.toFixed(2)}%</span>
                            </div>
                            {/* Price Bar - 3Commas Style */}
                            <div className="relative w-full pt-6 pb-6">
                              <div className="relative w-full h-2 bg-slate-700 rounded-full">
                                {(() => {
                                  const entryPrice = position.average_buy_price

                                  // Don't render price markers for new positions with no fills yet
                                  if (!entryPrice || entryPrice === 0) {
                                    return null
                                  }

                                  const currentPriceValue = pnl.currentPrice
                                  // Use bot's min_profit_percentage setting instead of hardcoded 2%
                                  const minProfitPercent = strategyConfig.min_profit_percentage || 1.5
                                  const targetPrice = entryPrice * (1 + minProfitPercent / 100)

                                  // Calculate next DCA level if manual DCA targets are configured
                                  // This extends the bar range to show where the next DCA would trigger
                                  const minPriceDropForDCA = strategyConfig.min_price_drop_for_dca
                                  const maxDCAOrders = strategyConfig.max_safety_orders || 3
                                  const completedDCAs = Math.max(0, (position.trade_count || 0) - 1)
                                  const nextDCA = completedDCAs + 1
                                  let nextDCAPrice: number | null = null
                                  if (minPriceDropForDCA && position.status === 'open' && nextDCA <= maxDCAOrders) {
                                    const dropPercentage = minPriceDropForDCA * nextDCA
                                    nextDCAPrice = entryPrice * (1 - dropPercentage / 100)
                                  }

                                  const defaultMin = entryPrice * 0.95
                                  const defaultMax = entryPrice * 1.05
                                  // Include next DCA price in range calculation so it's always visible
                                  const minPrice = nextDCAPrice
                                    ? Math.min(defaultMin, currentPriceValue * 0.98, nextDCAPrice * 0.98)
                                    : Math.min(defaultMin, currentPriceValue * 0.98)
                                  const maxPrice = Math.max(defaultMax, targetPrice * 1.01, currentPriceValue * 1.02)
                                  const priceRange = maxPrice - minPrice

                                  const entryPosition = ((entryPrice - minPrice) / priceRange) * 100
                                  const currentPosition = ((currentPriceValue - minPrice) / priceRange) * 100
                                  const targetPosition = ((targetPrice - minPrice) / priceRange) * 100

                                  const isProfit = currentPriceValue >= entryPrice
                                  const fillStart = Math.min(entryPosition, currentPosition)
                                  const fillWidth = Math.abs(currentPosition - entryPosition)

                                  // Collision detection - if labels are too close (< 15%), stagger them
                                  const buyCurrentGap = Math.abs(currentPosition - entryPosition)
                                  const currentTargetGap = Math.abs(targetPosition - currentPosition)
                                  const buyTargetGap = Math.abs(targetPosition - entryPosition)

                                  // Determine positioning: top or bottom
                                  let buyPos = 'top'
                                  let currentPos = 'top'
                                  let targetPos = 'top'

                                  // If buy and current are close, put current below
                                  if (buyCurrentGap < 15) {
                                    currentPos = 'bottom'
                                  }

                                  // If current and target are close, alternate
                                  if (currentTargetGap < 15) {
                                    if (currentPos === 'top') {
                                      targetPos = 'bottom'
                                    } else {
                                      targetPos = 'top'
                                    }
                                  }

                                  // If buy and target are close but current is far, alternate them
                                  if (buyTargetGap < 15 && buyCurrentGap >= 15 && currentTargetGap >= 15) {
                                    targetPos = 'bottom'
                                  }

                                  return (
                                    <>
                                      {/* Fill color between entry and current */}
                                      <div
                                        className={`absolute h-full rounded-full ${isProfit ? 'bg-green-500' : 'bg-red-500'}`}
                                        style={{
                                          left: `${Math.max(0, Math.min(100, fillStart))}%`,
                                          width: `${Math.max(0, Math.min(100 - fillStart, fillWidth))}%`
                                        }}
                                      />

                                      {/* Buy Price */}
                                      <div
                                        className="absolute flex flex-col items-center"
                                        style={{
                                          left: `${Math.max(0, Math.min(100, entryPosition))}%`,
                                          transform: 'translateX(-50%)',
                                          ...(buyPos === 'top' ? { bottom: '100%' } : { top: '100%' })
                                        }}
                                      >
                                        {buyPos === 'bottom' && <div className="w-px h-3 bg-slate-400" />}
                                        <div className={`text-[9px] text-slate-400 whitespace-nowrap ${buyPos === 'top' ? 'mb-0.5' : 'mt-0.5'}`}>
                                          Buy {formatPrice(entryPrice, position.product_id || 'ETH-BTC')}
                                        </div>
                                        {buyPos === 'top' && <div className="w-px h-3 bg-slate-400" />}
                                      </div>

                                      {/* Current Price */}
                                      <div
                                        className="absolute flex flex-col items-center"
                                        style={{
                                          left: `${Math.max(0, Math.min(100, currentPosition))}%`,
                                          transform: 'translateX(-50%)',
                                          ...(currentPos === 'top' ? { bottom: '100%' } : { top: '100%' })
                                        }}
                                      >
                                        {currentPos === 'bottom' && <div className={`w-px h-3 ${isProfit ? 'bg-green-400' : 'bg-red-400'}`} />}
                                        <div className={`text-[9px] whitespace-nowrap font-semibold ${isProfit ? 'text-green-400' : 'text-red-400'} ${currentPos === 'top' ? 'mb-0.5' : 'mt-0.5'}`}>
                                          {pnl.percent >= 0 ? '+' : ''}{pnl.percent.toFixed(2)}% {formatPrice(currentPriceValue, position.product_id || 'ETH-BTC')}
                                        </div>
                                        {currentPos === 'top' && <div className={`w-px h-3 ${isProfit ? 'bg-green-400' : 'bg-red-400'}`} />}
                                      </div>

                                      {/* Target Price (MP) */}
                                      <div
                                        className="absolute flex flex-col items-center"
                                        style={{
                                          left: `${Math.max(0, Math.min(100, targetPosition))}%`,
                                          transform: 'translateX(-50%)',
                                          ...(targetPos === 'top' ? { bottom: '100%' } : { top: '100%' })
                                        }}
                                      >
                                        {targetPos === 'bottom' && <div className="w-px h-3 bg-emerald-400" />}
                                        <div className={`text-[9px] text-emerald-400 whitespace-nowrap ${targetPos === 'top' ? 'mb-0.5' : 'mt-0.5'}`}>
                                          MP {formatPrice(targetPrice, position.product_id || 'ETH-BTC')}
                                        </div>
                                        {targetPos === 'top' && <div className="w-px h-3 bg-emerald-400" />}
                                      </div>

                                      {/* DCA Level Tick Mark (for bots with fixed DCA targets configured) */}
                                      {nextDCAPrice && (() => {
                                        const dcaBarPosition = ((nextDCAPrice - minPrice) / priceRange) * 100
                                        return (
                                          <div
                                            key={`dca-${nextDCA}`}
                                            className="absolute flex flex-col items-center"
                                            style={{
                                              left: `${Math.max(0, Math.min(100, dcaBarPosition))}%`,
                                              transform: 'translateX(-50%)',
                                              top: '100%'
                                            }}
                                          >
                                            <div className="w-px h-2 bg-purple-400" />
                                            <div className="text-[8px] text-purple-400 whitespace-nowrap mt-0.5">
                                              DCA{nextDCA}
                                            </div>
                                          </div>
                                        )
                                      })()}
                                    </>
                                  )
                                })()}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Column 4: Volume (2 cols) */}
                      <div className="col-span-2">
                        <div className="text-[10px] space-y-0.5">
                          <div className="text-white">
                            {formatQuoteAmount(position.total_quote_spent, position.product_id || 'ETH-BTC')}
                            {getQuoteCurrency(position.product_id || 'ETH-BTC').symbol === 'BTC' && btcUsdPrice > 0 && (
                              <span className="text-slate-400">
                                {' '}(${(position.total_quote_spent * btcUsdPrice).toLocaleString(undefined, { maximumFractionDigits: 2 })})
                              </span>
                            )}
                          </div>
                          <div className="text-slate-400">{formatBaseAmount(position.total_base_acquired, position.product_id || 'ETH-BTC')}</div>
                          {pnl && pnl.usd !== undefined && (
                            <div className={pnl.btc >= 0 ? 'text-green-400' : 'text-red-400'}>
                              {pnl.btc >= 0 ? '+' : ''}${Math.abs(pnl.usd).toFixed(2)}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Column 5: Avg. O (Averaging Orders) - Like 3Commas (1 col) */}
                      <div className="col-span-1">
                        <div className="text-[10px] space-y-0.5">
                          <div className="text-slate-400">
                            Completed: {(() => {
                              // Calculate DCA count from trade_count (total trades - 1 initial = DCA count)
                              // If trades array is available AND has trades for THIS position, use it for more detail
                              if (trades && trades.length > 0) {
                                const positionTrades = trades.filter(t => t.position_id === position.id && t.side === 'buy') || []
                                // Only use trades array if it actually has trades for this position
                                // Otherwise the trades are for a different selected position
                                if (positionTrades.length > 0) {
                                  const autoSO = positionTrades.filter(t => t.trade_type === 'dca').length
                                  const manualSO = positionTrades.filter(t => t.trade_type === 'manual_safety_order').length

                                  if (manualSO > 0) {
                                    return `${autoSO} (+${manualSO})`
                                  }
                                  return autoSO
                                }
                              }

                              // Fallback: use trade_count from position (trade_count - 1 = DCA count)
                              const dcaCount = Math.max(0, (position.trade_count || 0) - 1)
                              return dcaCount
                            })()}
                          </div>
                          <div className="text-slate-400">Active: {position.pending_orders_count || 0}</div>
                          <div className="text-slate-400">
                            Max: {position.strategy_config_snapshot?.max_safety_orders ?? bot?.strategy_config?.max_safety_orders ?? 0}
                          </div>
                        </div>
                      </div>

                      {/* Column 6: Created (1 col) */}
                      <div className="col-span-1">
                        <div className="text-[10px] space-y-0.5">
                          <div className="text-slate-400">Deal #{position.user_deal_number ?? position.id}</div>
                          <div className="text-slate-400">Start: {formatDateTimeCompact(position.opened_at)}</div>
                        </div>
                      </div>
                    </div>

                    {/* Our Special "Better than 3Commas" Budget Usage Bar */}
                    <div className="mt-3 px-4">
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="text-slate-400">Budget Used</span>
                        <span className="text-slate-300">
                          {formatQuoteAmount(position.total_quote_spent, position.product_id || 'ETH-BTC')} / {formatQuoteAmount(position.max_quote_allowed, position.product_id || 'ETH-BTC')}
                          <span className="text-slate-400 ml-1">({fundsUsedPercent.toFixed(0)}%)</span>
                        </span>
                      </div>
                      <div className="w-full bg-slate-700 rounded-full h-2">
                        <div
                          className="bg-blue-500 h-2 rounded-full transition-all"
                          style={{ width: `${Math.min(fundsUsedPercent, 100)}%` }}
                        />
                      </div>
                    </div>

                    {/* Action Buttons Row */}
                    <div className="mt-3 px-4 flex items-center gap-3">
                      <button
                        className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedPosition(null)
                        }}
                      >
                        <span>🚫</span> Cancel
                      </button>

                      {/* Show edit/cancel if there's a pending limit order */}
                      {position.closing_via_limit ? (
                        <>
                          <button
                            className="text-xs text-yellow-400 hover:text-yellow-300 flex items-center gap-1"
                            onClick={(e) => {
                              e.stopPropagation()
                              setLimitClosePosition(position)
                              setShowLimitCloseModal(true)
                            }}
                          >
                            <span>✏️</span> Edit limit price
                          </button>
                          <button
                            className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
                            onClick={async (e) => {
                              e.stopPropagation()
                              if (confirm('Cancel limit close order?')) {
                                try {
                                  await axios.post(`${API_BASE_URL}/api/positions/${position.id}/cancel-limit-close`)
                                  refetchPositions()
                                } catch (err: any) {
                                  alert(`Error: ${err.response?.data?.detail || err.message}`)
                                }
                              }
                            }}
                          >
                            <span>❌</span> Cancel limit order
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                            onClick={(e) => {
                              e.stopPropagation()
                              checkSlippageBeforeMarketClose(position.id)
                            }}
                          >
                            <span>💱</span> Close at market
                          </button>
                          <button
                            className="text-xs text-green-400 hover:text-green-300 flex items-center gap-1"
                            onClick={(e) => {
                              e.stopPropagation()
                              setLimitClosePosition(position)
                              setShowLimitCloseModal(true)
                            }}
                          >
                            <span>📊</span> Close at limit
                          </button>
                        </>
                      )}
                      <button
                        className="text-xs text-slate-400 hover:text-slate-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          setShowLogsModal(true)
                          setLogsModalPosition(position)
                        }}
                      >
                        <span>📊</span> AI Reasoning
                      </button>
                      <button
                        className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          openAddFundsModal(position)
                        }}
                      >
                        <span>💰</span> Add funds
                      </button>
                      <button
                        className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          setEditSettingsPosition(position)
                          setShowEditSettingsModal(true)
                        }}
                      >
                        <Settings size={12} /> Edit deal
                      </button>
                      <button
                        className="text-xs text-slate-400 hover:text-slate-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          refetchPositions()
                        }}
                      >
                        <span>🔄</span> Refresh
                      </button>
                    </div>

                    {/* Notes Section (like 3Commas) */}
                    <div className="mt-3 px-4 pb-3">
                      <div
                        className="text-xs flex items-center gap-2 cursor-pointer hover:opacity-70 transition-opacity"
                        onClick={(e) => {
                          e.stopPropagation()
                          openNotesModal(position)
                        }}
                      >
                        <span>📝</span>
                        {position.notes ? (
                          <span className="text-slate-300">{position.notes}</span>
                        ) : (
                          <span className="text-slate-500 italic">You can place a note here</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Expandable Details Section (keep existing chart/details) */}
                  {selectedPosition === position.id && (
                    <div className="border-t border-slate-700 bg-slate-900/50 p-6">
                      <DealChart
                        position={position}
                        productId={position.product_id || "ETH-BTC"}
                        currentPrice={currentPrice}
                        trades={trades}
                      />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Close Position Confirmation Modal */}
      {showCloseConfirm && closeConfirmPositionId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg w-full max-w-md p-6">
            <h2 className="text-xl font-bold mb-4 text-red-400 flex items-center gap-2">
              <span>⚠️</span> Close Position at Market Price
            </h2>

            <p className="text-slate-300 mb-4">
              This will immediately sell the entire position at the current market price.
            </p>

            <p className="text-slate-400 text-sm mb-6">
              <strong>Warning:</strong> This action cannot be undone. The position will be closed and profits/losses will be realized.
            </p>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowCloseConfirm(false)
                  setCloseConfirmPositionId(null)
                }}
                className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
                disabled={isProcessing}
              >
                Cancel
              </button>
              <button
                onClick={handleClosePosition}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg font-semibold transition-colors"
                disabled={isProcessing}
              >
                {isProcessing ? 'Closing...' : 'Close Position'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Funds Modal */}
      {addFundsPosition && (
        <AddFundsModal
          position={addFundsPosition}
          isOpen={showAddFundsModal}
          onClose={() => {
            setShowAddFundsModal(false)
            setAddFundsPosition(null)
          }}
          onSuccess={handleAddFundsSuccess}
        />
      )}

      {/* Position AI Logs Modal */}
      {logsModalPosition && (
        <PositionLogsModal
          botId={logsModalPosition.bot_id || 0}
          productId={logsModalPosition.product_id || 'ETH-BTC'}
          positionOpenedAt={logsModalPosition.opened_at}
          isOpen={showLogsModal}
          onClose={() => {
            setShowLogsModal(false)
            setLogsModalPosition(null)
          }}
        />
      )}

      {/* TradingView Chart Modal */}
      <TradingViewChartModal
        isOpen={showChartModal}
        onClose={() => setShowChartModal(false)}
        symbol={chartModalSymbol}
        position={chartModalPosition}
      />

      {/* Lightweight Chart Modal */}
      <LightweightChartModal
        isOpen={showLightweightChart}
        onClose={() => setShowLightweightChart(false)}
        symbol={lightweightChartSymbol}
        position={lightweightChartPosition}
      />

      {/* Notes Modal (like 3Commas) */}
      {showNotesModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg w-full max-w-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold text-white">Edit Note</h3>
              <button
                onClick={() => setShowNotesModal(false)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X size={24} />
              </button>
            </div>

            <div className="mb-4">
              <textarea
                value={notesText}
                onChange={(e) => setNotesText(e.target.value)}
                onKeyDown={(e) => {
                  // Save on Cmd+Enter or Ctrl+Enter
                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                    handleSaveNotes()
                  }
                }}
                className="w-full bg-slate-700 border border-slate-600 rounded px-2 sm:px-4 py-2 sm:py-3 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[120px] resize-y"
                placeholder="Add a note for this position..."
                autoFocus
                disabled={isProcessing}
              />
              <p className="text-xs text-slate-400 mt-2">Cmd + Enter to save</p>
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowNotesModal(false)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors"
                disabled={isProcessing}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveNotes}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
                disabled={isProcessing}
              >
                <span>✓</span> Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Limit Close Modal */}
      {showLimitCloseModal && limitClosePosition && (
        <LimitCloseModal
          positionId={limitClosePosition.id}
          productId={limitClosePosition.product_id || 'ETH-BTC'}
          totalAmount={limitClosePosition.total_base_acquired}
          quoteCurrency={limitClosePosition.product_id?.split('-')[1] || 'BTC'}
          isEditing={limitClosePosition.closing_via_limit}
          currentLimitPrice={limitClosePosition.limit_order_details?.limit_price}
          onClose={() => {
            setShowLimitCloseModal(false)
            setLimitClosePosition(null)
          }}
          onSuccess={() => {
            refetchPositions()
          }}
        />
      )}

      {showSlippageWarning && slippageData && pendingMarketClosePositionId && (
        <SlippageWarningModal
          positionId={pendingMarketClosePositionId}
          productId={slippageData.product_id}
          slippageData={slippageData}
          quoteCurrency={slippageData.product_id?.split('-')[1] || 'BTC'}
          onClose={() => {
            setShowSlippageWarning(false)
            setSlippageData(null)
            setPendingMarketClosePositionId(null)
          }}
          onProceedWithMarket={() => {
            setShowSlippageWarning(false)
            setCloseConfirmPositionId(pendingMarketClosePositionId)
            setShowCloseConfirm(true)
            setPendingMarketClosePositionId(null)
          }}
          onSwitchToLimit={() => {
            setShowSlippageWarning(false)
            const position = allPositions?.find(p => p.id === pendingMarketClosePositionId)
            if (position) {
              setLimitClosePosition(position)
              setShowLimitCloseModal(true)
            }
            setPendingMarketClosePositionId(null)
          }}
        />
      )}

      {/* Edit Position Settings Modal */}
      {showEditSettingsModal && editSettingsPosition && (
        <EditPositionSettingsModal
          position={editSettingsPosition}
          onClose={() => {
            setShowEditSettingsModal(false)
            setEditSettingsPosition(null)
          }}
          onSuccess={() => {
            refetchPositions()
          }}
        />
      )}
    </div>
  )
}
