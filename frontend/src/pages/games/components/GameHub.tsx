/**
 * Games Hub — landing page that displays all available games in a card grid.
 *
 * Features category filtering and responsive layout (1/2/3 columns).
 */

import { useState } from 'react'
import { GAMES, GAME_CATEGORIES } from '../constants'
import { useGameScores } from '../hooks/useGameScores'
import { GameCard } from './GameCard'
import type { GameCategory } from '../types'

export function GameHub() {
  const { getHighScore } = useGameScores()
  const [activeCategory, setActiveCategory] = useState<'all' | GameCategory>('all')

  const filteredGames = activeCategory === 'all'
    ? GAMES
    : GAMES.filter(g => g.category === activeCategory)

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-white">Games</h1>
        <p className="text-slate-400 text-sm hidden sm:block">
          Take a break between trades
        </p>
      </div>

      {/* Category filter pills */}
      <div className="flex space-x-2 mb-6 overflow-x-auto pb-1">
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

      {/* Game cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredGames.map(game => (
          <GameCard
            key={game.id}
            game={game}
            highScore={getHighScore(game.id)}
          />
        ))}
      </div>

      {filteredGames.length === 0 && (
        <p className="text-slate-500 text-center py-8">
          No games in this category yet.
        </p>
      )}
    </div>
  )
}
