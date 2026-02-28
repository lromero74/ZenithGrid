/**
 * Connect Four game — drop discs to get four in a row.
 *
 * Features: AI opponent with difficulty levels, column hover preview,
 * win highlighting, score tracking.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import {
  createBoard, dropDisc, checkWinner, getValidColumns,
  isBoardFull, getAIMove,
  type Board, type Player, type WinResult,
} from './connectFourEngine'
import { ConnectFourBoard } from './ConnectFourBoard'
import type { GameStatus, Difficulty } from '../../../types'

const DIFFICULTY_DEPTH: Record<string, number> = {
  easy: 2, medium: 4, hard: 6,
}

export default function ConnectFour() {
  const [board, setBoard] = useState<Board>(createBoard)
  const [currentPlayer, setCurrentPlayer] = useState<Player>('red')
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [winResult, setWinResult] = useState<WinResult | null>(null)
  const [difficulty, setDifficulty] = useState<Difficulty>('medium')
  const [scores, setScores] = useState({ red: 0, yellow: 0, draw: 0 })
  const [hoverCol, setHoverCol] = useState<number | null>(null)
  const aiThinking = useRef(false)

  const handleColumnClick = useCallback((col: number) => {
    if (gameStatus !== 'playing' || currentPlayer !== 'red' || aiThinking.current) return
    if (!getValidColumns(board).includes(col)) return

    const { board: newBoard, row } = dropDisc(board, col, 'red')
    if (row === -1) return

    setBoard(newBoard)
    const winner = checkWinner(newBoard)
    if (winner) {
      setWinResult(winner)
      setGameStatus('won')
      setScores(s => ({ ...s, red: s.red + 1 }))
      return
    }
    if (isBoardFull(newBoard)) {
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
  }, [])

  const controls = (
    <div className="flex items-center justify-between">
      <DifficultySelector
        value={difficulty}
        onChange={(d) => { setDifficulty(d); handleNewGame() }}
        options={['easy', 'medium', 'hard']}
      />
      <div className="flex space-x-3 text-xs">
        <span className="text-red-400">You: {scores.red}</span>
        <span className="text-slate-500">Draw: {scores.draw}</span>
        <span className="text-yellow-400">AI: {scores.yellow}</span>
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
          />
        )}
      </div>
    </GameLayout>
  )
}
