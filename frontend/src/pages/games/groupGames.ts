/**
 * Grouping utility for the Games Hub.
 *
 * Groups a GameInfo array by the chosen option and returns labeled sections.
 * Each group's games are sorted alphabetically unless the group type specifies otherwise.
 */

import type { GameInfo, GameGroupOption, GameGroup } from './types'
import { CATEGORY_LABELS, DIFFICULTY_LABELS } from './constants'

const DIFFICULTY_ORDER: Record<string, number> = { easy: 1, medium: 2, hard: 3 }

function sortAlpha(games: GameInfo[]): GameInfo[] {
  return [...games].sort((a, b) => a.name.localeCompare(b.name))
}

export function groupGames(
  games: GameInfo[],
  groupBy: GameGroupOption,
  options: { recentlyPlayed?: Record<string, number>; isCardsView?: boolean } = {},
): GameGroup[] {
  if (games.length === 0) return []

  switch (groupBy) {
    case 'none':
      return [{ label: '', games }]

    case 'category': {
      if (options.isCardsView) {
        // Group by subcategory when viewing Cards specifically
        const subMap = new Map<string, GameInfo[]>()
        for (const g of games) {
          const key = g.subcategory || 'Other'
          if (!subMap.has(key)) subMap.set(key, [])
          subMap.get(key)!.push(g)
        }
        // Sort subcategory groups alphabetically by label
        const keys = [...subMap.keys()].sort((a, b) => a.localeCompare(b))
        return keys.map(key => ({ label: key, games: sortAlpha(subMap.get(key)!) }))
      }
      // Group by category
      const catMap = new Map<string, GameInfo[]>()
      for (const g of games) {
        const key = g.category
        if (!catMap.has(key)) catMap.set(key, [])
        catMap.get(key)!.push(g)
      }
      // Sort category groups alphabetically by display label
      const catKeys = [...catMap.keys()].sort((a, b) =>
        (CATEGORY_LABELS[a] || a).localeCompare(CATEGORY_LABELS[b] || b)
      )
      return catKeys.map(key => ({
        label: CATEGORY_LABELS[key] || key,
        games: sortAlpha(catMap.get(key)!),
      }))
    }

    case 'difficulty': {
      const diffMap = new Map<string, GameInfo[]>()
      for (const g of games) {
        const key = g.difficulty
        if (!diffMap.has(key)) diffMap.set(key, [])
        diffMap.get(key)!.push(g)
      }
      // Order easy → medium → hard
      const diffKeys = [...diffMap.keys()].sort(
        (a, b) => (DIFFICULTY_ORDER[a] ?? 99) - (DIFFICULTY_ORDER[b] ?? 99)
      )
      return diffKeys.map(key => ({
        label: DIFFICULTY_LABELS[key] || key,
        games: sortAlpha(diffMap.get(key)!),
      }))
    }

    case 'a-z': {
      const letterMap = new Map<string, GameInfo[]>()
      for (const g of games) {
        const letter = g.name[0].toUpperCase()
        if (!letterMap.has(letter)) letterMap.set(letter, [])
        letterMap.get(letter)!.push(g)
      }
      const letters = [...letterMap.keys()].sort()
      return letters.map(letter => ({
        label: letter,
        games: sortAlpha(letterMap.get(letter)!),
      }))
    }

    case 'recent': {
      const recentMap = options.recentlyPlayed || {}
      const recent: GameInfo[] = []
      const rest: GameInfo[] = []
      for (const g of games) {
        if (recentMap[g.id]) recent.push(g)
        else rest.push(g)
      }
      // Sort recently played by most recent first
      recent.sort((a, b) => (recentMap[b.id] ?? 0) - (recentMap[a.id] ?? 0))
      const groups: GameGroup[] = []
      if (recent.length > 0) groups.push({ label: 'Recently Played', games: recent })
      if (rest.length > 0) groups.push({ label: 'Everything Else', games: sortAlpha(rest) })
      return groups
    }

    default:
      return [{ label: '', games }]
  }
}
