import { useQuery } from '@tanstack/react-query'
import { positionsApi, botsApi, orderHistoryApi } from '../services/api'
import { TrendingUp, TrendingDown, AlertTriangle, ChevronDown, ChevronUp, Building2, Wallet, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Filter } from 'lucide-react'
import { useState, useEffect, useMemo } from 'react'
import type { Trade, AIBotLog, Position, Bot } from '../types'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { formatDateTime } from '../utils/dateFormat'
import { useAccount, getChainName } from '../contexts/AccountContext'
import { useAuth } from '../contexts/AuthContext'
import { FilterPanel } from './positions/components/FilterPanel'

function ClosedPositions() {
  const { selectedAccount } = useAccount()
  const { getAccessToken } = useAuth()
  const [activeTab, setActiveTab] = useState<'closed' | 'failed'>('closed')
  const [expandedPositionId, setExpandedPositionId] = useState<number | null>(null)
  const [positionTrades, setPositionTrades] = useState<Record<number, Trade[]>>({})
  const [positionAILogs, setPositionAILogs] = useState<Record<number, AIBotLog[]>>({})

  // Filter state
  const [filterBot, setFilterBot] = useState<number | 'all'>('all')
  const [filterMarket, setFilterMarket] = useState<'all' | 'USD' | 'BTC'>('all')
  const [filterPair, setFilterPair] = useState<string>('all')
  const [showFilters, setShowFilters] = useState(false)

  // Pagination state
  const [failedPage, setFailedPage] = useState(1)
  const [closedPage, setClosedPage] = useState(1)
  const pageSize = 25

  // Track last seen counts separately for closed and failed (server-synced)
  const [lastSeenClosedCount, setLastSeenClosedCount] = useState<number>(0)
  const [lastSeenFailedCount, setLastSeenFailedCount] = useState<number>(0)
  const [currentBtcUsdPrice, setCurrentBtcUsdPrice] = useState<number>(0)

  // Fetch initial counts from server on mount
  useEffect(() => {
    const fetchLastSeenCounts = async () => {
      const token = getAccessToken()
      if (!token) return

      try {
        const response = await fetch('/api/auth/preferences/last-seen-history', {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (response.ok) {
          const data = await response.json()
          setLastSeenClosedCount(data.last_seen_history_count || 0)
          setLastSeenFailedCount(data.last_seen_failed_count || 0)
        }
      } catch (error) {
        console.error('Failed to fetch last seen counts:', error)
      }
    }

    fetchLastSeenCounts()
  }, [getAccessToken])

  // Fetch current BTC/USD price for "today's USD" calculation
  useEffect(() => {
    const fetchBtcPrice = async () => {
      try {
        const response = await fetch('/api/market/btc-usd-price')
        if (response.ok) {
          const data = await response.json()
          setCurrentBtcUsdPrice(data.price || 0)
        }
      } catch (error) {
        console.error('Failed to fetch BTC/USD price:', error)
      }
    }

    fetchBtcPrice()
    // Refresh every 60 seconds
    const interval = setInterval(fetchBtcPrice, 60000)
    return () => clearInterval(interval)
  }, [])

  const { data: bots } = useQuery({
    queryKey: ['bots', selectedAccount?.id],
    queryFn: () => botsApi.getAll(),
    select: (data) => {
      if (!selectedAccount) return data
      // Filter by account_id
      return data.filter((bot: Bot) => bot.account_id === selectedAccount.id)
    },
  })

  const { data: allPositions, isLoading } = useQuery({
    queryKey: ['positions-closed', selectedAccount?.id],
    queryFn: () => positionsApi.getAll('closed', 500), // Get closed positions with higher limit
    refetchInterval: 5000,
    select: (data) => {
      if (!selectedAccount) return data
      // Filter by account_id
      return data.filter((p: Position) => p.account_id === selectedAccount.id)
    },
  })

  const { data: failedOrdersData, isLoading: isLoadingFailed } = useQuery({
    queryKey: ['order-history-failed-paginated', selectedAccount?.id, failedPage],
    queryFn: () => orderHistoryApi.getFailedPaginated(failedPage, pageSize, undefined, selectedAccount?.id),
    refetchInterval: 30000,
  })

  // API now filters by account_id on server side
  const failedOrders = failedOrdersData?.items || []
  const failedTotal = failedOrdersData?.total || 0
  const failedTotalPages = failedOrdersData?.total_pages || 1

  // API returns closed positions already sorted by closed_at DESC
  const allClosedPositions = allPositions || []

  // Helper: check if a product_id matches the market filter
  const matchesMarket = (productId: string, market: 'all' | 'USD' | 'BTC') => {
    if (market === 'all') return true
    const quote = productId?.split('-')[1] || ''
    return quote === market
  }

  // Cascading filters: each dropdown's options are filtered by the OTHER selections
  // uniquePairs = pairs available given current bot + market selection
  const uniquePairs = useMemo(() => {
    const pairSet = new Set<string>()
    if (activeTab === 'closed') {
      allClosedPositions.forEach((p: Position) => {
        if (!p.product_id) return
        if (filterBot !== 'all' && p.bot_id !== filterBot) return
        if (!matchesMarket(p.product_id, filterMarket)) return
        pairSet.add(p.product_id)
      })
    } else {
      failedOrders.forEach((o: any) => {
        if (!o.product_id) return
        if (filterBot !== 'all') {
          const botName = bots?.find(b => b.id === filterBot)?.name
          if (!botName || o.bot_name !== botName) return
        }
        if (!matchesMarket(o.product_id, filterMarket)) return
        pairSet.add(o.product_id)
      })
    }
    return Array.from(pairSet).sort()
  }, [allClosedPositions, failedOrders, activeTab, filterBot, filterMarket, bots])

  // availableBots = bots that have data given current market + pair selection
  const availableBots = useMemo(() => {
    if (!bots) return undefined
    const botIdSet = new Set<number>()
    if (activeTab === 'closed') {
      allClosedPositions.forEach((p: Position) => {
        if (!p.bot_id) return
        if (filterPair !== 'all' && p.product_id !== filterPair) return
        if (!matchesMarket(p.product_id || '', filterMarket)) return
        botIdSet.add(p.bot_id)
      })
    } else {
      failedOrders.forEach((o: any) => {
        if (!o.bot_name) return
        if (filterPair !== 'all' && o.product_id !== filterPair) return
        if (!matchesMarket(o.product_id || '', filterMarket)) return
        const bot = bots.find(b => b.name === o.bot_name)
        if (bot) botIdSet.add(bot.id)
      })
    }
    return bots.filter(b => botIdSet.has(b.id))
  }, [bots, allClosedPositions, failedOrders, activeTab, filterPair, filterMarket])

  // Filter closed positions (all three filters applied)
  const filteredClosedPositions = useMemo(() => {
    return allClosedPositions.filter((p: Position) => {
      if (filterBot !== 'all' && p.bot_id !== filterBot) return false
      if (!matchesMarket(p.product_id || '', filterMarket)) return false
      if (filterPair !== 'all' && p.product_id !== filterPair) return false
      return true
    })
  }, [allClosedPositions, filterBot, filterMarket, filterPair])

  // Filter failed orders (all three filters applied)
  const filteredFailedOrders = useMemo(() => {
    return failedOrders.filter((o: any) => {
      if (filterBot !== 'all') {
        const botName = bots?.find(b => b.id === filterBot)?.name
        if (!botName || o.bot_name !== botName) return false
      }
      if (!matchesMarket(o.product_id || '', filterMarket)) return false
      if (filterPair !== 'all' && o.product_id !== filterPair) return false
      return true
    })
  }, [failedOrders, filterBot, filterMarket, filterPair, bots])

  const clearFilters = () => {
    setFilterBot('all')
    setFilterMarket('all')
    setFilterPair('all')
  }

  const hasActiveFilters = filterBot !== 'all' || filterMarket !== 'all' || filterPair !== 'all'

  // Auto-reset stale selections when options change
  useEffect(() => {
    if (filterPair !== 'all' && !uniquePairs.includes(filterPair)) {
      setFilterPair('all')
    }
  }, [uniquePairs, filterPair])

  useEffect(() => {
    if (filterBot !== 'all' && availableBots && !availableBots.some(b => b.id === filterBot)) {
      setFilterBot('all')
    }
  }, [availableBots, filterBot])

  // Reset pagination when filters change
  useEffect(() => {
    setClosedPage(1)
    setFailedPage(1)
  }, [filterBot, filterMarket, filterPair])

  // Client-side pagination for closed positions (use filtered)
  const closedTotalPages = Math.ceil(filteredClosedPositions.length / pageSize) || 1
  const closedPositions = filteredClosedPositions.slice(
    (closedPage - 1) * pageSize,
    closedPage * pageSize
  )

  // Calculate badge counts for each tab (use UNFILTERED total counts)
  const currentClosedCount = allClosedPositions.length
  const currentFailedCount = failedTotal
  const newClosedCount = Math.max(0, currentClosedCount - lastSeenClosedCount)
  const newFailedCount = Math.max(0, currentFailedCount - lastSeenFailedCount)

  // Update last seen count when user views a specific tab for 3 seconds (synced to server)
  // Use a ref to track the timer and prevent re-saves on data refetch
  useEffect(() => {
    // Don't start timer if count is 0 (data still loading)
    if (activeTab === 'closed' && currentClosedCount > 0) {
      // Only set timer if there are new items to mark as seen
      if (currentClosedCount > lastSeenClosedCount) {
        const timer = setTimeout(async () => {
          console.log('✅ Marking closed positions as viewed:', currentClosedCount)
          setLastSeenClosedCount(currentClosedCount)

          // Save to server
          const token = getAccessToken()
          if (token) {
            try {
              await fetch('/api/auth/preferences/last-seen-history', {
                method: 'PUT',
                headers: {
                  'Content-Type': 'application/json',
                  'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ count: currentClosedCount })
              })
            } catch (error) {
              console.error('Failed to save last seen closed count:', error)
            }
          }
        }, 3000)
        return () => clearTimeout(timer)
      }
    } else if (activeTab === 'failed' && currentFailedCount > 0) {
      // Only set timer if there are new items to mark as seen
      if (currentFailedCount > lastSeenFailedCount) {
        const timer = setTimeout(async () => {
          console.log('✅ Marking failed orders as viewed:', currentFailedCount)
          setLastSeenFailedCount(currentFailedCount)

          // Save to server
          const token = getAccessToken()
          if (token) {
            try {
              await fetch('/api/auth/preferences/last-seen-history', {
                method: 'PUT',
                headers: {
                  'Content-Type': 'application/json',
                  'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ failed_count: currentFailedCount })
              })
            } catch (error) {
              console.error('Failed to save last seen failed count:', error)
            }
          }
        }, 3000)
        return () => clearTimeout(timer)
      }
    }
  }, [activeTab, currentClosedCount, currentFailedCount, lastSeenClosedCount, lastSeenFailedCount, getAccessToken])

  const getQuoteCurrency = (productId: string) => {
    const quote = productId?.split('-')[1] || 'BTC'
    return {
      symbol: quote,
      decimals: quote === 'USD' ? 2 : 8
    }
  }

  const formatQuoteAmount = (amount: number, productId: string) => {
    const { symbol, decimals } = getQuoteCurrency(productId)
    return `${amount.toFixed(decimals)} ${symbol}`
  }

  const calculateDuration = (openedAt: string, closedAt: string) => {
    const start = new Date(openedAt)
    const end = new Date(closedAt)
    const diffMs = end.getTime() - start.getTime()

    const days = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    const hours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))
    const seconds = Math.floor((diffMs % (1000 * 60)) / 1000)

    const parts = []
    if (days > 0) parts.push(`${days} day${days > 1 ? 's' : ''}`)
    if (hours > 0) parts.push(`${hours} hour${hours > 1 ? 's' : ''}`)
    if (minutes > 0) parts.push(`${minutes} minute${minutes > 1 ? 's' : ''}`)
    if (seconds > 0) parts.push(`${seconds} second${seconds > 1 ? 's' : ''}`)

    return parts.length > 0 ? parts.join(' ') : 'Less than a second'
  }

  const togglePosition = async (positionId: number) => {
    if (expandedPositionId === positionId) {
      setExpandedPositionId(null)
    } else {
      setExpandedPositionId(positionId)
      // Fetch trades if not already loaded
      if (!positionTrades[positionId]) {
        try {
          const trades = await positionsApi.getTrades(positionId)
          setPositionTrades(prev => ({ ...prev, [positionId]: trades }))
        } catch (error) {
          console.error('Failed to fetch trades:', error)
        }
      }
      // Fetch AI logs if not already loaded
      if (!positionAILogs[positionId]) {
        try {
          const logs = await positionsApi.getAILogs(positionId, true)
          setPositionAILogs(prev => ({ ...prev, [positionId]: logs }))
        } catch (error) {
          console.error('Failed to fetch AI logs:', error)
        }
      }
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-white p-6">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Closed Positions</h1>
          <div className="flex justify-center py-12">
            <LoadingSpinner size="lg" text="Loading closed positions..." />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          {selectedAccount?.type === 'dex' ? (
            <Wallet className="w-8 h-8 text-orange-400" />
          ) : (
            <Building2 className="w-8 h-8 text-blue-400" />
          )}
          <div>
            <h1 className="text-3xl font-bold text-white">History</h1>
            <p className="text-slate-400 mt-1">
              {selectedAccount && (
                <>
                  <span className="text-slate-300">{selectedAccount.name}</span>
                  {selectedAccount.type === 'dex' && selectedAccount.chain_id && (
                    <span className="text-slate-500"> ({getChainName(selectedAccount.chain_id)})</span>
                  )}
                  <span> • </span>
                </>
              )}
              Closed positions and failed orders
            </p>
          </div>
        </div>

        {/* Tabs + Filter Toggle */}
        <div className="flex items-center justify-between mb-2 border-b border-slate-700">
          <div className="flex space-x-2">
          <button
            onClick={() => setActiveTab('closed')}
            className={`px-4 py-2 font-medium transition-colors relative ${
              activeTab === 'closed'
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <span className="flex items-center space-x-2">
              <span>Closed Positions ({hasActiveFilters ? `${filteredClosedPositions.length}/` : ''}{currentClosedCount})</span>
              {newClosedCount > 0 && (
                <span className="bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
                  {newClosedCount > 9 ? '9+' : newClosedCount}
                </span>
              )}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('failed')}
            className={`px-4 py-2 font-medium transition-colors relative ${
              activeTab === 'failed'
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <span className="flex items-center space-x-2">
              <span>Failed Orders ({hasActiveFilters ? `${filteredFailedOrders.length}/` : ''}{failedTotal})</span>
              {newFailedCount > 0 && (
                <span className="bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
                  {newFailedCount > 9 ? '9+' : newFailedCount}
                </span>
              )}
            </span>
          </button>
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors flex items-center gap-1.5 mb-1 ${
              showFilters || hasActiveFilters
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600 border border-slate-600'
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
            {hasActiveFilters && (
              <span className="bg-blue-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center">
                {(filterBot !== 'all' ? 1 : 0) + (filterMarket !== 'all' ? 1 : 0) + (filterPair !== 'all' ? 1 : 0)}
              </span>
            )}
          </button>
        </div>

        {/* Filter Panel */}
        {showFilters && (
          <FilterPanel
            filterBot={filterBot}
            setFilterBot={setFilterBot}
            filterMarket={filterMarket}
            setFilterMarket={setFilterMarket}
            filterPair={filterPair}
            setFilterPair={setFilterPair}
            bots={availableBots}
            uniquePairs={uniquePairs}
            onClearFilters={clearFilters}
          />
        )}

        {/* Closed Positions Tab */}
        {activeTab === 'closed' && (
          <>
            {closedPositions.length === 0 ? (
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-8 text-center">
            <p className="text-slate-400">{hasActiveFilters ? 'No closed positions match your filters' : 'No closed positions yet'}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {closedPositions.map((position: Position) => (
              <div key={position.id} className="bg-slate-800 rounded-lg border border-slate-700">
                <div
                  className="p-4 cursor-pointer hover:bg-slate-750 transition-colors"
                  onClick={() => togglePosition(position.id)}
                >
                  <div className="grid grid-cols-1 md:grid-cols-8 gap-4">
                    <div>
                      <p className="text-slate-400 text-xs mb-1">Deal</p>
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-semibold text-white">#{position.user_deal_number ?? position.id}</p>
                        {bots && position.bot_id && (
                          <span className="bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded text-xs font-medium">
                            {bots.find(b => b.id === position.bot_id)?.name || `Bot #${position.bot_id}`}
                          </span>
                        )}
                        <span className="bg-purple-500/20 text-purple-400 px-1.5 py-0.5 rounded text-xs font-medium">
                          {position.product_id || 'ETH-BTC'}
                        </span>
                      </div>
                    </div>
                    <div>
                      <p className="text-slate-400 text-xs mb-1">Opened</p>
                      <p className="font-semibold text-white">
                        {formatDateTime(position.opened_at)}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-400 text-xs mb-1">Closed</p>
                      <p className="font-semibold text-white">
                        {position.closed_at ? formatDateTime(position.closed_at) : '-'}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-400 text-xs mb-1">Duration</p>
                      <p className="font-semibold text-white">
                        {position.closed_at ? calculateDuration(position.opened_at, position.closed_at) : '-'}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-400 text-xs mb-1">Invested</p>
                      <p className="font-semibold text-white">{formatQuoteAmount(position.total_quote_spent, position.product_id || 'ETH-BTC')}</p>
                    </div>
                    <div>
                      <p className="text-slate-400 text-xs mb-1">Orders</p>
                      <p className="font-semibold text-white">{position.trade_count}</p>
                    </div>
                    <div>
                      <p className="text-slate-400 text-xs mb-1">Profit</p>
                      {position.profit_quote !== null ? (
                        <div>
                          <div className="flex items-center gap-1">
                            {position.profit_quote >= 0 ? (
                              <TrendingUp className="w-3 h-3 text-green-500" />
                            ) : (
                              <TrendingDown className="w-3 h-3 text-red-500" />
                            )}
                            <span className={`font-semibold ${position.profit_quote >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {position.profit_percentage?.toFixed(2)}%
                            </span>
                          </div>
                          <p className={`text-xs ${position.profit_quote >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
                            {formatQuoteAmount(position.profit_quote, position.product_id || 'ETH-BTC')}
                          </p>
                          {/* Show USD values for BTC pairs */}
                          {position.product_id?.endsWith('-BTC') && position.profit_quote !== null && (
                            <>
                              {/* Historical USD at time of close */}
                              {position.profit_usd !== undefined && position.profit_usd !== null && (
                                <p className={`text-xs ${position.profit_quote >= 0 ? 'text-green-400/50' : 'text-red-400/50'}`}>
                                  ${Math.abs(position.profit_usd).toFixed(2)} at close
                                </p>
                              )}
                              {/* Today's USD value */}
                              {currentBtcUsdPrice > 0 && (
                                <p className={`text-xs ${position.profit_quote >= 0 ? 'text-blue-400/70' : 'text-orange-400/70'}`}>
                                  ${Math.abs(position.profit_quote * currentBtcUsdPrice).toFixed(2)} today
                                </p>
                              )}
                            </>
                          )}
                        </div>
                      ) : (
                        <p className="font-semibold text-slate-400">-</p>
                      )}
                    </div>
                    <div className="flex items-center justify-end">
                      {expandedPositionId === position.id ? (
                        <ChevronUp className="w-5 h-5 text-slate-400" />
                      ) : (
                        <ChevronDown className="w-5 h-5 text-slate-400" />
                      )}
                    </div>
                  </div>
                </div>

                {/* Expanded trade details */}
                {expandedPositionId === position.id && (
                  <div className="border-t border-slate-700 p-4 bg-slate-850">
                    {positionTrades[position.id] ? (
                      <div>
                        <p className="text-slate-400 text-xs mb-3">Trade History</p>
                        <div className="space-y-2">
                          {positionTrades[position.id].map((trade) => (
                            <div key={trade.id} className="bg-slate-800 rounded p-3 grid grid-cols-5 gap-3 text-sm">
                              <div>
                                <p className="text-slate-500 text-xs mb-1">Time</p>
                                <p className="text-white">{formatDateTime(trade.timestamp)}</p>
                              </div>
                              <div>
                                <p className="text-slate-500 text-xs mb-1">Type</p>
                                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                  trade.side === 'sell'
                                    ? 'bg-purple-500/20 text-purple-400'
                                    : trade.trade_type === 'initial'
                                    ? 'bg-blue-500/20 text-blue-400'
                                    : 'bg-orange-500/20 text-orange-400'
                                }`}>
                                  {trade.side === 'sell' ? 'Take Profit' : trade.trade_type === 'initial' ? 'Base Order' : 'DCA'}
                                </span>
                              </div>
                              <div>
                                <p className="text-slate-500 text-xs mb-1">Side</p>
                                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                  trade.side === 'buy'
                                    ? 'bg-green-500/20 text-green-400'
                                    : 'bg-red-500/20 text-red-400'
                                }`}>
                                  {trade.side.toUpperCase()}
                                </span>
                              </div>
                              <div>
                                <p className="text-slate-500 text-xs mb-1">Amount</p>
                                <p className="text-white">{formatQuoteAmount(trade.quote_amount, position.product_id || 'ETH-BTC')}</p>
                              </div>
                              <div>
                                <p className="text-slate-500 text-xs mb-1">Price</p>
                                <p className="text-white">{trade.price?.toFixed(8) || '-'}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="text-center text-slate-400 py-4">
                        Loading trade history...
                      </div>
                    )}

                    {/* AI Reasoning History */}
                    {positionAILogs[position.id] && positionAILogs[position.id].length > 0 && (
                      <div className="mt-6 pt-4 border-t border-slate-700">
                        <p className="text-slate-400 text-xs mb-3">AI Reasoning History</p>
                        <div className="space-y-3">
                          {positionAILogs[position.id].map((log) => (
                            <div key={log.id} className="bg-slate-800/50 rounded p-4 border border-slate-700/50">
                              <div className="flex items-start justify-between mb-2">
                                <div className="flex items-center gap-3">
                                  <p className="text-slate-500 text-xs">
                                    {formatDateTime(log.timestamp)}
                                  </p>
                                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                    log.decision === 'buy' || log.decision === 'open_position'
                                      ? 'bg-green-500/20 text-green-400'
                                      : log.decision === 'sell' || log.decision === 'close_position'
                                      ? 'bg-red-500/20 text-red-400'
                                      : 'bg-slate-500/20 text-slate-400'
                                  }`}>
                                    {log.decision.toUpperCase()}
                                  </span>
                                  {log.confidence !== null && (
                                    <span className="text-slate-500 text-xs">
                                      {log.confidence.toFixed(0)}% confidence
                                    </span>
                                  )}
                                  {log.current_price !== null && (
                                    <span className="text-slate-500 text-xs">
                                      @ {log.current_price.toFixed(8)}
                                    </span>
                                  )}
                                </div>
                              </div>
                              <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                                {log.thinking}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

          {/* Pagination Controls for Closed Positions */}
          {closedTotalPages > 1 && (
            <div className="flex items-center justify-between mt-6 px-2">
              <p className="text-sm text-slate-400">
                Page {closedPage} of {closedTotalPages} ({filteredClosedPositions.length} total)
              </p>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setClosedPage(1)}
                  disabled={closedPage === 1}
                  className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="First page"
                >
                  <ChevronsLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setClosedPage(p => Math.max(1, p - 1))}
                  disabled={closedPage === 1}
                  className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Previous page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="px-4 py-2 text-sm text-slate-300">
                  {closedPage}
                </span>
                <button
                  onClick={() => setClosedPage(p => Math.min(closedTotalPages, p + 1))}
                  disabled={closedPage === closedTotalPages}
                  className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Next page"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setClosedPage(closedTotalPages)}
                  disabled={closedPage === closedTotalPages}
                  className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Last page"
                >
                  <ChevronsRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
          </>
        )}

        {/* Failed Orders Tab */}
        {activeTab === 'failed' && (
          <>
            {isLoadingFailed ? (
              <div className="flex justify-center py-12">
                <LoadingSpinner size="lg" text="Loading failed orders..." />
              </div>
            ) : filteredFailedOrders.length === 0 ? (
              <div className="bg-slate-800 rounded-lg border border-slate-700 p-8 text-center">
                <p className="text-slate-400">{hasActiveFilters ? 'No failed orders match your filters' : 'No failed orders'}</p>
              </div>
            ) : (
              <>
                <div className="space-y-3">
                  {filteredFailedOrders.map((order: any) => (
                    <div key={order.id} className="bg-slate-800 rounded-lg border border-red-900/30 p-4">
                      <div className="grid grid-cols-1 md:grid-cols-7 gap-4">
                        <div>
                          <p className="text-slate-400 text-xs mb-1">Bot</p>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded text-xs font-medium">
                              {order.bot_name}
                            </span>
                            <span className="bg-purple-500/20 text-purple-400 px-1.5 py-0.5 rounded text-xs font-medium">
                              {order.product_id}
                            </span>
                          </div>
                        </div>
                        <div>
                          <p className="text-slate-400 text-xs mb-1">Position</p>
                          <p className="font-semibold text-white">
                            {order.position_id ? `#${order.position_id}` : '-'}
                          </p>
                        </div>
                        <div>
                          <p className="text-slate-400 text-xs mb-1">Time</p>
                          <p className="font-semibold text-white">
                            {formatDateTime(order.timestamp)}
                          </p>
                        </div>
                        <div>
                          <p className="text-slate-400 text-xs mb-1">Type</p>
                          <p className="font-semibold text-white">
                            {order.trade_type === 'initial' ? 'Base Order' : order.trade_type.toUpperCase()}
                          </p>
                        </div>
                        <div>
                          <p className="text-slate-400 text-xs mb-1">Amount</p>
                          <p className="font-semibold text-white">
                            {order.quote_amount.toFixed(order.product_id.endsWith('USD') ? 2 : 8)} {order.product_id.split('-')[1]}
                          </p>
                        </div>
                        <div>
                          <p className="text-slate-400 text-xs mb-1">Price</p>
                          <p className="font-semibold text-white">
                            {order.price ? order.price.toFixed(8) : '-'}
                          </p>
                        </div>
                        <div>
                          <p className="text-slate-400 text-xs mb-1">Status</p>
                          <div className="flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3 text-red-500" />
                            <span className="font-semibold text-red-400">FAILED</span>
                          </div>
                        </div>
                      </div>
                      {order.error_message && (
                        <div className="mt-3 pt-3 border-t border-slate-700">
                          <p className="text-slate-400 text-xs mb-1">Error:</p>
                          <p className="text-red-400 text-sm font-mono">{order.error_message}</p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* Pagination Controls */}
                {failedTotalPages > 1 && (
                  <div className="flex items-center justify-between mt-6 px-2">
                    <p className="text-sm text-slate-400">
                      Page {failedPage} of {failedTotalPages} ({filteredFailedOrders.length} total)
                    </p>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setFailedPage(1)}
                        disabled={failedPage === 1}
                        className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        title="First page"
                      >
                        <ChevronsLeft className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setFailedPage(p => Math.max(1, p - 1))}
                        disabled={failedPage === 1}
                        className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        title="Previous page"
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </button>
                      <span className="px-4 py-2 text-sm text-slate-300">
                        {failedPage}
                      </span>
                      <button
                        onClick={() => setFailedPage(p => Math.min(failedTotalPages, p + 1))}
                        disabled={failedPage === failedTotalPages}
                        className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        title="Next page"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setFailedPage(failedTotalPages)}
                        disabled={failedPage === failedTotalPages}
                        className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        title="Last page"
                      >
                        <ChevronsRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default ClosedPositions
