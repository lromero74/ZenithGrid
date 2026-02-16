import { useState, FormEvent, useEffect, useCallback } from 'react'
import { User, Lock, CheckCircle, AlertCircle, Database, Trash2, Shield, ShieldCheck, ShieldOff, Copy, CheckSquare, Monitor, MapPin, Clock, X as XIcon } from 'lucide-react'
import { AccountsManagement } from '../components/AccountsManagement'
import { PaperTradingManager } from '../components/PaperTradingManager'
import { AddAccountModal } from '../components/AddAccountModal'
import { AIProvidersManager } from '../components/AIProvidersManager'
import { AutoBuySettings } from '../components/AutoBuySettings'
import { BlacklistManager } from '../components/BlacklistManager'
import { useAccount } from '../contexts/AccountContext'
import { useAuth } from '../contexts/AuthContext'
import { settingsApi } from '../services/api'

export default function Settings() {
  const [showAddAccountModal, setShowAddAccountModal] = useState(false)
  const { user, changePassword, getAccessToken, updateUser } = useAuth()
  const { accounts, selectedAccount } = useAccount()

  // Check if paper trading is currently active
  const isPaperTradingActive = Boolean(selectedAccount?.is_paper_trading)

  // Password change state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordSuccess, setPasswordSuccess] = useState(false)
  const [isChangingPassword, setIsChangingPassword] = useState(false)

  // MFA state
  const [mfaSetupStep, setMfaSetupStep] = useState<'idle' | 'loading' | 'scanning' | 'verifying'>('idle')
  const [mfaQrCode, setMfaQrCode] = useState<string | null>(null)
  const [mfaSecretKey, setMfaSecretKey] = useState<string | null>(null)
  const [mfaSetupCode, setMfaSetupCode] = useState('')
  const [mfaSetupError, setMfaSetupError] = useState<string | null>(null)
  const [mfaSetupSuccess, setMfaSetupSuccess] = useState(false)
  const [mfaDisablePassword, setMfaDisablePassword] = useState('')
  const [mfaDisableCode, setMfaDisableCode] = useState('')
  const [mfaDisableError, setMfaDisableError] = useState<string | null>(null)
  const [isDisablingMFA, setIsDisablingMFA] = useState(false)
  const [showDisableMFA, setShowDisableMFA] = useState(false)
  const [secretCopied, setSecretCopied] = useState(false)

  // Trusted devices state
  interface TrustedDeviceInfo {
    id: number
    device_name: string | null
    ip_address: string | null
    location: string | null
    created_at: string
    expires_at: string
  }
  const [trustedDevices, setTrustedDevices] = useState<TrustedDeviceInfo[]>([])
  const [isLoadingDevices, setIsLoadingDevices] = useState(false)
  const [deviceError, setDeviceError] = useState<string | null>(null)

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

  // MFA Setup: Start
  const handleMFASetup = async () => {
    setMfaSetupStep('loading')
    setMfaSetupError(null)
    setMfaSetupSuccess(false)

    try {
      const token = getAccessToken()
      const response = await fetch('/api/auth/mfa/setup', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to start MFA setup')
      }

      const data = await response.json()
      setMfaQrCode(data.qr_code_base64)
      setMfaSecretKey(data.secret_key)
      setMfaSetupStep('scanning')
    } catch (err) {
      setMfaSetupError(err instanceof Error ? err.message : 'Failed to start MFA setup')
      setMfaSetupStep('idle')
    }
  }

  // MFA Setup: Verify first code
  const handleMFAVerifySetup = async (e: FormEvent) => {
    e.preventDefault()
    setMfaSetupError(null)
    setMfaSetupStep('verifying')

    try {
      const token = getAccessToken()
      const response = await fetch('/api/auth/mfa/verify-setup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          secret_key: mfaSecretKey,
          totp_code: mfaSetupCode,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Verification failed')
      }

      const data = await response.json()
      updateUser(data.user)
      setMfaSetupSuccess(true)
      setMfaSetupStep('idle')
      setMfaQrCode(null)
      setMfaSecretKey(null)
      setMfaSetupCode('')
      setTimeout(() => setMfaSetupSuccess(false), 5000)
    } catch (err) {
      setMfaSetupError(err instanceof Error ? err.message : 'Verification failed')
      setMfaSetupStep('scanning')
      setMfaSetupCode('')
    }
  }

  // MFA Disable
  const handleMFADisable = async (e: FormEvent) => {
    e.preventDefault()
    setMfaDisableError(null)
    setIsDisablingMFA(true)

    try {
      const token = getAccessToken()
      const response = await fetch('/api/auth/mfa/disable', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          password: mfaDisablePassword,
          totp_code: mfaDisableCode,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to disable MFA')
      }

      const data = await response.json()
      updateUser(data.user)
      setShowDisableMFA(false)
      setMfaDisablePassword('')
      setMfaDisableCode('')
      setMfaSetupSuccess(false)
    } catch (err) {
      setMfaDisableError(err instanceof Error ? err.message : 'Failed to disable MFA')
    } finally {
      setIsDisablingMFA(false)
    }
  }

  const cancelMFASetup = () => {
    setMfaSetupStep('idle')
    setMfaQrCode(null)
    setMfaSecretKey(null)
    setMfaSetupCode('')
    setMfaSetupError(null)
  }

  const copySecretKey = async () => {
    if (mfaSecretKey) {
      await navigator.clipboard.writeText(mfaSecretKey)
      setSecretCopied(true)
      setTimeout(() => setSecretCopied(false), 2000)
    }
  }

  // Load trusted devices
  const loadTrustedDevices = useCallback(async () => {
    const token = getAccessToken()
    if (!token) return
    setIsLoadingDevices(true)
    setDeviceError(null)
    try {
      const response = await fetch('/api/auth/mfa/devices', {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setTrustedDevices(await response.json())
      }
    } catch (err) {
      setDeviceError('Failed to load trusted devices')
    } finally {
      setIsLoadingDevices(false)
    }
  }, [getAccessToken])

  // Load devices when MFA is enabled
  useEffect(() => {
    if (user?.mfa_enabled) {
      loadTrustedDevices()
    }
  }, [user?.mfa_enabled, loadTrustedDevices])

  const revokeDevice = async (deviceId: number) => {
    const token = getAccessToken()
    if (!token) return
    try {
      const response = await fetch(`/api/auth/mfa/devices/${deviceId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setTrustedDevices(prev => prev.filter(d => d.id !== deviceId))
      }
    } catch {
      setDeviceError('Failed to revoke device')
    }
  }

  const revokeAllDevices = async () => {
    const token = getAccessToken()
    if (!token) return
    try {
      const response = await fetch('/api/auth/mfa/devices', {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (response.ok) {
        setTrustedDevices([])
        // Also clear local device trust token
        localStorage.removeItem('auth_device_trust_token')
      }
    } catch {
      setDeviceError('Failed to revoke devices')
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
    })
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

        {/* Two-Factor Authentication Section */}
        <div className="border-t border-slate-700 pt-6">
          <div className="flex items-center space-x-2 mb-4">
            <Shield className="w-5 h-5 text-slate-400" />
            <h4 className="text-lg font-medium">Two-Factor Authentication</h4>
          </div>

          {/* MFA Success Message */}
          {mfaSetupSuccess && (
            <div className="mb-4 p-4 bg-green-500/10 border border-green-500/50 rounded-lg flex items-center space-x-3">
              <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
              <p className="text-green-400 text-sm">Two-factor authentication enabled successfully!</p>
            </div>
          )}

          {user?.mfa_enabled ? (
            /* MFA is enabled — show status + disable option */
            <div>
              <div className="flex items-center space-x-3 mb-4 p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
                <ShieldCheck className="w-6 h-6 text-green-400 flex-shrink-0" />
                <div>
                  <p className="text-green-400 font-medium">2FA is enabled</p>
                  <p className="text-slate-400 text-sm">Your account is protected with an authenticator app.</p>
                </div>
              </div>

              {!showDisableMFA ? (
                <button
                  onClick={() => { setShowDisableMFA(true); setMfaDisableError(null) }}
                  className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30 rounded-lg transition-colors text-sm"
                >
                  Disable 2FA
                </button>
              ) : (
                <div className="mt-4 p-4 bg-slate-700/50 rounded-lg border border-slate-600">
                  <p className="text-sm text-slate-300 mb-4">
                    To disable two-factor authentication, enter your password and a code from your authenticator app.
                  </p>

                  {mfaDisableError && (
                    <div className="mb-4 p-3 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-2">
                      <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                      <p className="text-red-400 text-sm">{mfaDisableError}</p>
                    </div>
                  )}

                  <form onSubmit={handleMFADisable} className="space-y-3">
                    <input
                      type="password"
                      value={mfaDisablePassword}
                      onChange={(e) => setMfaDisablePassword(e.target.value)}
                      required
                      autoComplete="current-password"
                      placeholder="Current password"
                      className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                    />
                    <input
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]{6}"
                      maxLength={6}
                      value={mfaDisableCode}
                      onChange={(e) => setMfaDisableCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      required
                      autoComplete="one-time-code"
                      placeholder="6-digit authenticator code"
                      className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent font-mono"
                    />
                    <div className="flex space-x-3">
                      <button
                        type="submit"
                        disabled={isDisablingMFA || !mfaDisablePassword || mfaDisableCode.length !== 6}
                        className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors text-sm"
                      >
                        {isDisablingMFA ? 'Disabling...' : 'Confirm Disable'}
                      </button>
                      <button
                        type="button"
                        onClick={() => { setShowDisableMFA(false); setMfaDisableError(null); setMfaDisablePassword(''); setMfaDisableCode('') }}
                        className="px-4 py-2 text-slate-400 hover:text-white transition-colors text-sm"
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                </div>
              )}
            </div>
          ) : mfaSetupStep === 'idle' ? (
            /* MFA not enabled, not setting up — show enable button */
            <div>
              <div className="flex items-center space-x-3 mb-4 p-4 bg-slate-700/50 border border-slate-600 rounded-lg">
                <ShieldOff className="w-6 h-6 text-slate-400 flex-shrink-0" />
                <div>
                  <p className="text-slate-300 font-medium">2FA is not enabled</p>
                  <p className="text-slate-400 text-sm">Add an extra layer of security with an authenticator app.</p>
                </div>
              </div>

              {mfaSetupError && (
                <div className="mb-4 p-3 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-2">
                  <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                  <p className="text-red-400 text-sm">{mfaSetupError}</p>
                </div>
              )}

              <button
                onClick={handleMFASetup}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors text-sm"
              >
                Enable 2FA
              </button>
            </div>
          ) : mfaSetupStep === 'loading' ? (
            /* Loading setup */
            <div className="flex items-center space-x-3 p-4">
              <svg className="animate-spin h-5 w-5 text-blue-400" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span className="text-slate-300">Setting up two-factor authentication...</span>
            </div>
          ) : (
            /* Scanning QR / Verifying setup code */
            <div className="space-y-4">
              <p className="text-sm text-slate-300">
                Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.):
              </p>

              {/* QR Code */}
              {mfaQrCode && (
                <div className="flex justify-center p-4 bg-white rounded-lg w-fit mx-auto">
                  <img
                    src={`data:image/png;base64,${mfaQrCode}`}
                    alt="MFA QR Code"
                    className="w-48 h-48"
                  />
                </div>
              )}

              {/* Manual Entry Key */}
              {mfaSecretKey && (
                <div className="p-3 bg-slate-700/50 rounded-lg border border-slate-600">
                  <p className="text-xs text-slate-400 mb-1">Can't scan? Enter this key manually:</p>
                  <div className="flex items-center space-x-2">
                    <code className="text-sm text-blue-300 font-mono tracking-wider flex-1 break-all">
                      {mfaSecretKey}
                    </code>
                    <button
                      onClick={copySecretKey}
                      className="p-1.5 text-slate-400 hover:text-white transition-colors flex-shrink-0"
                      title="Copy to clipboard"
                    >
                      {secretCopied ? <CheckSquare className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              )}

              {/* Verify Setup Code */}
              {mfaSetupError && (
                <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-2">
                  <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                  <p className="text-red-400 text-sm">{mfaSetupError}</p>
                </div>
              )}

              <form onSubmit={handleMFAVerifySetup} className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Enter the 6-digit code from your app to verify:
                  </label>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={mfaSetupCode}
                    onChange={(e) => setMfaSetupCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    required
                    autoComplete="one-time-code"
                    autoFocus
                    placeholder="000000"
                    className="w-full max-w-xs px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-center text-lg tracking-[0.3em] font-mono placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
                <div className="flex space-x-3">
                  <button
                    type="submit"
                    disabled={mfaSetupStep === 'verifying' || mfaSetupCode.length !== 6}
                    className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors text-sm"
                  >
                    {mfaSetupStep === 'verifying' ? 'Verifying...' : 'Verify & Enable'}
                  </button>
                  <button
                    type="button"
                    onClick={cancelMFASetup}
                    className="px-4 py-2 text-slate-400 hover:text-white transition-colors text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Trusted Devices — only show when MFA is enabled */}
          {user?.mfa_enabled && (
            <div className="mt-6 pt-4 border-t border-slate-600/50">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center space-x-2">
                  <Monitor className="w-4 h-4 text-slate-400" />
                  <h5 className="text-sm font-medium text-slate-300">Trusted Devices</h5>
                </div>
                {trustedDevices.length > 0 && (
                  <button
                    onClick={revokeAllDevices}
                    className="text-xs text-red-400 hover:text-red-300 transition-colors"
                  >
                    Revoke all
                  </button>
                )}
              </div>

              {deviceError && (
                <p className="text-xs text-red-400 mb-2">{deviceError}</p>
              )}

              {isLoadingDevices ? (
                <p className="text-xs text-slate-400">Loading devices...</p>
              ) : trustedDevices.length === 0 ? (
                <p className="text-xs text-slate-500">No trusted devices. Check "Remember this device" during MFA login to add one.</p>
              ) : (
                <div className="space-y-2">
                  {trustedDevices.map(device => (
                    <div key={device.id} className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg border border-slate-600/50">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center space-x-2">
                          <Monitor className="w-4 h-4 text-blue-400 flex-shrink-0" />
                          <span className="text-sm text-white truncate">{device.device_name || 'Unknown Device'}</span>
                        </div>
                        <div className="flex items-center space-x-3 mt-1 ml-6">
                          {device.location && (
                            <span className="flex items-center space-x-1 text-xs text-slate-400">
                              <MapPin className="w-3 h-3" />
                              <span>{device.location}</span>
                            </span>
                          )}
                          <span className="flex items-center space-x-1 text-xs text-slate-400">
                            <Clock className="w-3 h-3" />
                            <span>Added {formatDate(device.created_at)}</span>
                          </span>
                          <span className="text-xs text-slate-500">
                            Expires {formatDate(device.expires_at)}
                          </span>
                        </div>
                      </div>
                      <button
                        onClick={() => revokeDevice(device.id)}
                        className="ml-2 p-1.5 text-slate-400 hover:text-red-400 transition-colors flex-shrink-0"
                        title="Revoke device trust"
                      >
                        <XIcon className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Accounts Management Section - Hidden when paper trading is active */}
      {!isPaperTradingActive && (
        <AccountsManagement onAddAccount={() => setShowAddAccountModal(true)} />
      )}

      {/* Paper Trading Section */}
      <PaperTradingManager />

      {/* Auto-Buy BTC Section - Hidden when paper trading is active */}
      {!isPaperTradingActive && (
        <AutoBuySettings accounts={accounts} />
      )}

      {/* Coin Categorization Section - Always visible (informational) */}
      <BlacklistManager />

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
