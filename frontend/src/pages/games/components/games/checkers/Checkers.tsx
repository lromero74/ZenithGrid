/**
 * Checkers game — classic board game against AI opponent.
 *
 * Features: AI with difficulty levels, mandatory captures,
 * multi-jump chains, king promotion, score tracking.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import {
  createBoard, getAllMoves, applyMove, promoteKings,
  checkGameOver, getAIMove, getCaptureMoves,
  type Board, type Move,
} from './checkersEngine'
import { CheckersBoard } from './CheckersBoard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus, Difficulty } from '../../../types'

const DIFFICULTY_DEPTH: Record<string, number> = {
  easy: 2, medium: 4, hard: 6,
}

interface CheckersState {
  board: Board
  gameStatus: GameStatus
  difficulty: Difficulty
  scores: { red: number; black: number; draw: number }
  isPlayerTurn: boolean
}

export default function Checkers() {
  const { load, save, clear } = useGameState<CheckersState>('checkers')
  const saved = useRef(load()).current

  const [board, setBoard] = useState<Board>(saved?.board ?? createBoard)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedPiece, setSelectedPiece] = useState<[number, number] | null>(null)
  const [validMoves, setValidMoves] = useState<Move[]>([])
  const [lastMove, setLastMove] = useState<Move | null>(null)
  const [difficulty, setDifficulty] = useState<Difficulty>(saved?.difficulty ?? 'medium')
  const [scores, setScores] = useState(saved?.scores ?? { red: 0, black: 0, draw: 0 })
  const [isPlayerTurn, setIsPlayerTurn] = useState(saved?.isPlayerTurn ?? true)
  const aiThinking = useRef(false)

  // Persist state on changes
  useEffect(() => {
    save({ board, gameStatus, difficulty, scores, isPlayerTurn })
  }, [board, gameStatus, difficulty, scores, isPlayerTurn, save])

  /** Get all moves available for the player's piece at (r,c). */
  const getMovesForPiece = useCallback((board: Board, r: number, c: number): Move[] => {
    const allPlayerMoves = getAllMoves(board, 'red')
    return allPlayerMoves.filter(m => m.from[0] === r && m.from[1] === c)
  }, [])

  const handleSquareClick = useCallback((r: number, c: number) => {
    if (gameStatus !== 'playing' || !isPlayerTurn || aiThinking.current) return

    const piece = board[r][c]

    // If clicking on own piece, select it
    if (piece && piece.player === 'red') {
      const moves = getMovesForPiece(board, r, c)
      if (moves.length > 0) {
        setSelectedPiece([r, c])
        setValidMoves(moves)
      }
      return
    }

    // If a piece is selected and clicking on a valid target, make the move
    if (selectedPiece) {
      const move = validMoves.find(m => m.to[0] === r && m.to[1] === c)
      if (move) {
        let newBoard = applyMove(board, move)
        newBoard = promoteKings(newBoard)
        setBoard(newBoard)
        setLastMove(move)
        setSelectedPiece(null)
        setValidMoves([])

        // Check for multi-jump continuation
        if (move.captures.length > 0) {
          const furtherCaptures = getCaptureMoves(newBoard, move.to[0], move.to[1])
          if (furtherCaptures.length > 0) {
            // Must continue jumping with same piece
            setSelectedPiece(move.to)
            setValidMoves(furtherCaptures)
            return
          }
        }

        const winner = checkGameOver(newBoard)
        if (winner === 'red') {
          setGameStatus('won')
          setScores(s => ({ ...s, red: s.red + 1 }))
        } else if (winner === 'black') {
          setGameStatus('lost')
          setScores(s => ({ ...s, black: s.black + 1 }))
        } else {
          setIsPlayerTurn(false)
        }
      } else {
        // Clicked invalid square, deselect
        setSelectedPiece(null)
        setValidMoves([])
      }
    }
  }, [board, gameStatus, isPlayerTurn, selectedPiece, validMoves, getMovesForPiece])

  // AI turn
  useEffect(() => {
    if (isPlayerTurn || gameStatus !== 'playing') return
    aiThinking.current = true

    const timer = setTimeout(() => {
      const depth = DIFFICULTY_DEPTH[difficulty] || 4
      const aiMove = getAIMove(board, 'black', depth)
      if (!aiMove) {
        setGameStatus('won')
        setScores(s => ({ ...s, red: s.red + 1 }))
        aiThinking.current = false
        return
      }

      let newBoard = applyMove(board, aiMove)
      newBoard = promoteKings(newBoard)
      setBoard(newBoard)
      setLastMove(aiMove)

      const winner = checkGameOver(newBoard)
      if (winner === 'black') {
        setGameStatus('lost')
        setScores(s => ({ ...s, black: s.black + 1 }))
      } else if (winner === 'red') {
        setGameStatus('won')
        setScores(s => ({ ...s, red: s.red + 1 }))
      } else {
        setIsPlayerTurn(true)
      }
      aiThinking.current = false
    }, 300)

    return () => clearTimeout(timer)
  }, [isPlayerTurn, gameStatus, board, difficulty])

  const handleNewGame = useCallback(() => {
    setBoard(createBoard())
    setGameStatus('playing')
    setSelectedPiece(null)
    setValidMoves([])
    setLastMove(null)
    setIsPlayerTurn(true)
    clear()
  }, [clear])

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <DifficultySelector
          value={difficulty}
          onChange={(d) => { setDifficulty(d); handleNewGame() }}
          options={['easy', 'medium', 'hard']}
        />
        <button
          onClick={handleNewGame}
          className="px-3 py-1 rounded text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          New Game
        </button>
      </div>
      <div className="flex space-x-3 text-xs">
        <span className="text-red-400">You: {scores.red}</span>
        <span className="text-slate-500">Draw: {scores.draw}</span>
        <span className="text-slate-300">AI: {scores.black}</span>
      </div>
    </div>
  )

  return (
    <GameLayout title="Checkers" controls={controls}>
      <div className="relative flex flex-col items-center space-y-2">
        <p className="text-sm text-slate-400">
          {gameStatus === 'playing' && (isPlayerTurn ? 'Your turn (red)' : 'AI thinking...')}
        </p>

        <CheckersBoard
          board={board}
          selectedPiece={selectedPiece}
          validMoves={validMoves}
          onSquareClick={handleSquareClick}
          disabled={gameStatus !== 'playing' || !isPlayerTurn}
          lastMove={lastMove}
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
