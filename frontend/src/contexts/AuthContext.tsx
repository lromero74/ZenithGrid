/**
 * Authentication Context
 *
 * Manages user authentication state, tokens, and login/logout functionality.
 * Provides automatic token refresh and persistent sessions via localStorage.
 */

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'

// Types
interface User {
  id: number
  email: string
  display_name: string | null
  is_active: boolean
  is_superuser: boolean
  created_at: string
  last_login_at: string | null
}

// AuthTokens interface (used by LoginResponse)
// interface AuthTokens {
//   access_token: string
//   refresh_token: string
//   expires_in: number
// }

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
  getAccessToken: () => string | null
}

interface LoginResponse {
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
}

// API base URL
const API_BASE = '/api/auth'

// Create context with default values
const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  login: async () => {},
  logout: () => {},
  changePassword: async () => {},
  getAccessToken: () => null,
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

      const data: LoginResponse = await response.json()

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

  // Login function
  const login = async (email: string, password: string): Promise<void> => {
    const response = await fetch(`${API_BASE}/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Login failed')
    }

    const data: LoginResponse = await response.json()

    // Calculate and store token expiry
    const expiryTime = Date.now() + data.expires_in * 1000

    // Store in localStorage
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

    // Call logout endpoint (fire and forget)
    fetch(`${API_BASE}/logout`, { method: 'POST' }).catch(() => {})
  }, [])

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

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isLoading,
    login,
    logout,
    changePassword,
    getAccessToken,
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
