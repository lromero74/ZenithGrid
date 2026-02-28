/**
 * Tests for useGameTimer hook.
 *
 * Tests timer start/stop/reset and formatted output.
 */

import { describe, test, expect, beforeEach, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useGameTimer } from './useGameTimer'

describe('useGameTimer', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  test('starts at 0 seconds', () => {
    const { result } = renderHook(() => useGameTimer())
    expect(result.current.seconds).toBe(0)
    expect(result.current.formatted).toBe('0:00')
  })

  test('isRunning is false initially', () => {
    const { result } = renderHook(() => useGameTimer())
    expect(result.current.isRunning).toBe(false)
  })

  test('start begins counting', () => {
    const { result } = renderHook(() => useGameTimer())
    act(() => {
      result.current.start()
    })
    expect(result.current.isRunning).toBe(true)
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current.seconds).toBe(3)
  })

  test('stop pauses the timer', () => {
    const { result } = renderHook(() => useGameTimer())
    act(() => {
      result.current.start()
    })
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    act(() => {
      result.current.stop()
    })
    expect(result.current.isRunning).toBe(false)
    const secondsAtStop = result.current.seconds
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current.seconds).toBe(secondsAtStop)
  })

  test('reset sets timer back to 0 and stops', () => {
    const { result } = renderHook(() => useGameTimer())
    act(() => {
      result.current.start()
    })
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    act(() => {
      result.current.reset()
    })
    expect(result.current.seconds).toBe(0)
    expect(result.current.isRunning).toBe(false)
  })

  test('formatted shows minutes and seconds', () => {
    const { result } = renderHook(() => useGameTimer())
    act(() => {
      result.current.start()
    })
    act(() => {
      vi.advanceTimersByTime(65000) // 1 min 5 sec
    })
    expect(result.current.formatted).toBe('1:05')
  })

  test('formatted pads single-digit seconds', () => {
    const { result } = renderHook(() => useGameTimer())
    act(() => {
      result.current.start()
    })
    act(() => {
      vi.advanceTimersByTime(9000) // 9 seconds
    })
    expect(result.current.formatted).toBe('0:09')
  })

  test('double-start does not reset counter', () => {
    const { result } = renderHook(() => useGameTimer())
    act(() => {
      result.current.start()
    })
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    act(() => {
      result.current.start() // calling start again
    })
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    // Should be 8 seconds total, not 3
    expect(result.current.seconds).toBe(8)
  })
})
