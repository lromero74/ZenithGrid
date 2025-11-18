import { useQuery } from '@tanstack/react-query'
import { positionsApi, botsApi, orderHistoryApi } from '../services/api'
import { format } from 'date-fns'
import { TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react'
import { useState } from 'react'

function ClosedPositions() {
  const [activeTab, setActiveTab] = useState<'closed' | 'failed'>('closed')

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

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-white p-6">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Closed Positions</h1>
          <div className="text-slate-400">Loading closed positions...</div>
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
              <div key={position.id} className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
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
                </div>
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
