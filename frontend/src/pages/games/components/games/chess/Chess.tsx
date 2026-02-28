/**
 * Chess game — classic chess against AI opponent.
 *
 * Features: AI with difficulty levels (minimax + alpha-beta pruning),
 * full rules (castling, en passant, promotion), check/checkmate/stalemate,
 * captured pieces display, score tracking, state persistence.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import {
  createBoard, getValidMoves, isInCheck, isCheckmate, isStalemate, isDraw,
  applyMove, getAIMove, getPieceSymbol,
  type ChessState, type Move, type PieceType,
} from './chessEngine'
import { ChessBoard } from './ChessBoard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus, Difficulty } from '../../../types'

const DIFFICULTY_DEPTH: Record<string, number> = {
  easy: 2, medium: 3, hard: 4,
}

interface ChessSavedState {
  chessState: ChessState
  gameStatus: GameStatus
  difficulty: Difficulty
  scores: { white: number; black: number; draw: number }
  isPlayerTurn: boolean
}

export default function Chess() {
  const { load, save, clear } = useGameState<ChessSavedState>('chess')
  const saved = useRef(load()).current

  const [chessState, setChessState] = useState<ChessState>(saved?.chessState ?? createBoard)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedSquare, setSelectedSquare] = useState<[number, number] | null>(null)
  const [validMoves, setValidMoves] = useState<Move[]>([])
  const [lastMove, setLastMove] = useState<Move | null>(null)
  const [difficulty, setDifficulty] = useState<Difficulty>(saved?.difficulty ?? 'medium')
  const [scores, setScores] = useState(saved?.scores ?? { white: 0, black: 0, draw: 0 })
  const [isPlayerTurn, setIsPlayerTurn] = useState(saved?.isPlayerTurn ?? true)
  const [promotionMove, setPromotionMove] = useState<Move | null>(null)
  const aiThinking = useRef(false)

  // Persist state on changes
  useEffect(() => {
    save({ chessState, gameStatus, difficulty, scores, isPlayerTurn })
  }, [chessState, gameStatus, difficulty, scores, isPlayerTurn, save])

  const checkGameEnd = useCallback((state: ChessState) => {
    const nextPlayer = state.currentPlayer
    if (isCheckmate(state, nextPlayer)) {
      if (nextPlayer === 'black') {
        setGameStatus('won')
        setScores(s => ({ ...s, white: s.white + 1 }))
      } else {
        setGameStatus('lost')
        setScores(s => ({ ...s, black: s.black + 1 }))
      }
      return true
    }
    if (isStalemate(state, nextPlayer) || isDraw(state)) {
      setGameStatus('draw')
      setScores(s => ({ ...s, draw: s.draw + 1 }))
      return true
    }
    return false
  }, [])

  const handleSquareClick = useCallback((r: number, c: number) => {
    if (gameStatus !== 'playing' || !isPlayerTurn || aiThinking.current) return

    const piece = chessState.board[r][c]

    // If clicking on own piece, select it
    if (piece && piece.color === 'white') {
      const moves = getValidMoves(chessState, r, c)
      if (moves.length > 0) {
        setSelectedSquare([r, c])
        setValidMoves(moves)
      }
      return
    }

    // If a piece is selected and clicking on a valid target, make the move
    if (selectedSquare) {
      const move = validMoves.find(m => m.toRow === r && m.toCol === c)
      if (move) {
        // Check for pawn promotion
        const movingPiece = chessState.board[move.fromRow][move.fromCol]
        if (movingPiece?.type === 'pawn' && (move.toRow === 0 || move.toRow === 7) && !move.promotion) {
          // Show promotion dialog
          setPromotionMove(move)
          return
        }

        const newState = applyMove(chessState, move)
        setChessState(newState)
        setLastMove(move)
        setSelectedSquare(null)
        setValidMoves([])

        if (!checkGameEnd(newState)) {
          setIsPlayerTurn(false)
        }
      } else {
        setSelectedSquare(null)
        setValidMoves([])
      }
    }
  }, [chessState, gameStatus, isPlayerTurn, selectedSquare, validMoves, checkGameEnd])

  const handlePromotion = useCallback((pieceType: PieceType) => {
    if (!promotionMove) return
    const move: Move = { ...promotionMove, promotion: pieceType }
    const newState = applyMove(chessState, move)
    setChessState(newState)
    setLastMove(move)
    setSelectedSquare(null)
    setValidMoves([])
    setPromotionMove(null)

    if (!checkGameEnd(newState)) {
      setIsPlayerTurn(false)
    }
  }, [chessState, promotionMove, checkGameEnd])

  // AI turn
  useEffect(() => {
    if (isPlayerTurn || gameStatus !== 'playing') return
    aiThinking.current = true

    const timer = setTimeout(() => {
      const depth = DIFFICULTY_DEPTH[difficulty] || 3
      const aiMove = getAIMove(chessState, depth)
      if (!aiMove) {
        // No moves available — check why
        if (isInCheck(chessState, 'black')) {
          setGameStatus('won')
          setScores(s => ({ ...s, white: s.white + 1 }))
        } else {
          setGameStatus('draw')
          setScores(s => ({ ...s, draw: s.draw + 1 }))
        }
        aiThinking.current = false
        return
      }

      const newState = applyMove(chessState, aiMove)
      setChessState(newState)
      setLastMove(aiMove)

      if (!checkGameEnd(newState)) {
        setIsPlayerTurn(true)
      }
      aiThinking.current = false
    }, 300)

    return () => clearTimeout(timer)
  }, [isPlayerTurn, gameStatus, chessState, difficulty, checkGameEnd])

  const handleNewGame = useCallback(() => {
    setChessState(createBoard())
    setGameStatus('playing')
    setSelectedSquare(null)
    setValidMoves([])
    setLastMove(null)
    setIsPlayerTurn(true)
    setPromotionMove(null)
    clear()
  }, [clear])

  const playerCheck = isPlayerTurn && isInCheck(chessState, 'white')
  const aiCheck = !isPlayerTurn && isInCheck(chessState, 'black')

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
        <span className="text-white">You: {scores.white}</span>
        <span className="text-slate-500">Draw: {scores.draw}</span>
        <span className="text-slate-300">AI: {scores.black}</span>
      </div>
    </div>
  )

  return (
    <GameLayout title="Chess" controls={controls}>
      <div className="relative flex flex-col items-center space-y-2">
        {/* Captured by black (white pieces taken) */}
        <div className="flex gap-0.5 text-sm min-h-[20px] text-slate-400">
          {chessState.capturedPieces.black.map((type, i) => (
            <span key={i}>{getPieceSymbol({ type, color: 'white' })}</span>
          ))}
        </div>

        <p className="text-sm text-slate-400">
          {gameStatus === 'playing' && (
            isPlayerTurn
              ? `Your turn (white)${playerCheck ? ' — Check!' : ''}`
              : `AI thinking...${aiCheck ? ' — Check!' : ''}`
          )}
        </p>

        <ChessBoard
          state={chessState}
          selectedSquare={selectedSquare}
          validMoves={validMoves}
          onSquareClick={handleSquareClick}
          disabled={gameStatus !== 'playing' || !isPlayerTurn}
          lastMove={lastMove}
          inCheck={playerCheck || aiCheck}
        />

        {/* Captured by white (black pieces taken) */}
        <div className="flex gap-0.5 text-sm min-h-[20px] text-slate-400">
          {chessState.capturedPieces.white.map((type, i) => (
            <span key={i}>{getPieceSymbol({ type, color: 'black' })}</span>
          ))}
        </div>

        {/* Promotion modal */}
        {promotionMove && (
          <div className="absolute inset-0 bg-slate-900/70 flex items-center justify-center z-50 rounded-lg">
            <div className="bg-slate-800 border border-slate-600 rounded-lg p-4">
              <p className="text-white text-sm mb-2 text-center">Promote pawn to:</p>
              <div className="flex gap-2">
                {(['queen', 'rook', 'bishop', 'knight'] as PieceType[]).map(type => (
                  <button
                    key={type}
                    onClick={() => handlePromotion(type)}
                    className="w-12 h-12 bg-slate-700 hover:bg-slate-600 rounded-lg text-2xl flex items-center justify-center transition-colors"
                  >
                    {getPieceSymbol({ type, color: 'white' })}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

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
