/**
 * Tests for usePermission hook.
 *
 * Tests RBAC permission checking against user.permissions array.
 */

import { describe, test, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePermission, useHasPermission, useIsAdmin } from './usePermission'

// Mock useAuth to control user state
const mockUseAuth = vi.fn()
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

describe('usePermission', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  test('returns true for superuser regardless of permissions', () => {
    mockUseAuth.mockReturnValue({
      user: { is_superuser: true, permissions: [] },
    })
    const { result } = renderHook(() => usePermission('bots', 'read'))
    expect(result.current).toBe(true)
  })

  test('returns true when user has matching permission', () => {
    mockUseAuth.mockReturnValue({
      user: { is_superuser: false, permissions: ['bots:read', 'bots:write'] },
    })
    const { result } = renderHook(() => usePermission('bots', 'read'))
    expect(result.current).toBe(true)
  })

  test('returns false when user lacks permission', () => {
    mockUseAuth.mockReturnValue({
      user: { is_superuser: false, permissions: ['bots:read'] },
    })
    const { result } = renderHook(() => usePermission('bots', 'write'))
    expect(result.current).toBe(false)
  })

  test('returns false when user is null', () => {
    mockUseAuth.mockReturnValue({ user: null })
    const { result } = renderHook(() => usePermission('bots', 'read'))
    expect(result.current).toBe(false)
  })

  test('returns false when permissions array is undefined', () => {
    mockUseAuth.mockReturnValue({
      user: { is_superuser: false },
    })
    const { result } = renderHook(() => usePermission('bots', 'read'))
    expect(result.current).toBe(false)
  })
})

describe('useHasPermission', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  test('checks a full permission string', () => {
    mockUseAuth.mockReturnValue({
      user: { is_superuser: false, permissions: ['admin:users'] },
    })
    const { result } = renderHook(() => useHasPermission('admin:users'))
    expect(result.current).toBe(true)
  })

  test('returns false for unmatched permission string', () => {
    mockUseAuth.mockReturnValue({
      user: { is_superuser: false, permissions: ['bots:read'] },
    })
    const { result } = renderHook(() => useHasPermission('admin:users'))
    expect(result.current).toBe(false)
  })

  test('superuser bypasses check', () => {
    mockUseAuth.mockReturnValue({
      user: { is_superuser: true, permissions: [] },
    })
    const { result } = renderHook(() => useHasPermission('admin:users'))
    expect(result.current).toBe(true)
  })
})

describe('useIsAdmin', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  test('returns true for superuser', () => {
    mockUseAuth.mockReturnValue({
      user: { is_superuser: true, permissions: [] },
    })
    const { result } = renderHook(() => useIsAdmin())
    expect(result.current).toBe(true)
  })

  test('returns true when user has any admin permission', () => {
    mockUseAuth.mockReturnValue({
      user: { is_superuser: false, permissions: ['admin:users', 'bots:read'] },
    })
    const { result } = renderHook(() => useIsAdmin())
    expect(result.current).toBe(true)
  })

  test('returns false when user has no admin permissions', () => {
    mockUseAuth.mockReturnValue({
      user: { is_superuser: false, permissions: ['bots:read', 'bots:write'] },
    })
    const { result } = renderHook(() => useIsAdmin())
    expect(result.current).toBe(false)
  })

  test('returns false when user is null', () => {
    mockUseAuth.mockReturnValue({ user: null })
    const { result } = renderHook(() => useIsAdmin())
    expect(result.current).toBe(false)
  })
})
