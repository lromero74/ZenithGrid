/**
 * Individual game card displayed on the Games Hub page.
 *
 * Shows game icon, name, description, difficulty tag, session length,
 * and optional high score. Navigates to the game on click.
 */

import { useNavigate } from 'react-router-dom'
import { Trophy } from 'lucide-react'
import { GAME_ICONS } from '../constants'
import type { GameInfo } from '../types'

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: 'bg-emerald-900/50 text-emerald-400',
  medium: 'bg-yellow-900/50 text-yellow-400',
  hard: 'bg-red-900/50 text-red-400',
}

const CATEGORY_COLORS: Record<string, string> = {
  puzzle: 'text-blue-400',
  strategy: 'text-purple-400',
  word: 'text-emerald-400',
  arcade: 'text-orange-400',
}

interface GameCardProps {
  game: GameInfo
  highScore?: number | null
}

export function GameCard({ game, highScore }: GameCardProps) {
  const navigate = useNavigate()
  const IconComponent = GAME_ICONS[game.icon]

  return (
    <button
      onClick={() => navigate(game.path)}
      className="bg-slate-800 border border-slate-700 rounded-lg p-4 hover:border-slate-500 hover:bg-slate-750 transition-all text-left w-full group"
    >
      {/* Top row: icon + name */}
      <div className="flex items-center space-x-3 mb-2">
        <div className="w-10 h-10 rounded-lg bg-slate-700 flex items-center justify-center group-hover:bg-slate-600 transition-colors">
          {IconComponent && <IconComponent className="w-5 h-5 text-slate-300" />}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-white font-semibold text-sm sm:text-base truncate">
            {game.name}
          </h3>
          <p className="text-slate-400 text-xs sm:text-sm truncate">
            {game.description}
          </p>
        </div>
      </div>

      {/* Bottom row: tags + score */}
      <div className="flex items-center justify-between mt-3">
        <div className="flex items-center space-x-2">
          <span className={`text-xs px-2 py-0.5 rounded-full ${DIFFICULTY_COLORS[game.difficulty]}`}>
            {game.difficulty}
          </span>
          <span className={`text-xs ${CATEGORY_COLORS[game.category] || 'text-slate-400'}`}>
            {game.category}
          </span>
          <span className="text-xs text-slate-500">{game.sessionLength}</span>
        </div>

        {highScore !== undefined && highScore !== null && (
          <div className="flex items-center space-x-1 text-yellow-400">
            <Trophy className="w-3 h-3" />
            <span className="text-xs font-mono">{highScore}</span>
          </div>
        )}
      </div>
    </button>
  )
}
