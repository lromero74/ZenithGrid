/**
 * Speed — real-time 2-player card game. Race to empty your hand first!
 * Contributed by Shantina Jackson-Romero.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SIZE_MINI } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { getRankDisplay, getSuitSymbol } from '../../../utils/cardUtils'
import {
  createSpeedGame,
  playCard,
  aiPlayCard,
  flipCenterCards,
  getAiMove,
  getPlayerMoves,
  type SpeedState,
} from './speedEngine'

interface SavedState {
  gameState: SpeedState
  gameStatus: GameStatus
}

export default function Speed() {
  const { load, save, clear } = useGameState<SavedState>('speed')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('speed'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('speed')

  const [gameState, setGameState] = useState<SpeedState>(
    () => saved?.gameState ?? createSpeedGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedCard, setSelectedCard] = useState<number | null>(null)

  // Persist state
  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost' && gameStatus !== 'draw') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Detect game over
  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const pLeft = gameState.playerHand.length + gameState.playerDrawPile.length
      const aLeft = gameState.aiHand.length + gameState.aiDrawPile.length
      if (pLeft < aLeft) setGameStatus('won')
      else if (aLeft < pLeft) setGameStatus('lost')
      else setGameStatus('draw')
      clear()
    }
  }, [gameState, clear])

  // AI play loop — AI makes moves with random delay
  const aiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (gameState.phase !== 'playing' || gameStatus !== 'playing') return

    const delay = 400 + Math.random() * 400 // 400-800ms
    aiTimerRef.current = setTimeout(() => {
      setGameState(prev => {
        if (prev.phase !== 'playing') return prev
        const move = getAiMove(prev)
        if (!move) return prev
        sfx.play('play')
        return aiPlayCard(prev, move.handIndex, move.pileIndex)
      })
    }, delay)

    return () => {
      if (aiTimerRef.current) clearTimeout(aiTimerRef.current)
    }
  }, [gameState, gameStatus, sfx])

  // Get valid player moves
  const playerMoves = useMemo(() => getPlayerMoves(gameState), [gameState])
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

  const handleCardClick = useCallback((handIndex: number) => {
    music.init()
    sfx.init()
    music.start()

    if (!playableCardIndices.has(handIndex)) return

    // Find which piles this card can play on
    const validPiles = playerMoves.filter(m => m.handIndex === handIndex).map(m => m.pileIndex)

    if (validPiles.length === 1) {
      // Auto-play on the only valid pile
      sfx.play('play')
      setGameState(prev => playCard(prev, handIndex, validPiles[0]))
      setSelectedCard(null)
    } else if (validPiles.length > 1) {
      // Select card, let player choose pile
      setSelectedCard(handIndex)
    }
  }, [playableCardIndices, playerMoves, music, sfx])

  const handlePileClick = useCallback((pileIndex: number) => {
    if (selectedCard === null) return
    if (!playablePileIndices.has(pileIndex)) return

    sfx.play('play')
    setGameState(prev => playCard(prev, selectedCard, pileIndex))
    setSelectedCard(null)
  }, [selectedCard, playablePileIndices, sfx])

  const handleFlip = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('flip')
    setGameState(prev => flipCenterCards(prev))
  }, [music, sfx])

  const handleNewGame = useCallback(() => {
    setGameState(createSpeedGame())
    setGameStatus('playing')
    setSelectedCard(null)
    clear()
  }, [clear])

  const playerCardsLeft = gameState.playerHand.length + gameState.playerDrawPile.length
  const aiCardsLeft = gameState.aiHand.length + gameState.aiDrawPile.length

  const controls = (
    <div className="flex items-center justify-between text-xs w-full">
      <span className="text-slate-400">You: {playerCardsLeft} | AI: {aiCardsLeft}</span>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Speed" controls={controls}>
      <div className="flex flex-col items-center w-full max-w-md space-y-3">
        {/* AI area */}
        <div className="flex items-center justify-center gap-4 w-full">
          {/* AI draw pile */}
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">
              Draw ({gameState.aiDrawPile.length})
            </span>
            <div className={CARD_SIZE}>
              {gameState.aiDrawPile.length > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700 rounded-lg" />
              )}
            </div>
          </div>
          {/* AI hand (face down) */}
          <div className="flex gap-1">
            {gameState.aiHand.map((_, i) => (
              <div key={i} className={CARD_SIZE_MINI}>
                <CardBack />
              </div>
            ))}
          </div>
        </div>

        {/* Center piles */}
        <div className="flex items-center justify-center gap-6 py-2">
          {[0, 1].map(pi => {
            const pile = gameState.centerPiles[pi]
            const topCard = pile.length > 0 ? pile[pile.length - 1] : null
            const isTarget = playablePileIndices.has(pi)
            return (
              <button
                key={pi}
                onClick={() => handlePileClick(pi)}
                disabled={!isTarget}
                className={`${CARD_SIZE} transition-all ${
                  isTarget
                    ? 'ring-2 ring-green-400 rounded-lg cursor-pointer scale-105'
                    : ''
                }`}
              >
                {topCard ? (
                  <CardFace card={topCard} validTarget={isTarget} />
                ) : (
                  <div className="w-full h-full border border-dashed border-slate-600 rounded-lg" />
                )}
              </button>
            )
          })}
        </div>

        {/* Message + stall button */}
        <div className="text-center min-h-[2.5rem]">
          <p className="text-sm text-white font-medium">{gameState.message}</p>
          {gameState.phase === 'stalled' && gameStatus === 'playing' && (
            <button
              onClick={handleFlip}
              className="mt-1 px-5 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded-lg
                text-sm font-medium transition-colors active:scale-95 animate-pulse"
            >
              Flip!
            </button>
          )}
        </div>

        {/* Player hand */}
        <div className="flex items-center justify-center gap-4 w-full">
          <div className="flex gap-1.5">
            {gameState.playerHand.map((card, i) => {
              const canPlay = playableCardIndices.has(i)
              const isSelected = selectedCard === i
              return (
                <button
                  key={`${card.suit}-${card.rank}-${i}`}
                  onClick={() => handleCardClick(i)}
                  disabled={!canPlay && !isSelected}
                  className={`${CARD_SIZE} transition-all ${
                    canPlay ? 'hover:-translate-y-1 cursor-pointer' : 'opacity-60'
                  } ${isSelected ? '-translate-y-2' : ''}`}
                >
                  <CardFace card={card} selected={isSelected} />
                </button>
              )
            })}
          </div>
          {/* Player draw pile */}
          <div className="text-center">
            <div className={CARD_SIZE}>
              {gameState.playerDrawPile.length > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700 rounded-lg" />
              )}
            </div>
            <span className="text-[0.6rem] text-slate-500 block mt-0.5">
              Draw ({gameState.playerDrawPile.length})
            </span>
          </div>
        </div>

        {/* Center pile labels */}
        {gameState.phase === 'playing' && playerMoves.length > 0 && selectedCard === null && (
          <p className="text-xs text-slate-500">Tap a highlighted card to play it</p>
        )}
        {selectedCard !== null && (
          <p className="text-xs text-green-400">
            Playing {getRankDisplay(gameState.playerHand[selectedCard]?.rank ?? 0)}
            {getSuitSymbol(gameState.playerHand[selectedCard]?.suit ?? 'hearts')}
            — tap a green pile
          </p>
        )}

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            score={26 - playerCardsLeft}
            message={gameState.message}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
