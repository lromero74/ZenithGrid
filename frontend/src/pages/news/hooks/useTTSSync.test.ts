/**
 * Tests for useTTSSync volume control
 *
 * Verifies that setVolume directly applies to the Audio element
 * (not just React state), and that initial volume is restored from localStorage.
 */

import { describe, test, expect, beforeEach, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTTSSync } from './useTTSSync'

// Mock authFetch — not needed for volume tests but required by the module
vi.mock('../../../services/api', () => ({
  authFetch: vi.fn(),
}))

// Track Audio instances so we can inspect them
interface MockAudio {
  volume: number
  playbackRate: number
  src: string
  currentTime: number
  duration: number
  paused: boolean
  ended: boolean
  pause: ReturnType<typeof vi.fn>
  play: ReturnType<typeof vi.fn>
  addEventListener: ReturnType<typeof vi.fn>
  removeEventListener: ReturnType<typeof vi.fn>
  onplay: (() => void) | null
  onpause: (() => void) | null
  onended: (() => void) | null
  onerror: (() => void) | null
  onloadedmetadata: (() => void) | null
  ontimeupdate: (() => void) | null
}

let mockAudioInstances: MockAudio[] = []

function createMockAudio(): MockAudio {
  const instance: MockAudio = {
    volume: 1.0,
    playbackRate: 1.0,
    src: '',
    currentTime: 0,
    duration: NaN,
    paused: true,
    ended: false,
    pause: vi.fn(),
    play: vi.fn().mockResolvedValue(undefined),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    onplay: null,
    onpause: null,
    onended: null,
    onerror: null,
    onloadedmetadata: null,
    ontimeupdate: null,
  }
  mockAudioInstances.push(instance)
  return instance
}

beforeEach(() => {
  mockAudioInstances = []
  localStorage.clear()
  vi.restoreAllMocks()

  // Mock window.Audio constructor using a proper function constructor
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  vi.stubGlobal('Audio', function (this: any) {
    return createMockAudio()
  })

  // Mock requestAnimationFrame/cancelAnimationFrame
  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1))
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('useTTSSync volume control', () => {
  test('setVolume directly sets audio element volume', () => {
    const { result } = renderHook(() => useTTSSync())

    expect(mockAudioInstances).toHaveLength(1)
    const audio = mockAudioInstances[0]

    // Default volume should be 1.0
    expect(result.current.volume).toBe(1.0)
    expect(audio.volume).toBe(1.0)

    // Change volume via setVolume
    act(() => {
      result.current.setVolume(0.5)
    })

    // Both React state and audio element should update immediately
    expect(result.current.volume).toBe(0.5)
    expect(audio.volume).toBe(0.5)
  })

  test('setVolume clamps value to [0, 1]', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    // Over 1.0
    act(() => {
      result.current.setVolume(1.5)
    })
    expect(result.current.volume).toBe(1.0)
    expect(audio.volume).toBe(1.0)

    // Below 0.0
    act(() => {
      result.current.setVolume(-0.5)
    })
    expect(result.current.volume).toBe(0.0)
    expect(audio.volume).toBe(0.0)
  })

  test('setVolume persists to localStorage', () => {
    const { result } = renderHook(() => useTTSSync())

    act(() => {
      result.current.setVolume(0.3)
    })

    expect(localStorage.getItem('tts-volume')).toBe('0.3')
  })

  test('initial volume is restored from localStorage', () => {
    localStorage.setItem('tts-volume', '0.7')

    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    expect(result.current.volume).toBe(0.7)
    expect(audio.volume).toBe(0.7)
  })

  test('default volume is 1.0 when no localStorage value', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    expect(result.current.volume).toBe(1.0)
    expect(audio.volume).toBe(1.0)
  })

  test('setVolume to 0 mutes audio element', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    act(() => {
      result.current.setVolume(0)
    })

    expect(result.current.volume).toBe(0)
    expect(audio.volume).toBe(0)
  })
})
