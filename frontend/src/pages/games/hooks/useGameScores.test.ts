/**
 * Tests for useGameScores hook.
 *
 * Tests localStorage-based high score persistence.
 */

import { describe, test, expect, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useGameScores } from './useGameScores'

describe('useGameScores', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  test('getHighScore returns null when no score saved', () => {
    const { result } = renderHook(() => useGameScores())
    expect(result.current.getHighScore('tic-tac-toe')).toBeNull()
  })

  test('saveScore stores a score and getHighScore retrieves it', () => {
    const { result } = renderHook(() => useGameScores())
    act(() => {
      result.current.saveScore('tic-tac-toe', 100)
    })
    expect(result.current.getHighScore('tic-tac-toe')).toBe(100)
  })

  test('saveScore updates high score when new score is higher', () => {
    const { result } = renderHook(() => useGameScores())
    act(() => {
      result.current.saveScore('2048', 500)
    })
    act(() => {
      result.current.saveScore('2048', 1000)
    })
    expect(result.current.getHighScore('2048')).toBe(1000)
  })

  test('saveScore does not overwrite high score when new score is lower', () => {
    const { result } = renderHook(() => useGameScores())
    act(() => {
      result.current.saveScore('2048', 1000)
    })
    act(() => {
      result.current.saveScore('2048', 500)
    })
    expect(result.current.getHighScore('2048')).toBe(1000)
  })

  test('scores for different games are independent', () => {
    const { result } = renderHook(() => useGameScores())
    act(() => {
      result.current.saveScore('snake', 50)
      result.current.saveScore('2048', 2048)
    })
    expect(result.current.getHighScore('snake')).toBe(50)
    expect(result.current.getHighScore('2048')).toBe(2048)
  })

  test('getAllScores returns all saved scores', () => {
    const { result } = renderHook(() => useGameScores())
    act(() => {
      result.current.saveScore('snake', 50)
      result.current.saveScore('2048', 2048)
    })
    const all = result.current.getAllScores()
    expect(all['snake']).toBe(50)
    expect(all['2048']).toBe(2048)
  })

  test('clearScore removes a specific game score', () => {
    const { result } = renderHook(() => useGameScores())
    act(() => {
      result.current.saveScore('snake', 50)
      result.current.saveScore('2048', 2048)
    })
    act(() => {
      result.current.clearScore('snake')
    })
    expect(result.current.getHighScore('snake')).toBeNull()
    expect(result.current.getHighScore('2048')).toBe(2048)
  })

  test('handles localStorage errors gracefully', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Storage unavailable')
    })
    const { result } = renderHook(() => useGameScores())
    expect(result.current.getHighScore('tic-tac-toe')).toBeNull()
  })
})
