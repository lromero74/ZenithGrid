/**
 * Admin Management Page
 *
 * Tab-based interface for RBAC administration:
 * - Users: view/edit users, assign groups, enable/disable accounts
 * - Groups: CRUD groups with role assignments
 * - Roles: CRUD roles with permission assignments
 *
 * Requires admin-level permissions. Superusers have full access.
 */

import { useState } from 'react'
import { Shield, Users, FolderOpen, KeyRound } from 'lucide-react'
import { useIsAdmin } from '../hooks/usePermission'
import { AdminUsers } from './admin/AdminUsers'
import { AdminGroups } from './admin/AdminGroups'
import { AdminRoles } from './admin/AdminRoles'

type AdminTab = 'users' | 'groups' | 'roles'

const TABS: { id: AdminTab; label: string; icon: typeof Users }[] = [
  { id: 'users', label: 'Users', icon: Users },
  { id: 'groups', label: 'Groups', icon: FolderOpen },
  { id: 'roles', label: 'Roles', icon: KeyRound },
]

export default function Admin() {
  const isAdmin = useIsAdmin()
  const [activeTab, setActiveTab] = useState<AdminTab>('users')

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-400">
        <Shield className="w-12 h-12 mb-4 text-red-400" />
        <h2 className="text-xl font-semibold text-white mb-2">Access Denied</h2>
        <p>You do not have permission to access admin management.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Shield className="w-6 h-6 text-yellow-400" />
        <h1 className="text-2xl font-bold">Admin Management</h1>
      </div>

      {/* Tab Navigation */}
      <div className="flex space-x-1 bg-slate-800 rounded-lg p-1 border border-slate-700 w-fit">
        {TABS.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-700'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      {activeTab === 'users' && <AdminUsers />}
      {activeTab === 'groups' && <AdminGroups />}
      {activeTab === 'roles' && <AdminRoles />}
    </div>
  )
}
