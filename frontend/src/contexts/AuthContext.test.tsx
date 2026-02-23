/**
 * Tests for AuthContext
 *
 * Tests the isTokenExpired helper, useAuth hook, and RequireAuth component.
 * API calls are mocked via globalThis.fetch.
 */

import { describe, test, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { AuthProvider, useAuth, RequireAuth } from './AuthContext'

// Helper to render a test component that consumes useAuth
function TestConsumer() {
  const auth = useAuth()
  return (
    <div>
      <span data-testid="authenticated">{String(auth.isAuthenticated)}</span>
      <span data-testid="loading">{String(auth.isLoading)}</span>
      <span data-testid="mfa-pending">{String(auth.mfaPending)}</span>
      {auth.user && <span data-testid="user-email">{auth.user.email}</span>}
      <button data-testid="logout-btn" onClick={auth.logout}>
        Logout
      </button>
    </div>
  )
}

describe('AuthContext', () => {
  beforeEach(() => {
    // Clear all storage
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('initial state is unauthenticated when no tokens in storage', async () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('authenticated').textContent).toBe('false')
  })

  test('restores session from localStorage when valid token exists', async () => {
    const user = {
      id: 1,
      email: 'test@example.com',
      display_name: 'Test User',
      is_active: true,
      is_superuser: false,
      mfa_enabled: false,
      mfa_email_enabled: false,
      email_verified: true,
      email_verified_at: '2025-01-01T00:00:00Z',
      created_at: '2025-01-01T00:00:00Z',
      last_login_at: null,
      terms_accepted_at: '2025-01-01T00:00:00Z',
    }

    // Set valid token in localStorage (expires in 1 hour)
    const expiry = Date.now() + 3600000
    localStorage.setItem('auth_access_token', 'valid-token-123')
    localStorage.setItem('auth_refresh_token', 'refresh-token-123')
    localStorage.setItem('auth_token_expiry', expiry.toString())
    localStorage.setItem('auth_user', JSON.stringify(user))

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('user-email').textContent).toBe('test@example.com')
  })

  test('expired token triggers refresh attempt', async () => {
    const user = {
      id: 1,
      email: 'test@example.com',
      display_name: null,
      is_active: true,
      is_superuser: false,
      mfa_enabled: false,
      mfa_email_enabled: false,
      email_verified: true,
      email_verified_at: null,
      created_at: '2025-01-01T00:00:00Z',
      last_login_at: null,
      terms_accepted_at: null,
    }

    // Set expired token
    const expiry = Date.now() - 60000
    localStorage.setItem('auth_access_token', 'expired-token')
    localStorage.setItem('auth_refresh_token', 'refresh-token')
    localStorage.setItem('auth_token_expiry', expiry.toString())
    localStorage.setItem('auth_user', JSON.stringify(user))

    // Mock fetch for refresh endpoint - return failure
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
    })
    globalThis.fetch = mockFetch

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    // After failed refresh, should be unauthenticated
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    // Refresh should have been called
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/auth/refresh'),
      expect.any(Object)
    )
  })

  test('logout clears storage and state', async () => {
    const user = {
      id: 1, email: 'test@example.com', display_name: null,
      is_active: true, is_superuser: false, mfa_enabled: false,
      mfa_email_enabled: false, email_verified: true,
      email_verified_at: null, created_at: '2025-01-01T00:00:00Z',
      last_login_at: null, terms_accepted_at: null,
    }

    const expiry = Date.now() + 3600000
    localStorage.setItem('auth_access_token', 'valid-token')
    localStorage.setItem('auth_refresh_token', 'refresh-token')
    localStorage.setItem('auth_token_expiry', expiry.toString())
    localStorage.setItem('auth_user', JSON.stringify(user))

    // Mock fetch for logout endpoint
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true })

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    // Click logout
    act(() => {
      screen.getByTestId('logout-btn').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('false')
    })

    // Storage should be cleared
    expect(localStorage.getItem('auth_access_token')).toBeNull()
    expect(localStorage.getItem('auth_user')).toBeNull()
  })

  test('MFA pending state restored from sessionStorage', async () => {
    sessionStorage.setItem('auth_mfa_token', 'mfa-token-123')
    sessionStorage.setItem('auth_mfa_methods', JSON.stringify(['totp', 'email_code']))

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('mfa-pending').textContent).toBe('true')
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
  })
})

describe('RequireAuth', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  test('shows children when authenticated', async () => {
    const user = {
      id: 1, email: 'test@example.com', display_name: null,
      is_active: true, is_superuser: false, mfa_enabled: false,
      mfa_email_enabled: false, email_verified: true,
      email_verified_at: null, created_at: '2025-01-01T00:00:00Z',
      last_login_at: null, terms_accepted_at: null,
    }

    const expiry = Date.now() + 3600000
    localStorage.setItem('auth_access_token', 'valid-token')
    localStorage.setItem('auth_refresh_token', 'refresh-token')
    localStorage.setItem('auth_token_expiry', expiry.toString())
    localStorage.setItem('auth_user', JSON.stringify(user))

    render(
      <AuthProvider>
        <RequireAuth>
          <span data-testid="protected">Secret Content</span>
        </RequireAuth>
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('protected')).toBeInTheDocument()
    })
  })

  test('hides children when not authenticated', async () => {
    render(
      <AuthProvider>
        <RequireAuth>
          <span data-testid="protected">Secret Content</span>
        </RequireAuth>
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.queryByTestId('protected')).not.toBeInTheDocument()
    })
  })
})
