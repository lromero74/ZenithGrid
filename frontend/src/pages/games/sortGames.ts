/**
 * Pure sorting utility for the Games Hub.
 *
 * Sorts a GameInfo array by the chosen option without mutating the input.
 */

import type { GameInfo, GameSortOption } from './types'

const DIFFICULTY_ORDER: Record<string, number> = { easy: 1, medium: 2, hard: 3 }

export function sortGames(
  games: GameInfo[],
  sort: GameSortOption,
  recentlyPlayed: Record<string, number> = {},
): GameInfo[] {
  if (sort === 'default') return games
  const sorted = [...games]
  switch (sort) {
    case 'a-z':
      return sorted.sort((a, b) => a.name.localeCompare(b.name))
    case 'z-a':
      return sorted.sort((a, b) => b.name.localeCompare(a.name))
    case 'difficulty':
      return sorted.sort((a, b) => (DIFFICULTY_ORDER[a.difficulty] ?? 99) - (DIFFICULTY_ORDER[b.difficulty] ?? 99))
    case 'category':
      return sorted.sort((a, b) => a.category.localeCompare(b.category))
    case 'recent':
      return sorted.sort((a, b) => (recentlyPlayed[b.id] ?? 0) - (recentlyPlayed[a.id] ?? 0))
    default:
      return sorted
  }
}
