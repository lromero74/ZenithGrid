/**
 * Bridge VS Multiplayer — 2 humans + 2 AI in a 4-player partnership game.
 *
 * Host-authoritative. Player 0 (host) = South, Player 1 (guest) = North.
 * Teams: Host(0) + AI-Partner(2) = team 0, Guest(1) + AI-Partner(3) = team 1.
 * Bidding, declarer/dummy, trick-taking. First to 500 wins.
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
import {
  createBridgeGame,
  makeBid,
  passBid,
  playCard,
  nextHand,
  getValidPlays,
  strainSymbol,
  formatBid,
  PLAYER_NAMES,
  TEAM_NAMES,
  STRAIN_ORDER,
  type BridgeState,
  type Strain,
} from './BridgeEngine'

// ── Constants ────────────────────────────────────────────────────────

const STRAIN_LABELS: { strain: Strain; label: string; color: string }[] = [
  { strain: 'clubs', label: '\u2663', color: 'bg-slate-700 hover:bg-slate-600' },
  { strain: 'diamonds', label: '\u2666', color: 'bg-red-800 hover:bg-red-700' },
  { strain: 'hearts', label: '\u2665', color: 'bg-red-700 hover:bg-red-600' },
  { strain: 'spades', label: '\u2660', color: 'bg-slate-700 hover:bg-slate-600' },
  { strain: 'nt', label: 'NT', color: 'bg-amber-700 hover:bg-amber-600' },
]

// ── Props ────────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

// ── Component ────────────────────────────────────────────────────────

export function BridgeMultiplayer({ roomId, players, playerNames: _playerNames, onLeave }: Props) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myPlayerIndex = isHost ? 0 : 1

  const song = useMemo(() => getSongForGame('bridge'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('bridge')

  const [gameState, setGameState] = useState<BridgeState>(() => createBridgeGame())
  const stateRef = useRef(gameState)
  stateRef.current = gameState

  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [selectedLevel, setSelectedLevel] = useState(1)
  const [selectedStrain, setSelectedStrain] = useState<Strain>('clubs')

  const myTeam = myPlayerIndex % 2

  // ── Broadcast ──────────────────────────────────────────────────

  const broadcastState = useCallback((state: BridgeState) => {
    if (!isHost) return
    // Send guest their hand (index 1), strip others (except dummy if revealed)
    const sanitized = {
      ...state,
      hands: state.hands.map((h, i) => {
        if (i === 1) return h // guest's hand
        if (i === state.dummy && state.dummyRevealed) return h // dummy visible
        return [] // hide
      }),
    }
    gameSocket.sendAction(roomId, { type: 'state_sync', state: sanitized })
  }, [isHost, roomId])

  useEffect(() => {
    if (!isHost) return
    const state = createBridgeGame()
    setGameState(state)
    broadcastState(state)
  }, [isHost]) // eslint-disable-line react-hooks/exhaustive-deps

  const hostApply = useCallback((fn: (s: BridgeState) => BridgeState) => {
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
        const synced = action.state as BridgeState
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
        if (action.type === 'make_bid') {
          hostApply(s => makeBid(s, action.level as number, action.strain as Strain))
        } else if (action.type === 'pass_bid') {
          hostApply(s => passBid(s))
        } else if (action.type === 'play_card') {
          hostApply(s => playCard(s, action.playerIdx as number, action.cardIndex as number))
        } else if (action.type === 'next_hand') {
          hostApply(s => nextHand(s))
        }
      }
    })
    return unsub
  }, [roomId, isHost, user?.id, hostApply])

  // ── AI: The bridge engine already runs AI internally via advanceBidding and runAiTurns
  // No separate AI timer needed — the engine handles it when makeBid/passBid/playCard are called

  // ── Game over ──────────────────────────────────────────────────

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      setGameStatus(gameState.teamScores[myTeam] > gameState.teamScores[myTeam === 0 ? 1 : 0] ? 'won' : 'lost')
    }
  }, [gameState.phase, gameState.teamScores, myTeam])

  // ── Handlers ───────────────────────────────────────────────────

  const handleBid = useCallback(() => {
    music.init(); sfx.init(); music.start()
    sfx.play('place')
    if (isHost) {
      hostApply(s => makeBid(s, selectedLevel, selectedStrain))
    } else {
      gameSocket.sendAction(roomId, { type: 'make_bid', level: selectedLevel, strain: selectedStrain })
    }
  }, [isHost, roomId, hostApply, selectedLevel, selectedStrain, music, sfx])

  const handlePass = useCallback(() => {
    sfx.play('place')
    if (isHost) {
      hostApply(s => passBid(s))
    } else {
      gameSocket.sendAction(roomId, { type: 'pass_bid' })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handlePlayCard = useCallback((playerIdx: number, cardIndex: number) => {
    sfx.play('place')
    if (isHost) {
      hostApply(s => playCard(s, playerIdx, cardIndex))
    } else {
      gameSocket.sendAction(roomId, { type: 'play_card', playerIdx, cardIndex })
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

  const isBidding = gameState.phase === 'bidding' && gameState.currentPlayer === myPlayerIndex
  const isPlaying = gameState.phase === 'playing'
  const isHumanTurn = isPlaying && gameState.currentPlayer === myPlayerIndex
  // Check if it's dummy's turn and I'm the declarer
  const isDummyTurn = isPlaying && gameState.currentPlayer === gameState.dummy && gameState.declarer === myPlayerIndex

  const humanValidPlays = isHumanTurn ? getValidPlays(gameState, myPlayerIndex) : []
  const dummyValidPlays = isDummyTurn && gameState.dummy !== null ? getValidPlays(gameState, gameState.dummy) : []

  const highestBid = gameState.bids.reduce<{ level: number; strain: Strain } | null>((best, bid) => {
    if (bid.level === 0) return best
    if (!best) return { level: bid.level, strain: bid.strain as Strain }
    const bestIdx = STRAIN_ORDER.indexOf(best.strain)
    const bidIdx = STRAIN_ORDER.indexOf(bid.strain as Strain)
    if (bid.level > best.level || (bid.level === best.level && bidIdx > bestIdx)) {
      return { level: bid.level, strain: bid.strain as Strain }
    }
    return best
  }, null)

  const isValidBidSelection = !highestBid || (
    selectedLevel > highestBid.level ||
    (selectedLevel === highestBid.level && STRAIN_ORDER.indexOf(selectedStrain) > STRAIN_ORDER.indexOf(highestBid.strain))
  )

  const contractStr = gameState.contract
    ? `${gameState.contract.level}${strainSymbol(gameState.contract.strain!)} by ${PLAYER_NAMES[gameState.declarer!]}`
    : null

  const teamTricks = [
    (gameState.tricksWon[0] || 0) + (gameState.tricksWon[2] || 0),
    (gameState.tricksWon[1] || 0) + (gameState.tricksWon[3] || 0),
  ]

  const myHand = gameState.hands[myPlayerIndex]
  const opponentIdx = myPlayerIndex === 0 ? 1 : 0

  // ── Render ─────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between flex-wrap gap-1">
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
        <span className="text-blue-400">{TEAM_NAMES[0]}: {gameState.teamScores[0]}</span>
        <span className="text-red-400">{TEAM_NAMES[1]}: {gameState.teamScores[1]}</span>
        {contractStr && <span className="text-yellow-400">{contractStr}</span>}
        {isPlaying && <span className="text-slate-400">Tricks: {teamTricks[0]}-{teamTricks[1]}</span>}
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  const renderOpponentHand = (playerIdx: number, position: 'top' | 'left' | 'right') => {
    const hand = gameState.hands[playerIdx]
    const isDummy = playerIdx === gameState.dummy && gameState.dummyRevealed
    const label = playerIdx === gameState.dummy ? `${PLAYER_NAMES[playerIdx]} (Dummy)` : PLAYER_NAMES[playerIdx]
    const teamColor = playerIdx % 2 === myTeam ? 'text-blue-400' : 'text-red-400'
    const isDummyPlayable = isDummyTurn && playerIdx === gameState.dummy

    if (position === 'top') {
      return (
        <div className="text-center">
          <span className={`text-xs ${teamColor}`}>{label} ({hand.length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5 flex-wrap">
            {isDummy ? (
              hand.map((card, i) => {
                const isValid = isDummyPlayable && dummyValidPlays.includes(i)
                return (
                  <div
                    key={`${card.rank}-${card.suit}-${i}`}
                    className={`${CARD_SIZE_COMPACT} transition-transform ${
                      isValid ? 'cursor-pointer hover:-translate-y-1' : isDummyPlayable ? 'opacity-40' : ''
                    }`}
                    onClick={() => isDummyPlayable && isValid && handlePlayCard(playerIdx, i)}
                  >
                    <CardFace card={card} />
                  </div>
                )
              })
            ) : (
              hand.slice(0, 7).map((_, i) => (
                <div key={i} className={CARD_SLOT_V}><CardBack /></div>
              ))
            )}
            {!isDummy && hand.length > 7 && (
              <span className="text-[0.6rem] text-slate-500 self-center">+{hand.length - 7}</span>
            )}
          </div>
        </div>
      )
    }

    return (
      <div className="text-center w-16 flex-shrink-0">
        <span className={`text-[0.6rem] ${teamColor}`}>{label} ({hand.length})</span>
        <div className="flex flex-col items-center gap-0.5 mt-0.5">
          {isDummy ? (
            hand.map((card, i) => {
              const isValid = isDummyPlayable && dummyValidPlays.includes(i)
              return (
                <div
                  key={`${card.rank}-${card.suit}-${i}`}
                  className={`w-12 h-[4.25rem] transition-transform ${
                    isValid ? 'cursor-pointer hover:scale-105' : isDummyPlayable ? 'opacity-40' : ''
                  }`}
                  onClick={() => isDummyPlayable && isValid && handlePlayCard(playerIdx, i)}
                >
                  <CardFace card={card} />
                </div>
              )
            })
          ) : (
            hand.slice(0, 5).map((_, i) => (
              <div key={i} className={CARD_SLOT_H}><CardBack /></div>
            ))
          )}
        </div>
      </div>
    )
  }

  return (
    <GameLayout title="Bridge -- VS" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {renderOpponentHand(opponentIdx, 'top')}

        <div className="flex w-full items-center gap-2">
          {renderOpponentHand(3, 'left')}

          <div className="flex-1 relative h-36 sm:h-48">
            {gameState.currentTrick.map((play) => {
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

            {gameState.currentTrick.length === 0 && gameState.trumpSuit && (
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
                {gameState.trumpSuit === 'nt' ? (
                  <span className="text-lg font-bold text-amber-400">NT</span>
                ) : (
                  <span className="text-2xl">
                    {getSuitSymbol(gameState.trumpSuit as 'clubs' | 'diamonds' | 'hearts' | 'spades')}
                  </span>
                )}
                <p className="text-[0.6rem] text-slate-500 mt-0.5">
                  {gameState.trumpSuit === 'nt' ? 'No Trump' : 'Trump'}
                </p>
              </div>
            )}

            {gameState.phase === 'bidding' && gameState.bids.length > 0 && (
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
                <div className="text-[0.6rem] text-slate-400 space-y-0.5">
                  {gameState.bids.slice(-4).map((bid, i) => (
                    <div key={i}>
                      <span className="text-slate-500">{PLAYER_NAMES[bid.player]}: </span>
                      <span className={bid.level > 0 ? 'text-yellow-400' : 'text-slate-500'}>
                        {formatBid(bid)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {renderOpponentHand(2, 'right')}
        </div>

        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Bidding UI */}
        {isBidding && (
          <div className="flex flex-col items-center gap-2">
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5, 6, 7].map(level => (
                <button
                  key={level}
                  onClick={() => setSelectedLevel(level)}
                  className={`w-8 h-8 text-xs rounded transition-colors ${
                    selectedLevel === level ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
            <div className="flex gap-1">
              {STRAIN_LABELS.map(({ strain, label, color }) => (
                <button
                  key={strain}
                  onClick={() => setSelectedStrain(strain)}
                  className={`px-3 h-8 text-sm rounded transition-colors text-white ${
                    selectedStrain === strain ? 'ring-2 ring-yellow-400 ' + color : color
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleBid}
                disabled={!isValidBidSelection}
                className={`px-5 py-2 text-white rounded-lg text-sm font-medium transition-colors ${
                  isValidBidSelection ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-slate-600 text-slate-400 cursor-not-allowed'
                }`}
              >
                Bid {selectedLevel}{strainSymbol(selectedStrain)}
              </button>
              <button onClick={handlePass} className="px-5 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium transition-colors">
                Pass
              </button>
            </div>
            {highestBid && (
              <span className="text-[0.65rem] text-slate-500">
                Current high bid: {highestBid.level}{strainSymbol(highestBid.strain)}
              </span>
            )}
          </div>
        )}

        {/* My hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {myHand.map((card, i) => {
            const isValid = humanValidPlays.includes(i)
            const canPlay = isHumanTurn && isValid
            return (
              <div
                key={`${card.rank}-${card.suit}-${i}`}
                className={`${CARD_SIZE_COMPACT} transition-transform ${
                  canPlay ? 'cursor-pointer hover:-translate-y-1' : (isHumanTurn || isDummyTurn) ? 'opacity-40' : ''
                }`}
                onClick={() => canPlay && handlePlayCard(myPlayerIndex, i)}
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
