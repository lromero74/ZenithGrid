/**
 * AcceptInvite Page
 *
 * Route: /accept-invite?token={token}
 *
 * Flow:
 * 1. Read token from query string.
 * 2. If user is not authenticated → redirect to /login?next=<current URL>.
 * 3. Fetch preview from GET /api/invitations/preview/{token}.
 *    - 400 "different email address" → show auth-mismatch error with guidance.
 *    - Other 400 → show generic error (expired, revoked, etc.).
 * 4. Show preview card: account name, inviter, role offered.
 * 5. Accept → POST /api/invitations/{token}/accept → success screen.
 * 6. Decline → POST /api/invitations/{token}/decline → confirmation screen.
 */

import { useEffect, useState } from 'react'
import { CheckCircle, XCircle, AlertCircle, RefreshCw, UserCheck, Eye, LogIn } from 'lucide-react'
import { invitationsApi } from '../contexts/AccountContext'
import { useAuth } from '../contexts/AuthContext'

type PageState =
  | { status: 'loading' }
  | { status: 'unauthenticated'; redirectUrl: string }
  | { status: 'preview'; preview: InvitationPreview }
  | { status: 'accepting' }
  | { status: 'accepted'; role: string; accountName: string }
  | { status: 'declining' }
  | { status: 'declined' }
  | { status: 'error'; message: string; isEmailMismatch?: boolean }

interface InvitationPreview {
  invitation_id: number
  account_name: string
  invited_by: string
  role: 'manager' | 'observer'
  expires_at: string
}

export function AcceptInvite() {
  const { user, isLoading: authLoading } = useAuth()
  const [state, setState] = useState<PageState>({ status: 'loading' })

  const token = new URLSearchParams(window.location.search).get('token') || ''

  useEffect(() => {
    if (authLoading) return

    if (!user) {
      // Not logged in — redirect to login with ?next= so we return here after auth
      const next = encodeURIComponent(window.location.pathname + window.location.search)
      setState({ status: 'unauthenticated', redirectUrl: `/login?next=${next}` })
      return
    }

    if (!token) {
      setState({ status: 'error', message: 'No invitation token found in the URL.' })
      return
    }

    // Fetch preview
    setState({ status: 'loading' })
    invitationsApi.preview(token)
      .then((preview: InvitationPreview) => setState({ status: 'preview', preview }))
      .catch((err: Error) => {
        const message = err.message || 'Invalid invitation'
        const isEmailMismatch = message.toLowerCase().includes('different email')
        setState({ status: 'error', message, isEmailMismatch })
      })
  }, [token, user, authLoading])

  const handleAccept = async () => {
    setState({ status: 'accepting' })
    try {
      await invitationsApi.accept(token)
      const preview = (state as { status: 'preview'; preview: InvitationPreview }).preview
      setState({
        status: 'accepted',
        role: preview?.role || 'member',
        accountName: preview?.account_name || 'the account',
      })
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : 'Failed to accept invitation',
      })
    }
  }

  const handleDecline = async () => {
    setState({ status: 'declining' })
    try {
      await invitationsApi.decline(token)
      setState({ status: 'declined' })
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : 'Failed to decline invitation',
      })
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Brand header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-blue-400">Account Invitation</h1>
        </div>

        {state.status === 'loading' && (
          <div className="text-center">
            <RefreshCw className="w-10 h-10 text-blue-400 animate-spin mx-auto mb-4" />
            <p className="text-slate-400">Loading invitation details…</p>
          </div>
        )}

        {state.status === 'unauthenticated' && (
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 text-center">
            <LogIn className="w-10 h-10 text-blue-400 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-slate-100 mb-2">Sign in to Continue</h2>
            <p className="text-sm text-slate-400 mb-5">
              You need to be logged in as the invited email address to accept this invitation.
            </p>
            <a
              href={state.redirectUrl}
              className="inline-block w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg transition-colors text-sm text-center"
            >
              Sign In
            </a>
          </div>
        )}

        {state.status === 'preview' && (
          <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
            {/* Preview card */}
            <div className="p-6">
              <div className="flex items-center gap-3 mb-5">
                <div className="p-2.5 rounded-xl bg-violet-500/15">
                  {state.preview.role === 'manager'
                    ? <UserCheck className="w-6 h-6 text-violet-400" />
                    : <Eye className="w-6 h-6 text-violet-400" />
                  }
                </div>
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wider">You're invited as</p>
                  <p className="text-xl font-bold text-violet-300 capitalize">{state.preview.role}</p>
                </div>
              </div>

              <div className="space-y-3">
                <InfoRow label="Account" value={state.preview.account_name} />
                <InfoRow label="From" value={state.preview.invited_by} />
                <InfoRow
                  label="Access"
                  value={
                    state.preview.role === 'manager'
                      ? 'Manage bots, view positions, run reports'
                      : 'View balances, bots, positions (read-only)'
                  }
                />
                <InfoRow
                  label="Expires"
                  value={new Date(state.preview.expires_at).toLocaleDateString(undefined, {
                    month: 'long', day: 'numeric', year: 'numeric',
                  })}
                />
              </div>
            </div>

            <div className="border-t border-slate-700 p-4 bg-slate-900/30">
              <div className="flex gap-3">
                <button
                  onClick={handleDecline}
                  className="flex-1 py-2.5 text-sm font-medium text-slate-400 hover:text-red-400 border border-slate-600 hover:border-red-700/40 rounded-lg transition-colors"
                >
                  Decline
                </button>
                <button
                  onClick={handleAccept}
                  className="flex-1 py-2.5 text-sm font-medium text-white bg-violet-600 hover:bg-violet-500 rounded-lg transition-colors"
                >
                  Accept Invitation
                </button>
              </div>
            </div>
          </div>
        )}

        {(state.status === 'accepting' || state.status === 'declining') && (
          <div className="text-center">
            <RefreshCw className="w-10 h-10 text-violet-400 animate-spin mx-auto mb-4" />
            <p className="text-slate-400">
              {state.status === 'accepting' ? 'Accepting invitation…' : 'Declining invitation…'}
            </p>
          </div>
        )}

        {state.status === 'accepted' && (
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-8 text-center">
            <CheckCircle className="w-12 h-12 text-green-400 mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-slate-100 mb-2">You're in!</h2>
            <p className="text-sm text-slate-400 mb-6">
              You now have <span className="text-violet-300 font-medium capitalize">{state.role}</span> access
              to <span className="text-slate-200 font-medium">{state.accountName}</span>.
            </p>
            <a
              href="/"
              className="inline-block w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg transition-colors text-sm text-center"
            >
              Go to Dashboard
            </a>
          </div>
        )}

        {state.status === 'declined' && (
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-8 text-center">
            <XCircle className="w-10 h-10 text-slate-400 mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-slate-100 mb-2">Invitation Declined</h2>
            <p className="text-sm text-slate-400 mb-6">
              You've declined this invitation. No changes were made to your account.
            </p>
            <a
              href="/"
              className="inline-block w-full py-2.5 px-4 bg-slate-700 hover:bg-slate-600 text-slate-200 font-medium rounded-lg transition-colors text-sm text-center"
            >
              Back to Dashboard
            </a>
          </div>
        )}

        {state.status === 'error' && (
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-8 text-center">
            <AlertCircle className="w-10 h-10 text-red-400 mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-slate-100 mb-2">
              {state.isEmailMismatch ? 'Wrong Account' : 'Invalid Invitation'}
            </h2>
            <p className="text-sm text-slate-400 mb-2">{state.message}</p>
            {state.isEmailMismatch && (
              <p className="text-sm text-slate-500 mb-5">
                Please sign out and log in with the email address that received the invitation.
              </p>
            )}
            {!state.isEmailMismatch && (
              <p className="text-sm text-slate-500 mb-5">
                The invitation may have expired, been revoked, or already used.
              </p>
            )}
            <a
              href="/"
              className="inline-block w-full py-2.5 px-4 bg-slate-700 hover:bg-slate-600 text-slate-200 font-medium rounded-lg transition-colors text-sm text-center"
            >
              Back to Dashboard
            </a>
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// Helper
// =============================================================================

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-xs text-slate-500 uppercase tracking-wider pt-0.5 flex-shrink-0">{label}</span>
      <span className="text-sm text-slate-200 text-right">{value}</span>
    </div>
  )
}
