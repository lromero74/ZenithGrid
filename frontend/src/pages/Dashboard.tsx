import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { botsApi, positionsApi, authFetch } from '../services/api'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Play,
  Square,
  Bot as BotIcon,
  Target,
  Award,
  Clock,
  Building2,
  Wallet,
  Shield,
  AlertTriangle
} from 'lucide-react'
import { Bot } from '../types'
import { format } from 'date-fns'
import { useNavigate } from 'react-router-dom'
import { useAccount, getChainName } from '../contexts/AccountContext'
import { AccountValueChart } from '../components/AccountValueChart'

type Page = 'dashboard' | 'bots' | 'positions' | 'portfolio' | 'charts' | 'strategies' | 'settings'

interface DashboardProps {
  onNavigate: (page: Page) => void
}

export default function Dashboard({ onNavigate }: DashboardProps) {
  const { selectedAccount } = useAccount()

  const [showStoppedBots, setShowStoppedBots] = useState(() => {
    try { return localStorage.getItem('zenith-show-stopped-bots') !== 'false' } catch { return true }
  })
  useEffect(() => { try { localStorage.setItem('zenith-show-stopped-bots', String(showStoppedBots)) } catch { /* ignored */ } }, [showStoppedBots])

  const [projectionBasis, setProjectionBasis] = useState<string>(() => {
    try { return localStorage.getItem('zenith-bots-projection-basis') || '7d' } catch { return '7d' }
  })
  useEffect(() => { try { localStorage.setItem('zenith-bots-projection-basis', projectionBasis) } catch { /* ignored */ } }, [projectionBasis])

  // Fetch all bots with projection data (filtered by account if selected)
  const { data: bots = [] } = useQuery({
    queryKey: ['dashboard-bots', selectedAccount?.id, projectionBasis],
    queryFn: () => botsApi.getAll(projectionBasis),
    refetchInterval: 30000,
    staleTime: 15000,
    select: (data) => {
      if (!selectedAccount) return data
      return data.filter((bot: Bot) => bot.account_id === selectedAccount.id)
    },
  })

  // Fetch open positions for active deals count
  const { data: openPositions = [] } = useQuery({
    queryKey: ['open-positions', selectedAccount?.id],
    queryFn: () => positionsApi.getAll('open', 100),
    refetchInterval: 30000, // 30 seconds
    select: (data) => {
      if (!selectedAccount) return data
      // Filter by account_id
      return data.filter((p: any) => p.account_id === selectedAccount.id)
    },
  })

  // Fetch closed positions for profit/win rate metrics (high limit to get all)
  const { data: closedPositions = [] } = useQuery({
    queryKey: ['closed-positions', selectedAccount?.id],
    queryFn: () => positionsApi.getAll('closed', 1000),
    refetchInterval: 30000, // 30 seconds
    select: (data) => {
      if (!selectedAccount) return data
      // Filter by account_id
      return data.filter((p: any) => p.account_id === selectedAccount.id)
    },
  })

  // Combine for recent deals display
  const allPositions = [...openPositions, ...closedPositions]

  // Fetch portfolio for account value - account-specific for CEX/DEX switching
  const { data: portfolio } = useQuery({
    queryKey: ['account-portfolio', selectedAccount?.id],
    queryFn: async () => {
      // If we have a selected account, use the account-specific endpoint
      if (selectedAccount) {
        const response = await authFetch(`/api/accounts/${selectedAccount.id}/portfolio`)
        if (!response.ok) throw new Error('Failed to fetch portfolio')
        return response.json()
      }
      // Fallback to legacy endpoint
      const response = await authFetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 120000, // Match header timing
    staleTime: 60000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })

  // Fetch bidirectional bot reservations
  const { data: reservations } = useQuery({
    queryKey: ['account-reservations', selectedAccount?.id],
    queryFn: async () => {
      if (!selectedAccount) return null
      const response = await authFetch(`/api/account-value/reservations?account_id=${selectedAccount.id}`)
      if (!response.ok) throw new Error('Failed to fetch reservations')
      return response.json()
    },
    enabled: !!selectedAccount,
    refetchInterval: 30000, // 30 seconds
    staleTime: 15000,
  })

  // Fetch PropGuard status for prop firm accounts
  const isPropFirm = !!selectedAccount?.prop_firm
  const { data: propGuardStatus } = useQuery({
    queryKey: ['propguard-status', selectedAccount?.id],
    queryFn: async () => {
      if (!selectedAccount?.id) return null
      const response = await authFetch(`/api/propguard/${selectedAccount.id}/status`)
      if (!response.ok) return null
      return response.json()
    },
    enabled: isPropFirm && !!selectedAccount?.id,
    refetchInterval: 30000,
  })

  const activeBots = bots.filter(bot => bot.is_active)

  // Calculate total profit (USD is normalized across all bots)
  const totalProfitUSD = closedPositions.reduce((sum, p) => sum + (p.profit_usd || 0), 0)

  // Calculate total BTC profit (only from BTC-based positions)
  const totalProfitBTC = closedPositions
    .filter(p => p.product_id && p.product_id.endsWith('-BTC'))
    .reduce((sum, p) => sum + (p.profit_quote || 0), 0)

  // Calculate win rate (use profit_usd as normalized metric)
  const profitablePositions = closedPositions.filter(p => (p.profit_usd || 0) > 0)
  const winRate = closedPositions.length > 0
    ? (profitablePositions.length / closedPositions.length) * 100
    : 0

  // Recent deals (last 5)
  const recentDeals = [...allPositions]
    .sort((a, b) => new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime())
    .slice(0, 5)

  const formatCrypto = (amount: number | undefined | null, decimals: number = 8) => (amount ?? 0).toFixed(decimals)
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {selectedAccount?.type === 'dex' ? (
            <Wallet className="w-8 h-8 text-orange-400" />
          ) : (
            <Building2 className="w-8 h-8 text-blue-400" />
          )}
          <div>
            <h2 className="text-3xl font-bold text-white">Dashboard</h2>
            <p className="text-slate-400 text-sm mt-1">
              {selectedAccount && (
                <span className="text-slate-300">{selectedAccount.name}</span>
              )}
              {selectedAccount?.type === 'dex' && selectedAccount.chain_id && (
                <span className="text-slate-500"> ({getChainName(selectedAccount.chain_id)})</span>
              )}
              {selectedAccount && ' • '}
              {activeBots.length} active bot{activeBots.length !== 1 ? 's' : ''} • {openPositions.length} open deal{openPositions.length !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
      </div>

      {/* Performance Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Profit */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <p className="text-slate-400 text-sm font-medium">Total Profit</p>
            {totalProfitUSD >= 0 ? (
              <TrendingUp className="w-5 h-5 text-green-500" />
            ) : (
              <TrendingDown className="w-5 h-5 text-red-500" />
            )}
          </div>
          <p className={`text-2xl font-bold ${totalProfitUSD >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {totalProfitUSD >= 0 ? '+' : ''}{formatCurrency(totalProfitUSD)}
          </p>
          {totalProfitBTC !== 0 && (
            <p className={`text-sm mt-1 ${totalProfitBTC >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
              {totalProfitBTC >= 0 ? '+' : ''}{formatCrypto(totalProfitBTC, 8)} BTC
            </p>
          )}
        </div>

        {/* Win Rate */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <p className="text-slate-400 text-sm font-medium">Win Rate</p>
            <Award className="w-5 h-5 text-blue-500" />
          </div>
          <p className="text-2xl font-bold text-white">
            {winRate.toFixed(1)}%
          </p>
          <p className="text-sm text-slate-400 mt-1">
            {profitablePositions.length} / {closedPositions.length} deals
          </p>
        </div>

        {/* Active Deals */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <p className="text-slate-400 text-sm font-medium">Active Deals</p>
            <Target className="w-5 h-5 text-orange-500" />
          </div>
          <p className="text-2xl font-bold text-white">
            {openPositions.length}
          </p>
          <p className="text-sm text-slate-400 mt-1">
            {closedPositions.length} closed
          </p>
        </div>

        {/* Account Value */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <p className="text-slate-400 text-sm font-medium">Account Value</p>
            <DollarSign className="w-5 h-5 text-green-500" />
          </div>
          <p className="text-2xl font-bold text-white">
            {formatCrypto(portfolio?.total_btc_value || 0, 6)} BTC
          </p>
          <p className="text-sm text-slate-400 mt-1">
            {formatCurrency(portfolio?.total_usd_value || 0)}
          </p>

          {/* Bidirectional Reservations Breakdown */}
          {reservations && (reservations.reserved_usd > 0 || reservations.reserved_btc > 0) && (
            <div className="mt-3 pt-3 border-t border-slate-700 space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-500">Available USD:</span>
                <span className="text-white font-mono">{formatCurrency(reservations.available_usd)}</span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-500">Reserved (Grid):</span>
                <span className="text-yellow-400 font-mono">{formatCurrency(reservations.reserved_usd)}</span>
              </div>
              <div className="flex justify-between items-center text-xs mt-2 pt-2 border-t border-slate-700/50">
                <span className="text-slate-500">Available BTC:</span>
                <span className="text-white font-mono">{formatCrypto(reservations.available_btc, 8)} BTC</span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-500">Reserved (Grid):</span>
                <span className="text-yellow-400 font-mono">{formatCrypto(reservations.reserved_btc, 8)} BTC</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* PropGuard Status (prop firm accounts only) */}
      {isPropFirm && propGuardStatus && (
        <div className={`rounded-lg p-4 border ${propGuardStatus.is_killed ? 'bg-red-900/20 border-red-700/50' : 'bg-slate-800 border-slate-700'}`}>
          <div className="flex items-center gap-2 mb-3">
            <Shield className={`w-5 h-5 ${propGuardStatus.is_killed ? 'text-red-400' : 'text-green-400'}`} />
            <span className="text-sm font-semibold text-white">PropGuard</span>
            <span className="px-1.5 py-0.5 text-[10px] font-medium bg-purple-500/20 text-purple-300 rounded">
              {(selectedAccount?.prop_firm || '').toUpperCase()}
            </span>
            <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded ${propGuardStatus.is_killed ? 'bg-red-500/20 text-red-300 animate-pulse' : 'bg-green-500/20 text-green-300'}`}>
              {propGuardStatus.is_killed ? 'KILLED' : 'ACTIVE'}
            </span>
          </div>

          {propGuardStatus.is_killed && propGuardStatus.kill_reason && (
            <div className="flex items-center gap-2 mb-3 p-2 bg-red-900/30 rounded text-xs text-red-300">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{propGuardStatus.kill_reason}</span>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-slate-400 text-xs">Equity</p>
              <p className="text-white font-mono text-sm">{formatCurrency(propGuardStatus.current_equity || 0)}</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs">Initial Deposit</p>
              <p className="text-slate-300 font-mono text-sm">{formatCurrency(propGuardStatus.initial_deposit || 0)}</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs">Daily Drawdown</p>
              <p className={`font-mono text-sm ${(propGuardStatus.daily_drawdown_pct || 0) > (propGuardStatus.daily_drawdown_limit || 4.5) * 0.8 ? 'text-red-400' : (propGuardStatus.daily_drawdown_pct || 0) > (propGuardStatus.daily_drawdown_limit || 4.5) * 0.5 ? 'text-yellow-400' : 'text-green-400'}`}>
                {(propGuardStatus.daily_drawdown_pct || 0).toFixed(2)}% / {(propGuardStatus.daily_drawdown_limit || 4.5)}%
              </p>
            </div>
            <div>
              <p className="text-slate-400 text-xs">Total Drawdown</p>
              <p className={`font-mono text-sm ${(propGuardStatus.total_drawdown_pct || 0) > (propGuardStatus.total_drawdown_limit || 9.0) * 0.8 ? 'text-red-400' : (propGuardStatus.total_drawdown_pct || 0) > (propGuardStatus.total_drawdown_limit || 9.0) * 0.5 ? 'text-yellow-400' : 'text-green-400'}`}>
                {(propGuardStatus.total_drawdown_pct || 0).toFixed(2)}% / {(propGuardStatus.total_drawdown_limit || 9.0)}%
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Portfolio Totals - Projected PnL */}
      {bots.length > 0 && (() => {
        const filteredBots = bots.filter((b: Bot) => showStoppedBots || b.is_active)
        const totalDailyPnl = filteredBots.reduce((sum: number, bot: Bot) => sum + ((bot as any).avg_daily_pnl_usd || 0), 0)
        const portfolioUsd = portfolio?.total_usd_value || 0
        const dailyRate = portfolioUsd > 0 ? totalDailyPnl / portfolioUsd : 0
        const projectPnl = (days: number) => totalDailyPnl * days
        const totalWeeklyPnl = projectPnl(7)
        const totalMonthlyPnl = projectPnl(30)
        const totalYearlyPnl = projectPnl(365)
        const isPositive = totalDailyPnl > 0
        const isNegative = totalDailyPnl < 0
        const colorClass = isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'
        const prefix = isPositive ? '+' : ''
        const dailyPct = dailyRate * 100
        const weeklyPct = portfolioUsd > 0 ? (totalWeeklyPnl / portfolioUsd) * 100 : 0
        const monthlyPct = portfolioUsd > 0 ? (totalMonthlyPnl / portfolioUsd) * 100 : 0
        const yearlyPct = portfolioUsd > 0 ? (totalYearlyPnl / portfolioUsd) * 100 : 0
        const pctPrefix = isPositive ? '+' : ''
        const fmtPct = (pct: number) => portfolioUsd === 0 ? '--' : `${pctPrefix}${pct.toFixed(2)}`
        const compoundReturn = (days: number) => portfolioUsd > 0 ? portfolioUsd * (Math.pow(1 + dailyRate, days) - 1) : 0
        const compWeekly = compoundReturn(7)
        const compMonthly = compoundReturn(30)
        const compYearly = compoundReturn(365)
        const compWeeklyPct = portfolioUsd > 0 ? (compWeekly / portfolioUsd) * 100 : 0
        const compMonthlyPct = portfolioUsd > 0 ? (compMonthly / portfolioUsd) * 100 : 0
        const compYearlyPct = portfolioUsd > 0 ? (compYearly / portfolioUsd) * 100 : 0

        return (
          <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
            <table className="w-full">
              <thead className="bg-slate-900">
                <tr>
                  <th className="text-left px-2 sm:px-4 py-2 text-sm font-medium text-slate-400">
                    <div className="flex items-center space-x-2">
                      <span>Portfolio Totals</span>
                      <select
                        value={projectionBasis}
                        onChange={(e) => setProjectionBasis(e.target.value)}
                        className="bg-slate-700 text-xs text-slate-300 px-2 py-1 rounded border border-slate-600 font-normal"
                        title="Projection basis period"
                      >
                        <option value="7d">7d basis</option>
                        <option value="14d">14d basis</option>
                        <option value="30d">30d basis</option>
                        <option value="3m">3m basis</option>
                        <option value="6m">6m basis</option>
                        <option value="1y">1y basis</option>
                        <option value="all">All-time basis</option>
                      </select>
                    </div>
                  </th>
                  <th className="text-right px-2 sm:px-4 py-2 text-sm font-medium text-slate-400">Daily</th>
                  <th className="text-right px-2 sm:px-4 py-2 text-sm font-medium text-slate-400">Weekly</th>
                  <th className="text-right px-2 sm:px-4 py-2 text-sm font-medium text-slate-400">Monthly</th>
                  <th className="text-right px-2 sm:px-4 py-2 text-sm font-medium text-slate-400">Yearly</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="px-2 sm:px-4 py-2 text-sm font-semibold text-slate-300">Projected PnL</td>
                  <td className={`px-2 sm:px-4 py-2 text-right text-lg font-bold ${colorClass}`}>
                    {prefix}${totalDailyPnl.toFixed(2)}
                    <span className="text-xs ml-1 text-slate-400">({fmtPct(dailyPct)}%)</span>
                  </td>
                  <td className={`px-2 sm:px-4 py-2 text-right text-lg font-bold ${colorClass}`}>
                    {prefix}${totalWeeklyPnl.toFixed(2)}
                    <span className="text-xs ml-1 text-slate-400">({fmtPct(weeklyPct)}%)</span>
                  </td>
                  <td className={`px-2 sm:px-4 py-2 text-right text-lg font-bold ${colorClass}`}>
                    {prefix}${totalMonthlyPnl.toFixed(2)}
                    <span className="text-xs ml-1 text-slate-400">({fmtPct(monthlyPct)}%)</span>
                  </td>
                  <td className={`px-2 sm:px-4 py-2 text-right text-lg font-bold ${colorClass}`}>
                    {prefix}${totalYearlyPnl.toFixed(2)}
                    <span className="text-xs ml-1 text-slate-400">({fmtPct(yearlyPct)}%)</span>
                  </td>
                </tr>
                <tr>
                  <td className="px-2 sm:px-4 py-1 text-sm text-slate-400">Compounded</td>
                  <td className={`px-2 sm:px-4 py-1 text-right text-sm ${colorClass}`}>—</td>
                  <td className={`px-2 sm:px-4 py-1 text-right text-sm ${colorClass}`}>
                    {prefix}${compWeekly.toFixed(2)}
                    <span className="text-xs ml-1 text-slate-500">({fmtPct(compWeeklyPct)}%)</span>
                  </td>
                  <td className={`px-2 sm:px-4 py-1 text-right text-sm ${colorClass}`}>
                    {prefix}${compMonthly.toFixed(2)}
                    <span className="text-xs ml-1 text-slate-500">({fmtPct(compMonthlyPct)}%)</span>
                  </td>
                  <td className={`px-2 sm:px-4 py-1 text-right text-sm ${colorClass}`}>
                    {prefix}${compYearly.toFixed(2)}
                    <span className="text-xs ml-1 text-slate-500">({fmtPct(compYearlyPct)}%)</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )
      })()}

      {/* Account Value Chart */}
      <AccountValueChart />

      {/* Recent Deals */}
      {recentDeals.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-bold text-white flex items-center gap-2">
              <Clock className="w-5 h-5 text-blue-400" />
              Recent Deals
            </h3>
          </div>
          <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-900">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Deal</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Opened</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase">Invested</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase">Profit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700">
                  {recentDeals.map((position) => (
                    <tr key={position.id} className="hover:bg-slate-750 transition-colors">
                      <td className="px-4 py-3">
                        <span className="font-semibold text-white">#{position.user_deal_number ?? position.id}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                          position.status === 'open'
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-slate-700 text-slate-400'
                        }`}>
                          {position.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-300 text-sm">
                        {format(new Date(position.opened_at), 'MMM dd, HH:mm')}
                      </td>
                      <td className="px-4 py-3 text-right text-white font-mono text-sm">
                        {formatCrypto(position.total_quote_spent, 8)} {(position.product_id || 'ETH-BTC').split('-')[1]}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {position.profit_quote !== null ? (
                          <div className="flex items-center justify-end gap-1">
                            {position.profit_quote >= 0 ? (
                              <TrendingUp className="w-3 h-3 text-green-500" />
                            ) : (
                              <TrendingDown className="w-3 h-3 text-red-500" />
                            )}
                            <span className={`font-semibold text-sm ${
                              position.profit_quote >= 0 ? 'text-green-400' : 'text-red-400'
                            }`}>
                              {position.profit_percentage?.toFixed(2)}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-slate-400 text-sm">-</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Active Bots */}
      {activeBots.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-bold text-white flex items-center gap-2">
              <Play className="w-5 h-5 text-green-500" />
              Active Bots ({activeBots.length})
            </h3>
            {bots.filter(b => !b.is_active).length > 0 && (
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <span className="text-sm text-slate-400">Show stopped</span>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={showStoppedBots}
                    onChange={() => setShowStoppedBots(!showStoppedBots)}
                    className="peer sr-only"
                  />
                  <div className="w-9 h-5 bg-slate-600 rounded-full peer-checked:bg-blue-600 transition-colors" />
                  <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-4" />
                </div>
              </label>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {activeBots.map((bot) => (
              <BotCard key={bot.id} bot={bot} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      )}

      {/* Inactive Bots */}
      {showStoppedBots && bots.filter(b => !b.is_active).length > 0 && (
        <div>
          <h3 className="text-xl font-bold mb-4 text-white flex items-center gap-2">
            <Square className="w-5 h-5 text-slate-500" />
            Stopped Bots ({bots.filter(b => !b.is_active).length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {bots.filter(b => !b.is_active).map((bot) => (
              <BotCard key={bot.id} bot={bot} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      )}

      {/* No Bots Message */}
      {bots.length === 0 && (
        <div className="bg-slate-800 rounded-lg p-12 text-center border border-slate-700">
          <BotIcon className="w-16 h-16 text-slate-600 mx-auto mb-4" />
          <h3 className="text-xl font-semibold mb-2 text-white">No Bots Created</h3>
          <p className="text-slate-400 mb-6">
            Get started by creating your first trading bot
          </p>
        </div>
      )}
    </div>
  )
}

// Enhanced Bot Card Component
function BotCard({ bot, onNavigate: _onNavigate }: { bot: Bot, onNavigate: (page: Page) => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: stats } = useQuery({
    queryKey: ['bot-stats', bot.id],
    queryFn: () => botsApi.getStats(bot.id),
    refetchInterval: 10000,
    enabled: bot.is_active,
  })

  const formatCrypto = (amount: number | undefined | null, decimals: number = 8) => (amount ?? 0).toFixed(decimals)

  const handleToggleBot = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      if (bot.is_active) {
        await botsApi.stop(bot.id)
      } else {
        await botsApi.start(bot.id)
      }
      // Refresh bot data without full page reload
      queryClient.invalidateQueries({ queryKey: ['bots'] })
      queryClient.invalidateQueries({ queryKey: ['bot-stats', bot.id] })
    } catch (err) {
      alert(`Error: ${err}`)
    }
  }

  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    // Navigate to bots page with bot to edit
    navigate('/bots', { state: { editBot: bot } })
  }

  return (
    <div className={`bg-slate-800 rounded-lg p-5 border transition-all hover:border-slate-600 ${
      bot.is_active
        ? 'border-green-500/30'
        : 'border-slate-700'
    }`}>
      {/* Bot Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <h4 className="text-lg font-semibold truncate text-white">{bot.name}</h4>
          {bot.description && (
            <p className="text-sm text-slate-400 truncate mt-1">{bot.description}</p>
          )}
        </div>
        <div className={`px-2 py-1 rounded text-xs font-medium flex-shrink-0 ml-2 ${
          bot.is_active
            ? 'bg-green-500/20 text-green-400'
            : 'bg-slate-700 text-slate-400'
        }`}>
          {bot.is_active ? 'Active' : 'Stopped'}
        </div>
      </div>

      {/* Bot Info */}
      <div className="space-y-2 mb-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">Pair:</span>
          <span className="text-white font-medium">{bot.product_id}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">Strategy:</span>
          <span className="text-white font-medium text-xs">
            {bot.strategy_type.replace('_', ' ').toUpperCase()}
          </span>
        </div>

        {/* Bot Stats */}
        {stats && (
          <>
            <div className="flex items-center justify-between text-sm pt-2 border-t border-slate-700">
              <span className="text-slate-400">Deals:</span>
              <span className="text-white font-medium">
                {stats.open_positions} / {stats.max_concurrent_deals}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">Profit:</span>
              <span className={`font-semibold ${
                stats.total_profit_quote >= 0 ? 'text-green-400' : 'text-red-400'
              }`}>
                {stats.total_profit_quote >= 0 ? '+' : ''}{formatCrypto(stats.total_profit_quote, 6)} BTC
              </span>
            </div>
          </>
        )}
      </div>

      {/* Quick Actions */}
      <div className="flex gap-2">
        <button
          onClick={handleToggleBot}
          className={`flex-1 px-3 py-2 rounded font-medium text-sm transition-colors flex items-center justify-center gap-2 ${
            bot.is_active
              ? 'bg-red-600 hover:bg-red-700 text-white'
              : 'bg-green-600 hover:bg-green-700 text-white'
          }`}
        >
          {bot.is_active ? (
            <>
              <Square size={14} />
              Stop
            </>
          ) : (
            <>
              <Play size={14} />
              Start
            </>
          )}
        </button>
        <button
          onClick={handleEdit}
          className="px-3 py-2 rounded font-medium text-sm bg-slate-700 hover:bg-slate-600 text-white transition-colors"
        >
          Edit
        </button>
      </div>
    </div>
  )
}
