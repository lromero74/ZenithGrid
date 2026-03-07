/**
 * Minesweeper game — reveal cells, avoid mines.
 *
 * Features: 3 difficulty levels, first-click safety, flood fill,
 * flagging (right-click / long-press), timer, mine counter.
 */

import { useState, useCallback, useRef, useMemo, useEffect} from 'react'
import { Bomb, SmilePlus } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameTimer } from '../../../hooks/useGameTimer'
import { useGameScores } from '../../../hooks/useGameScores'
import { useGameState } from '../../../hooks/useGameState'
import {
  generateBoard, revealCell, toggleFlag, checkWin,
  type MineBoard,
} from './minesweeperEngine'
import { MinesweeperGrid } from './MinesweeperGrid'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'

interface DifficultyConfig {
  rows: number
  cols: number
  mines: number
  label: string
}

const DIFFICULTIES: Record<string, DifficultyConfig> = {
  beginner: { rows: 9, cols: 9, mines: 10, label: 'Beginner' },
  intermediate: { rows: 16, cols: 16, mines: 40, label: 'Intermediate' },
  expert: { rows: 16, cols: 30, mines: 99, label: 'Expert' },
}

interface MinesweeperSaved {
  diffKey: string
  board: MineBoard | null
  gameStatus: GameStatus
  explodedCell: [number, number] | null
  elapsed: number
  firstClick: boolean
}

export default function Minesweeper() {
  const { load, save, clear } = useGameState<MinesweeperSaved>('minesweeper')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('minesweeper'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('minesweeper')

  const [diffKey, setDiffKey] = useState(saved?.diffKey ?? 'beginner')
  const diff = DIFFICULTIES[diffKey]
  const [board, setBoard] = useState<MineBoard | null>(saved?.board ?? null)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'idle')
  const [explodedCell, setExplodedCell] = useState<[number, number] | null>(saved?.explodedCell ?? null)
  const firstClick = useRef(saved?.firstClick ?? true)
  const timer = useGameTimer(saved?.elapsed)
  const { getHighScore, saveScore } = useGameScores()

  // Persist state
  useEffect(() => {
    save({ diffKey, board, gameStatus, explodedCell, elapsed: timer.seconds, firstClick: firstClick.current })
  }, [diffKey, board, gameStatus, explodedCell, timer.seconds, save])

  const flagCount = board?.flat().filter(c => c.isFlagged).length ?? 0
  const minesRemaining = diff.mines - flagCount

  const handleReveal = useCallback((row: number, col: number) => {
    if (gameStatus === 'won' || gameStatus === 'lost') return

    music.init()
    sfx.init()
    music.start()

    let currentBoard = board
    if (firstClick.current || !currentBoard) {
      // Generate board with first-click safety
      currentBoard = generateBoard(diff.rows, diff.cols, diff.mines, row, col)
      firstClick.current = false
      timer.start()
    }

    const result = revealCell(currentBoard, row, col)
    setBoard(result.board)

    if (result.hitMine) {
      sfx.play('mine')
      // Reveal all mines
      const revealedBoard = result.board.map(r =>
        r.map(c => c.isMine ? { ...c, isRevealed: true } : c)
      )
      setBoard(revealedBoard)
      setExplodedCell([row, col])
      setGameStatus('lost')
      timer.stop()
      return
    }

    sfx.play('reveal')
    if (checkWin(result.board)) {
      sfx.play('win')
      setGameStatus('won')
      timer.stop()
      const bestKey = `minesweeper-${diffKey}`
      const best = getHighScore(bestKey)
      if (!best || timer.seconds < best) {
        saveScore(bestKey, timer.seconds)
      }
    }
  }, [board, gameStatus, diff, diffKey, timer, getHighScore, saveScore])

  const handleFlag = useCallback((row: number, col: number) => {
    if (!board || gameStatus !== 'playing' && gameStatus !== 'idle') return
    if (firstClick.current) return // Can't flag before first reveal
    sfx.play('flag')
    setBoard(toggleFlag(board, row, col))
  }, [board, gameStatus])

  const handleNewGame = useCallback(() => {
    setBoard(null)
    setGameStatus('idle')
    setExplodedCell(null)
    firstClick.current = true
    timer.reset()
    clear()
  }, [timer, clear])

  const handleDifficulty = useCallback((key: string) => {
    setDiffKey(key)
    setBoard(null)
    setGameStatus('idle')
    setExplodedCell(null)
    firstClick.current = true
    timer.reset()
    clear()
  }, [timer, clear])

  // Create placeholder board for initial render
  const displayBoard = board ?? Array.from({ length: diff.rows }, () =>
    Array.from({ length: diff.cols }, () => ({
      isMine: false, isRevealed: false, isFlagged: false, adjacentMines: 0,
    }))
  )

  const isGameOver = gameStatus === 'won' || gameStatus === 'lost'

  const controls = (
    <div className="flex flex-col space-y-2">
      {/* Difficulty buttons */}
      <div className="flex space-x-2">
        {Object.entries(DIFFICULTIES).map(([key, cfg]) => (
          <button
            key={key}
            onClick={() => handleDifficulty(key)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              diffKey === key
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
          >
            {cfg.label}
          </button>
        ))}
      </div>
      {/* Status bar */}
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center space-x-1 text-red-400">
          <Bomb className="w-3.5 h-3.5" />
          <span>{minesRemaining}</span>
        </div>
        <button
          onClick={handleNewGame}
          className="p-1 hover:bg-slate-700 rounded transition-colors"
          title="New Game"
        >
          <SmilePlus className="w-5 h-5 text-yellow-400" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
        <span className="text-slate-400 font-mono text-xs">{timer.formatted}</span>
      </div>
    </div>
  )

  return (
    <GameLayout title="Minesweeper" controls={controls}>
      <div className="relative flex flex-col items-center">
        <div className={diffKey === 'expert' ? 'overflow-x-auto max-w-full' : ''}>
          <MinesweeperGrid
            board={displayBoard}
            onReveal={handleReveal}
            onFlag={handleFlag}
            gameOver={isGameOver}
            explodedCell={explodedCell}
          />
        </div>

        <p className="text-xs text-slate-500 mt-3 hidden sm:block">
          Left-click to reveal. Right-click to flag.
        </p>

        {isGameOver && (
          <GameOverModal
            status={gameStatus}
            message={gameStatus === 'won' ? `Cleared in ${timer.formatted}` : undefined}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
