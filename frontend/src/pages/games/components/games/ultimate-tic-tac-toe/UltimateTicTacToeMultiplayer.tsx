/**
 * Ultimate Tic-Tac-Toe Multiplayer VS — two human players over WebSocket.
 *
 * Reuses SubBoard and ultimateEngine.
 * Host plays X (goes first), guest plays O.
 * Moves are sent via WebSocket; both clients validate locally.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { SubBoard } from './SubBoard'
import {
  createBoards, createMetaBoard, makeMove, getValidMoves,
  type SubBoard as SubBoardType, type MetaCell, type Player,
} from './ultimateEngine'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'

interface UltimateTicTacToeMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  onLeave?: () => void
}

export function UltimateTicTacToeMultiplayer({ roomId, players, playerNames = {}, onLeave }: UltimateTicTacToeMultiplayerProps) {
  const { user } = useAuth()
  const song = useMemo(() => getSongForGame('ultimate-tic-tac-toe'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('ultimate-tic-tac-toe')

  // Host (first player) = X, guest = O
  const myMark: Player = players[0] === user?.id ? 'X' : 'O'
  const opponentMark: Player = myMark === 'X' ? 'O' : 'X'
  const myName = playerNames[user?.id ?? 0] || 'You'
  const opponentId = players.find(id => id !== user?.id)
  const opponentName = opponentId ? (playerNames[opponentId] || 'Opponent') : 'Opponent'

  const [boards, setBoards] = useState<SubBoardType[]>(createBoards)
  const [meta, setMeta] = useState<MetaCell[]>(createMetaBoard)
  const [activeBoard, setActiveBoard] = useState<number | null>(null)
  const [currentPlayer, setCurrentPlayer] = useState<Player>('X')
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const isMyTurn = currentPlayer === myMark

  // Refs to avoid re-subscribing the WS listener on every state change
  const boardsRef = useRef(boards)
  boardsRef.current = boards
  const metaRef = useRef(meta)
  metaRef.current = meta

  // Listen for opponent's moves — stable deps, reads state via refs
  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      const action = msg.action
      if (!action || action.type !== 'mark') return
      if (msg.playerId === user?.id) return

      const boardIndex = action.boardIndex as number
      const cellIndex = action.cellIndex as number
      const result = makeMove(boardsRef.current, metaRef.current, boardIndex, cellIndex, opponentMark)

      sfx.play('place')

      // Check if a sub-board was just won
      if (result.meta.some((m, i) => m !== null && metaRef.current[i] === null)) {
        sfx.play('board_won')
      }

      setBoards(result.boards)
      setMeta(result.meta)

      if (result.winner) {
        setActiveBoard(null)
        setGameStatus('lost')
        return
      }
      if (result.isDraw) {
        setActiveBoard(null)
        setGameStatus('draw')
        return
      }
      setActiveBoard(result.nextActiveBoard)
      setCurrentPlayer(myMark)
    })
    return unsub
  }, [roomId, myMark, opponentMark, sfx, user?.id])

  const handleCellClick = useCallback((boardIndex: number, cellIndex: number) => {
    if (gameStatus !== 'playing' || !isMyTurn) return

    const validMoves = getValidMoves(boards, meta, activeBoard)
    if (!validMoves.some(([b, c]) => b === boardIndex && c === cellIndex)) return

    music.init()
    sfx.init()
    music.start()

    const result = makeMove(boards, meta, boardIndex, cellIndex, myMark)

    sfx.play('place')

    // Check if a sub-board was just won
    if (result.meta.some((m, i) => m !== null && meta[i] === null)) {
      sfx.play('board_won')
    }

    setBoards(result.boards)
    setMeta(result.meta)

    // Send move to opponent
    gameSocket.sendAction(roomId, { type: 'mark', boardIndex, cellIndex })

    if (result.winner) {
      sfx.play('win')
      setActiveBoard(null)
      setGameStatus('won')
      return
    }
    if (result.isDraw) {
      setActiveBoard(null)
      setGameStatus('draw')
      return
    }
    setActiveBoard(result.nextActiveBoard)
    setCurrentPlayer(opponentMark)
  }, [boards, meta, activeBoard, gameStatus, isMyTurn, myMark, opponentMark, roomId, music, sfx])

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
    <GameLayout title="Ultimate Tic-Tac-Toe — VS" controls={controls}>
      <div className="relative flex flex-col items-center space-y-2">
        <p className="text-sm text-slate-400">{gameStatus === 'playing' ? turnLabel : ''}</p>

        <div className="grid grid-cols-3 gap-1.5 sm:gap-2 p-2 bg-slate-800 rounded-xl">
          {boards.map((subBoard, bi) => (
            <SubBoard
              key={bi}
              board={subBoard}
              boardIndex={bi}
              metaStatus={meta[bi]}
              isActive={activeBoard === null || activeBoard === bi}
              onCellClick={(_, cellIndex) => handleCellClick(bi, cellIndex)}
              disabled={gameStatus !== 'playing' || !isMyTurn || (activeBoard !== null && activeBoard !== bi) || meta[bi] !== null}
            />
          ))}
        </div>

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
