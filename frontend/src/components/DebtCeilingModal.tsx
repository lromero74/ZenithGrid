/**
 * Debt Ceiling History Modal
 *
 * S13 fix: Added Escape key handler to close modal.
 */

import { useEffect } from 'react'
import { DollarSign, X, ExternalLink } from 'lucide-react'
import { LoadingSpinner } from './LoadingSpinner'
import type { DebtCeilingHistoryResponse } from '../types'

interface DebtCeilingModalProps {
  debtCeilingHistory: DebtCeilingHistoryResponse | undefined
  onClose: () => void
}

export function DebtCeilingModal({ debtCeilingHistory, onClose }: DebtCeilingModalProps) {
  // S13: Handle Escape key to close modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-slate-800 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-hidden shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center space-x-2">
            <DollarSign className="w-5 h-5 text-green-400" />
            <div>
              <h3 className="font-medium text-white">US Debt Ceiling History</h3>
              {debtCeilingHistory && (
                <p className="text-xs text-slate-500">{debtCeilingHistory.total_events} events from 1939 to present</p>
              )}
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center transition-colors">
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <div className="p-4 overflow-y-auto max-h-[calc(90vh-140px)]">
          {debtCeilingHistory ? (
            <div className="space-y-3">
              <p className="text-sm text-slate-400 mb-4">
                Complete history of US debt ceiling changes since the first statutory limit was established in 1939.
              </p>
              {debtCeilingHistory.events.map((event, idx) => (
                <div key={idx} className="bg-slate-900/50 rounded-lg p-3 border border-slate-700">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-medium text-slate-300">
                      {new Date(event.date).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
                    </span>
                    {event.suspended ? (
                      <span className="px-2 py-0.5 bg-yellow-500/20 text-yellow-400 text-xs rounded border border-yellow-500/30">SUSPENDED</span>
                    ) : (
                      <span className="text-lg font-mono font-bold text-green-400">
                        {event.amount_trillion && event.amount_trillion >= 1 ? `$${event.amount_trillion}T` : `$${((event.amount_trillion || 0) * 1000).toFixed(0)}B`}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-400">{event.note}</p>
                  {event.legislation && <p className="text-xs text-slate-500 mt-1 italic">{event.legislation}</p>}
                  {event.suspended && event.suspension_end && (
                    <p className="text-xs text-yellow-500/70 mt-1">
                      Suspension ended: {new Date(event.suspension_end).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    </p>
                  )}
                  {event.political_context && (
                    <p className="text-xs text-slate-400 mt-2 border-t border-slate-700 pt-2">{event.political_context}</p>
                  )}
                  {event.source_url && (
                    <a href={event.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 mt-2 transition-colors">
                      <ExternalLink className="w-3 h-3" />
                      View on Congress.gov
                    </a>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center py-8">
              <LoadingSpinner size="sm" text="Loading..." />
            </div>
          )}
        </div>

        <div className="p-4 border-t border-slate-700">
          <button onClick={onClose} className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition-colors">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
