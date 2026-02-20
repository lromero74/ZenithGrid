import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { botsApi } from '../services/api'
import { BarChart2, Check, X, Clock, Target, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { formatDateTime } from '../utils/dateFormat'

interface IndicatorLogsProps {
  botId: number
  isOpen: boolean
  onClose: () => void
}

interface ConditionDetail {
  type: string
  timeframe?: string
  operator?: string
  threshold?: number
  actual_value: number | null
  result: boolean
  negated?: boolean
  error?: string
  reason?: string
  previous_value?: number
  indicator?: string
}

interface IndicatorLog {
  id: number
  bot_id: number
  timestamp: string
  product_id: string
  phase: string
  conditions_met: boolean
  conditions_detail: ConditionDetail[]
  indicators_snapshot: Record<string, any> | null
  current_price: number | null
}

function IndicatorLogs({ botId, isOpen, onClose }: IndicatorLogsProps) {
  const [filterPhase, setFilterPhase] = useState<string>('all')
  const [filterResult, setFilterResult] = useState<string>('all')

  const { data: logs = [], isLoading, refetch } = useQuery({
    queryKey: ['indicator-logs', botId],
    queryFn: () => {
      const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
      return botsApi.getIndicatorLogs(botId, 1000, 0, undefined, undefined, undefined, since)
    },
    enabled: isOpen,
    refetchInterval: isOpen ? 10000 : false,
  })

  useEffect(() => {
    if (isOpen) {
      refetch()
    }
  }, [isOpen, refetch])

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }

    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const filteredLogs = logs.filter((log: IndicatorLog) => {
    if (filterPhase !== 'all' && log.phase !== filterPhase) return false
    if (filterResult !== 'all') {
      if (filterResult === 'met' && !log.conditions_met) return false
      if (filterResult === 'not_met' && log.conditions_met) return false
    }
    return true
  })

  // Calculate stats for display
  const totalMet = logs.filter((log: IndicatorLog) => log.conditions_met).length
  const totalNotMet = logs.filter((log: IndicatorLog) => !log.conditions_met).length

  const getPhaseLabel = (phase: string) => {
    switch (phase) {
      case 'base_order':
        return 'Entry'
      case 'safety_order':
        return 'DCA'
      case 'take_profit':
        return 'Exit'
      default:
        return phase
    }
  }

  const getPhaseColor = (phase: string) => {
    switch (phase) {
      case 'base_order':
        return 'bg-green-600/20 border-green-600/50 text-green-400'
      case 'safety_order':
        return 'bg-yellow-600/20 border-yellow-600/50 text-yellow-400'
      case 'take_profit':
        return 'bg-purple-600/20 border-purple-600/50 text-purple-400'
      default:
        return 'bg-slate-600/20 border-slate-600/50 text-slate-400'
    }
  }

  const getIndicatorLabel = (type: string) => {
    const labels: Record<string, string> = {
      rsi: 'RSI',
      macd: 'MACD',
      bb_percent: 'BB%',
      ema_cross: 'EMA Cross',
      sma_cross: 'SMA Cross',
      stochastic: 'Stoch',
      volume: 'Volume',
      ai_buy: 'AI Buy',
      ai_sell: 'AI Sell',
      bull_flag: 'Bull Flag',
      price_drop: 'Price Drop',
      budget: 'Budget',
    }
    return labels[type] || type
  }

  const getOperatorSymbol = (operator: string) => {
    const symbols: Record<string, string> = {
      greater_than: '>',
      less_than: '<',
      greater_equal: '>=',
      less_equal: '<=',
      equal: '=',
      not_equal: '!=',
      crossing_above: 'crossing above',
      crossing_below: 'crossing below',
      increasing: 'increasing',
      decreasing: 'decreasing',
    }
    return symbols[operator] || operator
  }

  const formatValue = (value: number | null, type: string) => {
    if (value === null || value === undefined) return 'N/A'
    if (type === 'bb_percent') return `${value.toFixed(1)}%`
    if (type === 'volume') return value.toLocaleString()
    // MACD values can be very small (e.g., 0.00000123), use scientific notation for tiny values
    if (type === 'macd') {
      if (Math.abs(value) < 0.000001 && value !== 0) {
        return value.toExponential(2)  // e.g., 1.23e-8
      }
      return value.toFixed(8)  // Show 8 decimal precision for MACD
    }
    // RSI and Stochastic are 0-100, show 1 decimal
    if (type === 'rsi' || type === 'stochastic') return value.toFixed(1)
    // Price drop values are BTC prices, show 8 decimals
    if (type === 'price_drop') return value.toFixed(8)
    return value.toFixed(4)  // Default: 4 decimals for other indicators
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-900 rounded-lg w-full max-w-4xl max-h-[90vh] flex flex-col border border-slate-700">
        {/* Header */}
        <div className="p-6 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <BarChart2 className="w-6 h-6 text-cyan-400" />
            <div>
              <h3 className="text-xl font-bold">Indicator Evaluation Log</h3>
              <p className="text-sm text-slate-400">Bot #{botId} - Condition History</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Filters */}
        <div className="p-4 border-b border-slate-700 bg-slate-800/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <label className="text-sm font-medium text-slate-300">Phase:</label>
                <select
                  value={filterPhase}
                  onChange={(e) => setFilterPhase(e.target.value)}
                  className="bg-slate-700 text-white px-3 py-1.5 rounded border border-slate-600 text-sm"
                >
                  <option value="all">All Phases</option>
                  <option value="base_order">Entry Only</option>
                  <option value="safety_order">DCA Only</option>
                  <option value="take_profit">Exit Only</option>
                </select>
              </div>
              <div className="flex items-center space-x-2">
                <label className="text-sm font-medium text-slate-300">Result:</label>
                <select
                  value={filterResult}
                  onChange={(e) => setFilterResult(e.target.value)}
                  className="bg-slate-700 text-white px-3 py-1.5 rounded border border-slate-600 text-sm"
                >
                  <option value="all">All (Debug Mode)</option>
                  <option value="met">✓ Matches Only</option>
                  <option value="not_met">✗ Failures Only</option>
                </select>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <span className="text-sm text-slate-400">
                ({filteredLogs.length} {filteredLogs.length === 1 ? 'entry' : 'entries'})
              </span>
              {filterResult === 'all' && (
                <span className="text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-700/50 px-2 py-1 rounded">
                  Debug: Showing all evaluations
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Logs List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {isLoading ? (
            <div className="text-center text-slate-400 py-8">Loading indicator logs...</div>
          ) : filteredLogs.length === 0 ? (
            <div className="text-center text-slate-400 py-8">
              {filterPhase === 'all' && filterResult === 'all'
                ? 'No indicator logs yet. Logs will appear as the bot evaluates conditions.'
                : 'No matching logs found with current filters.'}
            </div>
          ) : (
            filteredLogs.map((log: IndicatorLog) => (
              <div
                key={log.id}
                className="bg-slate-800 rounded-lg p-4 border border-slate-700 hover:border-slate-600 transition-colors"
              >
                {/* Header Row */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center space-x-3">
                    {log.conditions_met ? (
                      <Check className="w-5 h-5 text-green-400" />
                    ) : (
                      <X className="w-5 h-5 text-red-400" />
                    )}
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className={`px-2 py-1 rounded text-xs font-medium border ${getPhaseColor(log.phase)}`}>
                          {getPhaseLabel(log.phase)}
                        </span>
                        <span className={`px-2 py-1 rounded text-xs font-medium border ${
                          log.conditions_met
                            ? 'bg-green-600/20 border-green-600/50 text-green-400'
                            : 'bg-red-600/20 border-red-600/50 text-red-400'
                        }`}>
                          {log.conditions_met ? 'MET' : 'NOT MET'}
                        </span>
                      </div>
                      <div className="flex items-center space-x-3 mt-1 text-xs text-slate-400">
                        <span className="flex items-center space-x-1">
                          <Clock className="w-3 h-3" />
                          <span>{formatDateTime(log.timestamp)}</span>
                        </span>
                        <span className="px-1.5 py-0.5 bg-cyan-600/20 border border-cyan-600/50 rounded text-xs font-medium text-cyan-300">
                          {log.product_id}
                        </span>
                        {log.current_price && (
                          <span className="flex items-center space-x-1">
                            <Target className="w-3 h-3" />
                            <span>{(() => {
                              const quoteCurrency = log.product_id?.split('-')[1] || 'BTC'
                              if (quoteCurrency === 'USD') {
                                return `${log.current_price.toFixed(2)} USD`
                              }
                              return `${log.current_price.toFixed(8)} BTC`
                            })()}</span>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Conditions Detail */}
                <div className="bg-slate-900/50 rounded p-3 border border-slate-700">
                  <p className="text-sm font-medium text-cyan-300 mb-2">Condition Evaluations:</p>
                  <div className="space-y-2">
                    {(log.conditions_detail || []).map((cond, idx) => (
                      <div
                        key={idx}
                        className={`flex items-center justify-between p-2 rounded text-sm ${
                          cond.result
                            ? 'bg-green-900/20 border border-green-700/30'
                            : 'bg-red-900/20 border border-red-700/30'
                        }`}
                      >
                        <div className="flex items-center space-x-2">
                          {cond.result ? (
                            <TrendingUp className="w-4 h-4 text-green-400" />
                          ) : cond.error ? (
                            <Minus className="w-4 h-4 text-yellow-400" />
                          ) : (
                            <TrendingDown className="w-4 h-4 text-red-400" />
                          )}
                          <span className="font-medium text-slate-200">
                            {getIndicatorLabel(cond.type)}
                          </span>
                          <span className="text-slate-400 text-xs">
                            ({(cond.timeframe || '').replace('_', ' ') || 'n/a'})
                          </span>
                          {cond.negated && (
                            <span className="px-1 py-0.5 bg-yellow-600/20 border border-yellow-600/50 rounded text-xs text-yellow-400">
                              NOT
                            </span>
                          )}
                        </div>
                        <div className="flex items-center space-x-3 text-xs">
                          {cond.error || cond.reason ? (
                            <span className="text-yellow-400">{cond.error || cond.reason}</span>
                          ) : (cond.operator === 'increasing' || cond.operator === 'decreasing') && cond.previous_value !== undefined ? (
                            <span className="text-slate-400">
                              {formatValue(cond.previous_value, cond.type)} → {formatValue(cond.actual_value, cond.type)}
                              {' '}{cond.operator === 'increasing' ? '↑' : '↓'}
                              {cond.threshold ? ` (min ${cond.threshold}%)` : ''}
                            </span>
                          ) : (
                            <>
                              <span className="text-slate-400">
                                {formatValue(cond.actual_value, cond.type)} {getOperatorSymbol(cond.operator || '')} {cond.threshold ?? ''}
                              </span>
                              {cond.previous_value !== undefined && (
                                <span className="text-slate-500">
                                  (prev: {formatValue(cond.previous_value, cond.type)})
                                </span>
                              )}
                            </>
                          )}
                          <span className={cond.result ? 'text-green-400' : 'text-red-400'}>
                            {cond.result ? 'PASS' : 'FAIL'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 bg-slate-800/50">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center space-x-4 text-slate-400">
              <span>Total: {logs.length}</span>
              <span className="text-green-400">✓ Matched: {totalMet}</span>
              <span className="text-red-400">✗ Failed: {totalNotMet}</span>
            </div>
            <p className="text-slate-400">
              Refreshes automatically every 10 seconds
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default IndicatorLogs
