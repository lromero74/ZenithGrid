/**
 * Canasta — 4-player partnership card game with melds and canastas.
 *
 * Double deck (108 cards), 2v2 teams. Meld groups of same rank.
 * Canasta = 7+ cards. First team to 5000 wins.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SLOT_V, CARD_SLOT_H } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import type { Card } from '../../../utils/cardUtils'
import { getRankDisplay, getSuitSymbol, getCardColor } from '../../../utils/cardUtils'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import {
  createCanastaGame,
  drawFromStock,
  pickupDiscardPile,
  meldCards,
  discard,
  goOut,
  aiTurn,
  newRound,
  isWild,
  TEAM_NAMES,
  type CanastaState,
  type CanastaMeld,
} from './CanastaEngine'

// ── Types ────────────────────────────────────────────────────────────

interface SavedState {
  gameState: CanastaState
  gameStatus: GameStatus
}

// ── JokerCard ────────────────────────────────────────────────────────

function JokerCard() {
  return (
    <div className="w-full h-full rounded-md bg-slate-50 border border-slate-300 shadow-md flex flex-col items-center justify-center select-none">
      <span className="text-purple-600 font-bold text-xs">JKR</span>
      <span className="text-2xl">{'\uD83C\uDCCF'}</span>
    </div>
  )
}

// ── Card renderer ────────────────────────────────────────────────────

function GameCard({ card, selected, onClick, disabled }: {
  card: Card
  selected?: boolean
  onClick?: () => void
  disabled?: boolean
}) {
  return (
    <div
      className={`${CARD_SIZE} transition-transform ${
        !disabled ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
      } ${selected ? '-translate-y-2' : ''}`}
      onClick={disabled ? undefined : onClick}
    >
      {card.rank === 0 ? <JokerCard /> : (
        <CardFace card={card} selected={selected} />
      )}
    </div>
  )
}

// ── Meld display ─────────────────────────────────────────────────────

function MeldDisplay({ meld }: { meld: CanastaMeld }) {
  const borderClass = meld.isCanasta
    ? meld.isNatural
      ? 'border-yellow-400 bg-yellow-400/10'   // Gold for natural canasta
      : 'border-slate-400 bg-slate-400/10'      // Silver for mixed canasta
    : 'border-slate-600 bg-slate-800/50'

  return (
    <div className={`inline-flex items-center gap-0.5 p-1 rounded border ${borderClass}`}>
      {meld.cards.slice(0, 4).map((card, i) => (
        <div key={i} className="w-6 h-9 flex-shrink-0">
          {card.rank === 0 ? (
            <div className="w-full h-full rounded-sm bg-slate-50 border border-slate-300 flex items-center justify-center">
              <span className="text-[0.4rem] text-purple-600 font-bold">JKR</span>
            </div>
          ) : (
            <div className={`w-full h-full rounded-sm bg-slate-50 border border-slate-300 flex items-center justify-center text-[0.5rem] font-bold ${
              getCardColor(card) === 'red' ? 'text-red-500' : 'text-slate-900'
            }`}>
              {getRankDisplay(card.rank)}{getSuitSymbol(card.suit)}
            </div>
          )}
        </div>
      ))}
      {meld.cards.length > 4 && (
        <span className="text-[0.5rem] text-slate-400 px-0.5">+{meld.cards.length - 4}</span>
      )}
      {meld.isCanasta && (
        <span className={`text-[0.5rem] font-bold px-0.5 ${
          meld.isNatural ? 'text-yellow-400' : 'text-slate-300'
        }`}>
          {meld.isNatural ? 'NAT' : 'MIX'}
        </span>
      )}
    </div>
  )
}

// ── Constants ────────────────────────────────────────────────────────

const AI_DELAY = 800

// ── Main component ───────────────────────────────────────────────────

export default function Canasta() {
  const { load, save, clear } = useGameState<SavedState>('canasta')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('canasta'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('canasta')

  const [gameState, setGameState] = useState<CanastaState>(
    () => saved?.gameState ?? createCanastaGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedCards, setSelectedCards] = useState<number[]>([])
  const aiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Persist state
  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Detect game over
  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      if (gameState.teamScores[0] > gameState.teamScores[1]) sfx.play('gin')
      setGameStatus(gameState.teamScores[0] > gameState.teamScores[1] ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  // AI auto-play
  useEffect(() => {
    if (gameState.phase === 'gameOver' || gameState.phase === 'roundOver') return
    if (gameState.currentPlayer === 0) return

    aiTimerRef.current = setTimeout(() => {
      setGameState(prev => {
        if (prev.currentPlayer === 0) return prev
        if (prev.phase === 'gameOver' || prev.phase === 'roundOver') return prev

        // Run AI turns for all non-human players in sequence
        let current = prev
        while (current.currentPlayer !== 0 &&
               current.phase !== 'gameOver' &&
               current.phase !== 'roundOver') {
          current = aiTurn(current)
        }
        return current
      })
    }, AI_DELAY)

    return () => {
      if (aiTimerRef.current) clearTimeout(aiTimerRef.current)
    }
  }, [gameState.currentPlayer, gameState.phase])

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (aiTimerRef.current) clearTimeout(aiTimerRef.current)
    }
  }, [])

  // ── Handlers ─────────────────────────────────────────────────────

  const handleDraw = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    setGameState(prev => drawFromStock(prev))
    setSelectedCards([])
  }, [])

  const handlePickupPile = useCallback(() => {
    setGameState(prev => pickupDiscardPile(prev, selectedCards))
    setSelectedCards([])
  }, [selectedCards])

  const handleMeld = useCallback(() => {
    if (selectedCards.length === 0) return
    sfx.play('meld')
    // Check if any existing team meld matches the selected cards' rank
    const player = gameState.currentPlayer
    const team = player % 2
    const hand = gameState.hands[player]
    const cards = selectedCards.map(i => hand[i]).filter(Boolean)
    const naturalCard = cards.find(c => !isWild(c))
    const rank = naturalCard?.rank

    if (rank !== undefined) {
      const existingIdx = gameState.teamMelds.findIndex(m => m.team === team && m.rank === rank)
      if (existingIdx >= 0) {
        setGameState(prev => meldCards(prev, selectedCards, existingIdx))
        setSelectedCards([])
        return
      }
    }

    setGameState(prev => meldCards(prev, selectedCards))
    setSelectedCards([])
  }, [selectedCards, gameState])

  const handleDiscard = useCallback(() => {
    if (selectedCards.length !== 1) return
    setGameState(prev => discard(prev, selectedCards[0]))
    setSelectedCards([])
  }, [selectedCards])

  const handleGoOut = useCallback(() => {
    sfx.play('knock')
    setGameState(prev => goOut(prev))
    setSelectedCards([])
  }, [])

  const handleNextRound = useCallback(() => {
    setGameState(prev => newRound(prev))
    setSelectedCards([])
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createCanastaGame())
    setGameStatus('playing')
    setSelectedCards([])
    clear()
  }, [clear])

  const toggleCardSelection = useCallback((index: number) => {
    setSelectedCards(prev =>
      prev.includes(index) ? prev.filter(i => i !== index) : [...prev, index]
    )
  }, [])

  // ── Derived state ────────────────────────────────────────────────

  const isHumanTurn = gameState.currentPlayer === 0
  const canDraw = isHumanTurn && gameState.phase === 'draw' && !gameState.hasDrawn
  const canMeld = isHumanTurn && gameState.phase === 'meld' && gameState.hasDrawn
  const canDiscard = isHumanTurn && gameState.hasDrawn && selectedCards.length === 1
  const canPickup = isHumanTurn && gameState.phase === 'draw' && !gameState.hasDrawn
  const canGoOut = isHumanTurn && gameState.phase === 'meld' && gameState.hasDrawn &&
    gameState.hands[0].length === 0 &&
    gameState.teamMelds.some(m => m.team === 0 && m.isCanasta)

  const team0Melds = gameState.teamMelds.filter(m => m.team === 0)
  const team1Melds = gameState.teamMelds.filter(m => m.team === 1)

  // ── Render ───────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex gap-3">
        <span className="text-blue-400">{TEAM_NAMES[0]}: {gameState.teamScores[0]}</span>
        <span className="text-red-400">{TEAM_NAMES[1]}: {gameState.teamScores[1]}</span>
      </div>
      <div className="flex gap-2 text-slate-400">
        <span>Stock: {gameState.stock.length}</span>
        <span>Pile: {gameState.discardPile.length}</span>
        {gameState.pileFrozen && <span className="text-cyan-400">Frozen</span>}
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Canasta" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-2">

        {/* North (Partner) */}
        <div className="text-center">
          <span className="text-xs text-blue-400">North (Partner) ({gameState.hands[2].length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[2].slice(0, 7).map((_, i) => (
              <div key={i} className={CARD_SLOT_V}><CardBack /></div>
            ))}
            {gameState.hands[2].length > 7 && (
              <span className="text-[0.6rem] text-slate-500 self-center">+{gameState.hands[2].length - 7}</span>
            )}
          </div>
          {/* North's red 3s */}
          {gameState.redThrees[2].length > 0 && (
            <div className="flex gap-0.5 justify-center mt-0.5">
              {gameState.redThrees[2].map((card, i) => (
                <div key={i} className={CARD_SLOT_V}>
                  <CardFace card={card} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* West + Center + East */}
        <div className="flex w-full items-center gap-2">
          {/* West (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">West ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
            {gameState.redThrees[3].length > 0 && (
              <div className="flex gap-0.5 justify-center mt-0.5">
                {gameState.redThrees[3].map((card, i) => (
                  <div key={i} className={CARD_SLOT_V}>
                    <CardFace card={card} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Center: Stock + Discard pile */}
          <div className="flex-1 flex items-center justify-center gap-3 h-36 sm:h-48">
            {/* Stock */}
            <div className="text-center">
              {gameState.stock.length > 0 ? (
                <div className={CARD_SIZE}>
                  <CardBack />
                </div>
              ) : (
                <div className={`${CARD_SIZE} border border-dashed border-slate-600 rounded-md flex items-center justify-center`}>
                  <span className="text-[0.6rem] text-slate-600">Empty</span>
                </div>
              )}
              <span className="text-[0.55rem] text-slate-500 mt-0.5">{gameState.stock.length}</span>
            </div>

            {/* Discard pile */}
            <div className="text-center">
              {gameState.discardPile.length > 0 ? (
                <div className={`${CARD_SIZE} ${
                  gameState.pileFrozen ? 'ring-2 ring-cyan-400' : ''
                }`}>
                  {(() => {
                    const topCard = gameState.discardPile[gameState.discardPile.length - 1]
                    return topCard.rank === 0 ? <JokerCard /> : <CardFace card={topCard} />
                  })()}
                </div>
              ) : (
                <div className={`${CARD_SIZE} border border-dashed border-slate-600 rounded-md flex items-center justify-center`}>
                  <span className="text-[0.6rem] text-slate-600">Empty</span>
                </div>
              )}
              <span className="text-[0.55rem] text-slate-500 mt-0.5">
                {gameState.discardPile.length}
                {gameState.pileFrozen ? ' (frozen)' : ''}
              </span>
            </div>
          </div>

          {/* East (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">East ({gameState.hands[1].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[1].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
            {gameState.redThrees[1].length > 0 && (
              <div className="flex gap-0.5 justify-center mt-0.5">
                {gameState.redThrees[1].map((card, i) => (
                  <div key={i} className={CARD_SLOT_V}>
                    <CardFace card={card} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Team melds */}
        {(team0Melds.length > 0 || team1Melds.length > 0) && (
          <div className="w-full space-y-1">
            {team0Melds.length > 0 && (
              <div>
                <span className="text-[0.6rem] text-blue-400">Your team&apos;s melds:</span>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {team0Melds.map((meld, i) => (
                    <MeldDisplay key={i} meld={meld} />
                  ))}
                </div>
              </div>
            )}
            {team1Melds.length > 0 && (
              <div>
                <span className="text-[0.6rem] text-red-400">Opponent melds:</span>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {team1Melds.map((meld, i) => (
                    <MeldDisplay key={i} meld={meld} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Red 3s for player 0 */}
        {gameState.redThrees[0].length > 0 && (
          <div className="flex gap-1 justify-center">
            <span className="text-[0.6rem] text-red-400 self-center mr-1">Red 3s:</span>
            {gameState.redThrees[0].map((card, i) => (
              <div key={i} className="w-8 h-12">
                <CardFace card={card} />
              </div>
            ))}
          </div>
        )}

        {/* Action buttons */}
        {isHumanTurn && gameState.phase !== 'roundOver' && gameState.phase !== 'gameOver' && (
          <div className="flex flex-wrap gap-2 justify-center">
            {canDraw && (
              <button
                onClick={handleDraw}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Draw 2
              </button>
            )}
            {canPickup && (
              <button
                onClick={handlePickupPile}
                disabled={selectedCards.length < 2}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  selectedCards.length >= 2
                    ? 'bg-amber-600 hover:bg-amber-500 text-white'
                    : 'bg-slate-700 text-slate-500 cursor-not-allowed'
                }`}
              >
                Pick Up Pile
              </button>
            )}
            {canMeld && selectedCards.length >= 1 && (
              <button
                onClick={handleMeld}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Meld Selected
              </button>
            )}
            {canDiscard && (
              <button
                onClick={handleDiscard}
                className="px-3 py-1.5 bg-orange-600 hover:bg-orange-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Discard
              </button>
            )}
            {canGoOut && (
              <button
                onClick={handleGoOut}
                className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Go Out
              </button>
            )}
          </div>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {gameState.hands[0].map((card, i) => (
            <GameCard
              key={`${card.rank}-${card.suit}-${i}`}
              card={card}
              selected={selectedCards.includes(i)}
              onClick={() => toggleCardSelection(i)}
              disabled={!isHumanTurn || gameState.phase === 'roundOver' || gameState.phase === 'gameOver'}
            />
          ))}
        </div>

        {/* Round over */}
        {gameState.phase === 'roundOver' && (
          <button
            onClick={handleNextRound}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Next Round
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
