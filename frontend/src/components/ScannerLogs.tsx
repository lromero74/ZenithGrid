import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { botsApi } from '../services/api'
import { ScanLine, TrendingUp, TrendingDown, Clock, Target, Activity, AlertTriangle, CheckCircle, XCircle, Pause } from 'lucide-react'
import { formatDateTime } from '../utils/dateFormat'

interface ScannerLogsProps {
  botId: number
  isOpen: boolean
  onClose: () => void
}

function ScannerLogs({ botId, isOpen, onClose }: ScannerLogsProps) {
  const [filterScanType, setFilterScanType] = useState<string>('all')
  const [filterDecision, setFilterDecision] = useState<string>('all')

  const { data: logs = [], isLoading, refetch } = useQuery({
    queryKey: ['scanner-logs', botId],
    queryFn: () => botsApi.getScannerLogs(botId, 100, 0),
    enabled: isOpen,
    refetchInterval: isOpen ? 15000 : false, // Refresh every 15 seconds when open
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
    const matchesScanType = filterScanType === 'all' || log.scan_type === filterScanType
    const matchesDecision = filterDecision === 'all' || log.decision === filterDecision
    return matchesScanType && matchesDecision
  })

  const getScanTypeIcon = (scanType: string) => {
    switch (scanType) {
      case 'volume_check':
        return <Activity className="w-5 h-5 text-blue-400" />
      case 'pattern_check':
        return <ScanLine className="w-5 h-5 text-purple-400" />
      case 'entry_signal':
        return <TrendingUp className="w-5 h-5 text-green-400" />
      case 'exit_signal':
        return <TrendingDown className="w-5 h-5 text-orange-400" />
      case 'error':
        return <AlertTriangle className="w-5 h-5 text-red-400" />
      default:
        return <ScanLine className="w-5 h-5 text-slate-400" />
    }
  }

  const getScanTypeLabel = (scanType: string) => {
    switch (scanType) {
      case 'volume_check': return 'Volume Check'
      case 'pattern_check': return 'Pattern Check'
      case 'entry_signal': return 'Entry Signal'
      case 'exit_signal': return 'Exit Signal'
      case 'error': return 'Error'
      default: return scanType
    }
  }

  const getDecisionIcon = (decision: string) => {
    switch (decision.toLowerCase()) {
      case 'passed':
        return <CheckCircle className="w-4 h-4 text-green-400" />
      case 'triggered':
        return <TrendingUp className="w-4 h-4 text-green-400" />
      case 'rejected':
        return <XCircle className="w-4 h-4 text-red-400" />
      case 'hold':
        return <Pause className="w-4 h-4 text-yellow-400" />
      default:
        return <Activity className="w-4 h-4 text-slate-400" />
    }
  }

  const getDecisionColor = (decision: string) => {
    switch (decision.toLowerCase()) {
      case 'passed':
        return 'bg-green-600/20 border-green-600/50 text-green-400'
      case 'triggered':
        return 'bg-emerald-600/20 border-emerald-600/50 text-emerald-400'
      case 'rejected':
        return 'bg-red-600/20 border-red-600/50 text-red-400'
      case 'hold':
        return 'bg-yellow-600/20 border-yellow-600/50 text-yellow-400'
      default:
        return 'bg-slate-600/20 border-slate-600/50 text-slate-400'
    }
  }

  const getScanTypeColor = (scanType: string) => {
    switch (scanType) {
      case 'volume_check':
        return 'bg-blue-600/20 border-blue-600/50 text-blue-300'
      case 'pattern_check':
        return 'bg-purple-600/20 border-purple-600/50 text-purple-300'
      case 'entry_signal':
        return 'bg-green-600/20 border-green-600/50 text-green-300'
      case 'exit_signal':
        return 'bg-orange-600/20 border-orange-600/50 text-orange-300'
      case 'error':
        return 'bg-red-600/20 border-red-600/50 text-red-300'
      default:
        return 'bg-slate-600/20 border-slate-600/50 text-slate-300'
    }
  }

  const getVolumeRatioColor = (ratio: number | null) => {
    if (!ratio) return 'text-slate-400'
    if (ratio >= 5) return 'text-green-400'
    if (ratio >= 3) return 'text-yellow-400'
    return 'text-slate-400'
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-900 rounded-lg w-full max-w-5xl max-h-[90vh] flex flex-col border border-slate-700">
        {/* Header */}
        <div className="p-6 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <ScanLine className="w-6 h-6 text-blue-400" />
            <div>
              <h3 className="text-xl font-bold">Scanner / Monitor Log</h3>
              <p className="text-sm text-slate-400">Bot #{botId} - Scan Decision History</p>
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
          <div className="flex items-center space-x-4 flex-wrap gap-2">
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-slate-300">Scan Type:</label>
              <select
                value={filterScanType}
                onChange={(e) => setFilterScanType(e.target.value)}
                className="bg-slate-700 text-white px-3 py-1.5 rounded border border-slate-600 text-sm"
              >
                <option value="all">All Types</option>
                <option value="volume_check">Volume Check</option>
                <option value="pattern_check">Pattern Check</option>
                <option value="entry_signal">Entry Signal</option>
                <option value="exit_signal">Exit Signal</option>
                <option value="error">Errors</option>
              </select>
            </div>
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-slate-300">Decision:</label>
              <select
                value={filterDecision}
                onChange={(e) => setFilterDecision(e.target.value)}
                className="bg-slate-700 text-white px-3 py-1.5 rounded border border-slate-600 text-sm"
              >
                <option value="all">All Decisions</option>
                <option value="passed">Passed</option>
                <option value="triggered">Triggered</option>
                <option value="rejected">Rejected</option>
                <option value="hold">Hold</option>
              </select>
            </div>
            <span className="text-sm text-slate-400">
              ({filteredLogs.length} {filteredLogs.length === 1 ? 'entry' : 'entries'})
            </span>
          </div>
        </div>

        {/* Logs List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {isLoading ? (
            <div className="text-center text-slate-400 py-8">Loading scanner logs...</div>
          ) : filteredLogs.length === 0 ? (
            <div className="text-center text-slate-400 py-8">
              {filterScanType === 'all' && filterDecision === 'all'
                ? 'No scanner logs yet. The scanner will log its decisions as it analyzes coins.'
                : 'No matching logs found for the selected filters.'}
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
                    {getScanTypeIcon(log.scan_type)}
                    <div>
                      <div className="flex items-center space-x-2 flex-wrap gap-1">
                        <span className={`px-2 py-1 rounded text-xs font-medium border ${getScanTypeColor(log.scan_type)}`}>
                          {getScanTypeLabel(log.scan_type)}
                        </span>
                        <span className={`px-2 py-1 rounded text-xs font-medium border ${getDecisionColor(log.decision)} flex items-center space-x-1`}>
                          {getDecisionIcon(log.decision)}
                          <span>{log.decision.toUpperCase()}</span>
                        </span>
                      </div>
                      <div className="flex items-center space-x-3 mt-1 text-xs text-slate-400 flex-wrap gap-1">
                        <span className="flex items-center space-x-1">
                          <Clock className="w-3 h-3" />
                          <span>{formatDateTime(log.timestamp)}</span>
                        </span>
                        {log.product_id && (
                          <span className="px-1.5 py-0.5 bg-cyan-600/20 border border-cyan-600/50 rounded text-xs font-medium text-cyan-300">
                            {log.product_id}
                          </span>
                        )}
                        {log.current_price && (
                          <span className="flex items-center space-x-1">
                            <Target className="w-3 h-3" />
                            <span>${log.current_price.toFixed(4)}</span>
                          </span>
                        )}
                        {log.volume_ratio !== null && log.volume_ratio !== undefined && (
                          <span className={`flex items-center space-x-1 ${getVolumeRatioColor(log.volume_ratio)}`}>
                            <Activity className="w-3 h-3" />
                            <span>{log.volume_ratio.toFixed(2)}x volume</span>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Reason */}
                <div className="bg-slate-900/50 rounded p-3 border border-slate-700">
                  <p className="text-sm text-slate-300 leading-relaxed">{log.reason}</p>
                </div>

                {/* Pattern Data (if present) */}
                {log.pattern_data && (
                  <div className="mt-3 bg-emerald-900/20 rounded p-3 border border-emerald-700/50">
                    <p className="text-sm font-medium text-emerald-300 mb-2">Pattern Details:</p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                      <div>
                        <span className="text-slate-400">Entry:</span>
                        <span className="ml-1 text-white">${log.pattern_data.entry_price?.toFixed(4)}</span>
                      </div>
                      <div>
                        <span className="text-slate-400">Stop Loss:</span>
                        <span className="ml-1 text-red-400">${log.pattern_data.stop_loss?.toFixed(4)}</span>
                      </div>
                      <div>
                        <span className="text-slate-400">Take Profit:</span>
                        <span className="ml-1 text-green-400">${log.pattern_data.take_profit_target?.toFixed(4)}</span>
                      </div>
                      <div>
                        <span className="text-slate-400">R:R Ratio:</span>
                        <span className="ml-1 text-yellow-400">{log.pattern_data.risk_reward_ratio?.toFixed(1)}x</span>
                      </div>
                      <div>
                        <span className="text-slate-400">Pole Gain:</span>
                        <span className="ml-1 text-blue-400">{log.pattern_data.pole_gain_pct?.toFixed(1)}%</span>
                      </div>
                      <div>
                        <span className="text-slate-400">Retracement:</span>
                        <span className="ml-1 text-purple-400">{log.pattern_data.retracement_pct?.toFixed(1)}%</span>
                      </div>
                      <div>
                        <span className="text-slate-400">Volume Ratio:</span>
                        <span className="ml-1 text-cyan-400">{log.pattern_data.volume_ratio?.toFixed(2)}x</span>
                      </div>
                      <div>
                        <span className="text-slate-400">Pullback Candles:</span>
                        <span className="ml-1 text-orange-400">{log.pattern_data.pullback_candles}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 bg-slate-800/50">
          <p className="text-xs text-slate-400 text-center">
            Scanner logs refresh automatically every 15 seconds
          </p>
        </div>
      </div>
    </div>
  )
}

export default ScannerLogs
