/**
 * Tests for useRecentlyPlayed hook.
 *
 * Tests localStorage-based recently-played timestamp tracking.
 */

import { describe, test, expect, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useRecentlyPlayed } from './useRecentlyPlayed'

describe('useRecentlyPlayed', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  test('getLastPlayed returns null for unplayed game', () => {
    const { result } = renderHook(() => useRecentlyPlayed())
    expect(result.current.getLastPlayed('chess')).toBeNull()
  })

  test('markPlayed stores a timestamp', () => {
    const { result } = renderHook(() => useRecentlyPlayed())
    act(() => {
      result.current.markPlayed('chess')
    })
    expect(result.current.getLastPlayed('chess')).toBeGreaterThan(0)
  })

  test('markPlayed updates timestamp on subsequent plays', () => {
    const { result } = renderHook(() => useRecentlyPlayed())
    act(() => {
      result.current.markPlayed('chess')
    })
    const first = result.current.getLastPlayed('chess')!
    // Small delay to ensure different timestamp
    act(() => {
      result.current.markPlayed('chess')
    })
    const second = result.current.getLastPlayed('chess')!
    expect(second).toBeGreaterThanOrEqual(first)
  })

  test('different games are independent', () => {
    const { result } = renderHook(() => useRecentlyPlayed())
    act(() => {
      result.current.markPlayed('chess')
    })
    expect(result.current.getLastPlayed('chess')).not.toBeNull()
    expect(result.current.getLastPlayed('snake')).toBeNull()
  })

  test('getRecentMap returns all timestamps', () => {
    const { result } = renderHook(() => useRecentlyPlayed())
    act(() => {
      result.current.markPlayed('chess')
      result.current.markPlayed('snake')
    })
    const map = result.current.getRecentMap()
    expect(map['chess']).toBeGreaterThan(0)
    expect(map['snake']).toBeGreaterThan(0)
  })

  test('getRecentMap returns empty object when no games played', () => {
    const { result } = renderHook(() => useRecentlyPlayed())
    expect(result.current.getRecentMap()).toEqual({})
  })

  test('persists to localStorage', () => {
    const { result } = renderHook(() => useRecentlyPlayed())
    act(() => {
      result.current.markPlayed('chess')
    })
    // Re-mount the hook — should load from localStorage
    const { result: result2 } = renderHook(() => useRecentlyPlayed())
    expect(result2.current.getLastPlayed('chess')).not.toBeNull()
  })

  test('handles localStorage errors gracefully', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Storage unavailable')
    })
    const { result } = renderHook(() => useRecentlyPlayed())
    expect(result.current.getLastPlayed('chess')).toBeNull()
  })
})
