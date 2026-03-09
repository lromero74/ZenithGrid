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
  flipStartingCards,
  getAiMove,
  getPlayerMoves,
  generateAiPlayDelay,
  type SpeedState,
  type AiDifficulty,
} from './speedEngine'

interface SavedState {
  gameState: SpeedState
  gameStatus: GameStatus
}

// ── Difficulty selection screen ─────────────────────────────────────

function DifficultySelect({ onStart }: { onStart: (difficulty: AiDifficulty) => void }) {
  const [difficulty, setDifficulty] = useState<AiDifficulty>('normal')

  return (
    <div className="flex flex-col items-center gap-6 py-4">
      <div className="text-center">
        <h3 className="text-sm font-medium text-slate-300 mb-3 uppercase tracking-wider">AI Difficulty</h3>
        <div className="flex gap-2">
          {(['easy', 'normal', 'adept'] as const).map(d => (
            <button
              key={d}
              onClick={() => setDifficulty(d)}
              className={`px-4 py-2.5 rounded-lg text-sm font-medium transition-all capitalize ${
                difficulty === d
                  ? d === 'easy' ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/40'
                    : d === 'normal' ? 'bg-amber-600 text-white shadow-lg shadow-amber-900/40'
                    : 'bg-red-600 text-white shadow-lg shadow-red-900/40'
                  : 'bg-slate-700/60 text-slate-400 hover:bg-slate-700'
              }`}
            >
              {d}
            </button>
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-2 max-w-xs">
          {difficulty === 'easy' ? 'AI reacts like an average human — room to breathe.'
            : difficulty === 'normal' ? 'AI is competent — occasionally catches you off guard.'
            : 'AI has fast reflexes — top 10% reaction speed.'}
        </p>
      </div>

      <button
        onClick={() => onStart(difficulty)}
        className="mt-2 px-10 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl
          text-lg font-bold transition-all active:scale-95 shadow-lg shadow-emerald-900/50"
      >
        Deal Cards
      </button>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────

export default function Speed() {
  const { load, save, clear } = useGameState<SavedState>('speed')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('speed'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('speed')

  const [showDifficultySelect, setShowDifficultySelect] = useState<boolean>(() => {
    const s = saved?.gameState
    return !(s && s.replacementPiles && s.difficulty)
  })
  const [gameState, setGameState] = useState<SpeedState>(() => {
    const s = saved?.gameState
    if (s && s.replacementPiles && s.difficulty) return s
    return createSpeedGame()
  })
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedCard, setSelectedCard] = useState<number | null>(null)
  const [flipping, setFlipping] = useState(false)
  const [flipRevealed, setFlipRevealed] = useState(false)

  // Persist state
  useEffect(() => {
    if (showDifficultySelect) return
    if (gameStatus !== 'won' && gameStatus !== 'lost' && gameStatus !== 'draw') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save, showDifficultySelect])

  // Detect game over
  useEffect(() => {
    if (showDifficultySelect) return
    if (gameState.phase === 'gameOver') {
      const pLeft = gameState.playerHand.length + gameState.playerDrawPile.length
      const aLeft = gameState.aiHand.length + gameState.aiDrawPile.length
      if (pLeft < aLeft) setGameStatus('won')
      else if (aLeft < pLeft) setGameStatus('lost')
      else setGameStatus('draw')
      clear()
    }
  }, [gameState, clear, showDifficultySelect])

  // AI play loop — human-modeled reaction timing
  const aiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (showDifficultySelect) return
    if (gameState.phase !== 'playing' || gameStatus !== 'playing') return

    const delay = generateAiPlayDelay(gameState.difficulty)
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
  }, [gameState, gameStatus, sfx, showDifficultySelect])

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

  const handleStartingFlip = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('flip')
    setFlipping(true)
    setFlipRevealed(false)
    // At the halfway point (card is edge-on), swap to face-up
    setTimeout(() => setFlipRevealed(true), 300)
    // After full animation, update game state
    setTimeout(() => {
      setGameState(prev => flipStartingCards(prev))
      setFlipping(false)
      setFlipRevealed(false)
    }, 600)
  }, [music, sfx])

  const handleFlip = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('flip')
    setGameState(prev => flipCenterCards(prev))
  }, [music, sfx])

  const handleNewGame = useCallback(() => {
    setShowDifficultySelect(true)
    setGameStatus('playing')
    setSelectedCard(null)
    clear()
  }, [clear])

  const handleStart = useCallback((difficulty: AiDifficulty) => {
    music.init()
    sfx.init()
    music.start()
    setGameState(createSpeedGame(difficulty))
    setGameStatus('playing')
    setSelectedCard(null)
    setShowDifficultySelect(false)
  }, [music, sfx])

  // ── Difficulty selection screen ───────────────────────────────────
  if (showDifficultySelect) {
    return (
      <GameLayout title="Speed" controls={<MusicToggle music={music} sfx={sfx} />}>
        <DifficultySelect onStart={handleStart} />
      </GameLayout>
    )
  }

  // ── Game screen ───────────────────────────────────────────────────
  const playerCardsLeft = gameState.playerHand.length + gameState.playerDrawPile.length
  const aiCardsLeft = gameState.aiHand.length + gameState.aiDrawPile.length
  const difficultyLabel = gameState.difficulty === 'easy' ? 'Easy' : gameState.difficulty === 'normal' ? 'Normal' : 'Adept'

  const controls = (
    <div className="flex items-center justify-between text-xs w-full">
      <div className="flex items-center gap-2">
        <button
          onClick={handleNewGame}
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          New Game
        </button>
        <span className="text-slate-500">{difficultyLabel}</span>
        <span className="text-slate-400">You: {playerCardsLeft} | AI: {aiCardsLeft}</span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Speed" controls={controls}>
      {/* Card flip animation keyframes */}
      <style>{`
        @keyframes cardFlip {
          0% { transform: rotateY(0deg); }
          50% { transform: rotateY(90deg); }
          100% { transform: rotateY(0deg); }
        }
      `}</style>
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

        {/* Center area: replacement piles flanking center piles */}
        <div className="flex items-center justify-center gap-3 py-2">
          {/* Left replacement pile */}
          <div className="text-center">
            <div className={CARD_SIZE_MINI}>
              {gameState.replacementPiles[0].length > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700/50 rounded-md" />
              )}
            </div>
            <span className="text-[0.5rem] text-slate-600 block mt-0.5">
              {gameState.replacementPiles[0].length}
            </span>
          </div>

          {/* Center piles */}
          {[0, 1].map(pi => {
            const pile = gameState.centerPiles[pi]
            const topCard = pile.length > 0 ? pile[pile.length - 1] : null
            const isTarget = playablePileIndices.has(pi)
            const isReady = gameState.phase === 'ready'
            return (
              <div
                key={pi}
                className="perspective-500"
                style={{ perspective: '500px' }}
              >
                <button
                  onClick={() => isReady ? undefined : handlePileClick(pi)}
                  disabled={isReady || !isTarget}
                  className={`${CARD_SIZE} transition-all ${
                    isTarget ? 'cursor-pointer' : ''
                  } ${flipping ? 'animate-card-flip' : ''}`}
                  style={flipping ? {
                    animation: 'cardFlip 600ms ease-in-out',
                    transformStyle: 'preserve-3d',
                  } : undefined}
                >
                  {isReady && !flipRevealed ? (
                    <CardBack />
                  ) : topCard ? (
                    <CardFace card={{ ...topCard, faceUp: true }} validTarget={isTarget} />
                  ) : (
                    <div className="w-full h-full border border-dashed border-slate-600 rounded-lg" />
                  )}
                </button>
              </div>
            )
          })}

          {/* Right replacement pile */}
          <div className="text-center">
            <div className={CARD_SIZE_MINI}>
              {gameState.replacementPiles[1].length > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700/50 rounded-md" />
              )}
            </div>
            <span className="text-[0.5rem] text-slate-600 block mt-0.5">
              {gameState.replacementPiles[1].length}
            </span>
          </div>
        </div>

        {/* Message + flip buttons */}
        <div className="text-center min-h-[2.5rem]">
          <p className="text-sm text-white font-medium">{gameState.message}</p>
          {gameState.phase === 'ready' && !flipping && (
            <button
              onClick={handleStartingFlip}
              className="mt-2 px-8 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg
                text-base font-bold transition-colors active:scale-95 animate-pulse shadow-lg shadow-emerald-900/50"
            >
              Flip!
            </button>
          )}
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
              const isReady = gameState.phase === 'ready'
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
          <p className="text-xs text-slate-500">Tap a card, then tap a center pile to play it</p>
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
