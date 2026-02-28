/**
 * 2048 game — slide and merge tiles to reach 2048.
 *
 * Features: arrow/WASD + swipe controls, undo, score tracking,
 * win detection with continue option.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { Undo2 } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import {
  createBoard, move, addRandomTile, hasValidMoves, isGameWon,
  type Board, type MoveDirection,
} from './twenFoEiEngine'
import { TileGrid } from './TileGrid'
import type { GameStatus } from '../../../types'

function initBoard(): Board {
  return addRandomTile(addRandomTile(createBoard()))
}

export default function TwentyFortyEight() {
  const [board, setBoard] = useState<Board>(initBoard)
  const [score, setScore] = useState(0)
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [hasWon, setHasWon] = useState(false)
  const [history, setHistory] = useState<{ board: Board; score: number }[]>([])
  const { getHighScore, saveScore } = useGameScores()
  const bestScore = getHighScore('2048') ?? 0
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)

  const handleMove = useCallback((direction: MoveDirection) => {
    if (gameStatus !== 'playing') return

    const result = move(board, direction)
    if (!result.moved) return

    setHistory(prev => [...prev.slice(-20), { board, score }])
    const newScore = score + result.score
    const withTile = addRandomTile(result.board)
    setBoard(withTile)
    setScore(newScore)

    if (isGameWon(withTile) && !hasWon) {
      setHasWon(true)
      setGameStatus('won')
      saveScore('2048', newScore)
      return
    }

    if (!hasValidMoves(withTile)) {
      setGameStatus('lost')
      saveScore('2048', newScore)
    }
  }, [board, score, gameStatus, hasWon, saveScore])

  const handleContinue = useCallback(() => {
    setGameStatus('playing')
  }, [])

  const handleUndo = useCallback(() => {
    if (history.length === 0) return
    const prev = history[history.length - 1]
    setBoard(prev.board)
    setScore(prev.score)
    setHistory(h => h.slice(0, -1))
  }, [history])

  const handleNewGame = useCallback(() => {
    setBoard(initBoard())
    setScore(0)
    setGameStatus('playing')
    setHasWon(false)
    setHistory([])
  }, [])

  // Keyboard controls
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const map: Record<string, MoveDirection> = {
        ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
        w: 'up', s: 'down', a: 'left', d: 'right',
        W: 'up', S: 'down', A: 'left', D: 'right',
      }
      const dir = map[e.key]
      if (dir) { e.preventDefault(); handleMove(dir) }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [handleMove])

  // Touch/swipe controls
  useEffect(() => {
    const handleTouchStart = (e: TouchEvent) => {
      touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
    }
    const handleTouchEnd = (e: TouchEvent) => {
      if (!touchStartRef.current) return
      const dx = e.changedTouches[0].clientX - touchStartRef.current.x
      const dy = e.changedTouches[0].clientY - touchStartRef.current.y
      const minSwipe = 30
      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > minSwipe) {
        handleMove(dx > 0 ? 'right' : 'left')
      } else if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > minSwipe) {
        handleMove(dy > 0 ? 'down' : 'up')
      }
      touchStartRef.current = null
    }
    document.addEventListener('touchstart', handleTouchStart, { passive: true })
    document.addEventListener('touchend', handleTouchEnd, { passive: true })
    return () => {
      document.removeEventListener('touchstart', handleTouchStart)
      document.removeEventListener('touchend', handleTouchEnd)
    }
  }, [handleMove])

  const controls = (
    <div className="flex items-center justify-between">
      <button
        onClick={handleUndo}
        disabled={history.length === 0}
        className="flex items-center space-x-1 px-3 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        <Undo2 className="w-3 h-3" />
        <span>Undo</span>
      </button>
      <button
        onClick={handleNewGame}
        className="px-3 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
      >
        New Game
      </button>
    </div>
  )

  return (
    <GameLayout title="2048" score={score} bestScore={bestScore} controls={controls}>
      <div className="relative flex flex-col items-center space-y-4">
        <div style={{ touchAction: 'none' }}>
          <TileGrid board={board} />
        </div>

        <p className="text-xs text-slate-500 hidden sm:block">
          Arrow keys or WASD to move. Swipe on mobile.
        </p>

        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            score={score}
            bestScore={bestScore}
            message="You reached 2048!"
            onPlayAgain={handleContinue}
            playAgainText="Continue"
          />
        )}

        {gameStatus === 'lost' && (
          <GameOverModal
            status="lost"
            score={score}
            bestScore={bestScore}
            onPlayAgain={handleNewGame}
          />
        )}
      </div>
    </GameLayout>
  )
}
