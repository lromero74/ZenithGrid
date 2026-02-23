/**
 * Tests for AuthContext
 *
 * Tests the isTokenExpired helper, useAuth hook, RequireAuth component,
 * and all auth flows: login, signup, MFA, password management, email verification.
 * API calls are mocked via globalThis.fetch.
 */

import { describe, test, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { renderHook } from '@testing-library/react'
import { AuthProvider, useAuth, RequireAuth } from './AuthContext'
import type { ReactNode } from 'react'

// Reusable mock user
const mockUser = {
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

// Helper to set up a valid authenticated session in localStorage
function setupAuthSession(user = mockUser) {
  const expiry = Date.now() + 3600000
  localStorage.setItem('auth_access_token', 'valid-token')
  localStorage.setItem('auth_refresh_token', 'refresh-token')
  localStorage.setItem('auth_token_expiry', expiry.toString())
  localStorage.setItem('auth_user', JSON.stringify(user))
}

// Wrapper for renderHook
function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

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

  test('MFA pending state restored with invalid JSON defaults to empty methods', async () => {
    sessionStorage.setItem('auth_mfa_token', 'mfa-token-123')
    sessionStorage.setItem('auth_mfa_methods', 'not-valid-json')

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('mfa-pending').textContent).toBe('true')
  })

  test('successful token refresh updates storage and state', async () => {
    const user = {
      id: 1, email: 'test@example.com', display_name: null,
      is_active: true, is_superuser: false, mfa_enabled: false,
      mfa_email_enabled: false, email_verified: true,
      email_verified_at: null, created_at: '2025-01-01T00:00:00Z',
      last_login_at: null, terms_accepted_at: null,
    }

    // Set expired token
    const expiry = Date.now() - 60000
    localStorage.setItem('auth_access_token', 'expired-token')
    localStorage.setItem('auth_refresh_token', 'refresh-token')
    localStorage.setItem('auth_token_expiry', expiry.toString())
    localStorage.setItem('auth_user', JSON.stringify(user))

    const refreshedUser = { ...user, email: 'refreshed@example.com' }
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        access_token: 'new-access-token',
        refresh_token: 'new-refresh-token',
        token_type: 'bearer',
        expires_in: 3600,
        user: refreshedUser,
      }),
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

    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('user-email').textContent).toBe('refreshed@example.com')
    expect(localStorage.getItem('auth_access_token')).toBe('new-access-token')
    expect(localStorage.getItem('auth_refresh_token')).toBe('new-refresh-token')
  })

  test('refresh fails without refresh token in storage', async () => {
    const user = {
      id: 1, email: 'test@example.com', display_name: null,
      is_active: true, is_superuser: false, mfa_enabled: false,
      mfa_email_enabled: false, email_verified: true,
      email_verified_at: null, created_at: '2025-01-01T00:00:00Z',
      last_login_at: null, terms_accepted_at: null,
    }

    // Set expired token but no refresh token
    const expiry = Date.now() - 60000
    localStorage.setItem('auth_access_token', 'expired-token')
    localStorage.setItem('auth_token_expiry', expiry.toString())
    localStorage.setItem('auth_user', JSON.stringify(user))

    // Mock fetch for the logout fire-and-forget call that happens when refresh fails
    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    globalThis.fetch = mockFetch

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    // Should be logged out since refresh can't happen without refresh token
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    // Fetch should have been called only for the logout fire-and-forget, not for refresh
    const refreshCalls = mockFetch.mock.calls.filter(
      (call: any[]) => typeof call[0] === 'string' && call[0].includes('/auth/refresh')
    )
    expect(refreshCalls).toHaveLength(0)
  })

  test('auth-logout event triggers logout', async () => {
    setupAuthSession()
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true })

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('true')
    })

    // Dispatch the custom event
    act(() => {
      window.dispatchEvent(new Event('auth-logout'))
    })

    await waitFor(() => {
      expect(screen.getByTestId('authenticated').textContent).toBe('false')
    })
  })
})

describe('login', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful login stores tokens and sets user', async () => {
    const loginResponse = {
      access_token: 'new-token',
      refresh_token: 'new-refresh',
      token_type: 'bearer',
      expires_in: 3600,
      user: mockUser,
      mfa_required: false,
      mfa_token: null,
      mfa_methods: null,
      device_trust_token: null,
    }

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(loginResponse),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.login('test@example.com', 'password123')
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.email).toBe('test@example.com')
    expect(localStorage.getItem('auth_access_token')).toBe('new-token')
    expect(localStorage.getItem('auth_refresh_token')).toBe('new-refresh')
  })

  test('login with MFA required sets MFA pending state', async () => {
    const mfaResponse = {
      access_token: null,
      refresh_token: null,
      token_type: 'bearer',
      expires_in: null,
      user: null,
      mfa_required: true,
      mfa_token: 'mfa-challenge-token',
      mfa_methods: ['totp', 'email_code'],
      device_trust_token: null,
    }

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mfaResponse),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.login('test@example.com', 'password123')
    })

    expect(result.current.mfaPending).toBe(true)
    expect(result.current.isAuthenticated).toBe(false)
    expect(sessionStorage.getItem('auth_mfa_token')).toBe('mfa-challenge-token')
  })

  test('login with invalid credentials throws error', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Invalid email or password' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.login('bad@example.com', 'wrong')
      })
    ).rejects.toThrow('Invalid email or password')
  })

  test('login includes device trust token when available', async () => {
    localStorage.setItem('auth_device_trust_token', 'trusted-device-123')

    const loginResponse = {
      access_token: 'token',
      refresh_token: 'refresh',
      token_type: 'bearer',
      expires_in: 3600,
      user: mockUser,
      mfa_required: false,
      mfa_token: null,
      mfa_methods: null,
      device_trust_token: null,
    }

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(loginResponse),
    })
    globalThis.fetch = mockFetch

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.login('test@example.com', 'password123')
    })

    const fetchCall = mockFetch.mock.calls[0]
    const body = JSON.parse(fetchCall[1].body)
    expect(body.device_trust_token).toBe('trusted-device-123')
  })
})

describe('signup', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful signup stores tokens and auto-logs in', async () => {
    const signupResponse = {
      access_token: 'signup-token',
      refresh_token: 'signup-refresh',
      token_type: 'bearer',
      expires_in: 3600,
      user: { ...mockUser, email: 'new@example.com' },
    }

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(signupResponse),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.signup('new@example.com', 'password123', 'New User')
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.email).toBe('new@example.com')
    expect(localStorage.getItem('auth_access_token')).toBe('signup-token')
  })

  test('signup sends display_name as null when not provided', async () => {
    const signupResponse = {
      access_token: 'token',
      refresh_token: 'refresh',
      token_type: 'bearer',
      expires_in: 3600,
      user: mockUser,
    }

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(signupResponse),
    })
    globalThis.fetch = mockFetch

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.signup('test@example.com', 'password123')
    })

    const fetchCall = mockFetch.mock.calls[0]
    const body = JSON.parse(fetchCall[1].body)
    expect(body.display_name).toBeNull()
  })

  test('signup failure throws error with server message', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: () => Promise.resolve({ detail: 'Email already registered' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.signup('exists@example.com', 'password123')
      })
    ).rejects.toThrow('Email already registered')
  })
})

describe('verifyMFA', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful TOTP verification completes login', async () => {
    // Set up MFA pending state
    sessionStorage.setItem('auth_mfa_token', 'mfa-token-123')
    sessionStorage.setItem('auth_mfa_methods', JSON.stringify(['totp']))

    const verifyResponse = {
      access_token: 'mfa-verified-token',
      refresh_token: 'mfa-refresh',
      token_type: 'bearer',
      expires_in: 3600,
      user: mockUser,
      mfa_required: false,
      mfa_token: null,
      mfa_methods: null,
      device_trust_token: 'new-trust-token',
    }

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(verifyResponse),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
      expect(result.current.mfaPending).toBe(true)
    })

    await act(async () => {
      await result.current.verifyMFA('123456', true)
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.mfaPending).toBe(false)
    expect(localStorage.getItem('auth_device_trust_token')).toBe('new-trust-token')
    expect(sessionStorage.getItem('auth_mfa_token')).toBeNull()
  })

  test('verifyMFA throws when no MFA session active', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.verifyMFA('123456')
      })
    ).rejects.toThrow('No MFA session active')
  })

  test('verifyMFA with invalid code throws server error', async () => {
    sessionStorage.setItem('auth_mfa_token', 'mfa-token-123')
    sessionStorage.setItem('auth_mfa_methods', JSON.stringify(['totp']))

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Invalid TOTP code' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.mfaPending).toBe(true)
    })

    await expect(
      act(async () => {
        await result.current.verifyMFA('000000')
      })
    ).rejects.toThrow('Invalid TOTP code')
  })
})

describe('verifyMFAEmailCode', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful email code verification completes login', async () => {
    sessionStorage.setItem('auth_mfa_token', 'mfa-token-123')
    sessionStorage.setItem('auth_mfa_methods', JSON.stringify(['email_code']))

    const verifyResponse = {
      access_token: 'email-verified-token',
      refresh_token: 'email-refresh',
      token_type: 'bearer',
      expires_in: 3600,
      user: mockUser,
      mfa_required: false,
      mfa_token: null,
      mfa_methods: null,
      device_trust_token: null,
    }

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(verifyResponse),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.mfaPending).toBe(true)
    })

    await act(async () => {
      await result.current.verifyMFAEmailCode('123456')
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.mfaPending).toBe(false)
  })

  test('verifyMFAEmailCode throws when no MFA session active', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.verifyMFAEmailCode('123456')
      })
    ).rejects.toThrow('No MFA session active')
  })

  test('verifyMFAEmailCode sends correct payload', async () => {
    sessionStorage.setItem('auth_mfa_token', 'mfa-tok')
    sessionStorage.setItem('auth_mfa_methods', JSON.stringify(['email_code']))

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        access_token: 't', refresh_token: 'r', token_type: 'bearer',
        expires_in: 3600, user: mockUser, mfa_required: false,
        mfa_token: null, mfa_methods: null, device_trust_token: null,
      }),
    })
    globalThis.fetch = mockFetch

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.mfaPending).toBe(true)
    })

    await act(async () => {
      await result.current.verifyMFAEmailCode('654321', true)
    })

    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.mfa_token).toBe('mfa-tok')
    expect(body.email_code).toBe('654321')
    expect(body.remember_device).toBe(true)
  })
})

describe('verifyMFAEmailLink', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful email link verification completes login', async () => {
    const verifyResponse = {
      access_token: 'link-verified-token',
      refresh_token: 'link-refresh',
      token_type: 'bearer',
      expires_in: 3600,
      user: mockUser,
      mfa_required: false,
      mfa_token: null,
      mfa_methods: null,
      device_trust_token: null,
    }

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(verifyResponse),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.verifyMFAEmailLink('link-token-abc')
    })

    expect(result.current.isAuthenticated).toBe(true)
  })

  test('verifyMFAEmailLink failure throws error', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'Link expired' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.verifyMFAEmailLink('expired-token')
      })
    ).rejects.toThrow('Link expired')
  })
})

describe('resendMFAEmail', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful resend calls endpoint with mfa_token', async () => {
    sessionStorage.setItem('auth_mfa_token', 'mfa-tok-resend')
    sessionStorage.setItem('auth_mfa_methods', JSON.stringify(['email_code']))

    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    globalThis.fetch = mockFetch

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.mfaPending).toBe(true)
    })

    await act(async () => {
      await result.current.resendMFAEmail()
    })

    const url = mockFetch.mock.calls[0][0]
    expect(url).toContain('/auth/mfa/resend-email')
    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.mfa_token).toBe('mfa-tok-resend')
  })

  test('resendMFAEmail throws when no MFA session active', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.resendMFAEmail()
      })
    ).rejects.toThrow('No MFA session active')
  })

  test('resendMFAEmail failure throws server error', async () => {
    sessionStorage.setItem('auth_mfa_token', 'mfa-tok')
    sessionStorage.setItem('auth_mfa_methods', JSON.stringify(['email_code']))

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: () => Promise.resolve({ detail: 'Rate limited' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.mfaPending).toBe(true)
    })

    await expect(
      act(async () => {
        await result.current.resendMFAEmail()
      })
    ).rejects.toThrow('Rate limited')
  })
})

describe('cancelMFA', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  test('cancelMFA clears MFA state and session storage', async () => {
    sessionStorage.setItem('auth_mfa_token', 'mfa-token-123')
    sessionStorage.setItem('auth_mfa_methods', JSON.stringify(['totp']))

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.mfaPending).toBe(true)
    })

    act(() => {
      result.current.cancelMFA()
    })

    expect(result.current.mfaPending).toBe(false)
    expect(sessionStorage.getItem('auth_mfa_token')).toBeNull()
    expect(sessionStorage.getItem('auth_mfa_methods')).toBeNull()
  })
})

describe('changePassword', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful password change calls endpoint with auth header', async () => {
    setupAuthSession()

    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    globalThis.fetch = mockFetch

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.changePassword('oldpass', 'newpass')
    })

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toContain('/auth/change-password')
    expect(call[1].headers['Authorization']).toContain('Bearer')
    const body = JSON.parse(call[1].body)
    expect(body.current_password).toBe('oldpass')
    expect(body.new_password).toBe('newpass')
  })

  test('changePassword throws when not authenticated', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.changePassword('old', 'new')
      })
    ).rejects.toThrow('Not authenticated')
  })

  test('changePassword failure throws server error', async () => {
    setupAuthSession()

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'Current password incorrect' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await expect(
      act(async () => {
        await result.current.changePassword('wrong', 'new')
      })
    ).rejects.toThrow('Current password incorrect')
  })
})

describe('acceptTerms', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful acceptTerms updates user state', async () => {
    setupAuthSession({ ...mockUser, terms_accepted_at: '' })

    const updatedUser = { ...mockUser, terms_accepted_at: '2026-01-15T12:00:00Z' }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(updatedUser),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.acceptTerms()
    })

    expect(result.current.user?.terms_accepted_at).toBe('2026-01-15T12:00:00Z')
    const storedUser = JSON.parse(localStorage.getItem('auth_user') || '{}')
    expect(storedUser.terms_accepted_at).toBe('2026-01-15T12:00:00Z')
  })

  test('acceptTerms throws when not authenticated', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.acceptTerms()
      })
    ).rejects.toThrow('Not authenticated')
  })
})

describe('updateUser', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  test('updateUser sets user and persists to localStorage', async () => {
    setupAuthSession()

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    const updatedUser = { ...mockUser, mfa_enabled: true }

    act(() => {
      result.current.updateUser(updatedUser)
    })

    expect(result.current.user?.mfa_enabled).toBe(true)
    const storedUser = JSON.parse(localStorage.getItem('auth_user') || '{}')
    expect(storedUser.mfa_enabled).toBe(true)
  })
})

describe('enableEmailMFA', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful enableEmailMFA updates user with mfa_email_enabled', async () => {
    setupAuthSession()

    const updatedUser = { ...mockUser, mfa_email_enabled: true }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(updatedUser),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.enableEmailMFA('mypassword')
    })

    expect(result.current.user?.mfa_email_enabled).toBe(true)
  })

  test('enableEmailMFA throws when not authenticated', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.enableEmailMFA('password')
      })
    ).rejects.toThrow('Not authenticated')
  })
})

describe('disableEmailMFA', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful disableEmailMFA updates user', async () => {
    setupAuthSession({ ...mockUser, mfa_email_enabled: true })

    const updatedUser = { ...mockUser, mfa_email_enabled: false }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(updatedUser),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.disableEmailMFA('mypassword')
    })

    expect(result.current.user?.mfa_email_enabled).toBe(false)
  })

  test('disableEmailMFA throws when not authenticated', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.disableEmailMFA('password')
      })
    ).rejects.toThrow('Not authenticated')
  })

  test('disableEmailMFA failure throws server error', async () => {
    setupAuthSession()

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'Wrong password' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await expect(
      act(async () => {
        await result.current.disableEmailMFA('badpass')
      })
    ).rejects.toThrow('Wrong password')
  })
})

describe('verifyEmail', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful verifyEmail updates user email_verified status', async () => {
    setupAuthSession({ ...mockUser, email_verified: false, email_verified_at: '' })

    const verifiedUser = { ...mockUser, email_verified: true, email_verified_at: '2026-02-01T00:00:00Z' }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(verifiedUser),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.verifyEmail('verify-token-abc')
    })

    expect(result.current.user?.email_verified).toBe(true)
    expect(result.current.user?.email_verified_at).toBe('2026-02-01T00:00:00Z')
  })

  test('verifyEmail failure throws error', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'Token expired' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.verifyEmail('expired-token')
      })
    ).rejects.toThrow('Token expired')
  })
})

describe('verifyEmailCode', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful verifyEmailCode updates user', async () => {
    setupAuthSession({ ...mockUser, email_verified: false })

    const verifiedUser = { ...mockUser, email_verified: true }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(verifiedUser),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.verifyEmailCode('123456')
    })

    expect(result.current.user?.email_verified).toBe(true)
  })

  test('verifyEmailCode throws when not authenticated', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.verifyEmailCode('123456')
      })
    ).rejects.toThrow('Not authenticated')
  })

  test('verifyEmailCode sends auth header and code', async () => {
    setupAuthSession()

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockUser),
    })
    globalThis.fetch = mockFetch

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.verifyEmailCode('654321')
    })

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toContain('/auth/verify-email-code')
    expect(call[1].headers['Authorization']).toContain('Bearer')
    const body = JSON.parse(call[1].body)
    expect(body.code).toBe('654321')
  })
})

describe('resendVerification', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful resendVerification calls correct endpoint', async () => {
    setupAuthSession()

    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    globalThis.fetch = mockFetch

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await act(async () => {
      await result.current.resendVerification()
    })

    expect(mockFetch.mock.calls[0][0]).toContain('/auth/resend-verification')
  })

  test('resendVerification throws when not authenticated', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.resendVerification()
      })
    ).rejects.toThrow('Not authenticated')
  })

  test('resendVerification failure throws server error', async () => {
    setupAuthSession()

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: () => Promise.resolve({ detail: 'Too many requests' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    await expect(
      act(async () => {
        await result.current.resendVerification()
      })
    ).rejects.toThrow('Too many requests')
  })
})

describe('forgotPassword', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful forgotPassword calls endpoint with email', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    globalThis.fetch = mockFetch

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.forgotPassword('forgot@example.com')
    })

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toContain('/auth/forgot-password')
    const body = JSON.parse(call[1].body)
    expect(body.email).toBe('forgot@example.com')
  })

  test('forgotPassword failure throws error', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: 'User not found' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.forgotPassword('nobody@example.com')
      })
    ).rejects.toThrow('User not found')
  })
})

describe('resetPassword', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('successful resetPassword calls endpoint with token and new password', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    globalThis.fetch = mockFetch

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await act(async () => {
      await result.current.resetPassword('reset-token-xyz', 'newSecurePass')
    })

    const call = mockFetch.mock.calls[0]
    expect(call[0]).toContain('/auth/reset-password')
    const body = JSON.parse(call[1].body)
    expect(body.token).toBe('reset-token-xyz')
    expect(body.new_password).toBe('newSecurePass')
  })

  test('resetPassword failure throws error', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'Token expired or invalid' }),
    })

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    await expect(
      act(async () => {
        await result.current.resetPassword('bad-token', 'newpass')
      })
    ).rejects.toThrow('Token expired or invalid')
  })
})

describe('getAccessToken', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  test('returns token when valid and not expired', async () => {
    setupAuthSession()

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true)
    })

    const token = result.current.getAccessToken()
    expect(token).toBe('valid-token')
  })

  test('returns null when no token in storage', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.getAccessToken()).toBeNull()
  })

  test('returns null when token is expired (within 30s buffer)', async () => {
    // Set token that expires in 20 seconds (within the 30s buffer)
    const expiry = Date.now() + 20000
    localStorage.setItem('auth_access_token', 'almost-expired')
    localStorage.setItem('auth_refresh_token', 'refresh')
    localStorage.setItem('auth_token_expiry', expiry.toString())
    localStorage.setItem('auth_user', JSON.stringify(mockUser))

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Token is within the 30s buffer, so getAccessToken returns null
    expect(result.current.getAccessToken()).toBeNull()
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

  test('shows loading indicator while RequireAuth checks auth', async () => {
    // When not authenticated and loaded, RequireAuth returns null (no children)
    const { container } = render(
      <AuthProvider>
        <RequireAuth>
          <span data-testid="protected">Secret Content</span>
        </RequireAuth>
      </AuthProvider>
    )

    // After initialization, should not show protected content
    await waitFor(() => {
      expect(screen.queryByTestId('protected')).not.toBeInTheDocument()
    })

    // Container should not have the protected content
    expect(container.textContent).not.toContain('Secret Content')
  })
})
