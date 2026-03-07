/**
 * Shared game over overlay — shown when a game ends (win, loss, or draw).
 *
 * Displays status message, optional score, and action buttons.
 * Orchestrates smooth transition: fades out music, plays game-over jingle,
 * and animates the modal in with CSS transitions.
 */

import { useEffect, useRef } from 'react'
import { Trophy, RotateCcw, ArrowLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { clearLastGamePath } from './GameHub'
import type { GameStatus } from '../types'
import type { GameMusicControls } from '../audio/useGameMusic'
import type { GameSFXControls } from '../audio/useGameSFX'

interface GameOverModalProps {
  status: GameStatus
  score?: number
  bestScore?: number
  message?: string
  onPlayAgain: () => void
  playAgainText?: string
  music?: GameMusicControls
  sfx?: GameSFXControls
}

const STATUS_CONFIG: Record<string, { title: string; color: string; icon?: boolean; jingle: string }> = {
  won: { title: 'You Win!', color: 'text-emerald-400', icon: true, jingle: 'gameover_win' },
  lost: { title: 'Game Over', color: 'text-red-400', jingle: 'gameover_lose' },
  draw: { title: "It's a Draw", color: 'text-yellow-400', jingle: 'gameover_draw' },
}

export function GameOverModal({ status, score, bestScore, message, onPlayAgain, playAgainText, music, sfx }: GameOverModalProps) {
  const navigate = useNavigate()
  const hasPlayedRef = useRef(false)
  const config = STATUS_CONFIG[status]
  if (!config) return null

  const isNewBest = score !== undefined && bestScore !== undefined && score >= bestScore && score > 0

  // Orchestrate: fade out music, then play game-over jingle
  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => {
    if (hasPlayedRef.current) return
    hasPlayedRef.current = true

    // Fade out background music
    music?.fadeOut(800)

    // Play jingle after a short delay to let the fade begin
    const jingleTimer = setTimeout(() => {
      sfx?.playCatalog(config.jingle)
    }, 300)

    return () => clearTimeout(jingleTimer)
  }, [music, sfx, config.jingle])

  return (
    <div className="absolute inset-0 bg-slate-900/80 flex items-center justify-center z-[100] rounded-lg animate-fade-in">
      <div className="bg-slate-800 border border-slate-600 rounded-xl p-6 text-center max-w-xs w-full mx-4 animate-scale-in">
        {/* Status icon */}
        {config.icon && (
          <Trophy className="w-10 h-10 text-yellow-400 mx-auto mb-3" />
        )}

        {/* Title */}
        <h2 className={`text-2xl font-bold mb-2 ${config.color}`}>
          {config.title}
        </h2>

        {/* Custom message */}
        {message && (
          <p className="text-slate-400 text-sm mb-3">{message}</p>
        )}

        {/* Score display */}
        {score !== undefined && (
          <div className="mb-4">
            <p className="text-white text-lg font-mono">{score}</p>
            {isNewBest && (
              <p className="text-yellow-400 text-xs font-semibold mt-1">New Best!</p>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex space-x-3 justify-center">
          <button
            onClick={onPlayAgain}
            className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors text-sm font-medium"
          >
            <RotateCcw className="w-4 h-4" />
            <span>{playAgainText || 'Play Again'}</span>
          </button>
          <button
            onClick={() => { clearLastGamePath(); navigate('/games') }}
            className="flex items-center space-x-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors text-sm"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Games</span>
          </button>
        </div>
      </div>
    </div>
  )
}
