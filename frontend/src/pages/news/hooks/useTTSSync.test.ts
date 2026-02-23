/**
 * Tests for useTTSSync volume control
 *
 * Verifies that:
 * - Volume is applied via Web Audio API GainNode after lazy init (iOS support)
 * - Volume falls back to audio.volume when AudioContext is unavailable
 * - Initial volume is restored from localStorage
 * - GainNode is created lazily on first user gesture (loadAndPlay/play/resume)
 */

import { describe, test, expect, beforeEach, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTTSSync } from './useTTSSync'

// Mock authFetch
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
    vi.stubGlobal('AudioContext', undefined)
  }

  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1))
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('useTTSSync volume — with Web Audio API (lazy init)', () => {
  beforeEach(() => setupMocks(true))

  test('GainNode is NOT created on mount (lazy)', () => {
    renderHook(() => useTTSSync())
    // AudioContext should NOT be created until a user gesture
    expect(mockGainNodes).toHaveLength(0)
  })

  test('GainNode is created on first loadAndPlay call', async () => {
    const { result } = renderHook(() => useTTSSync())
    expect(mockGainNodes).toHaveLength(0)

    // loadAndPlay triggers lazy init (simulates user gesture)
    await act(async () => {
      result.current.loadAndPlay('test text')
    })

    expect(mockGainNodes).toHaveLength(1)
  })

  test('setVolume sets GainNode gain after lazy init', async () => {
    const { result } = renderHook(() => useTTSSync())

    // Trigger lazy init
    await act(async () => {
      result.current.loadAndPlay('test')
    })
    const gainNode = mockGainNodes[0]

    act(() => {
      result.current.setVolume(0.5)
    })

    expect(result.current.volume).toBe(0.5)
    expect(gainNode.gain.value).toBe(0.5)
  })

  test('setVolume before lazy init still updates audio.volume', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    // No GainNode yet — should fall back to audio.volume
    act(() => {
      result.current.setVolume(0.3)
    })

    expect(result.current.volume).toBe(0.3)
    expect(audio.volume).toBe(0.3)
  })

  test('GainNode gets current volume at creation time', async () => {
    localStorage.setItem('tts-volume', '0.4')
    const { result } = renderHook(() => useTTSSync())

    expect(result.current.volume).toBe(0.4)

    // Trigger lazy init — GainNode should pick up 0.4
    await act(async () => {
      result.current.loadAndPlay('test')
    })

    expect(mockGainNodes[0].gain.value).toBe(0.4)
  })

  test('setVolume clamps to [0, 1]', () => {
    const { result } = renderHook(() => useTTSSync())

    act(() => { result.current.setVolume(1.5) })
    expect(result.current.volume).toBe(1.0)

    act(() => { result.current.setVolume(-0.5) })
    expect(result.current.volume).toBe(0.0)
  })

  test('setVolume to 0 mutes', async () => {
    const { result } = renderHook(() => useTTSSync())

    await act(async () => { result.current.loadAndPlay('test') })
    const gainNode = mockGainNodes[0]

    act(() => { result.current.setVolume(0) })

    expect(result.current.volume).toBe(0)
    expect(gainNode.gain.value).toBe(0)
  })

  test('setVolume persists to localStorage', () => {
    const { result } = renderHook(() => useTTSSync())

    act(() => { result.current.setVolume(0.3) })

    expect(localStorage.getItem('tts-volume')).toBe('0.3')
  })
})

describe('useTTSSync volume — fallback without Web Audio API', () => {
  beforeEach(() => setupMocks(false))

  test('setVolume uses audio.volume directly', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    act(() => { result.current.setVolume(0.5) })

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

  test('default volume is 1.0', () => {
    const { result } = renderHook(() => useTTSSync())
    expect(result.current.volume).toBe(1.0)
    expect(mockAudioInstances[0].volume).toBe(1.0)
  })
})
