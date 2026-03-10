/**
 * Session Gate — checks for other active sessions before entering multiplayer.
 *
 * If no other sessions exist, auto-proceeds. Otherwise shows a dialog
 * listing active sessions with an option to terminate them all.
 */

import { useEffect, useRef } from 'react'
import { Loader2, AlertTriangle, Monitor } from 'lucide-react'
import { useOtherSessions, useTerminateAllOtherSessions } from '../../hooks/useSessions'
import type { SessionInfo } from '../../hooks/useSessions'

interface SessionGateProps {
  onProceed: () => void
  onCancel: () => void
}

/** Parse a user agent string into a readable device description. */
function parseUserAgent(ua: string): string {
  let browser = 'Unknown Browser'
  let os = 'Unknown OS'

  // Detect OS
  if (/iPhone/.test(ua)) os = 'iPhone'
  else if (/iPad/.test(ua)) os = 'iPad'
  else if (/Android/.test(ua)) os = 'Android'
  else if (/Mac OS X/.test(ua)) os = 'macOS'
  else if (/Windows/.test(ua)) os = 'Windows'
  else if (/Linux/.test(ua)) os = 'Linux'
  else if (/CrOS/.test(ua)) os = 'ChromeOS'

  // Detect browser (order matters — Chrome UA contains "Safari")
  if (/Edg\//.test(ua)) browser = 'Edge'
  else if (/OPR\//.test(ua)) browser = 'Opera'
  else if (/Chrome\//.test(ua) && !/Chromium/.test(ua)) browser = 'Chrome'
  else if (/Safari\//.test(ua) && !/Chrome/.test(ua)) browser = 'Safari'
  else if (/Firefox\//.test(ua)) browser = 'Firefox'

  return `${browser} on ${os}`
}

/** Format a date string into a relative time description. */
function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function SessionGate({ onProceed, onCancel }: SessionGateProps) {
  const { data: sessions, isLoading, isError } = useOtherSessions()
  const terminateAll = useTerminateAllOtherSessions()
  const proceeded = useRef(false)

  // Auto-proceed when no other sessions exist
  useEffect(() => {
    if (!isLoading && !isError && sessions && sessions.length === 0 && !proceeded.current) {
      proceeded.current = true
      onProceed()
    }
  }, [isLoading, isError, sessions, onProceed])

  // Auto-proceed after successful termination
  useEffect(() => {
    if (terminateAll.isSuccess && !proceeded.current) {
      proceeded.current = true
      onProceed()
    }
  }, [terminateAll.isSuccess, onProceed])

  // Loading state
  if (isLoading) {
    return (
      <div className="flex flex-col items-center gap-4 py-16">
        <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
        <p className="text-slate-400 text-sm">Checking for other sessions...</p>
      </div>
    )
  }

  // Error state
  if (isError) {
    return (
      <div className="flex flex-col items-center gap-4 py-16">
        <AlertTriangle className="w-8 h-8 text-red-400" />
        <p className="text-slate-400 text-sm">Failed to check sessions.</p>
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm text-slate-300 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
        >
          Go Back
        </button>
      </div>
    )
  }

  // No sessions (will auto-proceed via effect, but render nothing while transitioning)
  if (!sessions || sessions.length === 0) {
    return null
  }

  // Other sessions found — show dialog
  return (
    <div className="flex flex-col items-center py-12">
      <div className="w-full max-w-lg bg-slate-800 border border-slate-600 rounded-xl p-6">
        <div className="flex items-center gap-3 mb-2">
          <AlertTriangle className="w-6 h-6 text-amber-400 shrink-0" />
          <h3 className="text-lg font-bold text-white">Other Active Sessions Detected</h3>
        </div>
        <p className="text-sm text-slate-400 mb-5">
          Multiplayer requires a single active session. You have {sessions.length} other session{sessions.length !== 1 ? 's' : ''} that must be terminated first.
        </p>

        {/* Session list */}
        <div className="space-y-2 mb-6">
          {sessions.map((s: SessionInfo) => (
            <div
              key={s.session_id}
              className="flex items-center gap-3 px-3 py-2.5 bg-slate-700/50 rounded-lg"
            >
              <Monitor className="w-4 h-4 text-slate-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-200 truncate">
                  {s.user_agent ? parseUserAgent(s.user_agent) : 'Unknown device'}
                </p>
                <p className="text-xs text-slate-500">
                  {s.ip_address ?? 'Unknown IP'}
                  {s.created_at ? ` · ${relativeTime(s.created_at)}` : ''}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={terminateAll.isPending}
            className="px-4 py-2 text-sm text-slate-300 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => terminateAll.mutate()}
            disabled={terminateAll.isPending}
            className="px-4 py-2 text-sm text-white bg-green-600 hover:bg-green-500 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {terminateAll.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            Terminate All & Continue
          </button>
        </div>

        {terminateAll.isError && (
          <p className="text-xs text-red-400 mt-3 text-right">
            Failed to terminate sessions. Please try again.
          </p>
        )}
      </div>
    </div>
  )
}
