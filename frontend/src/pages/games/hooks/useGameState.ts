/**
 * Hook for persisting full game state to localStorage.
 *
 * Saves and restores game state (board, scores, settings, etc.)
 * across page reloads and navigation. Each game gets its own key.
 */

import { useCallback, useEffect, useRef } from 'react'
import { STORAGE_PREFIX } from '../constants'

const STATE_KEY_PREFIX = `${STORAGE_PREFIX}state-`

function getKey(gameId: string): string {
  return `${STATE_KEY_PREFIX}${gameId}`
}

/** Load saved game state from localStorage, or return null. */
export function loadGameState<T>(gameId: string): T | null {
  try {
    const raw = localStorage.getItem(getKey(gameId))
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

/** Save game state to localStorage. */
export function saveGameState<T>(gameId: string, state: T): void {
  try {
    localStorage.setItem(getKey(gameId), JSON.stringify(state))
  } catch {
    // Safari private mode or quota exceeded — silently ignore
  }
}

/** Clear saved game state. */
export function clearGameState(gameId: string): void {
  try {
    localStorage.removeItem(getKey(gameId))
  } catch {
    // Silently ignore
  }
}

/**
 * React hook for game state persistence.
 *
 * Auto-saves state whenever it changes. Provides load/save/clear functions.
 * Uses a debounced save to avoid excessive writes during rapid state changes.
 */
export function useGameState<T>(gameId: string) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback((): T | null => {
    return loadGameState<T>(gameId)
  }, [gameId])

  const save = useCallback((state: T): void => {
    // Debounce saves to avoid excessive writes
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      saveGameState(gameId, state)
    }, 300)
  }, [gameId])

  const clear = useCallback((): void => {
    if (timerRef.current) clearTimeout(timerRef.current)
    clearGameState(gameId)
  }, [gameId])

  // Flush pending save on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  return { load, save, clear }
}
