import { useState, useEffect, useRef } from 'react'
import { Bot } from '../../../types'
import { Account } from '../../../contexts/AccountContext'
import { Edit, Eye, Trash2, Copy, Brain, MoreVertical, BarChart2, XCircle, DollarSign, ScanLine, ArrowRightLeft, ChevronDown, ChevronUp, Download, Clipboard } from 'lucide-react'
import { botUsesAIIndicators, botUsesBullFlagIndicator, botUsesNonAIIndicators } from '../helpers'
import { useNotifications } from '../../../contexts/NotificationContext'
import { useConfirm } from '../../../contexts/ConfirmContext'

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
  canWrite?: boolean
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
  forceRunBot: _forceRunBot,
  cancelAllPositions,
  sellAllPositions,
  openMenuId,
  setOpenMenuId,
  setAiLogsBotId,
  setIndicatorLogsBotId,
  setScannerLogsBotId,
  canWrite = true,
}: BotListItemProps) {
  const { addToast } = useNotifications()
  const confirm = useConfirm()
  const botPairs = ((bot as any).product_ids || [bot.product_id])
  const strategyName = strategies.find((s) => s.id === bot.strategy_type)?.name || bot.strategy_type
  const botAccount = accounts.find(a => a.id === bot.account_id)
  const exchangeName = botAccount?.exchange || 'coinbase'
  const aiProvider = bot.strategy_config?.ai_provider

  // Ref and position for fixed-position dropdown menu
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null)

  // Calculate menu position when menu opens
  useEffect(() => {
    if (openMenuId === bot.id && menuButtonRef.current) {
      const rect = menuButtonRef.current.getBoundingClientRect()
      const menuWidth = 192 // w-48 = 12rem = 192px
      const estimatedMenuHeight = 320 // reasonable estimate for menu items
      const spaceBelow = window.innerHeight - rect.bottom
      const spaceAbove = rect.top
      let top: number
      if (spaceBelow >= estimatedMenuHeight) {
        top = rect.bottom + 4 // show below button
      } else if (spaceAbove >= estimatedMenuHeight) {
        top = rect.top - estimatedMenuHeight // flip above button
      } else {
        // Not enough room either way — show below and let it scroll
        top = rect.bottom + 4
      }
      setMenuPosition({
        top,
        left: rect.right - menuWidth,
      })
    } else {
      setMenuPosition(null)
    }
  }, [openMenuId, bot.id])

  // State for projected PnL carousel
  const [currentTimeframeIndex, setCurrentTimeframeIndex] = useState(0)
  const [isPnlExpanded, setIsPnlExpanded] = useState(false)
  const [isTransitioning, setIsTransitioning] = useState(true)
  const timeframes = ['day', 'week', 'month', 'year']

  // PnL carousel: auto-scrolls through timeframes using CSS translateY.
  // Items are rendered twice ([...projections, ...projections]) so that when
  // the index overshoots past the last real item, there's a duplicate set to
  // scroll into — then we snap back to index 0 without animation for seamless looping.
  useEffect(() => {
    if (isPnlExpanded) return

    const interval = setInterval(() => {
      setIsTransitioning(true)
      setCurrentTimeframeIndex((prev) => prev + 1)
    }, 5000)

    return () => clearInterval(interval)
  }, [isPnlExpanded])

  // Reset to beginning seamlessly after completing one cycle
  useEffect(() => {
    if (isPnlExpanded) return
    if (currentTimeframeIndex === timeframes.length) {
      // Wait for transition to complete, then reset without animation
      setTimeout(() => {
        setIsTransitioning(false)
        setCurrentTimeframeIndex(0)
        // Re-enable transitions on next frame
        requestAnimationFrame(() => {
          setIsTransitioning(true)
        })
      }, 500) // Match transition duration
    }
  }, [currentTimeframeIndex, isPnlExpanded, timeframes.length])

  return (
    <tr
      key={bot.id}
      className="border-b border-slate-700 hover:bg-slate-750 transition-colors"
    >
      {/* Name & Description */}
      <td className="px-1 sm:px-2 py-2">
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span className="font-medium text-white">{bot.name}</span>
            {exchangeName !== 'coinbase' && (
              <span className="px-1 py-0.5 text-[9px] font-medium bg-purple-500/20 text-purple-300 rounded">
                {exchangeName === 'bybit' ? 'BYBIT' : exchangeName === 'mt5_bridge' ? 'MT5' : exchangeName.toUpperCase()}
              </span>
            )}
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
      <td className="hidden md:table-cell px-1 sm:px-2 py-2">
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
      <td className="hidden sm:table-cell px-1 sm:px-2 py-2">
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
      <td className="hidden sm:table-cell px-0.5 sm:px-1 py-2 w-16">
        {(bot.strategy_config?.max_concurrent_deals || bot.strategy_config?.max_concurrent_positions) ? (
          <div className="text-sm whitespace-nowrap">
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
      <td className="hidden md:table-cell px-1 sm:px-2 py-2 text-right">
        <div className="flex flex-col items-end">
          <div className="text-xs text-slate-400">
            {(bot as any).closed_positions_count || 0} closed
          </div>
          <div className="text-xs text-slate-500">
            {((bot as any).trades_per_day || 0).toFixed(2)} trades/day
          </div>
        </div>
      </td>

      {/* Win Rate */}
      <td className="hidden md:table-cell px-1 sm:px-2 py-2 text-right w-16">
        {(() => {
          const winRate = (bot as any).win_rate || 0
          const closedCount = (bot as any).closed_positions_count || 0
          const colorClass = closedCount === 0 ? 'text-slate-500' :
            winRate >= 70 ? 'text-green-400' :
            winRate >= 50 ? 'text-yellow-400' :
            'text-red-400'
          return (
            <span className={`text-sm font-medium whitespace-nowrap ${colorClass}`}>
              {closedCount === 0 ? '—' : `${winRate.toFixed(1)}%`}
            </span>
          )
        })()}
      </td>

      {/* PnL */}
      <td className="px-1 sm:px-2 py-2 text-right whitespace-nowrap">
        {(() => {
          const pnlUsd = (bot as any).total_pnl_usd || 0
          const pnlBtc = (bot as any).total_pnl_btc || 0
          const pnlPct = (bot as any).total_pnl_percentage || 0
          const isPositive = pnlUsd > 0
          const isNegative = pnlUsd < 0
          const colorClass = isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'
          return (
            <div className="flex flex-col items-end text-xs">
              <span className={colorClass}>
                {pnlBtc.toFixed(8)} BTC
              </span>
              <span className={colorClass}>
                ${pnlUsd.toFixed(2)}
              </span>
              <span className={colorClass}>
                {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
              </span>
            </div>
          )
        })()}
      </td>

      {/* Projected PnL */}
      <td className="hidden lg:table-cell px-1 sm:px-2 py-2 text-right">
        {(() => {
          const dailyPnlUsd = (bot as any).avg_daily_pnl_usd || 0
          const dailyPnlBtc = (bot as any).avg_daily_pnl_btc || 0

          // Use simple linear projection (no compounding)
          const projectPnl = (days: number) => ({
            btc: dailyPnlBtc * days,
            usd: dailyPnlUsd * days
          })

          const daily = { btc: dailyPnlBtc, usd: dailyPnlUsd }
          const weekly = projectPnl(7)
          const monthly = projectPnl(30)
          const yearly = projectPnl(365)

          const projections = [
            { label: 'Day', data: daily, bg: 'bg-slate-900/50', border: 'border-slate-700/50', opacity: '' },
            { label: 'Week', data: weekly, bg: 'bg-slate-900/40', border: 'border-slate-700/40', opacity: 'opacity-90' },
            { label: 'Month', data: monthly, bg: 'bg-slate-900/30', border: 'border-slate-700/30', opacity: 'opacity-80' },
            { label: 'Year', data: yearly, bg: 'bg-slate-900/20', border: 'border-slate-700/20', opacity: 'opacity-70' },
          ]

          const isPositive = dailyPnlUsd > 0
          const isNegative = dailyPnlUsd < 0
          const colorClass = isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'

          const renderBox = (projection: typeof projections[0]) => (
            <div className={`${colorClass} ${projection.bg} rounded px-2 py-0.5 border ${projection.border} ${projection.opacity}`}>
              <div className="font-medium text-slate-300 whitespace-nowrap">{projection.label}:</div>
              <div className="whitespace-nowrap">{projection.data.btc.toFixed(8)} BTC</div>
              <div className="whitespace-nowrap">${projection.data.usd.toFixed(2)}</div>
            </div>
          )

          return (
            <div className="flex items-start gap-1">
              <div className="text-[10px] flex-1 min-w-0">
                {isPnlExpanded ? (
                  // Show all boxes when expanded
                  <div className="space-y-1">
                    {projections.map((proj, idx) => (
                      <div key={idx}>
                        {renderBox(proj)}
                      </div>
                    ))}
                  </div>
                ) : (
                  // Show only current box when collapsed (carousel mode) with smooth transition
                  <div className="relative overflow-hidden" style={{ height: '50px' }}>
                    <div
                      className={isTransitioning ? 'transition-transform duration-500 ease-in-out' : ''}
                      style={{ transform: `translateY(-${currentTimeframeIndex * 50}px)` }}
                    >
                      {/* Render projections twice for infinite loop effect */}
                      {[...projections, ...projections].map((proj, idx) => (
                        <div key={idx} style={{ height: '50px' }} className="pr-1">
                          {renderBox(proj)}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              {/* Toggle button */}
              <button
                onClick={() => {
                  setIsPnlExpanded(!isPnlExpanded)
                  // Reset carousel to first item when collapsing
                  if (isPnlExpanded) {
                    setCurrentTimeframeIndex(0)
                    setIsTransitioning(true)
                  }
                }}
                className="flex-shrink-0 p-0.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-400 hover:text-slate-200 transition-colors"
                title={isPnlExpanded ? 'Collapse' : 'Expand all timeframes'}
              >
                {isPnlExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
            </div>
          )
        })()}
      </td>

      {/* Budget */}
      <td className="hidden lg:table-cell px-1 sm:px-2 py-2 w-20">
        <div className="flex flex-col gap-1">
          <span className="text-sm text-emerald-400 font-medium whitespace-nowrap">
            {bot.budget_percentage}%
          </span>
          {/* Budget Utilization */}
          {bot.budget_utilization_percentage !== undefined && (
            <div className="text-[10px] text-slate-400 whitespace-nowrap">
              {bot.budget_utilization_percentage.toFixed(1)}% in use
            </div>
          )}
        </div>
      </td>

      {/* Status Toggle */}
      <td className="px-1 sm:px-2 py-2 w-16">
        <div className="flex justify-center">
          {canWrite ? (
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
          ) : (
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
              bot.is_active ? 'bg-green-600/20 text-green-400' : 'bg-slate-700/50 text-slate-400'
            }`}>
              {bot.is_active ? 'Active' : 'Stopped'}
            </span>
          )}
        </div>
      </td>

      {/* Actions */}
      <td className="px-1 sm:px-2 py-2">
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


          {/* More Actions Menu */}
          <div className="relative">
            <button
              ref={menuButtonRef}
              onClick={() => setOpenMenuId(openMenuId === bot.id ? null : bot.id)}
              className="p-1.5 bg-slate-700 hover:bg-slate-600 rounded transition-colors"
              title="More actions"
            >
              <MoreVertical className="w-4 h-4" />
            </button>

            {/* Dropdown Menu - fixed positioning to escape overflow:hidden */}
            {openMenuId === bot.id && menuPosition && (
              <div
                className="fixed w-48 bg-slate-800 rounded-lg shadow-lg border border-slate-700 z-50 max-h-[80vh] overflow-y-auto"
                style={{ top: menuPosition.top, left: menuPosition.left, maxHeight: window.innerHeight - menuPosition.top - 8 }}
              >
                <button
                  onClick={() => {
                    handleOpenEdit(bot)
                    setOpenMenuId(null)
                  }}
                  className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left rounded-t-lg transition-colors"
                >
                  {canWrite ? <Edit className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  <span>{canWrite ? 'Edit Bot' : 'View Bot'}</span>
                </button>
                {canWrite && (
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
                )}
                <button
                  onClick={() => {
                    // Export bot configuration to JSON file
                    // Note: exchange_type is NOT exported - importer's account type will be used
                    const exportData = {
                      name: bot.name,
                      description: bot.description,
                      strategy_type: bot.strategy_type,
                      strategy_config: bot.strategy_config,
                      product_id: bot.product_id,
                      product_ids: (bot as any).product_ids,
                      split_budget_across_pairs: (bot as any).split_budget_across_pairs,
                      budget_percentage: bot.budget_percentage,
                    }
                    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `${bot.name.replace(/[^a-z0-9]/gi, '_')}_bot.json`
                    a.click()
                    URL.revokeObjectURL(url)
                    setOpenMenuId(null)
                  }}
                  className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left transition-colors"
                >
                  <Download className="w-4 h-4 text-blue-400" />
                  <span>Export to File</span>
                </button>
                <button
                  onClick={async () => {
                    // Copy bot configuration to clipboard
                    // Note: exchange_type is NOT exported - importer's account type will be used
                    const exportData = {
                      name: bot.name,
                      description: bot.description,
                      strategy_type: bot.strategy_type,
                      strategy_config: bot.strategy_config,
                      product_id: bot.product_id,
                      product_ids: (bot as any).product_ids,
                      split_budget_across_pairs: (bot as any).split_budget_across_pairs,
                      budget_percentage: bot.budget_percentage,
                    }
                    try {
                      await navigator.clipboard.writeText(JSON.stringify(exportData, null, 2))
                      addToast({
                        type: 'success',
                        title: 'Copied to Clipboard',
                        message: `"${bot.name}" config ready to share`,
                      })
                    } catch (err) {
                      addToast({
                        type: 'error',
                        title: 'Copy Failed',
                        message: 'Could not access clipboard',
                      })
                    }
                    setOpenMenuId(null)
                  }}
                  className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left transition-colors"
                >
                  <Clipboard className="w-4 h-4 text-green-400" />
                  <span>Copy to Clipboard</span>
                </button>

                {/* Copy to Account - show if there are other accounts to copy to */}
                {canWrite && (() => {
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

                {/* Separator if bot has open positions and user can write */}
                {canWrite && (bot.open_positions_count ?? 0) > 0 && (
                  <div className="border-t border-slate-600 my-1"></div>
                )}

                {/* Cancel All Positions */}
                {canWrite && (bot.open_positions_count ?? 0) > 0 && (
                  <button
                    onClick={async () => {
                      setOpenMenuId(null)
                      if (await confirm({
                        title: 'Cancel All Deals',
                        message: `Cancel all ${bot.open_positions_count} open position(s) for "${bot.name}"?\n\nThis will mark them as CANCELLED without selling. Your holdings will remain as-is (no P&L impact).\n\nThis action cannot be undone.`,
                        variant: 'danger',
                        confirmLabel: 'Cancel All',
                      })) {
                        cancelAllPositions.mutate(bot.id)
                      }
                    }}
                    className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left transition-colors"
                  >
                    <XCircle className="w-4 h-4 text-orange-400" />
                    <span>Cancel All Deals</span>
                  </button>
                )}

                {/* Sell All Positions at Market Price */}
                {canWrite && (bot.open_positions_count ?? 0) > 0 && (
                  <button
                    onClick={async () => {
                      setOpenMenuId(null)
                      if (await confirm({
                        title: 'Sell All at Market',
                        message: `Sell all ${bot.open_positions_count} position(s) for "${bot.name}" at MARKET price?\n\nThis will immediately close all positions and realize gains/losses.\n\nThis action cannot be undone.`,
                        variant: 'danger',
                        confirmLabel: 'Sell All',
                      })) {
                        sellAllPositions.mutate(bot.id)
                      }
                    }}
                    className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left transition-colors"
                  >
                    <DollarSign className="w-4 h-4 text-yellow-400" />
                    <span>Sell All at Market</span>
                  </button>
                )}

                {canWrite && (
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
                )}
              </div>
            )}
          </div>
        </div>
      </td>
    </tr>
  )
}
