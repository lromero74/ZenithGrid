/**
 * DemoLogin - Auto-login for demo accounts via URL shortcut.
 *
 * Renders at /demo_usd, /demo_btc, /demo_both.
 * Calls login(username, username) on mount, then redirects to /.
 */

import { useState, useEffect, useRef } from 'react'
import { Navigate } from 'react-router-dom'
import { Truck, AlertCircle } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useBrand } from '../contexts/BrandContext'

interface DemoLoginProps {
  username: string
}

export function DemoLogin({ username }: DemoLoginProps) {
  const { isAuthenticated, login } = useAuth()
  const { brand } = useBrand()
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const attempted = useRef(false)

  useEffect(() => {
    if (isAuthenticated || attempted.current) return
    attempted.current = true

    const doLogin = async () => {
      try {
        await login(username, username)
      } catch (err: unknown) {
        const status = (err as any)?.status as
          number | undefined
        const msg = err instanceof Error
          ? err.message : 'Login failed'

        if (
          status === 403
          && msg.includes('simultaneous sessions')
        ) {
          setError(
            `${username} already has the maximum `
            + 'number of simultaneous sessions. '
            + 'Please try again later.'
          )
        } else if (status === 429) {
          const m = msg.match(/(\d+)\s*seconds?/)
          if (m) {
            const mins = Math.ceil(Number(m[1]) / 60)
            setError(
              `${username} session cooldown active. `
              + `Try again in ${mins} minute`
              + `${mins !== 1 ? 's' : ''}.`
            )
          } else {
            setError(msg)
          }
        } else {
          setError(msg)
        }
      } finally {
        setIsLoading(false)
      }
    }

    doLogin()
  }, [isAuthenticated, login, username])

  // After successful login, redirect to dashboard
  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center px-4">
      <div className="flex items-center space-x-3 mb-8">
        <Truck className="w-10 h-10 text-theme-primary" />
        <h1 className="text-3xl font-bold text-white">
          {brand.loginTitle}
        </h1>
      </div>

      <div className="w-full max-w-sm bg-slate-800/80 backdrop-blur-sm rounded-xl shadow-2xl border border-slate-700/50 p-8">
        {error ? (
          <div className="space-y-4">
            <div className="p-4 bg-red-500/10 border border-red-500/50 rounded-lg flex items-start space-x-3">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-red-400 text-sm">
                {error}
              </p>
            </div>
            <a
              href="/"
              className="block w-full py-3 text-center bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
            >
              Go to Login
            </a>
          </div>
        ) : isLoading ? (
          <div className="text-center space-y-4">
            <svg
              className="animate-spin h-8 w-8 mx-auto text-blue-400"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25" cx="12" cy="12"
                r="10" stroke="currentColor"
                strokeWidth="4" fill="none"
              />
              <path
                className="opacity-75" fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <p className="text-slate-400 text-sm">
              Signing in as{' '}
              <span className="text-white font-medium">
                {username}
              </span>
              ...
            </p>
          </div>
        ) : null}
      </div>
    </div>
  )
}
