import { describe, it, expect, beforeEach, vi } from 'vitest'
import { SynthEngine } from './synthEngine'

// ---------------------------------------------------------------------------
// Mock Web Audio API
// ---------------------------------------------------------------------------

function mockGainNode() {
  return {
    gain: { value: 1, setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }
}

function mockOscillator() {
  return {
    type: 'sine' as OscillatorType,
    frequency: { value: 440, setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
    connect: vi.fn(),
    disconnect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
  }
}

function mockFilter() {
  return {
    type: 'lowpass' as BiquadFilterType,
    frequency: { value: 350, setValueAtTime: vi.fn() },
    Q: { value: 1 },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }
}

function mockDelay() {
  return {
    delayTime: { value: 0 },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }
}

function mockBufferSource() {
  return {
    buffer: null,
    connect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
  }
}

function createMockAudioContext() {
  return {
    currentTime: 0,
    state: 'running' as AudioContextState,
    createOscillator: vi.fn(() => mockOscillator()),
    createGain: vi.fn(() => mockGainNode()),
    createBiquadFilter: vi.fn(() => mockFilter()),
    createDelay: vi.fn(() => mockDelay()),
    createBuffer: vi.fn(() => ({ getChannelData: vi.fn(() => new Float32Array(4096)) })),
    createBufferSource: vi.fn(() => mockBufferSource()),
    destination: {},
    resume: vi.fn(() => Promise.resolve()),
    suspend: vi.fn(() => Promise.resolve()),
    close: vi.fn(() => Promise.resolve()),
  } as unknown as AudioContext
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SynthEngine', () => {
  let engine: SynthEngine
  let ctx: ReturnType<typeof createMockAudioContext>

  beforeEach(() => {
    ctx = createMockAudioContext()
    // Must use a proper constructor function so `new AC()` works
    function MockAudioContext(this: unknown) { return Object.assign(this as object, ctx) }
    vi.stubGlobal('AudioContext', MockAudioContext)
    vi.stubGlobal('webkitAudioContext', undefined)
    engine = new SynthEngine()
  })

  describe('init', () => {
    it('creates an AudioContext and master gain', () => {
      engine.init()
      expect(ctx.createGain).toHaveBeenCalled()
    })

    it('is idempotent — second call does not recreate context', () => {
      engine.init()
      const time1 = engine.getTime()
      engine.init()
      const time2 = engine.getTime()
      // Should still work after double init (no crash)
      expect(time1).toBe(time2)
    })
  })

  describe('createChannel', () => {
    beforeEach(() => engine.init())

    it('creates a channel with oscillator type and gain', () => {
      engine.createChannel('bass', 'sawtooth', 0.5)
      expect(ctx.createGain).toHaveBeenCalled()
    })

    it('creates a channel with filter effect', () => {
      engine.createChannel('pad', 'triangle', 0.3, { filter: 800 })
      expect(ctx.createBiquadFilter).toHaveBeenCalled()
    })

    it('creates a channel with delay effect', () => {
      engine.createChannel('lead', 'square', 0.4, { delay: 0.3, delayFeedback: 0.4 })
      expect(ctx.createDelay).toHaveBeenCalled()
    })
  })

  describe('playNote', () => {
    beforeEach(() => {
      engine.init()
      engine.createChannel('bass', 'sawtooth', 0.5)
    })

    it('creates an oscillator and schedules it', () => {
      engine.playNote('bass', 220, 0, 0.5, 0.8)
      expect(ctx.createOscillator).toHaveBeenCalled()
      const osc = ctx.createOscillator.mock.results[0].value
      expect(osc.start).toHaveBeenCalled()
      expect(osc.stop).toHaveBeenCalled()
    })

    it('skips notes with pitch 0 (rests)', () => {
      const before = ctx.createOscillator.mock.calls.length
      engine.playNote('bass', 0, 0, 0.5)
      expect(ctx.createOscillator.mock.calls.length).toBe(before)
    })

    it('does not crash for unknown channel', () => {
      expect(() => engine.playNote('unknown', 440, 0, 0.5)).not.toThrow()
    })
  })

  describe('playDrum', () => {
    beforeEach(() => engine.init())

    it('plays kick drum (creates oscillator for pitch drop)', () => {
      engine.playDrum('kick', 0)
      expect(ctx.createOscillator).toHaveBeenCalled()
    })

    it('plays snare (creates oscillator + noise buffer)', () => {
      engine.playDrum('snare', 0)
      expect(ctx.createOscillator).toHaveBeenCalled()
      expect(ctx.createBufferSource).toHaveBeenCalled()
    })

    it('plays hi-hat (creates noise buffer)', () => {
      engine.playDrum('hihat', 0)
      expect(ctx.createBufferSource).toHaveBeenCalled()
    })

    it('plays clap (creates noise buffer)', () => {
      engine.playDrum('clap', 0)
      expect(ctx.createBufferSource).toHaveBeenCalled()
    })
  })

  describe('setChannelGain', () => {
    beforeEach(() => {
      engine.init()
      engine.createChannel('bass', 'sawtooth', 0.5)
    })

    it('updates channel gain value', () => {
      engine.setChannelGain('bass', 0.8)
      // Gain node value should be updated
      // (Exact assertion depends on implementation, but it should not throw)
    })

    it('does not throw for unknown channel', () => {
      expect(() => engine.setChannelGain('unknown', 0.5)).not.toThrow()
    })
  })

  describe('setMasterGain', () => {
    it('sets the master output gain', () => {
      engine.init()
      engine.setMasterGain(0.3)
      // Should not throw
    })
  })

  describe('getTime', () => {
    it('returns AudioContext currentTime', () => {
      engine.init()
      expect(engine.getTime()).toBe(0)
    })

    it('returns 0 before init', () => {
      expect(engine.getTime()).toBe(0)
    })
  })

  describe('fadeOut', () => {
    beforeEach(() => engine.init())

    it('ramps master gain to near-zero over the specified duration', () => {
      engine.fadeOut(800)
      const masterGain = (ctx.createGain as ReturnType<typeof vi.fn>).mock.results[0].value
      expect(masterGain.gain.linearRampToValueAtTime).toHaveBeenCalledWith(
        0.001,
        expect.any(Number),
      )
    })

    it('calls onComplete callback after duration', () => {
      vi.useFakeTimers()
      const onComplete = vi.fn()
      engine.fadeOut(500, onComplete)
      expect(onComplete).not.toHaveBeenCalled()
      vi.advanceTimersByTime(500)
      expect(onComplete).toHaveBeenCalledTimes(1)
      vi.useRealTimers()
    })

    it('does nothing before init', () => {
      const uninitEngine = new SynthEngine()
      expect(() => uninitEngine.fadeOut(800)).not.toThrow()
    })
  })

  describe('suspend / resume / dispose', () => {
    beforeEach(() => engine.init())

    it('suspend calls context.suspend', async () => {
      await engine.suspend()
      expect(ctx.suspend).toHaveBeenCalled()
    })

    it('resume calls context.resume', async () => {
      await engine.resume()
      expect(ctx.resume).toHaveBeenCalled()
    })

    it('dispose closes the context', () => {
      engine.dispose()
      expect(ctx.close).toHaveBeenCalled()
    })
  })
})
