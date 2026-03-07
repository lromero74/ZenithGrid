/**
 * Games Hub — landing page that displays all available games in a card grid.
 *
 * Features search by name, category filtering, and group-by with section headings
 * (category, difficulty, A-Z, recently played).
 */

import { useState, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, LayoutList } from 'lucide-react'
import { GAMES, GAME_CATEGORIES, CARD_SUBCATEGORIES, GROUP_OPTIONS } from '../constants'
import { useGameScores } from '../hooks/useGameScores'
import { useRecentlyPlayed } from '../hooks/useRecentlyPlayed'
import { groupGames } from '../groupGames'
import { GameCard } from './GameCard'
import type { GameCategory, GameGroupOption, GameInfo } from '../types'

const LAST_GAME_KEY = 'zenith-games-last-path'
const CATEGORY_KEY = 'zenith-games-category'
const SUBCATEGORY_KEY = 'zenith-games-subcategory'
const GROUP_KEY = 'zenith-games-group'

/** Store the current game path so we can resume it later. */
export function setLastGamePath(path: string): void {
  try { sessionStorage.setItem(LAST_GAME_KEY, path) } catch { /* ignore */ }
}

/** Clear the stored game path (used when explicitly going back to hub). */
export function clearLastGamePath(): void {
  try { sessionStorage.removeItem(LAST_GAME_KEY) } catch { /* ignore */ }
}

export function GameHub() {
  const navigate = useNavigate()

  // Auto-navigate to last-played game if returning from another page
  useEffect(() => {
    try {
      const lastPath = sessionStorage.getItem(LAST_GAME_KEY)
      if (lastPath) {
        navigate(lastPath, { replace: true })
      }
    } catch { /* ignore */ }
  }, [navigate])
  const { getHighScore } = useGameScores()
  const { markPlayed, getRecentMap } = useRecentlyPlayed()
  const [activeCategory, setActiveCategoryState] = useState<'all' | GameCategory>(() => {
    try {
      const saved = sessionStorage.getItem(CATEGORY_KEY)
      if (saved) return saved as 'all' | GameCategory
    } catch { /* ignore */ }
    return 'all'
  })
  const [activeSubcategory, setActiveSubcategoryState] = useState<string>(() => {
    try {
      const saved = sessionStorage.getItem(SUBCATEGORY_KEY)
      if (saved) return saved
    } catch { /* ignore */ }
    return 'all'
  })
  const setActiveCategory = (cat: 'all' | GameCategory) => {
    setActiveCategoryState(cat)
    try { sessionStorage.setItem(CATEGORY_KEY, cat) } catch { /* ignore */ }
    if (cat !== 'cards') {
      setActiveSubcategoryState('all')
      try { sessionStorage.removeItem(SUBCATEGORY_KEY) } catch { /* ignore */ }
    }
  }
  const setActiveSubcategory = (sub: string) => {
    setActiveSubcategoryState(sub)
    try { sessionStorage.setItem(SUBCATEGORY_KEY, sub) } catch { /* ignore */ }
  }
  const [searchQuery, setSearchQuery] = useState('')
  const [groupOption, setGroupOption] = useState<GameGroupOption>(() => {
    try {
      const saved = sessionStorage.getItem(GROUP_KEY)
      if (saved) return saved as GameGroupOption
    } catch { /* ignore */ }
    return 'none'
  })
  const setGroupOptionPersisted = (opt: GameGroupOption) => {
    setGroupOption(opt)
    try { sessionStorage.setItem(GROUP_KEY, opt) } catch { /* ignore */ }
  }

  const displayedGroups = useMemo(() => {
    let games = GAMES as GameInfo[]

    // Filter by category
    if (activeCategory !== 'all') {
      games = games.filter(g => g.category === activeCategory)
    }

    // Filter by card subcategory
    if (activeCategory === 'cards' && activeSubcategory !== 'all') {
      games = games.filter(g => g.subcategory === activeSubcategory)
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      games = games.filter(g => g.name.toLowerCase().includes(q))
    }

    // Group
    return groupGames(games, groupOption, {
      recentlyPlayed: getRecentMap(),
      isCardsView: activeCategory === 'cards',
    })
  }, [activeCategory, activeSubcategory, searchQuery, groupOption, getRecentMap])

  const totalGames = displayedGroups.reduce((sum, g) => sum + g.games.length, 0)

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-white">Games</h1>
        <p className="text-slate-400 text-sm hidden sm:block">
          Take a break between trades
        </p>
      </div>

      {/* Search bar */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          type="text"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="Search games..."
          className="w-full pl-9 pr-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
        />
      </div>

      {/* Category pills + Group By dropdown */}
      <div className="flex items-center justify-between mb-6 gap-3">
        <div className="flex space-x-2 overflow-x-auto pb-1">
          {GAME_CATEGORIES.map(cat => (
            <button
              key={cat.value}
              onClick={() => setActiveCategory(cat.value as 'all' | GameCategory)}
              className={`px-3 py-1 rounded-full text-sm whitespace-nowrap transition-colors ${
                activeCategory === cat.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-slate-300'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        <div className="flex items-center space-x-1.5 shrink-0">
          <LayoutList className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={groupOption}
            onChange={e => setGroupOptionPersisted(e.target.value as GameGroupOption)}
            className="bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-300 pl-1.5 pr-1 py-1 focus:outline-none focus:border-blue-500 transition-colors cursor-pointer"
          >
            {GROUP_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Card subcategory pills */}
      {activeCategory === 'cards' && (
        <div className="flex space-x-2 overflow-x-auto pb-1 mb-4 -mt-3">
          {CARD_SUBCATEGORIES.map(sub => (
            <button
              key={sub.value}
              onClick={() => setActiveSubcategory(sub.value)}
              className={`px-2.5 py-0.5 rounded-full text-xs whitespace-nowrap transition-colors ${
                activeSubcategory === sub.value
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-700/60 text-slate-400 hover:bg-slate-600 hover:text-slate-300'
              }`}
            >
              {sub.label}
            </button>
          ))}
        </div>
      )}

      {/* Grouped game cards */}
      {displayedGroups.map(group => (
        <div key={group.label || '__default'}>
          {group.label && (
            <div className="flex items-center gap-3 mb-3 mt-6 first:mt-0">
              <h2 className="text-sm font-semibold text-slate-300">{group.label}</h2>
              <span className="text-xs text-slate-500">({group.games.length})</span>
              <div className="flex-1 border-t border-slate-700/50" />
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {group.games.map(game => (
              <GameCard
                key={game.id}
                game={game}
                highScore={getHighScore(game.id)}
                onPlay={() => markPlayed(game.id)}
              />
            ))}
          </div>
        </div>
      ))}

      {totalGames === 0 && (
        <p className="text-slate-500 text-center py-8">
          {searchQuery.trim() ? 'No games match your search.' : 'No games in this category yet.'}
        </p>
      )}
    </div>
  )
}
