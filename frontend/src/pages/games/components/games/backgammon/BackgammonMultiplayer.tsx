/**
 * Backgammon Multiplayer VS -- two human players over WebSocket.
 *
 * Host plays White (goes first), guest plays Brown.
 * HOST-AUTHORITATIVE dice rolling: the host calls rollDice() for both
 * players and broadcasts the result so both clients see identical dice.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { BackgammonBoard } from './BackgammonBoard'
import {
  createBoard, rollDice, applyMove, getFilteredMoves, hasValidMoves, checkWin,
  type BackgammonState, type Player,
} from './backgammonEngine'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'

interface BackgammonMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  onLeave?: () => void
}

export function BackgammonMultiplayer({ roomId, players, playerNames = {}, onLeave }: BackgammonMultiplayerProps) {
  const { user } = useAuth()
  const song = useMemo(() => getSongForGame('backgammon'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('backgammon')

  // Host (first player) = white, guest = brown
  const isHost = players[0] === user?.id
  const myColor: Player = isHost ? 'white' : 'brown'
  const myName = playerNames[user?.id ?? 0] || 'You'
  const opponentId = players.find(id => id !== user?.id)
  const opponentName = opponentId ? (playerNames[opponentId] || 'Opponent') : 'Opponent'

  const [gameState, setGameState] = useState<BackgammonState>(createBoard)
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [selectedPoint, setSelectedPoint] = useState<number | 'bar' | null>(null)
  const [validMoves, setValidMoves] = useState<{ from: number | 'bar'; to: number | 'off'; dieIndex: number }[]>([])
  const [autoPassMsg, setAutoPassMsg] = useState<string | null>(null)

  const isMyTurn = gameState.currentPlayer === myColor
  const gameStateRef = useRef(gameState)
  gameStateRef.current = gameState
  const gameStatusRef = useRef(gameStatus)
  gameStatusRef.current = gameStatus

  // -- Helpers ---------------------------------------------------------------

  const finishTurn = useCallback((state: BackgammonState): BackgammonState => {
    const winner = checkWin(state)
    if (winner) {
      const status: GameStatus = winner === myColor ? 'won' : 'lost'
      setGameStatus(status)
      setGameState({ ...state, gamePhase: 'gameOver' })
      return { ...state, gamePhase: 'gameOver' }
    }

    const nextPlayer: Player = state.currentPlayer === 'white' ? 'brown' : 'white'
    const nextState: BackgammonState = {
      ...state,
      currentPlayer: nextPlayer,
      gamePhase: 'rolling',
      dice: [],
      usedDice: [],
    }
    setGameState(nextState)
    setSelectedPoint(null)
    setValidMoves([])
    return nextState
  }, [myColor])

  const applyDiceToState = useCallback((state: BackgammonState, dice: number[]): BackgammonState => {
    const newState: BackgammonState = {
      ...state,
      dice,
      usedDice: dice.map(() => false),
      gamePhase: 'moving',
    }

    if (!hasValidMoves(newState)) {
      // No valid moves -- auto-pass
      const who = newState.currentPlayer === myColor ? 'You have' : `${opponentName} has`
      setAutoPassMsg(`${who} no valid moves -- passing turn.`)
      setTimeout(() => setAutoPassMsg(null), 1500)
      // Use a timeout so the dice are briefly visible before passing
      setTimeout(() => {
        finishTurn(newState)
      }, 1200)
      // Still set the dice state so they are displayed briefly
      setGameState(newState)
      return newState
    }

    setGameState(newState)
    setSelectedPoint(null)
    setValidMoves([])
    return newState
  }, [myColor, opponentName, finishTurn])

  // -- Roll dice (host-authoritative) ----------------------------------------

  const handleRoll = useCallback(() => {
    if (gameStatusRef.current !== 'playing') return
    const state = gameStateRef.current
    if (state.gamePhase !== 'rolling') return

    // Only the host actually rolls dice
    if (!isHost) return

    music.init()
    sfx.init()
    music.start()

    const dice = rollDice()
    sfx.play('roll')

    // Broadcast the roll to both clients
    gameSocket.sendAction(roomId, { type: 'roll', dice })

    // Apply locally
    applyDiceToState(state, dice)
  }, [isHost, roomId, music, sfx, applyDiceToState])

  // -- Handle point click (select source or destination) ---------------------

  const handlePointClick = useCallback((point: number | 'bar') => {
    if (gameStatus !== 'playing' || !isMyTurn || gameState.gamePhase !== 'moving') return

    music.init()
    sfx.init()
    music.start()

    const allMoves = getFilteredMoves(gameState)

    // If a point is already selected, try to execute a move
    if (selectedPoint !== null) {
      const move = allMoves.find(m => m.from === selectedPoint && m.to === point)
      if (move) {
        const newState = applyMove(gameState, move.from, move.to, move.dieIndex)
        sfx.play('move')

        // Broadcast the move
        gameSocket.sendAction(roomId, { type: 'move', from: move.from, to: move.to, dieIndex: move.dieIndex })

        // Check if turn is over
        if (!hasValidMoves(newState)) {
          finishTurn(newState)
        } else {
          setGameState(newState)
          setSelectedPoint(null)
          setValidMoves([])
        }
        return
      }
    }

    // Select as source if it has valid moves from here
    const movesFromPoint = allMoves.filter(m => m.from === point)
    if (movesFromPoint.length > 0) {
      setSelectedPoint(point)
      setValidMoves(movesFromPoint)
      return
    }

    // Deselect
    setSelectedPoint(null)
    setValidMoves([])
  }, [gameState, gameStatus, isMyTurn, selectedPoint, roomId, music, sfx, finishTurn])

  // -- Handle bear-off -------------------------------------------------------

  const handleBearOff = useCallback(() => {
    if (selectedPoint === null || gameStatus !== 'playing' || !isMyTurn) return

    const allMoves = getFilteredMoves(gameState)
    const move = allMoves.find(m => m.from === selectedPoint && m.to === 'off')
    if (!move) return

    const newState = applyMove(gameState, move.from, 'off', move.dieIndex)

    // Broadcast the bear-off move
    gameSocket.sendAction(roomId, { type: 'move', from: move.from, to: 'off', dieIndex: move.dieIndex })

    if (!hasValidMoves(newState)) {
      finishTurn(newState)
    } else {
      setGameState(newState)
      setSelectedPoint(null)
      setValidMoves([])
    }
  }, [gameState, gameStatus, isMyTurn, selectedPoint, roomId, finishTurn])

  // -- Listen for opponent actions -------------------------------------------

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      const action = msg.action
      if (!action) return
      if (msg.playerId === user?.id) return

      const state = gameStateRef.current
      if (gameStatusRef.current !== 'playing') return

      if (action.type === 'roll') {
        const dice = action.dice as number[]
        sfx.play('roll')
        applyDiceToState(state, dice)
        return
      }

      if (action.type === 'move') {
        const from = action.from as number | 'bar'
        const to = action.to as number | 'off'
        const dieIndex = action.dieIndex as number
        const newState = applyMove(state, from, to, dieIndex)
        sfx.play('move')

        if (!hasValidMoves(newState)) {
          finishTurn(newState)
        } else {
          setGameState(newState)
          setSelectedPoint(null)
          setValidMoves([])
        }
      }
    })
    return unsub
  }, [roomId, user?.id, sfx, applyDiceToState, finishTurn])

  // -- When it's the guest's turn to roll, host auto-rolls for them ----------
  // The guest sees "Roll Dice" which triggers host to roll. But to keep it
  // simple: if it's the host, and it's the opponent's rolling phase, the host
  // doesn't auto-roll -- the guest clicks "Roll Dice" which sends a request.
  // Actually, the spec says the current player clicks Roll Dice. For the host's
  // turn, host rolls. For the guest's turn, the guest clicks Roll which tells
  // the host to roll.
  //
  // Simpler approach: both players see the Roll button on their own turn.
  // When the guest clicks Roll, send a 'requestRoll' action to the host.
  // The host receives it and performs the roll.

  const handleGuestRollRequest = useCallback(() => {
    if (gameStatusRef.current !== 'playing') return
    const state = gameStateRef.current
    if (state.gamePhase !== 'rolling' || state.currentPlayer !== myColor) return

    music.init()
    sfx.init()
    music.start()

    if (isHost) {
      // Host rolls directly
      handleRoll()
    } else {
      // Guest asks host to roll
      gameSocket.sendAction(roomId, { type: 'requestRoll' })
    }
  }, [isHost, myColor, roomId, music, sfx, handleRoll])

  // Host listens for guest roll requests
  useEffect(() => {
    if (!isHost) return

    const unsub = gameSocket.on('game:action', (msg) => {
      const action = msg.action
      if (!action || action.type !== 'requestRoll') return
      if (msg.playerId === user?.id) return

      // Host performs the roll for the guest's turn
      const state = gameStateRef.current
      if (gameStatusRef.current !== 'playing' || state.gamePhase !== 'rolling') return

      const dice = rollDice()
      sfx.play('roll')
      gameSocket.sendAction(roomId, { type: 'roll', dice })
      applyDiceToState(state, dice)
    })
    return unsub
  }, [isHost, roomId, user?.id, sfx, applyDiceToState])

  // -- Status message --------------------------------------------------------

  const statusMessage = (() => {
    if (autoPassMsg) return autoPassMsg
    if (gameStatus !== 'playing') return ''
    if (gameState.gamePhase === 'rolling') {
      return isMyTurn ? 'Your turn -- roll the dice!' : `${opponentName} is rolling...`
    }
    if (gameState.gamePhase === 'moving') {
      if (isMyTurn) {
        return selectedPoint !== null ? 'Select destination' : 'Select a checker to move'
      }
      return `${opponentName} is moving...`
    }
    return ''
  })()

  const disabled = gameStatus !== 'playing' || !isMyTurn || gameState.gamePhase !== 'moving'

  // -- Render ----------------------------------------------------------------

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
        <span className={`text-xs font-medium ${myColor === 'white' ? 'text-slate-200' : 'text-amber-600'}`}>
          {myName}: {myColor === 'white' ? 'White' : 'Brown'}
        </span>
      </div>
      <div className="flex items-center gap-2">
        {isMyTurn && gameState.gamePhase === 'rolling' && gameStatus === 'playing' && (
          <button
            onClick={handleGuestRollRequest}
            className="px-3 py-1 bg-emerald-700 hover:bg-emerald-600 text-white rounded text-sm font-medium transition-colors"
          >
            Roll Dice
          </button>
        )}
        {!isMyTurn && gameState.gamePhase === 'rolling' && gameStatus === 'playing' && (
          <p className="text-sm text-slate-400">{opponentName} is rolling...</p>
        )}
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Backgammon — VS" controls={controls}>
      <div className="relative flex flex-col items-center space-y-2">
        <p className="text-sm text-slate-400">{statusMessage}</p>

        {/* Dice display */}
        {gameState.dice.length > 0 && (
          <div className="flex gap-2">
            {gameState.dice.map((d, i) => (
              <div
                key={i}
                className={`w-8 h-8 flex items-center justify-center rounded bg-white text-black font-bold ${
                  gameState.usedDice[i] ? 'opacity-30' : ''
                }`}
              >
                {d}
              </div>
            ))}
          </div>
        )}

        <BackgammonBoard
          state={gameState}
          validMoves={validMoves}
          selectedPoint={selectedPoint}
          onPointClick={handlePointClick}
          onBearOff={handleBearOff}
          disabled={disabled}
        />

        {(gameStatus === 'won' || gameStatus === 'lost') && (
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
