import { describe, it, expect } from 'vitest'
import {
  noteFreq,
  getScale,
  getScaleMultiOctave,
  getChord,
  arpeggio,
  seededArpeggio,
  getProgression,
  resolveChordSpecs,
  applySwing,
  scaleDegreeWalk,
  motifDevelop,
  callAndResponse,
  SCALES,
  CHORD_INTERVALS,
  PROGRESSIONS,
  RHYTHM_TEMPLATES,
  MOOD_SCALES,
  NOTE_NAMES,
} from './musicTheory'

// ---------------------------------------------------------------------------
// Note frequencies
// ---------------------------------------------------------------------------

describe('noteFreq', () => {
  it('returns 440 for A4', () => {
    expect(noteFreq('A', 4)).toBeCloseTo(440, 1)
  })

  it('returns 261.63 for C4 (middle C)', () => {
    expect(noteFreq('C', 4)).toBeCloseTo(261.63, 0)
  })

  it('doubles frequency each octave', () => {
    const a3 = noteFreq('A', 3)
    const a4 = noteFreq('A', 4)
    const a5 = noteFreq('A', 5)
    expect(a4 / a3).toBeCloseTo(2, 2)
    expect(a5 / a4).toBeCloseTo(2, 2)
  })

  it('handles sharps (e.g. C#4, F#3)', () => {
    expect(noteFreq('C#', 4)).toBeCloseTo(277.18, 0)
    expect(noteFreq('F#', 3)).toBeCloseTo(185.0, 0)
  })

  it('handles flats as equivalent to sharps (Bb4 = A#4)', () => {
    expect(noteFreq('Bb', 4)).toBeCloseTo(noteFreq('A#', 4), 1)
  })

  it('returns correct frequencies at extremes (octave 1 and 7)', () => {
    expect(noteFreq('A', 1)).toBeCloseTo(55, 1)
    expect(noteFreq('A', 7)).toBeCloseTo(3520, 0)
  })

  it('throws on unknown note', () => {
    expect(() => noteFreq('X', 4)).toThrow('Unknown note: X')
  })
})

// ---------------------------------------------------------------------------
// Scales & Modes
// ---------------------------------------------------------------------------

describe('SCALES', () => {
  it('has all 7 church modes', () => {
    for (const mode of ['ionian', 'dorian', 'phrygian', 'lydian', 'mixolydian', 'aeolian', 'locrian']) {
      expect(SCALES).toHaveProperty(mode)
      expect(SCALES[mode]).toHaveLength(7)
    }
  })

  it('has common aliases matching their modes', () => {
    expect(SCALES.major).toEqual(SCALES.ionian)
    expect(SCALES.minor).toEqual(SCALES.aeolian)
  })

  it('has extended modes', () => {
    expect(SCALES.harmonicMinor).toHaveLength(7)
    expect(SCALES.melodicMinor).toHaveLength(7)
    expect(SCALES.harmonicMajor).toHaveLength(7)
  })

  it('has pentatonic and blues scales', () => {
    expect(SCALES.pentatonic).toHaveLength(5)
    expect(SCALES.majorPentatonic).toHaveLength(5)
    expect(SCALES.blues).toHaveLength(6)
    expect(SCALES.bluesMajor).toHaveLength(6)
  })

  it('has world/exotic scales', () => {
    expect(SCALES.japanese).toHaveLength(5)
    expect(SCALES.arabic).toHaveLength(7)
    expect(SCALES.hungarianMinor).toHaveLength(7)
    expect(SCALES.wholeTone).toHaveLength(6)
    expect(SCALES.chromatic).toHaveLength(12)
    expect(SCALES.bebopDominant).toHaveLength(8)
  })

  it('all scales start at 0', () => {
    for (const [, intervals] of Object.entries(SCALES)) {
      expect(intervals[0]).toBe(0)
    }
  })

  it('all scale intervals are ascending', () => {
    for (const [name, intervals] of Object.entries(SCALES)) {
      for (let i = 1; i < intervals.length; i++) {
        expect(intervals[i]).toBeGreaterThan(intervals[i - 1])
      }
    }
  })
})

describe('getScale', () => {
  it('returns A minor scale frequencies in octave 3', () => {
    const scale = getScale('A', 'minor', 3)
    expect(scale).toHaveLength(7)
    expect(scale[0]).toBeCloseTo(220, 0)
  })

  it('returns C major scale starting on C4', () => {
    const scale = getScale('C', 'major', 4)
    expect(scale).toHaveLength(7)
    expect(scale[0]).toBeCloseTo(261.63, 0)
  })

  it('pentatonic scale has 5 notes', () => {
    expect(getScale('A', 'pentatonic', 3)).toHaveLength(5)
  })

  it('blues scale has 6 notes', () => {
    expect(getScale('A', 'blues', 3)).toHaveLength(6)
  })

  it('throws on unknown scale', () => {
    expect(() => getScale('C', 'nonexistent', 4)).toThrow('Unknown scale')
  })
})

describe('getScaleMultiOctave', () => {
  it('returns notes across 2 octaves', () => {
    const freqs = getScaleMultiOctave('C', 'major', 4, 2)
    expect(freqs).toHaveLength(14) // 7 * 2
    // Second octave should be ~2x the first
    expect(freqs[7] / freqs[0]).toBeCloseTo(2, 1)
  })

  it('returns single octave for octaves=1', () => {
    expect(getScaleMultiOctave('A', 'minor', 3, 1)).toHaveLength(7)
  })
})

// ---------------------------------------------------------------------------
// Chords
// ---------------------------------------------------------------------------

describe('CHORD_INTERVALS', () => {
  it('has 18 chord types', () => {
    expect(Object.keys(CHORD_INTERVALS).length).toBe(18)
  })

  it('triads have 3 notes', () => {
    for (const type of ['minor', 'major', 'dim', 'aug', 'sus2', 'sus4']) {
      expect(CHORD_INTERVALS[type]).toHaveLength(3)
    }
  })

  it('7th chords have 4 notes', () => {
    for (const type of ['min7', 'maj7', 'dom7', 'dim7', 'min7b5', 'min6', 'maj6']) {
      expect(CHORD_INTERVALS[type]).toHaveLength(4)
    }
  })

  it('extended chords have 4-5 notes', () => {
    expect(CHORD_INTERVALS.add9).toHaveLength(4)
    expect(CHORD_INTERVALS.min9).toHaveLength(5)
    expect(CHORD_INTERVALS.maj9).toHaveLength(5)
    expect(CHORD_INTERVALS.dom9).toHaveLength(5)
  })
})

describe('getChord', () => {
  it('returns 3 notes for a minor chord', () => {
    const chord = getChord('A', 'minor', 3)
    expect(chord).toHaveLength(3)
    expect(chord[0]).toBeCloseTo(220, 0)
  })

  it('returns 3 notes for a major chord', () => {
    const chord = getChord('C', 'major', 4)
    expect(chord).toHaveLength(3)
    expect(chord[0]).toBeCloseTo(261.63, 0)
  })

  it('returns 4 notes for 7th chords', () => {
    expect(getChord('A', 'min7', 3)).toHaveLength(4)
    expect(getChord('C', 'maj7', 4)).toHaveLength(4)
    expect(getChord('G', 'dom7', 3)).toHaveLength(4)
  })

  it('returns 5 notes for 9th chords', () => {
    expect(getChord('C', 'min9', 4)).toHaveLength(5)
    expect(getChord('C', 'maj9', 4)).toHaveLength(5)
  })

  it('throws on unknown chord type', () => {
    expect(() => getChord('C', 'nonexistent', 4)).toThrow('Unknown chord type')
  })
})

// ---------------------------------------------------------------------------
// Progressions
// ---------------------------------------------------------------------------

describe('PROGRESSIONS', () => {
  it('has 20 named progressions', () => {
    expect(Object.keys(PROGRESSIONS).length).toBe(20)
  })

  it('every progression has chords and mood', () => {
    for (const [, prog] of Object.entries(PROGRESSIONS)) {
      expect(prog.chords.length).toBeGreaterThan(0)
      expect(prog.mood.length).toBeGreaterThan(0)
    }
  })

  it('chord specs are in degree:type format', () => {
    for (const [, prog] of Object.entries(PROGRESSIONS)) {
      for (const spec of prog.chords) {
        expect(spec).toMatch(/^[ivIVbx]+:[\w]+$/)
      }
    }
  })
})

describe('getProgression', () => {
  it('resolves pop progression in C to 4 chords', () => {
    const chords = getProgression('C', 'pop', 3)
    expect(chords).toHaveLength(4)
    // Each chord is an array of frequencies
    for (const chord of chords) {
      expect(chord.length).toBeGreaterThanOrEqual(3)
      for (const f of chord) {
        expect(f).toBeGreaterThan(0)
      }
    }
  })

  it('resolves blues12bar to 12 chords', () => {
    const chords = getProgression('E', 'blues12bar', 3)
    expect(chords).toHaveLength(12)
  })

  it('throws on unknown progression', () => {
    expect(() => getProgression('C', 'nonexistent', 3)).toThrow('Unknown progression')
  })
})

describe('resolveChordSpecs', () => {
  it('resolves I:major in C to C major chord', () => {
    const chords = resolveChordSpecs('C', ['I:major'], 4)
    expect(chords).toHaveLength(1)
    expect(chords[0][0]).toBeCloseTo(noteFreq('C', 4), 1)
  })

  it('resolves vi:minor in C to A minor', () => {
    const chords = resolveChordSpecs('C', ['vi:minor'], 3)
    expect(chords[0][0]).toBeCloseTo(noteFreq('A', 3), 1)
  })

  it('resolves flat degrees correctly', () => {
    const chords = resolveChordSpecs('A', ['bVII:major'], 3)
    expect(chords[0][0]).toBeCloseTo(noteFreq('G', 3), 1)
  })

  it('throws on unknown key', () => {
    expect(() => resolveChordSpecs('X', ['I:major'], 3)).toThrow('Unknown key')
  })
})

// ---------------------------------------------------------------------------
// Rhythm Templates
// ---------------------------------------------------------------------------

describe('RHYTHM_TEMPLATES', () => {
  it('has 15 rhythm templates', () => {
    expect(Object.keys(RHYTHM_TEMPLATES).length).toBe(15)
  })

  it('all templates sum to 16 steps (one bar)', () => {
    for (const [name, durations] of Object.entries(RHYTHM_TEMPLATES)) {
      const sum = durations.reduce((a, b) => a + b, 0)
      expect(sum).toBe(16)
    }
  })
})

describe('applySwing', () => {
  it('returns copy of notes with swingAmount 0', () => {
    const notes = [{ pitch: 440, duration: 2 }, { pitch: 330, duration: 2 }]
    const result = applySwing(notes, 0)
    expect(result).toEqual(notes)
    expect(result).not.toBe(notes) // different reference
  })

  it('returns copy of single-note array', () => {
    const notes = [{ pitch: 440, duration: 1 }]
    const result = applySwing(notes, 0.5)
    expect(result).toHaveLength(1)
  })

  it('does not change long notes', () => {
    const notes = [{ pitch: 440, duration: 4 }, { pitch: 330, duration: 4 }]
    const result = applySwing(notes, 0.8)
    expect(result[0].duration).toBe(4)
    expect(result[1].duration).toBe(4)
  })
})

// ---------------------------------------------------------------------------
// Melody Generation
// ---------------------------------------------------------------------------

describe('scaleDegreeWalk', () => {
  const scale = [220, 247, 262, 294, 330, 370, 415] // ~A minor

  it('returns empty for empty scale', () => {
    expect(scaleDegreeWalk([], () => 0.5, 10)).toEqual([])
  })

  it('returns requested number of notes', () => {
    let i = 0
    const rng = () => { i++; return (i * 0.17) % 1 }
    const result = scaleDegreeWalk(scale, rng, 20, 2)
    expect(result).toHaveLength(20)
  })

  it('all notes are from the scale', () => {
    let i = 0
    const rng = () => { i++; return (i * 0.31) % 1 }
    const result = scaleDegreeWalk(scale, rng, 30, 3)
    for (const freq of result) {
      expect(scale).toContain(freq)
    }
  })

  it('is deterministic with same rng', () => {
    const rng1 = () => 0.5
    const rng2 = () => 0.5
    expect(scaleDegreeWalk(scale, rng1, 10, 2)).toEqual(scaleDegreeWalk(scale, rng2, 10, 2))
  })
})

describe('motifDevelop', () => {
  const motif = [
    { pitch: 220, duration: 2 },
    { pitch: 330, duration: 4 },
    { pitch: 440, duration: 2 },
  ]

  it('retrograde reverses note order', () => {
    const result = motifDevelop(motif, 'retrograde')
    expect(result[0].pitch).toBe(440)
    expect(result[2].pitch).toBe(220)
  })

  it('invert mirrors pitches around first note', () => {
    const result = motifDevelop(motif, 'invert')
    expect(result[0].pitch).toBe(220) // pivot stays
    // Second note: 220 + (220 - 330) = 110
    expect(result[1].pitch).toBe(110)
  })

  it('invert preserves rests', () => {
    const withRest = [{ pitch: 440, duration: 2 }, { pitch: 0, duration: 2 }]
    const result = motifDevelop(withRest, 'invert')
    expect(result[1].pitch).toBe(0)
  })

  it('augment doubles durations', () => {
    const result = motifDevelop(motif, 'augment')
    expect(result[0].duration).toBe(4)
    expect(result[1].duration).toBe(8)
  })

  it('diminish halves durations (min 1)', () => {
    const result = motifDevelop(motif, 'diminish')
    expect(result[0].duration).toBe(1)
    expect(result[1].duration).toBe(2)
  })

  it('transpose shifts frequencies by semitones', () => {
    const result = motifDevelop(motif, 'transpose', 12)
    // +12 semitones = 1 octave = 2x frequency
    expect(result[0].pitch).toBeCloseTo(440, 0)
  })

  it('transpose preserves rests', () => {
    const withRest = [{ pitch: 0, duration: 2 }]
    const result = motifDevelop(withRest, 'transpose', 5)
    expect(result[0].pitch).toBe(0)
  })

  it('returns empty for empty motif', () => {
    expect(motifDevelop([], 'retrograde')).toEqual([])
  })
})

describe('callAndResponse', () => {
  const scale = [220, 247, 262, 294, 330, 370, 415]

  it('returns empty for empty call', () => {
    expect(callAndResponse([], scale)).toEqual([])
  })

  it('returns empty for empty scale', () => {
    expect(callAndResponse([{ pitch: 440, duration: 2 }], [])).toEqual([])
  })

  it('preserves rests', () => {
    const call = [{ pitch: 0, duration: 4 }]
    const response = callAndResponse(call, scale)
    expect(response[0].pitch).toBe(0)
  })

  it('returns same number of notes as call', () => {
    const call = [
      { pitch: 220, duration: 2 },
      { pitch: 330, duration: 4 },
      { pitch: 440, duration: 2 },
    ]
    const response = callAndResponse(call, scale)
    expect(response).toHaveLength(3)
  })

  it('response notes are from the scale', () => {
    const call = [
      { pitch: 220, duration: 2, velocity: 0.8 },
      { pitch: 330, duration: 4, velocity: 0.7 },
    ]
    const response = callAndResponse(call, scale)
    for (const note of response) {
      if (note.pitch > 0) expect(scale).toContain(note.pitch)
    }
  })
})

// ---------------------------------------------------------------------------
// Arpeggios
// ---------------------------------------------------------------------------

describe('arpeggio', () => {
  const freqs = [220, 261.63, 329.63]

  it('up pattern returns ascending order', () => {
    const notes = arpeggio(freqs, 'up')
    expect(notes).toHaveLength(3)
    expect(notes[0].pitch).toBe(220)
    expect(notes[2].pitch).toBe(329.63)
    expect(notes[0].duration).toBe(1)
  })

  it('down pattern returns descending order', () => {
    const notes = arpeggio(freqs, 'down')
    expect(notes[0].pitch).toBe(329.63)
    expect(notes[2].pitch).toBe(220)
  })

  it('updown goes up then down without repeating extremes', () => {
    const notes = arpeggio(freqs, 'updown')
    expect(notes.length).toBeGreaterThanOrEqual(4)
    expect(notes[0].pitch).toBe(220)
    expect(notes[notes.length - 1].pitch).toBe(261.63)
  })

  it('random contains all frequencies', () => {
    const notes = arpeggio(freqs, 'random')
    const pitches = notes.map(n => n.pitch)
    for (const f of freqs) expect(pitches).toContain(f)
  })

  it('accepts custom step duration', () => {
    const notes = arpeggio(freqs, 'up', 2)
    expect(notes[0].duration).toBe(2)
  })
})

describe('seededArpeggio', () => {
  const freqs = [220, 330, 440]

  it('delegates to arpeggio for non-random patterns', () => {
    const rng = () => 0.5
    const up = seededArpeggio(freqs, 'up', 1, rng)
    expect(up[0].pitch).toBe(220)
    expect(up[2].pitch).toBe(440)
  })

  it('uses rng for random pattern (deterministic)', () => {
    let i = 0
    const rng1 = () => { i++; return (i * 0.37) % 1 }
    i = 0
    const rng2 = () => { i++; return (i * 0.37) % 1 }
    const a = seededArpeggio(freqs, 'random', 2, rng1)
    i = 0
    const b = seededArpeggio(freqs, 'random', 2, rng2)
    expect(a.map(n => n.pitch)).toEqual(b.map(n => n.pitch))
  })
})

// ---------------------------------------------------------------------------
// Mood Descriptors
// ---------------------------------------------------------------------------

describe('MOOD_SCALES', () => {
  it('has 10 mood descriptors', () => {
    expect(Object.keys(MOOD_SCALES).length).toBe(10)
  })

  it('each mood has scales, tempoRange, and feel', () => {
    for (const [, mood] of Object.entries(MOOD_SCALES)) {
      expect(mood.scales.length).toBeGreaterThan(0)
      expect(mood.tempoRange[0]).toBeLessThan(mood.tempoRange[1])
      expect(mood.feel.length).toBeGreaterThan(0)
    }
  })

  it('all referenced scales exist in SCALES', () => {
    for (const [, mood] of Object.entries(MOOD_SCALES)) {
      for (const s of mood.scales) {
        expect(SCALES).toHaveProperty(s)
      }
    }
  })
})

// ---------------------------------------------------------------------------
// NOTE_NAMES
// ---------------------------------------------------------------------------

describe('NOTE_NAMES', () => {
  it('has 12 chromatic notes', () => {
    expect(NOTE_NAMES).toHaveLength(12)
  })

  it('starts with C and ends with B', () => {
    expect(NOTE_NAMES[0]).toBe('C')
    expect(NOTE_NAMES[11]).toBe('B')
  })
})
