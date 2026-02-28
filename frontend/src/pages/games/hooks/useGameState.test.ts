/**
 * Tests for useGameState hook and standalone functions
 *
 * Verifies localStorage-based game state persistence,
 * debounced saves, load/save/clear operations, and unmount cleanup.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useGameState, loadGameState, saveGameState, clearGameState } from './useGameState'

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

interface MockState {
  board: number[][]
  score: number
  level: number
}

const mockState: MockState = {
  board: [[1, 0], [0, 2]],
  score: 100,
  level: 3,
}

describe('loadGameState (standalone)', () => {
  test('returns null when no saved state exists', () => {
    const result = loadGameState<MockState>('chess')
    expect(result).toBeNull()
  })

  test('returns parsed state when data exists', () => {
    localStorage.setItem('zenith-games-state-chess', JSON.stringify(mockState))
    const result = loadGameState<MockState>('chess')
    expect(result).toEqual(mockState)
  })

  test('returns null on corrupted JSON', () => {
    localStorage.setItem('zenith-games-state-chess', '{broken json')
    const result = loadGameState<MockState>('chess')
    expect(result).toBeNull()
  })

  test('returns null when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Storage unavailable')
    })
    const result = loadGameState<MockState>('chess')
    expect(result).toBeNull()
  })
})

describe('saveGameState (standalone)', () => {
  test('saves state to localStorage with correct key', () => {
    saveGameState('chess', mockState)
    const stored = localStorage.getItem('zenith-games-state-chess')
    expect(JSON.parse(stored!)).toEqual(mockState)
  })

  test('does not throw when localStorage is full', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    // Should silently ignore the error
    expect(() => saveGameState('chess', mockState)).not.toThrow()
  })
})

describe('clearGameState (standalone)', () => {
  test('removes saved state from localStorage', () => {
    localStorage.setItem('zenith-games-state-chess', JSON.stringify(mockState))
    clearGameState('chess')
    expect(localStorage.getItem('zenith-games-state-chess')).toBeNull()
  })

  test('does not throw when key does not exist', () => {
    expect(() => clearGameState('nonexistent')).not.toThrow()
  })

  test('does not throw when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('Storage error')
    })
    expect(() => clearGameState('chess')).not.toThrow()
  })
})

describe('useGameState hook load', () => {
  test('load returns null when no saved state', () => {
    const { result } = renderHook(() => useGameState<MockState>('2048'))
    expect(result.current.load()).toBeNull()
  })

  test('load returns saved state', () => {
    localStorage.setItem('zenith-games-state-2048', JSON.stringify(mockState))
    const { result } = renderHook(() => useGameState<MockState>('2048'))
    expect(result.current.load()).toEqual(mockState)
  })
})

describe('useGameState hook save', () => {
  test('save writes to localStorage after debounce delay', () => {
    const { result } = renderHook(() => useGameState<MockState>('snake'))

    act(() => {
      result.current.save(mockState)
    })

    // Not written yet (debounced 300ms)
    expect(localStorage.getItem('zenith-games-state-snake')).toBeNull()

    // Advance past debounce
    act(() => { vi.advanceTimersByTime(300) })

    const stored = localStorage.getItem('zenith-games-state-snake')
    expect(JSON.parse(stored!)).toEqual(mockState)
  })

  test('save debounces rapid calls (only last state is persisted)', () => {
    const { result } = renderHook(() => useGameState<MockState>('snake'))

    act(() => {
      result.current.save({ ...mockState, score: 10 })
    })
    act(() => {
      result.current.save({ ...mockState, score: 50 })
    })
    act(() => {
      result.current.save({ ...mockState, score: 200 })
    })

    act(() => { vi.advanceTimersByTime(300) })

    const stored = JSON.parse(localStorage.getItem('zenith-games-state-snake')!)
    expect(stored.score).toBe(200) // Only last value persisted
  })
})

describe('useGameState hook clear', () => {
  test('clear removes state and cancels pending save', () => {
    const { result } = renderHook(() => useGameState<MockState>('minesweeper'))

    // Save something first
    act(() => { result.current.save(mockState) })
    act(() => { vi.advanceTimersByTime(300) })
    expect(localStorage.getItem('zenith-games-state-minesweeper')).not.toBeNull()

    // Start a new save then immediately clear
    act(() => { result.current.save({ ...mockState, score: 999 }) })
    act(() => { result.current.clear() })

    // The pending save should be canceled
    act(() => { vi.advanceTimersByTime(300) })
    expect(localStorage.getItem('zenith-games-state-minesweeper')).toBeNull()
  })
})

describe('useGameState hook unmount cleanup', () => {
  test('clears pending timer on unmount', () => {
    const { result, unmount } = renderHook(() => useGameState<MockState>('hangman'))

    act(() => {
      result.current.save(mockState)
    })

    // Unmount before debounce fires
    unmount()

    // Advance time — should NOT write because timer was cleared
    act(() => { vi.advanceTimersByTime(500) })
    expect(localStorage.getItem('zenith-games-state-hangman')).toBeNull()
  })
})

describe('useGameState different game IDs are isolated', () => {
  test('separate game IDs do not interfere', () => {
    saveGameState('chess', { score: 1 })
    saveGameState('snake', { score: 2 })

    expect(loadGameState<{ score: number }>('chess')!.score).toBe(1)
    expect(loadGameState<{ score: number }>('snake')!.score).toBe(2)

    clearGameState('chess')
    expect(loadGameState('chess')).toBeNull()
    expect(loadGameState<{ score: number }>('snake')!.score).toBe(2)
  })
})
