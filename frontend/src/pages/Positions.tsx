import { useQuery } from '@tanstack/react-query'
import { positionsApi } from '../services/api'
import { format } from 'date-fns'
import { useState } from 'react'
import { TrendingUp, TrendingDown, ChevronDown, ChevronUp } from 'lucide-react'
import type { Position } from '../types'

export default function Positions() {
  const [selectedPosition, setSelectedPosition] = useState<number | null>(null)

  const { data: positions } = useQuery({
    queryKey: ['positions'],
    queryFn: () => positionsApi.getAll(undefined, 100),
    refetchInterval: 10000,
  })

  const { data: trades } = useQuery({
    queryKey: ['position-trades', selectedPosition],
    queryFn: () => positionsApi.getTrades(selectedPosition!),
    enabled: selectedPosition !== null,
  })

  const formatBTC = (btc: number) => `${btc.toFixed(8)} BTC`
  const formatPrice = (price: number) => price.toFixed(8)

  const togglePosition = (positionId: number) => {
    if (selectedPosition === positionId) {
      setSelectedPosition(null)
    } else {
      setSelectedPosition(positionId)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Position History</h2>
        <p className="text-slate-400">{positions?.length || 0} total positions</p>
      </div>

      <div className="space-y-3">
        {positions?.map((position) => (
          <div key={position.id} className="card">
            <div
              className="flex items-center justify-between cursor-pointer"
              onClick={() => togglePosition(position.id)}
            >
              <div className="flex-1 grid grid-cols-1 md:grid-cols-5 gap-4">
                <div>
                  <p className="text-slate-400 text-sm">Status</p>
                  <p className="font-semibold">
                    <span
                      className={`inline-block px-2 py-1 rounded text-sm ${
                        position.status === 'open'
                          ? 'bg-green-600 text-white'
                          : 'bg-slate-600 text-white'
                      }`}
                    >
                      {position.status.toUpperCase()}
                    </span>
                  </p>
                </div>
                <div>
                  <p className="text-slate-400 text-sm">Opened</p>
                  <p className="font-semibold">
                    {format(new Date(position.opened_at), 'MMM dd, HH:mm')}
                  </p>
                </div>
                <div>
                  <p className="text-slate-400 text-sm">BTC Spent</p>
                  <p className="font-semibold">{formatBTC(position.total_btc_spent)}</p>
                </div>
                <div>
                  <p className="text-slate-400 text-sm">Trades</p>
                  <p className="font-semibold">{position.trade_count}</p>
                </div>
                <div>
                  <p className="text-slate-400 text-sm">Profit</p>
                  {position.profit_btc !== null ? (
                    <div>
                      <div className="flex items-center space-x-1">
                        {position.profit_btc >= 0 ? (
                          <TrendingUp className="w-4 h-4 text-green-500" />
                        ) : (
                          <TrendingDown className="w-4 h-4 text-red-500" />
                        )}
                        <p
                          className={`font-semibold ${
                            position.profit_btc >= 0 ? 'text-green-400' : 'text-red-400'
                          }`}
                        >
                          {formatBTC(position.profit_btc)}
                        </p>
                        <span className="text-slate-400 text-sm">
                          ({position.profit_percentage?.toFixed(2)}%)
                        </span>
                      </div>
                      {position.profit_usd && (
                        <p className="text-sm text-slate-400 mt-1">
                          ${position.profit_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </p>
                      )}
                    </div>
                  ) : (
                    <p className="font-semibold text-slate-400">-</p>
                  )}
                </div>
              </div>
              <div className="ml-4">
                {selectedPosition === position.id ? (
                  <ChevronUp className="w-5 h-5 text-slate-400" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-slate-400" />
                )}
              </div>
            </div>

            {/* Expanded Details */}
            {selectedPosition === position.id && (
              <div className="mt-6 pt-6 border-t border-slate-700">
                <h4 className="font-semibold mb-4">Position Details</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                  <div>
                    <p className="text-slate-400 text-sm">Initial BTC Balance</p>
                    <p className="font-semibold">{formatBTC(position.initial_btc_balance)}</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-sm">Max BTC Allowed</p>
                    <p className="font-semibold">{formatBTC(position.max_btc_allowed)}</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-sm">ETH Acquired</p>
                    <p className="font-semibold">{position.total_eth_acquired.toFixed(6)} ETH</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-sm">Avg Buy Price</p>
                    <p className="font-semibold">{formatPrice(position.average_buy_price)}</p>
                  </div>
                  {position.sell_price && (
                    <div>
                      <p className="text-slate-400 text-sm">Sell Price</p>
                      <p className="font-semibold">{formatPrice(position.sell_price)}</p>
                    </div>
                  )}
                  {position.closed_at && (
                    <div>
                      <p className="text-slate-400 text-sm">Closed</p>
                      <p className="font-semibold">
                        {format(new Date(position.closed_at), 'MMM dd, HH:mm')}
                      </p>
                    </div>
                  )}
                </div>

                {/* Trades */}
                {trades && trades.length > 0 && (
                  <div>
                    <h5 className="font-semibold mb-3">Trades</h5>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-slate-700">
                          <tr>
                            <th className="px-3 py-2 text-left">Time</th>
                            <th className="px-3 py-2 text-left">Type</th>
                            <th className="px-3 py-2 text-left">Side</th>
                            <th className="px-3 py-2 text-right">BTC Amount</th>
                            <th className="px-3 py-2 text-right">ETH Amount</th>
                            <th className="px-3 py-2 text-right">Price</th>
                          </tr>
                        </thead>
                        <tbody>
                          {trades.map((trade) => (
                            <tr key={trade.id} className="border-b border-slate-700">
                              <td className="px-3 py-2">
                                {format(new Date(trade.timestamp), 'MMM dd HH:mm:ss')}
                              </td>
                              <td className="px-3 py-2">
                                <span className="px-2 py-1 rounded bg-slate-700 text-xs">
                                  {trade.trade_type}
                                </span>
                              </td>
                              <td className="px-3 py-2">
                                <span
                                  className={`px-2 py-1 rounded text-xs ${
                                    trade.side === 'buy'
                                      ? 'bg-green-600 text-white'
                                      : 'bg-red-600 text-white'
                                  }`}
                                >
                                  {trade.side.toUpperCase()}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-right">{formatBTC(trade.btc_amount)}</td>
                              <td className="px-3 py-2 text-right">
                                {trade.eth_amount.toFixed(6)} ETH
                              </td>
                              <td className="px-3 py-2 text-right">{formatPrice(trade.price)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
