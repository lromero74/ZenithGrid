import { useQuery } from '@tanstack/react-query'
import { api } from '../../../services/api'

interface PerpsPosition {
  id: number
  product_id: string
  direction: string
  leverage: number
  entry_price: number
  unrealized_pnl: number | null
  tp_price: number | null
  sl_price: number | null
  liquidation_price: number | null
  notional_usdc: number
  opened_at: string
}

export default function PerpsPortfolioPanel() {
  const { data: portfolio } = useQuery({
    queryKey: ['perps-portfolio'],
    queryFn: async () => {
      const res = await api.get('/perps/portfolio')
      return res.data
    },
    retry: false,
    refetchInterval: 30000,
  })

  const { data: positionsData } = useQuery({
    queryKey: ['perps-positions'],
    queryFn: async () => {
      const res = await api.get('/perps/positions')
      return res.data
    },
    retry: false,
    refetchInterval: 15000,
  })

  const positions: PerpsPosition[] = positionsData?.positions || []
  const totalUnrealizedPnl = positions.reduce(
    (sum: number, p: PerpsPosition) => sum + (p.unrealized_pnl || 0),
    0
  )

  if (!portfolio && positions.length === 0) {
    return null
  }

  return (
    <div className="bg-slate-800/50 border border-purple-500/20 rounded-lg p-4 mb-4">
      <h3 className="text-sm font-semibold text-purple-400 mb-3 flex items-center gap-2">
        Perpetual Futures Portfolio
      </h3>

      <div className="grid grid-cols-4 gap-4 text-xs">
        {portfolio?.summary && (
          <>
            <div>
              <span className="text-slate-500">USDC Margin</span>
              <div className="text-white font-medium">
                ${parseFloat(portfolio.summary.total_margin || '0').toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </div>
            </div>
            <div>
              <span className="text-slate-500">Margin Used</span>
              <div className="text-yellow-400">
                ${parseFloat(portfolio.summary.margin_used || '0').toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </div>
            </div>
          </>
        )}
        <div>
          <span className="text-slate-500">Open Positions</span>
          <div className="text-white font-medium">{positions.length}</div>
        </div>
        <div>
          <span className="text-slate-500">Total uPnL</span>
          <div className={totalUnrealizedPnl >= 0 ? 'text-green-400 font-medium' : 'text-red-400 font-medium'}>
            {totalUnrealizedPnl >= 0 ? '+' : ''}{totalUnrealizedPnl.toFixed(2)} USDC
          </div>
        </div>
      </div>

      {positions.length > 0 && (
        <div className="mt-3 border-t border-slate-700 pt-2">
          <div className="space-y-1">
            {positions.map((p: PerpsPosition) => (
              <div key={p.id} className="flex items-center justify-between text-[10px] py-1">
                <div className="flex items-center gap-2">
                  <span className={p.direction === 'long' ? 'text-green-400' : 'text-red-400'}>
                    {p.direction.toUpperCase()}
                  </span>
                  <span className="text-white">{p.product_id}</span>
                  <span className="text-purple-400">{p.leverage}x</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-slate-400">${p.entry_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                  {p.unrealized_pnl != null && (
                    <span className={p.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                      {p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl.toFixed(2)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
