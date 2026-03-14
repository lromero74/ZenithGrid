/**
 * Hook for managing game high scores.
 *
 * For authenticated users, syncs scores with the backend database
 * and merges with localStorage (taking the better value for each game).
 * Falls back to localStorage-only for unauthenticated users.
 *
 * Supports score types: high_score (higher is better), fastest_time (lower is better).
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { useAuth } from '../../../contexts/AuthContext'
import { getStoragePrefix } from '../constants'

function getScoresKey(): string {
  return `${getStoragePrefix()}scores`
}

interface ScoreEntry {
  score: number
  score_type?: string
}

type ScoreMap = Record<string, ScoreEntry>
// Legacy format for backwards compat with localStorage
type LegacyScoreMap = Record<string, number>

function loadLocalScores(): ScoreMap {
  try {
    const raw = localStorage.getItem(getScoresKey())
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    // Handle legacy format (plain numbers)
    const result: ScoreMap = {}
    for (const [key, val] of Object.entries(parsed)) {
      if (typeof val === 'number') {
        result[key] = { score: val, score_type: 'high_score' }
      } else if (val && typeof val === 'object' && 'score' in (val as object)) {
        result[key] = val as ScoreEntry
      }
    }
    return result
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

function isBetter(newScore: number, oldScore: number, scoreType: string): boolean {
  if (scoreType === 'fastest_time') return newScore < oldScore
  return newScore > oldScore
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

        // Merge: take better of local vs server for each game
        const pushToServer: [string, ScoreEntry][] = []
        for (const [gameId, localEntry] of Object.entries(localScores)) {
          const serverEntry = serverScores[gameId]
          const scoreType = localEntry.score_type || 'high_score'
          if (!serverEntry || isBetter(localEntry.score, serverEntry.score, scoreType)) {
            merged[gameId] = localEntry
            pushToServer.push([gameId, localEntry])
          }
        }

        setScores(merged)
        persistLocalScores(merged)

        // Push any better local scores to server (fire-and-forget)
        for (const [gameId, entry] of pushToServer) {
          fetch(`/api/game-history/scores/${gameId}`, {
            method: 'PUT',
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ score: entry.score, score_type: entry.score_type || 'high_score' }),
          }).catch(() => {})
        }
      } catch {
        // Network error — use localStorage scores
      }
    }

    syncScores()
  }, [getAccessToken])

  const getHighScore = useCallback((gameId: string): number | null => {
    return scores[gameId]?.score ?? null
  }, [scores])

  const getScoreType = useCallback((gameId: string): string | undefined => {
    return scores[gameId]?.score_type
  }, [scores])

  const saveScore = useCallback((gameId: string, score: number, scoreType: string = 'high_score'): void => {
    setScores(prev => {
      const current = prev[gameId]
      if (current && !isBetter(score, current.score, scoreType)) return prev
      const entry: ScoreEntry = { score, score_type: scoreType }
      const next = { ...prev, [gameId]: entry }
      persistLocalScores(next)

      // Fire-and-forget backend update
      const token = getAccessToken()
      if (token) {
        fetch(`/api/game-history/scores/${gameId}`, {
          method: 'PUT',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ score, score_type: scoreType }),
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

  return { getHighScore, getScoreType, saveScore, clearScore, getAllScores }
}
