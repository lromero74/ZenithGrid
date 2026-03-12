/**
 * Blackjack VS — two human players at the same table.
 *
 * Host owns the shoe and dealer logic, broadcasting authoritative state.
 * Guest sends action intents via game:action and receives state_sync.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE } from '../../PlayingCard'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
import {
  createVsGame, vsPlaceBet, vsBothBetsPlaced, vsDeal,
  vsHit, vsStand, vsDoubleDown, vsSplit,
  vsDealerStep, vsDealerMustHit, vsNewRound,
  vsIsGameOver, vsGetWinner, vsCanSplit, vsCanDoubleDown,
  scoreHand, BET_SIZES,
  type VsBlackjackState, type Difficulty,
} from './blackjackVsEngine'

// ── Component ────────────────────────────────────────────────────────

interface BlackjackMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  difficulty?: string
  onLeave?: () => void
}

export function BlackjackMultiplayer({ roomId, players, playerNames = {}, difficulty, onLeave }: BlackjackMultiplayerProps) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myPlayerIndex = isHost ? 0 : 1

  const [gameState, setGameState] = useState<VsBlackjackState>(() =>
    createVsGame(
      (difficulty as Difficulty) || 'easy',
      players[0], playerNames[players[0]] ?? 'Player 1',
      players[1], playerNames[players[1]] ?? 'Player 2',
    )
  )
  const stateRef = useRef(gameState)
  stateRef.current = gameState

  const [selectedBet, setSelectedBet] = useState(BET_SIZES[0])
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')

  // Music & SFX
  const song = useMemo(() => getSongForGame('blackjack'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('blackjack')

  // ── Host: broadcast state after every change ─────────────────────

  const broadcastState = useCallback((state: VsBlackjackState) => {
    if (!isHost) return
    // Strip shoe — guest doesn't need it
    const { shoe: _shoe, ...rest } = state
    gameSocket.sendAction(roomId, {
      type: 'state_sync',
      state: { ...rest, shoe: [] },
    })
  }, [isHost, roomId])

  // Helper: host applies an action, updates state, and broadcasts
  const hostApply = useCallback((fn: (s: VsBlackjackState) => VsBlackjackState) => {
    setGameState(prev => {
      const next = fn(prev)
      broadcastState(next)
      return next
    })
  }, [broadcastState])

  // ── Action handlers ──────────────────────────────────────────────

  const handlePlaceBet = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('bet')

    if (isHost) {
      // Host places own bet, then checks if both ready
      setGameState(prev => {
        let next = vsPlaceBet(prev, 0, selectedBet)
        if (vsBothBetsPlaced(next)) {
          next = vsDeal(next)
          sfx.play('deal')
        }
        broadcastState(next)
        return next
      })
    } else {
      // Guest sends bet intent to host
      gameSocket.sendAction(roomId, { type: 'bet', amount: selectedBet })
      // Optimistic: mark own bet placed locally for UI feedback
      setGameState(prev => vsPlaceBet(prev, 1, selectedBet))
    }
  }, [isHost, selectedBet, roomId, broadcastState, music, sfx])

  const handleHit = useCallback(() => {
    sfx.play('hit')
    if (isHost) {
      hostApply(vsHit)
    } else {
      gameSocket.sendAction(roomId, { type: 'hit' })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handleStand = useCallback(() => {
    if (isHost) {
      hostApply(vsStand)
    } else {
      gameSocket.sendAction(roomId, { type: 'stand' })
    }
  }, [isHost, roomId, hostApply])

  const handleDouble = useCallback(() => {
    if (isHost) {
      hostApply(vsDoubleDown)
    } else {
      gameSocket.sendAction(roomId, { type: 'double' })
    }
  }, [isHost, roomId, hostApply])

  const handleSplit = useCallback(() => {
    if (isHost) {
      hostApply(vsSplit)
    } else {
      gameSocket.sendAction(roomId, { type: 'split' })
    }
  }, [isHost, roomId, hostApply])

  const handleNextRound = useCallback(() => {
    if (isHost) {
      setGameState(prev => {
        const next = vsNewRound(prev)
        broadcastState(next)
        return next
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'next_round' })
    }
  }, [isHost, roomId, broadcastState])

  // ── WebSocket: listen for opponent actions ───────────────────────

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: { playerId?: number; action?: Record<string, unknown> }) => {
      if (msg.playerId === user?.id) return  // Ignore own echo
      const action = msg.action
      if (!action) return

      if (action.type === 'state_sync') {
        // Guest receives authoritative state from host
        if (!isHost) {
          const syncedState = action.state as VsBlackjackState
          setGameState(syncedState)
          // Play SFX based on state
          if (syncedState.phase === 'payout') {
            sfx.play(syncedState.message.toLowerCase().includes('bust') ? 'bust' : 'deal')
          }
        }
        return
      }

      // Host processes guest actions
      if (isHost) {
        if (action.type === 'bet') {
          setGameState(prev => {
            let next = vsPlaceBet(prev, 1, action.amount as number)
            if (vsBothBetsPlaced(next)) {
              next = vsDeal(next)
              sfx.play('deal')
            }
            broadcastState(next)
            return next
          })
        } else if (action.type === 'hit') {
          sfx.play('hit')
          hostApply(vsHit)
        } else if (action.type === 'stand') {
          hostApply(vsStand)
        } else if (action.type === 'double') {
          hostApply(vsDoubleDown)
        } else if (action.type === 'split') {
          hostApply(vsSplit)
        } else if (action.type === 'next_round') {
          setGameState(prev => {
            const next = vsNewRound(prev)
            broadcastState(next)
            return next
          })
        }
      }
    })
    return unsub
  }, [roomId, isHost, user?.id, broadcastState, hostApply, sfx])

  // ── Dealer timer (host only) ─────────────────────────────────────

  useEffect(() => {
    if (!isHost) return
    if (gameState.phase !== 'dealerTurn') return

    const delay = vsDealerMustHit(gameState) ? 800 : 600
    const timer = setTimeout(() => {
      setGameState(prev => {
        const next = vsDealerStep(prev)
        broadcastState(next)
        if (next.phase === 'payout') {
          sfx.play(next.message.toLowerCase().includes('bust') ? 'bust' : 'deal')
        }
        return next
      })
    }, delay)
    return () => clearTimeout(timer)
  }, [isHost, gameState.phase, gameState.dealerHand.length, broadcastState, sfx])

  // ── Game over detection ──────────────────────────────────────────

  useEffect(() => {
    if (vsIsGameOver(gameState)) {
      const winnerIdx = vsGetWinner(gameState)
      if (winnerIdx === myPlayerIndex) {
        setGameStatus('won')
      } else if (winnerIdx === null) {
        setGameStatus('draw')
      } else {
        setGameStatus('lost')
      }
    }
  }, [gameState, myPlayerIndex])

  // ── Derived state ────────────────────────────────────────────────

  const isMyTurn = gameState.phase === 'playerTurn' && gameState.activePlayerIndex === myPlayerIndex
  const myBetPlaced = gameState.betsPlaced[myPlayerIndex]
  const isBettingPhase = gameState.phase === 'betting'
  const myPlayer = gameState.players[myPlayerIndex]
  const opponentPlayer = gameState.players[myPlayerIndex === 0 ? 1 : 0]

  const dealerScore = gameState.phase === 'payout' || gameState.phase === 'dealerTurn'
    ? scoreHand(gameState.dealerHand)
    : scoreHand(gameState.dealerHand.filter(c => c.faceUp))

  // ── Render ───────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
        <span className="text-xs text-slate-400">
          {gameState.difficulty === 'hard' ? 'Hard' : 'Easy'}
        </span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Blackjack — VS" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-2 sm:space-y-4">

        {/* Dealer area */}
        <div className="text-center">
          <span className="text-[0.65rem] sm:text-xs text-slate-400 block">
            Dealer {dealerScore.total > 0 ? `(${dealerScore.total})` : ''}
          </span>
          <div className="text-[0.55rem] text-yellow-400">{gameState.dealerChips}</div>
          <div className="flex gap-1.5 sm:gap-2 justify-center min-h-[5rem] sm:min-h-[7rem]">
            {gameState.dealerHand.map((card, i) => (
              <div key={i} className={CARD_SIZE}>
                {card.faceUp ? <CardFace card={card} /> : <CardBack />}
              </div>
            ))}
          </div>
        </div>

        {/* Message area */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Both player hands side by side */}
        <div className="flex w-full gap-4 justify-center">
          {gameState.players.map((player, pIdx) => {
            const isActive = gameState.phase === 'playerTurn' && gameState.activePlayerIndex === pIdx
            const isMe = pIdx === myPlayerIndex
            return (
              <div key={pIdx} className={`flex-1 max-w-[12rem] text-center ${isActive ? '' : gameState.phase === 'playerTurn' ? 'opacity-50' : ''}`}>
                <div className={`text-xs font-medium mb-1 ${isMe ? 'text-blue-400' : 'text-slate-400'}`}>
                  {player.name} {isMe ? '(You)' : ''}
                </div>
                <div className="text-[0.55rem] text-yellow-400 mb-1">{player.chips} chips</div>

                {/* Bet placed indicator during betting */}
                {isBettingPhase && gameState.betsPlaced[pIdx] && (
                  <div className="text-[0.55rem] text-emerald-400 mb-1">Bet: {player.currentBet}</div>
                )}

                {/* Hands */}
                {player.hands.map((hand, hIdx) => {
                  const hScore = scoreHand(hand.cards)
                  const handActive = isActive && hIdx === player.activeHandIndex
                  return (
                    <div key={hIdx} className={`mb-2 ${handActive ? '' : player.hands.length > 1 ? 'opacity-60' : ''}`}>
                      {player.hands.length > 1 && (
                        <span className="text-[0.55rem] text-slate-500 block">
                          Hand {hIdx + 1} (Bet: {hand.bet})
                        </span>
                      )}
                      <div className="flex gap-1 justify-center flex-wrap">
                        {hand.cards.map((card, ci) => (
                          <div key={ci} className={`${CARD_SIZE} ${handActive ? 'ring-1 ring-blue-400/40 rounded-md' : ''}`}>
                            <CardFace card={card} />
                          </div>
                        ))}
                      </div>
                      {hand.cards.length > 0 && (
                        <div className="mt-0.5">
                          <span className="text-[0.55rem] text-slate-500">
                            ({hScore.total}{hScore.isSoft ? ' soft' : ''}{hScore.isBust ? ' BUST' : ''})
                          </span>
                          {gameState.phase === 'payout' && hand.result && (
                            <span className={`text-[0.55rem] font-medium ml-1 ${
                              hand.result === 'win' || hand.result === 'blackjack'
                                ? 'text-green-400'
                                : hand.result === 'lose' || hand.result === 'bust'
                                  ? 'text-red-400'
                                  : 'text-slate-400'
                            }`}>
                              {hand.result === 'blackjack' ? 'BJ!' : hand.result === 'win' ? `+${hand.bet}` : hand.result === 'bust' ? 'Bust' : hand.result === 'lose' ? `-${hand.bet}` : 'Push'}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })}
        </div>

        {/* Betting phase */}
        {isBettingPhase && !myBetPlaced && (
          <div className="flex flex-col items-center gap-2">
            <div className="flex gap-1.5">
              {BET_SIZES.map(bet => (
                <button
                  key={bet}
                  onClick={() => setSelectedBet(bet)}
                  disabled={bet > myPlayer.chips}
                  className={`px-2.5 py-1 text-xs rounded font-mono transition-colors ${
                    selectedBet === bet
                      ? 'bg-yellow-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  } disabled:opacity-30 disabled:cursor-not-allowed`}
                >
                  {bet}
                </button>
              ))}
            </div>
            <button
              onClick={handlePlaceBet}
              disabled={selectedBet > myPlayer.chips}
              className="px-5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
            >
              Deal ({selectedBet} chips)
            </button>
          </div>
        )}

        {isBettingPhase && myBetPlaced && (
          <p className="text-xs text-slate-400">Waiting for {opponentPlayer.name} to bet...</p>
        )}

        {/* Player turn actions */}
        {isMyTurn && (
          <div className="flex flex-wrap gap-1.5 justify-center">
            <button onClick={handleHit} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition-colors">
              Hit
            </button>
            <button onClick={handleStand} className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition-colors">
              Stand
            </button>
            {vsCanDoubleDown(gameState) && (
              <button onClick={handleDouble} className="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg text-sm transition-colors">
                Double
              </button>
            )}
            {vsCanSplit(gameState) && (
              <button onClick={handleSplit} className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm transition-colors">
                Split
              </button>
            )}
          </div>
        )}

        {/* Waiting for opponent's turn */}
        {gameState.phase === 'playerTurn' && !isMyTurn && (
          <p className="text-xs text-slate-400">
            {gameState.players[gameState.activePlayerIndex].name} is playing...
          </p>
        )}

        {/* Payout — next round */}
        {gameState.phase === 'payout' && !vsIsGameOver(gameState) && (
          <button
            onClick={handleNextRound}
            className="px-5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Next Hand
          </button>
        )}

        {/* Round indicator */}
        <div className="text-[0.55rem] text-slate-600">Round {gameState.roundNumber}</div>

        {/* Game over */}
        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            message={
              gameStatus === 'won'
                ? `You win! ${opponentPlayer.name} is out of chips.`
                : gameStatus === 'lost'
                  ? `${opponentPlayer.name} wins! You're out of chips.`
                  : 'Draw!'
            }
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
