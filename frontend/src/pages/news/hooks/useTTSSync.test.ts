/**
 * Tests for useTTSSync volume control
 *
 * Verifies that setVolume applies via Web Audio API GainNode (for iOS compatibility),
 * falls back to audio.volume when AudioContext is unavailable,
 * and that initial volume is restored from localStorage.
 */

import { describe, test, expect, beforeEach, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTTSSync } from './useTTSSync'

// Mock authFetch — not needed for volume tests but required by the module
vi.mock('../../../services/api', () => ({
  authFetch: vi.fn(),
}))

// Track mock instances
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

interface MockGainNode {
  gain: { value: number }
  connect: ReturnType<typeof vi.fn>
}

let mockAudioInstances: MockAudio[] = []
let mockGainNodes: MockGainNode[] = []

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

function setupMocks(withAudioContext: boolean) {
  mockAudioInstances = []
  mockGainNodes = []
  localStorage.clear()
  vi.restoreAllMocks()

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  vi.stubGlobal('Audio', function (this: any) {
    return createMockAudio()
  })

  if (withAudioContext) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.stubGlobal('AudioContext', function (this: any) {
      const gainNode: MockGainNode = {
        gain: { value: 1.0 },
        connect: vi.fn(),
      }
      mockGainNodes.push(gainNode)
      return {
        state: 'running',
        createMediaElementSource: vi.fn(() => ({ connect: vi.fn() })),
        createGain: vi.fn(() => gainNode),
        destination: {},
        resume: vi.fn().mockResolvedValue(undefined),
        close: vi.fn().mockResolvedValue(undefined),
      }
    })
  } else {
    // No AudioContext — force fallback to audio.volume
    vi.stubGlobal('AudioContext', undefined)
  }

  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1))
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('useTTSSync volume control (with Web Audio API)', () => {
  beforeEach(() => setupMocks(true))

  test('setVolume sets GainNode gain value', () => {
    const { result } = renderHook(() => useTTSSync())

    expect(mockGainNodes).toHaveLength(1)
    const gainNode = mockGainNodes[0]

    // Default volume
    expect(result.current.volume).toBe(1.0)
    expect(gainNode.gain.value).toBe(1.0)

    act(() => {
      result.current.setVolume(0.5)
    })

    expect(result.current.volume).toBe(0.5)
    expect(gainNode.gain.value).toBe(0.5)
  })

  test('initial volume from localStorage is applied to GainNode', () => {
    localStorage.setItem('tts-volume', '0.7')

    const { result } = renderHook(() => useTTSSync())
    const gainNode = mockGainNodes[0]

    expect(result.current.volume).toBe(0.7)
    expect(gainNode.gain.value).toBe(0.7)
  })

  test('setVolume clamps value to [0, 1]', () => {
    const { result } = renderHook(() => useTTSSync())
    const gainNode = mockGainNodes[0]

    act(() => {
      result.current.setVolume(1.5)
    })
    expect(result.current.volume).toBe(1.0)
    expect(gainNode.gain.value).toBe(1.0)

    act(() => {
      result.current.setVolume(-0.5)
    })
    expect(result.current.volume).toBe(0.0)
    expect(gainNode.gain.value).toBe(0.0)
  })

  test('setVolume to 0 mutes via GainNode', () => {
    const { result } = renderHook(() => useTTSSync())
    const gainNode = mockGainNodes[0]

    act(() => {
      result.current.setVolume(0)
    })

    expect(result.current.volume).toBe(0)
    expect(gainNode.gain.value).toBe(0)
  })

  test('setVolume persists to localStorage', () => {
    const { result } = renderHook(() => useTTSSync())

    act(() => {
      result.current.setVolume(0.3)
    })

    expect(localStorage.getItem('tts-volume')).toBe('0.3')
  })
})

describe('useTTSSync volume control (fallback without Web Audio API)', () => {
  beforeEach(() => setupMocks(false))

  test('setVolume falls back to audio.volume without AudioContext', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    expect(result.current.volume).toBe(1.0)
    expect(audio.volume).toBe(1.0)

    act(() => {
      result.current.setVolume(0.5)
    })

    expect(result.current.volume).toBe(0.5)
    expect(audio.volume).toBe(0.5)
  })

  test('initial volume from localStorage applied to audio.volume', () => {
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
})
