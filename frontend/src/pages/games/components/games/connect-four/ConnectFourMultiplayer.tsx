/**
 * Connect Four Multiplayer VS — two human players over WebSocket.
 *
 * Reuses ConnectFourBoard and connectFourEngine.
 * Host plays Red (goes first), guest plays Yellow.
 * Moves are sent via WebSocket; both clients validate locally.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { ConnectFourBoard } from './ConnectFourBoard'
import {
  createBoard, dropDisc, checkWinner, getValidColumns, isBoardFull,
  type Board, type Player, type WinResult,
} from './connectFourEngine'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'

interface ConnectFourMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  onLeave?: () => void
}

export function ConnectFourMultiplayer({ roomId, players, playerNames = {}, onLeave }: ConnectFourMultiplayerProps) {
  const { user } = useAuth()
  const song = useMemo(() => getSongForGame('connect-four'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('connect-four')

  // Host (first player) = red, guest = yellow
  const myColor: Player = players[0] === user?.id ? 'red' : 'yellow'
  const opponentColor: Player = myColor === 'red' ? 'yellow' : 'red'
  const myName = playerNames[user?.id ?? 0] || 'You'
  const opponentId = players.find(id => id !== user?.id)
  const opponentName = opponentId ? (playerNames[opponentId] || 'Opponent') : 'Opponent'

  const [board, setBoard] = useState<Board>(createBoard)
  const [currentPlayer, setCurrentPlayer] = useState<Player>('red')
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [winResult, setWinResult] = useState<WinResult | null>(null)
  const [hoverCol, setHoverCol] = useState<number | null>(null)
  const [droppingDisc, setDroppingDisc] = useState<{ row: number; col: number; player: Player } | null>(null)
  const isMyTurn = currentPlayer === myColor

  // Ref to avoid re-subscribing the WS listener on every board change
  const boardRef = useRef(board)
  boardRef.current = board

  // Listen for opponent's moves — stable deps, reads board via ref
  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      const action = msg.action
      if (!action || action.type !== 'drop') return
      if (msg.playerId === user?.id) return

      const col = action.col as number
      const { board: newBoard, row } = dropDisc(boardRef.current, col, opponentColor)
      if (row === -1) return

      sfx.play('drop')
      setDroppingDisc({ row, col, player: opponentColor })
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
      setCurrentPlayer(myColor)
    })
    return unsub
  }, [roomId, myColor, opponentColor, sfx, user?.id])

  const handleColumnClick = useCallback((col: number) => {
    if (gameStatus !== 'playing' || !isMyTurn) return
    if (!getValidColumns(board).includes(col)) return

    music.init()
    sfx.init()
    music.start()

    const { board: newBoard, row } = dropDisc(board, col, myColor)
    if (row === -1) return

    sfx.play('drop')
    setDroppingDisc({ row, col, player: myColor })
    setBoard(newBoard)

    // Send move to opponent
    gameSocket.sendAction(roomId, { type: 'drop', col })

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
    setCurrentPlayer(opponentColor)
  }, [board, gameStatus, isMyTurn, myColor, opponentColor, roomId, music, sfx])

  const turnLabel = isMyTurn
    ? `${myName}'s turn (${myColor === 'red' ? 'Red' : 'Yellow'})`
    : `${opponentName}'s turn (${opponentColor === 'red' ? 'Red' : 'Yellow'})`

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
        <span className={`text-xs font-medium ${myColor === 'red' ? 'text-red-400' : 'text-yellow-400'}`}>
          {myName}: {myColor === 'red' ? 'Red' : 'Yellow'}
        </span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Connect Four — VS" controls={controls}>
      <div
        className="relative flex flex-col items-center space-y-2"
        onMouseMove={(e) => {
          if (!isMyTurn) return
          const rect = e.currentTarget.getBoundingClientRect()
          const x = e.clientX - rect.left
          const colWidth = rect.width / 7
          setHoverCol(Math.min(6, Math.floor(x / colWidth)))
        }}
        onMouseLeave={() => setHoverCol(null)}
      >
        <p className="text-sm text-slate-400">{gameStatus === 'playing' ? turnLabel : ''}</p>

        <ConnectFourBoard
          board={board}
          winResult={winResult}
          onColumnClick={handleColumnClick}
          disabled={gameStatus !== 'playing' || !isMyTurn}
          hoverCol={isMyTurn ? hoverCol : null}
          currentPlayer={currentPlayer}
          droppingDisc={droppingDisc}
          onDropComplete={() => setDroppingDisc(null)}
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
