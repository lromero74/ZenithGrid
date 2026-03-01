import { Clock } from 'lucide-react'
import type { SessionPolicy } from '../contexts/AuthContext'

interface SessionLimitsNoticeProps {
  policy: SessionPolicy
  onAcknowledge: () => void
}

export function SessionLimitsNotice({
  policy,
  onAcknowledge,
}: SessionLimitsNoticeProps) {
  return (
    <div className="fixed inset-0 bg-slate-900 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-2xl p-8 max-w-md w-full border border-slate-700 shadow-xl">
        <div className="flex items-center gap-3 mb-6">
          <Clock className="w-8 h-8 text-amber-400" />
          <h2 className="text-2xl font-bold text-white">
            Session Limits Active
          </h2>
        </div>

        <div className="space-y-3 mb-8">
          {policy.session_timeout_minutes && (
            <p className="text-slate-300">
              Your session will expire in{' '}
              {policy.session_timeout_minutes} minutes
            </p>
          )}
          {policy.auto_logout && (
            <p className="text-slate-300">
              You will be automatically logged out at expiry
            </p>
          )}
          {policy.max_simultaneous_sessions && (
            <p className="text-slate-300">
              Maximum {policy.max_simultaneous_sessions}{' '}
              simultaneous sessions
            </p>
          )}
          {policy.max_sessions_per_ip && (
            <p className="text-slate-300">
              Maximum {policy.max_sessions_per_ip}{' '}
              sessions from this IP
            </p>
          )}
          {policy.relogin_cooldown_minutes && (
            <p className="text-slate-300">
              {policy.relogin_cooldown_minutes}-minute cooldown
              before re-login after session ends
            </p>
          )}
        </div>

        <button
          onClick={onAcknowledge}
          className="w-full py-3 bg-amber-600 hover:bg-amber-700 text-white font-semibold rounded-lg transition-colors"
        >
          I Understand
        </button>
      </div>
    </div>
  )
}
