import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { botsApi } from '../services/api'
import { Brain, TrendingUp, TrendingDown, Clock, Target, CircleDot } from 'lucide-react'
import { formatDateTime } from '../utils/dateFormat'

interface AIBotLogsProps {
  botId: number
  isOpen: boolean
  onClose: () => void
}

function AIBotLogs({ botId, isOpen, onClose }: AIBotLogsProps) {
  const [filterDecision, setFilterDecision] = useState<string>('all')

  const { data: logs = [], isLoading, refetch } = useQuery({
    queryKey: ['bot-decision-logs', botId],
    queryFn: () => botsApi.getDecisionLogs(botId, 100, 0),
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
    // For AI logs, filter by decision
    if (log.log_type === 'ai') {
      return log.decision === filterDecision
    }
    // For indicator logs, check phase and conditions_met
    if (log.log_type === 'indicator') {
      if (filterDecision === 'buy' && (log.phase === 'base_order' || log.phase === 'safety_order') && log.conditions_met) {
        return true
      }
      if (filterDecision === 'sell' && log.phase === 'take_profit' && log.conditions_met) {
        return true
      }
      if (filterDecision === 'hold' && !log.conditions_met) {
        return true
      }
    }
    return false
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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-900 rounded-lg w-full max-w-4xl max-h-[90vh] flex flex-col border border-slate-700">
        {/* Header */}
        <div className="p-6 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Brain className="w-6 h-6 text-purple-400" />
            <div>
              <h3 className="text-xl font-bold">AI Bot Reasoning Log</h3>
              <p className="text-sm text-slate-400">Bot #{botId} - Decision History</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            ✕
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
              <option value="all">All Decisions</option>
              <option value="buy">Buy Only</option>
              <option value="sell">Sell Only</option>
              <option value="hold">Hold Only</option>
            </select>
            <span className="text-sm text-slate-400">
              ({filteredLogs.length} {filteredLogs.length === 1 ? 'entry' : 'entries'})
            </span>
          </div>
        </div>

        {/* Logs List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {isLoading ? (
            <div className="text-center text-slate-400 py-8">Loading AI logs...</div>
          ) : filteredLogs.length === 0 ? (
            <div className="text-center text-slate-400 py-8">
              {filterDecision === 'all'
                ? 'No AI reasoning logs yet. The AI will log its thinking as it makes decisions.'
                : `No "${filterDecision}" decisions logged yet.`}
            </div>
          ) : (
            filteredLogs.map((log: any) => {
              // Determine display values based on log type
              const isAILog = log.log_type === 'ai'
              const isIndicatorLog = log.log_type === 'indicator'

              let decision = 'hold'
              if (isAILog) {
                decision = log.decision
              } else if (isIndicatorLog) {
                if (log.phase === 'base_order' || log.phase === 'safety_order') {
                  decision = log.conditions_met ? 'buy' : 'hold'
                } else if (log.phase === 'take_profit') {
                  decision = log.conditions_met ? 'sell' : 'hold'
                }
              }

              return (
                <div
                  key={`${log.log_type}-${log.id}`}
                  className="bg-slate-800 rounded-lg p-4 border border-slate-700 hover:border-slate-600 transition-colors"
                >
                  {/* Header Row */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center space-x-3">
                      {getDecisionIcon(decision)}
                      <div>
                        <div className="flex items-center space-x-2">
                          {isIndicatorLog && (
                            <span className="px-2 py-1 rounded text-xs font-medium bg-cyan-600/20 border border-cyan-600/50 text-cyan-300">
                              {log.phase.replace('_', ' ').toUpperCase()}
                            </span>
                          )}
                          <span className={`px-2 py-1 rounded text-xs font-medium border ${getDecisionColor(decision)}`}>
                            {decision.toUpperCase()}
                          </span>
                          {log.confidence !== null && log.confidence !== undefined && (
                            <span className={`text-sm font-medium ${getConfidenceColor(log.confidence)}`}>
                              {log.confidence}% confidence
                            </span>
                          )}
                          {isIndicatorLog && (
                            <span className={`text-xs px-1.5 py-0.5 rounded ${log.conditions_met ? 'bg-green-600/20 text-green-400' : 'bg-slate-700 text-slate-400'}`}>
                              {log.conditions_met ? '✓ Conditions Met' : '✗ Not Met'}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center space-x-3 mt-1 text-xs text-slate-400">
                          <span className="flex items-center space-x-1">
                            <Clock className="w-3 h-3" />
                            <span>{formatDateTime(log.timestamp)}</span>
                          </span>
                          {log.product_id && (
                            <span className="px-1.5 py-0.5 bg-purple-600/20 border border-purple-600/50 rounded text-xs font-medium text-purple-300">
                              {log.product_id}
                            </span>
                          )}
                          {log.current_price && (
                            <span className="flex items-center space-x-1">
                              <Target className="w-3 h-3" />
                              <span>{(() => {
                                const quoteCurrency = log.product_id?.split('-')[1] || 'BTC';
                                if (quoteCurrency === 'USD') {
                                  return `${log.current_price.toFixed(2)} USD`;
                                }
                                return `${log.current_price.toFixed(8)} BTC`;
                              })()}</span>
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

                  {/* Log Content */}
                  {isAILog && log.thinking && (
                    <div className="bg-slate-900/50 rounded p-3 border border-slate-700">
                      <p className="text-sm font-medium text-purple-300 mb-1">🧠 AI Reasoning:</p>
                      <p className="text-sm text-slate-300 leading-relaxed">{log.thinking}</p>
                    </div>
                  )}

                  {isIndicatorLog && log.conditions_detail && (
                    <div className="bg-slate-900/50 rounded p-3 border border-slate-700">
                      <p className="text-sm font-medium text-cyan-300 mb-2">📊 Indicator Conditions:</p>
                      <div className="space-y-1">
                        {log.conditions_detail.map((cond: any, idx: number) => {
                          // Handle both old format (met/value/actual) and new format (result/threshold/actual_value)
                          const conditionMet = cond.result !== undefined ? cond.result : cond.met
                          const thresholdValue = cond.threshold !== undefined ? cond.threshold : cond.value
                          const actualValue = cond.actual_value !== undefined ? cond.actual_value : cond.actual

                          return (
                            <div key={idx} className="text-xs text-slate-300 flex items-center space-x-2">
                              <span className={conditionMet ? 'text-green-400' : 'text-red-400'}>
                                {conditionMet ? '✓' : '✗'}
                              </span>
                              <span className="font-mono">{cond.indicator || cond.type}</span>
                              {cond.timeframe && cond.timeframe !== 'required' && (
                                <span className="text-slate-600 text-[10px]">[{cond.timeframe}]</span>
                              )}
                              <span className="text-slate-500">{cond.operator}</span>
                              <span className="text-slate-400">
                                {thresholdValue !== undefined && thresholdValue !== null
                                  ? (typeof thresholdValue === 'number' ? thresholdValue.toFixed(8) : thresholdValue)
                                  : 'N/A'}
                              </span>
                              <span className="text-slate-500">→</span>
                              <span className={conditionMet ? 'text-green-400' : 'text-slate-400'}>
                                {actualValue !== undefined && actualValue !== null
                                  ? (typeof actualValue === 'number' ? actualValue.toFixed(8) : actualValue)
                                  : 'N/A'}
                              </span>
                              {cond.ai_reasoning && (
                                <span className="text-purple-300 ml-2">({cond.ai_reasoning})</span>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 bg-slate-800/50">
          <p className="text-xs text-slate-400 text-center">
            AI reasoning logs refresh automatically every 10 seconds
          </p>
        </div>
      </div>
    </div>
  )
}

export default AIBotLogs
