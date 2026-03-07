/**
 * Connect Four game — drop discs to get four in a row.
 *
 * Features: AI opponent with difficulty levels, column hover preview,
 * win highlighting, score tracking.
 */

import { useState, useCallback, useEffect, useRef, useMemo} from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import { useGameState } from '../../../hooks/useGameState'
import {
  createBoard, dropDisc, checkWinner, getValidColumns,
  isBoardFull, getAIMove,
  type Board, type Player, type WinResult,
} from './connectFourEngine'
import { ConnectFourBoard } from './ConnectFourBoard'
import type { GameStatus, Difficulty } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'

const DIFFICULTY_DEPTH: Record<string, number> = {
  easy: 2, medium: 4, hard: 6,
}

interface ConnectFourSaved {
  board: Board
  currentPlayer: Player
  gameStatus: GameStatus
  difficulty: Difficulty
  scores: { red: number; yellow: number; draw: number }
}

export default function ConnectFour() {
  const { load, save, clear } = useGameState<ConnectFourSaved>('connect-four')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('connect-four'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('connect-four')

  const [board, setBoard] = useState<Board>(() => saved?.board ?? createBoard())
  const [currentPlayer, setCurrentPlayer] = useState<Player>(saved?.currentPlayer ?? 'red')
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [winResult, setWinResult] = useState<WinResult | null>(null)
  const [difficulty, setDifficulty] = useState<Difficulty>(saved?.difficulty ?? 'medium')
  const [scores, setScores] = useState(saved?.scores ?? { red: 0, yellow: 0, draw: 0 })
  const [hoverCol, setHoverCol] = useState<number | null>(null)
  const aiThinking = useRef(false)

  // Persist state
  useEffect(() => {
    save({ board, currentPlayer, gameStatus, difficulty, scores })
  }, [board, currentPlayer, gameStatus, difficulty, scores, save])

  const handleColumnClick = useCallback((col: number) => {
    if (gameStatus !== 'playing' || currentPlayer !== 'red' || aiThinking.current) return
    if (!getValidColumns(board).includes(col)) return

    music.init()
    sfx.init()
    music.start()

    const { board: newBoard, row } = dropDisc(board, col, 'red')
    if (row === -1) return

    sfx.play('drop')
    setBoard(newBoard)
    const winner = checkWinner(newBoard)
    if (winner) {
      setWinResult(winner)
      sfx.play('win')
      setGameStatus('won')
      setScores(s => ({ ...s, red: s.red + 1 }))
      return
    }
    if (isBoardFull(newBoard)) {
      sfx.play('draw')
      setGameStatus('draw')
      setScores(s => ({ ...s, draw: s.draw + 1 }))
      return
    }
    setCurrentPlayer('yellow')
  }, [board, gameStatus, currentPlayer])

  // AI turn
  useEffect(() => {
    if (currentPlayer !== 'yellow' || gameStatus !== 'playing') return
    aiThinking.current = true

    const timer = setTimeout(() => {
      const depth = DIFFICULTY_DEPTH[difficulty] || 4
      const col = getAIMove(board, 'yellow', depth)
      const { board: newBoard } = dropDisc(board, col, 'yellow')
      sfx.play('drop')
      setBoard(newBoard)

      const winner = checkWinner(newBoard)
      if (winner) {
        setWinResult(winner)
        setGameStatus('lost')
        setScores(s => ({ ...s, yellow: s.yellow + 1 }))
      } else if (isBoardFull(newBoard)) {
        setGameStatus('draw')
        setScores(s => ({ ...s, draw: s.draw + 1 }))
      } else {
        setCurrentPlayer('red')
      }
      aiThinking.current = false
    }, 300)

    return () => clearTimeout(timer)
  }, [currentPlayer, gameStatus, board, difficulty])

  const handleNewGame = useCallback(() => {
    setBoard(createBoard())
    setCurrentPlayer('red')
    setGameStatus('playing')
    setWinResult(null)
    setHoverCol(null)
    music.start()
    clear()
  }, [music, clear])

  const controls = (
    <div className="flex items-center justify-between">
      <DifficultySelector
        value={difficulty}
        onChange={(d) => { setDifficulty(d); handleNewGame() }}
        options={['easy', 'medium', 'hard']}
      />
      <div className="flex items-center space-x-3 text-xs">
        <span className="text-red-400">You: {scores.red}</span>
        <span className="text-slate-500">Draw: {scores.draw}</span>
        <span className="text-yellow-400">AI: {scores.yellow}</span>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Connect Four" controls={controls}>
      <div
        className="relative flex flex-col items-center space-y-2"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect()
          const x = e.clientX - rect.left
          const colWidth = rect.width / 7
          setHoverCol(Math.min(6, Math.floor(x / colWidth)))
        }}
        onMouseLeave={() => setHoverCol(null)}
      >
        {/* Turn indicator */}
        <p className="text-sm text-slate-400">
          {gameStatus === 'playing' && (currentPlayer === 'red' ? 'Your turn' : 'AI thinking...')}
        </p>

        <ConnectFourBoard
          board={board}
          winResult={winResult}
          onColumnClick={handleColumnClick}
          disabled={gameStatus !== 'playing' || currentPlayer !== 'red'}
          hoverCol={hoverCol}
          currentPlayer={currentPlayer}
        />

        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
