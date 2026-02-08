import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { botsApi } from '../services/api'
import { Brain, TrendingUp, TrendingDown, CircleDot, Clock, Target, X, BarChart3, CheckCircle, XCircle } from 'lucide-react'
import { formatDateTime, formatDateTimeCompact } from '../utils/dateFormat'

interface PositionLogsModalProps {
  botId: number
  productId: string
  positionOpenedAt: string
  isOpen: boolean
  onClose: () => void
}

function PositionLogsModal({ botId, productId, positionOpenedAt, isOpen, onClose }: PositionLogsModalProps) {
  const [filterDecision, setFilterDecision] = useState<string>('all')

  const { data: logs = [], isLoading, refetch } = useQuery({
    queryKey: ['position-decision-logs', botId, productId, positionOpenedAt],
    queryFn: async () => {
      // Fetch unified decision logs (AI + Indicator) for this bot/product combination
      // Look back far enough to catch the buy decision that triggered this position
      const openedDate = new Date(positionOpenedAt)
      const lookbackDate = new Date(openedDate.getTime() - 300000) // 5 minutes before to be safe
      const since = lookbackDate.toISOString()

      const allLogs = await botsApi.getDecisionLogs(botId, 1000, 0, productId, since)

      // Only keep full condition matches:
      // - AI logs: always keep (each is a full decision)
      // - Indicator logs: only keep where conditions_met === true
      const matchedLogs = allLogs.filter((log: any) =>
        log.log_type === 'ai' || (log.log_type === 'indicator' && log.conditions_met)
      )

      // Find the most recent "buy" decision near the position opened time
      const positionTime = openedDate.getTime()
      const toleranceMs = 1000 // 1 second tolerance for log timing
      let buyIndex = -1

      for (let i = matchedLogs.length - 1; i >= 0; i--) {
        const logTime = new Date(matchedLogs[i].timestamp).getTime()
        const log = matchedLogs[i]

        // Accept buy signals from 5 minutes before to 1 second after position opened time
        if (logTime <= positionTime + toleranceMs) {
          const isBuySignal =
            (log.log_type === 'ai' && log.decision === 'buy') ||
            (log.log_type === 'indicator' && log.phase === 'base_order' && log.conditions_met)

          if (isBuySignal) {
            buyIndex = i
            break
          }
        }
      }

      // If we found a buy decision, return logs from that point onwards
      // Otherwise return all matched logs (shouldn't happen, but safer)
      return buyIndex >= 0 ? matchedLogs.slice(buyIndex) : matchedLogs
    },
    enabled: isOpen,
    refetchInterval: isOpen ? 10000 : false, // Refresh every 10 seconds when open
  })

  // Auto-refetch when opening
  useEffect(() => {
    if (isOpen) {
      refetch()
    }
  }, [isOpen, refetch])

  // Handle ESC key to close modal
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

  const filteredLogs = logs.filter((log: any) => {
    if (filterDecision === 'all') return true
    if (filterDecision === 'ai') return log.log_type === 'ai'
    if (filterDecision === 'indicator') return log.log_type === 'indicator'
    // Filter by AI decision type
    return log.log_type === 'ai' && log.decision === filterDecision
  })

  const getDecisionIcon = (decision: string) => {
    switch (decision.toLowerCase()) {
      case 'buy':
        return <TrendingUp className="w-5 h-5 text-green-400" />
      case 'sell':
        return <TrendingDown className="w-5 h-5 text-red-400" />
      case 'hold':
        return <CircleDot className="w-5 h-5 text-yellow-400" />
      default:
        return <Brain className="w-5 h-5 text-blue-400" />
    }
  }

  const getDecisionColor = (decision: string) => {
    switch (decision.toLowerCase()) {
      case 'buy':
        return 'bg-green-600/20 border-green-600/50 text-green-400'
      case 'sell':
        return 'bg-red-600/20 border-red-600/50 text-red-400'
      case 'hold':
        return 'bg-yellow-600/20 border-yellow-600/50 text-yellow-400'
      default:
        return 'bg-blue-600/20 border-blue-600/50 text-blue-400'
    }
  }

  const getConfidenceColor = (confidence: number | null) => {
    if (!confidence) return 'text-slate-400'
    if (confidence >= 80) return 'text-green-400'
    if (confidence >= 60) return 'text-yellow-400'
    return 'text-red-400'
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={onClose}>
      <div className="bg-slate-900 rounded-lg w-full max-w-4xl max-h-[90vh] flex flex-col border border-slate-700" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="p-6 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2">
              <Brain className="w-6 h-6 text-purple-400" />
              <BarChart3 className="w-6 h-6 text-blue-400" />
            </div>
            <div>
              <h3 className="text-xl font-bold">Decision History for Position</h3>
              <p className="text-sm text-slate-400">
                {productId} - Since {formatDateTimeCompact(positionOpenedAt)}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Filter */}
        <div className="p-4 border-b border-slate-700 bg-slate-800/50">
          <div className="flex items-center space-x-2">
            <label className="text-sm font-medium text-slate-300">Filter:</label>
            <select
              value={filterDecision}
              onChange={(e) => setFilterDecision(e.target.value)}
              className="bg-slate-700 text-white px-3 py-1.5 rounded border border-slate-600 text-sm"
            >
              <option value="all">All Logs</option>
              <option value="ai">AI Reasoning Only</option>
              <option value="indicator">Indicator Checks Only</option>
              <option value="buy">AI Buy Only</option>
              <option value="sell">AI Sell Only</option>
              <option value="hold">AI Hold Only</option>
            </select>
            <span className="text-sm text-slate-400">
              ({filteredLogs.length} {filteredLogs.length === 1 ? 'entry' : 'entries'})
            </span>
          </div>
        </div>

        {/* Logs List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {isLoading ? (
            <div className="text-center text-slate-400 py-8">Loading decision logs...</div>
          ) : filteredLogs.length === 0 ? (
            <div className="text-center text-slate-400 py-8">
              {filterDecision === 'all'
                ? 'No decision logs for this position yet.'
                : `No "${filterDecision}" logs found for this position.`}
            </div>
          ) : (
            filteredLogs.map((log: any) => (
              <div
                key={`${log.log_type}-${log.id}`}
                className="bg-slate-800 rounded-lg p-4 border border-slate-700 hover:border-slate-600 transition-colors"
              >
                {log.log_type === 'ai' ? (
                  /* AI Log */
                  <>
                    {/* Header Row */}
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center space-x-3">
                        {getDecisionIcon(log.decision)}
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="px-1.5 py-0.5 bg-purple-600/20 border border-purple-600/50 text-purple-300 rounded text-xs font-medium">
                              AI
                            </span>
                            <span className={`px-2 py-1 rounded text-xs font-medium border ${getDecisionColor(log.decision)}`}>
                              {log.decision.toUpperCase()}
                            </span>
                            {log.confidence !== null && (
                              <span className={`text-sm font-medium ${getConfidenceColor(log.confidence)}`}>
                                {log.confidence}% confidence
                              </span>
                            )}
                          </div>
                          <div className="flex items-center space-x-3 mt-1 text-xs text-slate-400">
                            <span className="flex items-center space-x-1">
                              <Clock className="w-3 h-3" />
                              <span>{formatDateTime(log.timestamp)}</span>
                            </span>
                            {log.current_price && (
                              <span className="flex items-center space-x-1">
                                <Target className="w-3 h-3" />
                                <span>{log.current_price.toFixed(8)} BTC</span>
                              </span>
                            )}
                            {log.position_status && (
                              <span className="px-1.5 py-0.5 bg-slate-700 rounded text-xs">
                                Position: {log.position_status}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* AI Thinking */}
                    <div className="bg-slate-900/50 rounded p-3 border border-slate-700">
                      <p className="text-sm font-medium text-purple-300 mb-1">🧠 AI Reasoning:</p>
                      <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">{log.thinking}</p>
                    </div>
                  </>
                ) : (
                  /* Indicator Log */
                  <>
                    {/* Header Row */}
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center space-x-3">
                        <BarChart3 className="w-5 h-5 text-blue-400" />
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="px-1.5 py-0.5 bg-blue-600/20 border border-blue-600/50 text-blue-300 rounded text-xs font-medium">
                              INDICATOR
                            </span>
                            <span className="px-2 py-1 rounded text-xs font-medium border bg-slate-700 border-slate-600 text-slate-300">
                              {log.phase.replace('_', ' ').toUpperCase()}
                            </span>
                            {log.conditions_met ? (
                              <CheckCircle className="w-4 h-4 text-green-400" />
                            ) : (
                              <XCircle className="w-4 h-4 text-red-400" />
                            )}
                            <span className={`text-sm font-medium ${log.conditions_met ? 'text-green-400' : 'text-red-400'}`}>
                              {log.conditions_met ? 'Conditions Met' : 'Conditions Not Met'}
                            </span>
                          </div>
                          <div className="flex items-center space-x-3 mt-1 text-xs text-slate-400">
                            <span className="flex items-center space-x-1">
                              <Clock className="w-3 h-3" />
                              <span>{formatDateTime(log.timestamp)}</span>
                            </span>
                            {log.current_price && (
                              <span className="flex items-center space-x-1">
                                <Target className="w-3 h-3" />
                                <span>{log.current_price.toFixed(8)} BTC</span>
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Indicator Conditions */}
                    <div className="bg-slate-900/50 rounded p-3 border border-slate-700 space-y-2">
                      <p className="text-sm font-medium text-blue-300 mb-2">📊 Indicator Conditions:</p>
                      {log.conditions_detail && log.conditions_detail.map((condition: any, idx: number) => (
                        <div key={idx} className="flex items-start space-x-2 text-xs">
                          {condition.result ? (
                            <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0 mt-0.5" />
                          ) : (
                            <XCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                          )}
                          <div className="flex-1">
                            <span className="text-slate-300 font-medium">
                              {condition.type.toUpperCase()} ({condition.timeframe})
                            </span>
                            <span className="text-slate-400">
                              {' '}{condition.operator.replace('_', ' ')} {condition.threshold}
                            </span>
                            <span className={condition.result ? 'text-green-400' : 'text-red-400'}>
                              {' '}→ {typeof condition.actual_value === 'number' ? condition.actual_value.toFixed(2) : condition.actual_value}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Indicator Snapshot (collapsible) */}
                    {log.indicators_snapshot && Object.keys(log.indicators_snapshot).length > 0 && (
                      <details className="mt-3">
                        <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-300">
                          View all indicator values ({Object.keys(log.indicators_snapshot).length} indicators)
                        </summary>
                        <div className="mt-2 bg-slate-900/50 rounded p-3 border border-slate-700 text-xs space-y-1 max-h-40 overflow-y-auto">
                          {Object.entries(log.indicators_snapshot).map(([key, value]: [string, any]) => (
                            <div key={key} className="flex justify-between">
                              <span className="text-slate-400">{key}:</span>
                              <span className="text-slate-300 font-mono">
                                {typeof value === 'number' ? value.toFixed(4) : String(value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 bg-slate-800/50">
          <p className="text-xs text-slate-400 text-center">
            Decision logs (AI + Indicators) refresh automatically every 10 seconds
          </p>
        </div>
      </div>
    </div>
  )
}

export default PositionLogsModal
