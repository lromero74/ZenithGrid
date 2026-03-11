/**
 * Hook for managing game high scores.
 *
 * For authenticated users, syncs scores with the backend database
 * and merges with localStorage (taking the higher value for each game).
 * Falls back to localStorage-only for unauthenticated users.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { useAuth } from '../../../contexts/AuthContext'
import { getStoragePrefix } from '../constants'

function getScoresKey(): string {
  return `${getStoragePrefix()}scores`
}

type ScoreMap = Record<string, number>

function loadLocalScores(): ScoreMap {
  try {
    const raw = localStorage.getItem(getScoresKey())
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function persistLocalScores(scores: ScoreMap): void {
  try {
    localStorage.setItem(getScoresKey(), JSON.stringify(scores))
  } catch {
    // Safari private mode or quota exceeded — silently ignore
  }
}

export function useGameScores() {
  const { getAccessToken } = useAuth()
  const [scores, setScores] = useState<ScoreMap>(loadLocalScores)
  const fetchedRef = useRef(false)

  // Fetch from backend on mount, merge with localStorage
  useEffect(() => {
    if (fetchedRef.current) return
    fetchedRef.current = true

    const syncScores = async () => {
      try {
        const token = getAccessToken()
        if (!token) return // unauthenticated — use localStorage only

        const res = await fetch('/api/game-history/scores', {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) return

        const serverScores: ScoreMap = await res.json()
        const localScores = loadLocalScores()
        const merged: ScoreMap = { ...serverScores }

        // Merge: take higher of local vs server for each game
        const pushToServer: [string, number][] = []
        for (const [gameId, localScore] of Object.entries(localScores)) {
          const serverScore = serverScores[gameId] ?? 0
          if (localScore > serverScore) {
            merged[gameId] = localScore
            pushToServer.push([gameId, localScore])
          }
        }

        setScores(merged)
        persistLocalScores(merged)

        // Push any higher local scores to server (fire-and-forget)
        for (const [gameId, score] of pushToServer) {
          fetch(`/api/game-history/scores/${gameId}`, {
            method: 'PUT',
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ score }),
          }).catch(() => {})
        }
      } catch {
        // Network error — use localStorage scores
      }
    }

    syncScores()
  }, [getAccessToken])

  const getHighScore = useCallback((gameId: string): number | null => {
    return scores[gameId] ?? null
  }, [scores])

  const saveScore = useCallback((gameId: string, score: number): void => {
    setScores(prev => {
      const current = prev[gameId]
      if (current !== undefined && current >= score) return prev
      const next = { ...prev, [gameId]: score }
      persistLocalScores(next)

      // Fire-and-forget backend update
      const token = getAccessToken()
      if (token) {
        fetch(`/api/game-history/scores/${gameId}`, {
          method: 'PUT',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ score }),
        }).catch(() => {})
      }

      return next
    })
  }, [getAccessToken])

  const clearScore = useCallback((gameId: string): void => {
    setScores(prev => {
      const next = { ...prev }
      delete next[gameId]
      persistLocalScores(next)
      return next
    })
  }, [])

  const getAllScores = useCallback((): ScoreMap => {
    return { ...scores }
  }, [scores])

  return { getHighScore, saveScore, clearScore, getAllScores }
}
