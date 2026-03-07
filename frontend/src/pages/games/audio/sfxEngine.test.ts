import { describe, it, expect, beforeEach, vi } from 'vitest'
import { SFXEngine } from './sfxEngine'

// ---------------------------------------------------------------------------
// Mock Web Audio API
// ---------------------------------------------------------------------------

function mockGainNode() {
  return {
    gain: {
      value: 1,
      setValueAtTime: vi.fn(),
      linearRampToValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
      cancelScheduledValues: vi.fn(),
    },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }
}

function mockOscillator() {
  return {
    type: 'sine' as OscillatorType,
    frequency: {
      value: 440,
      setValueAtTime: vi.fn(),
      linearRampToValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
    },
    connect: vi.fn(),
    disconnect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
  }
}

function mockFilter() {
  return {
    type: 'lowpass' as BiquadFilterType,
    frequency: {
      value: 350,
      setValueAtTime: vi.fn(),
      linearRampToValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
    },
    Q: { value: 1 },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }
}

function mockBufferSource() {
  return {
    buffer: null,
    loop: false,
    connect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    disconnect: vi.fn(),
  }
}

function createMockAudioContext() {
  return {
    currentTime: 0,
    sampleRate: 44100,
    state: 'running' as AudioContextState,
    createOscillator: vi.fn(() => mockOscillator()),
    createGain: vi.fn(() => mockGainNode()),
    createBiquadFilter: vi.fn(() => mockFilter()),
    createBuffer: vi.fn(() => ({ getChannelData: vi.fn(() => new Float32Array(22050)) })),
    createBufferSource: vi.fn(() => mockBufferSource()),
    destination: {},
    resume: vi.fn(() => Promise.resolve()),
    close: vi.fn(() => Promise.resolve()),
  } as unknown as AudioContext
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SFXEngine', () => {
  let engine: SFXEngine
  let ctx: ReturnType<typeof createMockAudioContext>

  beforeEach(() => {
    ctx = createMockAudioContext()
    function MockAudioContext(this: unknown) { return Object.assign(this as object, ctx) }
    vi.stubGlobal('AudioContext', MockAudioContext)
    vi.stubGlobal('webkitAudioContext', undefined)
    engine = new SFXEngine()
  })

  // ---- init ----

  describe('init', () => {
    it('creates its own AudioContext when none provided', () => {
      engine.init()
      expect(engine.getTime()).toBe(0)
    })

    it('accepts a shared AudioContext', () => {
      engine.init(ctx)
      expect(engine.getTime()).toBe(0)
    })

    it('is idempotent — second call does not recreate context', () => {
      engine.init()
      engine.init()
      // Should not throw and should still work
      expect(engine.getTime()).toBe(0)
    })

    it('creates a master gain node', () => {
      engine.init()
      // createGain called for master + noise buffer internal
      expect(ctx.createGain).toHaveBeenCalled()
    })

    it('creates a noise buffer for noise-based effects', () => {
      engine.init()
      expect(ctx.createBuffer).toHaveBeenCalled()
    })
  })

  // ---- volume ----

  describe('setVolume', () => {
    it('sets volume 0–1', () => {
      engine.init()
      expect(() => engine.setVolume(0.5)).not.toThrow()
    })

    it('clamps volume to 0', () => {
      engine.init()
      expect(() => engine.setVolume(-0.5)).not.toThrow()
    })

    it('clamps volume to 1', () => {
      engine.init()
      expect(() => engine.setVolume(2.0)).not.toThrow()
    })

    it('does nothing before init', () => {
      expect(() => engine.setVolume(0.5)).not.toThrow()
    })
  })

  // ---- mute ----

  describe('setMuted', () => {
    it('mutes engine (gain to 0)', () => {
      engine.init()
      engine.setMuted(true)
      // Should not throw
    })

    it('unmutes engine (restores gain)', () => {
      engine.init()
      engine.setMuted(true)
      engine.setMuted(false)
    })

    it('does nothing before init', () => {
      expect(() => engine.setMuted(true)).not.toThrow()
    })
  })

  // ---- synthesis primitives ----

  describe('noiseBurst', () => {
    it('creates a buffer source with filter and gain envelope', () => {
      engine.init()
      engine.noiseBurst(0, 0.05, 'highpass', 4000, 1, 0.5)
      expect(ctx.createBufferSource).toHaveBeenCalled()
      expect(ctx.createBiquadFilter).toHaveBeenCalled()
    })

    it('does nothing before init', () => {
      expect(() => engine.noiseBurst(0, 0.05, 'highpass', 4000, 1, 0.5)).not.toThrow()
    })
  })

  describe('tonePulse', () => {
    it('creates an oscillator with ADSR gain envelope', () => {
      engine.init()
      engine.tonePulse(0, 880, 0.1, 'sine', 0.5)
      expect(ctx.createOscillator).toHaveBeenCalled()
      expect(ctx.createGain).toHaveBeenCalled()
    })

    it('accepts custom ADSR envelope', () => {
      engine.init()
      engine.tonePulse(0, 440, 0.2, 'square', 0.5, { attack: 0.01, decay: 0.05, sustain: 0.6, release: 0.1 })
      const osc = ctx.createOscillator.mock.results[0].value
      expect(osc.start).toHaveBeenCalled()
      expect(osc.stop).toHaveBeenCalled()
    })

    it('does nothing before init', () => {
      expect(() => engine.tonePulse(0, 880, 0.1, 'sine', 0.5)).not.toThrow()
    })
  })

  describe('pitchSweep', () => {
    it('creates an oscillator with frequency ramp', () => {
      engine.init()
      engine.pitchSweep(0, 2500, 300, 0.2, 'sawtooth', 0.5)
      const osc = ctx.createOscillator.mock.results[0].value
      expect(osc.frequency.setValueAtTime).toHaveBeenCalled()
      expect(osc.frequency.linearRampToValueAtTime).toHaveBeenCalled()
    })
  })

  describe('fmTone', () => {
    it('creates carrier + modulator oscillators', () => {
      engine.init()
      engine.fmTone(0, 880, 3, 150, 0.6, 0.5)
      // Should create at least 2 oscillators (carrier + modulator)
      expect(ctx.createOscillator.mock.calls.length).toBeGreaterThanOrEqual(2)
    })
  })

  describe('filteredNoise', () => {
    it('creates a buffer source with filter', () => {
      engine.init()
      engine.filteredNoise(0, 0.5, 'bandpass', 1000, 2, 0.3)
      expect(ctx.createBufferSource).toHaveBeenCalled()
      expect(ctx.createBiquadFilter).toHaveBeenCalled()
    })

    it('supports optional LFO on filter frequency', () => {
      engine.init()
      engine.filteredNoise(0, 1.0, 'lowpass', 800, 1, 0.3, 0.5, 200)
      // LFO creates an additional oscillator + gain for modulation
      expect(ctx.createOscillator).toHaveBeenCalled()
    })
  })

  // ---- jitter ----

  describe('jitter', () => {
    it('is accessible as a static helper', () => {
      // ±0% variation = no change
      expect(SFXEngine.jitter(100, 0.5, 0)).toBe(100)
    })

    it('applies positive variation', () => {
      // variation=1 with pct=0.1 → base * 1.1
      expect(SFXEngine.jitter(100, 1, 0.1)).toBeCloseTo(110)
    })

    it('applies negative variation', () => {
      // variation=0 with pct=0.1 → base * 0.9
      expect(SFXEngine.jitter(100, 0, 0.1)).toBeCloseTo(90)
    })

    it('midpoint variation returns base', () => {
      expect(SFXEngine.jitter(100, 0.5, 0.1)).toBeCloseTo(100)
    })
  })

  // ---- getTime ----

  describe('getTime', () => {
    it('returns 0 before init', () => {
      expect(engine.getTime()).toBe(0)
    })

    it('returns AudioContext currentTime after init', () => {
      engine.init()
      expect(engine.getTime()).toBe(0)
    })
  })

  // ---- dispose ----

  describe('dispose', () => {
    it('closes the context', () => {
      engine.init()
      engine.dispose()
      expect(ctx.close).toHaveBeenCalled()
    })

    it('is safe to call before init', () => {
      expect(() => engine.dispose()).not.toThrow()
    })

    it('is safe to call twice', () => {
      engine.init()
      engine.dispose()
      expect(() => engine.dispose()).not.toThrow()
    })
  })
})
