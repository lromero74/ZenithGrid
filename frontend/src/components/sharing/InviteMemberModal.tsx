/**
 * InviteMemberModal
 *
 * Modal for inviting a user to co-manage or observe an exchange account.
 * Sends a one-time, 7-day expiring invitation email to the specified address.
 * The invitee must authenticate as that email before they can accept.
 */

import { useState } from 'react'
import { X, Mail, UserCheck, Eye } from 'lucide-react'
import { authFetch } from '../../services/api'

interface InviteMemberModalProps {
  accountId: number
  accountName: string
  onClose: () => void
  onSuccess: () => void
}

const ROLE_OPTIONS = [
  {
    value: 'manager',
    label: 'Manager',
    icon: UserCheck,
    description: 'Can create/stop bots, view positions, and run reports. Cannot edit credentials or delete the account.',
    color: 'blue',
  },
  {
    value: 'observer',
    label: 'Observer',
    icon: Eye,
    description: 'Read-only access — view balances, bots, positions, and reports. Cannot execute any trades or changes.',
    color: 'slate',
  },
] as const

export function InviteMemberModal({ accountId, accountName, onClose, onSuccess }: InviteMemberModalProps) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'manager' | 'observer'>('observer')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return

    setIsSubmitting(true)
    setError(null)

    try {
      const response = await authFetch(`/api/accounts/${accountId}/sharing/invite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), role }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to send invitation')
      }

      onSuccess()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send invitation')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-xl border border-slate-700 w-full max-w-md shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-700">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Invite to Account</h2>
            <p className="text-sm text-slate-400 mt-0.5">{accountName}</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-5">
          {/* Email input */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Email Address
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="colleague@example.com"
                required
                className="w-full pl-10 pr-4 py-2.5 bg-slate-900 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
              />
            </div>
            <p className="text-xs text-slate-500 mt-1">
              They must have a platform account with this email to accept.
            </p>
          </div>

          {/* Role picker */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Access Level
            </label>
            <div className="space-y-2">
              {ROLE_OPTIONS.map((option) => {
                const Icon = option.icon
                const isSelected = role === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setRole(option.value)}
                    className={`w-full text-left p-3 rounded-lg border transition-all ${
                      isSelected
                        ? 'border-blue-500 bg-blue-500/10'
                        : 'border-slate-600 bg-slate-900/50 hover:border-slate-500'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className={`mt-0.5 p-1.5 rounded-md ${isSelected ? 'bg-blue-500/20' : 'bg-slate-700'}`}>
                        <Icon className={`w-4 h-4 ${isSelected ? 'text-blue-400' : 'text-slate-400'}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`text-sm font-medium ${isSelected ? 'text-blue-300' : 'text-slate-200'}`}>
                            {option.label}
                          </span>
                          {isSelected && (
                            <span className="text-[10px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded font-medium">
                              SELECTED
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">
                          {option.description}
                        </p>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {error && (
            <div className="p-3 bg-red-900/30 border border-red-700/50 rounded-lg text-sm text-red-300">
              {error}
            </div>
          )}

          <div className="bg-slate-900/50 rounded-lg p-3 text-xs text-slate-400 border border-slate-700">
            The invitation link expires in <span className="text-slate-300 font-medium">7 days</span> and
            can only be used once. The recipient must log in as this email address to accept.
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2.5 text-sm font-medium text-slate-300 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !email.trim()}
              className="flex-1 px-4 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
            >
              {isSubmitting ? 'Sending...' : 'Send Invitation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
