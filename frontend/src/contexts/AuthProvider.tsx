/**
 * AuthProvider — authentication provider and protected-route wrapper.
 *
 * Manages user authentication state, tokens, and login/logout functionality.
 * Provides automatic token refresh and persistent sessions via localStorage.
 * Supports TOTP MFA (two-factor authentication) challenge flow.
 */

import { useEffect, useState, useCallback, useMemo, ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { clearSessionQueryCache, installSessionQueryPersistence } from '../utils/sessionQueryPersistence'
import { markStartupMilestone } from '../utils/startupPerformance'
import { AuthContext, useAuth, AuthContextType, User, SessionPolicy } from './AuthContext'

interface LoginResponse {
  access_token: string | null
  refresh_token: string | null
  token_type: string
  expires_in: number | null
  user: User | null
  mfa_required: boolean
  mfa_token: string | null
  mfa_methods: string[] | null
  device_trust_token: string | null
  session_policy?: SessionPolicy | null
  session_expires_at?: string | null
}

interface TokenRefreshResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

// Storage keys
const STORAGE_KEYS = {
  ACCESS_TOKEN: 'auth_access_token',
  REFRESH_TOKEN: 'auth_refresh_token',
  USER: 'auth_user',
  TOKEN_EXPIRY: 'auth_token_expiry',
  DEVICE_TRUST_TOKEN: 'auth_device_trust_token',
}

// Session storage keys (survive page reload within same tab, but not browser close)
const SESSION_KEYS = {
  MFA_TOKEN: 'auth_mfa_token',
  MFA_METHODS: 'auth_mfa_methods',
}

// API base URL
const API_BASE = '/api/auth'

// Helper to check if token is expired
function isTokenExpired(expiryTime: number | null): boolean {
  if (!expiryTime) return true
  // Add 30 second buffer before actual expiry
  return Date.now() >= expiryTime - 30000
}

function getInitialAuthSnapshot(): { user: User | null; tokenExpiry: number | null; isLoading: boolean } {
  try {
    const storedUser = localStorage.getItem(STORAGE_KEYS.USER)
    const accessToken = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
    const expiry = parseInt(localStorage.getItem(STORAGE_KEYS.TOKEN_EXPIRY) || '0')

    if (storedUser && accessToken && !isTokenExpired(expiry)) {
      return { user: JSON.parse(storedUser), tokenExpiry: expiry, isLoading: false }
    }

    // Expired sessions must keep the loader while the refresh-token request runs.
    if (storedUser && accessToken) {
      return { user: null, tokenExpiry: null, isLoading: true }
    }
  } catch {
    // Corrupt browser state falls through to the signed-out state.
  }
  return { user: null, tokenExpiry: null, isLoading: false }
}

// Provider component
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [initialAuth] = useState(getInitialAuthSnapshot)
  const [user, setUser] = useState<User | null>(initialAuth.user)
  const [isLoading, setIsLoading] = useState(initialAuth.isLoading)
  const [tokenExpiry, setTokenExpiry] = useState<number | null>(initialAuth.tokenExpiry)
  const [mfaPending, setMfaPending] = useState(false)
  const [mfaToken, setMfaToken] = useState<string | null>(null)
  const [mfaMethods, setMfaMethods] = useState<string[]>([])
  const [sessionPolicy, setSessionPolicy] = useState<SessionPolicy | null>(() => {
    try {
      const saved = localStorage.getItem('auth_session_policy')
      return saved ? JSON.parse(saved) : null
    } catch { return null }
  })
  const [sessionExpiresAt, setSessionExpiresAt] = useState<string | null>(
    () => localStorage.getItem('auth_session_expires_at') || null
  )
  const [showSessionLimitsPopup, setShowSessionLimitsPopup] = useState(false)

  useEffect(() => {
    if (!user) return
    markStartupMilestone('auth-ready')
    return installSessionQueryPersistence(queryClient, user.id)
  }, [queryClient, user])

  const acknowledgeSessionLimits = useCallback(() => {
    setShowSessionLimitsPopup(false)
  }, [])

  // Get access token (returns null if not available or expired)
  const getAccessToken = useCallback((): string | null => {
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
    const expiry = parseInt(localStorage.getItem(STORAGE_KEYS.TOKEN_EXPIRY) || '0')

    if (!token || isTokenExpired(expiry)) {
      return null
    }
    return token
  }, [])

  // Refresh token
  const refreshAccessToken = useCallback(async (): Promise<boolean> => {
    const refreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN)
    if (!refreshToken) {
      return false
    }

    try {
      const response = await fetch(`${API_BASE}/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })

      if (!response.ok) {
        return false
      }

      const data: TokenRefreshResponse = await response.json()

      // Update stored tokens
      const expiryTime = Date.now() + data.expires_in * 1000
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, data.access_token)
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, data.refresh_token)
      localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRY, expiryTime.toString())
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(data.user))

      setTokenExpiry(expiryTime)
      setUser(data.user)

      return true
    } catch (error) {
      console.error('Token refresh failed:', error)
      return false
    }
  }, [])

  // Initialize auth state from localStorage (and MFA state from sessionStorage)
  useEffect(() => {
    const initializeAuth = async () => {
      const storedUser = localStorage.getItem(STORAGE_KEYS.USER)
      const accessToken = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
      const expiry = parseInt(localStorage.getItem(STORAGE_KEYS.TOKEN_EXPIRY) || '0')

      if (storedUser && accessToken) {
        // Check if token is expired
        if (isTokenExpired(expiry)) {
          // Try to refresh
          const refreshed = await refreshAccessToken()
          if (!refreshed) {
            // Clear invalid session
            logout()
          }
        } else {
          // Token is valid, restore session
          setUser(JSON.parse(storedUser))
          setTokenExpiry(expiry)
        }
      } else {
        // No active session — check for pending MFA challenge
        // (survives mobile browser page eviction via sessionStorage)
        const savedMfaToken = sessionStorage.getItem(SESSION_KEYS.MFA_TOKEN)
        if (savedMfaToken) {
          setMfaPending(true)
          setMfaToken(savedMfaToken)
          try {
            const methods = JSON.parse(
              sessionStorage.getItem(SESSION_KEYS.MFA_METHODS) || '[]'
            )
            setMfaMethods(methods)
          } catch {
            setMfaMethods([])
          }
        }
      }

      setIsLoading(false)
    }

    initializeAuth()
    // Runs once on mount to restore auth from stored tokens; it calls the stable
    // `logout` only on the token-validation-failure path. `logout` is declared
    // below, so it can't be a dep here without a forward reference — and re-running
    // this bootstrap on its identity is not wanted anyway.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshAccessToken])

  // Set up automatic token refresh
  useEffect(() => {
    if (!tokenExpiry || !user) return

    // Calculate time until refresh (refresh 1 minute before expiry)
    const timeUntilRefresh = tokenExpiry - Date.now() - 60000

    if (timeUntilRefresh <= 0) {
      // Token is about to expire, refresh now
      refreshAccessToken()
      return
    }

    // Schedule refresh
    const refreshTimer = setTimeout(() => {
      refreshAccessToken()
    }, timeUntilRefresh)

    return () => clearTimeout(refreshTimer)
  }, [tokenExpiry, user, refreshAccessToken])

  // Login function — may return MFA challenge instead of tokens
  const login = useCallback(async (email: string, password: string): Promise<void> => {
    // Include device trust token if available (to skip MFA on trusted devices)
    const deviceTrustToken = localStorage.getItem(STORAGE_KEYS.DEVICE_TRUST_TOKEN)
    const loginBody: Record<string, string> = { email, password }
    if (deviceTrustToken) {
      loginBody.device_trust_token = deviceTrustToken
    }

    const response = await fetch(`${API_BASE}/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(loginBody),
    })

    if (!response.ok) {
      let detail = 'Login failed'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch {
        // Response was not JSON (e.g. nginx HTML error page)
      }
      const err = new Error(detail) as Error & { status?: number }
      err.status = response.status
      throw err
    }

    const data: LoginResponse = await response.json()

    // Check if MFA is required
    if (data.mfa_required && data.mfa_token) {
      // Persist to sessionStorage so MFA survives mobile page eviction
      sessionStorage.setItem(SESSION_KEYS.MFA_TOKEN, data.mfa_token)
      sessionStorage.setItem(
        SESSION_KEYS.MFA_METHODS,
        JSON.stringify(data.mfa_methods || [])
      )
      setMfaPending(true)
      setMfaToken(data.mfa_token)
      setMfaMethods(data.mfa_methods || [])
      return  // Don't set user/tokens yet — need MFA verification
    }

    // No MFA — complete login
    if (data.access_token && data.refresh_token && data.user && data.expires_in) {
      const expiryTime = Date.now() + data.expires_in * 1000

      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, data.access_token)
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, data.refresh_token)
      localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRY, expiryTime.toString())
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(data.user))

      setTokenExpiry(expiryTime)
      setUser(data.user)

      // Handle session policy
      if (data.session_policy) {
        setSessionPolicy(data.session_policy)
        setSessionExpiresAt(data.session_expires_at || null)
        localStorage.setItem('auth_session_policy', JSON.stringify(data.session_policy))
        localStorage.setItem('auth_session_expires_at', data.session_expires_at || '')
        setShowSessionLimitsPopup(true)
      }
    }
  }, [])

  // Verify TOTP MFA code to complete login
  const verifyMFA = useCallback(async (code: string, rememberDevice = false): Promise<void> => {
    if (!mfaToken) {
      throw new Error('No MFA session active')
    }

    const response = await fetch(`${API_BASE}/mfa/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mfa_token: mfaToken,
        totp_code: code,
        remember_device: rememberDevice,
      }),
    })

    if (!response.ok) {
      let detail = 'MFA verification failed'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }

    const data: LoginResponse = await response.json()
    _completeMFALogin(data)
  }, [mfaToken])

  // Helper to complete MFA login from any verification response
  const _completeMFALogin = (data: LoginResponse) => {
    if (data.access_token && data.refresh_token && data.user && data.expires_in) {
      const expiryTime = Date.now() + data.expires_in * 1000

      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, data.access_token)
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, data.refresh_token)
      localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRY, expiryTime.toString())
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(data.user))

      if (data.device_trust_token) {
        localStorage.setItem(STORAGE_KEYS.DEVICE_TRUST_TOKEN, data.device_trust_token)
      }

      setTokenExpiry(expiryTime)
      setUser(data.user)

      // Handle session policy
      if (data.session_policy) {
        setSessionPolicy(data.session_policy)
        setSessionExpiresAt(data.session_expires_at || null)
        localStorage.setItem('auth_session_policy', JSON.stringify(data.session_policy))
        localStorage.setItem('auth_session_expires_at', data.session_expires_at || '')
        setShowSessionLimitsPopup(true)
      }
    }

    // Clear MFA state from both React and sessionStorage
    sessionStorage.removeItem(SESSION_KEYS.MFA_TOKEN)
    sessionStorage.removeItem(SESSION_KEYS.MFA_METHODS)
    setMfaPending(false)
    setMfaToken(null)
    setMfaMethods([])
  }

  // Verify MFA email code to complete login
  const verifyMFAEmailCode = useCallback(async (code: string, rememberDevice = false): Promise<void> => {
    if (!mfaToken) {
      throw new Error('No MFA session active')
    }

    const response = await fetch(`${API_BASE}/mfa/verify-email-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mfa_token: mfaToken,
        email_code: code,
        remember_device: rememberDevice,
      }),
    })

    if (!response.ok) {
      let detail = 'Email code verification failed'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }

    const data: LoginResponse = await response.json()
    _completeMFALogin(data)
  }, [mfaToken])

  // Verify MFA email link to complete login
  const verifyMFAEmailLink = useCallback(async (token: string, rememberDevice = false): Promise<void> => {
    const response = await fetch(`${API_BASE}/mfa/verify-email-link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        token,
        remember_device: rememberDevice,
      }),
    })

    if (!response.ok) {
      let detail = 'Email link verification failed'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }

    const data: LoginResponse = await response.json()
    _completeMFALogin(data)
  }, [])

  // Resend MFA email during login
  const resendMFAEmail = useCallback(async (): Promise<void> => {
    if (!mfaToken) {
      throw new Error('No MFA session active')
    }

    const response = await fetch(`${API_BASE}/mfa/resend-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mfa_token: mfaToken }),
    })

    if (!response.ok) {
      let detail = 'Failed to resend MFA email'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }
  }, [mfaToken])

  // Cancel MFA (go back to login form)
  const cancelMFA = useCallback(() => {
    sessionStorage.removeItem(SESSION_KEYS.MFA_TOKEN)
    sessionStorage.removeItem(SESSION_KEYS.MFA_METHODS)
    setMfaPending(false)
    setMfaToken(null)
    setMfaMethods([])
  }, [])

  // Signup function
  const signup = useCallback(async (email: string, password: string, displayName?: string): Promise<void> => {
    const response = await fetch(`${API_BASE}/signup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password, display_name: displayName || null }),
    })

    if (!response.ok) {
      let detail = 'Signup failed'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }

    const data: TokenRefreshResponse = await response.json()

    // Calculate and store token expiry
    const expiryTime = Date.now() + data.expires_in * 1000

    // Store in localStorage (auto-login after signup)
    localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, data.access_token)
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, data.refresh_token)
    localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRY, expiryTime.toString())
    localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(data.user))

    setTokenExpiry(expiryTime)
    setUser(data.user)
  }, [])

  // Logout function
  const logout = useCallback(() => {
    // Grab token BEFORE clearing storage — needed for server-side session cleanup
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
    const userId = user?.id

    // Clear localStorage
    localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN)
    localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN)
    localStorage.removeItem(STORAGE_KEYS.TOKEN_EXPIRY)
    localStorage.removeItem(STORAGE_KEYS.USER)

    // Clear any pending MFA session
    sessionStorage.removeItem(SESSION_KEYS.MFA_TOKEN)
    sessionStorage.removeItem(SESSION_KEYS.MFA_METHODS)

    // Clear session policy
    localStorage.removeItem('auth_session_policy')
    localStorage.removeItem('auth_session_expires_at')

    // Clear account selection (prevents stale ID when switching users)
    localStorage.removeItem('selectedAccountId')

    // Clear React Query cache to prevent stale data when switching users
    queryClient.clear()
    if (userId !== undefined) clearSessionQueryCache(userId)

    // Clear state
    setUser(null)
    setTokenExpiry(null)
    setMfaPending(false)
    setMfaToken(null)
    setSessionPolicy(null)
    setSessionExpiresAt(null)

    // Call logout endpoint to end server-side session (fire and forget)
    if (token) {
      fetch(`${API_BASE}/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      }).catch(() => {})
    }
  }, [queryClient, user?.id])

  // Listen for auth-logout events from API interceptor (avoids full page reload)
  useEffect(() => {
    const handleLogout = () => logout()
    window.addEventListener('auth-logout', handleLogout)
    return () => window.removeEventListener('auth-logout', handleLogout)
  }, [logout])

  // Session expiry countdown (shows 30s before auto-logout)
  const [sessionExpiryCountdown, setSessionExpiryCountdown] = useState<number | null>(null)

  // Session auto-logout timer + countdown
  useEffect(() => {
    if (!sessionExpiresAt) {
      setSessionExpiryCountdown(null)
      return
    }

    const expiresMs = new Date(sessionExpiresAt).getTime() - Date.now()
    if (expiresMs <= 0) {
      setSessionExpiryCountdown(null)
      if (sessionPolicy?.auto_logout) logout()
      return
    }

    // Auto-logout at expiry
    const logoutTimer = setTimeout(() => {
      setSessionExpiryCountdown(null)
      if (sessionPolicy?.auto_logout) logout()
    }, expiresMs)

    // Start countdown 30s before expiry (or immediately if <30s remain)
    const countdownStartMs = Math.max(0, expiresMs - 30000)
    const countdownTimer = setTimeout(() => {
      const remaining = Math.ceil((new Date(sessionExpiresAt).getTime() - Date.now()) / 1000)
      setSessionExpiryCountdown(Math.max(0, remaining))
    }, countdownStartMs)

    // Tick every second once countdown is active
    const interval = setInterval(() => {
      const remaining = Math.ceil((new Date(sessionExpiresAt).getTime() - Date.now()) / 1000)
      if (remaining <= 30 && remaining > 0) {
        setSessionExpiryCountdown(remaining)
      } else if (remaining <= 0) {
        setSessionExpiryCountdown(null)
      }
    }, 1000)

    return () => {
      clearTimeout(logoutTimer)
      clearTimeout(countdownTimer)
      clearInterval(interval)
    }
  }, [sessionExpiresAt, sessionPolicy, logout])

  // Change password function
  const changePassword = useCallback(async (currentPassword: string, newPassword: string): Promise<void> => {
    const token = getAccessToken()
    if (!token) {
      throw new Error('Not authenticated')
    }

    const response = await fetch(`${API_BASE}/change-password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    })

    if (!response.ok) {
      let detail = 'Failed to change password'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }
  }, [getAccessToken])

  // Accept terms function - called after user accepts the risk disclaimer
  const acceptTerms = useCallback(async (): Promise<void> => {
    const token = getAccessToken()
    if (!token) {
      throw new Error('Not authenticated')
    }

    const response = await fetch(`${API_BASE}/accept-terms`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
    })

    if (!response.ok) {
      let detail = 'Failed to accept terms'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }

    // Update user state with the new terms_accepted_at timestamp
    const updatedUser: User = await response.json()
    setUser(updatedUser)
    localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(updatedUser))
  }, [getAccessToken])

  // Update user state (e.g., after enabling/disabling MFA in settings)
  const updateUser = useCallback((updatedUser: User) => {
    setUser(updatedUser)
    localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(updatedUser))
  }, [])

  // Enable email-based MFA (requires password confirmation)
  const enableEmailMFA = useCallback(async (password: string): Promise<void> => {
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
    if (!token) throw new Error('Not authenticated')

    const response = await fetch(`${API_BASE}/mfa/email/enable`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ password }),
    })

    if (!response.ok) {
      let detail = 'Failed to enable email MFA'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }

    const updatedUser: User = await response.json()
    setUser(updatedUser)
    localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(updatedUser))
  }, [])

  // Disable email-based MFA (requires password confirmation)
  const disableEmailMFA = useCallback(async (password: string): Promise<void> => {
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
    if (!token) throw new Error('Not authenticated')

    const response = await fetch(`${API_BASE}/mfa/email/disable`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ password }),
    })

    if (!response.ok) {
      let detail = 'Failed to disable email MFA'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }

    const updatedUser: User = await response.json()
    setUser(updatedUser)
    localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(updatedUser))
  }, [])

  // Verify email with token from email link
  const verifyEmail = useCallback(async (token: string): Promise<void> => {
    const response = await fetch(`${API_BASE}/verify-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })

    if (!response.ok) {
      let detail = 'Email verification failed'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }

    const updatedUser: User = await response.json()
    setUser(updatedUser)
    localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(updatedUser))
  }, [])

  // Verify email with 6-digit code (authenticated user enters code)
  const verifyEmailCode = useCallback(async (code: string): Promise<void> => {
    const accessToken = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
    if (!accessToken) throw new Error('Not authenticated')

    const response = await fetch(`${API_BASE}/verify-email-code`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ code }),
    })

    if (!response.ok) {
      let detail = 'Code verification failed'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }

    const updatedUser: User = await response.json()
    setUser(updatedUser)
    localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(updatedUser))
  }, [])

  // Resend verification email (authenticated)
  const resendVerification = useCallback(async (): Promise<void> => {
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
    if (!token) throw new Error('Not authenticated')

    const response = await fetch(`${API_BASE}/resend-verification`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
    })

    if (!response.ok) {
      let detail = 'Failed to resend verification email'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }
  }, [])

  // Request password reset email (unauthenticated)
  const forgotPassword = useCallback(async (email: string): Promise<void> => {
    const response = await fetch(`${API_BASE}/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })

    if (!response.ok) {
      let detail = 'Failed to send reset email'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }
  }, [])

  // Reset password with token (unauthenticated)
  const resetPassword = useCallback(async (token: string, newPassword: string): Promise<void> => {
    const response = await fetch(`${API_BASE}/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword }),
    })

    if (!response.ok) {
      let detail = 'Failed to reset password'
      try {
        const error = await response.json()
        detail = error.detail || detail
      } catch { /* non-JSON response */ }
      throw new Error(detail)
    }
  }, [])

  const value: AuthContextType = useMemo(() => ({
    user,
    isAuthenticated: !!user,
    isLoading,
    mfaPending,
    mfaToken,
    mfaMethods,
    login,
    verifyMFA,
    verifyMFAEmailCode,
    verifyMFAEmailLink,
    resendMFAEmail,
    cancelMFA,
    signup,
    logout,
    changePassword,
    getAccessToken,
    acceptTerms,
    updateUser,
    enableEmailMFA,
    disableEmailMFA,
    verifyEmail,
    verifyEmailCode,
    resendVerification,
    forgotPassword,
    resetPassword,
    sessionPolicy,
    sessionExpiresAt,
    sessionExpiryCountdown,
    showSessionLimitsPopup,
    acknowledgeSessionLimits,
  }), [
    user, isLoading, mfaPending, mfaToken, mfaMethods,
    login, verifyMFA, verifyMFAEmailCode, verifyMFAEmailLink, resendMFAEmail, cancelMFA,
    signup, logout, changePassword, getAccessToken, acceptTerms, updateUser,
    enableEmailMFA, disableEmailMFA, verifyEmail, verifyEmailCode, resendVerification,
    forgotPassword, resetPassword, sessionPolicy, sessionExpiresAt, sessionExpiryCountdown,
    showSessionLimitsPopup, acknowledgeSessionLimits,
  ])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// Protected route wrapper component
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-white text-lg">Loading...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    // Return null - the login page will be shown by the parent
    return null
  }

  return <>{children}</>
}
