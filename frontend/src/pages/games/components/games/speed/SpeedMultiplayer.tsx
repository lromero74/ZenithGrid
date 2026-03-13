/**
 * Speed VS — two human players race in real-time.
 *
 * Host-authoritative: host runs the game engine, broadcasts state.
 * Both players can act simultaneously — no turns. The host validates
 * moves and applies them immediately.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SIZE_MINI } from '../../PlayingCard'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { getRankDisplay, getSuitSymbol } from '../../../utils/cardUtils'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ───────────────────────────────────────────────────────────

type VsPhase = 'ready' | 'playing' | 'stalled' | 'gameOver'

interface VsSpeedState {
  hands: [Card[], Card[]]
  drawPiles: [Card[], Card[]]
  centerPiles: [Card[], Card[]]
  replacementPiles: [Card[], Card[]]
  phase: VsPhase
  message: string
}

/** What the guest sees — no opponent hand or draw pile cards. */
interface GuestViewState {
  myHand: Card[]
  myDrawPileCount: number
  oppHandCount: number
  oppDrawPileCount: number
  centerPiles: [Card[], Card[]]
  replacementPileCounts: [number, number]
  phase: VsPhase
  message: string
}

// ── Engine functions (inline, pure) ─────────────────────────────────

function isPlayable(card: Card, topCard: Card): boolean {
  const diff = Math.abs(card.rank - topCard.rank)
  return diff === 1 || diff === 12
}

function pileTop(pile: Card[]): Card {
  return pile[pile.length - 1]
}

function refillHand(hand: Card[], drawPile: Card[]): { hand: Card[]; drawPile: Card[] } {
  const newHand = [...hand]
  const newDraw = [...drawPile]
  while (newHand.length < 5 && newDraw.length > 0) {
    newHand.push({ ...newDraw.shift()!, faceUp: true })
  }
  return { hand: newHand, drawPile: newDraw }
}

function getPlayableMoves(hand: Card[], centerPiles: [Card[], Card[]]): { handIndex: number; pileIndex: number }[] {
  const moves: { handIndex: number; pileIndex: number }[] = []
  for (let hi = 0; hi < hand.length; hi++) {
    for (let pi = 0; pi < 2; pi++) {
      if (centerPiles[pi].length > 0 && isPlayable(hand[hi], pileTop(centerPiles[pi]))) {
        moves.push({ handIndex: hi, pileIndex: pi })
      }
    }
  }
  return moves
}

function checkStalled(state: VsSpeedState): boolean {
  const p0Moves = getPlayableMoves(state.hands[0], state.centerPiles)
  const p1Moves = getPlayableMoves(state.hands[1], state.centerPiles)
  return p0Moves.length === 0 && p1Moves.length === 0
}

function checkWin(state: VsSpeedState): VsSpeedState {
  if (state.hands[0].length === 0 && state.drawPiles[0].length === 0) {
    return { ...state, phase: 'gameOver', message: 'Player 1 wins! Emptied all cards first!' }
  }
  if (state.hands[1].length === 0 && state.drawPiles[1].length === 0) {
    return { ...state, phase: 'gameOver', message: 'Player 2 wins! Emptied all cards first!' }
  }
  return state
}

function resolveStall(state: VsSpeedState): VsSpeedState {
  if (!checkStalled(state)) return state

  if (state.replacementPiles[0].length === 0 && state.replacementPiles[1].length === 0) {
    const p0Left = state.hands[0].length + state.drawPiles[0].length
    const p1Left = state.hands[1].length + state.drawPiles[1].length
    if (p0Left < p1Left) return { ...state, phase: 'gameOver', message: 'Player 1 wins! Fewer cards remaining!' }
    if (p1Left < p0Left) return { ...state, phase: 'gameOver', message: 'Player 2 wins! Fewer cards remaining!' }
    return { ...state, phase: 'gameOver', message: 'Draw! Same cards remaining.' }
  }

  return { ...state, phase: 'stalled', message: 'No moves! Flip from replacement piles.' }
}

function createVsSpeedGame(): VsSpeedState {
  const deck = shuffleDeck(createDeck())
  let i = 0

  const hand0 = deck.slice(i, i + 5).map(c => ({ ...c, faceUp: false })); i += 5
  const draw0 = deck.slice(i, i + 15).map(c => ({ ...c, faceUp: false })); i += 15
  const replLeft = deck.slice(i, i + 5).map(c => ({ ...c, faceUp: false })); i += 5
  const center0: Card[] = [{ ...deck[i], faceUp: false }]; i += 1
  const center1: Card[] = [{ ...deck[i], faceUp: false }]; i += 1
  const replRight = deck.slice(i, i + 5).map(c => ({ ...c, faceUp: false })); i += 5
  const draw1 = deck.slice(i, i + 15).map(c => ({ ...c, faceUp: false })); i += 15
  const hand1 = deck.slice(i, i + 5).map(c => ({ ...c, faceUp: false }))

  return {
    hands: [hand0, hand1],
    drawPiles: [draw0, draw1],
    centerPiles: [center0, center1],
    replacementPiles: [replLeft, replRight],
    phase: 'ready',
    message: 'Ready? Flip the center cards to start!',
  }
}

function vsFlipStartingCards(state: VsSpeedState): VsSpeedState {
  if (state.phase !== 'ready') return state
  return {
    ...state,
    phase: 'playing',
    hands: [
      state.hands[0].map(c => ({ ...c, faceUp: true })),
      state.hands[1].map(c => ({ ...c, faceUp: true })),
    ],
    centerPiles: [
      state.centerPiles[0].map(c => ({ ...c, faceUp: true })),
      state.centerPiles[1].map(c => ({ ...c, faceUp: true })),
    ],
    message: 'Go! Play as fast as you can!',
  }
}

function vsPlayCard(state: VsSpeedState, player: number, handIndex: number, pileIndex: number): VsSpeedState {
  if (state.phase !== 'playing') return state
  if (handIndex < 0 || handIndex >= state.hands[player].length) return state
  if (pileIndex < 0 || pileIndex > 1) return state

  const card = state.hands[player][handIndex]
  const pile = state.centerPiles[pileIndex]
  if (pile.length === 0 || !isPlayable(card, pileTop(pile))) return state

  const newHand = state.hands[player].filter((_, i) => i !== handIndex)
  const newPiles: [Card[], Card[]] = [
    pileIndex === 0 ? [...pile, { ...card, faceUp: true }] : [...state.centerPiles[0]],
    pileIndex === 1 ? [...pile, { ...card, faceUp: true }] : [...state.centerPiles[1]],
  ]

  const { hand: filledHand, drawPile: newDrawPile } = refillHand(newHand, [...state.drawPiles[player]])

  const newHands: [Card[], Card[]] = [...state.hands] as [Card[], Card[]]
  newHands[player] = filledHand
  const newDrawPiles: [Card[], Card[]] = [...state.drawPiles] as [Card[], Card[]]
  newDrawPiles[player] = newDrawPile

  const next: VsSpeedState = {
    ...state,
    hands: newHands,
    drawPiles: newDrawPiles,
    centerPiles: newPiles,
    message: `Player ${player + 1} played!`,
  }

  const afterWin = checkWin(next)
  if (afterWin.phase === 'gameOver') return afterWin
  return resolveStall(afterWin)
}

function vsFlipCenter(state: VsSpeedState): VsSpeedState {
  if (state.phase !== 'stalled') return state

  const leftRepl = [...state.replacementPiles[0]]
  const rightRepl = [...state.replacementPiles[1]]
  const leftPile = [...state.centerPiles[0]]
  const rightPile = [...state.centerPiles[1]]

  if (leftRepl.length > 0) leftPile.push({ ...leftRepl.shift()!, faceUp: true })
  if (rightRepl.length > 0) rightPile.push({ ...rightRepl.shift()!, faceUp: true })

  const next: VsSpeedState = {
    ...state,
    replacementPiles: [leftRepl, rightRepl],
    centerPiles: [leftPile, rightPile],
    phase: 'playing',
    message: 'New cards flipped! Keep playing!',
  }

  return resolveStall(next)
}

// ── Guest view builder ──────────────────────────────────────────────

function toGuestView(state: VsSpeedState, guestIdx: number): GuestViewState {
  const oppIdx = guestIdx === 0 ? 1 : 0
  return {
    myHand: state.hands[guestIdx],
    myDrawPileCount: state.drawPiles[guestIdx].length,
    oppHandCount: state.hands[oppIdx].length,
    oppDrawPileCount: state.drawPiles[oppIdx].length,
    centerPiles: state.centerPiles,
    replacementPileCounts: [state.replacementPiles[0].length, state.replacementPiles[1].length],
    phase: state.phase,
    message: state.message,
  }
}

// ── Component ────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

export function SpeedMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myIdx = isHost ? 0 : 1
  const oppIdx = myIdx === 0 ? 1 : 0

  const myName = playerNames[players[myIdx]] ?? `Player ${myIdx + 1}`
  const oppName = playerNames[players[oppIdx]] ?? `Player ${oppIdx + 1}`

  const [gameState, setGameState] = useState<VsSpeedState>(() => createVsSpeedGame())
  const stateRef = useRef(gameState)
  stateRef.current = gameState

  const [guestView, setGuestView] = useState<GuestViewState | null>(null)
  const [selectedCard, setSelectedCard] = useState<number | null>(null)
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')

  const song = useMemo(() => getSongForGame('speed'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('speed')

  // ── Host: broadcast state ─────────────────────────────────────────

  const broadcastState = useCallback((state: VsSpeedState) => {
    if (!isHost) return
    gameSocket.sendAction(roomId, {
      type: 'state_sync',
      state: toGuestView(state, 1),
    })
  }, [isHost, roomId])

  // ── Action handlers ───────────────────────────────────────────────

  const handleFlipStart = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('flip')

    if (isHost) {
      setGameState(prev => {
        const next = vsFlipStartingCards(prev)
        broadcastState(next)
        return next
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'flip_start' })
    }
  }, [isHost, roomId, broadcastState, music, sfx])

  const handleFlipCenter = useCallback(() => {
    sfx.play('flip')
    if (isHost) {
      setGameState(prev => {
        const next = vsFlipCenter(prev)
        broadcastState(next)
        return next
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'flip_center' })
    }
  }, [isHost, roomId, broadcastState, sfx])

  // ── Card/pile click handlers ──────────────────────────────────────

  // Get valid moves for my hand
  const myHand = isHost ? gameState.hands[0] : (guestView?.myHand ?? [])
  const centerPiles = isHost ? gameState.centerPiles : (guestView?.centerPiles ?? [[], []] as [Card[], Card[]])
  const phase = isHost ? gameState.phase : (guestView?.phase ?? 'ready')

  const playerMoves = useMemo(() => {
    if (phase !== 'playing') return []
    return getPlayableMoves(myHand, centerPiles)
  }, [phase, myHand, centerPiles])

  const playableCardIndices = useMemo(() => {
    const set = new Set<number>()
    for (const m of playerMoves) set.add(m.handIndex)
    return set
  }, [playerMoves])

  const playablePileIndices = useMemo(() => {
    if (selectedCard === null) return new Set<number>()
    const set = new Set<number>()
    for (const m of playerMoves) {
      if (m.handIndex === selectedCard) set.add(m.pileIndex)
    }
    return set
  }, [playerMoves, selectedCard])

  const doPlayCard = useCallback((handIndex: number, pileIndex: number) => {
    sfx.play('place')
    if (isHost) {
      setGameState(prev => {
        const next = vsPlayCard(prev, 0, handIndex, pileIndex)
        broadcastState(next)
        return next
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'play_card', handIndex, pileIndex })
    }
    setSelectedCard(null)
  }, [isHost, roomId, broadcastState, sfx])

  const handleCardClick = useCallback((handIndex: number) => {
    music.init()
    sfx.init()
    music.start()

    if (!playableCardIndices.has(handIndex)) return

    const validPiles = playerMoves.filter(m => m.handIndex === handIndex).map(m => m.pileIndex)
    if (validPiles.length === 1) {
      doPlayCard(handIndex, validPiles[0])
    } else if (validPiles.length > 1) {
      setSelectedCard(handIndex)
    }
  }, [playableCardIndices, playerMoves, doPlayCard, music, sfx])

  const handlePileClick = useCallback((pileIndex: number) => {
    if (selectedCard === null) return
    if (!playablePileIndices.has(pileIndex)) return
    doPlayCard(selectedCard, pileIndex)
  }, [selectedCard, playablePileIndices, doPlayCard])

  // ── WebSocket listener ────────────────────────────────────────────

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: { playerId?: number; action?: Record<string, unknown> }) => {
      if (msg.playerId === user?.id) return
      const action = msg.action
      if (!action) return

      if (action.type === 'state_sync') {
        if (!isHost) {
          setGuestView(action.state as GuestViewState)
          setSelectedCard(null)  // Reset selection on state update
        }
        return
      }

      if (isHost) {
        if (action.type === 'flip_start') {
          sfx.play('flip')
          setGameState(prev => {
            const next = vsFlipStartingCards(prev)
            broadcastState(next)
            return next
          })
        } else if (action.type === 'flip_center') {
          sfx.play('flip')
          setGameState(prev => {
            const next = vsFlipCenter(prev)
            broadcastState(next)
            return next
          })
        } else if (action.type === 'play_card') {
          sfx.play('place')
          setGameState(prev => {
            const next = vsPlayCard(prev, 1, action.handIndex as number, action.pileIndex as number)
            broadcastState(next)
            return next
          })
        }
      }
    })
    return unsub
  }, [roomId, isHost, user?.id, broadcastState, sfx])

  // ── Game over detection ───────────────────────────────────────────

  useEffect(() => {
    if (phase !== 'gameOver') return
    const msg = isHost ? gameState.message : (guestView?.message ?? '')
    const myPlayerLabel = `Player ${myIdx + 1}`
    if (msg.includes(`${myPlayerLabel} wins`)) setGameStatus('won')
    else if (msg.includes('Draw')) setGameStatus('draw')
    else setGameStatus('lost')
  }, [phase, isHost, gameState.message, guestView?.message, myIdx])

  // ── Derived state ─────────────────────────────────────────────────

  const message = isHost ? gameState.message : (guestView?.message ?? 'Waiting for host...')
  const myDrawPileCount = isHost ? gameState.drawPiles[0].length : (guestView?.myDrawPileCount ?? 15)
  const oppHandCount = isHost ? gameState.hands[1].length : (guestView?.oppHandCount ?? 5)
  const oppDrawPileCount = isHost ? gameState.drawPiles[1].length : (guestView?.oppDrawPileCount ?? 15)
  const replCounts = isHost
    ? [gameState.replacementPiles[0].length, gameState.replacementPiles[1].length]
    : (guestView?.replacementPileCounts ?? [5, 5])

  const myCardsLeft = myHand.length + myDrawPileCount
  const oppCardsLeft = oppHandCount + oppDrawPileCount

  // ── Render ────────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between text-xs w-full">
      <div className="flex items-center gap-2">
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-slate-400">VS Mode</span>
        <span className="text-slate-400">{myName}: {myCardsLeft} | {oppName}: {oppCardsLeft}</span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Speed — VS" controls={controls}>
      <div className="flex flex-col items-center w-full max-w-md space-y-3">
        {/* Opponent area */}
        <div className="flex items-center justify-center gap-4 w-full">
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">
              Draw ({oppDrawPileCount})
            </span>
            <div className={CARD_SIZE}>
              {oppDrawPileCount > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700 rounded-lg" />
              )}
            </div>
          </div>
          <div className="flex gap-1">
            {Array.from({ length: oppHandCount }).map((_, i) => (
              <div key={i} className={CARD_SIZE_MINI}>
                <CardBack />
              </div>
            ))}
          </div>
          <div className="text-center">
            <span className="text-[0.6rem] text-red-400 block mb-0.5">{oppName}</span>
          </div>
        </div>

        {/* Center area: replacement piles flanking center piles */}
        <div className="flex items-center justify-center gap-3 py-2">
          {/* Left replacement pile */}
          <div className="text-center">
            <div className={CARD_SIZE_MINI}>
              {replCounts[0] > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700/50 rounded-md" />
              )}
            </div>
            <span className="text-[0.5rem] text-slate-600 block mt-0.5">{replCounts[0]}</span>
          </div>

          {/* Center piles */}
          {[0, 1].map(pi => {
            const pile = centerPiles[pi]
            const topCard = pile.length > 0 ? pile[pile.length - 1] : null
            const isTarget = playablePileIndices.has(pi)
            const isReady = phase === 'ready'
            return (
              <button
                key={pi}
                onClick={() => isReady ? undefined : handlePileClick(pi)}
                disabled={isReady || !isTarget}
                className={`${CARD_SIZE} transition-all ${isTarget ? 'cursor-pointer' : ''}`}
              >
                {isReady ? (
                  <CardBack />
                ) : topCard ? (
                  <CardFace card={{ ...topCard, faceUp: true }} validTarget={isTarget} />
                ) : (
                  <div className="w-full h-full border border-dashed border-slate-600 rounded-lg" />
                )}
              </button>
            )
          })}

          {/* Right replacement pile */}
          <div className="text-center">
            <div className={CARD_SIZE_MINI}>
              {replCounts[1] > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700/50 rounded-md" />
              )}
            </div>
            <span className="text-[0.5rem] text-slate-600 block mt-0.5">{replCounts[1]}</span>
          </div>
        </div>

        {/* Message + flip buttons */}
        <div className="text-center min-h-[2.5rem]">
          <p className="text-sm text-white font-medium">{message}</p>
          {phase === 'ready' && (
            <button
              onClick={handleFlipStart}
              className="mt-2 px-8 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg
                text-base font-bold transition-colors active:scale-95 animate-pulse shadow-lg shadow-emerald-900/50"
            >
              Flip!
            </button>
          )}
          {phase === 'stalled' && gameStatus === 'playing' && (
            <button
              onClick={handleFlipCenter}
              className="mt-1 px-5 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded-lg
                text-sm font-medium transition-colors active:scale-95 animate-pulse"
            >
              Flip!
            </button>
          )}
        </div>

        {/* My hand */}
        <div className="flex items-center justify-center gap-4 w-full">
          <div className="flex gap-1.5">
            {myHand.map((card, i) => {
              const isReady = phase === 'ready'
              const canPlay = !isReady && playableCardIndices.has(i)
              const isSelected = selectedCard === i
              return (
                <button
                  key={`${card.suit}-${card.rank}-${i}`}
                  onClick={() => !isReady && handleCardClick(i)}
                  disabled={isReady || (!canPlay && !isSelected)}
                  className={`${CARD_SIZE} transition-all ${
                    isReady ? '' : canPlay ? 'hover:-translate-y-1 cursor-pointer' : 'cursor-default'
                  } ${isSelected ? '-translate-y-2' : ''}`}
                >
                  {isReady ? <CardBack /> : <CardFace card={card} selected={isSelected} />}
                </button>
              )
            })}
          </div>
          <div className="text-center">
            <div className={CARD_SIZE}>
              {myDrawPileCount > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700 rounded-lg" />
              )}
            </div>
            <span className="text-[0.6rem] text-slate-500 block mt-0.5">
              Draw ({myDrawPileCount})
            </span>
          </div>
        </div>

        {/* Hints */}
        {phase === 'playing' && playerMoves.length > 0 && selectedCard === null && (
          <p className="text-xs text-slate-500">Tap a card, then tap a center pile to play it</p>
        )}
        {selectedCard !== null && myHand[selectedCard] && (
          <p className="text-xs text-green-400">
            Playing {getRankDisplay(myHand[selectedCard].rank)}
            {getSuitSymbol(myHand[selectedCard].suit)}
            — tap a green pile
          </p>
        )}
        {phase === 'playing' && playerMoves.length === 0 && (
          <p className="text-xs text-amber-400">No moves available — waiting for stall detection...</p>
        )}

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            score={20 - myCardsLeft}
            message={
              gameStatus === 'won'
                ? `You win! You emptied your cards first!`
                : gameStatus === 'lost'
                  ? `${oppName} wins!`
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
