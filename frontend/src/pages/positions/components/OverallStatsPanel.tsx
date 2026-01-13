interface CompletedStats {
  total_profit_btc: number
  total_profit_usd: number
  win_rate: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  average_profit_usd: number
}

interface Balances {
  btc: number
  eth: number
  usd: number
  usdc: number
  usdt: number
  eth_value_in_btc: number
  total_btc_value: number
  current_eth_btc_price: number
  btc_usd_price: number
  total_usd_value: number
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
              <div className="flex gap-4">
                <span className="w-24 text-right" title="Funds locked in active positions">Reserved</span>
                <span className="w-24 text-right" title="Available balance in account">Available</span>
              </div>
            </div>
            {/* BTC - Always show */}
            <div className="flex justify-between">
              <span className="text-slate-300">BTC</span>
              <div className="flex gap-4">
                <span className="text-white w-24 text-right font-mono text-xs">
                  {(stats.reservedByQuote['BTC'] || 0).toFixed(8)}
                </span>
                <span className="text-white w-24 text-right font-mono text-xs">
                  {balances ? balances.btc.toFixed(8) : '...'}
                </span>
              </div>
            </div>
            {/* ETH - Always show */}
            <div className="flex justify-between">
              <span className="text-slate-300">ETH</span>
              <div className="flex gap-4">
                <span className="text-white w-24 text-right font-mono text-xs">
                  {(stats.reservedByQuote['ETH'] || 0).toFixed(6)}
                </span>
                <span className="text-white w-24 text-right font-mono text-xs">
                  {balances ? balances.eth.toFixed(6) : '...'}
                </span>
              </div>
            </div>
            {/* USD - Always show */}
            <div className="flex justify-between">
              <span className="text-slate-300">USD</span>
              <div className="flex gap-4">
                <span className="text-white w-24 text-right font-mono text-xs">
                  ${(stats.reservedByQuote['USD'] || 0).toFixed(2)}
                </span>
                <span className="text-white w-24 text-right font-mono text-xs">
                  {balances ? `$${balances.usd.toFixed(2)}` : '...'}
                </span>
              </div>
            </div>
            {/* USDC - Always show */}
            <div className="flex justify-between">
              <span className="text-slate-300">USDC</span>
              <div className="flex gap-4">
                <span className="text-white w-24 text-right font-mono text-xs">
                  ${(stats.reservedByQuote['USDC'] || 0).toFixed(2)}
                </span>
                <span className="text-white w-24 text-right font-mono text-xs">
                  {balances ? `$${balances.usdc.toFixed(2)}` : '...'}
                </span>
              </div>
            </div>
            {/* USDT - Always show */}
            <div className="flex justify-between">
              <span className="text-slate-300">USDT</span>
              <div className="flex gap-4">
                <span className="text-white w-24 text-right font-mono text-xs">
                  ${(stats.reservedByQuote['USDT'] || 0).toFixed(2)}
                </span>
                <span className="text-white w-24 text-right font-mono text-xs">
                  {balances ? `$${balances.usdt.toFixed(2)}` : '...'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
