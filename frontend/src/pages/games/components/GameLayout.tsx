/**
 * Shared game page wrapper — provides consistent chrome for all games.
 *
 * Renders: back navigation, game title, optional score/timer display,
 * optional controls toolbar, and centered game content area.
 */

import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

interface GameLayoutProps {
  title: string
  children: React.ReactNode
  score?: number
  bestScore?: number
  timer?: string
  controls?: React.ReactNode
}

export function GameLayout({ title, children, score, bestScore, timer, controls }: GameLayoutProps) {
  const navigate = useNavigate()

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => navigate('/games')}
          className="flex items-center space-x-2 text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
          <span className="hidden sm:inline">Back to Games</span>
        </button>

        <h1 className="text-lg sm:text-xl font-bold text-white">{title}</h1>

        <div className="flex items-center space-x-3 sm:space-x-4 text-xs sm:text-sm">
          {timer && <span className="text-slate-400 font-mono">{timer}</span>}
          {score !== undefined && <span className="text-white">Score: {score}</span>}
          {bestScore !== undefined && <span className="text-yellow-400">Best: {bestScore}</span>}
        </div>
      </div>

      {/* Game-specific controls toolbar */}
      {controls && <div className="mb-4">{controls}</div>}

      {/* Game board area */}
      <div className="flex justify-center">
        {children}
      </div>
    </div>
  )
}
