/**
 * AccountSharingPanel
 *
 * Settings panel for managing account co-management members and invitations.
 * Owner view: invite button, member list with role controls, outbound pending invitations.
 * Member view: role display, "Leave this account" button.
 */

import { useState, useEffect, useCallback } from 'react'
import { UserPlus, Users, Trash2, ChevronDown, Clock, UserMinus, RefreshCw, X } from 'lucide-react'
import { authFetch } from '../../services/api'
import { InviteMemberModal } from './InviteMemberModal'

interface Member {
  user_id: number
  email: string
  display_name: string | null
  role: 'manager' | 'shadow'
  joined_at: string
  expires_at: string | null
  invited_by: string | null
}

interface PendingOutboundInvitation {
  id: number
  invited_email: string
  role: 'manager' | 'shadow'
  expires_at: string
  created_at: string
}

interface AccountSharingPanelProps {
  accountId: number
  accountName: string
  membershipRole: 'owner' | 'manager' | 'shadow'
  currentUserId: number
  onLeave?: () => void
}

const ROLE_LABELS: Record<string, string> = {
  manager: 'Manager',
  shadow: 'Shadow',
}

export function AccountSharingPanel({
  accountId,
  accountName,
  membershipRole,
  currentUserId,
  onLeave,
}: AccountSharingPanelProps) {
  const [members, setMembers] = useState<Member[]>([])
  const [outboundInvitations, setOutboundInvitations] = useState<PendingOutboundInvitation[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [updatingMember, setUpdatingMember] = useState<number | null>(null)

  const isOwner = membershipRole === 'owner'

  const fetchData = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [membersRes, invitesRes] = await Promise.all([
        authFetch(`/api/accounts/${accountId}/sharing/members`),
        isOwner ? authFetch(`/api/accounts/${accountId}/sharing/invitations`) : Promise.resolve(null),
      ])

      if (membersRes.ok) {
        setMembers(await membersRes.json())
      }
      if (invitesRes?.ok) {
        setOutboundInvitations(await invitesRes.json())
      }
    } catch {
      setError('Failed to load sharing data')
    } finally {
      setIsLoading(false)
    }
  }, [accountId, isOwner])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleChangeRole = async (userId: number, newRole: 'manager' | 'shadow') => {
    setUpdatingMember(userId)
    try {
      const res = await authFetch(`/api/accounts/${accountId}/sharing/members/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: newRole }),
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Failed to update role')
      }
      setMembers((prev) => prev.map((m) => m.user_id === userId ? { ...m, role: newRole } : m))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update role')
    } finally {
      setUpdatingMember(null)
    }
  }

  const handleRemoveMember = async (userId: number, memberEmail: string) => {
    if (!confirm(`Remove ${memberEmail} from this account?`)) return
    setUpdatingMember(userId)
    try {
      const res = await authFetch(`/api/accounts/${accountId}/sharing/members/${userId}`, {
        method: 'DELETE',
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Failed to remove member')
      }
      setMembers((prev) => prev.filter((m) => m.user_id !== userId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove member')
    } finally {
      setUpdatingMember(null)
    }
  }

  const handleLeave = async () => {
    if (!confirm(`Leave "${accountName}"? You will lose access immediately.`)) return
    try {
      const res = await authFetch(`/api/accounts/${accountId}/sharing/members/${currentUserId}`, {
        method: 'DELETE',
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Failed to leave account')
      }
      onLeave?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to leave account')
    }
  }

  const handleRevokeInvitation = async (invitationId: number, email: string) => {
    if (!confirm(`Revoke invitation for ${email}?`)) return
    try {
      const res = await authFetch(`/api/accounts/${accountId}/sharing/invitations/${invitationId}`, {
        method: 'DELETE',
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Failed to revoke invitation')
      }
      setOutboundInvitations((prev) => prev.filter((i) => i.id !== invitationId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke invitation')
    }
  }

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-violet-400" />
          <h3 className="text-sm font-semibold text-slate-200">Account Sharing</h3>
          {members.length > 0 && (
            <span className="text-xs px-1.5 py-0.5 bg-violet-500/20 text-violet-300 rounded">
              {members.length} member{members.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchData}
            disabled={isLoading}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-700 rounded transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          {isOwner && (
            <button
              onClick={() => setShowInviteModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-violet-600 hover:bg-violet-500 rounded-lg transition-colors"
            >
              <UserPlus className="w-3.5 h-3.5" />
              Invite
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-900/30 border border-red-700/50 rounded-lg text-xs text-red-300">
          {error}
        </div>
      )}

      {/* Member view — show own role and leave button */}
      {!isOwner && (
        <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-700 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400">Your access level</p>
            <p className="text-sm font-medium text-violet-300 capitalize">{membershipRole}</p>
          </div>
          <button
            onClick={handleLeave}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-400 hover:text-red-300 hover:bg-red-900/30 border border-red-700/40 rounded-lg transition-colors"
          >
            <UserMinus className="w-3.5 h-3.5" />
            Leave Account
          </button>
        </div>
      )}

      {/* Members list */}
      {members.length > 0 ? (
        <div className="space-y-1.5">
          {members.map((member) => (
            <MemberRow
              key={member.user_id}
              member={member}
              isOwner={isOwner}
              isUpdating={updatingMember === member.user_id}
              onChangeRole={handleChangeRole}
              onRemove={handleRemoveMember}
            />
          ))}
        </div>
      ) : (
        isOwner && !isLoading && (
          <div className="text-center py-6 text-slate-500 text-sm">
            <Users className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p>No members yet.</p>
            <p className="text-xs mt-1">Invite someone to collaborate on this account.</p>
          </div>
        )
      )}

      {/* Outbound pending invitations (owner only) */}
      {isOwner && outboundInvitations.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <Clock className="w-3 h-3" />
            Pending Invitations
          </p>
          <div className="space-y-1.5">
            {outboundInvitations.map((inv) => (
              <div
                key={inv.id}
                className="flex items-center justify-between px-3 py-2 bg-slate-900/40 rounded-lg border border-slate-700/50"
              >
                <div className="min-w-0">
                  <p className="text-sm text-slate-300 truncate">{inv.invited_email}</p>
                  <p className="text-xs text-slate-500">
                    <span className="capitalize">{inv.role}</span>
                    {' · '}expires {formatDate(inv.expires_at)}
                  </p>
                </div>
                <button
                  onClick={() => handleRevokeInvitation(inv.id, inv.invited_email)}
                  className="ml-3 p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-900/20 rounded transition-colors flex-shrink-0"
                  title="Revoke invitation"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {showInviteModal && (
        <InviteMemberModal
          accountId={accountId}
          accountName={accountName}
          onClose={() => setShowInviteModal(false)}
          onSuccess={() => {
            setShowInviteModal(false)
            fetchData()
          }}
        />
      )}
    </div>
  )
}

// =============================================================================
// MemberRow sub-component
// =============================================================================

interface MemberRowProps {
  member: Member
  isOwner: boolean
  isUpdating: boolean
  onChangeRole: (userId: number, role: 'manager' | 'shadow') => void
  onRemove: (userId: number, email: string) => void
}

function MemberRow({ member, isOwner, isUpdating, onChangeRole, onRemove }: MemberRowProps) {
  const [roleOpen, setRoleOpen] = useState(false)

  const displayName = member.display_name || member.email

  return (
    <div className={`flex items-center justify-between px-3 py-2.5 rounded-lg border transition-opacity ${
      isUpdating ? 'opacity-50' : ''
    } bg-slate-900/40 border-slate-700/50`}>
      <div className="flex items-center gap-3 min-w-0">
        {/* Avatar placeholder */}
        <div className="w-7 h-7 rounded-full bg-violet-700/40 flex items-center justify-center flex-shrink-0">
          <span className="text-xs font-semibold text-violet-300">
            {(member.display_name || member.email).charAt(0).toUpperCase()}
          </span>
        </div>
        <div className="min-w-0">
          <p className="text-sm text-slate-200 truncate">{displayName}</p>
          {member.display_name && (
            <p className="text-xs text-slate-500 truncate">{member.email}</p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 flex-shrink-0 ml-3">
        {/* Role selector (owner only) */}
        {isOwner ? (
          <div className="relative">
            <button
              onClick={() => setRoleOpen((o) => !o)}
              disabled={isUpdating}
              className="flex items-center gap-1 px-2 py-1 text-xs text-slate-300 bg-slate-700 hover:bg-slate-600 rounded border border-slate-600 transition-colors"
            >
              <span className="capitalize">{ROLE_LABELS[member.role]}</span>
              <ChevronDown className="w-3 h-3 text-slate-400" />
            </button>
            {roleOpen && (
              <div className="absolute right-0 mt-1 w-32 bg-slate-800 border border-slate-700 rounded-lg shadow-lg z-10 overflow-hidden">
                {(['manager', 'shadow'] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => {
                      setRoleOpen(false)
                      if (r !== member.role) onChangeRole(member.user_id, r)
                    }}
                    className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                      r === member.role
                        ? 'text-blue-400 bg-blue-500/10'
                        : 'text-slate-300 hover:bg-slate-700'
                    }`}
                  >
                    {ROLE_LABELS[r]}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <span className="text-xs px-2 py-1 bg-violet-500/10 text-violet-400 rounded capitalize">
            {ROLE_LABELS[member.role]}
          </span>
        )}

        {/* Remove button (owner only) */}
        {isOwner && (
          <button
            onClick={() => onRemove(member.user_id, member.email)}
            disabled={isUpdating}
            className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-900/20 rounded transition-colors"
            title={`Remove ${displayName}`}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  )
}

