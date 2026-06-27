import { useState, useEffect } from 'react'
import { api } from '../../services/api'

export function AdminDisplayNameField() {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const [saved, setSaved] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/admin/users').then(res => {
      const me = res.data.find((u: { is_superuser?: boolean; admin_display_name?: string }) => u.is_superuser)
      if (me?.admin_display_name) {
        setSaved(me.admin_display_name)
        setValue(me.admin_display_name)
      }
    }).catch(() => {})
  }, [])

  const handleSave = async () => {
    if (!value.trim() || value.trim().length < 2) return
    setSaving(true)
    try {
      await api.put('/users/admin-display-name', { admin_display_name: value.trim() })
      setSaved(value.trim())
      setEditing(false)
    } catch {
      // Error silently
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-3 pt-3 border-t border-slate-700/50">
      <label className="block text-sm text-slate-400 mb-1">Admin Display Name</label>
      {editing ? (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={value}
            onChange={e => setValue(e.target.value)}
            className="px-3 py-1.5 bg-slate-800 border border-slate-600 rounded text-sm text-white w-48"
            placeholder="e.g., Louis"
            maxLength={50}
            autoFocus
          />
          <button onClick={handleSave} disabled={saving || value.trim().length < 2}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded text-xs">
            {saving ? '...' : 'Save'}
          </button>
          <button onClick={() => { setEditing(false); setValue(saved || '') }}
            className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-xs">
            Cancel
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <p className="text-white">{saved || 'Not set'}</p>
          <button onClick={() => setEditing(true)}
            className="text-xs text-blue-400 hover:text-blue-300">Edit</button>
        </div>
      )}
      <p className="text-xs text-slate-500 mt-1">This name appears when you message users as Admin</p>
    </div>
  )
}
