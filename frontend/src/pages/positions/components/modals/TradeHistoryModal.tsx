import { X } from 'lucide-react'
import { formatDateTime } from '../../../../utils/dateFormat'
import type { Position } from '../../../../types'

interface Trade {
  id: number
  timestamp: string
  side: string
  trade_type: string
  trade_type_display?: string
  price: number
  base_amount: number
  quote_amount: number
}

interface TradeHistoryModalProps {
  isOpen: boolean
  position: Position | null
  trades: Trade[] | undefined
  isLoading: boolean
  onClose: () => void
}

export const TradeHistoryModal = ({
  isOpen,
  position,
  trades,
  isLoading,
  onClose,
}: TradeHistoryModalProps) => {
  if (!isOpen || !position) return null

  const sortedTrades = trades
    ? [...trades].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    : []

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-lg w-full max-w-3xl p-6 max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-2xl font-bold text-white">Trade History</h3>
            <p className="text-sm text-slate-400 mt-1">
              Deal #{position.user_deal_number ?? position.id} • {position.product_id || 'ETH-BTC'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        {isLoading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
            <p className="text-slate-400 mt-4">Loading trade history...</p>
          </div>
        ) : sortedTrades.length > 0 ? (
          <div className="space-y-3">
            {sortedTrades.map((trade) => (
              <div
                key={trade.id}
                className="bg-slate-700/50 rounded-lg p-4 border border-slate-600"
              >
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <div className="text-xs text-slate-400 mb-1">Type</div>
                    <div className={`text-sm font-semibold ${
                      trade.side.toUpperCase() === 'BUY' ? 'text-green-400' : 'text-blue-400'
                    }`}>
                      {trade.trade_type_display || trade.trade_type}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400 mb-1">Price</div>
                    <div className="text-sm text-white font-mono">
                      {trade.price.toFixed(8)}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400 mb-1">Amount</div>
                    <div className="text-sm text-white">
                      {trade.base_amount.toFixed(8)} {(position.product_id || 'ETH-BTC').split('-')[0]}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400 mb-1">Total</div>
                    <div className="text-sm text-white">
                      {trade.quote_amount.toFixed(8)} {(position.product_id || 'ETH-BTC').split('-')[1]}
                    </div>
                  </div>
                </div>
                <div className="mt-3 pt-3 border-t border-slate-600">
                  <div className="text-xs text-slate-400">
                    {formatDateTime(trade.timestamp)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <p className="text-slate-400">No trades found for this position</p>
          </div>
        )}

        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
