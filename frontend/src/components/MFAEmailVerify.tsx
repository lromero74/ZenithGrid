/**
 * MFA Email Link Verification Component
 *
 * Handles the /mfa-email-verify?token=... route when a user clicks
 * the "Verify Login" link in their MFA email. Auto-verifies the token
 * and completes login.
 */

import { useState, useEffect } from 'react'
import { Shield, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

interface MFAEmailVerifyProps {
  token: string
  onComplete: () => void
}

export default function MFAEmailVerify({ token, onComplete }: MFAEmailVerifyProps) {
  const { verifyMFAEmailLink } = useAuth()
  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying')
  const [error, setError] = useState<string | null>(null)

  // Auto-verify on mount
  useEffect(() => {
    const verify = async () => {
      try {
        await verifyMFAEmailLink(token, false)
        setStatus('success')
        // Auto-navigate to dashboard after brief success message
        setTimeout(() => onComplete(), 1500)
      } catch (err) {
        setStatus('error')
        setError(err instanceof Error ? err.message : 'Verification failed')
      }
    }

    verify()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-md bg-slate-800/80 backdrop-blur-sm rounded-xl shadow-2xl border border-slate-700/50 p-8">
        <div className="flex items-center space-x-3 mb-6">
          <Shield className="w-7 h-7 text-blue-400" />
          <h2 className="text-2xl font-semibold text-white">Login Verification</h2>
        </div>

        {status === 'verifying' && (
          <div className="text-center py-8">
            <Loader2 className="w-12 h-12 text-blue-400 animate-spin mx-auto mb-4" />
            <p className="text-slate-300">Verifying your login...</p>
          </div>
        )}

        {status === 'success' && (
          <div className="text-center py-8">
            <CheckCircle className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
            <p className="text-emerald-300 font-medium mb-1">Login verified!</p>
            <p className="text-slate-400 text-sm">Redirecting to dashboard...</p>
          </div>
        )}

        {status === 'error' && (
          <div className="space-y-6">
            <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-6 text-center">
              <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-3" />
              <p className="text-red-300 font-medium mb-1">Verification failed</p>
              <p className="text-slate-400 text-sm">{error || 'The link may have expired or already been used.'}</p>
            </div>

            <a
              href="/"
              className="block w-full py-3 px-4 bg-slate-700 hover:bg-slate-600 text-white font-medium rounded-lg transition-colors text-center"
            >
              Back to Login
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
