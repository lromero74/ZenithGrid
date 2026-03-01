/**
 * Hook for tracking when each game was last played via localStorage.
 *
 * Stores a timestamp per game ID. Used by the "Recently Played" sort option.
 */

import { useState, useCallback } from 'react'
import { STORAGE_PREFIX } from '../constants'

const RECENT_KEY = `${STORAGE_PREFIX}recent`

type RecentMap = Record<string, number>

function loadRecent(): RecentMap {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function persistRecent(recent: RecentMap): void {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent))
  } catch {
    // Safari private mode or quota exceeded — silently ignore
  }
}

export function useRecentlyPlayed() {
  const [recent, setRecent] = useState<RecentMap>(loadRecent)

  const markPlayed = useCallback((gameId: string): void => {
    setRecent(prev => {
      const next = { ...prev, [gameId]: Date.now() }
      persistRecent(next)
      return next
    })
  }, [])

  const getLastPlayed = useCallback((gameId: string): number | null => {
    return recent[gameId] ?? null
  }, [recent])

  const getRecentMap = useCallback((): RecentMap => {
    return { ...recent }
  }, [recent])

  return { markPlayed, getLastPlayed, getRecentMap }
}
