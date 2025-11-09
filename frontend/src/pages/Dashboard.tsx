import { useQuery } from '@tanstack/react-query'
import { botsApi, accountApi } from '../services/api'
import { Activity, TrendingUp, DollarSign, Play, Square, Bot as BotIcon } from 'lucide-react'
import { Bot } from '../types'
import { useState } from 'react'

export default function Dashboard() {
  // Fetch all bots
  const { data: bots = [] } = useQuery({
    queryKey: ['bots'],
    queryFn: botsApi.getAll,
    refetchInterval: 5000,
  })

  // Fetch account balances
  const { data: balances } = useQuery({
    queryKey: ['account-balances'],
    queryFn: accountApi.getBalances,
    refetchInterval: 10000,
  })

  // Fetch stats for all active bots
  const activeBots = bots.filter(bot => bot.is_active)
  const inactiveBots = bots.filter(bot => !bot.is_active)

  // Aggregate stats across all bots
  const totalActiveBots = activeBots.length
  const totalBots = bots.length

  const formatPrice = (price: number) => price.toFixed(8)
  const formatBTC = (btc: number) => `${btc.toFixed(8)} BTC`

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold">Dashboard</h2>
          <p className="text-slate-400 text-sm mt-1">
            {totalActiveBots} active bot{totalActiveBots !== 1 ? 's' : ''} running
          </p>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="stat-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">Total Bots</p>
              <p className="text-2xl font-bold mt-1">{totalBots}</p>
              <p className="text-xs text-slate-500 mt-1">
                {totalActiveBots} active, {inactiveBots.length} stopped
              </p>
            </div>
            <BotIcon className="w-10 h-10 text-blue-500 opacity-50" />
          </div>
        </div>

        <div className="stat-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">BTC Balance</p>
              <p className="text-2xl font-bold mt-1">{(balances?.btc || 0).toFixed(6)}</p>
              <p className="text-xs text-slate-500 mt-1">Available</p>
            </div>
            <DollarSign className="w-10 h-10 text-yellow-500 opacity-50" />
          </div>
        </div>

        <div className="stat-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">Total Value</p>
              <p className="text-2xl font-bold mt-1">{formatBTC(balances?.total_btc_value || 0)}</p>
              <p className="text-xs text-slate-500 mt-1">
                ${(balances?.total_usd_value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </p>
            </div>
            <DollarSign className="w-10 h-10 text-green-500 opacity-50" />
          </div>
        </div>

        <div className="stat-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">ETH Balance</p>
              <p className="text-2xl font-bold mt-1">{(balances?.eth || 0).toFixed(6)}</p>
              <p className="text-xs text-slate-500 mt-1">
                {formatBTC(balances?.eth_value_in_btc || 0)}
              </p>
            </div>
            <Activity className="w-10 h-10 text-purple-500 opacity-50" />
          </div>
        </div>
      </div>

      {/* Active Bots */}
      {activeBots.length > 0 && (
        <div>
          <h3 className="text-xl font-bold mb-4 flex items-center">
            <Play className="w-5 h-5 mr-2 text-green-500" />
            Active Bots ({activeBots.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {activeBots.map((bot) => (
              <BotCard key={bot.id} bot={bot} />
            ))}
          </div>
        </div>
      )}

      {/* Inactive Bots */}
      {inactiveBots.length > 0 && (
        <div>
          <h3 className="text-xl font-bold mb-4 flex items-center">
            <Square className="w-5 h-5 mr-2 text-slate-500" />
            Stopped Bots ({inactiveBots.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {inactiveBots.map((bot) => (
              <BotCard key={bot.id} bot={bot} />
            ))}
          </div>
        </div>
      )}

      {/* No Bots Message */}
      {totalBots === 0 && (
        <div className="bg-slate-800 rounded-lg p-12 text-center">
          <BotIcon className="w-16 h-16 text-slate-600 mx-auto mb-4" />
          <h3 className="text-xl font-semibold mb-2">No Bots Created</h3>
          <p className="text-slate-400 mb-6">
            Get started by creating your first trading bot
          </p>
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault()
              // This would normally trigger navigation to Bots page
              // For now, just show a message
              alert('Navigate to the "Bots" tab to create your first bot!')
            }}
            className="inline-block bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded font-medium transition-colors"
          >
            Go to Bot Management
          </a>
        </div>
      )}
    </div>
  )
}

// Bot Card Component
function BotCard({ bot }: { bot: Bot }) {
  const { data: stats } = useQuery({
    queryKey: ['bot-stats', bot.id],
    queryFn: () => botsApi.getStats(bot.id),
    refetchInterval: 10000,
    enabled: bot.is_active, // Only fetch stats for active bots
  })

  const formatBTC = (btc: number) => `${btc.toFixed(8)} BTC`

  return (
    <div className={`bg-slate-800 rounded-lg p-5 border transition-colors ${
      bot.is_active
        ? 'border-green-500/30 hover:border-green-500/50'
        : 'border-slate-700 hover:border-slate-600'
    }`}>
      {/* Bot Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <h4 className="text-lg font-semibold truncate">{bot.name}</h4>
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
          <span className="text-slate-400">Product:</span>
          <span className="text-white font-medium">{bot.product_id}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">Strategy:</span>
          <span className="text-white font-medium text-xs">
            {bot.strategy_type.replace('_', ' ').toUpperCase()}
          </span>
        </div>
        {bot.last_signal_check && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-400">Last Check:</span>
            <span className="text-slate-500 text-xs">
              {new Date(bot.last_signal_check).toLocaleTimeString()}
            </span>
          </div>
        )}
      </div>

      {/* Bot Stats (only for active bots with data) */}
      {bot.is_active && stats && (
        <div className="border-t border-slate-700 pt-3 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-400">Positions:</span>
            <span className="text-white">
              {stats.open_positions} open, {stats.closed_positions} closed
            </span>
          </div>
          {stats.total_profit_btc !== 0 && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">Profit:</span>
              <span className={stats.total_profit_btc >= 0 ? 'text-green-400' : 'text-red-400'}>
                {formatBTC(stats.total_profit_btc)}
              </span>
            </div>
          )}
          {stats.closed_positions > 0 && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">Win Rate:</span>
              <span className="text-white">{stats.win_rate.toFixed(1)}%</span>
            </div>
          )}
        </div>
      )}

      {/* Idle State for Stopped Bots */}
      {!bot.is_active && (
        <div className="border-t border-slate-700 pt-3">
          <p className="text-sm text-slate-500 text-center">
            Bot is stopped
          </p>
        </div>
      )}
    </div>
  )
}
