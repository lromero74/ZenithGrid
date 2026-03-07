/**
 * Shared types for the reusable synthwave music engine.
 *
 * Any game can define a Song and plug it into the engine via useGameMusic.
 */

/** A single note event in a pattern. */
export interface Note {
  /** Frequency in Hz (0 = rest/silence). */
  pitch: number
  /** Duration in steps (1 step = 1 subdivision, e.g. 16th note). */
  duration: number
  /** Velocity 0–1 (default 0.8). */
  velocity?: number
}

/** A sequence of notes that fills a fixed number of steps. */
export interface Pattern {
  /** Notes in this pattern (scheduled sequentially at their step positions). */
  notes: Note[]
  /** Total length in steps. */
  length: number
}

/** A synthesizer channel (instrument voice). */
export interface Channel {
  name: string
  type: 'sine' | 'square' | 'sawtooth' | 'triangle' | 'noise'
  /** Named patterns this channel can play, keyed by section name. */
  patterns: Record<string, Pattern>
  /** Base gain 0–1. */
  gain: number
  /** Optional effects. */
  effects?: {
    /** Lowpass filter frequency in Hz. */
    filter?: number
    /** Delay time in seconds. */
    delay?: number
    /** Delay feedback 0–1. */
    delayFeedback?: number
  }
  /** Optional per-channel ADSR envelope override. */
  adsr?: { attack: number; decay: number; sustain: number; release: number }
}

/** A song section (e.g. intro, verse, chorus). */
export interface Section {
  name: string
  /** Number of bars in this section. */
  bars: number
  /** Map of channelName → patternName to play in this section. */
  channels: Record<string, string>
  /** Next section name, or null to loop self. */
  next: string | null
}

/** Parameters a game passes to update the music in real-time. */
export interface GameMusicParams {
  /** Current game speed (used to scale BPM). */
  speed?: number
  /** Current score (used for intensity mapping). */
  score?: number
  /** Night mode transition 0–1. */
  isNight?: number
  /** Current weather type. */
  weather?: string
}

/** A complete song definition — game-agnostic. */
export interface Song {
  title: string
  /** Beats per minute (base tempo). */
  bpm: number
  /** Subdivisions per beat (4 = 16th notes). */
  stepsPerBeat: number
  /** Musical key, e.g. 'A'. */
  key: string
  /** Scale name, e.g. 'minor'. */
  scale: string
  /** All sections keyed by name. */
  sections: Record<string, Section>
  /** All channels keyed by name. */
  channels: Record<string, Channel>
  /** Name of the first section to play. */
  startSection: string
  /**
   * Score thresholds → channel names to activate.
   * Keys are score thresholds (as numbers), values are arrays of channel names.
   * At each threshold, exactly those channels are active.
   */
  intensityMap?: Record<number, string[]>
  /** Genre tag for factory-generated songs (e.g. 'synthwave'). */
  genre?: string
  /** Factory seed for reproducibility. */
  seed?: number
}
