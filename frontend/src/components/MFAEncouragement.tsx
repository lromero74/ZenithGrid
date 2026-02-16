/**
 * MFA Encouragement Screen
 *
 * Shown ONE TIME after email verification, before dashboard access.
 * Encourages users to set up MFA for their trading account.
 * Once dismissed, stores flag in localStorage and never shows again.
 */

import { Shield, ArrowRight, Clock } from 'lucide-react'
import { Activity } from 'lucide-react'

interface MFAEncouragementProps {
  onSetupMFA: () => void
  onSkip: () => void
}

export const MFA_DISMISSED_KEY = 'mfa_encouragement_dismissed'

export function MFAEncouragement({ onSetupMFA, onSkip }: MFAEncouragementProps) {
  const handleSkip = () => {
    localStorage.setItem(MFA_DISMISSED_KEY, 'true')
    onSkip()
  }

  const handleSetup = () => {
    localStorage.setItem(MFA_DISMISSED_KEY, 'true')
    onSetupMFA()
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
            <Shield className="w-8 h-8 text-blue-400" />
          </div>
        </div>

        <h2 className="text-xl font-semibold text-white mb-2">Secure Your Account</h2>
        <p className="text-slate-400 text-sm mb-6">
          Your account manages real trading activity. We strongly recommend
          enabling two-factor authentication (MFA) to protect your account.
          You can use an authenticator app or email verification.
        </p>

        <div className="bg-slate-700/50 rounded-lg p-4 mb-6 text-left">
          <p className="text-slate-300 text-sm font-medium mb-2">MFA options:</p>
          <ul className="space-y-1.5 text-slate-400 text-sm">
            <li className="flex items-start space-x-2">
              <span className="text-green-400 mt-0.5">&#10003;</span>
              <span>Authenticator app (Google Authenticator, Authy, etc.)</span>
            </li>
            <li className="flex items-start space-x-2">
              <span className="text-green-400 mt-0.5">&#10003;</span>
              <span>Email verification code and link</span>
            </li>
            <li className="flex items-start space-x-2">
              <span className="text-green-400 mt-0.5">&#10003;</span>
              <span>Enable one or both — only one needs to succeed at login</span>
            </li>
            <li className="flex items-start space-x-2">
              <span className="text-green-400 mt-0.5">&#10003;</span>
              <span>Option to "Remember this device" for 30-day convenience</span>
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          <button
            onClick={handleSetup}
            className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors flex items-center justify-center space-x-2"
          >
            <Shield className="w-4 h-4" />
            <span>Set Up MFA Now</span>
            <ArrowRight className="w-4 h-4" />
          </button>

          <button
            onClick={handleSkip}
            className="w-full py-3 px-4 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors flex items-center justify-center space-x-2"
          >
            <Clock className="w-4 h-4" />
            <span>Maybe Later</span>
          </button>
        </div>
      </div>
    </div>
  )
}
