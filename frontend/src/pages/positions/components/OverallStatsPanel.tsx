import { Balances } from '../../../types'

interface CompletedStats {
  total_profit_btc: number
  total_profit_usd: number
  win_rate: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  average_profit_usd: number
}

interface OverallStatsPanelProps {
  stats: {
    activeTrades: number
    reservedByQuote: Record<string, number>
    uPnL: number
    uPnLUSD: number
  }
  completedStats?: CompletedStats
  balances?: Balances
  onRefreshBalances: () => void
}

export const OverallStatsPanel = ({ stats, completedStats, balances, onRefreshBalances }: OverallStatsPanelProps) => {
  return (
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
              <span className="text-slate-400">uPnL of active trades (BTC):</span>
              <span className={`font-medium ${stats.uPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {stats.uPnL >= 0 ? '+' : ''}{stats.uPnL.toFixed(8)} BTC
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">uPnL of active trades (USD):</span>
              <span className={`font-medium ${stats.uPnLUSD >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {stats.uPnLUSD >= 0 ? '+' : ''}${stats.uPnLUSD.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Completed Trades Profit */}
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Completed trades profit</h3>
          <div className="space-y-2 text-sm">
            {completedStats ? (
              <>
                <div className="flex justify-between">
                  <span className="text-slate-400">Total profit (USD):</span>
                  <span className={`font-medium ${completedStats.total_profit_usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${completedStats.total_profit_usd.toFixed(2)}
                  </span>
                </div>
                {completedStats.total_profit_btc !== 0 && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Total profit (BTC):</span>
                    <span className={`font-medium ${completedStats.total_profit_btc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {completedStats.total_profit_btc >= 0 ? '+' : ''}{completedStats.total_profit_btc.toFixed(8)} BTC
                    </span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-slate-400">Completed trades:</span>
                  <span className="text-white font-medium">{completedStats.total_trades}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Win rate:</span>
                  <span className={`font-medium ${completedStats.win_rate >= 50 ? 'text-green-400' : 'text-yellow-400'}`}>
                    {completedStats.win_rate.toFixed(1)}% ({completedStats.winning_trades}W / {completedStats.losing_trades}L)
                  </span>
                </div>
              </>
            ) : (
              <div className="text-slate-400">Loading...</div>
            )}
          </div>
        </div>

        {/* Balances */}
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center justify-between">
            Balances
            <button
              onClick={() => onRefreshBalances()}
              className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
            >
              🔄 Refresh
            </button>
          </h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between text-slate-400 text-xs">
              <span>Currency</span>
              <div className="flex gap-3">
                <span className="w-20 text-right" title="Locked in open positions">In Positions</span>
                <span className="w-20 text-right" title="Locked in pending orders (grids)">In Grids</span>
                <span className="w-20 text-right" title="Available for new bots">Available</span>
              </div>
            </div>
            {/* BTC - Always show */}
            <div className="flex justify-between">
              <span className="text-slate-300 font-medium">BTC</span>
              <div className="flex gap-3">
                <span className="text-amber-400 w-20 text-right font-mono text-xs">
                  {balances ? balances.reserved_in_positions.BTC.toFixed(8) : '...'}
                </span>
                <span className="text-purple-400 w-20 text-right font-mono text-xs">
                  {balances ? balances.reserved_in_pending_orders.BTC.toFixed(8) : '...'}
                </span>
                <span className="text-green-400 w-20 text-right font-mono text-xs font-semibold">
                  {balances ? balances.available_btc.toFixed(8) : '...'}
                </span>
              </div>
            </div>
            {/* ETH - Always show */}
            <div className="flex justify-between">
              <span className="text-slate-300 font-medium">ETH</span>
              <div className="flex gap-3">
                <span className="text-amber-400 w-20 text-right font-mono text-xs">
                  {balances ? balances.reserved_in_positions.ETH.toFixed(6) : '...'}
                </span>
                <span className="text-purple-400 w-20 text-right font-mono text-xs">
                  {balances ? balances.reserved_in_pending_orders.ETH.toFixed(6) : '...'}
                </span>
                <span className="text-green-400 w-20 text-right font-mono text-xs font-semibold">
                  {balances ? balances.available_eth.toFixed(6) : '...'}
                </span>
              </div>
            </div>
            {/* USD - Always show */}
            <div className="flex justify-between">
              <span className="text-slate-300 font-medium">USD</span>
              <div className="flex gap-3">
                <span className="text-amber-400 w-20 text-right font-mono text-xs">
                  ${balances ? balances.reserved_in_positions.USD.toFixed(2) : '...'}
                </span>
                <span className="text-purple-400 w-20 text-right font-mono text-xs">
                  ${balances ? balances.reserved_in_pending_orders.USD.toFixed(2) : '...'}
                </span>
                <span className="text-green-400 w-20 text-right font-mono text-xs font-semibold">
                  ${balances ? balances.available_usd.toFixed(2) : '...'}
                </span>
              </div>
            </div>
            {/* USDC - Always show */}
            <div className="flex justify-between">
              <span className="text-slate-300 font-medium">USDC</span>
              <div className="flex gap-3">
                <span className="text-amber-400 w-20 text-right font-mono text-xs">
                  ${balances ? balances.reserved_in_positions.USDC.toFixed(2) : '...'}
                </span>
                <span className="text-purple-400 w-20 text-right font-mono text-xs">
                  ${balances ? balances.reserved_in_pending_orders.USDC.toFixed(2) : '...'}
                </span>
                <span className="text-green-400 w-20 text-right font-mono text-xs font-semibold">
                  ${balances ? balances.available_usdc.toFixed(2) : '...'}
                </span>
              </div>
            </div>
            {/* USDT - Always show */}
            <div className="flex justify-between">
              <span className="text-slate-300 font-medium">USDT</span>
              <div className="flex gap-3">
                <span className="text-amber-400 w-20 text-right font-mono text-xs">
                  ${balances ? balances.reserved_in_positions.USDT.toFixed(2) : '...'}
                </span>
                <span className="text-purple-400 w-20 text-right font-mono text-xs">
                  ${balances ? balances.reserved_in_pending_orders.USDT.toFixed(2) : '...'}
                </span>
                <span className="text-green-400 w-20 text-right font-mono text-xs font-semibold">
                  ${balances ? balances.available_usdt.toFixed(2) : '...'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
