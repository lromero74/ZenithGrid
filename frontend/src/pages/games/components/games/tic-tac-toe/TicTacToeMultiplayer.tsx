/**
 * Tic-Tac-Toe Multiplayer VS — two human players over WebSocket.
 *
 * Reuses TicTacToeBoard and ticTacToeEngine.
 * Host plays X (goes first), guest plays O.
 * Moves are sent via WebSocket; both clients validate locally.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { TicTacToeBoard } from './TicTacToeBoard'
import {
  createBoard,
  checkWinner,
  isBoardFull,
  type Board,
  type Player,
  type WinResult,
} from './ticTacToeEngine'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'

interface TicTacToeMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  onLeave?: () => void
}

export function TicTacToeMultiplayer({ roomId, players, playerNames = {}, onLeave }: TicTacToeMultiplayerProps) {
  const { user } = useAuth()
  const song = useMemo(() => getSongForGame('tic-tac-toe'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('tic-tac-toe')

  // Host (first player) = X, guest = O
  const myMark: Player = players[0] === user?.id ? 'X' : 'O'
  const opponentMark: Player = myMark === 'X' ? 'O' : 'X'
  const myName = playerNames[user?.id ?? 0] || 'You'
  const opponentId = players.find(id => id !== user?.id)
  const opponentName = opponentId ? (playerNames[opponentId] || 'Opponent') : 'Opponent'

  const [board, setBoard] = useState<Board>(createBoard)
  const [currentPlayer, setCurrentPlayer] = useState<Player>('X')
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [winResult, setWinResult] = useState<WinResult | null>(null)
  const isMyTurn = currentPlayer === myMark

  // Ref to avoid re-subscribing the WS listener on every board change
  const boardRef = useRef(board)
  boardRef.current = board

  // Listen for opponent's moves — stable deps, reads board via ref
  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      const action = msg.action
      if (!action || action.type !== 'mark') return
      if (msg.playerId === user?.id) return

      const index = action.index as number
      const currentBoard = boardRef.current
      if (index < 0 || index > 8 || currentBoard[index] !== null) return

      sfx.play('place')
      const newBoard = [...currentBoard]
      newBoard[index] = opponentMark
      setBoard(newBoard)

      const winner = checkWinner(newBoard)
      if (winner) {
        setWinResult(winner)
        setGameStatus('lost')
        return
      }
      if (isBoardFull(newBoard)) {
        setGameStatus('draw')
        return
      }
      setCurrentPlayer(myMark)
    })
    return unsub
  }, [roomId, myMark, opponentMark, sfx, user?.id])

  const handleCellClick = useCallback((index: number) => {
    if (gameStatus !== 'playing' || !isMyTurn) return
    if (board[index] !== null) return

    music.init()
    sfx.init()
    music.start()

    sfx.play('place')
    const newBoard = [...board]
    newBoard[index] = myMark
    setBoard(newBoard)

    // Send move to opponent
    gameSocket.sendAction(roomId, { type: 'mark', index })

    const winner = checkWinner(newBoard)
    if (winner) {
      setWinResult(winner)
      setGameStatus('won')
      return
    }
    if (isBoardFull(newBoard)) {
      setGameStatus('draw')
      return
    }
    setCurrentPlayer(opponentMark)
  }, [board, gameStatus, isMyTurn, myMark, opponentMark, roomId, music, sfx])

  const turnLabel = isMyTurn
    ? `${myName}'s turn (${myMark})`
    : `${opponentName}'s turn (${opponentMark})`

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
        <span className={`text-xs font-medium ${myMark === 'X' ? 'text-blue-400' : 'text-red-400'}`}>
          {myName}: {myMark}
        </span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Tic-Tac-Toe — VS" controls={controls}>
      <div className="relative flex flex-col items-center space-y-2">
        <p className="text-sm text-slate-400">{gameStatus === 'playing' ? turnLabel : ''}</p>

        <TicTacToeBoard
          board={board}
          winResult={winResult}
          onCellClick={handleCellClick}
          disabled={gameStatus !== 'playing' || !isMyTurn}
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
