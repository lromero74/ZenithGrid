/**
 * Email Verification Handler
 *
 * Shown when user clicks /verify-email?token=xxx from their email.
 * Calls the verify endpoint and shows success/error.
 */

import { useState, useEffect } from 'react'
import { Truck, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useBrand } from '../contexts/BrandContext'

interface VerifyEmailProps {
  token: string
  onComplete: () => void
}

export function VerifyEmail({ token, onComplete }: VerifyEmailProps) {
  const { verifyEmail } = useAuth()
  const { brand } = useBrand()
  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const doVerify = async () => {
      try {
        await verifyEmail(token)
        if (!cancelled) setStatus('success')
      } catch (err) {
        if (!cancelled) {
          setStatus('error')
          setError(err instanceof Error ? err.message : 'Verification failed')
        }
      }
    }

    doVerify()
    return () => { cancelled = true }
  }, [token, verifyEmail])

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

      <div className="w-full max-w-md bg-slate-800/80 backdrop-blur-sm rounded-xl shadow-2xl border border-slate-700/50 p-8 text-center">
        {status === 'verifying' && (
          <>
            <div className="flex justify-center mb-4">
              <RefreshCw className="w-12 h-12 text-blue-400 animate-spin" />
            </div>
            <h2 className="text-xl font-semibold text-white mb-2">Verifying Email...</h2>
            <p className="text-slate-400 text-sm">Please wait while we verify your email address.</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="flex justify-center mb-4">
              <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center">
                <CheckCircle className="w-8 h-8 text-green-400" />
              </div>
            </div>
            <h2 className="text-xl font-semibold text-white mb-2">Email Verified!</h2>
            <p className="text-slate-400 text-sm mb-6">
              Your email has been verified. You can now access the platform.
            </p>
            <button
              onClick={onComplete}
              className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
            >
              Continue
            </button>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="flex justify-center mb-4">
              <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
                <AlertCircle className="w-8 h-8 text-red-400" />
              </div>
            </div>
            <h2 className="text-xl font-semibold text-white mb-2">Verification Failed</h2>
            <p className="text-slate-400 text-sm mb-6">
              {error || 'The verification link may be expired or invalid.'}
            </p>
            <button
              onClick={onComplete}
              className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
            >
              Continue
            </button>
          </>
        )}
      </div>

      <p className="mt-8 text-sm text-slate-500">
        &copy; {new Date().getFullYear()} Romero Tech Solutions
      </p>
    </div>
  )
}
