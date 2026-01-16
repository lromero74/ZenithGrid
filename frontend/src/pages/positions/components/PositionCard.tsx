import { AlertCircle, BarChart2, Settings } from 'lucide-react'
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
import axios from 'axios'
import { API_BASE_URL } from '../../../config/api'

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
}: PositionCardProps) => {
  const pnl = position._cachedPnL
  const fundsUsedPercent = (position.total_quote_spent / position.max_quote_allowed) * 100

  const bot = bots?.find(b => b.id === position.bot_id)
  const strategyConfig = position.strategy_config_snapshot || bot?.strategy_config || {}

  const handleCancelLimitClose = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirm('Cancel limit close order?')) {
      try {
        await axios.post(`${API_BASE_URL}/api/positions/${position.id}/cancel-limit-close`)
        onRefetch()
      } catch (err: any) {
        alert(`Error: ${err.response?.data?.detail || err.message}`)
      }
    }
  }

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
      {/* Deal Row - 3Commas Style Horizontal Layout */}
      <div
        className="p-4 cursor-pointer hover:bg-slate-750 transition-colors"
        onClick={() => onTogglePosition(position.id)}
      >
        <div className="grid grid-cols-12 gap-4 items-start text-sm">
          {/* Column 1: Bot Info + Strategy (2 cols) */}
          <div className="col-span-2">
            <div className="text-white font-semibold mb-1">
              {bot?.name || `Bot #${position.bot_id || 'N/A'}`}
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
          <div className="col-span-2 flex items-start gap-2">
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
                {/* Error Indicator (like 3Commas) */}
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
                  const displayReason = reason.replace(/^\[(APPROVED|BORDERLINE|QUESTIONABLE)\]\s*/, '');

                  if (isApproved) {
                    return (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-600/20 border border-green-600/50 text-green-400 cursor-help"
                        title={displayReason || 'Approved coin'}
                      >
                        APPROVED
                      </span>
                    );
                  } else if (isBorderline) {
                    return (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-yellow-600/20 border border-yellow-600/50 text-yellow-400 cursor-help"
                        title={displayReason || 'Borderline coin'}
                      >
                        BORDERLINE
                      </span>
                    );
                  } else if (isQuestionable) {
                    return (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-orange-600/20 border border-orange-600/50 text-orange-400 cursor-help"
                        title={displayReason || 'Questionable coin'}
                      >
                        QUESTIONABLE
                      </span>
                    );
                  } else {
                    return (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-600/20 border border-red-600/50 text-red-400 cursor-help"
                        title={reason || 'Blacklisted coin'}
                      >
                        BLACKLISTED
                      </span>
                    );
                  }
                })()}
              </div>
              <div className="flex items-center gap-2">
                <div className="text-[10px] text-slate-400">My Coinbase Advanced</div>
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
          <div className="col-span-4">
            <PriceBar
              position={position}
              currentPrice={currentPrice || position.average_buy_price}
              pnl={pnl}
              strategyConfig={strategyConfig}
              fundsUsedPercent={fundsUsedPercent}
            />
          </div>

          {/* Column 4: Volume (2 cols) */}
          <div className="col-span-2">
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
                <div className={pnl.btc >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {pnl.btc >= 0 ? '+' : ''}${Math.abs(pnl.usd).toFixed(2)}
                </div>
              )}
            </div>
          </div>

          {/* Column 5: Avg. O (Averaging Orders) - Like 3Commas (1 col) */}
          <div className="col-span-1">
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

          {/* Column 6: Created (1 col) */}
          <div className="col-span-1">
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

        {/* Our Special "Better than 3Commas" Budget Usage Bar */}
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

        {/* Action Buttons Row */}
        <div className="mt-3 px-4 flex items-center gap-3">
          <button
            className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
            onClick={(e) => {
              e.stopPropagation()
              onTogglePosition(position.id)
            }}
          >
            <span>🚫</span> Cancel
          </button>

          {/* Show edit/cancel if there's a pending limit order */}
          {position.closing_via_limit ? (
            <>
              <button
                className="text-xs text-yellow-400 hover:text-yellow-300 flex items-center gap-1"
                onClick={(e) => {
                  e.stopPropagation()
                  onOpenLimitClose(position)
                }}
              >
                <span>✏️</span> Edit limit price
              </button>
              <button
                className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
                onClick={handleCancelLimitClose}
              >
                <span>❌</span> Cancel limit order
              </button>
            </>
          ) : (
            <>
              <button
                className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                onClick={(e) => {
                  e.stopPropagation()
                  onCheckSlippage(position.id)
                }}
              >
                <span>💱</span> Close at market
              </button>
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
            className="text-xs text-slate-400 hover:text-slate-300 flex items-center gap-1"
            onClick={(e) => {
              e.stopPropagation()
              onOpenLogs(position)
            }}
          >
            <span>📊</span> AI Reasoning
          </button>
          <button
            className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
            onClick={(e) => {
              e.stopPropagation()
              onOpenAddFunds(position)
            }}
          >
            <span>💰</span> Add funds
          </button>
          <button
            className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1"
            onClick={(e) => {
              e.stopPropagation()
              onOpenEditSettings(position)
            }}
          >
            <Settings size={12} /> Edit deal
          </button>
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

        {/* Notes Section (like 3Commas) */}
        <div className="mt-3 px-4 pb-3">
          <div
            className="text-xs flex items-center gap-2 cursor-pointer hover:opacity-70 transition-opacity"
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
