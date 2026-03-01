/**
 * Games Hub — landing page that displays all available games in a card grid.
 *
 * Features search by name, category filtering, and sort by name/difficulty/
 * category/recently played.
 */

import { useState, useMemo } from 'react'
import { Search, ArrowUpDown } from 'lucide-react'
import { GAMES, GAME_CATEGORIES, SORT_OPTIONS } from '../constants'
import { useGameScores } from '../hooks/useGameScores'
import { useRecentlyPlayed } from '../hooks/useRecentlyPlayed'
import { sortGames } from '../sortGames'
import { GameCard } from './GameCard'
import type { GameCategory, GameSortOption } from '../types'

export function GameHub() {
  const { getHighScore } = useGameScores()
  const { markPlayed, getRecentMap } = useRecentlyPlayed()
  const [activeCategory, setActiveCategory] = useState<'all' | GameCategory>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortOption, setSortOption] = useState<GameSortOption>('default')

  const displayedGames = useMemo(() => {
    let games = GAMES

    // Filter by category
    if (activeCategory !== 'all') {
      games = games.filter(g => g.category === activeCategory)
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      games = games.filter(g => g.name.toLowerCase().includes(q))
    }

    // Sort
    return sortGames(games, sortOption, getRecentMap())
  }, [activeCategory, searchQuery, sortOption, getRecentMap])

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

      {/* Category pills + Sort dropdown */}
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
          <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={sortOption}
            onChange={e => setSortOption(e.target.value as GameSortOption)}
            className="bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-300 pl-1.5 pr-1 py-1 focus:outline-none focus:border-blue-500 transition-colors cursor-pointer"
          >
            {SORT_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Game cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {displayedGames.map(game => (
          <GameCard
            key={game.id}
            game={game}
            highScore={getHighScore(game.id)}
            onPlay={() => markPlayed(game.id)}
          />
        ))}
      </div>

      {displayedGames.length === 0 && (
        <p className="text-slate-500 text-center py-8">
          {searchQuery.trim() ? 'No games match your search.' : 'No games in this category yet.'}
        </p>
      )}
    </div>
  )
}
