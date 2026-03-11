/**
 * Chess Multiplayer VS — two human players over WebSocket.
 *
 * Reuses ChessBoard and chessEngine.
 * Host plays White (goes first), guest plays Black.
 * Moves are sent via WebSocket; both clients validate locally.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { ChessBoard } from './ChessBoard'
import {
  createBoard, applyMove, getValidMoves, isCheckmate, isStalemate, isDraw, isInCheck,
  getPieceSymbol,
  type ChessState, type Move, type PieceType, type PieceColor,
} from './chessEngine'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'

// ── Piece symbols for promotion modal ────────────────────────────────

const PIECE_SYMBOLS: Record<PieceColor, Record<PieceType, string>> = {
  white: { king: '\u2654', queen: '\u2655', rook: '\u2656', bishop: '\u2657', knight: '\u2658', pawn: '\u2659' },
  black: { king: '\u265A', queen: '\u265B', rook: '\u265C', bishop: '\u265D', knight: '\u265E', pawn: '\u265F' },
}

// ── Promotion modal ──────────────────────────────────────────────────

function PromotionModal({ color, onSelect }: { color: PieceColor; onSelect: (type: PieceType) => void }) {
  const pieces: PieceType[] = ['queen', 'rook', 'bishop', 'knight']
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-slate-800 rounded-xl p-4 border border-slate-600">
        <p className="text-sm text-white mb-3 text-center">Choose promotion piece</p>
        <div className="flex gap-2">
          {pieces.map(p => (
            <button key={p} onClick={() => onSelect(p)}
              className="px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded text-white text-lg">
              {PIECE_SYMBOLS[color][p]}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Component ────────────────────────────────────────────────────────

interface ChessMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  onLeave?: () => void
}

export function ChessMultiplayer({ roomId, players, playerNames = {}, onLeave }: ChessMultiplayerProps) {
  const { user } = useAuth()
  const song = useMemo(() => getSongForGame('chess'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('chess')

  // Host (first player) = white, guest = black
  const myColor: PieceColor = players[0] === user?.id ? 'white' : 'black'
  const opponentColor: PieceColor = myColor === 'white' ? 'black' : 'white'
  const myName = playerNames[user?.id ?? 0] || 'You'
  const opponentId = players.find(id => id !== user?.id)
  const opponentName = opponentId ? (playerNames[opponentId] || 'Opponent') : 'Opponent'

  const [chessState, setChessState] = useState<ChessState>(createBoard)
  const [selectedSquare, setSelectedSquare] = useState<[number, number] | null>(null)
  const [validMoves, setValidMoves] = useState<Move[]>([])
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [lastMove, setLastMove] = useState<Move | null>(null)
  const [promotionMove, setPromotionMove] = useState<Move | null>(null)

  const isMyTurn = chessState.currentPlayer === myColor

  // Ref to avoid re-subscribing WS listener on every state change
  const stateRef = useRef(chessState)
  stateRef.current = chessState

  // Check game end conditions after a move
  const checkGameEnd = useCallback((state: ChessState, mover: PieceColor): GameStatus => {
    const nextPlayer = state.currentPlayer
    if (isCheckmate(state, nextPlayer)) {
      // The player who just moved delivered checkmate
      return mover === myColor ? 'won' : 'lost'
    }
    if (isStalemate(state, nextPlayer) || isDraw(state)) {
      return 'draw'
    }
    return 'playing'
  }, [myColor])

  // Listen for opponent's moves
  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      const action = msg.action
      if (!action || action.type !== 'move') return
      if (msg.playerId === user?.id) return

      const move: Move = {
        fromRow: action.fromRow as number,
        fromCol: action.fromCol as number,
        toRow: action.toRow as number,
        toCol: action.toCol as number,
        ...(action.promotion ? { promotion: action.promotion as PieceType } : {}),
      }

      const currentState = stateRef.current
      const newState = applyMove(currentState, move)

      // SFX
      if (currentState.board[move.toRow][move.toCol]) {
        sfx.play('capture')
      } else {
        sfx.play('move')
      }

      setChessState(newState)
      setLastMove(move)
      setSelectedSquare(null)
      setValidMoves([])

      const result = checkGameEnd(newState, opponentColor)
      if (result !== 'playing') {
        setGameStatus(result)
        if (result === 'lost') sfx.play('checkmate')
        return
      }
      if (isInCheck(newState, newState.currentPlayer)) {
        sfx.play('check')
      }
    })
    return unsub
  }, [roomId, myColor, opponentColor, sfx, user?.id, checkGameEnd])

  const executeMove = useCallback((move: Move) => {
    const currentState = chessState
    const newState = applyMove(currentState, move)

    // SFX
    if (currentState.board[move.toRow][move.toCol]) {
      sfx.play('capture')
    } else {
      sfx.play('move')
    }

    setChessState(newState)
    setLastMove(move)
    setSelectedSquare(null)
    setValidMoves([])
    setPromotionMove(null)

    // Send move to opponent
    gameSocket.sendAction(roomId, {
      type: 'move',
      fromRow: move.fromRow,
      fromCol: move.fromCol,
      toRow: move.toRow,
      toCol: move.toCol,
      ...(move.promotion ? { promotion: move.promotion } : {}),
    })

    const result = checkGameEnd(newState, myColor)
    if (result !== 'playing') {
      setGameStatus(result)
      if (result === 'won') sfx.play('checkmate')
      return
    }
    if (isInCheck(newState, newState.currentPlayer)) {
      sfx.play('check')
    }
  }, [chessState, roomId, myColor, sfx, checkGameEnd])

  const handleSquareClick = useCallback((r: number, c: number) => {
    if (gameStatus !== 'playing' || !isMyTurn) return

    music.init()
    sfx.init()
    music.start()

    const piece = chessState.board[r][c]

    // Click own piece → select it
    if (piece && piece.color === myColor) {
      const moves = getValidMoves(chessState, r, c)
      if (moves.length > 0) {
        setSelectedSquare([r, c])
        setValidMoves(moves)
      }
      return
    }

    // If a piece is selected and clicking a valid target, attempt move
    if (selectedSquare) {
      const move = validMoves.find(m => m.toRow === r && m.toCol === c)
      if (move) {
        // Check for pawn promotion
        const movingPiece = chessState.board[move.fromRow][move.fromCol]
        if (movingPiece?.type === 'pawn' && (move.toRow === 0 || move.toRow === 7) && !move.promotion) {
          setPromotionMove(move)
          return
        }
        executeMove(move)
      } else {
        setSelectedSquare(null)
        setValidMoves([])
      }
    }
  }, [chessState, gameStatus, isMyTurn, myColor, selectedSquare, validMoves, executeMove, music, sfx])

  const handlePromotion = useCallback((pieceType: PieceType) => {
    if (!promotionMove) return
    const move: Move = { ...promotionMove, promotion: pieceType }
    executeMove(move)
  }, [promotionMove, executeMove])

  const inCheck = gameStatus === 'playing' && isInCheck(chessState, chessState.currentPlayer)

  const turnLabel = isMyTurn
    ? `${myName}'s turn (${myColor === 'white' ? 'White' : 'Black'})${inCheck ? ' \u2014 Check!' : ''}`
    : `${opponentName}'s turn (${opponentColor === 'white' ? 'White' : 'Black'})${inCheck ? ' \u2014 Check!' : ''}`

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
        <span className={`text-xs font-medium ${myColor === 'white' ? 'text-white' : 'text-slate-300'}`}>
          {myName}: {myColor === 'white' ? 'White' : 'Black'}
        </span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Chess — VS" controls={controls}>
      <div className="relative flex flex-col items-center space-y-2">
        {/* Captured by opponent (my pieces taken) */}
        <div className="flex gap-0.5 text-sm min-h-[20px] text-slate-400">
          {chessState.capturedPieces[opponentColor].map((type, i) => (
            <span key={i}>{getPieceSymbol({ type, color: myColor })}</span>
          ))}
        </div>

        <p className="text-sm text-slate-400">{gameStatus === 'playing' ? turnLabel : ''}</p>

        <ChessBoard
          state={chessState}
          selectedSquare={selectedSquare}
          validMoves={validMoves}
          onSquareClick={handleSquareClick}
          disabled={gameStatus !== 'playing' || !isMyTurn}
          lastMove={lastMove}
          inCheck={inCheck}
        />

        {/* Captured by me (opponent pieces taken) */}
        <div className="flex gap-0.5 text-sm min-h-[20px] text-slate-400">
          {chessState.capturedPieces[myColor].map((type, i) => (
            <span key={i}>{getPieceSymbol({ type, color: opponentColor })}</span>
          ))}
        </div>

        {/* Promotion modal */}
        {promotionMove && <PromotionModal color={myColor} onSelect={handlePromotion} />}

        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            onPlayAgain={onLeave || (() => {})}
            playAgainText={onLeave ? 'Back to Lobby' : undefined}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
