/**
 * PendingInvitationsPopover
 *
 * Header bell/badge showing inbound pending invitations.
 * When clicked, shows a popover listing all pending invitations with
 * "Review" links (navigates to /accept-invite?token=...) and quick Decline.
 *
 * Also serves as the in-app notification surface for real-time invitations
 * pushed via WebSocket (handled by NotificationContext).
 */

import { useState, useRef, useEffect } from 'react'
import { Bell, X, Users, ChevronRight, UserCheck, Eye } from 'lucide-react'
import { useAccount, PendingInvitation } from '../../contexts/AccountContext'

interface PendingInvitationsPopoverProps {
  onNavigate?: (path: string) => void
}

export function PendingInvitationsPopover({ onNavigate }: PendingInvitationsPopoverProps) {
  const { pendingInvitations, pendingInvitationCount, declineInvitation, refreshInvitations } = useAccount()
  const [isOpen, setIsOpen] = useState(false)
  const [decliningToken, setDecliningToken] = useState<string | null>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  if (pendingInvitationCount === 0) return null

  const handleReview = (token: string) => {
    setIsOpen(false)
    const path = `/accept-invite?token=${token}`
    if (onNavigate) {
      onNavigate(path)
    } else {
      window.location.href = path
    }
  }

  const handleDecline = async (token: string) => {
    setDecliningToken(token)
    try {
      await declineInvitation(token)
    } finally {
      setDecliningToken(null)
    }
  }

  return (
    <div className="relative" ref={popoverRef}>
      <button
        onClick={() => setIsOpen((o) => !o)}
        className="relative p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-700 rounded-lg transition-colors"
        title="Account invitations"
      >
        <Bell className="w-5 h-5" />
        <span className="absolute -top-1 -right-1 bg-violet-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center leading-none">
          {pendingInvitationCount > 9 ? '9+' : pendingInvitationCount}
        </span>
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-slate-800 rounded-xl border border-slate-700 shadow-2xl z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-violet-400" />
              <span className="text-sm font-semibold text-slate-200">Account Invitations</span>
              <span className="text-xs px-1.5 py-0.5 bg-violet-500/20 text-violet-300 rounded">
                {pendingInvitationCount}
              </span>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 text-slate-500 hover:text-slate-300 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="max-h-80 overflow-y-auto">
            {pendingInvitations.map((inv) => (
              <InvitationRow
                key={inv.token}
                invitation={inv}
                isDeclinePending={decliningToken === inv.token}
                onReview={() => handleReview(inv.token)}
                onDecline={() => handleDecline(inv.token)}
              />
            ))}
          </div>

          <div className="border-t border-slate-700 px-4 py-2.5">
            <button
              onClick={refreshInvitations}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              Refresh
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// InvitationRow
// =============================================================================

interface InvitationRowProps {
  invitation: PendingInvitation
  isDeclinePending: boolean
  onReview: () => void
  onDecline: () => void
}

function InvitationRow({ invitation, isDeclinePending, onReview, onDecline }: InvitationRowProps) {
  const RoleIcon = invitation.role === 'manager' ? UserCheck : Eye
  const expiresDate = new Date(invitation.expires_at).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric',
  })

  return (
    <div className={`px-4 py-3 border-b border-slate-700/50 transition-opacity ${isDeclinePending ? 'opacity-50' : ''}`}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5 p-1.5 rounded-lg bg-violet-500/15 flex-shrink-0">
          <RoleIcon className="w-4 h-4 text-violet-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-200 truncate">{invitation.account_name}</p>
          <p className="text-xs text-slate-400 mt-0.5">
            <span className="text-violet-400">{invitation.invited_by}</span>
            {' '}invited you as{' '}
            <span className="text-slate-300 capitalize">{invitation.role}</span>
          </p>
          <p className="text-xs text-slate-500 mt-0.5">Expires {expiresDate}</p>
        </div>
      </div>

      <div className="flex gap-2 mt-2.5">
        <button
          onClick={onReview}
          className="flex-1 flex items-center justify-center gap-1 py-1.5 text-xs font-medium text-white bg-violet-600 hover:bg-violet-500 rounded-lg transition-colors"
        >
          Review
          <ChevronRight className="w-3 h-3" />
        </button>
        <button
          onClick={onDecline}
          disabled={isDeclinePending}
          className="px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-red-400 hover:bg-red-900/20 border border-slate-600 hover:border-red-700/40 rounded-lg transition-colors disabled:opacity-50"
        >
          Decline
        </button>
      </div>
    </div>
  )
}
