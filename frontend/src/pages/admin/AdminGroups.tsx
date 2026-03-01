/**
 * Admin Groups Tab
 *
 * CRUD for groups: create, edit name/description/roles, delete non-system groups.
 */

import { useState, useEffect } from 'react'
import { FolderOpen, Plus, Trash2, Edit2, RefreshCw, X } from 'lucide-react'
import { adminApi, AdminGroup, AdminRole } from '../../services/api'
import { useConfirm } from '../../contexts/ConfirmContext'

export function AdminGroups() {
  const [groups, setGroups] = useState<AdminGroup[]>([])
  const [roles, setRoles] = useState<AdminRole[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [editingGroup, setEditingGroup] = useState<AdminGroup | null>(null)
  const [formName, setFormName] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formRoleIds, setFormRoleIds] = useState<number[]>([])
  const confirm = useConfirm()

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [groupsData, rolesData] = await Promise.all([
        adminApi.getGroups(),
        adminApi.getRoles(),
      ])
      setGroups(groupsData)
      setRoles(rolesData)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load groups')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const resetForm = () => {
    setFormName('')
    setFormDescription('')
    setFormRoleIds([])
    setShowCreate(false)
    setEditingGroup(null)
  }

  const handleCreate = async () => {
    if (!formName.trim()) return
    try {
      await adminApi.createGroup({ name: formName.trim(), description: formDescription.trim() || undefined, role_ids: formRoleIds.length > 0 ? formRoleIds : undefined })
      resetForm()
      await fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create group')
    }
  }

  const handleEdit = (group: AdminGroup) => {
    setEditingGroup(group)
    setFormName(group.name)
    setFormDescription(group.description || '')
    setFormRoleIds(group.roles.map(r => r.id))
    setShowCreate(false)
  }

  const handleUpdate = async () => {
    if (!editingGroup || !formName.trim()) return
    try {
      await adminApi.updateGroup(editingGroup.id, {
        name: formName.trim(),
        description: formDescription.trim() || undefined,
        role_ids: formRoleIds,
      })
      resetForm()
      await fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update group')
    }
  }

  const handleDelete = async (group: AdminGroup) => {
    const confirmed = await confirm({
      title: 'Delete Group',
      message: `Delete group "${group.name}"? This cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    })
    if (!confirmed) return

    try {
      await adminApi.deleteGroup(group.id)
      await fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete group')
    }
  }

  const toggleRole = (roleId: number) => {
    setFormRoleIds(prev =>
      prev.includes(roleId) ? prev.filter(id => id !== roleId) : [...prev, roleId]
    )
  }

  if (loading) {
    return <div className="flex justify-center py-12"><RefreshCw className="w-6 h-6 animate-spin text-slate-400" /></div>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <FolderOpen className="w-5 h-5" /> Groups ({groups.length})
        </h2>
        <div className="flex gap-2">
          <button onClick={() => { resetForm(); setShowCreate(true) }} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm flex items-center gap-1 transition-colors">
            <Plus className="w-4 h-4" /> New Group
          </button>
          <button onClick={fetchData} className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-700 transition-colors">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-sm">
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-200">dismiss</button>
        </div>
      )}

      {/* Create / Edit Form */}
      {(showCreate || editingGroup) && (
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-medium">{editingGroup ? 'Edit Group' : 'Create Group'}</h3>
            <button onClick={resetForm} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
          </div>
          <input
            type="text" value={formName} onChange={e => setFormName(e.target.value)}
            placeholder="Group name" className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="text" value={formDescription} onChange={e => setFormDescription(e.target.value)}
            placeholder="Description (optional)" className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-sm focus:border-blue-500 focus:outline-none"
          />
          <div>
            <p className="text-xs text-slate-400 mb-1">Assign Roles:</p>
            <div className="flex flex-wrap gap-2">
              {roles.map(r => (
                <label key={r.id} className="flex items-center gap-1.5 text-xs cursor-pointer">
                  <input type="checkbox" checked={formRoleIds.includes(r.id)} onChange={() => toggleRole(r.id)} className="rounded border-slate-600" />
                  <span className={r.is_system ? 'text-yellow-300' : ''}>{r.name}</span>
                  {r.requires_mfa && <span className="text-orange-400">(MFA)</span>}
                </label>
              ))}
            </div>
          </div>
          <button
            onClick={editingGroup ? handleUpdate : handleCreate}
            disabled={!formName.trim()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed rounded-lg text-sm transition-colors"
          >
            {editingGroup ? 'Save Changes' : 'Create'}
          </button>
        </div>
      )}

      <div className="grid gap-3">
        {groups.map(group => (
          <div key={group.id} className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-medium">{group.name}</h3>
                  {group.is_system && <span className="px-1.5 py-0.5 bg-yellow-900/40 text-yellow-400 text-xs rounded">System</span>}
                </div>
                {group.description && <p className="text-sm text-slate-400 mt-0.5">{group.description}</p>}
                <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
                  <span>{group.member_count} member{group.member_count !== 1 ? 's' : ''}</span>
                  <span>{group.roles.length} role{group.roles.length !== 1 ? 's' : ''}: {group.roles.map(r => r.name).join(', ') || 'none'}</span>
                </div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => handleEdit(group)} className="p-1.5 text-slate-400 hover:text-blue-400 hover:bg-slate-700 rounded transition-colors">
                  <Edit2 className="w-4 h-4" />
                </button>
                {!group.is_system && (
                  <button onClick={() => handleDelete(group)} className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
