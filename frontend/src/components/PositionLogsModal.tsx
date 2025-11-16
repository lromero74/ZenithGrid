import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { botsApi } from '../services/api'
import { Brain, TrendingUp, TrendingDown, CircleDot, Clock, Target, X } from 'lucide-react'
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
    queryKey: ['position-logs', botId, productId, positionOpenedAt],
    queryFn: () => botsApi.getLogs(botId, 200, 0, productId, positionOpenedAt),
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
    return log.decision === filterDecision
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
            <Brain className="w-6 h-6 text-purple-400" />
            <div>
              <h3 className="text-xl font-bold">AI Reasoning for Position</h3>
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
                ? 'No AI reasoning logs for this position yet.'
                : `No "${filterDecision}" decisions logged for this position.`}
            </div>
          ) : (
            filteredLogs.map((log: any) => (
              <div
                key={log.id}
                className="bg-slate-800 rounded-lg p-4 border border-slate-700 hover:border-slate-600 transition-colors"
              >
                {/* Header Row */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center space-x-3">
                    {getDecisionIcon(log.decision)}
                    <div>
                      <div className="flex items-center space-x-2">
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
              </div>
            ))
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

export default PositionLogsModal
