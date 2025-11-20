import { useQuery } from '@tanstack/react-query'
import { positionsApi, botsApi, orderHistoryApi } from '../services/api'
import { format } from 'date-fns'
import { TrendingUp, TrendingDown, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import type { Trade, AIBotLog } from '../types'
import { LoadingSpinner } from '../components/LoadingSpinner'

function ClosedPositions() {
  const [activeTab, setActiveTab] = useState<'closed' | 'failed'>('closed')
  const [expandedPositionId, setExpandedPositionId] = useState<number | null>(null)
  const [positionTrades, setPositionTrades] = useState<Record<number, Trade[]>>({})
  const [positionAILogs, setPositionAILogs] = useState<Record<number, AIBotLog[]>>({})

  const { data: bots } = useQuery({
    queryKey: ['bots'],
    queryFn: botsApi.getAll,
  })

  const { data: allPositions, isLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: positionsApi.getAll,
    refetchInterval: 5000,
  })

  const { data: failedOrders, isLoading: isLoadingFailed } = useQuery({
    queryKey: ['order-history-failed'],
    queryFn: () => orderHistoryApi.getFailed(undefined, 100),
    refetchInterval: 30000,
  })

  const closedPositions = allPositions?.filter(p => p.status === 'closed') || []

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

    const weeks = Math.floor(diffMs / (1000 * 60 * 60 * 24 * 7))
    const days = Math.floor((diffMs % (1000 * 60 * 60 * 24 * 7)) / (1000 * 60 * 60 * 24))
    const hours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))

    const parts = []
    if (weeks > 0) parts.push(`${weeks} week${weeks > 1 ? 's' : ''}`)
    if (days > 0) parts.push(`${days} day${days > 1 ? 's' : ''}`)
    if (hours > 0) parts.push(`${hours} hour${hours > 1 ? 's' : ''}`)
    if (minutes > 0) parts.push(`${minutes} minute${minutes > 1 ? 's' : ''}`)

    return parts.length > 0 ? parts.join(' ') : 'Less than a minute'
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
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-white">History</h1>
          <p className="text-slate-400 mt-2">Closed positions and failed orders</p>
        </div>

        {/* Tabs */}
        <div className="flex space-x-2 mb-6 border-b border-slate-700">
          <button
            onClick={() => setActiveTab('closed')}
            className={`px-4 py-2 font-medium transition-colors ${
              activeTab === 'closed'
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Closed Positions ({closedPositions.length})
          </button>
          <button
            onClick={() => setActiveTab('failed')}
            className={`px-4 py-2 font-medium transition-colors ${
              activeTab === 'failed'
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Failed Orders ({failedOrders?.length || 0})
          </button>
        </div>

        {/* Closed Positions Tab */}
        {activeTab === 'closed' && (
          <>
            {closedPositions.length === 0 ? (
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-8 text-center">
            <p className="text-slate-400">No closed positions yet</p>
          </div>
        ) : (
          <div className="space-y-3">
            {closedPositions.map((position) => (
              <div key={position.id} className="bg-slate-800 rounded-lg border border-slate-700">
                <div
                  className="p-4 cursor-pointer hover:bg-slate-750 transition-colors"
                  onClick={() => togglePosition(position.id)}
                >
                  <div className="grid grid-cols-1 md:grid-cols-7 gap-4">
                    <div>
                      <p className="text-slate-400 text-xs mb-1">Deal</p>
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-semibold text-white">#{position.id}</p>
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
                        {format(new Date(position.opened_at), 'MMM dd, HH:mm')}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-400 text-xs mb-1">Closed</p>
                      <p className="font-semibold text-white">
                        {position.closed_at ? format(new Date(position.closed_at), 'MMM dd, HH:mm') : '-'}
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
                    {position.closed_at && (
                      <div className="mb-4 pb-3 border-b border-slate-700">
                        <p className="text-slate-400 text-xs mb-1">Duration</p>
                        <p className="font-semibold text-white">
                          {calculateDuration(position.opened_at, position.closed_at)}
                        </p>
                      </div>
                    )}

                    {positionTrades[position.id] ? (
                      <div>
                        <p className="text-slate-400 text-xs mb-3">Trade History</p>
                        <div className="space-y-2">
                          {positionTrades[position.id].map((trade) => (
                            <div key={trade.id} className="bg-slate-800 rounded p-3 grid grid-cols-5 gap-3 text-sm">
                              <div>
                                <p className="text-slate-500 text-xs mb-1">Time</p>
                                <p className="text-white">{format(new Date(trade.timestamp), 'MMM dd, HH:mm:ss')}</p>
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
                                    {format(new Date(log.timestamp), 'MMM dd, HH:mm:ss')}
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
          </>
        )}

        {/* Failed Orders Tab */}
        {activeTab === 'failed' && (
          <>
            {!failedOrders || failedOrders.length === 0 ? (
              <div className="bg-slate-800 rounded-lg border border-slate-700 p-8 text-center">
                <p className="text-slate-400">No failed orders</p>
              </div>
            ) : (
              <div className="space-y-3">
                {failedOrders.map((order) => (
                  <div key={order.id} className="bg-slate-800 rounded-lg border border-red-900/30 p-4">
                    <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
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
                        <p className="text-slate-400 text-xs mb-1">Time</p>
                        <p className="font-semibold text-white">
                          {format(new Date(order.timestamp), 'MMM dd, HH:mm:ss')}
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
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default ClosedPositions
