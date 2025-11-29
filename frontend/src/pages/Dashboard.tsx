import { useQuery } from '@tanstack/react-query'
import { botsApi, positionsApi } from '../services/api'
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
  Wallet
} from 'lucide-react'
import { Bot } from '../types'
import { format } from 'date-fns'
import { useNavigate } from 'react-router-dom'
import { useAccount, getChainName } from '../contexts/AccountContext'

type Page = 'dashboard' | 'bots' | 'positions' | 'portfolio' | 'charts' | 'strategies' | 'settings'

interface DashboardProps {
  onNavigate: (page: Page) => void
}

export default function Dashboard({ onNavigate }: DashboardProps) {
  const { selectedAccount } = useAccount()

  // Fetch all bots (filtered by account if selected)
  const { data: bots = [] } = useQuery({
    queryKey: ['bots', selectedAccount?.id],
    queryFn: botsApi.getAll,
    refetchInterval: 5000,
    select: (data) => {
      if (!selectedAccount) return data
      // Filter bots by account_id
      return data.filter((bot: Bot) => bot.account_id === selectedAccount.id || !bot.account_id)
    },
  })

  // Fetch all positions for metrics (filtered by account)
  const { data: allPositions = [] } = useQuery({
    queryKey: ['all-positions', selectedAccount?.id],
    queryFn: () => positionsApi.getAll(undefined, 100),
    refetchInterval: 10000,
    select: (data) => {
      if (!selectedAccount) return data
      // Filter positions by account_id
      return data.filter((p: any) => p.account_id === selectedAccount.id || !p.account_id)
    },
  })

  // Fetch portfolio for account value - use same endpoint/queryKey as header for consistency
  const { data: portfolio } = useQuery({
    queryKey: ['account-portfolio'],
    queryFn: async () => {
      const response = await fetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 120000, // Match header timing
    staleTime: 60000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })

  const activeBots = bots.filter(bot => bot.is_active)
  const openPositions = allPositions.filter(p => p.status === 'open')
  const closedPositions = allPositions.filter(p => p.status === 'closed')

  // Calculate total profit
  const totalProfitQuote = closedPositions.reduce((sum, p) => sum + (p.profit_quote || 0), 0)
  const totalProfitUSD = closedPositions.reduce((sum, p) => sum + (p.profit_usd || 0), 0)

  // Calculate win rate
  const profitablePositions = closedPositions.filter(p => (p.profit_quote || 0) > 0)
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
            {totalProfitQuote >= 0 ? (
              <TrendingUp className="w-5 h-5 text-green-500" />
            ) : (
              <TrendingDown className="w-5 h-5 text-red-500" />
            )}
          </div>
          <p className={`text-2xl font-bold ${totalProfitQuote >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {totalProfitQuote >= 0 ? '+' : ''}{formatCrypto(totalProfitQuote, 8)}
          </p>
          <p className={`text-sm mt-1 ${totalProfitUSD >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
            {totalProfitUSD >= 0 ? '+' : ''}{formatCurrency(totalProfitUSD)}
          </p>
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
        </div>
      </div>

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
                        <span className="font-semibold text-white">#{position.id}</span>
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
          <h3 className="text-xl font-bold mb-4 text-white flex items-center gap-2">
            <Play className="w-5 h-5 text-green-500" />
            Active Bots ({activeBots.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {activeBots.map((bot) => (
              <BotCard key={bot.id} bot={bot} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      )}

      {/* Inactive Bots */}
      {bots.filter(b => !b.is_active).length > 0 && (
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
function BotCard({ bot, onNavigate }: { bot: Bot, onNavigate: (page: Page) => void }) {
  const navigate = useNavigate()
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
      // Trigger refetch
      window.location.reload()
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
                {stats.open_positions} / {stats.total_positions}
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
