import { Balances } from '../../../types'
import { useState, useEffect } from 'react'

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
  daily_profit_by_quote: Record<string, number>
  yesterday_profit_btc: number
  yesterday_profit_usd: number
  yesterday_profit_by_quote: Record<string, number>
  last_week_profit_btc: number
  last_week_profit_usd: number
  last_week_profit_by_quote: Record<string, number>
  last_month_profit_btc: number
  last_month_profit_usd: number
  last_month_profit_by_quote: Record<string, number>
  last_quarter_profit_btc: number
  last_quarter_profit_usd: number
  last_quarter_profit_by_quote: Record<string, number>
  last_year_profit_btc: number
  last_year_profit_usd: number
  last_year_profit_by_quote: Record<string, number>
  wtd_profit_btc: number
  wtd_profit_usd: number
  wtd_profit_by_quote: Record<string, number>
  mtd_profit_btc: number
  mtd_profit_usd: number
  mtd_profit_by_quote: Record<string, number>
  qtd_profit_btc: number
  qtd_profit_usd: number
  qtd_profit_by_quote: Record<string, number>
  ytd_profit_btc: number
  ytd_profit_usd: number
  ytd_profit_by_quote: Record<string, number>
  alltime_profit_btc: number
  alltime_profit_usd: number
  alltime_profit_by_quote: Record<string, number>
}

interface OverallStatsPanelProps {
  stats: {
    activeTrades: number
    reservedByQuote: Record<string, number>
    totalBudgetByQuote: Record<string, number>
    uPnLByQuote: Record<string, number>
    uPnLUSD: number
  }
  completedStats?: CompletedStats
  realizedPnL?: RealizedPnL
  balances?: Balances
  onRefreshBalances: () => void
}

export const OverallStatsPanel = ({ stats, completedStats, realizedPnL, balances, onRefreshBalances }: OverallStatsPanelProps) => {
  const [selectedHistorical, setSelectedHistorical] = useState<'yesterday' | 'last_week' | 'last_month' | 'last_quarter' | 'last_year'>(() => {
    try { return (localStorage.getItem('zenith-stats-historical') as any) || 'last_week' } catch { return 'last_week' }
  })
  const [selectedToDate, setSelectedToDate] = useState<'wtd' | 'mtd' | 'qtd' | 'ytd'>(() => {
    try { return (localStorage.getItem('zenith-stats-to-date') as any) || 'ytd' } catch { return 'ytd' }
  })
  const [selectedCumulative, setSelectedCumulative] = useState<'alltime' | 'net'>(() => {
    try { return (localStorage.getItem('zenith-stats-cumulative') as any) || 'alltime' } catch { return 'alltime' }
  })

  useEffect(() => { try { localStorage.setItem('zenith-stats-historical', selectedHistorical) } catch { /* ignored */ } }, [selectedHistorical])
  useEffect(() => { try { localStorage.setItem('zenith-stats-to-date', selectedToDate) } catch { /* ignored */ } }, [selectedToDate])
  useEffect(() => { try { localStorage.setItem('zenith-stats-cumulative', selectedCumulative) } catch { /* ignored */ } }, [selectedCumulative])

  const emptyPeriod = { byQuote: {} as Record<string, number>, usd: 0 }

  // Get the selected historical period's data
  const getHistoricalData = () => {
    if (!realizedPnL) return emptyPeriod
    switch (selectedHistorical) {
      case 'yesterday':
        return { byQuote: realizedPnL.yesterday_profit_by_quote || {}, usd: realizedPnL.yesterday_profit_usd }
      case 'last_week':
        return { byQuote: realizedPnL.last_week_profit_by_quote || {}, usd: realizedPnL.last_week_profit_usd }
      case 'last_month':
        return { byQuote: realizedPnL.last_month_profit_by_quote || {}, usd: realizedPnL.last_month_profit_usd }
      case 'last_quarter':
        return { byQuote: realizedPnL.last_quarter_profit_by_quote || {}, usd: realizedPnL.last_quarter_profit_usd }
      case 'last_year':
        return { byQuote: realizedPnL.last_year_profit_by_quote || {}, usd: realizedPnL.last_year_profit_usd }
    }
  }

  // Get the selected to-date period's data
  const getToDateData = () => {
    if (!realizedPnL) return emptyPeriod
    switch (selectedToDate) {
      case 'wtd':
        return { byQuote: realizedPnL.wtd_profit_by_quote || {}, usd: realizedPnL.wtd_profit_usd }
      case 'mtd':
        return { byQuote: realizedPnL.mtd_profit_by_quote || {}, usd: realizedPnL.mtd_profit_usd }
      case 'qtd':
        return { byQuote: realizedPnL.qtd_profit_by_quote || {}, usd: realizedPnL.qtd_profit_usd }
      case 'ytd':
        return { byQuote: realizedPnL.ytd_profit_by_quote || {}, usd: realizedPnL.ytd_profit_usd }
    }
  }

  // Get cumulative (all-time or net) data
  const getCumulativeData = () => {
    if (!realizedPnL) return emptyPeriod
    const allByQuote = realizedPnL.alltime_profit_by_quote || {}
    const allUsd = realizedPnL.alltime_profit_usd ?? 0
    if (selectedCumulative === 'alltime') {
      return { byQuote: allByQuote, usd: allUsd }
    }
    // Net = all-time realized + current uPnL, merged per quote currency
    const merged: Record<string, number> = { ...allByQuote }
    for (const [currency, amount] of Object.entries(stats.uPnLByQuote)) {
      merged[currency] = (merged[currency] || 0) + amount
    }
    return { byQuote: merged, usd: allUsd + stats.uPnLUSD }
  }

  // Render per-quote breakdown with independent colors + pipe divider + USD total
  const renderPnLBreakdown = (data: { byQuote: Record<string, number>, usd: number }) => {
    const isUsdLike = (c: string) => c === 'USD' || c === 'USDC' || c === 'USDT'
    const entries = Object.entries(data.byQuote).sort(([a], [b]) => a.localeCompare(b))
    return (
      <span className="font-medium text-xs flex flex-wrap justify-end gap-x-1">
        {entries.map(([currency, amount], i) => (
          <span key={currency} className={amount >= 0 ? 'text-green-400' : 'text-red-400'}>
            {i > 0 && <span className="text-slate-500">, </span>}
            {amount >= 0 ? '+' : ''}
            {isUsdLike(currency) ? `$${Math.abs(amount).toFixed(2)}` : amount.toFixed(8)}
            {' '}{currency}
          </span>
        ))}
        {entries.length > 0 && <span className="text-slate-500"> | </span>}
        <span className={data.usd >= 0 ? 'text-green-400' : 'text-red-400'}>
          {data.usd >= 0 ? '+' : ''}${data.usd.toFixed(2)}
        </span>
      </span>
    )
  }

  const historicalData = getHistoricalData()
  const toDateData = getToDateData()
  const cumulativeData = getCumulativeData()

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-3 sm:p-6 mb-4">
      <div className="grid grid-cols-1 md:grid-cols-[2fr_1.2fr_2fr] gap-6">
        {/* Overall Stats */}
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Overall stats</h3>
          <div className="space-y-2 text-sm">
            <div className="flex flex-wrap justify-between items-baseline gap-x-2">
              <span className="text-slate-400 text-xs">Active trades:</span>
              <span className="text-white font-medium text-xs">{stats.activeTrades}</span>
            </div>
            <div className="flex flex-wrap justify-between items-baseline gap-x-2">
              <span className="text-slate-400 text-xs flex-shrink-0">uPnL (active):</span>
              {renderPnLBreakdown({ byQuote: stats.uPnLByQuote, usd: stats.uPnLUSD })}
            </div>
            {realizedPnL && (
              <>
                <div className="flex flex-wrap justify-between items-baseline gap-x-2">
                  <span className="text-slate-400 text-xs flex-shrink-0">Realized (today):</span>
                  {renderPnLBreakdown({ byQuote: realizedPnL.daily_profit_by_quote || {}, usd: realizedPnL.daily_profit_usd })}
                </div>
                <div className="flex flex-wrap justify-between items-baseline gap-x-2">
                  <span className="text-slate-400 text-xs flex items-center gap-1 flex-shrink-0">
                    Realized (
                    <select
                      value={selectedHistorical}
                      onChange={(e) => setSelectedHistorical(e.target.value as 'yesterday' | 'last_week' | 'last_month' | 'last_quarter' | 'last_year')}
                      className="bg-slate-700 text-slate-300 border border-slate-600 rounded px-1 py-0.5 text-xs cursor-pointer hover:bg-slate-600"
                    >
                      <option value="yesterday">Yesterday</option>
                      <option value="last_week">Last Week</option>
                      <option value="last_month">Last Month</option>
                      <option value="last_quarter">Last Quarter</option>
                      <option value="last_year">Last Year</option>
                    </select>
                    ):
                  </span>
                  {renderPnLBreakdown(historicalData)}
                </div>
                <div className="flex flex-wrap justify-between items-baseline gap-x-2">
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
                  {renderPnLBreakdown(toDateData)}
                </div>
                <div className="flex flex-wrap justify-between items-baseline gap-x-2">
                  <span className="text-slate-400 text-xs flex items-center gap-1 flex-shrink-0">
                    <select
                      value={selectedCumulative}
                      onChange={(e) => setSelectedCumulative(e.target.value as 'alltime' | 'net')}
                      className="bg-slate-700 text-slate-300 border border-slate-600 rounded px-1 py-0.5 text-xs cursor-pointer hover:bg-slate-600"
                    >
                      <option value="alltime">All-Time</option>
                      <option value="net">Net (All-Time + uPnL)</option>
                    </select>
                    :
                  </span>
                  {renderPnLBreakdown(cumulativeData)}
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
                <div className="flex flex-wrap justify-between items-baseline gap-x-2">
                  <span className="text-slate-400 text-xs">Total profit (USD):</span>
                  <span className={`font-medium text-xs ${completedStats.total_profit_usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${completedStats.total_profit_usd.toFixed(2)}
                  </span>
                </div>
                {completedStats.total_profit_btc !== 0 && (
                  <div className="flex flex-wrap justify-between items-baseline gap-x-2">
                    <span className="text-slate-400 text-xs">Total profit (BTC):</span>
                    <span className={`font-medium text-xs ${completedStats.total_profit_btc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {completedStats.total_profit_btc >= 0 ? '+' : ''}{completedStats.total_profit_btc.toFixed(8)} BTC
                    </span>
                  </div>
                )}
                <div className="flex flex-wrap justify-between items-baseline gap-x-2">
                  <span className="text-slate-400 text-xs">Completed trades:</span>
                  <span className="text-white font-medium text-xs">{completedStats.total_trades}</span>
                </div>
                <div className="flex flex-wrap justify-between items-baseline gap-x-2">
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
            <div className="flex items-baseline text-slate-400 text-xs gap-1.5 sm:gap-3">
              <span className="w-10 sm:w-14 flex-shrink-0">Currency</span>
              <span className="w-[52px] sm:w-20 text-right flex-shrink-0" title="Total assigned budget (sum of max budget per deal)">Budget</span>
              <span className="w-[52px] sm:w-20 text-right flex-shrink-0" title="Locked in open positions">In Pos.</span>
              <span className="hidden sm:inline w-20 text-right flex-shrink-0" title="Locked in pending orders (grids)">In Grids</span>
              <span className="w-[52px] sm:w-20 text-right flex-shrink-0" title="Available for new bots">Available</span>
            </div>
            {/* BTC - Always show */}
            <div className="flex items-baseline gap-1.5 sm:gap-3">
              <span className="text-slate-300 font-medium text-xs w-10 sm:w-14 flex-shrink-0">BTC</span>
              <span className="text-blue-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs flex-shrink-0">
                {(stats.totalBudgetByQuote.BTC || 0).toFixed(6)}
              </span>
              <span className="text-amber-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs flex-shrink-0">
                {balances ? balances.reserved_in_positions.BTC.toFixed(6) : '...'}
              </span>
              <span className="hidden sm:inline text-purple-400 w-20 text-right font-mono text-xs flex-shrink-0">
                {balances ? balances.reserved_in_pending_orders.BTC.toFixed(6) : '...'}
              </span>
              <span className="text-green-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs font-semibold flex-shrink-0">
                {balances ? balances.available_btc.toFixed(6) : '...'}
              </span>
            </div>
            {/* ETH - Always show */}
            <div className="flex items-baseline gap-1.5 sm:gap-3">
              <span className="text-slate-300 font-medium text-xs w-10 sm:w-14 flex-shrink-0">ETH</span>
              <span className="text-blue-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs flex-shrink-0">
                {(stats.totalBudgetByQuote.ETH || 0).toFixed(6)}
              </span>
              <span className="text-amber-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs flex-shrink-0">
                {balances ? balances.reserved_in_positions.ETH.toFixed(6) : '...'}
              </span>
              <span className="hidden sm:inline text-purple-400 w-20 text-right font-mono text-xs flex-shrink-0">
                {balances ? balances.reserved_in_pending_orders.ETH.toFixed(6) : '...'}
              </span>
              <span className="text-green-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs font-semibold flex-shrink-0">
                {balances ? balances.available_eth.toFixed(6) : '...'}
              </span>
            </div>
            {/* USD - Always show */}
            <div className="flex items-baseline gap-1.5 sm:gap-3">
              <span className="text-slate-300 font-medium text-xs w-10 sm:w-14 flex-shrink-0">USD</span>
              <span className="text-blue-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs flex-shrink-0">
                ${(stats.totalBudgetByQuote.USD || 0).toFixed(2)}
              </span>
              <span className="text-amber-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs flex-shrink-0">
                ${balances ? balances.reserved_in_positions.USD.toFixed(2) : '...'}
              </span>
              <span className="hidden sm:inline text-purple-400 w-20 text-right font-mono text-xs flex-shrink-0">
                ${balances ? balances.reserved_in_pending_orders.USD.toFixed(2) : '...'}
              </span>
              <span className="text-green-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs font-semibold flex-shrink-0">
                ${balances ? balances.available_usd.toFixed(2) : '...'}
              </span>
            </div>
            {/* USDC - Always show */}
            <div className="flex items-baseline gap-1.5 sm:gap-3">
              <span className="text-slate-300 font-medium text-xs w-10 sm:w-14 flex-shrink-0">USDC</span>
              <span className="text-blue-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs flex-shrink-0">
                ${(stats.totalBudgetByQuote.USDC || 0).toFixed(2)}
              </span>
              <span className="text-amber-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs flex-shrink-0">
                ${balances ? balances.reserved_in_positions.USDC.toFixed(2) : '...'}
              </span>
              <span className="hidden sm:inline text-purple-400 w-20 text-right font-mono text-xs flex-shrink-0">
                ${balances ? balances.reserved_in_pending_orders.USDC.toFixed(2) : '...'}
              </span>
              <span className="text-green-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs font-semibold flex-shrink-0">
                ${balances ? balances.available_usdc.toFixed(2) : '...'}
              </span>
            </div>
            {/* USDT - Always show */}
            <div className="flex items-baseline gap-1.5 sm:gap-3">
              <span className="text-slate-300 font-medium text-xs w-10 sm:w-14 flex-shrink-0">USDT</span>
              <span className="text-blue-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs flex-shrink-0">
                ${(stats.totalBudgetByQuote.USDT || 0).toFixed(2)}
              </span>
              <span className="text-amber-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs flex-shrink-0">
                ${balances ? balances.reserved_in_positions.USDT.toFixed(2) : '...'}
              </span>
              <span className="hidden sm:inline text-purple-400 w-20 text-right font-mono text-xs flex-shrink-0">
                ${balances ? balances.reserved_in_pending_orders.USDT.toFixed(2) : '...'}
              </span>
              <span className="text-green-400 w-[52px] sm:w-20 text-right font-mono text-[10px] sm:text-xs font-semibold flex-shrink-0">
                ${balances ? balances.available_usdt.toFixed(2) : '...'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
