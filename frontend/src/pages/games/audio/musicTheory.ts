/**
 * Music theory utilities: note frequencies, scales, modes, chords, progressions,
 * rhythm templates, melody generation, and mood descriptors.
 *
 * Pure functions with no Web Audio dependency — usable in tests and song definitions.
 */

import type { Note } from './songTypes'

// ---------------------------------------------------------------------------
// Note → Frequency mapping (equal temperament, A4 = 440 Hz)
// ---------------------------------------------------------------------------

/** Semitone offsets from C within one octave. */
const NOTE_SEMITONES: Record<string, number> = {
  'C': 0, 'C#': 1, 'Db': 1,
  'D': 2, 'D#': 3, 'Eb': 3,
  'E': 4, 'Fb': 4,
  'F': 5, 'F#': 6, 'Gb': 6,
  'G': 7, 'G#': 8, 'Ab': 8,
  'A': 9, 'A#': 10, 'Bb': 10,
  'B': 11, 'Cb': 11,
}

/** All 12 chromatic note names (using sharps). */
export const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

/**
 * Get the frequency of a note in equal temperament.
 * @param note - Note name (e.g. 'A', 'C#', 'Bb')
 * @param octave - Octave number (4 = middle octave, A4=440)
 */
export function noteFreq(note: string, octave: number): number {
  const semitone = NOTE_SEMITONES[note]
  if (semitone === undefined) throw new Error(`Unknown note: ${note}`)
  // Distance in semitones from A4 (which is C4 + 9 semitones)
  const dist = (octave - 4) * 12 + (semitone - 9)
  return 440 * Math.pow(2, dist / 12)
}

// ---------------------------------------------------------------------------
// Scales & Modes (intervals in semitones from root)
// ---------------------------------------------------------------------------

export const SCALES: Record<string, number[]> = {
  // ---- 7 Church Modes ----
  ionian:     [0, 2, 4, 5, 7, 9, 11],       // major scale
  dorian:     [0, 2, 3, 5, 7, 9, 10],
  phrygian:   [0, 1, 3, 5, 7, 8, 10],
  lydian:     [0, 2, 4, 6, 7, 9, 11],
  mixolydian: [0, 2, 4, 5, 7, 9, 10],
  aeolian:    [0, 2, 3, 5, 7, 8, 10],        // natural minor
  locrian:    [0, 1, 3, 5, 6, 8, 10],

  // ---- Common aliases ----
  major:      [0, 2, 4, 5, 7, 9, 11],        // = ionian
  minor:      [0, 2, 3, 5, 7, 8, 10],        // = aeolian

  // ---- Extended modes ----
  harmonicMinor: [0, 2, 3, 5, 7, 8, 11],
  melodicMinor:  [0, 2, 3, 5, 7, 9, 11],
  harmonicMajor: [0, 2, 4, 5, 7, 8, 11],

  // ---- Pentatonic & Blues ----
  pentatonic:      [0, 3, 5, 7, 10],          // minor pentatonic
  majorPentatonic: [0, 2, 4, 7, 9],
  blues:           [0, 3, 5, 6, 7, 10],
  bluesMajor:      [0, 2, 3, 4, 7, 9],

  // ---- World / Exotic ----
  japanese:        [0, 1, 5, 7, 8],           // in-sen scale
  arabic:          [0, 1, 4, 5, 7, 8, 11],   // double harmonic major
  hungarianMinor:  [0, 2, 3, 6, 7, 8, 11],
  wholeTone:       [0, 2, 4, 6, 8, 10],
  chromatic:       [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
  bebopDominant:   [0, 2, 4, 5, 7, 9, 10, 11],
}

/**
 * Get frequencies for a scale starting at root + octave.
 * @param root - Root note name (e.g. 'A')
 * @param scaleName - Scale name from SCALES
 * @param octave - Starting octave
 */
export function getScale(root: string, scaleName: string, octave: number): number[] {
  const intervals = SCALES[scaleName]
  if (!intervals) throw new Error(`Unknown scale: ${scaleName}`)
  const rootFreq = noteFreq(root, octave)
  return intervals.map(i => rootFreq * Math.pow(2, i / 12))
}

/**
 * Get scale frequencies spanning multiple octaves.
 */
export function getScaleMultiOctave(
  root: string, scaleName: string, startOctave: number, octaves: number,
): number[] {
  const freqs: number[] = []
  for (let o = 0; o < octaves; o++) {
    freqs.push(...getScale(root, scaleName, startOctave + o))
  }
  return freqs
}

// ---------------------------------------------------------------------------
// Chords (intervals in semitones)
// ---------------------------------------------------------------------------

export const CHORD_INTERVALS: Record<string, number[]> = {
  // ---- Triads ----
  minor:  [0, 3, 7],
  major:  [0, 4, 7],
  dim:    [0, 3, 6],
  aug:    [0, 4, 8],
  sus2:   [0, 2, 7],
  sus4:   [0, 5, 7],

  // ---- 7th chords ----
  min7:   [0, 3, 7, 10],
  maj7:   [0, 4, 7, 11],
  dom7:   [0, 4, 7, 10],
  dim7:   [0, 3, 6, 9],
  min7b5: [0, 3, 6, 10],   // half-diminished
  min6:   [0, 3, 7, 9],
  maj6:   [0, 4, 7, 9],

  // ---- Extended ----
  add9:   [0, 4, 7, 14],
  min9:   [0, 3, 7, 10, 14],
  maj9:   [0, 4, 7, 11, 14],
  dom9:   [0, 4, 7, 10, 14],
  maj7s11: [0, 4, 7, 11, 18], // maj7#11
}

/**
 * Get frequencies for a chord.
 * @param root - Root note name
 * @param type - Chord type from CHORD_INTERVALS
 * @param octave - Octave for the root
 */
export function getChord(root: string, type: string, octave: number): number[] {
  const intervals = CHORD_INTERVALS[type]
  if (!intervals) throw new Error(`Unknown chord type: ${type}`)
  const rootFreq = noteFreq(root, octave)
  return intervals.map(i => rootFreq * Math.pow(2, i / 12))
}

// ---------------------------------------------------------------------------
// Chord Progressions Library
// ---------------------------------------------------------------------------

/** Roman numeral → semitone offset from root. */
const ROMAN_TO_SEMITONE: Record<string, number> = {
  'I': 0, 'II': 2, 'III': 4, 'IV': 5, 'V': 7, 'VI': 9, 'VII': 11,
  'i': 0, 'ii': 2, 'iii': 4, 'iv': 5, 'v': 7, 'vi': 9, 'vii': 11,
  'bII': 1, 'bIII': 3, 'bVI': 8, 'bVII': 10,
  'bii': 1, 'biii': 3, 'bvi': 8, 'bvii': 10,
}

export interface ProgressionDef {
  /** Chord specs: e.g. ['I:major', 'V:major', 'vi:minor', 'IV:major'] */
  chords: string[]
  mood: string
}

export const PROGRESSIONS: Record<string, ProgressionDef> = {
  pop:          { chords: ['I:major', 'V:major', 'vi:minor', 'IV:major'], mood: 'upbeat' },
  axis:         { chords: ['I:major', 'V:major', 'vi:minor', 'IV:major'], mood: 'anthemic' },
  sad:          { chords: ['vi:minor', 'IV:major', 'I:major', 'V:major'], mood: 'melancholy' },
  jazz251:      { chords: ['ii:min7', 'V:dom7', 'I:maj7'], mood: 'smooth' },
  jazz1625:     { chords: ['I:maj7', 'vi:min7', 'ii:min7', 'V:dom7'], mood: 'jazzy' },
  andalusian:   { chords: ['i:minor', 'bVII:major', 'bVI:major', 'V:major'], mood: 'spanish' },
  blues12bar:   { chords: ['I:dom7', 'I:dom7', 'I:dom7', 'I:dom7', 'IV:dom7', 'IV:dom7', 'I:dom7', 'I:dom7', 'V:dom7', 'IV:dom7', 'I:dom7', 'V:dom7'], mood: 'blues' },
  modal:        { chords: ['I:major', 'bVII:major', 'I:major', 'bVII:major'], mood: 'modal' },
  neosoul:      { chords: ['IV:maj7', 'iii:min7', 'vi:min7', 'V:dom7'], mood: 'soulful' },
  rock:         { chords: ['I:major', 'IV:major', 'V:major', 'I:major'], mood: 'driving' },
  power:        { chords: ['I:major', 'bVII:major', 'bVI:major', 'I:major'], mood: 'powerful' },
  dorian:       { chords: ['i:minor', 'IV:major', 'i:minor', 'IV:major'], mood: 'funky' },
  epic:         { chords: ['I:major', 'V:major', 'vi:minor', 'III:major'], mood: 'epic' },
  dark:         { chords: ['i:minor', 'bVI:major', 'bIII:major', 'bVII:major'], mood: 'dark' },
  dreamy:       { chords: ['I:maj7', 'III:major', 'IV:maj7', 'iv:minor'], mood: 'dreamy' },
  tension:      { chords: ['i:minor', 'bII:major', 'V:major', 'i:minor'], mood: 'tense' },
  coltrane:     { chords: ['I:maj7', 'bIII:maj7', 'V:maj7', 'I:maj7'], mood: 'adventurous' },
  reggae:       { chords: ['I:major', 'IV:major', 'I:major', 'V:major'], mood: 'relaxed' },
  waltz:        { chords: ['I:major', 'IV:major', 'V:dom7', 'I:major'], mood: 'elegant' },
  minorBlues:   { chords: ['i:min7', 'iv:min7', 'i:min7', 'bVI:dom7', 'V:dom7', 'i:min7'], mood: 'moody' },
}

/**
 * Resolve a progression to arrays of frequencies.
 * @param key - Root note name (e.g. 'C', 'A')
 * @param progressionName - Name from PROGRESSIONS
 * @param octave - Base octave for chord voicings
 * @returns Array of chord frequency arrays
 */
export function getProgression(key: string, progressionName: string, octave: number): number[][] {
  const prog = PROGRESSIONS[progressionName]
  if (!prog) throw new Error(`Unknown progression: ${progressionName}`)
  return resolveChordSpecs(key, prog.chords, octave)
}

/**
 * Resolve chord spec strings to frequency arrays.
 * Each spec is "degree:type" e.g. "I:major", "vi:min7"
 */
export function resolveChordSpecs(key: string, specs: string[], octave: number): number[][] {
  const keySemitone = NOTE_SEMITONES[key]
  if (keySemitone === undefined) throw new Error(`Unknown key: ${key}`)

  return specs.map(spec => {
    const [degree, type] = spec.split(':')
    const offset = ROMAN_TO_SEMITONE[degree]
    if (offset === undefined) throw new Error(`Unknown degree: ${degree}`)
    // Find the note name at this offset
    const noteIdx = (keySemitone + offset) % 12
    const noteName = NOTE_NAMES[noteIdx]
    return getChord(noteName, type, octave)
  })
}

// ---------------------------------------------------------------------------
// Rhythm Templates
// ---------------------------------------------------------------------------

/**
 * Rhythm templates: arrays of step durations that sum to 16 (one bar of 16th notes).
 * Each number = how many 16th-note steps that hit occupies.
 */
export const RHYTHM_TEMPLATES: Record<string, number[]> = {
  straight8ths:  [2, 2, 2, 2, 2, 2, 2, 2],
  straight16ths: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
  quarterNotes:  [4, 4, 4, 4],
  halfNotes:     [8, 8],
  wholeNote:     [16],
  syncopated:    [3, 3, 2, 3, 3, 2],                   // 16 steps
  shuffle:       [3, 1, 3, 1, 3, 1, 3, 1],             // swung 8ths
  dotted:        [3, 1, 3, 1, 3, 1, 2, 2],             // dotted 8th + 16th
  bossanova:     [3, 3, 4, 3, 3],                       // Brazilian 16
  reggae:        [4, 2, 2, 4, 2, 2],                    // off-beat emphasis
  waltz:         [4, 4, 4, 4],                          // 3/4 feel at 4 steps
  tresillo:      [3, 3, 2, 3, 3, 2],                   // Latin tresillo
  halftime:      [4, 4, 4, 4],                          // same as quarter
  drumAndBass:   [2, 1, 1, 2, 2, 1, 1, 2, 2, 2],      // 16
  fourOnFloor:   [4, 4, 4, 4],                          // dance kick
}

/**
 * Apply swing to a sequence of notes by shifting even-indexed 8th notes later.
 * @param notes - Input note array
 * @param swingAmount - 0 = straight, 1 = full triplet swing
 * @returns New note array with adjusted durations
 */
export function applySwing(notes: Note[], swingAmount: number): Note[] {
  if (swingAmount <= 0 || notes.length < 2) return [...notes]
  const result: Note[] = []
  // Swing pairs: make odd notes shorter, even notes longer
  for (let i = 0; i < notes.length; i++) {
    const note = { ...notes[i] }
    if (note.duration <= 1) {
      // Only swing short notes in pairs
      if (i % 2 === 0 && i + 1 < notes.length) {
        // Stretch this note, shrink the next
        const shift = Math.round(note.duration * swingAmount * 0.33)
        note.duration = note.duration + shift
        result.push(note)
      } else if (i % 2 === 1) {
        const shift = Math.round(notes[i - 1]?.duration ?? 1 * swingAmount * 0.33)
        note.duration = Math.max(1, note.duration - shift)
        result.push(note)
      } else {
        result.push(note)
      }
    } else {
      result.push(note)
    }
  }
  return result
}

// ---------------------------------------------------------------------------
// Melody Generation Helpers
// ---------------------------------------------------------------------------

/**
 * Seeded random walk along scale degrees. Returns an array of frequency indices
 * into the given scale. Uses a simple PRNG for determinism.
 *
 * @param scaleFreqs - Array of scale frequencies (from getScale or getScaleMultiOctave)
 * @param rng - A seeded random function returning 0–1
 * @param length - Number of notes to generate
 * @param stepRange - Max interval jump in scale degrees (default 3)
 * @returns Array of frequencies from the scale
 */
export function scaleDegreeWalk(
  scaleFreqs: number[], rng: () => number, length: number, stepRange: number = 3,
): number[] {
  if (scaleFreqs.length === 0) return []
  const result: number[] = []
  let idx = Math.floor(rng() * Math.min(scaleFreqs.length, 4)) // start in lower range
  for (let i = 0; i < length; i++) {
    result.push(scaleFreqs[Math.max(0, Math.min(idx, scaleFreqs.length - 1))])
    const step = Math.floor(rng() * (stepRange * 2 + 1)) - stepRange
    idx = Math.max(0, Math.min(scaleFreqs.length - 1, idx + step))
  }
  return result
}

/**
 * Transform a motif using classic techniques.
 * @param motif - Original note sequence
 * @param technique - Transformation type
 * @returns Transformed note sequence
 */
export function motifDevelop(
  motif: Note[],
  technique: 'invert' | 'retrograde' | 'augment' | 'diminish' | 'transpose',
  param?: number,
): Note[] {
  if (motif.length === 0) return []

  switch (technique) {
    case 'retrograde':
      return [...motif].reverse()

    case 'invert': {
      // Invert around the first note's pitch
      const pivot = motif[0].pitch
      return motif.map(n => ({
        ...n,
        pitch: n.pitch === 0 ? 0 : pivot + (pivot - n.pitch),
      }))
    }

    case 'augment':
      // Double durations
      return motif.map(n => ({ ...n, duration: n.duration * 2 }))

    case 'diminish':
      // Halve durations (min 1)
      return motif.map(n => ({ ...n, duration: Math.max(1, Math.round(n.duration / 2)) }))

    case 'transpose': {
      // Transpose by semitones (param = semitone offset, default +2)
      const offset = param ?? 2
      const ratio = Math.pow(2, offset / 12)
      return motif.map(n => ({
        ...n,
        pitch: n.pitch === 0 ? 0 : n.pitch * ratio,
      }))
    }
  }
}

/**
 * Generate a melodic response to a call phrase. The response uses the same
 * rhythm but walks the scale in the opposite direction, ending near the tonic.
 */
export function callAndResponse(call: Note[], scaleFreqs: number[]): Note[] {
  if (call.length === 0 || scaleFreqs.length === 0) return []

  return call.map((note, i) => {
    if (note.pitch === 0) return { ...note } // preserve rests
    // Find nearest scale degree
    const idx = findNearestIndex(scaleFreqs, note.pitch)
    // Mirror from the opposite end of the used range
    const mirrorIdx = scaleFreqs.length - 1 - idx
    // Clamp and add slight variation
    const responseIdx = Math.max(0, Math.min(scaleFreqs.length - 1,
      mirrorIdx + (i % 2 === 0 ? 1 : -1)))
    return {
      ...note,
      pitch: scaleFreqs[responseIdx],
      velocity: (note.velocity ?? 0.8) * 0.9,
    }
  })
}

/** Find the index of the nearest frequency in an array. */
function findNearestIndex(freqs: number[], target: number): number {
  let best = 0
  let bestDist = Math.abs(freqs[0] - target)
  for (let i = 1; i < freqs.length; i++) {
    const dist = Math.abs(freqs[i] - target)
    if (dist < bestDist) {
      bestDist = dist
      best = i
    }
  }
  return best
}

// ---------------------------------------------------------------------------
// Chord-Tone Helpers
// ---------------------------------------------------------------------------

/**
 * Find the nearest chord tone frequency to a given frequency.
 * Useful for snapping melody notes to chord tones on strong beats.
 */
export function nearestChordTone(freq: number, chordFreqs: number[]): number {
  if (chordFreqs.length === 0) return freq
  let best = chordFreqs[0]
  let bestDist = Math.abs(Math.log2(freq / chordFreqs[0]))
  for (let i = 1; i < chordFreqs.length; i++) {
    const dist = Math.abs(Math.log2(freq / chordFreqs[i]))
    if (dist < bestDist) {
      bestDist = dist
      best = chordFreqs[i]
    }
  }
  return best
}

/**
 * Generate a walking bass line connecting chord roots via stepwise scale movement.
 * Returns an array of frequencies, one per step (16th note).
 * @param chordRoots - Root frequency for each bar
 * @param scaleFreqs - Scale frequencies spanning the bass range
 * @param rng - Seeded PRNG
 * @param stepsPerBar - Steps per bar (default 16)
 */
export function walkingBassLine(
  chordRoots: number[], scaleFreqs: number[], rng: () => number, stepsPerBar: number = 16,
): number[] {
  if (scaleFreqs.length === 0 || chordRoots.length === 0) return []
  const result: number[] = []

  for (let bar = 0; bar < chordRoots.length; bar++) {
    const currentRoot = chordRoots[bar]
    const nextRoot = chordRoots[(bar + 1) % chordRoots.length]
    const rootIdx = findNearestIndex(scaleFreqs, currentRoot)
    const targetIdx = findNearestIndex(scaleFreqs, nextRoot)

    // Walk from current root toward next root over the bar
    let idx = rootIdx
    for (let step = 0; step < stepsPerBar; step++) {
      result.push(scaleFreqs[Math.max(0, Math.min(scaleFreqs.length - 1, idx))])
      // Move toward target on even 8th-note boundaries
      if (step % 2 === 1) {
        if (idx < targetIdx) idx += rng() < 0.7 ? 1 : 0
        else if (idx > targetIdx) idx -= rng() < 0.7 ? 1 : 0
        else idx += rng() < 0.5 ? 1 : -1 // at target, add neighbor variation
        idx = Math.max(0, Math.min(scaleFreqs.length - 1, idx))
      }
    }
  }
  return result
}

// ---------------------------------------------------------------------------
// Arpeggios
// ---------------------------------------------------------------------------

/**
 * Generate an arpeggio pattern from frequencies.
 * @param frequencies - Array of frequencies to arpeggiate
 * @param pattern - 'up' | 'down' | 'updown' | 'random'
 * @param stepDuration - Duration per note in steps (default 1)
 */
export function arpeggio(
  frequencies: number[],
  pattern: 'up' | 'down' | 'updown' | 'random',
  stepDuration: number = 1,
): Note[] {
  const toNote = (pitch: number): Note => ({ pitch, duration: stepDuration })

  switch (pattern) {
    case 'up':
      return frequencies.map(toNote)
    case 'down':
      return [...frequencies].reverse().map(toNote)
    case 'updown': {
      // up: all notes, down: skip top and bottom to avoid repeats
      const up = frequencies.map(toNote)
      const down = frequencies.length > 2
        ? frequencies.slice(1, -1).reverse().map(toNote)
        : []
      return [...up, ...down]
    }
    case 'random': {
      const shuffled = [...frequencies]
      for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
      }
      return shuffled.map(toNote)
    }
  }
}

/**
 * Seeded arpeggio — same as arpeggio but uses a provided RNG for 'random' pattern.
 */
export function seededArpeggio(
  frequencies: number[],
  pattern: 'up' | 'down' | 'updown' | 'random',
  stepDuration: number,
  rng: () => number,
): Note[] {
  if (pattern !== 'random') return arpeggio(frequencies, pattern, stepDuration)

  const toNote = (pitch: number): Note => ({ pitch, duration: stepDuration })
  const shuffled = [...frequencies]
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1))
    ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
  }
  return shuffled.map(toNote)
}

// ---------------------------------------------------------------------------
// Mood Descriptors
// ---------------------------------------------------------------------------

export interface MoodDescriptor {
  scales: string[]
  tempoRange: [number, number]
  feel: string
}

export const MOOD_SCALES: Record<string, MoodDescriptor> = {
  epic:        { scales: ['major', 'harmonicMinor', 'mixolydian'], tempoRange: [80, 120], feel: 'powerful' },
  chill:       { scales: ['dorian', 'pentatonic', 'majorPentatonic'], tempoRange: [65, 85], feel: 'relaxed' },
  dark:        { scales: ['minor', 'phrygian', 'locrian'], tempoRange: [70, 110], feel: 'ominous' },
  upbeat:      { scales: ['major', 'mixolydian', 'majorPentatonic'], tempoRange: [110, 140], feel: 'energetic' },
  mysterious:  { scales: ['wholeTone', 'lydian', 'harmonicMinor'], tempoRange: [70, 100], feel: 'enigmatic' },
  triumphant:  { scales: ['major', 'lydian', 'ionian'], tempoRange: [90, 130], feel: 'victorious' },
  melancholy:  { scales: ['minor', 'dorian', 'harmonicMinor'], tempoRange: [60, 90], feel: 'wistful' },
  funky:       { scales: ['mixolydian', 'dorian', 'blues'], tempoRange: [95, 120], feel: 'groovy' },
  ethereal:    { scales: ['lydian', 'wholeTone', 'majorPentatonic'], tempoRange: [55, 80], feel: 'floating' },
  aggressive:  { scales: ['phrygian', 'locrian', 'harmonicMinor'], tempoRange: [130, 180], feel: 'intense' },
}
