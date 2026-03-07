/**
 * Seeded song factory — generates complete Song objects from genre presets
 * and a deterministic seed. Same seed + genre = same song every time.
 *
 * Uses Mulberry32 PRNG for all random decisions.
 * v2: Musically-aware generation with chord-tone melodies, genre-specific bass,
 * section contrast, drum fills, per-channel ADSR, and genre filter design.
 */

import type { Song, Note, Channel, Section, Pattern } from './songTypes'
import {
  getScaleMultiOctave,
  seededArpeggio,
  SCALES, RHYTHM_TEMPLATES,
  resolveChordSpecs,
  nearestChordTone, walkingBassLine,
  motifDevelop, callAndResponse,
} from './musicTheory'

// ---------------------------------------------------------------------------
// Deterministic PRNG (Mulberry32)
// ---------------------------------------------------------------------------

/** Create a seeded PRNG. Returns a function that produces 0–1 on each call. */
export function mulberry32(seed: number): () => number {
  let s = seed | 0
  return () => {
    s = (s + 0x6D2B79F5) | 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Pick a random element from an array using the provided RNG. */
function pick<T>(arr: readonly T[], rng: () => number): T {
  return arr[Math.floor(rng() * arr.length)]
}

/** Pick a random integer in [min, max] inclusive. */
function randInt(min: number, max: number, rng: () => number): number {
  return Math.floor(rng() * (max - min + 1)) + min
}

// ---------------------------------------------------------------------------
// ADSR Envelope Configs (per-genre, per-channel)
// ---------------------------------------------------------------------------

interface AdsrConfig {
  attack: number; decay: number; sustain: number; release: number
}

interface GenreAdsrSet {
  bass: AdsrConfig
  lead: AdsrConfig
  pad: AdsrConfig
  arp: AdsrConfig
}

const GENRE_ADSR: Record<string, GenreAdsrSet> = {
  synthwave:  { bass: { attack: 0.02, decay: 0.1, sustain: 0.6, release: 0.05 }, lead: { attack: 0.005, decay: 0.05, sustain: 0.8, release: 0.1 }, pad: { attack: 0.2, decay: 0.3, sustain: 0.5, release: 0.3 }, arp: { attack: 0.005, decay: 0.03, sustain: 0.3, release: 0.05 } },
  chiptune:   { bass: { attack: 0.005, decay: 0.02, sustain: 0.8, release: 0.02 }, lead: { attack: 0.001, decay: 0.01, sustain: 0.9, release: 0.02 }, pad: { attack: 0.01, decay: 0.05, sustain: 0.7, release: 0.05 }, arp: { attack: 0.001, decay: 0.01, sustain: 0.6, release: 0.02 } },
  lofi:       { bass: { attack: 0.02, decay: 0.1, sustain: 0.5, release: 0.1 }, lead: { attack: 0.01, decay: 0.08, sustain: 0.5, release: 0.15 }, pad: { attack: 0.15, decay: 0.2, sustain: 0.5, release: 0.25 }, arp: { attack: 0.01, decay: 0.05, sustain: 0.4, release: 0.08 } },
  ambient:    { bass: { attack: 0.1, decay: 0.3, sustain: 0.4, release: 0.5 }, lead: { attack: 0.15, decay: 0.4, sustain: 0.3, release: 0.5 }, pad: { attack: 0.5, decay: 0.5, sustain: 0.4, release: 0.8 }, arp: { attack: 0.1, decay: 0.2, sustain: 0.3, release: 0.3 } },
  jazz:       { bass: { attack: 0.01, decay: 0.05, sustain: 0.7, release: 0.08 }, lead: { attack: 0.01, decay: 0.08, sustain: 0.6, release: 0.15 }, pad: { attack: 0.1, decay: 0.2, sustain: 0.6, release: 0.2 }, arp: { attack: 0.005, decay: 0.04, sustain: 0.5, release: 0.08 } },
  classical:  { bass: { attack: 0.02, decay: 0.08, sustain: 0.6, release: 0.12 }, lead: { attack: 0.01, decay: 0.06, sustain: 0.7, release: 0.15 }, pad: { attack: 0.15, decay: 0.25, sustain: 0.5, release: 0.3 }, arp: { attack: 0.01, decay: 0.04, sustain: 0.5, release: 0.08 } },
  blues:      { bass: { attack: 0.01, decay: 0.06, sustain: 0.65, release: 0.08 }, lead: { attack: 0.005, decay: 0.05, sustain: 0.7, release: 0.12 }, pad: { attack: 0.1, decay: 0.15, sustain: 0.55, release: 0.2 }, arp: { attack: 0.005, decay: 0.04, sustain: 0.5, release: 0.06 } },
  rock:       { bass: { attack: 0.01, decay: 0.05, sustain: 0.7, release: 0.05 }, lead: { attack: 0.005, decay: 0.03, sustain: 0.85, release: 0.08 }, pad: { attack: 0.08, decay: 0.15, sustain: 0.6, release: 0.15 }, arp: { attack: 0.005, decay: 0.03, sustain: 0.5, release: 0.05 } },
  edm:        { bass: { attack: 0.005, decay: 0.05, sustain: 0.7, release: 0.03 }, lead: { attack: 0.005, decay: 0.04, sustain: 0.8, release: 0.08 }, pad: { attack: 0.15, decay: 0.2, sustain: 0.5, release: 0.25 }, arp: { attack: 0.003, decay: 0.02, sustain: 0.4, release: 0.03 } },
  latin:      { bass: { attack: 0.01, decay: 0.05, sustain: 0.65, release: 0.06 }, lead: { attack: 0.008, decay: 0.05, sustain: 0.7, release: 0.1 }, pad: { attack: 0.1, decay: 0.15, sustain: 0.55, release: 0.2 }, arp: { attack: 0.005, decay: 0.03, sustain: 0.5, release: 0.05 } },
  funk:       { bass: { attack: 0.005, decay: 0.04, sustain: 0.7, release: 0.04 }, lead: { attack: 0.005, decay: 0.03, sustain: 0.8, release: 0.08 }, pad: { attack: 0.08, decay: 0.12, sustain: 0.55, release: 0.15 }, arp: { attack: 0.003, decay: 0.025, sustain: 0.45, release: 0.04 } },
  reggae:     { bass: { attack: 0.02, decay: 0.08, sustain: 0.6, release: 0.1 }, lead: { attack: 0.01, decay: 0.06, sustain: 0.6, release: 0.12 }, pad: { attack: 0.1, decay: 0.15, sustain: 0.5, release: 0.2 }, arp: { attack: 0.008, decay: 0.04, sustain: 0.5, release: 0.08 } },
  celtic:     { bass: { attack: 0.01, decay: 0.06, sustain: 0.65, release: 0.08 }, lead: { attack: 0.005, decay: 0.04, sustain: 0.75, release: 0.1 }, pad: { attack: 0.1, decay: 0.2, sustain: 0.5, release: 0.2 }, arp: { attack: 0.005, decay: 0.03, sustain: 0.5, release: 0.06 } },
  arabic:     { bass: { attack: 0.01, decay: 0.06, sustain: 0.6, release: 0.08 }, lead: { attack: 0.008, decay: 0.05, sustain: 0.7, release: 0.12 }, pad: { attack: 0.12, decay: 0.2, sustain: 0.5, release: 0.25 }, arp: { attack: 0.005, decay: 0.035, sustain: 0.5, release: 0.06 } },
  japanese:   { bass: { attack: 0.05, decay: 0.15, sustain: 0.5, release: 0.2 }, lead: { attack: 0.08, decay: 0.2, sustain: 0.4, release: 0.3 }, pad: { attack: 0.3, decay: 0.35, sustain: 0.45, release: 0.5 }, arp: { attack: 0.05, decay: 0.1, sustain: 0.35, release: 0.15 } },
  cinematic:  { bass: { attack: 0.05, decay: 0.15, sustain: 0.5, release: 0.2 }, lead: { attack: 0.08, decay: 0.2, sustain: 0.4, release: 0.3 }, pad: { attack: 0.4, decay: 0.4, sustain: 0.45, release: 0.6 }, arp: { attack: 0.05, decay: 0.1, sustain: 0.35, release: 0.15 } },
  disco:      { bass: { attack: 0.005, decay: 0.04, sustain: 0.7, release: 0.04 }, lead: { attack: 0.005, decay: 0.03, sustain: 0.8, release: 0.08 }, pad: { attack: 0.1, decay: 0.15, sustain: 0.55, release: 0.2 }, arp: { attack: 0.003, decay: 0.025, sustain: 0.4, release: 0.04 } },
  bossanova:  { bass: { attack: 0.01, decay: 0.06, sustain: 0.6, release: 0.08 }, lead: { attack: 0.01, decay: 0.06, sustain: 0.6, release: 0.12 }, pad: { attack: 0.12, decay: 0.2, sustain: 0.5, release: 0.25 }, arp: { attack: 0.008, decay: 0.04, sustain: 0.45, release: 0.08 } },
  metal:      { bass: { attack: 0.005, decay: 0.03, sustain: 0.8, release: 0.03 }, lead: { attack: 0.003, decay: 0.02, sustain: 0.9, release: 0.05 }, pad: { attack: 0.05, decay: 0.1, sustain: 0.7, release: 0.1 }, arp: { attack: 0.003, decay: 0.02, sustain: 0.5, release: 0.03 } },
  electronic: { bass: { attack: 0.005, decay: 0.05, sustain: 0.65, release: 0.04 }, lead: { attack: 0.005, decay: 0.04, sustain: 0.75, release: 0.08 }, pad: { attack: 0.2, decay: 0.25, sustain: 0.45, release: 0.3 }, arp: { attack: 0.003, decay: 0.025, sustain: 0.4, release: 0.04 } },
}

// Default ADSR for genres not explicitly listed
const DEFAULT_ADSR: GenreAdsrSet = {
  bass: { attack: 0.02, decay: 0.08, sustain: 0.6, release: 0.05 },
  lead: { attack: 0.005, decay: 0.04, sustain: 0.8, release: 0.1 },
  pad:  { attack: 0.15, decay: 0.2, sustain: 0.5, release: 0.3 },
  arp:  { attack: 0.005, decay: 0.03, sustain: 0.4, release: 0.05 },
}

// ---------------------------------------------------------------------------
// Per-Genre Filter Configs
// ---------------------------------------------------------------------------

interface GenreFilterSet {
  bass: number
  pad: number
  arp: number
  lead: number
  delay?: number
  delayFeedback?: number
}

const GENRE_FILTERS: Record<string, GenreFilterSet> = {
  synthwave:  { bass: 600, pad: 1500, arp: 3000, lead: 2000, delay: 0.2, delayFeedback: 0.25 },
  chiptune:   { bass: 4000, pad: 2000, arp: 5000, lead: 4000 },
  lofi:       { bass: 400, pad: 800, arp: 1200, lead: 1000, delay: 0.1, delayFeedback: 0.2 },
  ambient:    { bass: 300, pad: 600, arp: 1500, lead: 800, delay: 0.4, delayFeedback: 0.35 },
  jazz:       { bass: 500, pad: 1200, arp: 2000, lead: 1500, delay: 0.15, delayFeedback: 0.2 },
  classical:  { bass: 600, pad: 1500, arp: 2500, lead: 2000 },
  blues:      { bass: 450, pad: 1000, arp: 1800, lead: 1200, delay: 0.12, delayFeedback: 0.2 },
  rock:       { bass: 700, pad: 1200, arp: 2500, lead: 2000 },
  edm:        { bass: 1000, pad: 2000, arp: 4000, lead: 3000, delay: 0.15, delayFeedback: 0.3 },
  latin:      { bass: 500, pad: 1200, arp: 2200, lead: 1800, delay: 0.1, delayFeedback: 0.2 },
  funk:       { bass: 600, pad: 1200, arp: 2500, lead: 2000 },
  reggae:     { bass: 400, pad: 1000, arp: 1800, lead: 1200, delay: 0.2, delayFeedback: 0.3 },
  celtic:     { bass: 500, pad: 1500, arp: 2500, lead: 2000, delay: 0.15, delayFeedback: 0.2 },
  arabic:     { bass: 400, pad: 1200, arp: 2200, lead: 1500, delay: 0.15, delayFeedback: 0.25 },
  japanese:   { bass: 350, pad: 700, arp: 1500, lead: 1000, delay: 0.3, delayFeedback: 0.3 },
  cinematic:  { bass: 350, pad: 700, arp: 1800, lead: 1000, delay: 0.35, delayFeedback: 0.3 },
  disco:      { bass: 700, pad: 1500, arp: 3500, lead: 2500, delay: 0.15, delayFeedback: 0.2 },
  bossanova:  { bass: 450, pad: 1000, arp: 1800, lead: 1200, delay: 0.15, delayFeedback: 0.2 },
  metal:      { bass: 800, pad: 1000, arp: 3000, lead: 2500 },
  electronic: { bass: 600, pad: 1500, arp: 3500, lead: 2500, delay: 0.2, delayFeedback: 0.3 },
}

// ---------------------------------------------------------------------------
// Per-Genre Intensity Maps
// ---------------------------------------------------------------------------

type IntensityCategory = 'arcade' | 'chill' | 'strategic' | 'highEnergy'

const INTENSITY_MAPS: Record<IntensityCategory, Record<number, string[]>> = {
  arcade: {
    0:    ['drums', 'bass'],
    200:  ['drums', 'bass', 'pad'],
    500:  ['drums', 'bass', 'pad', 'arp'],
    1000: ['drums', 'bass', 'pad', 'arp', 'lead'],
  },
  chill: {
    0:    ['pad'],
    300:  ['pad', 'bass'],
    1000: ['pad', 'bass', 'arp'],
    2000: ['pad', 'bass', 'arp', 'drums'],
    3000: ['pad', 'bass', 'arp', 'drums', 'lead'],
  },
  strategic: {
    0:    ['pad', 'bass'],
    400:  ['pad', 'bass', 'drums'],
    1000: ['pad', 'bass', 'drums', 'arp'],
    1500: ['pad', 'bass', 'drums', 'arp', 'lead'],
  },
  highEnergy: {
    0:    ['drums', 'bass'],
    150:  ['drums', 'bass', 'pad'],
    400:  ['drums', 'bass', 'pad', 'arp'],
    800:  ['drums', 'bass', 'pad', 'arp', 'lead'],
  },
}

const GENRE_INTENSITY_CATEGORY: Record<string, IntensityCategory> = {
  synthwave: 'arcade', chiptune: 'arcade', edm: 'highEnergy', metal: 'highEnergy',
  rock: 'highEnergy', disco: 'arcade', funk: 'highEnergy', electronic: 'highEnergy',
  ambient: 'chill', japanese: 'chill', lofi: 'chill', bossanova: 'chill',
  jazz: 'strategic', classical: 'strategic', blues: 'strategic', celtic: 'strategic',
  latin: 'strategic', arabic: 'strategic', cinematic: 'strategic', reggae: 'chill',
}

// ---------------------------------------------------------------------------
// Section Density Config
// ---------------------------------------------------------------------------

interface SectionCharacter {
  /** Which channels are active (others muted in pattern). */
  activeChannels: string[]
  /** Velocity multiplier 0–1. */
  velocityMul: number
  /** Melodic density: 'sparse' | 'medium' | 'full'. */
  density: 'sparse' | 'medium' | 'full'
  /** Whether to add drum fill on last bar. */
  drumFill: boolean
}

function getSectionCharacter(sectionName: string): SectionCharacter {
  if (sectionName === 'intro') {
    return { activeChannels: ['bass', 'drums'], velocityMul: 0.6, density: 'sparse', drumFill: false }
  }
  if (sectionName === 'outro') {
    return { activeChannels: ['bass', 'drums', 'pad'], velocityMul: 0.5, density: 'sparse', drumFill: false }
  }
  if (sectionName.includes('verse')) {
    return { activeChannels: ['bass', 'drums', 'pad', 'lead'], velocityMul: 0.75, density: 'medium', drumFill: true }
  }
  if (sectionName.includes('chorus') || sectionName.includes('drop')) {
    return { activeChannels: ['bass', 'drums', 'pad', 'lead', 'arp'], velocityMul: 1.0, density: 'full', drumFill: true }
  }
  if (sectionName.includes('bridge')) {
    return { activeChannels: ['bass', 'drums', 'pad', 'lead'], velocityMul: 0.7, density: 'medium', drumFill: false }
  }
  if (sectionName.includes('break') || sectionName.includes('breakdown')) {
    return { activeChannels: ['bass', 'pad'], velocityMul: 0.4, density: 'sparse', drumFill: false }
  }
  if (sectionName.includes('build')) {
    return { activeChannels: ['bass', 'drums', 'pad', 'arp'], velocityMul: 0.85, density: 'medium', drumFill: true }
  }
  if (sectionName.includes('climax')) {
    return { activeChannels: ['bass', 'drums', 'pad', 'lead', 'arp'], velocityMul: 1.0, density: 'full', drumFill: true }
  }
  // Default: verse-like
  return { activeChannels: ['bass', 'drums', 'pad', 'lead'], velocityMul: 0.75, density: 'medium', drumFill: true }
}

// ---------------------------------------------------------------------------
// Genre-Specific Rest Probability
// ---------------------------------------------------------------------------

function getRestProbability(genre: string, sectionName: string): number {
  const base: Record<string, number> = {
    ambient: 0.4, japanese: 0.35, cinematic: 0.3, lofi: 0.25,
    jazz: 0.25, blues: 0.2, bossanova: 0.2, classical: 0.2,
    reggae: 0.2, celtic: 0.15, latin: 0.15, funk: 0.15,
    synthwave: 0.15, rock: 0.12, disco: 0.12, edm: 0.1,
    chiptune: 0.1, metal: 0.08, electronic: 0.12, arabic: 0.2,
  }
  const prob = base[genre] ?? 0.15
  // More rests in intro/outro, fewer in chorus/drop
  if (sectionName === 'intro' || sectionName === 'outro') return Math.min(prob + 0.15, 0.6)
  if (sectionName.includes('chorus') || sectionName.includes('drop') || sectionName.includes('climax'))
    return Math.max(prob - 0.05, 0.05)
  return prob
}

// ---------------------------------------------------------------------------
// Genre Presets
// ---------------------------------------------------------------------------

export interface GenrePreset {
  name: string
  scaleOptions: string[]
  keyOptions: string[]
  bpmRange: [number, number]
  progressions: string[]
  rhythmStyle: string
  arpStyle: 'up' | 'down' | 'updown' | 'random'
  drumStyle: 'fourOnFloor' | 'halftime' | 'shuffle' | 'sparse' | 'blast' | 'offbeat' | 'dnb' | 'none'
  channelTypes: {
    bass: 'sawtooth' | 'square' | 'triangle' | 'sine'
    lead: 'square' | 'sawtooth' | 'triangle' | 'sine'
    pad: 'triangle' | 'sine' | 'sawtooth'
    arp: 'square' | 'triangle' | 'sawtooth' | 'sine'
  }
  sectionFlow: string[]
  bassOctave: number
  chordOctave: number
  leadOctave: number
  filterRange: [number, number]
  hasDelay: boolean
  character: string
}

export const GENRE_PRESETS: Record<string, GenrePreset> = {
  synthwave: {
    name: 'Synthwave',
    scaleOptions: ['minor', 'dorian'],
    keyOptions: ['A', 'E', 'D', 'F#'],
    bpmRange: [110, 130],
    progressions: ['sad', 'dark', 'pop'],
    rhythmStyle: 'straight8ths',
    arpStyle: 'updown',
    drumStyle: 'fourOnFloor',
    channelTypes: { bass: 'sawtooth', lead: 'square', pad: 'triangle', arp: 'square' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'bridge', 'chorus2', 'outro'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [400, 2000],
    hasDelay: true,
    character: 'Retro neon, arpeggiated',
  },
  chiptune: {
    name: 'Chiptune',
    scaleOptions: ['major', 'minor', 'pentatonic'],
    keyOptions: ['C', 'G', 'D', 'A'],
    bpmRange: [130, 160],
    progressions: ['pop', 'rock', 'power'],
    rhythmStyle: 'straight16ths',
    arpStyle: 'up',
    drumStyle: 'fourOnFloor',
    channelTypes: { bass: 'square', lead: 'square', pad: 'triangle', arp: 'square' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'bridge', 'chorus2'],
    bassOctave: 2, chordOctave: 3, leadOctave: 5,
    filterRange: [800, 4000],
    hasDelay: false,
    character: '8-bit, fast arps',
  },
  lofi: {
    name: 'Lo-fi',
    scaleOptions: ['dorian', 'minor', 'pentatonic'],
    keyOptions: ['D', 'G', 'C', 'Bb'],
    bpmRange: [70, 85],
    progressions: ['jazz251', 'jazz1625', 'neosoul'],
    rhythmStyle: 'shuffle',
    arpStyle: 'random',
    drumStyle: 'halftime',
    channelTypes: { bass: 'triangle', lead: 'sine', pad: 'triangle', arp: 'sine' },
    sectionFlow: ['intro', 'verse', 'verse2', 'chorus', 'verse3', 'chorus2', 'outro'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [300, 1200],
    hasDelay: true,
    character: 'Jazzy chords, vinyl feel',
  },
  ambient: {
    name: 'Ambient',
    scaleOptions: ['lydian', 'majorPentatonic', 'wholeTone'],
    keyOptions: ['C', 'F', 'Ab', 'Eb'],
    bpmRange: [60, 80],
    progressions: ['dreamy', 'modal'],
    rhythmStyle: 'halfNotes',
    arpStyle: 'updown',
    drumStyle: 'none',
    channelTypes: { bass: 'sine', lead: 'sine', pad: 'sine', arp: 'triangle' },
    sectionFlow: ['intro', 'verse', 'verse2', 'chorus', 'verse3', 'outro'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [200, 800],
    hasDelay: true,
    character: 'Slow pads, atmospheric',
  },
  jazz: {
    name: 'Jazz',
    scaleOptions: ['dorian', 'mixolydian', 'bebopDominant'],
    keyOptions: ['Bb', 'F', 'Eb', 'C'],
    bpmRange: [100, 140],
    progressions: ['jazz251', 'jazz1625', 'neosoul'],
    rhythmStyle: 'shuffle',
    arpStyle: 'random',
    drumStyle: 'shuffle',
    channelTypes: { bass: 'triangle', lead: 'sine', pad: 'triangle', arp: 'sine' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'bridge', 'chorus2', 'outro'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [400, 2000],
    hasDelay: true,
    character: 'Walking bass, complex chords',
  },
  classical: {
    name: 'Classical',
    scaleOptions: ['ionian', 'minor', 'harmonicMinor'],
    keyOptions: ['C', 'G', 'D', 'A', 'F'],
    bpmRange: [80, 120],
    progressions: ['waltz', 'pop', 'sad'],
    rhythmStyle: 'straight8ths',
    arpStyle: 'updown',
    drumStyle: 'none',
    channelTypes: { bass: 'triangle', lead: 'triangle', pad: 'sine', arp: 'triangle' },
    sectionFlow: ['intro', 'verse', 'verse2', 'chorus', 'bridge', 'chorus2', 'outro'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [500, 3000],
    hasDelay: false,
    character: 'Counterpoint, dynamic range',
  },
  blues: {
    name: 'Blues',
    scaleOptions: ['blues', 'pentatonic', 'mixolydian'],
    keyOptions: ['E', 'A', 'G', 'C'],
    bpmRange: [80, 110],
    progressions: ['blues12bar', 'minorBlues'],
    rhythmStyle: 'shuffle',
    arpStyle: 'up',
    drumStyle: 'shuffle',
    channelTypes: { bass: 'triangle', lead: 'sawtooth', pad: 'triangle', arp: 'triangle' },
    sectionFlow: ['intro', 'verse', 'verse2', 'chorus', 'verse3', 'chorus2'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [300, 1500],
    hasDelay: true,
    character: '12-bar, pentatonic leads',
  },
  rock: {
    name: 'Rock',
    scaleOptions: ['mixolydian', 'pentatonic', 'minor'],
    keyOptions: ['E', 'A', 'G', 'D'],
    bpmRange: [120, 150],
    progressions: ['rock', 'power', 'pop'],
    rhythmStyle: 'straight8ths',
    arpStyle: 'up',
    drumStyle: 'fourOnFloor',
    channelTypes: { bass: 'sawtooth', lead: 'sawtooth', pad: 'sawtooth', arp: 'square' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'chorus2', 'bridge', 'chorus3'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [500, 3000],
    hasDelay: false,
    character: 'Power chords, driving rhythm',
  },
  edm: {
    name: 'EDM',
    scaleOptions: ['minor', 'dorian', 'harmonicMinor'],
    keyOptions: ['F', 'G', 'A', 'C'],
    bpmRange: [125, 140],
    progressions: ['dark', 'sad', 'pop'],
    rhythmStyle: 'straight16ths',
    arpStyle: 'updown',
    drumStyle: 'fourOnFloor',
    channelTypes: { bass: 'sawtooth', lead: 'sawtooth', pad: 'triangle', arp: 'square' },
    sectionFlow: ['intro', 'buildup', 'drop', 'breakdown', 'buildup2', 'drop2', 'outro'],
    bassOctave: 1, chordOctave: 3, leadOctave: 4,
    filterRange: [200, 3000],
    hasDelay: true,
    character: 'Build-drop structure',
  },
  latin: {
    name: 'Latin',
    scaleOptions: ['phrygian', 'minor', 'harmonicMinor'],
    keyOptions: ['A', 'D', 'E', 'G'],
    bpmRange: [100, 130],
    progressions: ['andalusian', 'tension'],
    rhythmStyle: 'tresillo',
    arpStyle: 'up',
    drumStyle: 'fourOnFloor',
    channelTypes: { bass: 'triangle', lead: 'triangle', pad: 'sine', arp: 'triangle' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'bridge', 'chorus2'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [400, 2000],
    hasDelay: true,
    character: 'Tresillo rhythm, Andalusian cadence',
  },
  funk: {
    name: 'Funk',
    scaleOptions: ['mixolydian', 'dorian', 'blues'],
    keyOptions: ['E', 'A', 'D', 'G'],
    bpmRange: [95, 115],
    progressions: ['dorian', 'rock', 'neosoul'],
    rhythmStyle: 'syncopated',
    arpStyle: 'random',
    drumStyle: 'fourOnFloor',
    channelTypes: { bass: 'sawtooth', lead: 'square', pad: 'triangle', arp: 'square' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'bridge', 'chorus2', 'outro'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [500, 2500],
    hasDelay: false,
    character: 'Syncopated, slap bass feel',
  },
  reggae: {
    name: 'Reggae',
    scaleOptions: ['minor', 'pentatonic', 'dorian'],
    keyOptions: ['G', 'C', 'D', 'A'],
    bpmRange: [70, 85],
    progressions: ['reggae', 'pop', 'rock'],
    rhythmStyle: 'reggae',
    arpStyle: 'up',
    drumStyle: 'offbeat',
    channelTypes: { bass: 'triangle', lead: 'sine', pad: 'triangle', arp: 'sine' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'chorus2', 'outro'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [300, 1500],
    hasDelay: true,
    character: 'Off-beat chords, one-drop',
  },
  celtic: {
    name: 'Celtic',
    scaleOptions: ['mixolydian', 'dorian', 'majorPentatonic'],
    keyOptions: ['D', 'G', 'A', 'C'],
    bpmRange: [100, 130],
    progressions: ['modal', 'rock', 'waltz'],
    rhythmStyle: 'dotted',
    arpStyle: 'updown',
    drumStyle: 'fourOnFloor',
    channelTypes: { bass: 'triangle', lead: 'triangle', pad: 'sine', arp: 'triangle' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'bridge', 'chorus2'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [400, 2500],
    hasDelay: true,
    character: 'Jig/reel patterns, pentatonic melody',
  },
  arabic: {
    name: 'Arabic',
    scaleOptions: ['arabic', 'harmonicMinor', 'phrygian'],
    keyOptions: ['D', 'A', 'E', 'G'],
    bpmRange: [90, 120],
    progressions: ['andalusian', 'tension', 'dark'],
    rhythmStyle: 'dotted',
    arpStyle: 'updown',
    drumStyle: 'fourOnFloor',
    channelTypes: { bass: 'triangle', lead: 'sine', pad: 'sine', arp: 'triangle' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'bridge', 'chorus2'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [300, 2000],
    hasDelay: true,
    character: 'Double harmonic scale, ornamental',
  },
  japanese: {
    name: 'Japanese',
    scaleOptions: ['japanese', 'pentatonic'],
    keyOptions: ['D', 'A', 'E', 'G'],
    bpmRange: [70, 100],
    progressions: ['modal', 'dreamy'],
    rhythmStyle: 'halfNotes',
    arpStyle: 'updown',
    drumStyle: 'sparse',
    channelTypes: { bass: 'sine', lead: 'triangle', pad: 'sine', arp: 'sine' },
    sectionFlow: ['intro', 'verse', 'verse2', 'chorus', 'verse3', 'outro'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [200, 1500],
    hasDelay: true,
    character: 'Pentatonic, sparse, meditative',
  },
  cinematic: {
    name: 'Cinematic',
    scaleOptions: ['harmonicMinor', 'minor', 'lydian'],
    keyOptions: ['D', 'C', 'A', 'E'],
    bpmRange: [70, 100],
    progressions: ['epic', 'dark', 'tension'],
    rhythmStyle: 'halfNotes',
    arpStyle: 'updown',
    drumStyle: 'sparse',
    channelTypes: { bass: 'sine', lead: 'triangle', pad: 'sine', arp: 'triangle' },
    sectionFlow: ['intro', 'verse', 'buildup', 'chorus', 'verse2', 'climax', 'outro'],
    bassOctave: 1, chordOctave: 3, leadOctave: 4,
    filterRange: [200, 1500],
    hasDelay: true,
    character: 'Dramatic builds, epic chords',
  },
  disco: {
    name: 'Disco',
    scaleOptions: ['major', 'mixolydian', 'dorian'],
    keyOptions: ['C', 'F', 'G', 'D'],
    bpmRange: [115, 125],
    progressions: ['pop', 'neosoul', 'rock'],
    rhythmStyle: 'straight8ths',
    arpStyle: 'up',
    drumStyle: 'fourOnFloor',
    channelTypes: { bass: 'sawtooth', lead: 'square', pad: 'triangle', arp: 'square' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'bridge', 'chorus2', 'outro'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [500, 3000],
    hasDelay: true,
    character: 'Four-on-floor, octave bass',
  },
  bossanova: {
    name: 'Bossa Nova',
    scaleOptions: ['dorian', 'major', 'lydian'],
    keyOptions: ['C', 'F', 'G', 'D'],
    bpmRange: [130, 150],
    progressions: ['jazz251', 'jazz1625', 'dreamy'],
    rhythmStyle: 'bossanova',
    arpStyle: 'updown',
    drumStyle: 'sparse',
    channelTypes: { bass: 'triangle', lead: 'sine', pad: 'sine', arp: 'triangle' },
    sectionFlow: ['intro', 'verse', 'verse2', 'chorus', 'verse3', 'chorus2', 'outro'],
    bassOctave: 2, chordOctave: 3, leadOctave: 4,
    filterRange: [300, 1500],
    hasDelay: true,
    character: 'Brazilian rhythm, extended chords',
  },
  metal: {
    name: 'Metal',
    scaleOptions: ['phrygian', 'locrian', 'harmonicMinor'],
    keyOptions: ['E', 'D', 'B', 'A'],
    bpmRange: [140, 180],
    progressions: ['dark', 'power', 'tension'],
    rhythmStyle: 'straight16ths',
    arpStyle: 'up',
    drumStyle: 'blast',
    channelTypes: { bass: 'sawtooth', lead: 'sawtooth', pad: 'sawtooth', arp: 'square' },
    sectionFlow: ['intro', 'verse', 'chorus', 'verse2', 'bridge', 'chorus2', 'breakdown'],
    bassOctave: 1, chordOctave: 2, leadOctave: 4,
    filterRange: [600, 4000],
    hasDelay: false,
    character: 'Tremolo, blast beats, dark',
  },
  electronic: {
    name: 'Electronic',
    scaleOptions: ['wholeTone', 'chromatic', 'lydian'],
    keyOptions: ['C', 'F#', 'Bb', 'E'],
    bpmRange: [120, 140],
    progressions: ['modal', 'dreamy', 'coltrane'],
    rhythmStyle: 'syncopated',
    arpStyle: 'random',
    drumStyle: 'dnb',
    channelTypes: { bass: 'sawtooth', lead: 'square', pad: 'sine', arp: 'square' },
    sectionFlow: ['intro', 'verse', 'drop', 'verse2', 'drop2', 'breakdown', 'outro'],
    bassOctave: 1, chordOctave: 3, leadOctave: 4,
    filterRange: [200, 3000],
    hasDelay: true,
    character: 'Experimental, atonal elements',
  },
}

// ---------------------------------------------------------------------------
// Song Generation
// ---------------------------------------------------------------------------

export interface GenerateOptions {
  /** Override BPM (ignores genre range). */
  bpm?: number
  /** Override key. */
  key?: string
  /** Override scale. */
  scale?: string
  /** Custom title. */
  title?: string
}

/**
 * Generate a complete Song object from a genre preset and deterministic seed.
 */
export function generateSong(genre: string, seed: number, options?: GenerateOptions): Song {
  const preset = GENRE_PRESETS[genre]
  if (!preset) throw new Error(`Unknown genre: ${genre}`)

  const rng = mulberry32(seed)

  // Pick key, scale, BPM
  const key = options?.key ?? pick(preset.keyOptions, rng)
  const scaleName = options?.scale ?? pick(preset.scaleOptions, rng)
  const bpm = options?.bpm ?? randInt(preset.bpmRange[0], preset.bpmRange[1], rng)
  const title = options?.title ?? `${preset.name} #${seed}`

  // Validate scale exists (fall back to minor if exotic scale not available)
  const usedScale = SCALES[scaleName] ? scaleName : 'minor'

  // Generate chord progressions for each section type
  const progName = pick(preset.progressions, rng)
  const chords = resolveChordSpecs(key, getProgressionChords(progName), preset.chordOctave)

  // Get scale frequencies for melody generation
  const scaleFreqs = getScaleMultiOctave(key, usedScale, preset.leadOctave, 2)
  const bassScaleFreqs = getScaleMultiOctave(key, usedScale, preset.bassOctave, 2)

  // Get per-genre configs
  const adsrSet = GENRE_ADSR[genre] ?? DEFAULT_ADSR
  const filters = GENRE_FILTERS[genre] ?? { bass: 600, pad: 1500, arp: 3000, lead: 2000 }

  // Generate patterns for each channel (section-aware)
  const bassPatterns = generateBassPatterns(preset, chords, bassScaleFreqs, rng, genre)
  const padPatterns = generatePadPatterns(preset, chords, rng)
  const leadPatterns = generateLeadPatterns(preset, scaleFreqs, chords, rng, genre)
  const arpPatterns = generateArpPatterns(preset, chords, rng, genre)
  const drumPatterns = generateDrumPatterns(preset, rng)

  // Build channels with per-genre filter and ADSR configs
  const channels: Record<string, Channel> = {
    bass: {
      name: 'bass',
      type: preset.channelTypes.bass,
      patterns: bassPatterns,
      gain: 0.45,
      effects: { filter: filters.bass },
      adsr: adsrSet.bass,
    },
    lead: {
      name: 'lead',
      type: preset.channelTypes.lead,
      patterns: leadPatterns,
      gain: 0.3,
      effects: {
        filter: filters.lead,
        ...(filters.delay ? { delay: filters.delay, delayFeedback: filters.delayFeedback ?? 0.25 } : {}),
      },
      adsr: adsrSet.lead,
    },
    pad: {
      name: 'pad',
      type: preset.channelTypes.pad,
      patterns: padPatterns,
      gain: 0.25,
      effects: { filter: filters.pad },
      adsr: adsrSet.pad,
    },
    arp: {
      name: 'arp',
      type: preset.channelTypes.arp,
      patterns: arpPatterns,
      gain: 0.2,
      effects: {
        filter: filters.arp,
        ...(filters.delay ? { delay: Math.max(0.08, filters.delay - 0.05), delayFeedback: (filters.delayFeedback ?? 0.25) + 0.05 } : {}),
      },
      adsr: adsrSet.arp,
    },
    drums: {
      name: 'drums',
      type: 'noise',
      patterns: drumPatterns,
      gain: 0.65,
    },
  }

  // Build sections from the preset's section flow
  const sections = buildSections(preset.sectionFlow, channels)

  // Per-genre intensity map
  const category = GENRE_INTENSITY_CATEGORY[genre] ?? 'strategic'
  const intensityMap = INTENSITY_MAPS[category]

  return {
    title,
    bpm,
    stepsPerBeat: 4,
    key,
    scale: usedScale,
    sections,
    channels,
    startSection: preset.sectionFlow[0],
    intensityMap,
    genre,
    seed,
  }
}

// ---------------------------------------------------------------------------
// Pattern Generators
// ---------------------------------------------------------------------------

function getProgressionChords(progName: string): string[] {
  const PROG_CHORDS: Record<string, string[]> = {
    pop:        ['I:major', 'V:major', 'vi:minor', 'IV:major'],
    axis:       ['I:major', 'V:major', 'vi:minor', 'IV:major'],
    sad:        ['vi:minor', 'IV:major', 'I:major', 'V:major'],
    jazz251:    ['ii:min7', 'V:dom7', 'I:maj7'],
    jazz1625:   ['I:maj7', 'vi:min7', 'ii:min7', 'V:dom7'],
    andalusian: ['i:minor', 'bVII:major', 'bVI:major', 'V:major'],
    blues12bar: ['I:dom7', 'I:dom7', 'I:dom7', 'I:dom7', 'IV:dom7', 'IV:dom7', 'I:dom7', 'I:dom7', 'V:dom7', 'IV:dom7', 'I:dom7', 'V:dom7'],
    modal:      ['I:major', 'bVII:major', 'I:major', 'bVII:major'],
    neosoul:    ['IV:maj7', 'iii:min7', 'vi:min7', 'V:dom7'],
    rock:       ['I:major', 'IV:major', 'V:major', 'I:major'],
    power:      ['I:major', 'bVII:major', 'bVI:major', 'I:major'],
    dorian:     ['i:minor', 'IV:major', 'i:minor', 'IV:major'],
    epic:       ['I:major', 'V:major', 'vi:minor', 'III:major'],
    dark:       ['i:minor', 'bVI:major', 'bIII:major', 'bVII:major'],
    dreamy:     ['I:maj7', 'III:major', 'IV:maj7', 'iv:minor'],
    tension:    ['i:minor', 'bII:major', 'V:major', 'i:minor'],
    coltrane:   ['I:maj7', 'bIII:maj7', 'V:maj7', 'I:maj7'],
    reggae:     ['I:major', 'IV:major', 'I:major', 'V:major'],
    waltz:      ['I:major', 'IV:major', 'V:dom7', 'I:major'],
    minorBlues: ['i:min7', 'iv:min7', 'i:min7', 'bVI:dom7', 'V:dom7', 'i:min7'],
  }
  return PROG_CHORDS[progName] || PROG_CHORDS['pop']
}

// ---------------------------------------------------------------------------
// Bass Pattern Generator — Genre-Aware
// ---------------------------------------------------------------------------

function generateBassPatterns(
  preset: GenrePreset, chords: number[][], bassScale: number[],
  rng: () => number, genre: string,
): Record<string, Pattern> {
  const patterns: Record<string, Pattern> = {}
  const barsPerSection = 4

  for (const sectionName of preset.sectionFlow) {
    const notes: Note[] = []
    const section = getSectionCharacter(sectionName)

    for (let bar = 0; bar < barsPerSection; bar++) {
      const chordIdx = bar % chords.length
      const chord = chords[chordIdx]
      const root = chord[0]
      const fifth = chord.length > 2 ? chord[2] : chord[0]
      const bassRoot = findNearestFreq(bassScale, root / (2 ** Math.floor(Math.log2(root / bassScale[0]))))
      const bassFifth = findNearestFreq(bassScale, fifth / (2 ** Math.floor(Math.log2(fifth / bassScale[0]))))

      if (section.density === 'sparse') {
        // Intro/outro: whole notes on root
        notes.push({ pitch: bassRoot, duration: 12, velocity: 0.5 * section.velocityMul })
        notes.push({ pitch: 0, duration: 4 })
      } else if (genre === 'jazz' || genre === 'lofi' || genre === 'bossanova') {
        // Walking bass — stepwise movement
        const chordRoots = chords.map(c =>
          findNearestFreq(bassScale, c[0] / (2 ** Math.floor(Math.log2(c[0] / bassScale[0]))))
        )
        const walkFreqs = walkingBassLine([chordRoots[chordIdx]], bassScale, rng, 8)
        for (let i = 0; i < 8; i++) {
          const vel = (i % 2 === 0 ? 0.65 : 0.5) * section.velocityMul
          notes.push({ pitch: walkFreqs[i] ?? bassRoot, duration: 2, velocity: vel })
        }
      } else if (genre === 'funk' || genre === 'disco') {
        // Syncopated 16ths with ghost notes and octave slaps
        const octave = bassRoot * 2
        for (let step = 0; step < 16; step++) {
          if (step === 0 || step === 6 || step === 10) {
            notes.push({ pitch: bassRoot, duration: 1, velocity: 0.7 * section.velocityMul })
          } else if (step === 3 || step === 13) {
            notes.push({ pitch: octave, duration: 1, velocity: 0.6 * section.velocityMul })
          } else if (step === 8) {
            notes.push({ pitch: bassFifth, duration: 1, velocity: 0.65 * section.velocityMul })
          } else if (rng() < 0.3) {
            notes.push({ pitch: bassRoot, duration: 1, velocity: 0.25 * section.velocityMul })
          } else {
            notes.push({ pitch: 0, duration: 1 })
          }
        }
      } else if (genre === 'blues') {
        // Root-5th-octave shuffle pattern
        const octave = bassRoot * 2
        notes.push({ pitch: bassRoot, duration: 3, velocity: 0.7 * section.velocityMul })
        notes.push({ pitch: bassFifth, duration: 1, velocity: 0.55 * section.velocityMul })
        notes.push({ pitch: bassRoot, duration: 2, velocity: 0.6 * section.velocityMul })
        notes.push({ pitch: octave, duration: 2, velocity: 0.55 * section.velocityMul })
        notes.push({ pitch: bassRoot, duration: 3, velocity: 0.65 * section.velocityMul })
        notes.push({ pitch: bassFifth, duration: 1, velocity: 0.55 * section.velocityMul })
        notes.push({ pitch: octave, duration: 2, velocity: 0.5 * section.velocityMul })
        notes.push({ pitch: bassRoot, duration: 2, velocity: 0.6 * section.velocityMul })
      } else if (genre === 'reggae') {
        // One-drop bass: hit on beat 3, rest on beat 1
        notes.push({ pitch: 0, duration: 8 })
        notes.push({ pitch: bassRoot, duration: 4, velocity: 0.75 * section.velocityMul })
        notes.push({ pitch: bassFifth, duration: 2, velocity: 0.55 * section.velocityMul })
        notes.push({ pitch: 0, duration: 2 })
      } else if (genre === 'rock' || genre === 'metal') {
        // Power root + 5th, 8th-note chugging in chorus
        if (section.density === 'full') {
          for (let i = 0; i < 8; i++) {
            const p = i % 4 === 0 ? bassRoot : (i % 4 === 2 ? bassFifth : bassRoot)
            notes.push({ pitch: p, duration: 2, velocity: (0.65 + rng() * 0.15) * section.velocityMul })
          }
        } else {
          notes.push({ pitch: bassRoot, duration: 4, velocity: 0.75 * section.velocityMul })
          notes.push({ pitch: 0, duration: 4 })
          notes.push({ pitch: bassFifth, duration: 4, velocity: 0.65 * section.velocityMul })
          notes.push({ pitch: 0, duration: 4 })
        }
      } else if (genre === 'ambient' || genre === 'japanese' || genre === 'cinematic') {
        // Sparse whole/half notes on root
        notes.push({ pitch: bassRoot, duration: 8, velocity: 0.4 * section.velocityMul })
        if (rng() < 0.4) {
          notes.push({ pitch: bassFifth, duration: 8, velocity: 0.35 * section.velocityMul })
        } else {
          notes.push({ pitch: 0, duration: 8 })
        }
      } else if (genre === 'chiptune') {
        // Quick arpeggiated bass: root-5th-octave-5th
        const octave = bassRoot * 2
        for (let i = 0; i < 4; i++) {
          const pitches = [bassRoot, bassFifth, octave, bassFifth]
          notes.push({ pitch: pitches[i], duration: 2, velocity: 0.6 * section.velocityMul })
          notes.push({ pitch: 0, duration: 2 })
        }
      } else if (genre === 'latin' || genre === 'arabic') {
        // Tresillo-style anticipated bass
        notes.push({ pitch: bassRoot, duration: 3, velocity: 0.7 * section.velocityMul })
        notes.push({ pitch: bassRoot, duration: 3, velocity: 0.55 * section.velocityMul })
        notes.push({ pitch: bassFifth, duration: 2, velocity: 0.6 * section.velocityMul })
        notes.push({ pitch: bassRoot, duration: 3, velocity: 0.65 * section.velocityMul })
        notes.push({ pitch: bassFifth, duration: 3, velocity: 0.55 * section.velocityMul })
        notes.push({ pitch: 0, duration: 2 })
      } else {
        // Default: rhythm template with root + 5th variation
        const rhythm = RHYTHM_TEMPLATES[preset.rhythmStyle] || RHYTHM_TEMPLATES['straight8ths']
        let step = 0
        let noteIdx = 0
        for (const dur of rhythm) {
          if (step >= 16) break
          const actualDur = Math.min(dur, 16 - step)
          const p = noteIdx % 3 === 0 ? bassRoot : (noteIdx % 3 === 1 ? bassFifth : bassRoot)
          notes.push({ pitch: p, duration: actualDur, velocity: (0.55 + rng() * 0.15) * section.velocityMul })
          step += actualDur
          noteIdx++
        }
        if (step < 16) notes.push({ pitch: 0, duration: 16 - step })
      }
    }
    const totalSteps = barsPerSection * 16
    patterns[sectionName] = { notes, length: totalSteps }
  }

  return patterns
}

// ---------------------------------------------------------------------------
// Pad Pattern Generator — Section-Contrasted Voicings
// ---------------------------------------------------------------------------

function generatePadPatterns(
  preset: GenrePreset, chords: number[][], rng: () => number,
): Record<string, Pattern> {
  const patterns: Record<string, Pattern> = {}
  const barsPerSection = 4

  for (const sectionName of preset.sectionFlow) {
    const notes: Note[] = []
    const section = getSectionCharacter(sectionName)

    for (let bar = 0; bar < barsPerSection; bar++) {
      const chord = chords[bar % chords.length]

      if (section.density === 'sparse') {
        // One long chord tone per bar (root only)
        notes.push({ pitch: chord[0], duration: 14, velocity: 0.25 * section.velocityMul })
        notes.push({ pitch: 0, duration: 2 })
      } else if (section.density === 'full') {
        // Full voiced chord: cycle tones with different voicing per bar
        const voicing = bar % 2 === 0
          ? chord.slice(0, Math.min(chord.length, 4))       // root position
          : [...chord.slice(1), chord[0] * 2].slice(0, Math.min(chord.length, 4))  // 1st inversion (approx)
        const durPerTone = Math.max(2, Math.floor(16 / voicing.length))
        let step = 0
        for (let i = 0; i < voicing.length && step < 16; i++) {
          const d = i === voicing.length - 1 ? 16 - step : durPerTone
          notes.push({ pitch: voicing[i], duration: d, velocity: (0.35 + rng() * 0.1) * section.velocityMul })
          step += d
        }
      } else {
        // Medium: 3 chord tones with slight velocity shaping
        const tones = chord.slice(0, Math.min(3, chord.length))
        const durPerTone = Math.floor(16 / tones.length)
        let step = 0
        for (let i = 0; i < tones.length; i++) {
          const d = i === tones.length - 1 ? 16 - step : durPerTone
          // Shape: slight accent on first tone
          const vel = (i === 0 ? 0.35 : 0.28) * section.velocityMul + rng() * 0.05
          notes.push({ pitch: tones[i], duration: d, velocity: vel })
          step += d
        }
      }
    }
    patterns[sectionName] = { notes, length: barsPerSection * 16 }
  }

  return patterns
}

// ---------------------------------------------------------------------------
// Lead Melody Generator — Chord-Aware with Motif Development
// ---------------------------------------------------------------------------

function generateLeadPatterns(
  preset: GenrePreset, scaleFreqs: number[], chords: number[][],
  rng: () => number, genre: string,
): Record<string, Pattern> {
  const patterns: Record<string, Pattern> = {}
  const barsPerSection = 4

  // Generate a 4-note motif in the first pass — reused and developed across sections
  const motif = generateMotif(scaleFreqs, chords[0], rng, genre)
  let sectionIdx = 0

  for (const sectionName of preset.sectionFlow) {
    const section = getSectionCharacter(sectionName)
    const sectionRestProb = getRestProbability(genre, sectionName)

    if (section.density === 'sparse' && !section.activeChannels.includes('lead')) {
      // No lead in sparse sections
      patterns[sectionName] = { notes: [{ pitch: 0, duration: barsPerSection * 16 }], length: barsPerSection * 16 }
      sectionIdx++
      continue
    }

    const notes: Note[] = []
    const rhythm = RHYTHM_TEMPLATES[preset.rhythmStyle] || RHYTHM_TEMPLATES['straight8ths']

    for (let bar = 0; bar < barsPerSection; bar++) {
      const chordIdx = bar % chords.length
      const chord = chords[chordIdx]
      // Expand chord tones across lead octave range
      const chordTones = expandChordToRange(chord, scaleFreqs)

      // Develop motif differently per section
      let barMotif: Note[]
      if (bar === 0 && sectionIdx === 0) {
        barMotif = motif // Original motif in first section
      } else if (sectionName.includes('chorus') || sectionName.includes('drop') || sectionName.includes('climax')) {
        // Chorus: transpose motif up, use inversion for variety
        barMotif = bar % 2 === 0
          ? motifDevelop(motif, 'transpose', 5 + (sectionIdx % 3))
          : motifDevelop(motif, 'invert')
      } else if (sectionName.includes('bridge')) {
        barMotif = motifDevelop(motif, 'retrograde')
      } else {
        // Verse: develop with slight transposition
        barMotif = bar % 2 === 0 ? motif : motifDevelop(motif, 'transpose', 2)
      }

      // Apply call-and-response on bars 3-4
      if (bar >= 2) {
        barMotif = callAndResponse(barMotif, scaleFreqs)
      }

      // Fill the bar using motif + passing tones, anchored to chord tones
      let step = 0
      let motifIdx = 0
      for (const dur of rhythm) {
        if (step >= 16) break
        const actualDur = Math.min(dur, 16 - step)

        // Rest insertion
        if (rng() < sectionRestProb) {
          notes.push({ pitch: 0, duration: actualDur })
          step += actualDur
          motifIdx++
          continue
        }

        let pitch: number
        const isStrongBeat = step === 0 || step === 4 || step === 8 || step === 12

        if (isStrongBeat && chordTones.length > 0) {
          // Strong beats: anchor to chord tones
          if (motifIdx < barMotif.length && barMotif[motifIdx].pitch > 0) {
            // Snap motif note to nearest chord tone
            pitch = nearestChordTone(barMotif[motifIdx].pitch, chordTones)
          } else {
            pitch = pick(chordTones, rng)
          }
        } else {
          // Weak beats: use motif or scale passing tones
          if (motifIdx < barMotif.length && barMotif[motifIdx].pitch > 0) {
            pitch = barMotif[motifIdx].pitch
          } else {
            // Passing tone: pick from scale near the last note
            const lastPitch = notes.length > 0 && notes[notes.length - 1].pitch > 0
              ? notes[notes.length - 1].pitch
              : scaleFreqs[Math.floor(scaleFreqs.length / 2)]
            const nearIdx = findNearestFreqIndex(scaleFreqs, lastPitch)
            const stepDir = rng() < 0.5 ? 1 : -1
            const newIdx = Math.max(0, Math.min(scaleFreqs.length - 1, nearIdx + stepDir))
            pitch = scaleFreqs[newIdx]
          }
        }

        const vel = isStrongBeat
          ? (0.65 + rng() * 0.2) * section.velocityMul
          : (0.5 + rng() * 0.2) * section.velocityMul

        notes.push({ pitch, duration: actualDur, velocity: vel })
        step += actualDur
        motifIdx++
      }
      if (step < 16) notes.push({ pitch: 0, duration: 16 - step })
    }

    patterns[sectionName] = { notes, length: barsPerSection * 16 }
    sectionIdx++
  }

  return patterns
}

/** Generate a 4-note motif anchored to chord tones with genre character. */
function generateMotif(
  scaleFreqs: number[], chord: number[], rng: () => number, genre: string,
): Note[] {
  const chordTones = expandChordToRange(chord, scaleFreqs)
  const notes: Note[] = []

  if (genre === 'ambient' || genre === 'japanese' || genre === 'cinematic') {
    // Long, sparse notes — 2 held notes with rests
    notes.push({ pitch: pick(chordTones, rng), duration: 4, velocity: 0.5 })
    notes.push({ pitch: 0, duration: 2 })
    notes.push({ pitch: pick(chordTones, rng), duration: 4, velocity: 0.45 })
    notes.push({ pitch: 0, duration: 2 })
  } else if (genre === 'chiptune' || genre === 'edm') {
    // Fast repeated motif with octave jump
    const base = pick(chordTones, rng)
    notes.push({ pitch: base, duration: 2, velocity: 0.7 })
    notes.push({ pitch: base * 2, duration: 1, velocity: 0.6 }) // octave up
    notes.push({ pitch: pick(chordTones, rng), duration: 2, velocity: 0.65 })
    notes.push({ pitch: base, duration: 1, velocity: 0.55 })
  } else if (genre === 'jazz' || genre === 'blues') {
    // Chromatic approach + wider leaps
    const root = pick(chordTones, rng)
    const rootIdx = findNearestFreqIndex(scaleFreqs, root)
    notes.push({ pitch: root, duration: 2, velocity: 0.6 })
    const leap = Math.min(scaleFreqs.length - 1, rootIdx + randInt(2, 4, rng))
    notes.push({ pitch: scaleFreqs[leap], duration: 2, velocity: 0.55 })
    // Chromatic approach to next chord tone
    const target = pick(chordTones, rng)
    const approachIdx = findNearestFreqIndex(scaleFreqs, target)
    const chromatic = approachIdx > 0 ? scaleFreqs[approachIdx - 1] : scaleFreqs[0]
    notes.push({ pitch: chromatic, duration: 1, velocity: 0.5 })
    notes.push({ pitch: target, duration: 3, velocity: 0.65 })
  } else if (genre === 'rock' || genre === 'metal') {
    // Power riff on root + 5th
    const root = chordTones[0] || scaleFreqs[0]
    const fifth = chordTones.length > 1 ? chordTones[1] : root
    notes.push({ pitch: root, duration: 2, velocity: 0.8 })
    notes.push({ pitch: root, duration: 1, velocity: 0.75 })
    notes.push({ pitch: fifth, duration: 2, velocity: 0.75 })
    notes.push({ pitch: root, duration: 1, velocity: 0.7 })
  } else {
    // Default: chord-tone based melodic motif
    for (let i = 0; i < 4; i++) {
      const p = i % 2 === 0 ? pick(chordTones, rng) : scaleFreqs[randInt(0, scaleFreqs.length - 1, rng)]
      notes.push({ pitch: p, duration: 2, velocity: 0.6 + rng() * 0.15 })
    }
  }

  return notes
}

/** Expand chord frequencies to cover the scale range (multiple octaves). */
function expandChordToRange(chord: number[], scaleFreqs: number[]): number[] {
  if (scaleFreqs.length === 0 || chord.length === 0) return []
  const minF = scaleFreqs[0]
  const maxF = scaleFreqs[scaleFreqs.length - 1]
  const expanded: number[] = []
  for (const f of chord) {
    let freq = f
    // Bring into range by octave shifting
    while (freq < minF && freq > 0) freq *= 2
    while (freq > maxF && freq > minF) freq /= 2
    if (freq >= minF && freq <= maxF) expanded.push(freq)
    // Also add octave above if in range
    if (freq * 2 <= maxF) expanded.push(freq * 2)
  }
  return expanded.length > 0 ? expanded : [scaleFreqs[Math.floor(scaleFreqs.length / 2)]]
}

// ---------------------------------------------------------------------------
// Arpeggio Pattern Generator — Genre-Aware
// ---------------------------------------------------------------------------

function generateArpPatterns(
  preset: GenrePreset, chords: number[][], rng: () => number, genre: string,
): Record<string, Pattern> {
  const patterns: Record<string, Pattern> = {}
  const barsPerSection = 4

  for (const sectionName of preset.sectionFlow) {
    const notes: Note[] = []
    const section = getSectionCharacter(sectionName)

    for (let bar = 0; bar < barsPerSection; bar++) {
      const chord = chords[bar % chords.length]

      if (section.density === 'sparse') {
        // Sparse arps: slow, few notes
        const arpNotes = seededArpeggio(chord, preset.arpStyle, 4, rng)
        let step = 0
        for (const n of arpNotes) {
          if (step >= 16) break
          notes.push({ ...n, velocity: 0.3 * section.velocityMul })
          step += n.duration
        }
        if (step < 16) notes.push({ pitch: 0, duration: 16 - step })
      } else if (genre === 'chiptune') {
        // Fast 16th-note arps cycling through extended chord
        const extended = [...chord, chord[0] * 2]
        let step = 0
        let i = 0
        while (step < 16) {
          notes.push({
            pitch: extended[i % extended.length],
            duration: 1,
            velocity: (i % 4 === 0 ? 0.55 : 0.4) * section.velocityMul,
          })
          step++
          i++
        }
      } else if (genre === 'edm' || genre === 'electronic') {
        // Gated arp: note-rest-note-rest at 16ths
        const arpNotes = seededArpeggio(chord, preset.arpStyle, 1, rng)
        let step = 0
        let i = 0
        while (step < 16) {
          if (step % 2 === 0) {
            notes.push({
              pitch: arpNotes[i % arpNotes.length].pitch,
              duration: 1,
              velocity: (0.4 + rng() * 0.15) * section.velocityMul,
            })
          } else {
            notes.push({ pitch: 0, duration: 1 })
          }
          step++
          if (step % 2 === 0) i++
        }
      } else if (genre === 'synthwave' || genre === 'disco') {
        // Repeated chord-tone arp with updown pattern
        const arpNotes = seededArpeggio(chord, 'updown', 1, rng)
        let step = 0
        let i = 0
        while (step < 16) {
          const n = arpNotes[i % arpNotes.length]
          notes.push({
            pitch: n.pitch,
            duration: 1,
            velocity: (step % 4 === 0 ? 0.5 : 0.35) * section.velocityMul,
          })
          step++
          i++
        }
      } else if (genre === 'ambient' || genre === 'japanese' || genre === 'cinematic') {
        // Slow, gentle arps with long notes
        const arpNotes = seededArpeggio(chord, 'updown', 4, rng)
        let step = 0
        for (const n of arpNotes) {
          if (step >= 16) break
          const d = Math.min(n.duration, 16 - step)
          notes.push({ pitch: n.pitch, duration: d, velocity: 0.3 * section.velocityMul })
          step += d
        }
        if (step < 16) notes.push({ pitch: 0, duration: 16 - step })
      } else {
        // Default: standard arp with accent on beat 1
        const arpNotes = seededArpeggio(chord, preset.arpStyle, 1, rng)
        let step = 0
        let i = 0
        while (step < 16) {
          const n = arpNotes[i % arpNotes.length]
          notes.push({
            pitch: n.pitch,
            duration: 1,
            velocity: (step % 4 === 0 ? 0.5 : 0.35 + rng() * 0.1) * section.velocityMul,
          })
          step++
          i++
        }
      }
    }

    patterns[sectionName] = { notes, length: barsPerSection * 16 }
  }

  return patterns
}

// ---------------------------------------------------------------------------
// Drum Pattern Generator — Section-Aware with Fills
// ---------------------------------------------------------------------------

function generateDrumPatterns(
  preset: GenrePreset, rng: () => number,
): Record<string, Pattern> {
  const patterns: Record<string, Pattern> = {}
  const barsPerSection = 4

  for (const sectionName of preset.sectionFlow) {
    const notes: Note[] = []
    const section = getSectionCharacter(sectionName)

    for (let bar = 0; bar < barsPerSection; bar++) {
      const isFillBar = section.drumFill && bar === barsPerSection - 1
      const barNotes = generateDrumBar(preset.drumStyle, sectionName, rng, isFillBar, section.density)
      notes.push(...barNotes)
    }

    patterns[sectionName] = { notes, length: barsPerSection * 16 }
  }

  return patterns
}

/** Generate one bar (16 steps) of drums with section awareness and fills. */
function generateDrumBar(
  style: string, sectionName: string, rng: () => number,
  isFillBar: boolean, density: 'sparse' | 'medium' | 'full',
): Note[] {
  // Pitch codes: 1=kick, 2=snare, 3=hihat, 4=clap
  const notes: Note[] = []

  if (style === 'none') {
    notes.push({ pitch: 0, duration: 16 })
    return notes
  }

  if (sectionName === 'intro') {
    // Sparse intro: just quiet hi-hats building
    for (let i = 0; i < 4; i++) {
      notes.push({ pitch: 3, duration: 1, velocity: 0.2 + i * 0.05 })
      notes.push({ pitch: 0, duration: 3 })
    }
    return notes
  }

  if (sectionName === 'outro') {
    // Fading out: kick on 1, hat trail
    notes.push({ pitch: 1, duration: 1, velocity: 0.6 })
    notes.push({ pitch: 0, duration: 3 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.25 })
    notes.push({ pitch: 0, duration: 3 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.2 })
    notes.push({ pitch: 0, duration: 3 })
    notes.push({ pitch: 3, duration: 1, velocity: 0.15 })
    notes.push({ pitch: 0, duration: 3 })
    return notes
  }

  if (sectionName.includes('break') || sectionName.includes('breakdown')) {
    // Minimal: sparse kick + atmospheric hi-hat
    notes.push({ pitch: 1, duration: 1, velocity: 0.5 })
    notes.push({ pitch: 0, duration: 7 })
    if (rng() < 0.4) {
      notes.push({ pitch: 3, duration: 1, velocity: 0.2 })
      notes.push({ pitch: 0, duration: 7 })
    } else {
      notes.push({ pitch: 0, duration: 8 })
    }
    return notes
  }

  // Fill bar: add extra hits for energy
  if (isFillBar) {
    return generateDrumFill(style, rng)
  }

  // Standard patterns by style
  switch (style) {
    case 'fourOnFloor':
      // Section-aware: chorus gets open hi-hat on off-beats
      if (density === 'full') {
        // Full: kick+hat on every beat, open hat on offbeats, snare on 2 and 4
        notes.push({ pitch: 1, duration: 1, velocity: 0.9 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.35 + rng() * 0.1 }) // ghost hat
        notes.push({ pitch: 3, duration: 1, velocity: 0.5 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.3 + rng() * 0.1 })
        notes.push({ pitch: 2, duration: 1, velocity: 0.85 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.35 + rng() * 0.1 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.5 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.3 + rng() * 0.1 })
        notes.push({ pitch: 1, duration: 1, velocity: 0.85 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.35 + rng() * 0.1 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.5 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.3 + rng() * 0.1 })
        notes.push({ pitch: 2, duration: 1, velocity: 0.85 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.35 + rng() * 0.1 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.5 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
      } else {
        // Medium: basic four-on-floor
        notes.push({ pitch: 1, duration: 1, velocity: 0.85 })
        notes.push({ pitch: 0, duration: 1 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
        notes.push({ pitch: 0, duration: 1 })
        notes.push({ pitch: 2, duration: 1, velocity: 0.8 })
        notes.push({ pitch: 0, duration: 1 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
        notes.push({ pitch: 0, duration: 1 })
        notes.push({ pitch: 1, duration: 1, velocity: 0.8 })
        notes.push({ pitch: 0, duration: 1 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
        notes.push({ pitch: 0, duration: 1 })
        notes.push({ pitch: 2, duration: 1, velocity: 0.8 })
        notes.push({ pitch: 0, duration: 1 })
        notes.push({ pitch: 3, duration: 1, velocity: 0.5 })
        notes.push({ pitch: 0, duration: 1 })
      }
      break

    case 'halftime':
      // Kick on 1, snare on 3, sparse hats
      notes.push({ pitch: 1, duration: 1, velocity: 0.9 })
      notes.push({ pitch: 0, duration: 3 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.25 + rng() * 0.1 })
      notes.push({ pitch: 0, duration: 3 })
      notes.push({ pitch: 2, duration: 1, velocity: 0.8 })
      notes.push({ pitch: 0, duration: 3 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.25 + rng() * 0.1 })
      notes.push({ pitch: 0, duration: 3 })
      break

    case 'shuffle':
      // Swing feel with ghost note hats
      notes.push({ pitch: 1, duration: 1, velocity: 0.85 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.2 + rng() * 0.1 }) // ghost
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
      notes.push({ pitch: 2, duration: 1, velocity: 0.8 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.2 + rng() * 0.1 }) // ghost
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
      notes.push({ pitch: 1, duration: 1, velocity: 0.8 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.2 + rng() * 0.1 }) // ghost
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
      notes.push({ pitch: 2, duration: 1, velocity: 0.8 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.2 + rng() * 0.1 }) // ghost
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.5 })
      break

    case 'sparse':
      // Minimal: just kick and occasional hat
      notes.push({ pitch: 1, duration: 1, velocity: 0.65 })
      notes.push({ pitch: 0, duration: 3 })
      if (rng() < 0.5) {
        notes.push({ pitch: 3, duration: 1, velocity: 0.2 })
        notes.push({ pitch: 0, duration: 3 })
      } else {
        notes.push({ pitch: 0, duration: 4 })
      }
      notes.push({ pitch: 0, duration: 4 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.2 + rng() * 0.1 })
      notes.push({ pitch: 0, duration: 3 })
      break

    case 'blast':
      // Fast kick-snare alternation with variable velocity
      for (let i = 0; i < 8; i++) {
        const isKick = i % 2 === 0
        notes.push({
          pitch: isKick ? 1 : 2,
          duration: 1,
          velocity: (isKick ? 0.85 : 0.75) + rng() * 0.1,
        })
        notes.push({ pitch: 3, duration: 1, velocity: 0.35 + rng() * 0.1 })
      }
      break

    case 'offbeat':
      // Reggae one-drop: kick+snare on 3, rim/hat off-beat
      notes.push({ pitch: 0, duration: 2 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 0, duration: 2 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 1, duration: 1, velocity: 0.8 })
      notes.push({ pitch: 2, duration: 1, velocity: 0.6 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 0, duration: 2 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
      notes.push({ pitch: 0, duration: 1 })
      break

    case 'dnb':
      // Drum and bass: fast broken beat with variation
      notes.push({ pitch: 1, duration: 1, velocity: 0.9 })
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
      notes.push({ pitch: 2, duration: 1, velocity: 0.7 })
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.35 + rng() * 0.1 })
      notes.push({ pitch: 1, duration: 1, velocity: 0.7 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 2, duration: 1, velocity: 0.8 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.35 + rng() * 0.1 })
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 1, duration: 1, velocity: 0.6 })
      notes.push({ pitch: 0, duration: 1 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.45 })
      notes.push({ pitch: 2, duration: 1, velocity: 0.7 })
      break

    default:
      // Fallback: basic kick-snare with hi-hat
      notes.push({ pitch: 1, duration: 1, velocity: 0.8 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.3 })
      notes.push({ pitch: 0, duration: 2 })
      notes.push({ pitch: 2, duration: 1, velocity: 0.8 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.3 })
      notes.push({ pitch: 0, duration: 2 })
      notes.push({ pitch: 1, duration: 1, velocity: 0.8 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.3 })
      notes.push({ pitch: 0, duration: 2 })
      notes.push({ pitch: 2, duration: 1, velocity: 0.8 })
      notes.push({ pitch: 3, duration: 1, velocity: 0.3 })
      notes.push({ pitch: 0, duration: 2 })
  }

  return notes
}

/** Generate a drum fill (16 steps) — snare rolls, tom runs, crash. */
function generateDrumFill(style: string, rng: () => number): Note[] {
  const notes: Note[] = []

  // First half: normal pattern kick
  notes.push({ pitch: 1, duration: 1, velocity: 0.85 })
  notes.push({ pitch: 0, duration: 1 })
  notes.push({ pitch: 3, duration: 1, velocity: 0.4 })
  notes.push({ pitch: 0, duration: 1 })

  if (style === 'blast') {
    // Metal fill: rapid snare roll
    for (let i = 0; i < 12; i++) {
      notes.push({ pitch: 2, duration: 1, velocity: 0.6 + (i / 12) * 0.35 })
    }
  } else if (style === 'shuffle' || style === 'halftime') {
    // Jazz/blues fill: swung snare build
    notes.push({ pitch: 2, duration: 2, velocity: 0.5 })
    notes.push({ pitch: 0, duration: 1 })
    notes.push({ pitch: 2, duration: 1, velocity: 0.55 })
    notes.push({ pitch: 2, duration: 2, velocity: 0.6 })
    notes.push({ pitch: 2, duration: 1, velocity: 0.65 })
    notes.push({ pitch: 2, duration: 1, velocity: 0.7 })
    notes.push({ pitch: 4, duration: 1, velocity: 0.8 }) // crash/clap on end
    notes.push({ pitch: 1, duration: 1, velocity: 0.9 })
    notes.push({ pitch: 0, duration: 2 })
  } else {
    // Standard fill: snare roll building to crash
    notes.push({ pitch: 2, duration: 1, velocity: 0.5 })
    notes.push({ pitch: 0, duration: 1 })
    notes.push({ pitch: 2, duration: 1, velocity: 0.55 })
    notes.push({ pitch: 2, duration: 1, velocity: 0.6 })
    notes.push({ pitch: 2, duration: 1, velocity: 0.65 + rng() * 0.1 })
    notes.push({ pitch: 2, duration: 1, velocity: 0.7 })
    notes.push({ pitch: 2, duration: 1, velocity: 0.75 })
    notes.push({ pitch: 2, duration: 1, velocity: 0.8 })
    notes.push({ pitch: 4, duration: 1, velocity: 0.9 }) // clap hit
    notes.push({ pitch: 1, duration: 1, velocity: 0.85 })
    notes.push({ pitch: 0, duration: 2 })
  }

  return notes
}

// ---------------------------------------------------------------------------
// Section & Utility
// ---------------------------------------------------------------------------

/** Build section objects from a section flow array. */
function buildSections(
  sectionFlow: string[],
  channels: Record<string, Channel>,
): Record<string, Section> {
  const sections: Record<string, Section> = {}
  const channelNames = Object.keys(channels)

  for (let i = 0; i < sectionFlow.length; i++) {
    const name = sectionFlow[i]
    if (sections[name]) continue // already defined (duplicate names in flow)

    const next = i + 1 < sectionFlow.length ? sectionFlow[i + 1] : sectionFlow[1] // loop back to verse

    // Map channels that have a pattern for this section
    const activeChannels: Record<string, string> = {}
    for (const chName of channelNames) {
      const ch = channels[chName]
      if (ch.patterns[name]) {
        activeChannels[chName] = name
      }
    }

    sections[name] = {
      name,
      bars: 4,
      channels: activeChannels,
      next: next !== name ? next : null, // null = loop self
    }
  }

  return sections
}

/** Find the frequency in an array nearest to the target. */
function findNearestFreq(freqs: number[], target: number): number {
  let best = freqs[0]
  let bestDist = Math.abs(freqs[0] - target)
  for (let i = 1; i < freqs.length; i++) {
    const dist = Math.abs(freqs[i] - target)
    if (dist < bestDist) {
      bestDist = dist
      best = freqs[i]
    }
  }
  return best
}

/** Find the index of the nearest frequency in an array. */
function findNearestFreqIndex(freqs: number[], target: number): number {
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
