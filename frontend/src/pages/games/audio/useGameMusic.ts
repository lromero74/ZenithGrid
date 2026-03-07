/**
 * useGameMusic — React hook for integrating the music engine into games.
 *
 * Handles lifecycle: init (from user gesture), start, stop, updateParams, cleanup.
 */

import { useRef, useCallback, useEffect } from 'react'
import { SynthEngine } from './synthEngine'
import { Sequencer } from './sequencer'
import type { Song, GameMusicParams } from './songTypes'

const MUTE_STORAGE_KEY = 'game-music-muted'

/** BPM scaling: maps game speed range to BPM range. */
const MIN_SPEED = 2.5   // Dino Runner's INITIAL_SPEED
const MAX_SPEED = 6     // Dino Runner's MAX_SPEED
const MIN_BPM_SCALE = 1.0
const MAX_BPM_SCALE = 1.2  // Up to 20% faster at max speed

export interface GameMusicControls {
  /** Initialize audio (MUST call from user gesture). Returns true if initialized. */
  init: () => boolean
  /** Start playback. */
  start: () => void
  /** Stop playback. */
  stop: () => void
  /** Fade out music over durationMs, then stop. */
  fadeOut: (durationMs: number) => void
  /** Update music parameters from game state. */
  updateParams: (params: GameMusicParams) => void
  /** Toggle mute. Returns new muted state. */
  toggleMute: () => boolean
  /** Whether music is currently muted. */
  isMuted: () => boolean
  /** Whether the engine has been initialized. */
  isInitialized: () => boolean
}

export function useGameMusic(song: Song): GameMusicControls {
  const engineRef = useRef<SynthEngine | null>(null)
  const sequencerRef = useRef<Sequencer | null>(null)
  const initializedRef = useRef(false)
  const mutedRef = useRef(() => {
    try { return localStorage.getItem(MUTE_STORAGE_KEY) === 'true' } catch { return false }
  })
  const isMutedRef = useRef(mutedRef.current())

  const init = useCallback((): boolean => {
    if (initializedRef.current) return true

    try {
      const engine = new SynthEngine()
      engine.init()
      const seq = new Sequencer()

      // Create channels from song definition
      for (const ch of Object.values(song.channels)) {
        engine.createChannel(ch.name, ch.type as OscillatorType, ch.gain, ch.effects)
      }

      // Apply mute state
      if (isMutedRef.current) {
        engine.setMasterGain(0)
      }

      engineRef.current = engine
      sequencerRef.current = seq
      initializedRef.current = true
      return true
    } catch {
      return false
    }
  }, [song])

  const start = useCallback(() => {
    const engine = engineRef.current
    const seq = sequencerRef.current
    if (!engine || !seq || seq.isPlaying()) return

    // Reset master gain in case a prior fadeOut set it to 0.001
    engine.setMasterGain(isMutedRef.current ? 0 : 0.7)
    // Resume is a safety net — primary resume happens in init() during user gesture
    engine.resume()
    seq.start(song, engine)
  }, [song])

  const stop = useCallback(() => {
    sequencerRef.current?.stop()
  }, [])

  const fadeOut = useCallback((durationMs: number) => {
    sequencerRef.current?.fadeOut(durationMs)
  }, [])

  const updateParams = useCallback((params: GameMusicParams) => {
    const seq = sequencerRef.current
    const engine = engineRef.current
    if (!seq || !engine || !seq.isPlaying()) return

    // Scale BPM with game speed
    if (params.speed !== undefined) {
      const t = Math.max(0, Math.min(1, (params.speed - MIN_SPEED) / (MAX_SPEED - MIN_SPEED)))
      const scale = MIN_BPM_SCALE + t * (MAX_BPM_SCALE - MIN_BPM_SCALE)
      seq.setBpm(Math.round(song.bpm * scale))
    }

    // Intensity mapping based on score
    if (params.score !== undefined && song.intensityMap) {
      const thresholds = Object.keys(song.intensityMap).map(Number).sort((a, b) => b - a)
      for (const threshold of thresholds) {
        if (params.score >= threshold) {
          seq.setActiveChannels(song.intensityMap[threshold])
          break
        }
      }
    }

    // Night mode: reduce lead volume, add slight detuning feel via gain
    if (params.isNight !== undefined) {
      const nightFactor = 1 - params.isNight * 0.3
      const padBoost = 1 + params.isNight * 0.2
      if (song.channels.lead) {
        engine.setChannelGain('lead', song.channels.lead.gain * nightFactor)
      }
      if (song.channels.pad) {
        engine.setChannelGain('pad', song.channels.pad.gain * padBoost)
      }
    }

    // Weather: thunderstorm boosts delay feel via master gain pulse (subtle)
    // This is a simple approach — real reverb would need convolver nodes
    if (params.weather === 'thunderstorm') {
      engine.setMasterGain(isMutedRef.current ? 0 : 0.75)
    } else if (params.weather !== undefined) {
      engine.setMasterGain(isMutedRef.current ? 0 : 0.7)
    }
  }, [song])

  const toggleMute = useCallback((): boolean => {
    isMutedRef.current = !isMutedRef.current
    try { localStorage.setItem(MUTE_STORAGE_KEY, String(isMutedRef.current)) } catch { /* noop */ }
    if (engineRef.current) {
      engineRef.current.setMasterGain(isMutedRef.current ? 0 : 0.5)
    }
    return isMutedRef.current
  }, [])

  const isMuted = useCallback((): boolean => {
    return isMutedRef.current
  }, [])

  const isInitialized = useCallback((): boolean => {
    return initializedRef.current
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      sequencerRef.current?.stop()
      engineRef.current?.dispose()
      engineRef.current = null
      sequencerRef.current = null
      initializedRef.current = false
    }
  }, [])

  return { init, start, stop, fadeOut, updateParams, toggleMute, isMuted, isInitialized }
}
