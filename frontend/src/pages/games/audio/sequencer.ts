/**
 * Sequencer — look-ahead pattern scheduler for the music engine.
 *
 * Uses a timer-based look-ahead approach: fires every TIMER_INTERVAL ms,
 * scheduling notes up to LOOK_AHEAD seconds into the future. This avoids
 * timing jitter from JavaScript's event loop.
 */

import type { Song, Note } from './songTypes'
import type { SynthEngine } from './synthEngine'

const TIMER_INTERVAL = 25   // ms between scheduler ticks
const LOOK_AHEAD = 0.1      // seconds to schedule ahead
const MIN_BPM = 40
const MAX_BPM = 240

/** Drum pitch codes used in drum patterns: 1=kick, 2=snare, 3=hihat, 4=clap. */
const DRUM_MAP: Record<number, 'kick' | 'snare' | 'hihat' | 'clap'> = {
  1: 'kick',
  2: 'snare',
  3: 'hihat',
  4: 'clap',
}

export class Sequencer {
  private song: Song | null = null
  private engine: SynthEngine | null = null
  private timerId: ReturnType<typeof setInterval> | null = null
  private playing = false

  // Timing state
  private bpm = 120
  private stepDuration = 0  // seconds per step
  private nextStepTime = 0  // AudioContext time of next step to schedule

  // Position tracking
  private currentSection = ''
  private currentStep = 0
  private stepsPerBar = 0

  // Channel activation
  private activeChannels = new Set<string>()
  private sectionChangeCb: ((section: string) => void) | null = null

  /** Start playback from the song's start section. */
  start(song: Song, engine: SynthEngine): void {
    if (this.playing) return

    this.song = song
    this.engine = engine
    this.bpm = song.bpm
    this.stepsPerBar = song.stepsPerBeat * 4 // 4 beats per bar
    this.updateStepDuration()

    // Start from the beginning
    this.currentSection = song.startSection
    this.currentStep = 0
    this.nextStepTime = engine.getTime() + 0.05 // small delay to avoid scheduling in the past

    // Activate all channels by default
    this.activeChannels = new Set(Object.keys(song.channels))
    this.applyChannelGains()

    this.playing = true
    this.timerId = setInterval(() => this.scheduler(), TIMER_INTERVAL)
  }

  /** Stop playback and silence all. */
  stop(): void {
    if (this.timerId !== null) {
      clearInterval(this.timerId)
      this.timerId = null
    }
    this.playing = false
  }

  /** Fade out music and stop the sequencer when fade completes. */
  fadeOut(durationMs: number): void {
    if (!this.playing || !this.engine) return
    this.engine.fadeOut(durationMs, () => this.stop())
  }

  /** Whether the sequencer is currently playing. */
  isPlaying(): boolean {
    return this.playing
  }

  /** Set a callback for section changes. */
  onSectionChange(cb: (section: string) => void): void {
    this.sectionChangeCb = cb
  }

  /** Dynamically change the BPM (clamped to MIN_BPM–MAX_BPM). */
  setBpm(bpm: number): void {
    this.bpm = Math.max(MIN_BPM, Math.min(MAX_BPM, bpm))
    this.updateStepDuration()
  }

  /** Set which channels are audible. Others are muted. */
  setActiveChannels(names: string[]): void {
    this.activeChannels = new Set(names)
    this.applyChannelGains()
  }

  // -----------------------------------------------------------------------
  // Internal scheduling
  // -----------------------------------------------------------------------

  private updateStepDuration(): void {
    // seconds per step = 60 / bpm / stepsPerBeat
    const stepsPerBeat = this.song?.stepsPerBeat ?? 4
    this.stepDuration = 60 / this.bpm / stepsPerBeat
  }

  /** Core scheduler — called every TIMER_INTERVAL ms. */
  private scheduler(): void {
    if (!this.playing || !this.song || !this.engine) return

    const currentTime = this.engine.getTime()
    const scheduleUntil = currentTime + LOOK_AHEAD

    while (this.nextStepTime < scheduleUntil) {
      this.scheduleStep(this.nextStepTime)
      this.advanceStep()
      this.nextStepTime += this.stepDuration
    }
  }

  /** Schedule all channel notes for the current step. */
  private scheduleStep(time: number): void {
    if (!this.song || !this.engine) return

    const section = this.song.sections[this.currentSection]
    if (!section) return

    for (const [channelName, patternName] of Object.entries(section.channels)) {
      if (!this.activeChannels.has(channelName)) continue

      const channel = this.song.channels[channelName]
      if (!channel) continue

      const pattern = channel.patterns[patternName]
      if (!pattern) continue

      // Find the note at the current step position within the pattern
      const note = this.getNoteAtStep(pattern.notes, pattern.length, this.currentStep % pattern.length)
      if (!note || note.pitch === 0) continue

      const noteDuration = note.duration * this.stepDuration
      const velocity = note.velocity ?? 0.8

      if (channel.type === 'noise') {
        // Drum channel — use pitch codes
        const drumType = DRUM_MAP[note.pitch]
        if (drumType) {
          this.engine.playDrum(drumType, time, velocity)
        }
      } else {
        this.engine.playNote(channelName, note.pitch, time, noteDuration, velocity, channel.adsr)
      }
    }
  }

  /**
   * Get the note that should sound at a given step position.
   * Notes are laid out sequentially — each note occupies `duration` steps.
   */
  private getNoteAtStep(notes: Note[], _patternLength: number, step: number): Note | null {
    let pos = 0
    for (const note of notes) {
      if (step >= pos && step < pos + note.duration) {
        // Only trigger on the first step of the note
        if (step === pos) return note
        return null // in the middle of a held note
      }
      pos += note.duration
    }
    return null
  }

  /** Advance the step counter and handle section transitions. */
  private advanceStep(): void {
    if (!this.song) return

    this.currentStep++
    const section = this.song.sections[this.currentSection]
    if (!section) return

    const totalSteps = section.bars * this.stepsPerBar

    if (this.currentStep >= totalSteps) {
      // Section complete — transition
      this.currentStep = 0

      const nextSection = section.next ?? this.currentSection
      if (nextSection !== this.currentSection) {
        this.currentSection = nextSection
        this.sectionChangeCb?.(nextSection)
      }
    }
  }

  /** Apply gain values based on active channel set. */
  private applyChannelGains(): void {
    if (!this.song || !this.engine) return

    for (const [name, channel] of Object.entries(this.song.channels)) {
      const gain = this.activeChannels.has(name) ? channel.gain : 0
      this.engine.setChannelGain(name, gain)
    }
  }
}
