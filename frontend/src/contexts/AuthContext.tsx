/**
 * Authentication Context
 *
 * Manages user authentication state, tokens, and login/logout functionality.
 * Provides automatic token refresh and persistent sessions via localStorage.
 * Supports TOTP MFA (two-factor authentication) challenge flow.
 */

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'

// Types
interface User {
  id: number
  email: string
  display_name: string | null
  is_active: boolean
  is_superuser: boolean
  mfa_enabled: boolean
  email_verified: boolean
  email_verified_at: string | null
  created_at: string
  last_login_at: string | null
  terms_accepted_at: string | null  // NULL = must accept terms before accessing dashboard
}

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  mfaPending: boolean  // True when MFA verification is needed
  mfaToken: string | null  // Short-lived token for MFA verification
  login: (email: string, password: string) => Promise<void>
  verifyMFA: (code: string, rememberDevice?: boolean) => Promise<void>
  cancelMFA: () => void
  signup: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => void
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
  getAccessToken: () => string | null
  acceptTerms: () => Promise<void>
  updateUser: (user: User) => void  // Update user state (e.g., after MFA enable/disable)
  verifyEmail: (token: string) => Promise<void>
  verifyEmailCode: (code: string) => Promise<void>
  resendVerification: () => Promise<void>
  forgotPassword: (email: string) => Promise<void>
  resetPassword: (token: string, newPassword: string) => Promise<void>
}

interface LoginResponse {
  access_token: string | null
  refresh_token: string | null
  token_type: string
  expires_in: number | null
  user: User | null
  mfa_required: boolean
  mfa_token: string | null
  device_trust_token: string | null
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

// API base URL
const API_BASE = '/api/auth'

// Create context with default values
const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  mfaPending: false,
  mfaToken: null,
  login: async () => {},
  verifyMFA: async (_code: string, _rememberDevice?: boolean) => {},
  cancelMFA: () => {},
  signup: async () => {},
  logout: () => {},
  changePassword: async () => {},
  getAccessToken: () => null,
  acceptTerms: async () => {},
  updateUser: () => {},
  verifyEmail: async () => {},
  verifyEmailCode: async () => {},
  resendVerification: async () => {},
  forgotPassword: async () => {},
  resetPassword: async () => {},
})

// Helper to check if token is expired
function isTokenExpired(expiryTime: number | null): boolean {
  if (!expiryTime) return true
  // Add 30 second buffer before actual expiry
  return Date.now() >= expiryTime - 30000
}

// Provider component
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [tokenExpiry, setTokenExpiry] = useState<number | null>(null)
  const [mfaPending, setMfaPending] = useState(false)
  const [mfaToken, setMfaToken] = useState<string | null>(null)

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

  // Initialize auth state from localStorage
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
      }

      setIsLoading(false)
    }

    initializeAuth()
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
  const login = async (email: string, password: string): Promise<void> => {
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
      const error = await response.json()
      throw new Error(error.detail || 'Login failed')
    }

    const data: LoginResponse = await response.json()

    // Check if MFA is required
    if (data.mfa_required && data.mfa_token) {
      setMfaPending(true)
      setMfaToken(data.mfa_token)
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
    }
  }

  // Verify MFA code to complete login
  const verifyMFA = async (code: string, rememberDevice = false): Promise<void> => {
    if (!mfaToken) {
      throw new Error('No MFA session active')
    }

    const response = await fetch(`${API_BASE}/mfa/verify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        mfa_token: mfaToken,
        totp_code: code,
        remember_device: rememberDevice,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'MFA verification failed')
    }

    const data: LoginResponse = await response.json()

    if (data.access_token && data.refresh_token && data.user && data.expires_in) {
      const expiryTime = Date.now() + data.expires_in * 1000

      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, data.access_token)
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, data.refresh_token)
      localStorage.setItem(STORAGE_KEYS.TOKEN_EXPIRY, expiryTime.toString())
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(data.user))

      // Store device trust token if provided
      if (data.device_trust_token) {
        localStorage.setItem(STORAGE_KEYS.DEVICE_TRUST_TOKEN, data.device_trust_token)
      }

      setTokenExpiry(expiryTime)
      setUser(data.user)
    }

    // Clear MFA state
    setMfaPending(false)
    setMfaToken(null)
  }

  // Cancel MFA (go back to login form)
  const cancelMFA = useCallback(() => {
    setMfaPending(false)
    setMfaToken(null)
  }, [])

  // Signup function
  const signup = async (email: string, password: string, displayName?: string): Promise<void> => {
    const response = await fetch(`${API_BASE}/signup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password, display_name: displayName || null }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Signup failed')
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
  }

  // Logout function
  const logout = useCallback(() => {
    // Clear localStorage
    localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN)
    localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN)
    localStorage.removeItem(STORAGE_KEYS.TOKEN_EXPIRY)
    localStorage.removeItem(STORAGE_KEYS.USER)

    // Clear state
    setUser(null)
    setTokenExpiry(null)
    setMfaPending(false)
    setMfaToken(null)

    // Call logout endpoint (fire and forget)
    fetch(`${API_BASE}/logout`, { method: 'POST' }).catch(() => {})
  }, [])

  // Listen for auth-logout events from API interceptor (avoids full page reload)
  useEffect(() => {
    const handleLogout = () => logout()
    window.addEventListener('auth-logout', handleLogout)
    return () => window.removeEventListener('auth-logout', handleLogout)
  }, [logout])

  // Change password function
  const changePassword = async (currentPassword: string, newPassword: string): Promise<void> => {
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
      const error = await response.json()
      throw new Error(error.detail || 'Failed to change password')
    }
  }

  // Accept terms function - called after user accepts the risk disclaimer
  const acceptTerms = async (): Promise<void> => {
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
      const error = await response.json()
      throw new Error(error.detail || 'Failed to accept terms')
    }

    // Update user state with the new terms_accepted_at timestamp
    const updatedUser: User = await response.json()
    setUser(updatedUser)
    localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(updatedUser))
  }

  // Update user state (e.g., after enabling/disabling MFA in settings)
  const updateUser = useCallback((updatedUser: User) => {
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
      const error = await response.json()
      throw new Error(error.detail || 'Email verification failed')
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
      const error = await response.json()
      throw new Error(error.detail || 'Code verification failed')
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
      const error = await response.json()
      throw new Error(error.detail || 'Failed to resend verification email')
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
      const error = await response.json()
      throw new Error(error.detail || 'Failed to send reset email')
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
      const error = await response.json()
      throw new Error(error.detail || 'Failed to reset password')
    }
  }, [])

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isLoading,
    mfaPending,
    mfaToken,
    login,
    verifyMFA,
    cancelMFA,
    signup,
    logout,
    changePassword,
    getAccessToken,
    acceptTerms,
    updateUser,
    verifyEmail,
    verifyEmailCode,
    resendVerification,
    forgotPassword,
    resetPassword,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// Hook for consuming auth context
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
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
