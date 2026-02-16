/**
 * Email Verification Pending Screen
 *
 * Shown when user is authenticated but email_verified=false.
 * User can either click the link in their email OR enter the 6-digit code here.
 */

import { useState, useRef, FormEvent } from 'react'
import { Activity, Mail, RefreshCw, LogOut, CheckCircle, AlertCircle } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

export function EmailVerificationPending() {
  const { user, logout, resendVerification, verifyEmailCode } = useAuth()
  const [resending, setResending] = useState(false)
  const [resent, setResent] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Code entry state
  const [code, setCode] = useState('')
  const [verifying, setVerifying] = useState(false)
  const codeInputRef = useRef<HTMLInputElement>(null)

  const handleResend = async () => {
    setResending(true)
    setError(null)
    setResent(false)
    try {
      await resendVerification()
      setResent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resend')
    } finally {
      setResending(false)
    }
  }

  const handleCodeSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (code.length !== 6) return

    setVerifying(true)
    setError(null)
    try {
      await verifyEmailCode(code)
      // Success — AuthContext updates user, App re-renders past this gate
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid code')
      setCode('')
      codeInputRef.current?.focus()
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center px-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-indigo-500/5 rounded-full blur-3xl" />
      </div>

      <div className="flex items-center space-x-3 mb-8">
        <Activity className="w-9 h-9 text-blue-500" />
        <h1 className="text-3xl font-bold text-white tracking-tight">Zenith Grid</h1>
      </div>

      <div className="w-full max-w-md bg-slate-800/80 backdrop-blur-sm rounded-xl shadow-2xl border border-slate-700/50 p-8 text-center">
        <div className="flex justify-center mb-4">
          <div className="w-16 h-16 rounded-full bg-blue-500/10 flex items-center justify-center">
            <Mail className="w-8 h-8 text-blue-400" />
          </div>
        </div>

        <h2 className="text-xl font-semibold text-white mb-2">Verify Your Email</h2>
        <p className="text-slate-400 text-sm mb-6">
          We sent a verification email to{' '}
          <span className="text-slate-200 font-medium">{user?.email}</span>.
          <br />
          Click the link in the email, or enter the 6-digit code below.
        </p>

        {resent && (
          <div className="mb-4 p-3 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center justify-center space-x-2">
            <CheckCircle className="w-4 h-4 text-green-400" />
            <span className="text-green-400 text-sm">Verification email resent!</span>
          </div>
        )}

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center space-x-2 justify-center">
            <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <span className="text-red-400 text-sm">{error}</span>
          </div>
        )}

        {/* Code entry form */}
        <form onSubmit={handleCodeSubmit} className="mb-6">
          <label htmlFor="verifyCode" className="block text-sm font-medium text-slate-300 mb-2 text-left">
            Verification Code
          </label>
          <div className="flex space-x-3">
            <input
              ref={codeInputRef}
              id="verifyCode"
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              autoComplete="one-time-code"
              placeholder="000000"
              className="flex-1 px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white text-center text-xl tracking-[0.4em] font-mono placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <button
              type="submit"
              disabled={verifying || code.length !== 6}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
            >
              {verifying ? (
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              ) : (
                'Verify'
              )}
            </button>
          </div>
        </form>

        <div className="space-y-3">
          <button
            onClick={handleResend}
            disabled={resending}
            className="w-full py-2.5 px-4 text-slate-300 hover:text-white hover:bg-slate-700 border border-slate-600 rounded-lg transition-colors flex items-center justify-center space-x-2 text-sm"
          >
            {resending ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Sending...</span>
              </>
            ) : (
              <>
                <RefreshCw className="w-4 h-4" />
                <span>Resend Verification Email</span>
              </>
            )}
          </button>

          <button
            onClick={logout}
            className="w-full py-2.5 px-4 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors flex items-center justify-center space-x-2 text-sm"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign Out</span>
          </button>
        </div>

        <p className="text-slate-500 text-xs mt-6">
          Wrong email? Sign out and create a new account.
        </p>
      </div>

      <p className="mt-8 text-sm text-slate-500">
        &copy; {new Date().getFullYear()} Romero Tech Solutions
      </p>
    </div>
  )
}
