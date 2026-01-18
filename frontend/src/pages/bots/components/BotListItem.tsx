import { Bot } from '../../../types'
import { Account } from '../../../contexts/AccountContext'
import { Edit, Trash2, Copy, Brain, MoreVertical, FastForward, BarChart2, XCircle, DollarSign, ScanLine, ArrowRightLeft } from 'lucide-react'
import { botUsesAIIndicators, botUsesBullFlagIndicator, botUsesNonAIIndicators } from '../helpers'

interface BotListItemProps {
  bot: Bot
  strategies: any[]
  handleOpenEdit: (bot: Bot) => void
  handleDelete: (bot: Bot) => void
  startBot: any
  stopBot: any
  cloneBot: any
  copyToAccount: any
  accounts: Account[]
  currentAccountId?: number
  forceRunBot: any
  cancelAllPositions: any
  sellAllPositions: any
  openMenuId: number | null
  setOpenMenuId: (id: number | null) => void
  setAiLogsBotId: (id: number | null) => void
  setIndicatorLogsBotId: (id: number | null) => void
  setScannerLogsBotId: (id: number | null) => void
  portfolio?: any
  botsFetching?: boolean
}

export function BotListItem({
  bot,
  strategies,
  handleOpenEdit,
  handleDelete,
  startBot,
  stopBot,
  cloneBot,
  copyToAccount,
  accounts,
  currentAccountId,
  forceRunBot,
  cancelAllPositions,
  sellAllPositions,
  openMenuId,
  setOpenMenuId,
  setAiLogsBotId,
  setIndicatorLogsBotId,
  setScannerLogsBotId,
}: BotListItemProps) {
  const botPairs = ((bot as any).product_ids || [bot.product_id])
  const strategyName = strategies.find((s) => s.id === bot.strategy_type)?.name || bot.strategy_type
  const aiProvider = bot.strategy_config?.ai_provider

  return (
    <tr
      key={bot.id}
      className="border-b border-slate-700 hover:bg-slate-750 transition-colors"
    >
      {/* Name & Description */}
      <td className="px-2 sm:px-4 py-2 sm:py-3">
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span className="font-medium text-white">{bot.name}</span>
            {(bot as any).insufficient_funds && (
              <span
                className="text-amber-500 text-sm"
                title="Insufficient funds to open new positions"
              >
                💰
              </span>
            )}
          </div>
          {bot.description && (
            <div className="text-xs text-slate-400 mt-0.5 line-clamp-1">
              {bot.description}
            </div>
          )}
        </div>
      </td>

      {/* Strategy */}
      <td className="px-2 sm:px-4 py-2 sm:py-3">
        <div className="flex flex-col">
          <div className="text-sm text-white">{strategyName}</div>
          {aiProvider && (
            <a
              href={
                aiProvider === 'claude' ? 'https://console.anthropic.com/settings/billing'
                : aiProvider === 'gemini' ? 'https://aistudio.google.com/app/apikey'
                : aiProvider === 'grok' ? 'https://console.x.ai/'
                : '#'
              }
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-purple-400 hover:text-purple-300 mt-0.5 flex items-center gap-1 transition-colors cursor-pointer"
              title="View API credits/usage"
              onClick={(e) => e.stopPropagation()}
            >
              {aiProvider === 'claude' ? '🤖 Claude'
                : aiProvider === 'gemini' ? '🤖 Gemini'
                : aiProvider === 'grok' ? '🤖 Grok'
                : `🤖 ${aiProvider}`}
              <span className="text-[10px]">💳</span>
            </a>
          )}
        </div>
      </td>

      {/* Pairs */}
      <td className="px-2 sm:px-4 py-2 sm:py-3">
        <div className="flex items-center gap-1">
          {botPairs.length === 1 ? (
            <span className="text-sm text-white font-mono">
              {botPairs[0]}
            </span>
          ) : (
            <span className="text-sm text-white font-mono" title={botPairs.join(', ')}>
              {botPairs[0]} +{botPairs.length - 1}
            </span>
          )}
        </div>
      </td>

      {/* Active Trades */}
      <td className="px-2 sm:px-4 py-2 sm:py-3">
        {(bot.strategy_config?.max_concurrent_deals || bot.strategy_config?.max_concurrent_positions) ? (
          <div className="text-sm">
            <span className="text-blue-400 font-medium">
              {bot.open_positions_count ?? 0}
            </span>
            <span className="text-slate-500"> / </span>
            <span className="text-slate-400">
              {bot.strategy_config.max_concurrent_deals || bot.strategy_config.max_concurrent_positions}
            </span>
          </div>
        ) : (
          <span className="text-sm text-slate-500">—</span>
        )}
      </td>

      {/* Trade Stats */}
      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right">
        <div className="flex flex-col items-end">
          <div className="text-xs text-slate-400">
            {(bot as any).closed_positions_count || 0} closed
          </div>
          <div className="text-xs text-slate-500">
            {((bot as any).trades_per_day || 0).toFixed(2)}/day
          </div>
        </div>
      </td>

      {/* Win Rate */}
      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right">
        {(() => {
          const winRate = (bot as any).win_rate || 0
          const closedCount = (bot as any).closed_positions_count || 0
          const colorClass = closedCount === 0 ? 'text-slate-500' :
            winRate >= 70 ? 'text-green-400' :
            winRate >= 50 ? 'text-yellow-400' :
            'text-red-400'
          return (
            <span className={`text-sm font-medium ${colorClass}`}>
              {closedCount === 0 ? '—' : `${winRate.toFixed(1)}%`}
            </span>
          )
        })()}
      </td>

      {/* PnL */}
      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right">
        {(() => {
          const pnl = (bot as any).total_pnl_usd || 0
          const isPositive = pnl > 0
          const isNegative = pnl < 0
          return (
            <span className={`text-sm font-medium ${
              isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'
            }`}>
              {isPositive ? '+' : ''}${pnl.toFixed(2)} {isPositive ? '↑' : isNegative ? '↓' : ''}
            </span>
          )
        })()}
      </td>

      {/* Projected PnL */}
      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right">
        {(() => {
          const dailyPnl = (bot as any).avg_daily_pnl_usd || 0

          // Use simple linear projection (no compounding)
          // Compounding daily rates leads to unrealistic projections
          const projectPnl = (days: number) => dailyPnl * days

          const weeklyPnl = projectPnl(7)
          const monthlyPnl = projectPnl(30)
          const yearlyPnl = projectPnl(365)

          const isPositive = dailyPnl > 0
          const isNegative = dailyPnl < 0
          const colorClass = isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'
          const prefix = isPositive ? '+' : ''

          return (
            <div className="text-xs space-y-0.5">
              <div className={`font-medium ${colorClass}`}>
                Day: {prefix}${dailyPnl.toFixed(2)}
              </div>
              <div className={`${colorClass}`}>
                Week: {prefix}${weeklyPnl.toFixed(2)}
              </div>
              <div className={`${colorClass}`}>
                Month: {prefix}${monthlyPnl.toFixed(2)}
              </div>
              <div className={`${colorClass}`}>
                Year: {prefix}${yearlyPnl.toFixed(2)}
              </div>
            </div>
          )
        })()}
      </td>

      {/* Budget */}
      <td className="px-2 sm:px-4 py-2 sm:py-3">
        <div className="flex flex-col gap-1">
          <span className="text-sm text-emerald-400 font-medium">
            {bot.budget_percentage}%
          </span>
          {/* Budget Utilization */}
          {bot.budget_utilization_percentage !== undefined && (
            <div className="text-[10px] text-slate-400">
              {bot.budget_utilization_percentage.toFixed(1)}% in use
            </div>
          )}
        </div>
      </td>

      {/* Status Toggle */}
      <td className="px-2 sm:px-4 py-2 sm:py-3">
        <div className="flex justify-center">
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={bot.is_active}
              onChange={() => {
                if (bot.is_active) {
                  stopBot.mutate(bot.id)
                } else {
                  startBot.mutate(bot.id)
                }
              }}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
          </label>
        </div>
      </td>

      {/* Actions */}
      <td className="px-2 sm:px-4 py-2 sm:py-3">
        <div className="flex items-center justify-center gap-2">
          {botUsesAIIndicators(bot) && (
            <button
              onClick={() => setAiLogsBotId(bot.id)}
              className="p-1.5 bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 rounded transition-colors"
              title="View AI Reasoning Logs"
            >
              <Brain className="w-4 h-4" />
            </button>
          )}
          {botUsesNonAIIndicators(bot) && (
            <button
              onClick={() => setIndicatorLogsBotId(bot.id)}
              className="p-1.5 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-400 rounded transition-colors"
              title="View Indicator Logs"
            >
              <BarChart2 className="w-4 h-4" />
            </button>
          )}
          {botUsesBullFlagIndicator(bot) && (
            <button
              onClick={() => setScannerLogsBotId(bot.id)}
              className="p-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded transition-colors"
              title="View Scanner Logs"
            >
              <ScanLine className="w-4 h-4" />
            </button>
          )}

          {/* Force Run Button - show for active bots OR stopped bots with open positions */}
          {(bot.is_active || (bot.open_positions_count ?? 0) > 0) && (
            <button
              onClick={() => forceRunBot.mutate(bot.id)}
              disabled={forceRunBot.isPending}
              className={`p-1.5 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                bot.is_active
                  ? 'bg-blue-600/20 hover:bg-blue-600/30 text-blue-400'
                  : 'bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-400'
              }`}
              title={bot.is_active ? "Force Run Now" : "Force Run (check DCA/Exit for open positions)"}
            >
              <FastForward className="w-4 h-4" />
            </button>
          )}

          {/* More Actions Menu */}
          <div className="relative">
            <button
              onClick={() => setOpenMenuId(openMenuId === bot.id ? null : bot.id)}
              className="p-1.5 bg-slate-700 hover:bg-slate-600 rounded transition-colors"
              title="More actions"
            >
              <MoreVertical className="w-4 h-4" />
            </button>

            {/* Dropdown Menu */}
            {openMenuId === bot.id && (
              <div className="absolute right-0 mt-2 w-48 bg-slate-800 rounded-lg shadow-lg border border-slate-700 z-10">
                <button
                  onClick={() => {
                    handleOpenEdit(bot)
                    setOpenMenuId(null)
                  }}
                  className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left rounded-t-lg transition-colors"
                >
                  <Edit className="w-4 h-4" />
                  <span>Edit Bot</span>
                </button>
                <button
                  onClick={() => {
                    cloneBot.mutate(bot.id)
                    setOpenMenuId(null)
                  }}
                  className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left transition-colors"
                >
                  <Copy className="w-4 h-4 text-blue-400" />
                  <span>Clone Bot</span>
                </button>

                {/* Copy to Account - show if there are other accounts to copy to */}
                {(() => {
                  // Get accounts other than the current one
                  const targetAccounts = accounts.filter(acc => acc.id !== currentAccountId && acc.is_active)

                  if (targetAccounts.length === 0) return null

                  return (
                    <>
                      <div className="border-t border-slate-600 my-1"></div>
                      {targetAccounts.map((targetAccount) => (
                        <button
                          key={targetAccount.id}
                          onClick={() => {
                            copyToAccount.mutate({ id: bot.id, targetAccountId: targetAccount.id })
                            setOpenMenuId(null)
                          }}
                          className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left transition-colors"
                        >
                          <ArrowRightLeft className="w-4 h-4 text-purple-400" />
                          <span>Copy to {targetAccount.name}</span>
                          {targetAccount.is_paper_trading && (
                            <span className="text-xs text-slate-400">(Paper)</span>
                          )}
                        </button>
                      ))}
                    </>
                  )
                })()}

                {/* Separator if bot has open positions */}
                {(bot.open_positions_count ?? 0) > 0 && (
                  <div className="border-t border-slate-600 my-1"></div>
                )}

                {/* Cancel All Positions */}
                {(bot.open_positions_count ?? 0) > 0 && (
                  <button
                    onClick={() => {
                      if (confirm(
                        `⚠️ Cancel all ${bot.open_positions_count} open position(s) for "${bot.name}"?\n\n` +
                        `This will mark them as CANCELLED without selling.\n` +
                        `Your holdings will remain as-is (no P&L impact).\n\n` +
                        `This action cannot be undone.`
                      )) {
                        cancelAllPositions.mutate(bot.id)
                      }
                      setOpenMenuId(null)
                    }}
                    className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left transition-colors"
                  >
                    <XCircle className="w-4 h-4 text-orange-400" />
                    <span>Cancel All Deals</span>
                  </button>
                )}

                {/* Sell All Positions at Market Price */}
                {(bot.open_positions_count ?? 0) > 0 && (
                  <button
                    onClick={() => {
                      if (confirm(
                        `⚠️ Sell all ${bot.open_positions_count} position(s) for "${bot.name}" at MARKET price?\n\n` +
                        `This will immediately close all positions and realize gains/losses.\n\n` +
                        `This action cannot be undone.`
                      )) {
                        sellAllPositions.mutate(bot.id)
                      }
                      setOpenMenuId(null)
                    }}
                    className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left transition-colors"
                  >
                    <DollarSign className="w-4 h-4 text-yellow-400" />
                    <span>Sell All at Market</span>
                  </button>
                )}

                <button
                  onClick={() => {
                    handleDelete(bot)
                    setOpenMenuId(null)
                  }}
                  disabled={bot.is_active}
                  className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left rounded-b-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Trash2 className="w-4 h-4 text-red-400" />
                  <span>Delete Bot</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </td>
    </tr>
  )
}
