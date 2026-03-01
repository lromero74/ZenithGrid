/**
 * Admin Users Tab
 *
 * Lists all users with group memberships, MFA status, and enable/disable controls.
 */

import { useState, useEffect } from 'react'
import { Users, Shield, ShieldCheck, ShieldOff, CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import { adminApi, AdminUser, AdminGroup } from '../../services/api'
import { useConfirm } from '../../contexts/ConfirmContext'

export function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [groups, setGroups] = useState<AdminGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingUserId, setEditingUserId] = useState<number | null>(null)
  const [selectedGroupIds, setSelectedGroupIds] = useState<number[]>([])
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
    </div>
  )
}
