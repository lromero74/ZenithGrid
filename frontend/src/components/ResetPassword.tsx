/**
 * Reset Password Page
 *
 * Shown when user clicks the password reset link from their email.
 * Route: /reset-password?token=xxx
 */

import { useState, FormEvent } from 'react'
import { Truck, Lock, AlertCircle, CheckCircle, Check } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useBrand } from '../contexts/BrandContext'
import { PasswordStrengthMeter, isPasswordValid } from './PasswordStrengthMeter'

interface ResetPasswordProps {
  token: string
  onComplete: () => void
}

export function ResetPassword({ token, onComplete }: ResetPasswordProps) {
  const { resetPassword } = useAuth()
  const { brand } = useBrand()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const passwordsMatch = password.length > 0 && password === confirmPassword
  const canSubmit = isPasswordValid(password) && passwordsMatch && !isSubmitting

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return

    setError(null)
    setIsSubmitting(true)

    try {
      await resetPassword(token, password)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset password')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center px-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-indigo-500/5 rounded-full blur-3xl" />
      </div>

      <div className="flex items-center space-x-3 mb-8">
        <Truck className="w-9 h-9 text-theme-primary" />
        <h1 className="text-3xl font-bold text-white tracking-tight">{brand.shortName}</h1>
      </div>

      <div className="w-full max-w-md bg-slate-800/80 backdrop-blur-sm rounded-xl shadow-2xl border border-slate-700/50 p-8">
        {success ? (
          <div className="text-center py-4">
            <div className="flex justify-center mb-4">
              <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center">
                <CheckCircle className="w-8 h-8 text-green-400" />
              </div>
            </div>
            <h2 className="text-xl font-semibold text-white mb-2">Password Reset!</h2>
            <p className="text-slate-400 text-sm mb-6">
              Your password has been updated. Please sign in with your new password.
            </p>
            <button
              onClick={onComplete}
              className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
            >
              Go to Login
            </button>
          </div>
        ) : (
          <>
            <h2 className="text-2xl font-semibold text-white mb-2 text-center">Set New Password</h2>
            <p className="text-slate-400 text-sm mb-6 text-center">
              Choose a strong password for your account.
            </p>

            {error && (
              <div className="mb-4 p-3 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <span className="text-red-400 text-sm">{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label htmlFor="newPassword" className="block text-sm font-medium text-slate-300 mb-2">
                  New Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    id="newPassword"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoFocus
                    autoComplete="new-password"
                    placeholder="Minimum 8 characters"
                    className={`w-full pl-10 pr-4 py-3 bg-slate-700 border rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:border-transparent transition-colors ${
                      passwordsMatch
                        ? 'border-green-500 focus:ring-green-500 ring-1 ring-green-500/50'
                        : 'border-slate-600 focus:ring-blue-500'
                    }`}
                  />
                </div>
                <PasswordStrengthMeter password={password} />
              </div>

              <div>
                <label htmlFor="confirmNewPassword" className="block text-sm font-medium text-slate-300 mb-2">
                  Confirm New Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    id="confirmNewPassword"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    placeholder="Re-enter your password"
                    className={`w-full pl-10 pr-12 py-3 bg-slate-700 border rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:border-transparent transition-colors ${
                      confirmPassword && passwordsMatch
                        ? 'border-green-500 focus:ring-green-500 ring-1 ring-green-500/50'
                        : confirmPassword && !passwordsMatch
                          ? 'border-red-500 focus:ring-red-500 ring-1 ring-red-500/50'
                          : 'border-slate-600 focus:ring-blue-500'
                    }`}
                  />
                  {confirmPassword.length > 0 && (
                    <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
                      {passwordsMatch ? (
                        <Check className="w-5 h-5 text-green-400" />
                      ) : (
                        <span className="text-xs text-red-400">No match</span>
                      )}
                    </div>
                  )}
                </div>
              </div>

              <button
                type="submit"
                disabled={!canSubmit}
                className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
              >
                {isSubmitting ? (
                  <span className="flex items-center justify-center space-x-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <span>Resetting...</span>
                  </span>
                ) : (
                  'Reset Password'
                )}
              </button>
            </form>
          </>
        )}
      </div>

      <p className="mt-8 text-sm text-slate-500">
        &copy; {new Date().getFullYear()} Romero Tech Solutions
      </p>
    </div>
  )
}
