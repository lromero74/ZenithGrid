/**
 * Hook for managing game high scores via localStorage.
 *
 * Stores one high score per game, keyed by game ID.
 * All keys prefixed with 'zenith-games-scores-'.
 */

import { useState, useCallback } from 'react'
import { STORAGE_PREFIX } from '../constants'

const SCORES_KEY = `${STORAGE_PREFIX}scores`

type ScoreMap = Record<string, number>

function loadScores(): ScoreMap {
  try {
    const raw = localStorage.getItem(SCORES_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function persistScores(scores: ScoreMap): void {
  try {
    localStorage.setItem(SCORES_KEY, JSON.stringify(scores))
  } catch {
    // Safari private mode or quota exceeded — silently ignore
  }
}

export function useGameScores() {
  const [scores, setScores] = useState<ScoreMap>(loadScores)

  const getHighScore = useCallback((gameId: string): number | null => {
    return scores[gameId] ?? null
  }, [scores])

  const saveScore = useCallback((gameId: string, score: number): void => {
    setScores(prev => {
      const current = prev[gameId]
      if (current !== undefined && current >= score) return prev
      const next = { ...prev, [gameId]: score }
      persistScores(next)
      return next
    })
  }, [])

  const clearScore = useCallback((gameId: string): void => {
    setScores(prev => {
      const next = { ...prev }
      delete next[gameId]
      persistScores(next)
      return next
    })
  }, [])

  const getAllScores = useCallback((): ScoreMap => {
    return { ...scores }
  }, [scores])

  return { getHighScore, saveScore, clearScore, getAllScores }
}
