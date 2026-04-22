import { useState } from 'react'
import { AlertCircle, Monitor, X as XIcon, RefreshCw } from 'lucide-react'
import { useOtherSessions, useTerminateSessions, useTerminateAllOtherSessions, SessionInfo } from '../../hooks/useSessions'
import { parseDevice, timeAgo } from './SettingsHelpers'

export function ActiveSessions() {
  const { data: sessions, isLoading, error } = useOtherSessions()
  const terminateMutation = useTerminateSessions()
  const terminateAllMutation = useTerminateAllOtherSessions()
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const toggleSelect = (sessionId: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(sessionId)) {
        next.delete(sessionId)
      } else {
        next.add(sessionId)
      }
      return next
    })
  }

  const toggleSelectAll = () => {
    if (!sessions) return
    if (selected.size === sessions.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(sessions.map(s => s.session_id)))
    }
  }

  const handleTerminateSelected = () => {
    terminateMutation.mutate(Array.from(selected), {
      onSuccess: () => setSelected(new Set()),
    })
  }

  const handleTerminateAll = () => {
    terminateAllMutation.mutate(undefined, {
      onSuccess: () => setSelected(new Set()),
    })
  }

  return (
    <div className="card p-6">
      <div className="flex items-center space-x-3 mb-2">
        <Monitor className="w-6 h-6 text-cyan-400" />
        <h3 className="text-xl font-semibold">Active Sessions</h3>
      </div>
      <p className="text-sm text-slate-400 mb-6">
        Manage your login sessions across devices
      </p>

      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-5 h-5 text-slate-400 animate-spin" />
          <span className="ml-2 text-slate-400">Loading sessions...</span>
        </div>
      )}

      {error && (
        <div className="flex items-start space-x-2 p-3 bg-red-900/20 border border-red-700 rounded-lg">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-300">Failed to load sessions</p>
        </div>
      )}

      {!isLoading && !error && sessions && sessions.length === 0 && (
        <div className="text-center py-8">
          <Monitor className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">No other active sessions</p>
          <p className="text-xs text-slate-500 mt-1">Your current session is not shown</p>
        </div>
      )}

      {!isLoading && !error && sessions && sessions.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="pb-2 pr-3 text-left w-8">
                    <input
                      type="checkbox"
                      checked={selected.size === sessions.length}
                      onChange={toggleSelectAll}
                      className="rounded border-slate-600 bg-slate-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
                    />
                  </th>
                  <th className="pb-2 pr-3 text-left text-slate-400 font-medium">Device</th>
                  <th className="pb-2 pr-3 text-left text-slate-400 font-medium">IP Address</th>
                  <th className="pb-2 pr-3 text-left text-slate-400 font-medium">Started</th>
                  <th className="pb-2 text-right text-slate-400 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {sessions.map((session: SessionInfo) => (
                  <tr key={session.session_id} className="hover:bg-slate-700/30 transition-colors">
                    <td className="py-3 pr-3">
                      <input
                        type="checkbox"
                        checked={selected.has(session.session_id)}
                        onChange={() => toggleSelect(session.session_id)}
                        className="rounded border-slate-600 bg-slate-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
                      />
                    </td>
                    <td className="py-3 pr-3 text-white">
                      {parseDevice(session.user_agent)}
                    </td>
                    <td className="py-3 pr-3 text-slate-400 font-mono text-xs">
                      {session.ip_address || 'Unknown'}
                    </td>
                    <td className="py-3 pr-3 text-slate-400">
                      {timeAgo(session.created_at)}
                    </td>
                    <td className="py-3 text-right">
                      <button
                        onClick={() => terminateMutation.mutate([session.session_id], {
                          onSuccess: () => {
                            setSelected(prev => {
                              const next = new Set(prev)
                              next.delete(session.session_id)
                              return next
                            })
                          },
                        })}
                        disabled={terminateMutation.isPending}
                        className="p-1.5 text-slate-400 hover:text-red-400 transition-colors disabled:opacity-50"
                        title="Terminate session"
                      >
                        <XIcon className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-slate-500 mt-3">Your current session is not shown</p>

          <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-700">
            <div>
              {selected.size > 0 && (
                <button
                  onClick={handleTerminateSelected}
                  disabled={terminateMutation.isPending}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
                >
                  {terminateMutation.isPending ? 'Terminating...' : `Terminate Selected (${selected.size})`}
                </button>
              )}
            </div>
            <button
              onClick={handleTerminateAll}
              disabled={terminateAllMutation.isPending}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-600 disabled:cursor-not-allowed text-red-400 text-sm font-medium rounded-lg border border-slate-600 transition-colors"
            >
              {terminateAllMutation.isPending ? 'Terminating...' : 'Terminate All Others'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
