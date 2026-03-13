/**
 * Euchre VS Multiplayer — 2 humans + 2 AI in a 4-player partnership game.
 *
 * Host-authoritative. Player 0 (host) = South, Player 1 (guest) = North.
 * Teams: Host(0) + Guest(1) vs AI-East(2) + AI-West(3).
 * 24-card deck, bowers, trump selection via two rounds. First to 10 wins.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi, ArrowLeft } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE_COMPACT, CARD_SLOT_V, CARD_SLOT_H } from '../../PlayingCard'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
import type { GameStatus } from '../../../types'
import { getSuitSymbol } from '../../../utils/cardUtils'
import type { Suit } from '../../../utils/cardUtils'
import {
  createEuchreGame,
  orderUp,
  pass,
  nameTrump,
  dealerDiscard,
  setGoingAlone,
  playCard,
  aiTrumpSelection,
  aiDealerDiscard,
  getPlayableCards,
  nextHand,
  PLAYER_NAMES as _PNAMES,
  TEAM_NAMES as _TNAMES,
  type EuchreState,
} from './EuchreEngine'

// ── Constants ────────────────────────────────────────────────────────

const AI_DELAY = 800
const SUIT_OPTIONS: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']

// In VS mode, seats: 0=host(South), 1=guest(North), 2=AI East, 3=AI West
// The engine uses 0-3 with teams 0,2 vs 1,3
// We need humans on the same team: team of player%2
// player 0 team=0, player 1 team=1, player 2 team=0, player 3 team=1
// So host(0)+AI-East(2) = team 0, guest(1)+AI-West(3) = team 1
// That's the same as the single-player mapping. Good.

// ── Props ────────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

// ── Component ────────────────────────────────────────────────────────

export function EuchreMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myPlayerIndex = isHost ? 0 : 1

  const song = useMemo(() => getSongForGame('euchre'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('euchre')

  const [gameState, setGameState] = useState<EuchreState>(() => createEuchreGame())
  const stateRef = useRef(gameState)
  stateRef.current = gameState

  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')

  const myName = playerNames[user?.id ?? 0] ?? 'You'
  const partnerName = playerNames[players[isHost ? 1 : 0]] ?? 'Partner'
  const myTeam = myPlayerIndex % 2

  // ── Broadcast ──────────────────────────────────────────────────

  const broadcastState = useCallback((state: EuchreState) => {
    if (!isHost) return
    const sanitized = {
      ...state,
      hands: state.hands.map((h, i) => i === 1 ? h : []),
    }
    gameSocket.sendAction(roomId, { type: 'state_sync', state: sanitized })
  }, [isHost, roomId])

  useEffect(() => {
    if (!isHost) return
    const state = createEuchreGame()
    setGameState(state)
    broadcastState(state)
  }, [isHost]) // eslint-disable-line react-hooks/exhaustive-deps

  const hostApply = useCallback((fn: (s: EuchreState) => EuchreState) => {
    setGameState(prev => {
      const next = fn(prev)
      broadcastState(next)
      return next
    })
  }, [broadcastState])

  // ── WebSocket ──────────────────────────────────────────────────

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: { playerId?: number; action?: Record<string, unknown> }) => {
      if (msg.playerId === user?.id) return
      const action = msg.action
      if (!action) return

      if (action.type === 'state_sync' && !isHost) {
        const synced = action.state as EuchreState
        setGameState(prev => ({
          ...synced,
          hands: synced.hands.map((h, i) => {
            if (i === 1 && h.length > 0) return h
            if (i === 1) return prev.hands[1]
            return h
          }),
        }))
        return
      }

      if (isHost) {
        if (action.type === 'order_up') {
          hostApply(s => orderUp(s))
        } else if (action.type === 'pass') {
          hostApply(s => {
            let next = pass(s)
            // Run AI trump selection if needed
            if (next.currentPlayer !== 0 && next.currentPlayer !== 1 &&
                (next.phase === 'trumpRound1' || next.phase === 'trumpRound2')) {
              next = aiTrumpSelection(next)
            }
            return next
          })
        } else if (action.type === 'name_trump') {
          hostApply(s => nameTrump(s, action.suit as Suit))
        } else if (action.type === 'go_alone') {
          hostApply(s => {
            let next = setGoingAlone(s, action.alone as boolean)
            if (next.phase === 'dealerDiscard' && next.currentPlayer !== 0 && next.currentPlayer !== 1) {
              next = aiDealerDiscard(next)
            }
            return next
          })
        } else if (action.type === 'dealer_discard') {
          hostApply(s => dealerDiscard(s, action.cardIndex as number))
        } else if (action.type === 'play_card') {
          hostApply(s => playCard(s, action.cardIndex as number))
        } else if (action.type === 'next_hand') {
          hostApply(s => nextHand(s))
        }
      }
    })
    return unsub
  }, [roomId, isHost, user?.id, hostApply])

  // ── AI turns (host only) ───────────────────────────────────────

  useEffect(() => {
    if (!isHost) return
    const cp = gameState.currentPlayer
    // Only run AI for players 2 and 3
    if (cp === 0 || cp === 1) return
    if (gameState.phase === 'gameOver' || gameState.phase === 'handOver') return

    const timer = setTimeout(() => {
      setGameState(prev => {
        if (prev.currentPlayer === 0 || prev.currentPlayer === 1) return prev

        let current = prev

        // Trump selection phases (including goAlonePrompt)
        if (current.phase === 'trumpRound1' || current.phase === 'trumpRound2' || current.phase === 'goAlonePrompt') {
          current = aiTrumpSelection(current)
          if (current.phase === 'dealerDiscard' && current.currentPlayer !== 0 && current.currentPlayer !== 1) {
            current = aiDealerDiscard(current)
          }
          broadcastState(current)
          return current
        }

        // Dealer discard
        if (current.phase === 'dealerDiscard') {
          current = aiDealerDiscard(current)
          broadcastState(current)
          return current
        }

        // Playing
        if (current.phase === 'playing') {
          const hand = prev.hands[prev.currentPlayer]
          const playable = getPlayableCards(hand, prev.ledSuit, prev.trumpSuit!)
          if (playable.length > 0) {
            current = playCard(prev, playable[0])
          }

          // Continue AI turns
          while ((current.currentPlayer === 2 || current.currentPlayer === 3) && current.phase === 'playing') {
            const h = current.hands[current.currentPlayer]
            const p = getPlayableCards(h, current.ledSuit, current.trumpSuit!)
            if (p.length > 0) {
              current = playCard(current, p[0])
            } else {
              break
            }
          }

          broadcastState(current)
          return current
        }

        return current
      })
    }, AI_DELAY)
    return () => clearTimeout(timer)
  }, [isHost, gameState.currentPlayer, gameState.phase, gameState.currentTrick.length, broadcastState])

  // ── Game over ──────────────────────────────────────────────────

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const myTeamScore = gameState.teamScores[myTeam]
      const oppTeamScore = gameState.teamScores[myTeam === 0 ? 1 : 0]
      setGameStatus(myTeamScore >= oppTeamScore ? 'won' : 'lost')
    }
  }, [gameState.phase, gameState.teamScores, myTeam])

  // ── Handlers ───────────────────────────────────────────────────

  const handleOrderUp = useCallback(() => {
    music.init(); sfx.init(); music.start()
    sfx.play('place')
    if (isHost) {
      hostApply(s => orderUp(s))
    } else {
      gameSocket.sendAction(roomId, { type: 'order_up' })
    }
  }, [isHost, roomId, hostApply, music, sfx])

  const handleGoAlone = useCallback((alone: boolean) => {
    sfx.play('place')
    if (isHost) {
      hostApply(s => {
        let next = setGoingAlone(s, alone)
        if (next.phase === 'dealerDiscard' && next.currentPlayer !== 0 && next.currentPlayer !== 1) {
          next = aiDealerDiscard(next)
        }
        return next
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'go_alone', alone })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handlePass = useCallback(() => {
    music.init(); sfx.init(); music.start()
    if (isHost) {
      hostApply(s => {
        let next = pass(s)
        if (next.currentPlayer !== 0 && next.currentPlayer !== 1 &&
            (next.phase === 'trumpRound1' || next.phase === 'trumpRound2')) {
          next = aiTrumpSelection(next)
        }
        return next
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'pass' })
    }
  }, [isHost, roomId, hostApply, music, sfx])

  const handleNameTrump = useCallback((suit: Suit) => {
    sfx.play('place')
    if (isHost) {
      hostApply(s => nameTrump(s, suit))
    } else {
      gameSocket.sendAction(roomId, { type: 'name_trump', suit })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handleDealerDiscard = useCallback((cardIndex: number) => {
    sfx.play('place')
    if (isHost) {
      hostApply(s => dealerDiscard(s, cardIndex))
    } else {
      gameSocket.sendAction(roomId, { type: 'dealer_discard', cardIndex })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handlePlayCard = useCallback((cardIndex: number) => {
    sfx.play('place')
    if (isHost) {
      hostApply(s => playCard(s, cardIndex))
    } else {
      gameSocket.sendAction(roomId, { type: 'play_card', cardIndex })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handleNextHand = useCallback(() => {
    sfx.play('deal')
    if (isHost) {
      hostApply(s => nextHand(s))
    } else {
      gameSocket.sendAction(roomId, { type: 'next_hand' })
    }
  }, [isHost, roomId, hostApply, sfx])

  // ── Derived ────────────────────────────────────────────────────

  const isHumanTurn = gameState.currentPlayer === myPlayerIndex
  const isPlaying = gameState.phase === 'playing' && isHumanTurn
  const isTrumpRound1 = gameState.phase === 'trumpRound1' && isHumanTurn
  const isTrumpRound2 = gameState.phase === 'trumpRound2' && isHumanTurn
  const isGoAlonePrompt = gameState.phase === 'goAlonePrompt' && isHumanTurn
  const isDealerDiscard = gameState.phase === 'dealerDiscard' && isHumanTurn

  const myHand = gameState.hands[myPlayerIndex]
  const playableIndices = isPlaying
    ? getPlayableCards(myHand, gameState.ledSuit, gameState.trumpSuit!)
    : []

  const opponentIdx = myPlayerIndex === 0 ? 1 : 0

  // ── Render ─────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        {onLeave && (
          <button onClick={onLeave} className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors">
            <ArrowLeft className="w-3 h-3" /> Leave
          </button>
        )}
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
      </div>
      <div className="flex items-center gap-3 text-xs">
        <span className={myTeam === 0 ? 'text-blue-400' : 'text-red-400'}>
          Team 1: {gameState.teamScores[0]}
        </span>
        <span className={myTeam === 1 ? 'text-blue-400' : 'text-red-400'}>
          Team 2: {gameState.teamScores[1]}
        </span>
        {gameState.trumpSuit && (
          <span className="text-yellow-400">Trump: {getSuitSymbol(gameState.trumpSuit)}</span>
        )}
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Euchre -- VS" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* North (partner human or opponent AI depending on seating) */}
        <div className="text-center">
          <span className="text-xs text-slate-400">
            {opponentIdx === 1 ? partnerName : myName} ({gameState.hands[opponentIdx].length})
          </span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[opponentIdx].map((_, i) => (
              <div key={i} className={CARD_SLOT_V}><CardBack /></div>
            ))}
          </div>
        </div>

        {/* West + Trick + East */}
        <div className="flex w-full items-center gap-2">
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-slate-400">AI West ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>

          <div className="flex-1 relative h-36 sm:h-48">
            {/* Flipped card during trump selection / go-alone prompt */}
            {(gameState.phase === 'trumpRound1' || gameState.phase === 'trumpRound2' || gameState.phase === 'goAlonePrompt') && (
              <div className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 ${CARD_SIZE_COMPACT}`}>
                {gameState.phase === 'trumpRound1' ? (
                  <CardFace card={gameState.flippedCard} />
                ) : (
                  <CardBack />
                )}
              </div>
            )}

            {/* Trick cards */}
            {gameState.phase === 'playing' && gameState.currentTrick.map((play) => {
              const posMap: Record<number, string> = {
                [myPlayerIndex]: 'bottom-0 left-1/2 -translate-x-1/2',
                [opponentIdx]: 'top-0 left-1/2 -translate-x-1/2',
                2: 'right-0 top-1/2 -translate-y-1/2',
                3: 'left-0 top-1/2 -translate-y-1/2',
              }
              return (
                <div key={`${play.player}-${play.card.rank}-${play.card.suit}`}
                  className={`absolute ${posMap[play.player]} ${CARD_SIZE_COMPACT}`}
                >
                  <CardFace card={play.card} />
                </div>
              )
            })}

            {/* Trump indicator */}
            {gameState.phase === 'playing' && gameState.trumpSuit && gameState.currentTrick.length === 0 && (
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
                <span className="text-2xl">{getSuitSymbol(gameState.trumpSuit)}</span>
                <p className="text-[0.6rem] text-slate-500 mt-0.5">Trump</p>
                {gameState.goingAlone !== null && (
                  <p className="text-[0.6rem] text-amber-400 mt-0.5 font-medium">
                    {_PNAMES[gameState.goingAlone]} alone
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-slate-400">AI East ({gameState.hands[2].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[2].map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>
        </div>

        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Trump Round 1 */}
        {isTrumpRound1 && (
          <div className="flex gap-2">
            <button onClick={handleOrderUp} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors">
              Order Up ({getSuitSymbol(gameState.flippedCard.suit)})
            </button>
            <button onClick={handlePass} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium transition-colors">
              Pass
            </button>
          </div>
        )}

        {/* Trump Round 2 */}
        {isTrumpRound2 && (
          <div className="flex flex-col items-center gap-2">
            <span className="text-xs text-slate-400">
              Name trump (not {getSuitSymbol(gameState.flippedCard.suit)})
            </span>
            <div className="flex gap-2">
              {SUIT_OPTIONS.filter(s => s !== gameState.flippedCard.suit).map(suit => (
                <button
                  key={suit}
                  onClick={() => handleNameTrump(suit)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    suit === 'hearts' || suit === 'diamonds'
                      ? 'bg-red-700 hover:bg-red-600 text-white'
                      : 'bg-slate-700 hover:bg-slate-600 text-white'
                  }`}
                >
                  {getSuitSymbol(suit)} {suit}
                </button>
              ))}
            </div>
            {gameState.currentPlayer !== gameState.dealer && (
              <button onClick={handlePass} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium transition-colors">
                Pass
              </button>
            )}
          </div>
        )}

        {/* Go Alone prompt */}
        {isGoAlonePrompt && (
          <div className="flex flex-col items-center gap-2">
            <span className="text-xs text-slate-400">
              You called {getSuitSymbol(gameState.trumpSuit!)} as trump. Go alone?
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => handleGoAlone(true)}
                className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Go Alone
              </button>
              <button
                onClick={() => handleGoAlone(false)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium transition-colors"
              >
                Play with Partner
              </button>
            </div>
          </div>
        )}

        {/* Dealer discard */}
        {isDealerDiscard && (
          <span className="text-xs text-yellow-400">Click a card to discard</span>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {myHand.map((card, i) => {
            const isValid = isPlaying ? playableIndices.includes(i) : isDealerDiscard
            return (
              <div
                key={`${card.rank}-${card.suit}-${i}`}
                className={`${CARD_SIZE_COMPACT} transition-transform ${
                  isValid ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
                }`}
                onClick={() => {
                  if (isPlaying && playableIndices.includes(i)) handlePlayCard(i)
                  else if (isDealerDiscard) handleDealerDiscard(i)
                }}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {gameState.phase === 'handOver' && (
          <button onClick={handleNextHand} className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
            Next Hand
          </button>
        )}

        {(gameStatus === 'won' || gameStatus === 'lost') && (
          <GameOverModal
            status={gameStatus}
            score={gameState.teamScores[myTeam]}
            message={gameState.message}
            onPlayAgain={onLeave || (() => {})}
            playAgainText="Back to Lobby"
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
