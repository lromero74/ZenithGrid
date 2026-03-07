/**
 * Euchre — 4-player partnership trick-taking card game.
 *
 * 24-card deck, bowers (J of trump & same-color J), trump selection via two rounds.
 * Teams: You+North vs East+West. First to 10 points wins.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { getSuitSymbol } from '../../../utils/cardUtils'
import type { Suit } from '../../../utils/cardUtils'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import {
  createEuchreGame,
  orderUp,
  pass,
  nameTrump,
  dealerDiscard,
  playCard,
  advanceAi,
  getPlayableCards,
  aiTrumpSelection,
  aiDealerDiscard,
  nextHand,
  PLAYER_NAMES,
  TEAM_NAMES,
  type EuchreState,
} from './EuchreEngine'

interface SavedState {
  gameState: EuchreState
  gameStatus: GameStatus
}

const SUIT_OPTIONS: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']

const AI_DELAY = 600

export default function Euchre() {
  const { load, save, clear } = useGameState<SavedState>('euchre')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('euchre'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('euchre')

  const [gameState, setGameState] = useState<EuchreState>(
    () => saved?.gameState ?? createEuchreGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const aiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // SFX on trick completion
  const prevTrickLen = useRef(0)
  useEffect(() => {
    if (prevTrickLen.current > 0 && gameState.currentTrick.length === 0) sfx.play('trick_won')
    prevTrickLen.current = gameState.currentTrick.length
  }, [gameState.currentTrick.length])

  // Persist state
  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Detect game over
  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      setGameStatus(gameState.teamScores[0] > gameState.teamScores[1] ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  // AI auto-advance: trump selection, dealer discard, and playing
  useEffect(() => {
    if (gameState.phase === 'gameOver' || gameState.phase === 'handOver') return
    if (gameState.currentPlayer === 0) return

    // AI needs to act
    aiTimerRef.current = setTimeout(() => {
      setGameState(prev => {
        if (prev.currentPlayer === 0) return prev

        if (prev.phase === 'trumpRound1' || prev.phase === 'trumpRound2') {
          return aiTrumpSelection(prev)
        }

        if (prev.phase === 'dealerDiscard') {
          return aiDealerDiscard(prev)
        }

        if (prev.phase === 'playing') {
          return advanceAi(prev)
        }

        return prev
      })
    }, AI_DELAY)

    return () => {
      if (aiTimerRef.current) clearTimeout(aiTimerRef.current)
    }
  }, [gameState.currentPlayer, gameState.phase, gameState.currentTrick.length])

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (aiTimerRef.current) clearTimeout(aiTimerRef.current)
    }
  }, [])

  const handleOrderUp = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    setGameState(prev => orderUp(prev))
  }, [])

  const handlePass = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    setGameState(prev => pass(prev))
  }, [])

  const handleNameTrump = useCallback((suit: Suit) => {
    setGameState(prev => nameTrump(prev, suit))
  }, [])

  const handleDealerDiscard = useCallback((i: number) => {
    setGameState(prev => dealerDiscard(prev, i))
  }, [])

  const handlePlay = useCallback((i: number) => {
    sfx.play('play')
    setGameState(prev => playCard(prev, i))
  }, [])

  const handleNextHand = useCallback(() => {
    sfx.play('hand_won')
    setGameState(prev => nextHand(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createEuchreGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const isHumanTurn = gameState.currentPlayer === 0
  const isPlaying = gameState.phase === 'playing' && isHumanTurn
  const isTrumpRound1 = gameState.phase === 'trumpRound1' && isHumanTurn
  const isTrumpRound2 = gameState.phase === 'trumpRound2' && isHumanTurn
  const isDealerDiscard = gameState.phase === 'dealerDiscard' && isHumanTurn

  const playableIndices = isPlaying
    ? getPlayableCards(gameState.hands[0], gameState.ledSuit, gameState.trumpSuit!)
    : []

  // Use original hand for play/discard indices (unsorted in state)
  const humanHand = gameState.hands[0]

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex gap-3">
        <span className="text-blue-400">{TEAM_NAMES[0]}: {gameState.teamScores[0]}</span>
        <span className="text-red-400">{TEAM_NAMES[1]}: {gameState.teamScores[1]}</span>
      </div>
      <div className="flex gap-2 text-slate-400">
        {gameState.trumpSuit && (
          <span className="text-yellow-400">
            Trump: {getSuitSymbol(gameState.trumpSuit)}
          </span>
        )}
        <span>Dealer: {PLAYER_NAMES[gameState.dealer]}</span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Euchre" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* North (Partner) */}
        <div className="text-center">
          <span className="text-xs text-blue-400">North (Partner) ({gameState.hands[2].length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[2].map((_, i) => (
              <div key={i} className="w-5 h-8"><CardBack /></div>
            ))}
          </div>
        </div>

        {/* West + Trick area + East */}
        <div className="flex w-full items-center gap-2">
          {/* West (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">West ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].map((_, i) => (
                <div key={i} className="w-8 h-3"><CardBack /></div>
              ))}
            </div>
          </div>

          {/* Trick area + flipped card */}
          <div className="flex-1 relative h-36 sm:h-48">
            {/* Flipped card during trump selection */}
            {(gameState.phase === 'trumpRound1' || gameState.phase === 'trumpRound2') && (
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-14 h-[5rem] sm:w-16 sm:h-[5.625rem]">
                {gameState.phase === 'trumpRound1' ? (
                  <CardFace card={gameState.flippedCard} />
                ) : (
                  <CardBack />
                )}
              </div>
            )}

            {/* Current trick cards */}
            {gameState.phase === 'playing' && gameState.currentTrick.map((play) => {
              const positions = [
                'bottom-0 left-1/2 -translate-x-1/2',  // South (You)
                'right-0 top-1/2 -translate-y-1/2',     // East
                'top-0 left-1/2 -translate-x-1/2',      // North
                'left-0 top-1/2 -translate-y-1/2',      // West
              ]
              return (
                <div key={`${play.player}-${play.card.rank}-${play.card.suit}`}
                  className={`absolute ${positions[play.player]} w-14 h-[5rem] sm:w-16 sm:h-[5.625rem]`}
                >
                  <CardFace card={play.card} />
                </div>
              )
            })}

            {/* Trump indicator in center during play */}
            {gameState.phase === 'playing' && gameState.trumpSuit && gameState.currentTrick.length === 0 && (
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
                <span className="text-2xl">
                  {getSuitSymbol(gameState.trumpSuit)}
                </span>
                <p className="text-[0.6rem] text-slate-500 mt-0.5">Trump</p>
              </div>
            )}

            {/* Trick counts during play */}
            {gameState.phase === 'playing' && (
              <div className="absolute bottom-0 right-0 text-[0.55rem] text-slate-500">
                {PLAYER_NAMES.map((name, i) => (
                  <span key={i} className="mr-1">{name.charAt(0)}:{gameState.tricksTaken[i]}</span>
                ))}
              </div>
            )}
          </div>

          {/* East (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">East ({gameState.hands[1].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[1].map((_, i) => (
                <div key={i} className="w-8 h-3"><CardBack /></div>
              ))}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Trump Round 1 controls */}
        {isTrumpRound1 && (
          <div className="flex gap-2">
            <button
              onClick={handleOrderUp}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Order Up ({getSuitSymbol(gameState.flippedCard.suit)})
            </button>
            <button
              onClick={handlePass}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium transition-colors"
            >
              Pass
            </button>
          </div>
        )}

        {/* Trump Round 2 controls — suit picker */}
        {isTrumpRound2 && (
          <div className="flex flex-col items-center gap-2">
            <span className="text-xs text-slate-400">
              Name trump (not {getSuitSymbol(gameState.flippedCard.suit)} {gameState.flippedCard.suit})
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
              <button
                onClick={handlePass}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium transition-colors"
              >
                Pass
              </button>
            )}
          </div>
        )}

        {/* Dealer discard prompt */}
        {isDealerDiscard && (
          <span className="text-xs text-yellow-400">Click a card to discard</span>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {humanHand.map((card, i) => {
            const isValid = isPlaying
              ? playableIndices.includes(i)
              : isDealerDiscard
            return (
              <div
                key={`${card.rank}-${card.suit}-${i}`}
                className={`w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] transition-transform ${
                  isValid ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
                }`}
                onClick={() => {
                  if (isPlaying && playableIndices.includes(i)) handlePlay(i)
                  else if (isDealerDiscard) handleDealerDiscard(i)
                }}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {/* Hand over — next hand */}
        {gameState.phase === 'handOver' && (
          <button
            onClick={handleNextHand}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Next Hand
          </button>
        )}

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost') && (
          <GameOverModal
            status={gameStatus}
            score={gameState.teamScores[0]}
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
