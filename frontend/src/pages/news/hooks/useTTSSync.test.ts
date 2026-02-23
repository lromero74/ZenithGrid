/**
 * Tests for useTTSSync hook
 *
 * Verifies volume control, playback controls, seeking, rate/voice changes,
 * getPlaybackState, setVolumeImmediate, and default options.
 * The persistent Audio element and authFetch are mocked.
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

describe('useTTSSync setVolumeImmediate', () => {
  test('sets audio element volume without updating React state', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    act(() => { result.current.setVolumeImmediate(0.4) })

    // Audio element should be updated
    expect(audio.volume).toBe(0.4)
    // React state should NOT be updated (it stays at initial)
    expect(result.current.volume).toBe(1.0)
  })

  test('setVolumeImmediate clamps to [0, 1]', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    act(() => { result.current.setVolumeImmediate(2.0) })
    expect(audio.volume).toBe(1.0)

    act(() => { result.current.setVolumeImmediate(-1.0) })
    expect(audio.volume).toBe(0.0)
  })

  test('setVolumeImmediate does not persist to localStorage', () => {
    const { result } = renderHook(() => useTTSSync())

    act(() => { result.current.setVolumeImmediate(0.6) })

    expect(localStorage.getItem('tts-volume')).toBeNull()
  })
})

describe('useTTSSync default options', () => {
  test('uses default voice "aria"', () => {
    const { result } = renderHook(() => useTTSSync())
    expect(result.current.currentVoice).toBe('aria')
  })

  test('uses default rate 1.0', () => {
    const { result } = renderHook(() => useTTSSync())
    expect(result.current.playbackRate).toBe(1.0)
  })

  test('accepts custom default voice', () => {
    const { result } = renderHook(() => useTTSSync({ defaultVoice: 'nova' }))
    expect(result.current.currentVoice).toBe('nova')
  })

  test('accepts custom default rate', () => {
    const { result } = renderHook(() => useTTSSync({ defaultRate: 1.5 }))
    expect(result.current.playbackRate).toBe(1.5)
    expect(mockAudioInstances[0].playbackRate).toBe(1.5)
  })
})

describe('useTTSSync setVoice', () => {
  test('changes current voice', () => {
    const { result } = renderHook(() => useTTSSync())
    expect(result.current.currentVoice).toBe('aria')

    act(() => { result.current.setVoice('nova') })
    expect(result.current.currentVoice).toBe('nova')
  })
})

describe('useTTSSync setRate', () => {
  test('changes playback rate on audio element', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    act(() => { result.current.setRate(2.0) })

    expect(result.current.playbackRate).toBe(2.0)
    expect(audio.playbackRate).toBe(2.0)
  })
})

describe('useTTSSync initial state', () => {
  test('starts in non-playing, non-loading state', () => {
    const { result } = renderHook(() => useTTSSync())

    expect(result.current.isLoading).toBe(false)
    expect(result.current.isPlaying).toBe(false)
    expect(result.current.isPaused).toBe(false)
    expect(result.current.isReady).toBe(false)
    expect(result.current.error).toBeNull()
    expect(result.current.words).toEqual([])
    expect(result.current.currentWordIndex).toBe(-1)
    expect(result.current.currentTime).toBe(0)
    expect(result.current.duration).toBe(0)
  })
})

describe('useTTSSync getPlaybackState', () => {
  test('returns currentTime and duration from audio element', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    audio.currentTime = 5.5
    audio.duration = 120.0

    const state = result.current.getPlaybackState()
    expect(state.currentTime).toBe(5.5)
    expect(state.duration).toBe(120.0)
  })

  test('returns 0 for duration when NaN', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    audio.duration = NaN

    const state = result.current.getPlaybackState()
    expect(state.duration).toBe(0)
  })
})

describe('useTTSSync pause', () => {
  test('calls audio.pause when audio is not paused', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]
    audio.paused = false

    act(() => { result.current.pause() })

    expect(audio.pause).toHaveBeenCalled()
  })

  test('does not call audio.pause when already paused', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]
    audio.paused = true

    act(() => { result.current.pause() })

    expect(audio.pause).not.toHaveBeenCalled()
  })
})

describe('useTTSSync stop', () => {
  test('resets all state to initial values', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    act(() => { result.current.stop() })

    expect(audio.pause).toHaveBeenCalled()
    expect(audio.currentTime).toBe(0)
    expect(result.current.isPlaying).toBe(false)
    expect(result.current.isPaused).toBe(false)
    expect(result.current.isLoading).toBe(false)
    expect(result.current.isReady).toBe(false)
    expect(result.current.currentWordIndex).toBe(-1)
    expect(result.current.currentTime).toBe(0)
    expect(result.current.duration).toBe(0)
    expect(result.current.words).toEqual([])
    expect(result.current.error).toBeNull()
  })

  test('sets audio source to silent WAV', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    act(() => { result.current.stop() })

    expect(audio.src).toContain('data:audio/wav;base64,')
  })
})

describe('useTTSSync replay', () => {
  test('resets currentTime to 0 and plays', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]
    audio.currentTime = 30.0
    audio.paused = true

    act(() => { result.current.replay() })

    expect(audio.currentTime).toBe(0)
    expect(audio.play).toHaveBeenCalled()
  })

  test('does not call play when audio is already playing', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]
    audio.paused = false

    act(() => { result.current.replay() })

    expect(audio.currentTime).toBe(0)
    expect(audio.play).not.toHaveBeenCalled()
  })
})

describe('useTTSSync audio event handlers', () => {
  test('onended resets playing state', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    // Simulate play then ended
    act(() => {
      audio.onplay?.()
    })
    expect(result.current.isPlaying).toBe(true)

    act(() => {
      audio.onended?.()
    })
    expect(result.current.isPlaying).toBe(false)
    expect(result.current.isPaused).toBe(false)
    expect(result.current.currentWordIndex).toBe(-1)
  })

  test('onpause sets paused state when not ended', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]
    audio.ended = false

    act(() => {
      audio.onpause?.()
    })

    expect(result.current.isPaused).toBe(true)
    expect(result.current.isPlaying).toBe(false)
  })

  test('onloadedmetadata sets duration', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]
    audio.duration = 45.5

    act(() => {
      audio.onloadedmetadata?.()
    })

    expect(result.current.duration).toBe(45.5)
  })

  test('ontimeupdate updates currentTime', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]
    audio.currentTime = 10.2
    audio.paused = true

    act(() => {
      audio.ontimeupdate?.()
    })

    expect(result.current.currentTime).toBe(10.2)
  })

  test('onplay sets isPlaying and clears error/loading', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    act(() => {
      audio.onplay?.()
    })

    expect(result.current.isPlaying).toBe(true)
    expect(result.current.isPaused).toBe(false)
    expect(result.current.isLoading).toBe(false)
    expect(result.current.error).toBeNull()
  })
})

describe('useTTSSync resume', () => {
  test('calls play when audio is paused and hook is in isPaused state', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    // Simulate pause state
    audio.paused = true
    audio.ended = false
    act(() => { audio.onpause?.() })
    expect(result.current.isPaused).toBe(true)

    act(() => { result.current.resume() })
    expect(audio.play).toHaveBeenCalled()
  })

  test('does not call play when not in isPaused state', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]
    audio.paused = true

    // isPaused is false by default
    act(() => { result.current.resume() })
    expect(audio.play).not.toHaveBeenCalled()
  })
})

describe('useTTSSync play (isReady)', () => {
  test('does not call play when isReady is false', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    // isReady is false by default
    act(() => { result.current.play() })
    expect(audio.play).not.toHaveBeenCalled()
  })
})

describe('useTTSSync seekToTime', () => {
  test('seeks directly when no words are available', () => {
    const { result } = renderHook(() => useTTSSync())
    const audio = mockAudioInstances[0]

    act(() => { result.current.seekToTime(15.5) })

    expect(audio.currentTime).toBe(15.5)
    expect(result.current.currentTime).toBe(15.5)
  })
})

describe('useTTSSync skipWords', () => {
  test('does nothing when no words or audio', () => {
    const { result } = renderHook(() => useTTSSync())

    // Should not throw
    act(() => { result.current.skipWords(5) })
  })
})

describe('useTTSSync seekToWord', () => {
  test('does nothing when no words available', () => {
    const { result } = renderHook(() => useTTSSync())

    // Should not throw
    act(() => { result.current.seekToWord(3) })
  })
})
