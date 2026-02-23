/**
 * Tests for useTTSSync volume control
 *
 * Verifies that setVolume directly applies to the audio element,
 * clamps values, persists to localStorage, and restores on init.
 */

import { describe, test, expect, beforeEach, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTTSSync } from './useTTSSync'

vi.mock('../../../services/api', () => ({
  authFetch: vi.fn(),
}))

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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  vi.stubGlobal('Audio', function (this: any) {
    return createMockAudio()
  })
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
    const audio = mockAudioInstances[0]

    expect(result.current.volume).toBe(1.0)
    expect(audio.volume).toBe(1.0)

    act(() => { result.current.setVolume(0.5) })

    expect(result.current.volume).toBe(0.5)
    expect(audio.volume).toBe(0.5)
  })

  test('setVolume clamps to [0, 1]', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    act(() => { result.current.setVolume(1.5) })
    expect(result.current.volume).toBe(1.0)
    expect(audio.volume).toBe(1.0)

    act(() => { result.current.setVolume(-0.5) })
    expect(result.current.volume).toBe(0.0)
    expect(audio.volume).toBe(0.0)
  })

  test('setVolume persists to localStorage', () => {
    const { result } = renderHook(() => useTTSSync())

    act(() => { result.current.setVolume(0.3) })

    expect(localStorage.getItem('tts-volume')).toBe('0.3')
  })

  test('initial volume restored from localStorage', () => {
    localStorage.setItem('tts-volume', '0.7')

    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    expect(result.current.volume).toBe(0.7)
    expect(audio.volume).toBe(0.7)
  })

  test('default volume is 1.0', () => {
    const { result } = renderHook(() => useTTSSync())
    expect(result.current.volume).toBe(1.0)
    expect(mockAudioInstances[0].volume).toBe(1.0)
  })

  test('setVolume to 0 mutes audio', () => {
    const { result } = renderHook(() => useTTSSync())

    act(() => { result.current.setVolume(0) })

    expect(result.current.volume).toBe(0)
    expect(mockAudioInstances[0].volume).toBe(0)
  })
})
