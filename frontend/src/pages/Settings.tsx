import { useState, FormEvent, useEffect } from 'react'
import { User, Lock, CheckCircle, AlertCircle, Database, Trash2 } from 'lucide-react'
import { AccountsManagement } from '../components/AccountsManagement'
import { PaperTradingManager } from '../components/PaperTradingManager'
import { AddAccountModal } from '../components/AddAccountModal'
import { AIProvidersManager } from '../components/AIProvidersManager'
import { AutoBuySettings } from '../components/AutoBuySettings'
import { useAccount } from '../contexts/AccountContext'
import { useAuth } from '../contexts/AuthContext'
import { settingsApi } from '../services/api'

export default function Settings() {
  const [showAddAccountModal, setShowAddAccountModal] = useState(false)
  const { user, changePassword } = useAuth()
  const { accounts } = useAccount()

  // Password change state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordSuccess, setPasswordSuccess] = useState(false)
  const [isChangingPassword, setIsChangingPassword] = useState(false)

  // Log retention settings
  const [logRetentionDays, setLogRetentionDays] = useState<number>(14)
  const [isSavingRetention, setIsSavingRetention] = useState(false)
  const [retentionSuccess, setRetentionSuccess] = useState(false)
  const [retentionError, setRetentionError] = useState<string | null>(null)

  // Load log retention setting on mount
  useEffect(() => {
    const loadRetentionSetting = async () => {
      try {
        const setting = await settingsApi.get('decision_log_retention_days') as { key: string; value: string; value_type: string; description: string; updated_at: string }
        if (setting && setting.value) {
          setLogRetentionDays(parseInt(setting.value))
        }
      } catch (err) {
        console.error('Failed to load log retention setting:', err)
      }
    }
    loadRetentionSetting()
  }, [])

  const handleLogRetentionChange = async (e: FormEvent) => {
    e.preventDefault()
    setRetentionError(null)
    setRetentionSuccess(false)

    if (logRetentionDays < 1 || logRetentionDays > 365) {
      setRetentionError('Retention period must be between 1 and 365 days')
      return
    }

    setIsSavingRetention(true)

    try {
      await settingsApi.update('decision_log_retention_days', logRetentionDays.toString())
      setRetentionSuccess(true)
      setTimeout(() => setRetentionSuccess(false), 5000)
    } catch (err) {
      setRetentionError(err instanceof Error ? err.message : 'Failed to save setting')
    } finally {
      setIsSavingRetention(false)
    }
  }

  const handlePasswordChange = async (e: FormEvent) => {
    e.preventDefault()
    setPasswordError(null)
    setPasswordSuccess(false)

    // Validation
    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match')
      return
    }

    if (newPassword.length < 8) {
      setPasswordError('New password must be at least 8 characters')
      return
    }

    if (currentPassword === newPassword) {
      setPasswordError('New password must be different from current password')
      return
    }

    setIsChangingPassword(true)

    try {
      await changePassword(currentPassword, newPassword)
      setPasswordSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      // Clear success message after 5 seconds
      setTimeout(() => setPasswordSuccess(false), 5000)
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : 'Failed to change password')
    } finally {
      setIsChangingPassword(false)
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Settings</h2>
      </div>

      {/* User Profile & Security Section */}
      <div className="card p-6">
        <div className="flex items-center space-x-3 mb-6">
          <User className="w-6 h-6 text-blue-400" />
          <h3 className="text-xl font-semibold">Account Security</h3>
        </div>

        {/* User Info */}
        <div className="mb-6 p-4 bg-slate-700/50 rounded-lg">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Email</label>
              <p className="text-white">{user?.email || 'Not logged in'}</p>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Display Name</label>
              <p className="text-white">{user?.display_name || 'Not set'}</p>
            </div>
          </div>
        </div>

        {/* Password Change Form */}
        <div className="border-t border-slate-700 pt-6">
          <div className="flex items-center space-x-2 mb-4">
            <Lock className="w-5 h-5 text-slate-400" />
            <h4 className="text-lg font-medium">Change Password</h4>
          </div>

          {/* Success Message */}
          {passwordSuccess && (
            <div className="mb-4 p-4 bg-green-500/10 border border-green-500/50 rounded-lg flex items-center space-x-3">
              <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
              <p className="text-green-400 text-sm">Password changed successfully!</p>
            </div>
          )}

          {/* Error Message */}
          {passwordError && (
            <div className="mb-4 p-4 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-3">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
              <p className="text-red-400 text-sm">{passwordError}</p>
            </div>
          )}

          <form onSubmit={handlePasswordChange} className="space-y-4 max-w-md">
            <div>
              <label htmlFor="currentPassword" className="block text-sm font-medium text-slate-300 mb-2">
                Current Password
              </label>
              <input
                id="currentPassword"
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Enter current password"
              />
            </div>

            <div>
              <label htmlFor="newPassword" className="block text-sm font-medium text-slate-300 mb-2">
                New Password
              </label>
              <input
                id="newPassword"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                autoComplete="new-password"
                minLength={8}
                className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Minimum 8 characters"
              />
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-slate-300 mb-2">
                Confirm New Password
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                autoComplete="new-password"
                className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Re-enter new password"
              />
            </div>

            <button
              type="submit"
              disabled={isChangingPassword || !currentPassword || !newPassword || !confirmPassword}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-800"
            >
              {isChangingPassword ? (
                <span className="flex items-center space-x-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>Changing...</span>
                </span>
              ) : (
                'Change Password'
              )}
            </button>
          </form>
        </div>
      </div>

      {/* Accounts Management Section */}
      <AccountsManagement onAddAccount={() => setShowAddAccountModal(true)} />

      {/* Paper Trading Section */}
      <PaperTradingManager />

      {/* Auto-Buy BTC Section */}
      <AutoBuySettings accounts={accounts} />

      {/* AI Providers Section */}
      <AIProvidersManager />

      {/* Database Maintenance Section */}
      <div className="card p-6">
        <div className="flex items-center space-x-3 mb-6">
          <Database className="w-6 h-6 text-orange-400" />
          <h3 className="text-xl font-semibold">Database Maintenance</h3>
        </div>

        <form onSubmit={handleLogRetentionChange} className="space-y-4">
          <div>
            <div className="flex items-center space-x-2 mb-2">
              <Trash2 className="w-5 h-5 text-slate-400" />
              <label htmlFor="logRetentionDays" className="block text-sm font-medium text-slate-300">
                Decision Log Retention Period
              </label>
            </div>
            <div className="flex items-center space-x-4">
              <input
                id="logRetentionDays"
                type="number"
                min="1"
                max="365"
                value={logRetentionDays}
                onChange={(e) => setLogRetentionDays(parseInt(e.target.value) || 1)}
                onBlur={() => {
                  if (logRetentionDays === '' as any || isNaN(logRetentionDays)) {
                    setLogRetentionDays(14)
                  }
                }}
                className="w-32 px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
              />
              <span className="text-slate-400">days</span>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Automatically clean up AI and indicator decision logs for closed positions older than this many days.
              Logs for open positions are never deleted. (Default: 14 days / 2 weeks)
            </p>
          </div>

          {/* Success Message */}
          {retentionSuccess && (
            <div className="p-4 bg-green-500/10 border border-green-500/50 rounded-lg flex items-center space-x-3">
              <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
              <p className="text-green-400 text-sm">Log retention period saved successfully!</p>
            </div>
          )}

          {/* Error Message */}
          {retentionError && (
            <div className="p-4 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-3">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
              <p className="text-red-400 text-sm">{retentionError}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={isSavingRetention}
            className="px-6 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 focus:ring-offset-slate-800"
          >
            {isSavingRetention ? 'Saving...' : 'Save Retention Setting'}
          </button>
        </form>
      </div>

      {/* Add Account Modal */}
      <AddAccountModal
        isOpen={showAddAccountModal}
        onClose={() => setShowAddAccountModal(false)}
      />
    </div>
  )
}
