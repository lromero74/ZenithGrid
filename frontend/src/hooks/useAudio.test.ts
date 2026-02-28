/**
 * Tests for useAudio hook.
 *
 * Verifies audio-notification preference persistence via localStorage,
 * AUDIO_CONFIGS shape exported per order type, playOrderSound behaviour
 * when audio is enabled/disabled, and AudioContext cleanup on unmount.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAudio, type OrderFillType } from './useAudio'

// ---------- AudioContext mock ----------

function createMockOscillator() {
  return {
    type: 'sine' as OscillatorType,
    frequency: { value: 0 },
    connect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
  }
}

function createMockGainNode() {
  return {
    gain: {
      value: 0,
      setValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
    },
    connect: vi.fn(),
  }
}

// Shared mock context instance used by the class below
let mockCtx: {
  currentTime: number
  state: string
  destination: object
  createOscillator: ReturnType<typeof vi.fn>
  createGain: ReturnType<typeof vi.fn>
  resume: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>
}

function freshMockCtx() {
  mockCtx = {
    currentTime: 0,
    state: 'running',
    destination: {},
    createOscillator: vi.fn(() => createMockOscillator()),
    createGain: vi.fn(() => createMockGainNode()),
    resume: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
  }
}

// A proper class that `new` can be called on
class MockAudioContext {
  currentTime: number
  state: string
  destination: object
  createOscillator: ReturnType<typeof vi.fn>
  createGain: ReturnType<typeof vi.fn>
  resume: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>

  constructor() {
    // Copy methods from the shared mock so tests can assert on them
    this.currentTime = mockCtx.currentTime
    this.state = mockCtx.state
    this.destination = mockCtx.destination
    this.createOscillator = mockCtx.createOscillator
    this.createGain = mockCtx.createGain
    this.resume = mockCtx.resume
    this.close = mockCtx.close
  }
}

// ---------- Suite ----------

describe('useAudio', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    freshMockCtx()
    vi.stubGlobal('AudioContext', MockAudioContext)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  // ---- localStorage persistence ----

  test('isAudioEnabled returns true by default when no localStorage value', () => {
    const { result } = renderHook(() => useAudio())
    expect(result.current.isAudioEnabled()).toBe(true)
  })

  test('setAudioEnabled(false) persists to localStorage and isAudioEnabled reflects it', () => {
    const { result } = renderHook(() => useAudio())

    act(() => {
      result.current.setAudioEnabled(false)
    })

    expect(result.current.isAudioEnabled()).toBe(false)
    expect(localStorage.getItem('audio-notifications-enabled')).toBe('false')
  })

  test('setAudioEnabled(true) persists to localStorage', () => {
    const { result } = renderHook(() => useAudio())

    act(() => {
      result.current.setAudioEnabled(true)
    })

    expect(result.current.isAudioEnabled()).toBe(true)
    expect(localStorage.getItem('audio-notifications-enabled')).toBe('true')
  })

  test('loads saved preference from localStorage on mount', () => {
    localStorage.setItem('audio-notifications-enabled', 'false')
    const { result } = renderHook(() => useAudio())
    expect(result.current.isAudioEnabled()).toBe(false)
  })

  test('loads true preference from localStorage on mount', () => {
    localStorage.setItem('audio-notifications-enabled', 'true')
    const { result } = renderHook(() => useAudio())
    expect(result.current.isAudioEnabled()).toBe(true)
  })

  // ---- playOrderSound ----

  test('playOrderSound creates oscillator and gain nodes for base_order', async () => {
    const { result } = renderHook(() => useAudio())

    await act(async () => {
      await result.current.playOrderSound('base_order')
    })

    // base_order has 4 tones
    expect(mockCtx.createOscillator).toHaveBeenCalledTimes(4)
    expect(mockCtx.createGain).toHaveBeenCalledTimes(4)
  })

  test('playOrderSound creates correct number of tones per order type', async () => {
    const expectedToneCounts: Record<OrderFillType, number> = {
      base_order: 4,
      dca_order: 2,
      sell_order: 3,
      partial_fill: 1,
    }

    for (const [orderType, expectedCount] of Object.entries(expectedToneCounts)) {
      // Reset mocks and context for each iteration
      freshMockCtx()
      vi.stubGlobal('AudioContext', MockAudioContext)

      const { result, unmount } = renderHook(() => useAudio())

      await act(async () => {
        await result.current.playOrderSound(orderType as OrderFillType)
      })

      expect(mockCtx.createOscillator).toHaveBeenCalledTimes(expectedCount)
      unmount()
    }
  })

  test('playOrderSound does nothing when audio is disabled', async () => {
    const { result } = renderHook(() => useAudio())

    act(() => {
      result.current.setAudioEnabled(false)
    })

    await act(async () => {
      await result.current.playOrderSound('sell_order')
    })

    expect(mockCtx.createOscillator).not.toHaveBeenCalled()
  })

  test('playOrderSound resumes suspended AudioContext', async () => {
    mockCtx.state = 'suspended'
    const { result } = renderHook(() => useAudio())

    await act(async () => {
      await result.current.playOrderSound('partial_fill')
    })

    expect(mockCtx.resume).toHaveBeenCalled()
  })

  test('playOrderSound catches errors gracefully', async () => {
    mockCtx.createOscillator.mockImplementation(() => {
      throw new Error('Audio not supported')
    })

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { result } = renderHook(() => useAudio())

    await act(async () => {
      await result.current.playOrderSound('base_order')
    })

    expect(warnSpy).toHaveBeenCalledWith('Audio playback failed:', expect.any(Error))
  })

  // ---- AudioContext cleanup ----

  test('closes AudioContext on unmount', async () => {
    const { result, unmount } = renderHook(() => useAudio())

    // Force AudioContext creation by playing a sound
    await act(async () => {
      await result.current.playOrderSound('partial_fill')
    })

    unmount()

    expect(mockCtx.close).toHaveBeenCalled()
  })

  test('does not error on unmount when AudioContext was never created', () => {
    const { unmount } = renderHook(() => useAudio())
    expect(() => unmount()).not.toThrow()
  })

  // ---- webkitAudioContext fallback ----

  test('falls back to webkitAudioContext when AudioContext is undefined', async () => {
    vi.unstubAllGlobals()
    freshMockCtx()

    // Remove AudioContext, provide webkitAudioContext
    vi.stubGlobal('AudioContext', undefined)
    ;(window as any).webkitAudioContext = MockAudioContext

    const { result } = renderHook(() => useAudio())

    await act(async () => {
      await result.current.playOrderSound('partial_fill')
    })

    expect(mockCtx.createOscillator).toHaveBeenCalled()

    // Cleanup
    delete (window as any).webkitAudioContext
  })
})
