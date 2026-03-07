/**
 * Dino Runner synthwave song — "Neon Extinction" — A minor, 120 BPM base.
 *
 * 10 sections with varied progressions, 7 channels including counter-melody
 * and atmosphere. Adapts to gameplay via intensity map and BPM scaling.
 *
 * Section flow: intro → verse1 → prechorus → chorus1 → verse2 → bridge →
 *               chorus2 → breakdown → climax → outro (loops back to verse1)
 */

import { noteFreq, getChord, arpeggio } from '../musicTheory'
import type { Song, Note } from '../songTypes'

// ---------------------------------------------------------------------------
// Frequencies
// ---------------------------------------------------------------------------

// Bass notes (octave 2)
const bassA = noteFreq('A', 2)
const bassF = noteFreq('F', 2)
const bassC = noteFreq('C', 3)
const bassG = noteFreq('G', 2)
const bassD = noteFreq('D', 3)
const bassE = noteFreq('E', 2)

// Chords (octave 2 for arps)
const Am = getChord('A', 'minor', 2)
const F  = getChord('F', 'major', 2)
const G  = getChord('G', 'major', 2)
const Dm = getChord('D', 'minor', 3)
const Em = getChord('E', 'minor', 2)

// Lead melody notes (octave 4–5)
const A4 = noteFreq('A', 4)
const B4 = noteFreq('B', 4)
const C5 = noteFreq('C', 5)
const D5 = noteFreq('D', 5)
const E5 = noteFreq('E', 5)
const G4 = noteFreq('G', 4)
const F4 = noteFreq('F', 4)
const E4 = noteFreq('E', 4)

// Counter-melody notes (octave 3, triangle, sits below lead)
const A3 = noteFreq('A', 3)
const C4 = noteFreq('C', 4)
const G3 = noteFreq('G', 3)
const F3 = noteFreq('F', 3)
const D3 = noteFreq('D', 3)
const E3 = noteFreq('E', 3)

// Pad voicings (octave 3 for warmth)
const padAm = getChord('A', 'minor', 3)
const padF  = getChord('F', 'major', 3)
const padC  = getChord('C', 'major', 4)
const padG  = getChord('G', 'major', 3)
const padDm = getChord('D', 'minor', 3)
const padEm = getChord('E', 'minor', 3)

// Atmosphere notes (octave 5, very quiet sine, ambient texture)
const atA5 = noteFreq('A', 5)
const atC6 = noteFreq('C', 6)
const atE5 = noteFreq('E', 5)
const atG5 = noteFreq('G', 5)

// ---------------------------------------------------------------------------
// Bass patterns
// ---------------------------------------------------------------------------

function bassLine(roots: number[]): Note[] {
  const notes: Note[] = []
  for (const root of roots) {
    for (let i = 0; i < 4; i++) {
      notes.push({ pitch: root, duration: 2, velocity: 0.7 })
      notes.push({ pitch: 0, duration: 2 })
    }
  }
  return notes
}

function bassLineIntro(roots: number[]): Note[] {
  const notes: Note[] = []
  for (const root of roots) {
    notes.push({ pitch: root, duration: 12, velocity: 0.6 })
    notes.push({ pitch: 0, duration: 4 })
  }
  return notes
}

function bassLineSyncopated(roots: number[]): Note[] {
  const notes: Note[] = []
  for (const root of roots) {
    // Syncopated: short-long-short-rest pattern
    notes.push({ pitch: root, duration: 2, velocity: 0.75 })
    notes.push({ pitch: 0, duration: 1 })
    notes.push({ pitch: root, duration: 4, velocity: 0.7 })
    notes.push({ pitch: 0, duration: 1 })
    notes.push({ pitch: root, duration: 2, velocity: 0.65 })
    notes.push({ pitch: root * 2, duration: 2, velocity: 0.6 }) // octave up accent
    notes.push({ pitch: 0, duration: 4 })
  }
  return notes
}

function bassLineClimb(roots: number[]): Note[] {
  const notes: Note[] = []
  for (let i = 0; i < roots.length; i++) {
    const root = roots[i]
    // Ascending energy: more notes as bar progresses
    notes.push({ pitch: root, duration: 3, velocity: 0.8 })
    notes.push({ pitch: root, duration: 1, velocity: 0.6 })
    notes.push({ pitch: root, duration: 2, velocity: 0.75 })
    notes.push({ pitch: root, duration: 1, velocity: 0.6 })
    notes.push({ pitch: root, duration: 2, velocity: 0.7 })
    notes.push({ pitch: root, duration: 1, velocity: 0.6 })
    notes.push({ pitch: root, duration: 3, velocity: 0.75 })
    notes.push({ pitch: root * 1.5, duration: 2, velocity: 0.65 }) // fifth accent
    notes.push({ pitch: 0, duration: 1 })
  }
  return notes
}

// ---------------------------------------------------------------------------
// Drum patterns (pitch codes: 1=kick, 2=snare, 3=hihat, 4=clap)
// ---------------------------------------------------------------------------

function drumPatternBasic(bars: number): Note[] {
  const bar: Note[] = [
    { pitch: 1, duration: 1, velocity: 0.9 },
    { pitch: 0, duration: 1 },
    { pitch: 3, duration: 1, velocity: 0.4 },
    { pitch: 0, duration: 1 },
    { pitch: 2, duration: 1, velocity: 0.8 },
    { pitch: 0, duration: 1 },
    { pitch: 3, duration: 1, velocity: 0.4 },
    { pitch: 0, duration: 1 },
    { pitch: 1, duration: 1, velocity: 0.85 },
    { pitch: 0, duration: 1 },
    { pitch: 3, duration: 1, velocity: 0.4 },
    { pitch: 0, duration: 1 },
    { pitch: 2, duration: 1, velocity: 0.8 },
    { pitch: 0, duration: 1 },
    { pitch: 3, duration: 1, velocity: 0.5 },
    { pitch: 0, duration: 1 },
  ]
  const notes: Note[] = []
  for (let i = 0; i < bars; i++) notes.push(...bar)
  return notes
}

function drumPatternIntro(): Note[] {
  const bar: Note[] = [
    { pitch: 1, duration: 1, velocity: 0.7 },
    { pitch: 0, duration: 7 },
    { pitch: 1, duration: 1, velocity: 0.5 },
    { pitch: 0, duration: 7 },
  ]
  const notes: Note[] = []
  for (let i = 0; i < 4; i++) notes.push(...bar)
  return notes
}

function drumPatternBuild(): Note[] {
  const notes: Note[] = []
  // 4 bars of escalating energy
  for (let bar = 0; bar < 4; bar++) {
    const density = bar + 1 // 1-4 hits per beat position
    for (let beat = 0; beat < 4; beat++) {
      if (density >= 4) {
        notes.push({ pitch: 1, duration: 1, velocity: 0.7 + bar * 0.05 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
        notes.push({ pitch: beat % 2 === 1 ? 2 : 3, duration: 1, velocity: 0.6 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.3 })
      } else if (density >= 2) {
        notes.push({ pitch: beat % 2 === 0 ? 1 : 2, duration: 1, velocity: 0.7 })
        notes.push({ pitch: 0, duration: 1 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.35 })
        notes.push({ pitch: 0, duration: 1 })
      } else {
        notes.push({ pitch: 1, duration: 1, velocity: 0.6 })
        notes.push({ pitch: 0, duration: 3 })
      }
    }
  }
  return notes
}

function drumPatternClimaxFill(): Note[] {
  const notes: Note[] = []
  // Intense 4-on-floor with 16th hat accents and clap layers
  for (let bar = 0; bar < 4; bar++) {
    notes.push({ pitch: 1, duration: 1, velocity: 0.95 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.5 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.35 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.45 })
    notes.push({ pitch: 4, duration: 1, velocity: 0.85 }) // clap on 2
    notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.35 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.45 })
    notes.push({ pitch: 1, duration: 1, velocity: 0.9 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.5 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.35 })
    notes.push({ pitch: 1, duration: 1, velocity: 0.6 }) // ghost kick
    notes.push({ pitch: 4, duration: 1, velocity: 0.85 }) // clap on 4
    notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.5 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.35 })
  }
  return notes
}

function drumPatternHalfTime(bars: number): Note[] {
  const bar: Note[] = [
    { pitch: 1, duration: 1, velocity: 0.85 },
    { pitch: 0, duration: 3 },
    { pitch: 3, duration: 1, velocity: 0.3 },
    { pitch: 0, duration: 3 },
    { pitch: 2, duration: 1, velocity: 0.8 },
    { pitch: 0, duration: 3 },
    { pitch: 3, duration: 1, velocity: 0.3 },
    { pitch: 0, duration: 3 },
  ]
  const notes: Note[] = []
  for (let i = 0; i < bars; i++) notes.push(...bar)
  return notes
}

// ---------------------------------------------------------------------------
// Lead melodies
// ---------------------------------------------------------------------------

function leadVerseA(): Note[] {
  return [
    // Bar 1 (Am): ascending run
    { pitch: A4, duration: 2, velocity: 0.7 },
    { pitch: C5, duration: 2, velocity: 0.75 },
    { pitch: E5, duration: 4, velocity: 0.8 },
    { pitch: D5, duration: 2, velocity: 0.7 },
    { pitch: C5, duration: 2, velocity: 0.65 },
    { pitch: A4, duration: 4, velocity: 0.7 },
    // Bar 2 (F)
    { pitch: F4, duration: 2, velocity: 0.7 },
    { pitch: A4, duration: 2, velocity: 0.75 },
    { pitch: C5, duration: 6, velocity: 0.8 },
    { pitch: A4, duration: 2, velocity: 0.65 },
    { pitch: G4, duration: 4, velocity: 0.7 },
    // Bar 3 (C)
    { pitch: E5, duration: 2, velocity: 0.75 },
    { pitch: C5, duration: 2, velocity: 0.7 },
    { pitch: D5, duration: 4, velocity: 0.8 },
    { pitch: C5, duration: 4, velocity: 0.7 },
    { pitch: B4, duration: 2, velocity: 0.65 },
    { pitch: A4, duration: 2, velocity: 0.6 },
    // Bar 4 (G): resolution
    { pitch: G4, duration: 2, velocity: 0.7 },
    { pitch: B4, duration: 2, velocity: 0.75 },
    { pitch: D5, duration: 4, velocity: 0.8 },
    { pitch: C5, duration: 2, velocity: 0.7 },
    { pitch: B4, duration: 2, velocity: 0.65 },
    { pitch: A4, duration: 4, velocity: 0.7 },
  ]
}

function leadChorusA(): Note[] {
  // Chorus uses F→G→Am→Em — more triumphant feel
  return [
    // Bar 1 (F)
    { pitch: C5, duration: 4, velocity: 0.85 },
    { pitch: A4, duration: 2, velocity: 0.75 },
    { pitch: C5, duration: 2, velocity: 0.8 },
    { pitch: F4, duration: 4, velocity: 0.7 },
    { pitch: A4, duration: 2, velocity: 0.75 },
    { pitch: C5, duration: 2, velocity: 0.8 },
    // Bar 2 (G)
    { pitch: D5, duration: 4, velocity: 0.85 },
    { pitch: B4, duration: 2, velocity: 0.75 },
    { pitch: D5, duration: 2, velocity: 0.8 },
    { pitch: G4, duration: 4, velocity: 0.7 },
    { pitch: B4, duration: 4, velocity: 0.75 },
    // Bar 3 (Am)
    { pitch: E5, duration: 4, velocity: 0.9 },
    { pitch: C5, duration: 2, velocity: 0.8 },
    { pitch: A4, duration: 2, velocity: 0.75 },
    { pitch: E5, duration: 4, velocity: 0.85 },
    { pitch: D5, duration: 2, velocity: 0.8 },
    { pitch: C5, duration: 2, velocity: 0.75 },
    // Bar 4 (Em)
    { pitch: B4, duration: 4, velocity: 0.8 },
    { pitch: G4, duration: 2, velocity: 0.7 },
    { pitch: E4, duration: 2, velocity: 0.65 },
    { pitch: G4, duration: 4, velocity: 0.75 },
    { pitch: A4, duration: 4, velocity: 0.8 },
  ]
}

function leadBridge(): Note[] {
  // Bridge uses Dm→Em→F→G — building tension
  return [
    // Bar 1 (Dm)
    { pitch: D5, duration: 4, velocity: 0.7 },
    { pitch: F4, duration: 4, velocity: 0.65 },
    { pitch: A4, duration: 4, velocity: 0.7 },
    { pitch: 0, duration: 4 }, // rest
    // Bar 2 (Em)
    { pitch: E4, duration: 4, velocity: 0.7 },
    { pitch: G4, duration: 4, velocity: 0.65 },
    { pitch: B4, duration: 4, velocity: 0.7 },
    { pitch: 0, duration: 4 },
    // Bar 3 (F) — ascending tension
    { pitch: F4, duration: 2, velocity: 0.75 },
    { pitch: A4, duration: 2, velocity: 0.8 },
    { pitch: C5, duration: 2, velocity: 0.85 },
    { pitch: E5, duration: 6, velocity: 0.9 },
    { pitch: D5, duration: 2, velocity: 0.8 },
    { pitch: C5, duration: 2, velocity: 0.75 },
    // Bar 4 (G) — peak
    { pitch: G4, duration: 2, velocity: 0.8 },
    { pitch: B4, duration: 2, velocity: 0.85 },
    { pitch: D5, duration: 4, velocity: 0.9 },
    { pitch: E5, duration: 4, velocity: 0.85 },
    { pitch: D5, duration: 4, velocity: 0.8 },
  ]
}

function leadClimax(): Note[] {
  // Climax: high energy, wide intervals, highest velocity
  return [
    // Bar 1
    { pitch: E5, duration: 2, velocity: 0.9 },
    { pitch: A4, duration: 1, velocity: 0.85 },
    { pitch: C5, duration: 1, velocity: 0.85 },
    { pitch: E5, duration: 4, velocity: 0.95 },
    { pitch: D5, duration: 2, velocity: 0.85 },
    { pitch: E5, duration: 2, velocity: 0.9 },
    { pitch: C5, duration: 2, velocity: 0.85 },
    { pitch: A4, duration: 2, velocity: 0.8 },
    // Bar 2
    { pitch: D5, duration: 2, velocity: 0.9 },
    { pitch: C5, duration: 2, velocity: 0.85 },
    { pitch: B4, duration: 2, velocity: 0.85 },
    { pitch: D5, duration: 6, velocity: 0.95 },
    { pitch: C5, duration: 2, velocity: 0.85 },
    { pitch: B4, duration: 2, velocity: 0.8 },
    // Bar 3
    { pitch: C5, duration: 2, velocity: 0.9 },
    { pitch: E5, duration: 2, velocity: 0.95 },
    { pitch: E5, duration: 4, velocity: 0.9 },
    { pitch: D5, duration: 4, velocity: 0.85 },
    { pitch: C5, duration: 2, velocity: 0.85 },
    { pitch: A4, duration: 2, velocity: 0.8 },
    // Bar 4: resolution
    { pitch: A4, duration: 4, velocity: 0.85 },
    { pitch: G4, duration: 4, velocity: 0.8 },
    { pitch: A4, duration: 8, velocity: 0.9 },
  ]
}

// ---------------------------------------------------------------------------
// Counter-melody (triangle, octave below lead, fills the mid-range)
// ---------------------------------------------------------------------------

function counterMelodyVerse(): Note[] {
  return [
    // Bar 1: long held notes
    { pitch: A3, duration: 8, velocity: 0.5 },
    { pitch: E3, duration: 4, velocity: 0.45 },
    { pitch: C4, duration: 4, velocity: 0.5 },
    // Bar 2
    { pitch: F3, duration: 8, velocity: 0.5 },
    { pitch: A3, duration: 4, velocity: 0.45 },
    { pitch: C4, duration: 4, velocity: 0.5 },
    // Bar 3
    { pitch: C4, duration: 8, velocity: 0.5 },
    { pitch: G3, duration: 4, velocity: 0.45 },
    { pitch: E3, duration: 4, velocity: 0.5 },
    // Bar 4
    { pitch: G3, duration: 8, velocity: 0.5 },
    { pitch: D3, duration: 4, velocity: 0.45 },
    { pitch: G3, duration: 4, velocity: 0.5 },
  ]
}

function counterMelodyChorus(): Note[] {
  return [
    // More active counter-melody during chorus
    { pitch: F3, duration: 4, velocity: 0.55 },
    { pitch: A3, duration: 4, velocity: 0.5 },
    { pitch: C4, duration: 4, velocity: 0.55 },
    { pitch: A3, duration: 4, velocity: 0.5 },
    { pitch: G3, duration: 4, velocity: 0.55 },
    { pitch: D3, duration: 4, velocity: 0.5 },
    { pitch: G3, duration: 4, velocity: 0.55 },
    { pitch: D3, duration: 4, velocity: 0.5 },
    { pitch: A3, duration: 4, velocity: 0.55 },
    { pitch: E3, duration: 4, velocity: 0.5 },
    { pitch: A3, duration: 4, velocity: 0.55 },
    { pitch: C4, duration: 4, velocity: 0.5 },
    { pitch: E3, duration: 8, velocity: 0.55 },
    { pitch: G3, duration: 4, velocity: 0.5 },
    { pitch: A3, duration: 4, velocity: 0.55 },
  ]
}

// ---------------------------------------------------------------------------
// Atmosphere (very quiet sine notes, ambient texture)
// ---------------------------------------------------------------------------

function atmosphereBasic(): Note[] {
  return [
    // Very long, quiet sustained tones
    { pitch: atA5, duration: 32, velocity: 0.12 },
    { pitch: atE5, duration: 16, velocity: 0.1 },
    { pitch: atG5, duration: 16, velocity: 0.1 },
  ]
}

function atmosphereActive(): Note[] {
  return [
    { pitch: atE5, duration: 16, velocity: 0.15 },
    { pitch: atC6, duration: 16, velocity: 0.12 },
    { pitch: atA5, duration: 16, velocity: 0.15 },
    { pitch: atG5, duration: 16, velocity: 0.12 },
  ]
}

// ---------------------------------------------------------------------------
// Pad chords
// ---------------------------------------------------------------------------

function padChordCycle(chords: number[][]): Note[] {
  const notes: Note[] = []
  for (const chord of chords) {
    const toneCount = chord.length
    const stepsPerTone = Math.floor(16 / toneCount)
    for (let i = 0; i < toneCount; i++) {
      const dur = i === toneCount - 1 ? 16 - stepsPerTone * i : stepsPerTone
      notes.push({ pitch: chord[i], duration: dur, velocity: 0.35 })
    }
  }
  return notes
}

// ---------------------------------------------------------------------------
// Arp patterns
// ---------------------------------------------------------------------------

function arpPattern(chords: number[][]): Note[] {
  const notes: Note[] = []
  for (const chord of chords) {
    const arpNotes = arpeggio(chord, 'updown', 1)
    let step = 0
    while (step < 16) {
      for (const n of arpNotes) {
        if (step >= 16) break
        notes.push({ pitch: n.pitch, duration: 1, velocity: 0.5 })
        step++
      }
    }
  }
  return notes
}

function arpPatternSlow(chords: number[][]): Note[] {
  const notes: Note[] = []
  for (const chord of chords) {
    const arpNotes = arpeggio(chord, 'updown', 2)
    let step = 0
    while (step < 16) {
      for (const n of arpNotes) {
        if (step >= 16) break
        notes.push({ pitch: n.pitch, duration: 2, velocity: 0.4 })
        step += 2
      }
    }
  }
  return notes
}

// ---------------------------------------------------------------------------
// Progressions
// ---------------------------------------------------------------------------

const PROG_VERSE = [bassA, bassF, bassC, bassG]
const PROG_CHORUS = [bassF, bassG, bassA, bassE]
const PROG_BRIDGE = [bassD, bassE, bassF, bassG]

const PADS_VERSE = [padAm, padF, padC, padG]
const PADS_CHORUS = [padF, padG, padAm, padEm]
const PADS_BRIDGE = [padDm, padEm, padF, padG]

const ARPS_CHORUS = [F, G, Am, Em]
const ARPS_BRIDGE = [Dm, Em, F, G]

// ---------------------------------------------------------------------------
// Song definition
// ---------------------------------------------------------------------------

export const dinoRunnerSong: Song = {
  title: 'Neon Extinction',
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
        intro:     { notes: bassLineIntro(PROG_VERSE), length: 64 },
        verse1:    { notes: bassLine(PROG_VERSE), length: 64 },
        prechorus: { notes: bassLineSyncopated(PROG_BRIDGE), length: 64 },
        chorus1:   { notes: bassLine(PROG_CHORUS), length: 64 },
        verse2:    { notes: bassLine(PROG_VERSE), length: 64 },
        bridge:    { notes: bassLineIntro(PROG_BRIDGE), length: 64 },
        chorus2:   { notes: bassLine(PROG_CHORUS), length: 64 },
        breakdown: { notes: bassLineIntro(PROG_VERSE), length: 64 },
        climax:    { notes: bassLineClimb(PROG_CHORUS), length: 64 },
        outro:     { notes: bassLineIntro(PROG_VERSE), length: 64 },
      },
      gain: 0.5,
      effects: { filter: 600 },
    },

    lead: {
      name: 'lead',
      type: 'square',
      patterns: {
        chorus1:   { notes: leadChorusA(), length: 64 },
        verse2:    { notes: leadVerseA(), length: 64 },
        bridge:    { notes: leadBridge(), length: 64 },
        chorus2:   { notes: leadChorusA(), length: 64 },
        climax:    { notes: leadClimax(), length: 64 },
      },
      gain: 0.3,
      effects: { delay: 0.2, delayFeedback: 0.25 },
    },

    counterMelody: {
      name: 'counterMelody',
      type: 'triangle',
      patterns: {
        verse1:    { notes: counterMelodyVerse(), length: 64 },
        prechorus: { notes: counterMelodyVerse(), length: 64 },
        chorus1:   { notes: counterMelodyChorus(), length: 64 },
        verse2:    { notes: counterMelodyVerse(), length: 64 },
        chorus2:   { notes: counterMelodyChorus(), length: 64 },
        climax:    { notes: counterMelodyChorus(), length: 64 },
      },
      gain: 0.18,
      effects: { filter: 1500 },
    },

    pad: {
      name: 'pad',
      type: 'triangle',
      patterns: {
        verse1:    { notes: padChordCycle(PADS_VERSE), length: 64 },
        prechorus: { notes: padChordCycle(PADS_BRIDGE), length: 64 },
        chorus1:   { notes: padChordCycle(PADS_CHORUS), length: 64 },
        verse2:    { notes: padChordCycle(PADS_VERSE), length: 64 },
        bridge:    { notes: padChordCycle(PADS_BRIDGE), length: 64 },
        chorus2:   { notes: padChordCycle(PADS_CHORUS), length: 64 },
        breakdown: { notes: padChordCycle(PADS_VERSE), length: 64 },
        climax:    { notes: padChordCycle(PADS_CHORUS), length: 64 },
        outro:     { notes: padChordCycle(PADS_VERSE), length: 64 },
      },
      gain: 0.25,
      effects: { filter: 1200 },
    },

    arp: {
      name: 'arp',
      type: 'square',
      patterns: {
        prechorus: { notes: arpPatternSlow(ARPS_BRIDGE), length: 64 },
        chorus1:   { notes: arpPattern(ARPS_CHORUS), length: 64 },
        bridge:    { notes: arpPatternSlow(ARPS_BRIDGE), length: 64 },
        chorus2:   { notes: arpPattern(ARPS_CHORUS), length: 64 },
        climax:    { notes: arpPattern(ARPS_CHORUS), length: 64 },
      },
      gain: 0.2,
      effects: { filter: 2000, delay: 0.15, delayFeedback: 0.3 },
    },

    atmosphere: {
      name: 'atmosphere',
      type: 'sine',
      patterns: {
        intro:     { notes: atmosphereBasic(), length: 64 },
        verse1:    { notes: atmosphereBasic(), length: 64 },
        bridge:    { notes: atmosphereBasic(), length: 64 },
        breakdown: { notes: atmosphereActive(), length: 64 },
        climax:    { notes: atmosphereActive(), length: 64 },
        outro:     { notes: atmosphereBasic(), length: 64 },
      },
      gain: 0.08,
      effects: { filter: 3000 },
    },

    drums: {
      name: 'drums',
      type: 'noise',
      patterns: {
        intro:     { notes: drumPatternIntro(), length: 64 },
        verse1:    { notes: drumPatternBasic(4), length: 64 },
        prechorus: { notes: drumPatternBuild(), length: 64 },
        chorus1:   { notes: drumPatternBasic(4), length: 64 },
        verse2:    { notes: drumPatternBasic(4), length: 64 },
        bridge:    { notes: drumPatternHalfTime(4), length: 64 },
        chorus2:   { notes: drumPatternBasic(4), length: 64 },
        breakdown: { notes: drumPatternHalfTime(4), length: 64 },
        climax:    { notes: drumPatternClimaxFill(), length: 64 },
        outro:     { notes: drumPatternIntro(), length: 64 },
      },
      gain: 0.7,
    },
  },

  sections: {
    intro:     { name: 'intro',     bars: 4, channels: { drums: 'intro', bass: 'intro', atmosphere: 'intro' }, next: 'verse1' },
    verse1:    { name: 'verse1',    bars: 4, channels: { drums: 'verse1', bass: 'verse1', pad: 'verse1', counterMelody: 'verse1', atmosphere: 'verse1' }, next: 'prechorus' },
    prechorus: { name: 'prechorus', bars: 4, channels: { drums: 'prechorus', bass: 'prechorus', pad: 'prechorus', arp: 'prechorus', counterMelody: 'prechorus' }, next: 'chorus1' },
    chorus1:   { name: 'chorus1',   bars: 4, channels: { drums: 'chorus1', bass: 'chorus1', pad: 'chorus1', arp: 'chorus1', lead: 'chorus1', counterMelody: 'chorus1' }, next: 'verse2' },
    verse2:    { name: 'verse2',    bars: 4, channels: { drums: 'verse2', bass: 'verse2', pad: 'verse2', lead: 'verse2', counterMelody: 'verse2' }, next: 'bridge' },
    bridge:    { name: 'bridge',    bars: 4, channels: { bass: 'bridge', pad: 'bridge', arp: 'bridge', lead: 'bridge', atmosphere: 'bridge' }, next: 'chorus2' },
    chorus2:   { name: 'chorus2',   bars: 4, channels: { drums: 'chorus2', bass: 'chorus2', pad: 'chorus2', arp: 'chorus2', lead: 'chorus2', counterMelody: 'chorus2' }, next: 'breakdown' },
    breakdown: { name: 'breakdown', bars: 4, channels: { drums: 'breakdown', bass: 'breakdown', pad: 'breakdown', atmosphere: 'breakdown' }, next: 'climax' },
    climax:    { name: 'climax',    bars: 4, channels: { drums: 'climax', bass: 'climax', pad: 'climax', arp: 'climax', lead: 'climax', counterMelody: 'climax', atmosphere: 'climax' }, next: 'outro' },
    outro:     { name: 'outro',     bars: 4, channels: { drums: 'outro', bass: 'outro', pad: 'outro', atmosphere: 'outro' }, next: 'verse1' },
  },

  // Progressive intensity: channels unlock as score increases
  intensityMap: {
    0:    ['drums', 'bass'],
    300:  ['drums', 'bass', 'pad'],
    800:  ['drums', 'bass', 'pad', 'atmosphere'],
    1500: ['drums', 'bass', 'pad', 'atmosphere', 'counterMelody'],
    2500: ['drums', 'bass', 'pad', 'atmosphere', 'counterMelody', 'arp'],
    4000: ['drums', 'bass', 'pad', 'atmosphere', 'counterMelody', 'arp', 'lead'],
  },
}
