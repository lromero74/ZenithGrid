/**
 * Admin Users Tab
 *
 * Lists all users with group memberships, MFA status, and enable/disable controls.
 */

import { useState, useEffect } from 'react'
import {
  Users, Shield, ShieldCheck, ShieldOff,
  CheckCircle, XCircle, RefreshCw, Clock, X, Trash2,
} from 'lucide-react'
import {
  adminApi, AdminUser, AdminGroup, SessionPolicyConfig,
} from '../../services/api'
import { useConfirm } from '../../contexts/ConfirmContext'

export function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [groups, setGroups] = useState<AdminGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingUserId, setEditingUserId] = useState<number | null>(null)
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([])
  // Session management modal
  const [sessionUser, setSessionUser] = useState<AdminUser | null>(null)
  const [effectivePolicy, setEffectivePolicy] = useState<SessionPolicyConfig | null>(null)
  const [overridePolicy, setOverridePolicy] = useState<SessionPolicyConfig>({})
  const [activeSessions, setActiveSessions] = useState<any[]>([])
  const [sessionLoading, setSessionLoading] = useState(false)
  const confirm = useConfirm()

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [usersData, groupsData] = await Promise.all([
        adminApi.getUsers(),
        adminApi.getGroups(),
      ])
      setUsers(usersData)
      setGroups(groupsData)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const handleToggleStatus = async (user: AdminUser) => {
    const action = user.is_active ? 'disable' : 'enable'
    const confirmed = await confirm({
      title: `${action === 'disable' ? 'Disable' : 'Enable'} User`,
      message: `Are you sure you want to ${action} ${user.email}?`,
      confirmLabel: action === 'disable' ? 'Disable' : 'Enable',
      variant: action === 'disable' ? 'danger' : 'default',
    })
    if (!confirmed) return

    try {
      await adminApi.updateUserStatus(user.id, !user.is_active)
      await fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || `Failed to ${action} user`)
    }
  }

  const handleEditGroups = (user: AdminUser) => {
    setEditingUserId(user.id)
    setSelectedGroupIds(user.groups.map(g => g.id))
  }

  const handleSaveGroups = async () => {
    if (editingUserId === null) return
    try {
      await adminApi.updateUserGroups(editingUserId, selectedGroupIds)
      setEditingUserId(null)
      await fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update groups')
    }
  }

  const toggleGroup = (groupId: number) => {
    setSelectedGroupIds(prev =>
      prev.includes(groupId)
        ? prev.filter(id => id !== groupId)
        : [...prev, groupId]
    )
  }

  const openSessionModal = async (user: AdminUser) => {
    setSessionUser(user)
    setOverridePolicy(user.session_policy_override || {})
    setSessionLoading(true)
    try {
      const [policy, sessions] = await Promise.all([
        adminApi.getEffectiveSessionPolicy(user.id),
        adminApi.getUserSessions(user.id),
      ])
      setEffectivePolicy(policy)
      setActiveSessions(sessions)
    } catch (err: any) {
      setError(
        err.response?.data?.detail
          || 'Failed to load session info'
      )
    } finally {
      setSessionLoading(false)
    }
  }

  const closeSessionModal = () => {
    setSessionUser(null)
    setEffectivePolicy(null)
    setActiveSessions([])
  }

  const handleSaveOverride = async () => {
    if (!sessionUser) return
    try {
      await adminApi.updateUserSessionPolicy(
        sessionUser.id, overridePolicy
      )
      const policy =
        await adminApi.getEffectiveSessionPolicy(
          sessionUser.id
        )
      setEffectivePolicy(policy)
      await fetchData()
    } catch (err: any) {
      setError(
        err.response?.data?.detail
          || 'Failed to save session override'
      )
    }
  }

  const handleForceEnd = async (sessionId: string) => {
    if (!sessionUser) return
    const confirmed = await confirm({
      title: 'End Session',
      message: 'Force-end this session? The user will be logged out.',
      confirmLabel: 'End Session',
      variant: 'danger',
    })
    if (!confirmed) return
    try {
      await adminApi.forceEndSession(
        sessionUser.id, sessionId
      )
      const sessions = await adminApi.getUserSessions(
        sessionUser.id
      )
      setActiveSessions(sessions)
    } catch (err: any) {
      setError(
        err.response?.data?.detail
          || 'Failed to end session'
      )
    }
  }

  if (loading) {
    return <div className="flex justify-center py-12"><RefreshCw className="w-6 h-6 animate-spin text-slate-400" /></div>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Users className="w-5 h-5" /> Users ({users.length})
        </h2>
        <button onClick={fetchData} className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-700 transition-colors">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-sm">
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-200">dismiss</button>
        </div>
      )}

      <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-slate-400">
              <th className="text-left p-3">Email</th>
              <th className="text-left p-3">Groups</th>
              <th className="text-center p-3">MFA</th>
              <th className="text-center p-3">Status</th>
              <th className="text-right p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(user => (
              <tr key={user.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                <td className="p-3">
                  <div className="flex items-center gap-2">
                    {user.is_superuser && <span title="Superuser"><Shield className="w-4 h-4 text-yellow-400" /></span>}
                    <div>
                      <p className="font-medium">{user.display_name || user.email}</p>
                      {user.display_name && <p className="text-xs text-slate-400">{user.email}</p>}
                    </div>
                  </div>
                </td>
                <td className="p-3">
                  {editingUserId === user.id ? (
                    <div className="space-y-1">
                      {groups.map(g => (
                        <label key={g.id} className="flex items-center gap-1.5 text-xs cursor-pointer">
                          <input
                            type="checkbox"
                            checked={selectedGroupIds.includes(g.id)}
                            onChange={() => toggleGroup(g.id)}
                            className="rounded border-slate-600"
                          />
                          <span className={g.is_system ? 'text-yellow-300' : ''}>{g.name}</span>
                        </label>
                      ))}
                      <div className="flex gap-1 mt-2">
                        <button onClick={handleSaveGroups} className="px-2 py-1 bg-blue-600 hover:bg-blue-700 rounded text-xs">Save</button>
                        <button onClick={() => setEditingUserId(null)} className="px-2 py-1 bg-slate-600 hover:bg-slate-500 rounded text-xs">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {user.groups.length === 0 && <span className="text-slate-500 text-xs">No groups</span>}
                      {user.groups.map(g => (
                        <span key={g.id} className="px-2 py-0.5 bg-slate-700 rounded text-xs">{g.name}</span>
                      ))}
                    </div>
                  )}
                </td>
                <td className="p-3 text-center">
                  {user.mfa_enabled || user.mfa_email_enabled ? (
                    <span title="MFA enabled"><ShieldCheck className="w-4 h-4 text-green-400 mx-auto" /></span>
                  ) : (
                    <span title="MFA disabled"><ShieldOff className="w-4 h-4 text-slate-500 mx-auto" /></span>
                  )}
                </td>
                <td className="p-3 text-center">
                  {user.is_active ? (
                    <span title="Active"><CheckCircle className="w-4 h-4 text-green-400 mx-auto" /></span>
                  ) : (
                    <span title="Disabled"><XCircle className="w-4 h-4 text-red-400 mx-auto" /></span>
                  )}
                </td>
                <td className="p-3 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={() => openSessionModal(user)}
                      className="px-2 py-1 text-xs text-amber-400 hover:text-amber-300 hover:bg-slate-700 rounded transition-colors"
                    >
                      Session
                    </button>
                    <button
                      onClick={() => handleEditGroups(user)}
                      className="px-2 py-1 text-xs text-blue-400 hover:text-blue-300 hover:bg-slate-700 rounded transition-colors"
                    >
                      Groups
                    </button>
                    <button
                      onClick={() => handleToggleStatus(user)}
                      disabled={user.is_superuser}
                      className={`px-2 py-1 text-xs rounded transition-colors ${
                        user.is_superuser
                          ? 'text-slate-600 cursor-not-allowed'
                          : user.is_active
                            ? 'text-red-400 hover:text-red-300 hover:bg-slate-700'
                            : 'text-green-400 hover:text-green-300 hover:bg-slate-700'
                      }`}
                    >
                      {user.is_active ? 'Disable' : 'Enable'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Session Management Modal */}
      {sessionUser && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 max-w-lg w-full max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold flex items-center gap-2">
                <Clock className="w-5 h-5 text-amber-400" />
                Sessions: {sessionUser.email}
              </h3>
              <button
                onClick={closeSessionModal}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {sessionLoading ? (
              <div className="flex justify-center py-8">
                <RefreshCw className="w-5 h-5 animate-spin text-slate-400" />
              </div>
            ) : (
              <div className="space-y-4">
                {/* Effective Policy */}
                {effectivePolicy && (
                  <div className="bg-slate-900 rounded-lg p-3">
                    <p className="text-xs text-slate-400 mb-2 font-medium">
                      Effective Policy (from groups):
                    </p>
                    <div className="grid grid-cols-2 gap-1 text-xs">
                      <span className="text-slate-500">
                        Timeout:
                      </span>
                      <span>
                        {effectivePolicy
                          .session_timeout_minutes
                          ? `${effectivePolicy.session_timeout_minutes}m`
                          : 'None'}
                      </span>
                      <span className="text-slate-500">
                        Auto-logout:
                      </span>
                      <span>
                        {effectivePolicy.auto_logout
                          ? 'Yes' : 'No'}
                      </span>
                      <span className="text-slate-500">
                        Max sessions:
                      </span>
                      <span>
                        {effectivePolicy
                          .max_simultaneous_sessions
                          ?? 'Unlimited'}
                      </span>
                      <span className="text-slate-500">
                        Max per IP:
                      </span>
                      <span>
                        {effectivePolicy
                          .max_sessions_per_ip
                          ?? 'Unlimited'}
                      </span>
                      <span className="text-slate-500">
                        Cooldown:
                      </span>
                      <span>
                        {effectivePolicy
                          .relogin_cooldown_minutes
                          ? `${effectivePolicy.relogin_cooldown_minutes}m`
                          : 'None'}
                      </span>
                    </div>
                  </div>
                )}

                {/* Override Fields */}
                <div>
                  <p className="text-xs text-slate-400 mb-2 font-medium">
                    User Override:
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs text-slate-500">
                        Timeout (min)
                      </label>
                      <input
                        type="number" min={1}
                        value={overridePolicy
                          .session_timeout_minutes ?? ''}
                        onChange={e =>
                          setOverridePolicy(p => ({
                            ...p,
                            session_timeout_minutes:
                              e.target.value
                                ? Number(e.target.value)
                                : null,
                          }))
                        }
                        placeholder="Inherit"
                        className="w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm focus:border-blue-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-500">
                        Max Sessions
                      </label>
                      <input
                        type="number" min={1}
                        value={overridePolicy
                          .max_simultaneous_sessions
                          ?? ''}
                        onChange={e =>
                          setOverridePolicy(p => ({
                            ...p,
                            max_simultaneous_sessions:
                              e.target.value
                                ? Number(e.target.value)
                                : null,
                          }))
                        }
                        placeholder="Inherit"
                        className="w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm focus:border-blue-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-500">
                        Max Per IP
                      </label>
                      <input
                        type="number" min={1}
                        value={overridePolicy
                          .max_sessions_per_ip ?? ''}
                        onChange={e =>
                          setOverridePolicy(p => ({
                            ...p,
                            max_sessions_per_ip:
                              e.target.value
                                ? Number(e.target.value)
                                : null,
                          }))
                        }
                        placeholder="Inherit"
                        className="w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm focus:border-blue-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-500">
                        Cooldown (min)
                      </label>
                      <input
                        type="number" min={1}
                        value={overridePolicy
                          .relogin_cooldown_minutes
                          ?? ''}
                        onChange={e =>
                          setOverridePolicy(p => ({
                            ...p,
                            relogin_cooldown_minutes:
                              e.target.value
                                ? Number(e.target.value)
                                : null,
                          }))
                        }
                        placeholder="Inherit"
                        className="w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm focus:border-blue-500 focus:outline-none"
                      />
                    </div>
                  </div>
                  <label className="flex items-center gap-2 mt-2 text-xs cursor-pointer">
                    <input
                      type="checkbox"
                      checked={
                        overridePolicy.auto_logout
                          ?? false
                      }
                      onChange={e =>
                        setOverridePolicy(p => ({
                          ...p,
                          auto_logout:
                            e.target.checked || null,
                        }))
                      }
                      className="rounded border-slate-600"
                    />
                    <span className="text-slate-300">
                      Auto-logout at expiry
                    </span>
                  </label>
                  <button
                    onClick={handleSaveOverride}
                    className="mt-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-xs transition-colors"
                  >
                    Save Override
                  </button>
                </div>

                {/* Active Sessions */}
                <div>
                  <p className="text-xs text-slate-400 mb-2 font-medium">
                    Active Sessions
                    ({activeSessions.length}):
                  </p>
                  {activeSessions.length === 0 ? (
                    <p className="text-xs text-slate-500">
                      No active sessions
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {activeSessions.map((s: any) => (
                        <div
                          key={s.session_id || s.id}
                          className="flex items-center justify-between bg-slate-900 rounded p-2 text-xs"
                        >
                          <div>
                            <p className="text-slate-300">
                              {s.ip_address || 'Unknown IP'}
                            </p>
                            {s.created_at && (
                              <p className="text-slate-500">
                                Started:{' '}
                                {new Date(
                                  s.created_at
                                ).toLocaleString()}
                              </p>
                            )}
                          </div>
                          <button
                            onClick={() =>
                              handleForceEnd(
                                s.session_id || s.id
                              )
                            }
                            className="p-1 text-red-400 hover:text-red-300 hover:bg-slate-700 rounded transition-colors"
                            title="Force end session"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
