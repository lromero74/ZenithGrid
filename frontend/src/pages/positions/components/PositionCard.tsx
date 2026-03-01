import { useState, useRef, useEffect } from 'react'
import { AlertCircle, BarChart2, Brain, ChevronDown, Edit, Play, Scale, Settings, Square, TrendingUp, TrendingDown } from 'lucide-react'
import { formatDateTime, formatDateTimeCompact, formatDuration } from '../../../utils/dateFormat'
import type { Position, Bot } from '../../../types'
import CoinIcon from '../../../components/CoinIcon'
import {
  getQuoteCurrency,
  formatBaseAmount,
  formatQuoteAmount,
  AISentimentIcon,
  DealChart,
  PriceBar,
} from '../../../components/positions'
import { GridVisualizer } from '../../../components/GridVisualizer'
import { api, botsApi } from '../../../services/api'
import { useConfirm } from '../../../contexts/ConfirmContext'
import { useNotifications } from '../../../contexts/NotificationContext'
import { useQueryClient } from '@tanstack/react-query'

interface PositionCardProps {
  position: Position & { _cachedPnL?: any }
  currentPrice: number | undefined
  bots: Bot[] | undefined
  btcUsdPrice: number
  trades: any[] | undefined
  selectedPosition: number | null
  onTogglePosition: (positionId: number) => void
  onOpenChart: (productId: string, position: Position) => void
  onOpenLightweightChart: (productId: string, position: Position) => void
  onOpenLimitClose: (position: Position) => void
  onOpenLogs: (position: Position) => void
  onOpenAddFunds: (position: Position) => void
  onOpenEditSettings: (position: Position) => void
  onOpenNotes: (position: Position) => void
  onOpenTradeHistory: (position: Position) => void
  onCheckSlippage: (positionId: number) => void
  onRefetch: () => void
  onEditBot?: (bot: Bot) => void
  canWrite?: boolean
}

export const PositionCard = ({
  position,
  currentPrice,
  bots,
  btcUsdPrice,
  trades,
  selectedPosition,
  onTogglePosition,
  onOpenChart,
  onOpenLightweightChart,
  onOpenLimitClose,
  onOpenLogs,
  onOpenAddFunds,
  onOpenEditSettings,
  onOpenNotes,
  onOpenTradeHistory,
  onCheckSlippage,
  onRefetch,
  onEditBot,
  canWrite = true,
}: PositionCardProps) => {
  const confirm = useConfirm()
  const { addToast } = useNotifications()
  const queryClient = useQueryClient()
  const [showBotMenu, setShowBotMenu] = useState(false)
  const botMenuRef = useRef<HTMLDivElement>(null)
  const pnl = position._cachedPnL
  const fundsUsedPercent = (position.total_quote_spent / position.max_quote_allowed) * 100

  const bot = bots?.find(b => b.id === position.bot_id)
  const strategyConfig = position.strategy_config_snapshot || bot?.strategy_config || {}

  // Close bot menu on outside click
  useEffect(() => {
    if (!showBotMenu) return
    const handler = (e: MouseEvent) => {
      if (botMenuRef.current && !botMenuRef.current.contains(e.target as Node)) {
        setShowBotMenu(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showBotMenu])

  const handleToggleBot = async () => {
    if (!bot) return
    setShowBotMenu(false)
    try {
      if (bot.is_active) {
        await botsApi.stop(bot.id)
        addToast({ type: 'info', title: 'Bot Stopped', message: `${bot.name} stopped` })
      } else {
        await botsApi.start(bot.id)
        addToast({ type: 'success', title: 'Bot Started', message: `${bot.name} started` })
      }
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    } catch (err: any) {
      addToast({ type: 'error', title: 'Error', message: err.response?.data?.detail || err.message })
    }
  }

  const handleCancelLimitClose = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (await confirm({ title: 'Cancel Limit Close', message: 'Cancel limit close order?', variant: 'warning', confirmLabel: 'Cancel Order' })) {
      try {
        await api.post(`/positions/${position.id}/cancel-limit-close`)
        onRefetch()
      } catch (err: any) {
        addToast({ type: 'error', title: 'Error', message: err.response?.data?.detail || err.message })
      }
    }
  }

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
      {/* Deal Row - Horizontal Layout */}
      <div
        className="p-4 cursor-pointer hover:bg-slate-750 transition-colors"
        onClick={() => onTogglePosition(position.id)}
      >
        <div className="grid grid-cols-2 sm:grid-cols-12 gap-4 items-start text-sm">
          {/* Column 1: Bot Info + Strategy (2 cols) */}
          <div className="col-span-1 sm:col-span-2">
            <div className="flex items-center gap-2 mb-1">
              {/* Bot name with dropdown menu */}
              <div className="relative" ref={botMenuRef}>
                <button
                  className="text-white font-semibold flex items-center gap-1 hover:text-blue-300 transition-colors"
                  onClick={(e) => {
                    e.stopPropagation()
                    if (bot) setShowBotMenu(!showBotMenu)
                  }}
                  title={bot ? 'Bot actions' : undefined}
                >
                  {bot?.name || `Bot #${position.bot_id || 'N/A'}`}
                  {bot && <ChevronDown size={12} className={`transition-transform ${showBotMenu ? 'rotate-180' : ''}`} />}
                </button>
                {showBotMenu && bot && (
                  <div className="absolute left-0 top-full mt-1 w-40 bg-slate-800 rounded-lg shadow-lg border border-slate-700 z-50 py-1">
                    {canWrite && (bot.is_active ? (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleToggleBot() }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-red-400 hover:bg-slate-700 transition-colors"
                      >
                        <Square size={12} /> Stop Bot
                      </button>
                    ) : (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleToggleBot() }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-green-400 hover:bg-slate-700 transition-colors"
                      >
                        <Play size={12} /> Start Bot
                      </button>
                    ))}
                    {canWrite && onEditBot && (
                      <button
                        onClick={(e) => { e.stopPropagation(); setShowBotMenu(false); onEditBot(bot) }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition-colors"
                      >
                        <Edit size={12} /> Edit Bot
                      </button>
                    )}
                  </div>
                )}
              </div>
              {/* Bidirectional DCA: Show direction badge */}
              {position.direction && position.direction !== 'long' && (
                <div className="flex items-center gap-1 px-1.5 py-0.5 bg-red-500/20 border border-red-500/30 rounded text-[9px] font-semibold text-red-400">
                  <TrendingDown size={10} />
                  <span>SHORT</span>
                </div>
              )}
              {position.direction === 'long' && (
                <div className="flex items-center gap-1 px-1.5 py-0.5 bg-green-500/20 border border-green-500/30 rounded text-[9px] font-semibold text-green-400">
                  <TrendingUp size={10} />
                  <span>LONG</span>
                </div>
              )}
              {/* Perpetual futures badges */}
              {position.product_type === 'future' && position.leverage && (
                <div className="px-1.5 py-0.5 bg-purple-500/20 border border-purple-500/30 rounded text-[9px] font-semibold text-purple-400">
                  {position.leverage}x
                </div>
              )}
              {position.product_type === 'future' && (
                <div className="px-1.5 py-0.5 bg-yellow-500/20 border border-yellow-500/30 rounded text-[9px] font-semibold text-yellow-400">
                  PERP
                </div>
              )}
            </div>
            <div className="text-[10px] text-slate-400 space-y-0.5">
              {bot?.strategy_type && (
                <div>[{bot.strategy_type.toUpperCase()}]</div>
              )}
              {strategyConfig.take_profit_percent && (
                <div>MP: {strategyConfig.take_profit_percent}%</div>
              )}
              {strategyConfig.base_order_size && (
                <div>BO: {strategyConfig.base_order_size}</div>
              )}
            </div>
          </div>

          {/* Column 2: Pair + Exchange (1.5 cols) */}
          <div className="col-span-1 sm:col-span-2 flex items-start gap-2">
            <CoinIcon
              symbol={position.product_id?.split('-')[0] || 'BTC'}
              size="sm"
            />
            <div className="flex-1">
              <div className="flex items-center gap-1.5">
                <span
                  className="text-white font-semibold cursor-pointer hover:opacity-80 transition-opacity"
                  onClick={(e) => {
                    e.stopPropagation()
                    onOpenChart(position.product_id || 'ETH-BTC', position)
                  }}
                >
                  {position.product_id || 'ETH-BTC'}
                </span>
                <BarChart2
                  size={14}
                  className="text-slate-400 hover:text-blue-400 cursor-pointer transition-colors"
                  onClick={(e) => {
                    e.stopPropagation()
                    onOpenLightweightChart(position.product_id || 'ETH-BTC', position)
                  }}
                />
                {/* AI Sentiment Indicator */}
                {position.bot_id && (
                  <AISentimentIcon
                    botId={position.bot_id}
                    productId={position.product_id || 'ETH-BTC'}
                  />
                )}
                {/* Error Indicator */}
                {position.last_error_message && (
                  <div
                    className="flex items-center cursor-help"
                    title={`Error: ${position.last_error_message}\n${position.last_error_timestamp ? `Time: ${formatDateTime(position.last_error_timestamp)}` : ''}`}
                  >
                    <AlertCircle size={14} className="text-red-400" />
                  </div>
                )}
                {/* Coin Status Badge - different colors by category */}
                {position.is_blacklisted && (() => {
                  const reason = position.blacklist_reason || '';
                  const isApproved = reason.startsWith('[APPROVED]');
                  const isBorderline = reason.startsWith('[BORDERLINE]');
                  const isQuestionable = reason.startsWith('[QUESTIONABLE]');
                  const isMeme = reason.startsWith('[MEME]');
                  const displayReason = reason.replace(/^\[(APPROVED|BORDERLINE|QUESTIONABLE|MEME)\]\s*/, '');

                  let badgeClass = 'bg-red-600/20 border-red-600/50 text-red-400';
                  let label = 'BLACKLISTED';
                  let fallback = 'Blacklisted coin';
                  let tooltipReason = reason;

                  if (isApproved) {
                    badgeClass = 'bg-green-600/20 border-green-600/50 text-green-400';
                    label = 'APPROVED';
                    fallback = 'Approved coin';
                    tooltipReason = displayReason;
                  } else if (isBorderline) {
                    badgeClass = 'bg-yellow-600/20 border-yellow-600/50 text-yellow-400';
                    label = 'BORDERLINE';
                    fallback = 'Borderline coin';
                    tooltipReason = displayReason;
                  } else if (isQuestionable) {
                    badgeClass = 'bg-orange-600/20 border-orange-600/50 text-orange-400';
                    label = 'QUESTIONABLE';
                    fallback = 'Questionable coin';
                    tooltipReason = displayReason;
                  } else if (isMeme) {
                    badgeClass = 'bg-purple-600/20 border-purple-600/50 text-purple-400';
                    label = 'MEME';
                    fallback = 'Meme coin';
                    tooltipReason = displayReason;
                  }

                  return (
                    <div className="group/badge relative">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border cursor-help ${badgeClass}`}>
                        {label}
                      </span>
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 bg-slate-900 border border-slate-600 rounded shadow-xl text-[11px] text-slate-200 whitespace-nowrap opacity-0 invisible group-hover/badge:opacity-100 group-hover/badge:visible transition-all duration-150 delay-[250ms] z-50 pointer-events-none">
                        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 rotate-45 w-2 h-2 bg-slate-900 border-r border-b border-slate-600" />
                        {tooltipReason || fallback}
                      </div>
                    </div>
                  );
                })()}
              </div>
              <div className="flex items-center gap-2">
                <div className="text-[10px] text-slate-400">{(bot as any)?.account_name || 'Exchange Account'}</div>
                {/* Limit Close Status Badge */}
                {position.closing_via_limit && position.limit_order_details && (
                  <div className="bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded text-[10px] font-medium">
                    Limit Close {position.limit_order_details.fill_percentage > 0 ? `${position.limit_order_details.fill_percentage.toFixed(0)}%` : 'Pending'}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Column 3: uPnL + Price Bar (4 cols) */}
          <div className="col-span-2 sm:col-span-4">
            <PriceBar
              position={position}
              currentPrice={currentPrice || position.average_buy_price}
              pnl={pnl}
              strategyConfig={strategyConfig}
              fundsUsedPercent={fundsUsedPercent}
            />
          </div>

          {/* Column 4: Volume (2 cols) - hidden on mobile */}
          <div className="hidden sm:block col-span-2">
            <div className="text-[10px] space-y-0.5">
              <div className="text-white">
                {formatQuoteAmount(position.total_quote_spent, position.product_id || 'ETH-BTC')}
                {getQuoteCurrency(position.product_id || 'ETH-BTC').symbol === 'BTC' && btcUsdPrice > 0 && (
                  <span className="text-slate-400">
                    {' '}(${(position.total_quote_spent * btcUsdPrice).toLocaleString(undefined, { maximumFractionDigits: 2 })})
                  </span>
                )}
              </div>
              <div className="text-slate-400">{formatBaseAmount(position.total_base_acquired, position.product_id || 'ETH-BTC')}</div>
              {pnl && pnl.usd !== undefined && (
                <div className={pnl.quote >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {pnl.quote >= 0 ? '+' : ''}${Math.abs(pnl.usd).toFixed(2)}
                </div>
              )}
            </div>
          </div>

          {/* Column 5: Avg. O (Averaging Orders) (1 col) - hidden on mobile */}
          <div className="hidden sm:block col-span-1">
            <div className="text-[10px] space-y-0.5">
              <div className="text-slate-400">
                Completed: {(() => {
                  // Calculate DCA count from trade_count (total trades - 1 initial = DCA count)
                  // If trades array is available AND has trades for THIS position, use it for more detail
                  if (trades && trades.length > 0) {
                    const positionTrades = trades.filter(t => t.position_id === position.id && t.side === 'buy') || []
                    // Only use trades array if it actually has trades for this position
                    // Otherwise the trades are for a different selected position
                    if (positionTrades.length > 0) {
                      const autoSO = positionTrades.filter(t => t.trade_type === 'dca').length
                      const manualSO = positionTrades.filter(t => t.trade_type === 'manual_safety_order').length

                      if (manualSO > 0) {
                        return `${autoSO} (+${manualSO})`
                      }
                      return autoSO
                    }
                  }

                  // Fallback: use trade_count from position (trade_count - 1 = DCA count)
                  const dcaCount = Math.max(0, (position.trade_count || 0) - 1)
                  return dcaCount
                })()}
              </div>
              <div className="text-slate-400">Active: {position.pending_orders_count || 0}</div>
              <div className="text-slate-400">
                Max: {position.strategy_config_snapshot?.max_safety_orders ?? bot?.strategy_config?.max_safety_orders ?? 0}
              </div>
            </div>
          </div>

          {/* Column 6: Created (1 col) - hidden on mobile */}
          <div className="hidden sm:block col-span-1">
            <div className="text-[10px] space-y-0.5">
              <div
                className="text-blue-400 hover:text-blue-300 cursor-pointer underline"
                onClick={(e) => {
                  e.stopPropagation()
                  onOpenTradeHistory(position)
                }}
                title="Click to view trade history"
              >
                Deal #{position.user_deal_number ?? position.id}
              </div>
              <div className="text-slate-400">Start: {formatDateTimeCompact(position.opened_at)}</div>
              <div className="text-slate-400">Age: {formatDuration(position.opened_at)}</div>
            </div>
          </div>
        </div>

        {/* Budget Usage Bar */}
        <div className="mt-3 px-4">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-slate-400">Budget Used</span>
            <span className="text-slate-300">
              {formatQuoteAmount(position.total_quote_spent, position.product_id || 'ETH-BTC')} / {formatQuoteAmount(position.max_quote_allowed, position.product_id || 'ETH-BTC')}
              <span className="text-slate-400 ml-1">({fundsUsedPercent.toFixed(0)}%)</span>
            </span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all"
              style={{ width: `${Math.min(fundsUsedPercent, 100)}%` }}
            />
          </div>
        </div>

        {/* Perpetual Futures Info Row */}
        {position.product_type === 'future' && (
          <div className="mt-2 px-4 py-2 bg-purple-500/5 border-t border-purple-500/20 grid grid-cols-4 gap-2 text-[10px]">
            {position.liquidation_price != null && (
              <div>
                <span className="text-slate-500">Liq Price</span>
                <div className="text-red-400 font-medium">${position.liquidation_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
              </div>
            )}
            {position.tp_price != null && (
              <div>
                <span className="text-slate-500">TP</span>
                <div className="text-green-400">${position.tp_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
              </div>
            )}
            {position.sl_price != null && (
              <div>
                <span className="text-slate-500">SL</span>
                <div className="text-red-400">${position.sl_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
              </div>
            )}
            {position.unrealized_pnl != null && (
              <div>
                <span className="text-slate-500">uPnL</span>
                <div className={position.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {position.unrealized_pnl >= 0 ? '+' : ''}{position.unrealized_pnl.toFixed(2)} USDC
                </div>
              </div>
            )}
            {(position.funding_fees_total ?? 0) > 0 && (
              <div>
                <span className="text-slate-500">Funding</span>
                <div className="text-yellow-400">-{position.funding_fees_total?.toFixed(4)} USDC</div>
              </div>
            )}
          </div>
        )}

        {/* Action Buttons Row */}
        <div className="mt-3 px-4 flex flex-wrap items-center gap-2 sm:gap-3">
          {canWrite && (
          <button
            className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
            onClick={(e) => {
              e.stopPropagation()
              onTogglePosition(position.id)
            }}
          >
            <span>🚫</span> Cancel
          </button>
          )}

          {/* Show edit/cancel if there's a pending limit order */}
          {position.closing_via_limit ? (
            <>
              {canWrite && (
              <button
                className="text-xs text-yellow-400 hover:text-yellow-300 flex items-center gap-1"
                onClick={(e) => {
                  e.stopPropagation()
                  onOpenLimitClose(position)
                }}
              >
                <span>✏️</span> Edit limit price
              </button>
              )}
              {canWrite && (
              <button
                className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
                onClick={handleCancelLimitClose}
              >
                <span>❌</span> Cancel limit order
              </button>
              )}
            </>
          ) : (
            <>
              {canWrite && (
              <button
                className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                onClick={(e) => {
                  e.stopPropagation()
                  onCheckSlippage(position.id)
                }}
              >
                <span>💱</span> Close at market
              </button>
              )}
              <button
                className="text-xs text-green-400 hover:text-green-300 flex items-center gap-1"
                onClick={(e) => {
                  e.stopPropagation()
                  onOpenLimitClose(position)
                }}
              >
                <span>📊</span> Close at limit
              </button>
            </>
          )}
          <button
            className="text-xs px-2 py-1 bg-purple-500/10 border border-purple-500/30 text-purple-300 hover:bg-purple-500/20 hover:border-purple-500/50 hover:text-purple-200 rounded flex items-center gap-1 transition-colors"
            onClick={(e) => {
              e.stopPropagation()
              onOpenLogs(position)
            }}
          >
            <Brain size={12} /> Decision History
          </button>
          {canWrite && (
          <button
            className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
            onClick={(e) => {
              e.stopPropagation()
              onOpenAddFunds(position)
            }}
          >
            <span>💰</span> Add funds
          </button>
          )}
          {canWrite && (
          <button
            className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1"
            onClick={(e) => {
              e.stopPropagation()
              onOpenEditSettings(position)
            }}
          >
            <Settings size={12} /> Edit deal
          </button>
          )}
          {canWrite && position.computed_max_budget != null && position.computed_max_budget > (position.max_quote_allowed || 0) && (
          <button
            className="text-xs text-sky-400 hover:text-sky-300 flex items-center gap-1"
            title="Recalculate budget to base order + all safety orders with volume scaling"
            onClick={async (e) => {
              e.stopPropagation()
              try {
                const result = await api.post(`/positions/${position.id}/resize-budget`)
                const d = result.data
                addToast({ type: 'success', title: 'Budget Resized', message: `${d.old_max.toFixed(8)} → ${d.new_max.toFixed(8)} ${d.quote_currency}` })
                onRefetch()
              } catch (err: any) {
                addToast({ type: 'error', title: 'Resize Failed', message: err.response?.data?.detail || err.message })
              }
            }}
          >
            <Scale size={12} /> Resize budget
          </button>
          )}
          <button
            className="text-xs text-slate-400 hover:text-slate-300 flex items-center gap-1"
            onClick={(e) => {
              e.stopPropagation()
              onRefetch()
            }}
          >
            <span>🔄</span> Refresh
          </button>
        </div>

        {/* Notes Section */}
        <div className="mt-3 px-4 pb-3">
          {canWrite ? (
          <div
            className="text-xs inline-flex items-center gap-2 cursor-pointer hover:opacity-70 transition-opacity"
            onClick={(e) => {
              e.stopPropagation()
              onOpenNotes(position)
            }}
          >
            <span>📝</span>
            {position.notes ? (
              <span className="text-slate-300">{position.notes}</span>
            ) : (
              <span className="text-slate-500 italic">You can place a note here</span>
            )}
          </div>
          ) : position.notes ? (
          <div className="text-xs inline-flex items-center gap-2">
            <span>📝</span>
            <span className="text-slate-300">{position.notes}</span>
          </div>
          ) : null}
        </div>
      </div>

      {/* Expandable Details Section (keep existing chart/details) */}
      {selectedPosition === position.id && (
        <div className="border-t border-slate-700 bg-slate-900/50 p-6">
          {/* Grid Trading Visualization */}
          {bot?.strategy_type === 'grid_trading' && bot?.strategy_config?.grid_state && currentPrice ? (
            <GridVisualizer
              gridState={bot.strategy_config.grid_state}
              currentPrice={currentPrice}
              productId={position.product_id || 'ETH-BTC'}
            />
          ) : (
            /* Default Deal Chart for non-grid positions */
            <DealChart
              position={position}
              productId={position.product_id || "ETH-BTC"}
              currentPrice={currentPrice}
              trades={trades}
            />
          )}
        </div>
      )}
    </div>
  )
}
