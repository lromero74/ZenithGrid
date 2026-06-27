/**
 * Authentication Context
 *
 * Context, types, and the useAuth hook for authentication state.
 * The AuthProvider component (and RequireAuth wrapper) live in AuthProvider.tsx.
 */

import { createContext, useContext } from 'react'

// Types
export interface User {
  id: number
  email: string
  display_name: string | null
  is_active: boolean
  is_superuser: boolean
  mfa_enabled: boolean
  mfa_email_enabled: boolean
  email_verified: boolean
  email_verified_at: string | null
  created_at: string
  last_login_at: string | null
  terms_accepted_at: string | null  // NULL = must accept terms before accessing dashboard
  last_seen_history_count: number
  last_seen_failed_count: number
  groups?: { id: number; name: string; description: string | null }[]
  permissions?: string[]
}

export interface SessionPolicy {
  session_timeout_minutes?: number | null
  auto_logout?: boolean | null
  max_simultaneous_sessions?: number | null
  max_sessions_per_ip?: number | null
  relogin_cooldown_minutes?: number | null
}

export interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  mfaPending: boolean  // True when MFA verification is needed
  mfaToken: string | null  // Short-lived token for MFA verification
  mfaMethods: string[]  // Available MFA methods (e.g. ["totp", "email_code", "email_link"])
  login: (email: string, password: string) => Promise<void>
  verifyMFA: (code: string, rememberDevice?: boolean) => Promise<void>
  verifyMFAEmailCode: (code: string, rememberDevice?: boolean) => Promise<void>
  verifyMFAEmailLink: (token: string, rememberDevice?: boolean) => Promise<void>
  resendMFAEmail: () => Promise<void>
  cancelMFA: () => void
  signup: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => void
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
  getAccessToken: () => string | null
  acceptTerms: () => Promise<void>
  updateUser: (user: User) => void  // Update user state (e.g., after MFA enable/disable)
  enableEmailMFA: (password: string) => Promise<void>
  disableEmailMFA: (password: string) => Promise<void>
  verifyEmail: (token: string) => Promise<void>
  verifyEmailCode: (code: string) => Promise<void>
  resendVerification: () => Promise<void>
  forgotPassword: (email: string) => Promise<void>
  resetPassword: (token: string, newPassword: string) => Promise<void>
  sessionPolicy: SessionPolicy | null
  sessionExpiresAt: string | null
  sessionExpiryCountdown: number | null
  showSessionLimitsPopup: boolean
  acknowledgeSessionLimits: () => void
}

// Create context with default values
export const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  mfaPending: false,
  mfaToken: null,
  mfaMethods: [],
  login: async () => {},
  verifyMFA: async (_code: string, _rememberDevice?: boolean) => {},
  verifyMFAEmailCode: async (_code: string, _rememberDevice?: boolean) => {},
  verifyMFAEmailLink: async (_token: string, _rememberDevice?: boolean) => {},
  resendMFAEmail: async () => {},
  cancelMFA: () => {},
  signup: async () => {},
  logout: () => {},
  changePassword: async () => {},
  getAccessToken: () => null,
  acceptTerms: async () => {},
  updateUser: () => {},
  enableEmailMFA: async () => {},
  disableEmailMFA: async () => {},
  verifyEmail: async () => {},
  verifyEmailCode: async () => {},
  resendVerification: async () => {},
  forgotPassword: async () => {},
  resetPassword: async () => {},
  sessionPolicy: null,
  sessionExpiresAt: null,
  sessionExpiryCountdown: null,
  showSessionLimitsPopup: false,
  acknowledgeSessionLimits: () => {},
})

// Hook for consuming auth context
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
