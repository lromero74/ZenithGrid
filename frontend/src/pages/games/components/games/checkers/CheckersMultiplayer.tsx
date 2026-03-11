/**
 * Checkers Multiplayer VS — two human players over WebSocket.
 *
 * Reuses CheckersBoard and checkersEngine.
 * Host plays red (goes first), guest plays black.
 * Each individual hop is sent as a move action so both clients
 * stay in sync. After a capture, both sides check if the same
 * player can continue jumping; if not, the turn switches.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CheckersBoard } from './CheckersBoard'
import {
  createBoard, applyMove, promoteKings, checkGameOver,
  getAllMoves, getCaptureMoves,
  type Board, type Move, type Player,
} from './checkersEngine'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'

interface CheckersMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  onLeave?: () => void
}

export function CheckersMultiplayer({ roomId, players, playerNames = {}, onLeave }: CheckersMultiplayerProps) {
  const { user } = useAuth()
  const song = useMemo(() => getSongForGame('checkers'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('checkers')

  // Host (first player) = red, guest = black
  const myColor: Player = players[0] === user?.id ? 'red' : 'black'
  const opponentColor: Player = myColor === 'red' ? 'black' : 'red'
  const myName = playerNames[user?.id ?? 0] || 'You'
  const opponentId = players.find(id => id !== user?.id)
  const opponentName = opponentId ? (playerNames[opponentId] || 'Opponent') : 'Opponent'

  const [board, setBoard] = useState<Board>(createBoard)
  const [currentPlayer, setCurrentPlayer] = useState<Player>('red')
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [selectedPiece, setSelectedPiece] = useState<[number, number] | null>(null)
  const [validMoves, setValidMoves] = useState<Move[]>([])
  const [lastMove, setLastMove] = useState<Move | null>(null)
  // Track if current player is mid-multijump (must continue with same piece)
  const [multiJumpPiece, setMultiJumpPiece] = useState<[number, number] | null>(null)

  const isMyTurn = currentPlayer === myColor
  const boardRef = useRef(board)
  boardRef.current = board
  const currentPlayerRef = useRef(currentPlayer)
  currentPlayerRef.current = currentPlayer

  /** After a move lands, check continuation / game-over / turn switch. */
  const finishMove = useCallback((newBoard: Board, move: Move, _mover: Player): {
    board: Board; continues: boolean; status: GameStatus
  } => {
    // Check multi-jump continuation
    if (move.captures.length > 0) {
      const further = getCaptureMoves(newBoard, move.to[0], move.to[1])
      if (further.length > 0) {
        return { board: newBoard, continues: true, status: 'playing' }
      }
    }

    // No more jumps — promote kings and check game over
    const promoted = promoteKings(newBoard)
    const winner = checkGameOver(promoted)
    let status: GameStatus = 'playing'
    if (winner) {
      status = winner === myColor ? 'won' : 'lost'
    }
    return { board: promoted, continues: false, status }
  }, [myColor])

  // Listen for opponent's moves
  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      const action = msg.action
      if (!action || action.type !== 'move') return
      if (msg.playerId === user?.id) return

      const from: [number, number] = [action.from[0], action.from[1]]
      const to: [number, number] = [action.to[0], action.to[1]]

      // Build move from the action
      const allMoves = getAllMoves(boardRef.current, opponentColor)
      const move = allMoves.find(
        m => m.from[0] === from[0] && m.from[1] === from[1] &&
             m.to[0] === to[0] && m.to[1] === to[1]
      )
      if (!move) return

      let newBoard = applyMove(boardRef.current, move)
      if (move.captures.length > 0) { sfx.play('jump') } else { sfx.play('move') }

      const result = finishMove(newBoard, move, opponentColor)
      newBoard = result.board

      setBoard(newBoard)
      setLastMove(move)

      if (result.status !== 'playing') {
        setGameStatus(result.status)
        return
      }

      if (result.continues) {
        // Opponent continues jumping — still their turn
        setMultiJumpPiece(move.to)
      } else {
        setMultiJumpPiece(null)
        setCurrentPlayer(myColor)
      }
    })
    return unsub
  }, [roomId, myColor, opponentColor, sfx, user?.id, finishMove])

  /** Get legal moves for a piece, respecting mandatory capture and multi-jump rules. */
  const getMovesForPiece = useCallback((currentBoard: Board, r: number, c: number, player: Player): Move[] => {
    const allPlayerMoves = getAllMoves(currentBoard, player)
    return allPlayerMoves.filter(m => m.from[0] === r && m.from[1] === c)
  }, [])

  const handleSquareClick = useCallback((r: number, c: number) => {
    if (gameStatus !== 'playing' || !isMyTurn) return

    music.init()
    sfx.init()
    music.start()

    const piece = board[r][c]

    // If mid-multijump, can only continue with that piece
    if (multiJumpPiece) {
      // Only accept clicks on valid targets for the jumping piece
      const move = validMoves.find(m => m.to[0] === r && m.to[1] === c)
      if (move) {
        let newBoard = applyMove(board, move)
        sfx.play('jump')
        gameSocket.sendAction(roomId, { type: 'move', from: move.from, to: move.to })

        const result = finishMove(newBoard, move, myColor)
        newBoard = result.board
        setBoard(newBoard)
        setLastMove(move)

        if (result.status !== 'playing') {
          setGameStatus(result.status)
          setSelectedPiece(null)
          setValidMoves([])
          setMultiJumpPiece(null)
          return
        }

        if (result.continues) {
          // Continue jumping
          const further = getCaptureMoves(newBoard, move.to[0], move.to[1])
          setMultiJumpPiece(move.to)
          setSelectedPiece(move.to)
          setValidMoves(further)
        } else {
          setMultiJumpPiece(null)
          setSelectedPiece(null)
          setValidMoves([])
          setCurrentPlayer(opponentColor)
        }
      }
      return
    }

    // Click own piece to select
    if (piece && piece.player === myColor) {
      const moves = getMovesForPiece(board, r, c, myColor)
      if (moves.length > 0) {
        setSelectedPiece([r, c])
        setValidMoves(moves)
      }
      return
    }

    // Click valid target to move
    if (selectedPiece) {
      const move = validMoves.find(m => m.to[0] === r && m.to[1] === c)
      if (move) {
        let newBoard = applyMove(board, move)
        if (move.captures.length > 0) { sfx.play('jump') } else { sfx.play('move') }
        gameSocket.sendAction(roomId, { type: 'move', from: move.from, to: move.to })

        const result = finishMove(newBoard, move, myColor)
        newBoard = result.board
        setBoard(newBoard)
        setLastMove(move)

        if (result.status !== 'playing') {
          setGameStatus(result.status)
          setSelectedPiece(null)
          setValidMoves([])
          setMultiJumpPiece(null)
          return
        }

        if (result.continues) {
          const further = getCaptureMoves(newBoard, move.to[0], move.to[1])
          setMultiJumpPiece(move.to)
          setSelectedPiece(move.to)
          setValidMoves(further)
        } else {
          setMultiJumpPiece(null)
          setSelectedPiece(null)
          setValidMoves([])
          setCurrentPlayer(opponentColor)
        }
      } else {
        // Clicked invalid square — deselect
        setSelectedPiece(null)
        setValidMoves([])
      }
    }
  }, [board, gameStatus, isMyTurn, myColor, opponentColor, selectedPiece, validMoves,
      multiJumpPiece, roomId, music, sfx, getMovesForPiece, finishMove])

  // Auto-select the multi-jump piece when it becomes our turn to continue
  useEffect(() => {
    if (!isMyTurn || !multiJumpPiece || gameStatus !== 'playing') return
    const captures = getCaptureMoves(board, multiJumpPiece[0], multiJumpPiece[1])
    if (captures.length > 0) {
      setSelectedPiece(multiJumpPiece)
      setValidMoves(captures)
    }
  }, [isMyTurn, multiJumpPiece, board, gameStatus])

  const turnLabel = isMyTurn
    ? `${myName}'s turn (${myColor === 'red' ? 'Red' : 'Black'})`
    : `${opponentName}'s turn (${opponentColor === 'red' ? 'Red' : 'Black'})`

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
        <span className={`text-xs font-medium ${myColor === 'red' ? 'text-red-400' : 'text-slate-300'}`}>
          {myName}: {myColor === 'red' ? 'Red' : 'Black'}
        </span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Checkers — VS" controls={controls}>
      <div className="relative flex flex-col items-center space-y-2">
        <p className="text-sm text-slate-400">
          {gameStatus === 'playing' ? turnLabel : ''}
          {gameStatus === 'playing' && multiJumpPiece && isMyTurn ? ' (continue jumping!)' : ''}
        </p>

        <CheckersBoard
          board={board}
          selectedPiece={selectedPiece}
          validMoves={validMoves}
          onSquareClick={handleSquareClick}
          disabled={gameStatus !== 'playing' || !isMyTurn}
          lastMove={lastMove}
        />

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
