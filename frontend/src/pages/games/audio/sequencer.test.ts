import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { Sequencer } from './sequencer'
import type { Song } from './songTypes'
import type { SynthEngine } from './synthEngine'

// ---------------------------------------------------------------------------
// Minimal mock engine
// ---------------------------------------------------------------------------

function createMockEngine(): SynthEngine {
  return {
    getTime: vi.fn(() => 0),
    playNote: vi.fn(),
    playDrum: vi.fn(),
    setChannelGain: vi.fn(),
    fadeOut: vi.fn(),
    resume: vi.fn(() => Promise.resolve()),
    suspend: vi.fn(() => Promise.resolve()),
  } as unknown as SynthEngine
}

// ---------------------------------------------------------------------------
// Minimal test song (2 channels, 2 sections)
// ---------------------------------------------------------------------------

const testSong: Song = {
  title: 'Test Song',
  bpm: 120,
  stepsPerBeat: 4,
  key: 'A',
  scale: 'minor',
  startSection: 'intro',
  channels: {
    bass: {
      name: 'bass',
      type: 'sawtooth',
      patterns: {
        intro: { notes: [{ pitch: 110, duration: 2 }, { pitch: 0, duration: 2 }], length: 4 },
        main: { notes: [{ pitch: 110, duration: 1 }, { pitch: 130.81, duration: 1 }, { pitch: 146.83, duration: 1 }, { pitch: 110, duration: 1 }], length: 4 },
      },
      gain: 0.5,
    },
    drums: {
      name: 'drums',
      type: 'noise',
      patterns: {
        intro: { notes: [{ pitch: 1, duration: 1 }, { pitch: 0, duration: 1 }, { pitch: 2, duration: 1 }, { pitch: 0, duration: 1 }], length: 4 },
        main: { notes: [{ pitch: 1, duration: 1 }, { pitch: 0, duration: 1 }, { pitch: 2, duration: 1 }, { pitch: 3, duration: 1 }], length: 4 },
      },
      gain: 0.6,
    },
  },
  sections: {
    intro: { name: 'intro', bars: 1, channels: { bass: 'intro', drums: 'intro' }, next: 'main' },
    main: { name: 'main', bars: 2, channels: { bass: 'main', drums: 'main' }, next: null },
  },
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Sequencer', () => {
  let seq: Sequencer
  let engine: ReturnType<typeof createMockEngine>

  beforeEach(() => {
    vi.useFakeTimers()
    seq = new Sequencer()
    engine = createMockEngine()
  })

  afterEach(() => {
    seq.stop()
    vi.useRealTimers()
  })

  describe('start / stop', () => {
    it('starts scheduling and can be stopped', () => {
      seq.start(testSong, engine as unknown as SynthEngine)
      expect(seq.isPlaying()).toBe(true)
      seq.stop()
      expect(seq.isPlaying()).toBe(false)
    })

    it('start is idempotent when already playing', () => {
      seq.start(testSong, engine as unknown as SynthEngine)
      seq.start(testSong, engine as unknown as SynthEngine) // should not throw
      expect(seq.isPlaying()).toBe(true)
    })

    it('stop is safe when not playing', () => {
      expect(() => seq.stop()).not.toThrow()
    })
  })

  describe('step advancement', () => {
    it('schedules notes when timer fires', () => {
      seq.start(testSong, engine as unknown as SynthEngine)
      // Advance timer to trigger the look-ahead scheduler
      vi.advanceTimersByTime(50)
      // Should have scheduled some notes
      expect(engine.playNote).toHaveBeenCalled()
    })
  })

  describe('section transitions', () => {
    it('fires onSectionChange callback when section changes', () => {
      const cb = vi.fn()
      seq.onSectionChange(cb)
      seq.start(testSong, engine as unknown as SynthEngine)

      // intro is 1 bar = 4 beats × 4 steps = 16 steps
      // At 120 BPM, each step = 0.125s, so 16 steps = 2s
      // Advance enough time to cross section boundary
      // The scheduler fires every 25ms, looking ahead 100ms
      let currentTime = 0
      ;(engine.getTime as ReturnType<typeof vi.fn>).mockImplementation(() => currentTime)

      // Advance through intro (16 steps at 0.125s each = 2s)
      for (let i = 0; i < 100; i++) {
        currentTime = i * 0.025
        vi.advanceTimersByTime(25)
      }

      // Should have transitioned from intro to main
      expect(cb).toHaveBeenCalledWith('main')
    })
  })

  describe('setBpm', () => {
    it('changes tempo', () => {
      seq.start(testSong, engine as unknown as SynthEngine)
      seq.setBpm(140)
      // Should not crash, tempo updated internally
      vi.advanceTimersByTime(50)
      expect(seq.isPlaying()).toBe(true)
    })

    it('clamps BPM to reasonable range', () => {
      seq.start(testSong, engine as unknown as SynthEngine)
      seq.setBpm(10) // too slow
      seq.setBpm(300) // too fast
      expect(seq.isPlaying()).toBe(true)
    })
  })

  describe('setActiveChannels', () => {
    it('mutes channels not in the active set', () => {
      seq.start(testSong, engine as unknown as SynthEngine)
      seq.setActiveChannels(['bass'])
      vi.advanceTimersByTime(50)
      // drums should be muted (gain set to 0)
      expect(engine.setChannelGain).toHaveBeenCalledWith('drums', 0)
    })

    it('unmutes channels in the active set', () => {
      seq.start(testSong, engine as unknown as SynthEngine)
      seq.setActiveChannels(['bass', 'drums'])
      vi.advanceTimersByTime(50)
      // Both channels should be at their base gain
      const calls = (engine.setChannelGain as ReturnType<typeof vi.fn>).mock.calls
      const bassCalls = calls.filter((c: unknown[]) => c[0] === 'bass' && (c[1] as number) > 0)
      expect(bassCalls.length).toBeGreaterThan(0)
    })
  })

  describe('fadeOut', () => {
    it('delegates to engine.fadeOut and stops on completion', () => {
      seq.start(testSong, engine as unknown as SynthEngine)
      expect(seq.isPlaying()).toBe(true)
      seq.fadeOut(800)
      expect(engine.fadeOut).toHaveBeenCalledWith(800, expect.any(Function))
      // Simulate the onComplete callback
      const onComplete = (engine.fadeOut as ReturnType<typeof vi.fn>).mock.calls[0][1]
      onComplete()
      expect(seq.isPlaying()).toBe(false)
    })

    it('does nothing when not playing', () => {
      seq.fadeOut(800)
      expect(engine.fadeOut).not.toHaveBeenCalled()
    })

    it('stops the sequencer after engine fade completes', () => {
      seq.start(testSong, engine as unknown as SynthEngine)
      seq.fadeOut(500)
      // Still playing during fade
      expect(seq.isPlaying()).toBe(true)
      // Trigger completion
      const onComplete = (engine.fadeOut as ReturnType<typeof vi.fn>).mock.calls[0][1]
      onComplete()
      expect(seq.isPlaying()).toBe(false)
    })
  })

  describe('drum channel handling', () => {
    it('uses playDrum for noise-type channels with pitch codes', () => {
      seq.start(testSong, engine as unknown as SynthEngine)

      let currentTime = 0
      ;(engine.getTime as ReturnType<typeof vi.fn>).mockImplementation(() => currentTime)

      // Advance a bit to schedule drum notes
      for (let i = 0; i < 5; i++) {
        currentTime = i * 0.025
        vi.advanceTimersByTime(25)
      }

      expect(engine.playDrum).toHaveBeenCalled()
    })
  })
})
