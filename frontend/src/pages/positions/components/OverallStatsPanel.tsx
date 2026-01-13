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
    fundsLocked: number
    uPnL: number
    uPnLUSD: number
  }
  completedStats?: CompletedStats
}

export const OverallStatsPanel = ({ stats, completedStats }: OverallStatsPanelProps) => {
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
  )
}
