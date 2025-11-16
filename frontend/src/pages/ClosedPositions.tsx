import { useQuery } from '@tanstack/react-query'
import { positionsApi, botsApi } from '../services/api'
import { format } from 'date-fns'
import { TrendingUp, TrendingDown } from 'lucide-react'

function ClosedPositions() {
  const { data: bots } = useQuery({
    queryKey: ['bots'],
    queryFn: botsApi.getAll,
  })

  const { data: allPositions, isLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: positionsApi.getAll,
    refetchInterval: 5000,
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
          <h1 className="text-3xl font-bold text-white">Closed Positions</h1>
          <p className="text-slate-400 mt-2">{closedPositions.length} closed position{closedPositions.length !== 1 ? 's' : ''}</p>
        </div>

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
                    <p className="font-semibold text-white">{formatQuoteAmount(position.total_btc_spent, position.product_id || 'ETH-BTC')}</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Orders</p>
                    <p className="font-semibold text-white">{position.trade_count}</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Profit</p>
                    {position.profit_btc !== null ? (
                      <div>
                        <div className="flex items-center gap-1">
                          {position.profit_btc >= 0 ? (
                            <TrendingUp className="w-3 h-3 text-green-500" />
                          ) : (
                            <TrendingDown className="w-3 h-3 text-red-500" />
                          )}
                          <span className={`font-semibold ${position.profit_btc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {position.profit_percentage?.toFixed(2)}%
                          </span>
                        </div>
                        <p className={`text-xs ${position.profit_btc >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
                          {formatQuoteAmount(position.profit_btc, position.product_id || 'ETH-BTC')}
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
      </div>
    </div>
  )
}

export default ClosedPositions
