/**
 * useGameSFX — React hook for integrating procedural SFX into games.
 *
 * Mirrors useGameMusic's lifecycle pattern: init (from user gesture),
 * play (by event name), ambient start/stop, mute toggle.
 * SFX volume and mute state are independent from music.
 */

import { useRef, useCallback, useEffect } from 'react'
import { SFXEngine } from './sfxEngine'
import { SFX_CATALOG } from './sfxCatalog'
import { getGameSFXMap } from './sfxRegistry'

const SFX_MUTE_KEY = 'game-sfx-muted'

export interface GameSFXControls {
  /** Initialize SFX engine. Pass shared AudioContext from music if available. */
  init: (sharedCtx?: AudioContext) => boolean
  /** Play an SFX by game event name (looked up via registry). */
  play: (event: string) => void
  /** Play an SFX directly by catalog name (bypasses per-game registry). */
  playCatalog: (catalogName: string) => void
  /** Start a looping ambient effect by catalog name. */
  startAmbient: (name: string) => void
  /** Stop a specific ambient effect. */
  stopAmbient: (name: string) => void
  /** Stop all ambient effects. */
  stopAllAmbient: () => void
  /** Toggle mute. Returns new muted state. */
  toggleMute: () => boolean
  /** Whether SFX are currently muted. */
  isMuted: () => boolean
}

export function useGameSFX(gameId: string): GameSFXControls {
  const engineRef = useRef<SFXEngine | null>(null)
  const initializedRef = useRef(false)
  const eventMapRef = useRef(getGameSFXMap(gameId))
  const ambientRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map())
  const isMutedRef = useRef(() => {
    try { return localStorage.getItem(SFX_MUTE_KEY) === 'true' } catch { return false }
  })
  const mutedState = useRef(isMutedRef.current())

  const init = useCallback((sharedCtx?: AudioContext): boolean => {
    if (initializedRef.current) return true
    try {
      const engine = new SFXEngine()
      engine.init(sharedCtx)
      engine.setMuted(mutedState.current)
      engineRef.current = engine
      initializedRef.current = true
      return true
    } catch {
      return false
    }
  }, [])

  const play = useCallback((event: string): void => {
    const engine = engineRef.current
    const map = eventMapRef.current
    if (!engine || !map) return

    const effectName = map[event]
    if (!effectName) return

    const recipe = SFX_CATALOG[effectName]
    if (!recipe) return

    const t = engine.getTime()
    const variation = Math.random()
    recipe(engine, t, variation)
  }, [])

  const playCatalog = useCallback((catalogName: string): void => {
    const engine = engineRef.current
    if (!engine) return

    const recipe = SFX_CATALOG[catalogName]
    if (!recipe) return

    const t = engine.getTime()
    const variation = Math.random()
    recipe(engine, t, variation)
  }, [])

  const startAmbient = useCallback((name: string): void => {
    const engine = engineRef.current
    if (!engine || ambientRef.current.has(name)) return

    const recipe = SFX_CATALOG[name]
    if (!recipe) return

    // Play immediately, then repeat for continuous ambient
    recipe(engine, engine.getTime(), Math.random())

    // For ambient effects, re-trigger periodically with variation
    const interval = setInterval(() => {
      if (!engineRef.current) return
      recipe(engineRef.current, engineRef.current.getTime(), Math.random())
    }, 4000) // Re-trigger every 4s (ambient effects are long/looping)

    ambientRef.current.set(name, interval)
  }, [])

  const stopAmbient = useCallback((name: string): void => {
    const interval = ambientRef.current.get(name)
    if (interval) {
      clearInterval(interval)
      ambientRef.current.delete(name)
    }
  }, [])

  const stopAllAmbient = useCallback((): void => {
    for (const [, interval] of ambientRef.current) {
      clearInterval(interval)
    }
    ambientRef.current.clear()
  }, [])

  const toggleMute = useCallback((): boolean => {
    mutedState.current = !mutedState.current
    try { localStorage.setItem(SFX_MUTE_KEY, String(mutedState.current)) } catch { /* noop */ }
    if (engineRef.current) {
      engineRef.current.setMuted(mutedState.current)
    }
    return mutedState.current
  }, [])

  const isMuted = useCallback((): boolean => {
    return mutedState.current
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      // Stop all ambient loops
      for (const interval of ambientRef.current.values()) {
        clearInterval(interval)
      }
      ambientRef.current.clear()
      // Dispose engine
      engineRef.current?.dispose()
      engineRef.current = null
      initializedRef.current = false
    }
  }, [])

  return { init, play, playCatalog, startAmbient, stopAmbient, stopAllAmbient, toggleMute, isMuted }
}
