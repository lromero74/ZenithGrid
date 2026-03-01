/**
 * Admin Roles Tab
 *
 * CRUD for roles: create, edit name/description/MFA/permissions, delete non-system roles.
 */

import { useState, useEffect } from 'react'
import { KeyRound, Plus, Trash2, Edit2, RefreshCw, X, ShieldCheck } from 'lucide-react'
import { adminApi, AdminRole, AdminPermission } from '../../services/api'
import { useConfirm } from '../../contexts/ConfirmContext'

export function AdminRoles() {
  const [roles, setRoles] = useState<AdminRole[]>([])
  const [permissions, setPermissions] = useState<AdminPermission[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [editingRole, setEditingRole] = useState<AdminRole | null>(null)
  const [formName, setFormName] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formRequiresMfa, setFormRequiresMfa] = useState(false)
  const [formPermissionIds, setFormPermissionIds] = useState<number[]>([])
  const confirm = useConfirm()

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [rolesData, permsData] = await Promise.all([
        adminApi.getRoles(),
        adminApi.getPermissions(),
      ])
      setRoles(rolesData)
      setPermissions(permsData)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load roles')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const resetForm = () => {
    setFormName('')
    setFormDescription('')
    setFormRequiresMfa(false)
    setFormPermissionIds([])
    setShowCreate(false)
    setEditingRole(null)
  }

  const handleCreate = async () => {
    if (!formName.trim()) return
    try {
      await adminApi.createRole({
        name: formName.trim(),
        description: formDescription.trim() || undefined,
        requires_mfa: formRequiresMfa,
        permission_ids: formPermissionIds.length > 0 ? formPermissionIds : undefined,
      })
      resetForm()
      await fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create role')
    }
  }

  const handleEdit = (role: AdminRole) => {
    setEditingRole(role)
    setFormName(role.name)
    setFormDescription(role.description || '')
    setFormRequiresMfa(role.requires_mfa)
    setFormPermissionIds(role.permissions.map(p => p.id))
    setShowCreate(false)
  }

  const handleUpdate = async () => {
    if (!editingRole || !formName.trim()) return
    try {
      await adminApi.updateRole(editingRole.id, {
        name: formName.trim(),
        description: formDescription.trim() || undefined,
        requires_mfa: formRequiresMfa,
        permission_ids: formPermissionIds,
      })
      resetForm()
      await fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update role')
    }
  }

  const handleDelete = async (role: AdminRole) => {
    const confirmed = await confirm({
      title: 'Delete Role',
      message: `Delete role "${role.name}"? This cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    })
    if (!confirmed) return

    try {
      await adminApi.deleteRole(role.id)
      await fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete role')
    }
  }

  const togglePermission = (permId: number) => {
    setFormPermissionIds(prev =>
      prev.includes(permId) ? prev.filter(id => id !== permId) : [...prev, permId]
    )
  }

  // Group permissions by resource for display
  const permissionsByResource = permissions.reduce<Record<string, AdminPermission[]>>((acc, p) => {
    const resource = p.name.split(':')[0] || 'other'
    if (!acc[resource]) acc[resource] = []
    acc[resource].push(p)
    return acc
  }, {})

  if (loading) {
    return <div className="flex justify-center py-12"><RefreshCw className="w-6 h-6 animate-spin text-slate-400" /></div>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <KeyRound className="w-5 h-5" /> Roles ({roles.length})
        </h2>
        <div className="flex gap-2">
          <button onClick={() => { resetForm(); setShowCreate(true) }} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm flex items-center gap-1 transition-colors">
            <Plus className="w-4 h-4" /> New Role
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
      {(showCreate || editingRole) && (
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-medium">{editingRole ? 'Edit Role' : 'Create Role'}</h3>
            <button onClick={resetForm} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
          </div>
          <input
            type="text" value={formName} onChange={e => setFormName(e.target.value)}
            placeholder="Role name (e.g. custom_trader)" className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="text" value={formDescription} onChange={e => setFormDescription(e.target.value)}
            placeholder="Description (optional)" className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-sm focus:border-blue-500 focus:outline-none"
          />
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={formRequiresMfa} onChange={e => setFormRequiresMfa(e.target.checked)} className="rounded border-slate-600" />
            <ShieldCheck className="w-4 h-4 text-orange-400" />
            Requires MFA
          </label>
          <div>
            <p className="text-xs text-slate-400 mb-2">Permissions:</p>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {Object.entries(permissionsByResource).map(([resource, perms]) => (
                <div key={resource}>
                  <p className="text-xs font-medium text-slate-300 mb-1 capitalize">{resource}</p>
                  <div className="flex flex-wrap gap-2 ml-2">
                    {perms.map(p => (
                      <label key={p.id} className="flex items-center gap-1 text-xs cursor-pointer">
                        <input type="checkbox" checked={formPermissionIds.includes(p.id)} onChange={() => togglePermission(p.id)} className="rounded border-slate-600" />
                        {p.name}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <button
            onClick={editingRole ? handleUpdate : handleCreate}
            disabled={!formName.trim()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed rounded-lg text-sm transition-colors"
          >
            {editingRole ? 'Save Changes' : 'Create'}
          </button>
        </div>
      )}

      <div className="grid gap-3">
        {roles.map(role => (
          <div key={role.id} className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-medium">{role.name}</h3>
                  {role.is_system && <span className="px-1.5 py-0.5 bg-yellow-900/40 text-yellow-400 text-xs rounded">System</span>}
                  {role.requires_mfa && <span className="px-1.5 py-0.5 bg-orange-900/40 text-orange-400 text-xs rounded">MFA Required</span>}
                </div>
                {role.description && <p className="text-sm text-slate-400 mt-0.5">{role.description}</p>}
                <div className="flex flex-wrap gap-1 mt-2">
                  {role.permissions.map(p => (
                    <span key={p.id} className="px-1.5 py-0.5 bg-slate-700 text-xs rounded text-slate-300">{p.name}</span>
                  ))}
                  {role.permissions.length === 0 && <span className="text-xs text-slate-500">No permissions</span>}
                </div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => handleEdit(role)} className="p-1.5 text-slate-400 hover:text-blue-400 hover:bg-slate-700 rounded transition-colors">
                  <Edit2 className="w-4 h-4" />
                </button>
                {!role.is_system && (
                  <button onClick={() => handleDelete(role)} className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded transition-colors">
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
