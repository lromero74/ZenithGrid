import { Balances } from '../../../types'
import { useState } from 'react'

interface CompletedStats {
  total_profit_btc: number
  total_profit_usd: number
  win_rate: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  average_profit_usd: number
}

interface RealizedPnL {
  daily_profit_btc: number
  daily_profit_usd: number
  yesterday_profit_btc: number
  yesterday_profit_usd: number
  last_week_profit_btc: number
  last_week_profit_usd: number
  last_month_profit_btc: number
  last_month_profit_usd: number
  last_quarter_profit_btc: number
  last_quarter_profit_usd: number
  wtd_profit_btc: number
  wtd_profit_usd: number
  mtd_profit_btc: number
  mtd_profit_usd: number
  qtd_profit_btc: number
  qtd_profit_usd: number
  ytd_profit_btc: number
  ytd_profit_usd: number
}

interface OverallStatsPanelProps {
  stats: {
    activeTrades: number
    reservedByQuote: Record<string, number>
    uPnL: number
    uPnLUSD: number
  }
  completedStats?: CompletedStats
  realizedPnL?: RealizedPnL
  balances?: Balances
  onRefreshBalances: () => void
}

export const OverallStatsPanel = ({ stats, completedStats, realizedPnL, balances, onRefreshBalances }: OverallStatsPanelProps) => {
  const [selectedHistorical, setSelectedHistorical] = useState<'yesterday' | 'last_week' | 'last_month' | 'last_quarter'>('last_week')
  const [selectedToDate, setSelectedToDate] = useState<'wtd' | 'mtd' | 'qtd' | 'ytd'>('ytd')

  // Get the selected historical period's data
  const getHistoricalData = () => {
    if (!realizedPnL) return { btc: 0, usd: 0 }
    switch (selectedHistorical) {
      case 'yesterday':
        return { btc: realizedPnL.yesterday_profit_btc, usd: realizedPnL.yesterday_profit_usd }
      case 'last_week':
        return { btc: realizedPnL.last_week_profit_btc, usd: realizedPnL.last_week_profit_usd }
      case 'last_month':
        return { btc: realizedPnL.last_month_profit_btc, usd: realizedPnL.last_month_profit_usd }
      case 'last_quarter':
        return { btc: realizedPnL.last_quarter_profit_btc, usd: realizedPnL.last_quarter_profit_usd }
    }
  }

  // Get the selected to-date period's data
  const getToDateData = () => {
    if (!realizedPnL) return { btc: 0, usd: 0 }
    switch (selectedToDate) {
      case 'wtd':
        return { btc: realizedPnL.wtd_profit_btc, usd: realizedPnL.wtd_profit_usd }
      case 'mtd':
        return { btc: realizedPnL.mtd_profit_btc, usd: realizedPnL.mtd_profit_usd }
      case 'qtd':
        return { btc: realizedPnL.qtd_profit_btc, usd: realizedPnL.qtd_profit_usd }
      case 'ytd':
        return { btc: realizedPnL.ytd_profit_btc, usd: realizedPnL.ytd_profit_usd }
    }
  }

  const historicalData = getHistoricalData()
  const toDateData = getToDateData()

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 mb-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Overall Stats */}
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Overall stats</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between items-baseline">
              <span className="text-slate-400 text-xs">Active trades:</span>
              <span className="text-white font-medium text-xs">{stats.activeTrades}</span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-slate-400 text-xs">uPnL (active):</span>
              <span className={`font-medium text-xs ${stats.uPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {stats.uPnL >= 0 ? '+' : ''}{stats.uPnL.toFixed(8)} BTC / {stats.uPnLUSD >= 0 ? '+' : ''}${stats.uPnLUSD.toFixed(2)}
              </span>
            </div>
            {realizedPnL && (
              <>
                <div className="flex justify-between items-baseline">
                  <span className="text-slate-400 text-xs">Realized (today):</span>
                  <span className={`font-medium text-xs ${realizedPnL.daily_profit_btc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {realizedPnL.daily_profit_btc >= 0 ? '+' : ''}{realizedPnL.daily_profit_btc.toFixed(8)} BTC / {realizedPnL.daily_profit_usd >= 0 ? '+' : ''}${realizedPnL.daily_profit_usd.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between items-baseline gap-2">
                  <span className="text-slate-400 text-xs flex items-center gap-1 flex-shrink-0">
                    Realized (
                    <select
                      value={selectedHistorical}
                      onChange={(e) => setSelectedHistorical(e.target.value as 'yesterday' | 'last_week' | 'last_month' | 'last_quarter')}
                      className="bg-slate-700 text-slate-300 border border-slate-600 rounded px-1 py-0.5 text-xs cursor-pointer hover:bg-slate-600"
                    >
                      <option value="yesterday">Yesterday</option>
                      <option value="last_week">Last Week</option>
                      <option value="last_month">Last Month</option>
                      <option value="last_quarter">Last Quarter</option>
                    </select>
                    ):
                  </span>
                  <span className={`font-medium text-xs ${historicalData.btc >= 0 ? 'text-green-400' : 'text-red-400'} whitespace-nowrap`}>
                    {historicalData.btc >= 0 ? '+' : ''}{historicalData.btc.toFixed(8)} BTC / {historicalData.usd >= 0 ? '+' : ''}${historicalData.usd.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between items-baseline gap-2">
                  <span className="text-slate-400 text-xs flex items-center gap-1 flex-shrink-0">
                    Realized (
                    <select
                      value={selectedToDate}
                      onChange={(e) => setSelectedToDate(e.target.value as 'wtd' | 'mtd' | 'qtd' | 'ytd')}
                      className="bg-slate-700 text-slate-300 border border-slate-600 rounded px-1 py-0.5 text-xs cursor-pointer hover:bg-slate-600"
                    >
                      <option value="wtd">WTD</option>
                      <option value="mtd">MTD</option>
                      <option value="qtd">QTD</option>
                      <option value="ytd">YTD</option>
                    </select>
                    ):
                  </span>
                  <span className={`font-medium text-xs ${toDateData.btc >= 0 ? 'text-green-400' : 'text-red-400'} whitespace-nowrap`}>
                    {toDateData.btc >= 0 ? '+' : ''}{toDateData.btc.toFixed(8)} BTC / {toDateData.usd >= 0 ? '+' : ''}${toDateData.usd.toFixed(2)}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Completed Trades Profit */}
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Completed trades profit</h3>
          <div className="space-y-2">
            {completedStats ? (
              <>
                <div className="flex justify-between items-baseline">
                  <span className="text-slate-400 text-xs">Total profit (USD):</span>
                  <span className={`font-medium text-xs ${completedStats.total_profit_usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${completedStats.total_profit_usd.toFixed(2)}
                  </span>
                </div>
                {completedStats.total_profit_btc !== 0 && (
                  <div className="flex justify-between items-baseline">
                    <span className="text-slate-400 text-xs">Total profit (BTC):</span>
                    <span className={`font-medium text-xs ${completedStats.total_profit_btc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {completedStats.total_profit_btc >= 0 ? '+' : ''}{completedStats.total_profit_btc.toFixed(8)} BTC
                    </span>
                  </div>
                )}
                <div className="flex justify-between items-baseline">
                  <span className="text-slate-400 text-xs">Completed trades:</span>
                  <span className="text-white font-medium text-xs">{completedStats.total_trades}</span>
                </div>
                <div className="flex justify-between items-baseline">
                  <span className="text-slate-400 text-xs">Win rate:</span>
                  <span className={`font-medium text-xs ${completedStats.win_rate >= 50 ? 'text-green-400' : 'text-yellow-400'}`}>
                    {completedStats.win_rate.toFixed(1)}% ({completedStats.winning_trades}W / {completedStats.losing_trades}L)
                  </span>
                </div>
              </>
            ) : (
              <div className="text-slate-400 text-xs">Loading...</div>
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
          <div className="space-y-2">
            <div className="flex justify-between text-slate-400 text-xs">
              <span>Currency</span>
              <div className="flex gap-3">
                <span className="w-20 text-right" title="Locked in open positions">In Positions</span>
                <span className="w-20 text-right" title="Locked in pending orders (grids)">In Grids</span>
                <span className="w-20 text-right" title="Available for new bots">Available</span>
              </div>
            </div>
            {/* BTC - Always show */}
            <div className="flex justify-between items-baseline">
              <span className="text-slate-300 font-medium text-xs">BTC</span>
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
            <div className="flex justify-between items-baseline">
              <span className="text-slate-300 font-medium text-xs">ETH</span>
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
            <div className="flex justify-between items-baseline">
              <span className="text-slate-300 font-medium text-xs">USD</span>
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
            <div className="flex justify-between items-baseline">
              <span className="text-slate-300 font-medium text-xs">USDC</span>
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
            <div className="flex justify-between items-baseline">
              <span className="text-slate-300 font-medium text-xs">USDT</span>
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
