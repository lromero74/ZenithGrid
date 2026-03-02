/**
 * Solitaire (Klondike) — classic card game.
 *
 * Click-to-move interaction: select a card, then click destination.
 * Double-click to auto-send to foundation. DOM-based layout with CSS transitions.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import {
  createDeck,
  shuffleDeck,
  deal,
  canMoveToTableau,
  canMoveToFoundation,
  moveToTableau,
  moveToFoundation,
  drawFromStock,
  checkWin,
  canAutoComplete,
  autoComplete,
  getHint,
  getSuitSymbol,
  type Card,
  type SolitaireState,
  type Suit,
  type Hint,
} from './solitaireEngine'

// ── Persistence shape ────────────────────────────────────────────────

interface SavedSolitaireState {
  gameState: SolitaireState
  gameStatus: GameStatus
}

// ── Selection tracking ───────────────────────────────────────────────

interface Selection {
  type: 'tableau' | 'waste'
  pileIndex: number
  cardIndex: number  // index within the pile (for multi-card moves)
}

// ── Suit order for foundation slots ──────────────────────────────────

const FOUNDATION_SUITS: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']

// ── Component ────────────────────────────────────────────────────────

export default function Solitaire() {
  const { load, save, clear } = useGameState<SavedSolitaireState>('solitaire')
  const saved = useRef(load()).current

  const [gameState, setGameState] = useState<SolitaireState>(
    () => saved?.gameState ?? deal(shuffleDeck(createDeck()))
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selection, setSelection] = useState<Selection | null>(null)
  const [undoStack, setUndoStack] = useState<SolitaireState[]>([])
  const [autoCompleting, setAutoCompleting] = useState(false)
  const [activeHint, setActiveHint] = useState<Hint | null>(null)
  const [noMoves, setNoMoves] = useState(false)

  // Persist on changes
  useEffect(() => {
    if (gameStatus !== 'won') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Check for win after state changes
  useEffect(() => {
    if (checkWin(gameState)) {
      setGameStatus('won')
      setSelection(null)
      clear()
    }
  }, [gameState, clear])

  // Clear hint when user makes a move (gameState changes)
  useEffect(() => {
    setActiveHint(null)
  }, [gameState])

  // Check for no-moves after each state change
  useEffect(() => {
    if (gameStatus !== 'playing' || autoCompleting) {
      setNoMoves(false)
      return
    }
    setNoMoves(getHint(gameState) === null)
  }, [gameState, gameStatus, autoCompleting])

  // Auto-complete when possible
  useEffect(() => {
    if (autoCompleting || gameStatus !== 'playing') return
    if (canAutoComplete(gameState) && !checkWin(gameState)) {
      setAutoCompleting(true)
      setSelection(null)
      // Animate auto-complete with slight delays
      const timer = setTimeout(() => {
        setGameState(prev => autoComplete(prev))
        setAutoCompleting(false)
      }, 300)
      return () => clearTimeout(timer)
    }
  }, [gameState, gameStatus, autoCompleting])

  // ── Push undo ────────────────────────────────────────────────────

  const pushUndo = useCallback((state: SolitaireState) => {
    setUndoStack([state]) // max 1 level
  }, [])

  const handleUndo = useCallback(() => {
    if (undoStack.length === 0) return
    setGameState(undoStack[0])
    setUndoStack([])
    setSelection(null)
  }, [undoStack])

  // ── Hint ────────────────────────────────────────────────────────

  const handleHint = useCallback(() => {
    if (gameStatus !== 'playing' || autoCompleting) return
    const hint = getHint(gameState)
    if (hint) {
      setActiveHint(hint)
      setSelection(null)
    }
  }, [gameState, gameStatus, autoCompleting])

  // ── Try to auto-move card to foundation ──────────────────────────

  const tryAutoFoundation = useCallback((
    state: SolitaireState,
    fromType: 'tableau' | 'waste',
    fromIndex: number,
    card: Card
  ): SolitaireState | null => {
    for (let f = 0; f < 4; f++) {
      if (canMoveToFoundation(card, state.foundations[f])) {
        return moveToFoundation(state, fromType, fromIndex, f)
      }
    }
    return null
  }, [])

  // ── Handle stock click ───────────────────────────────────────────

  const handleStockClick = useCallback(() => {
    if (gameStatus !== 'playing' || autoCompleting) return
    setSelection(null)
    pushUndo(gameState)
    setGameState(drawFromStock(gameState))
  }, [gameState, gameStatus, autoCompleting, pushUndo])

  // ── Handle waste click ───────────────────────────────────────────

  const handleWasteClick = useCallback(() => {
    if (gameStatus !== 'playing' || gameState.waste.length === 0 || autoCompleting) return
    setSelection({ type: 'waste', pileIndex: 0, cardIndex: 0 })
  }, [gameState, gameStatus, autoCompleting])

  const handleWasteDoubleClick = useCallback(() => {
    if (gameStatus !== 'playing' || gameState.waste.length === 0 || autoCompleting) return
    const card = gameState.waste[gameState.waste.length - 1]
    const result = tryAutoFoundation(gameState, 'waste', 0, card)
    if (result) {
      pushUndo(gameState)
      setGameState(result)
      setSelection(null)
    }
  }, [gameState, gameStatus, autoCompleting, tryAutoFoundation, pushUndo])

  // ── Handle foundation click ──────────────────────────────────────

  const handleFoundationClick = useCallback((foundationIndex: number) => {
    if (gameStatus !== 'playing' || !selection || autoCompleting) return

    const card = selection.type === 'waste'
      ? gameState.waste[gameState.waste.length - 1]
      : gameState.tableau[selection.pileIndex][gameState.tableau[selection.pileIndex].length - 1]

    // Only top card can move to foundation
    if (selection.type === 'tableau') {
      const pile = gameState.tableau[selection.pileIndex]
      if (selection.cardIndex !== pile.length - 1) {
        setSelection(null)
        return
      }
    }

    if (card && canMoveToFoundation(card, gameState.foundations[foundationIndex])) {
      pushUndo(gameState)
      setGameState(moveToFoundation(gameState, selection.type, selection.pileIndex, foundationIndex))
    }
    setSelection(null)
  }, [gameState, gameStatus, selection, autoCompleting, pushUndo])

  // ── Handle tableau click ─────────────────────────────────────────

  const handleTableauClick = useCallback((pileIndex: number, cardIndex: number) => {
    if (gameStatus !== 'playing' || autoCompleting) return
    const pile = gameState.tableau[pileIndex]

    // Click on empty pile
    if (pile.length === 0) {
      if (selection) {
        // Try to move selected card(s) here
        const sourceCard = selection.type === 'waste'
          ? gameState.waste[gameState.waste.length - 1]
          : gameState.tableau[selection.pileIndex][selection.cardIndex]

        if (sourceCard && canMoveToTableau(sourceCard, pile)) {
          pushUndo(gameState)
          const count = selection.type === 'waste'
            ? 1
            : gameState.tableau[selection.pileIndex].length - selection.cardIndex
          setGameState(moveToTableau(gameState, selection.type, selection.pileIndex, pileIndex, count))
        }
        setSelection(null)
      }
      return
    }

    const card = pile[cardIndex]

    // Can't click face-down cards
    if (!card.faceUp) {
      setSelection(null)
      return
    }

    // If nothing selected, select this card
    if (!selection) {
      setSelection({ type: 'tableau', pileIndex, cardIndex })
      return
    }

    // If clicking the same card, deselect
    if (selection.type === 'tableau' && selection.pileIndex === pileIndex && selection.cardIndex === cardIndex) {
      setSelection(null)
      return
    }

    // Try to move selected card(s) to this pile
    const sourceCard = selection.type === 'waste'
      ? gameState.waste[gameState.waste.length - 1]
      : gameState.tableau[selection.pileIndex][selection.cardIndex]

    // Target is top card of destination pile
    if (sourceCard && canMoveToTableau(sourceCard, pile)) {
      pushUndo(gameState)
      const count = selection.type === 'waste'
        ? 1
        : gameState.tableau[selection.pileIndex].length - selection.cardIndex
      setGameState(moveToTableau(gameState, selection.type, selection.pileIndex, pileIndex, count))
      setSelection(null)
    } else {
      // Reselect if clicking a different face-up card
      setSelection({ type: 'tableau', pileIndex, cardIndex })
    }
  }, [gameState, gameStatus, selection, autoCompleting, pushUndo])

  const handleTableauDoubleClick = useCallback((pileIndex: number, cardIndex: number) => {
    if (gameStatus !== 'playing' || autoCompleting) return
    const pile = gameState.tableau[pileIndex]
    if (cardIndex !== pile.length - 1) return // only top card

    const card = pile[cardIndex]
    if (!card.faceUp) return

    const result = tryAutoFoundation(gameState, 'tableau', pileIndex, card)
    if (result) {
      pushUndo(gameState)
      setGameState(result)
      setSelection(null)
    }
  }, [gameState, gameStatus, autoCompleting, tryAutoFoundation, pushUndo])

  // ── New game ─────────────────────────────────────────────────────

  const handleNewGame = useCallback(() => {
    const newState = deal(shuffleDeck(createDeck()))
    setGameState(newState)
    setGameStatus('playing')
    setSelection(null)
    setUndoStack([])
    setAutoCompleting(false)
    setActiveHint(null)
    setNoMoves(false)
    clear()
  }, [clear])

  // ── Check if a card is selected ──────────────────────────────────

  const isSelected = useCallback((type: 'tableau' | 'waste', pileIndex: number, cardIndex: number) => {
    if (!selection) return false
    if (selection.type !== type) return false
    if (type === 'waste') return true
    return selection.pileIndex === pileIndex && cardIndex >= selection.cardIndex
  }, [selection])

  // ── Valid destination highlighting ───────────────────────────────

  const validDestinations = useMemo(() => {
    if (!selection || gameStatus !== 'playing') return { tableau: new Set<number>(), foundations: new Set<number>() }

    const card = selection.type === 'waste'
      ? gameState.waste[gameState.waste.length - 1]
      : gameState.tableau[selection.pileIndex][selection.cardIndex]

    if (!card) return { tableau: new Set<number>(), foundations: new Set<number>() }

    const tableau = new Set<number>()
    const foundations = new Set<number>()

    for (let i = 0; i < 7; i++) {
      if (selection.type === 'tableau' && i === selection.pileIndex) continue
      if (canMoveToTableau(card, gameState.tableau[i])) tableau.add(i)
    }

    // Only top card can go to foundation
    const isTopCard = selection.type === 'waste' ||
      selection.cardIndex === gameState.tableau[selection.pileIndex].length - 1
    if (isTopCard) {
      for (let f = 0; f < 4; f++) {
        if (canMoveToFoundation(card, gameState.foundations[f])) foundations.add(f)
      }
    }

    return { tableau, foundations }
  }, [selection, gameState, gameStatus])

  // ── Controls ─────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <button
          onClick={handleUndo}
          disabled={undoStack.length === 0}
          className="px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Undo
        </button>
        <button
          onClick={handleHint}
          disabled={gameStatus !== 'playing' || noMoves}
          className="px-3 py-1.5 text-xs rounded bg-emerald-700 text-emerald-100 hover:bg-emerald-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Hint
        </button>
        <button
          onClick={handleNewGame}
          className="px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          New Game
        </button>
      </div>
      <span className="text-xs text-slate-400">Moves: {gameState.moves}</span>
    </div>
  )

  // ── Render ───────────────────────────────────────────────────────

  return (
    <GameLayout title="Solitaire" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* Top row: Stock + Waste | Foundations */}
        <div className="flex w-full justify-between gap-2">
          {/* Stock + Waste */}
          <div className="flex gap-2">
            {/* Stock */}
            <div
              onClick={handleStockClick}
              className={`card-slot cursor-pointer ${gameState.stock.length > 0 ? '' : 'empty'} ${activeHint?.type === 'draw-stock' ? 'ring-2 ring-amber-400 animate-pulse' : ''}`}
            >
              {gameState.stock.length > 0 ? (
                <CardBack />
              ) : gameState.waste.length > 0 ? (
                <div className="w-full h-full flex items-center justify-center">
                  <span className="text-slate-500 text-lg">↻</span>
                </div>
              ) : null}
            </div>

            {/* Waste */}
            <div
              onClick={handleWasteClick}
              onDoubleClick={handleWasteDoubleClick}
              className="card-slot"
            >
              {gameState.waste.length > 0 ? (
                <CardFace
                  card={gameState.waste[gameState.waste.length - 1]}
                  selected={isSelected('waste', 0, 0)}
                  hinted={activeHint?.type === 'waste-to-foundation' || activeHint?.type === 'waste-to-tableau'}
                />
              ) : null}
            </div>
          </div>

          {/* Foundations */}
          <div className="flex gap-2">
            {FOUNDATION_SUITS.map((suit, f) => (
              <div
                key={suit}
                onClick={() => handleFoundationClick(f)}
                className={`card-slot ${validDestinations.foundations.has(f) ? 'ring-2 ring-emerald-400/60' : ''} ${
                  (activeHint?.type === 'tableau-to-foundation' || activeHint?.type === 'waste-to-foundation') && activeHint?.toPile === f
                    ? 'ring-2 ring-amber-400 animate-pulse' : ''
                }`}
              >
                {gameState.foundations[f].length > 0 ? (
                  <CardFace card={gameState.foundations[f][gameState.foundations[f].length - 1]} />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <span className={`text-xl opacity-20 ${suit === 'hearts' || suit === 'diamonds' ? 'text-red-400' : 'text-slate-400'}`}>
                      {getSuitSymbol(suit)}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Tableau */}
        <div className="flex w-full gap-1.5 sm:gap-2">
          {gameState.tableau.map((pile, pileIdx) => (
            <div
              key={pileIdx}
              className={`flex-1 relative min-h-[5.5rem] sm:min-h-[6.5rem] ${
                pile.length === 0 && validDestinations.tableau.has(pileIdx) ? 'ring-2 ring-emerald-400/60 rounded-lg' : ''
              } ${
                pile.length === 0 && (activeHint?.type === 'tableau-to-tableau' || activeHint?.type === 'waste-to-tableau') && activeHint?.toPile === pileIdx ? 'ring-2 ring-amber-400 animate-pulse rounded-lg' : ''
              }`}
              onClick={() => pile.length === 0 && handleTableauClick(pileIdx, 0)}
            >
              {pile.length === 0 && (
                <div className="card-slot absolute inset-x-0 top-0 opacity-30" />
              )}
              {pile.map((card, cardIdx) => (
                <div
                  key={cardIdx}
                  className="absolute left-0 right-0 transition-transform duration-200 h-[4.25rem] sm:h-[5.625rem]"
                  style={{ top: `${cardIdx * (window.innerWidth < 640 ? 16 : 22)}px` }}
                  onClick={(e) => { e.stopPropagation(); handleTableauClick(pileIdx, cardIdx) }}
                  onDoubleClick={(e) => { e.stopPropagation(); handleTableauDoubleClick(pileIdx, cardIdx) }}
                >
                  {card.faceUp ? (
                    <CardFace
                      card={card}
                      selected={isSelected('tableau', pileIdx, cardIdx)}
                      validTarget={validDestinations.tableau.has(pileIdx) && cardIdx === pile.length - 1}
                      hinted={
                        (activeHint?.type === 'tableau-to-foundation' && activeHint.fromPile === pileIdx && cardIdx === pile.length - 1) ||
                        (activeHint?.type === 'tableau-to-tableau' && activeHint.fromPile === pileIdx && activeHint.fromCard !== undefined && cardIdx >= activeHint.fromCard) ||
                        ((activeHint?.type === 'tableau-to-tableau' || activeHint?.type === 'waste-to-tableau') && activeHint.toPile === pileIdx && cardIdx === pile.length - 1)
                      }
                    />
                  ) : (
                    <CardBack />
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Spacer for stacked cards */}
        <div style={{ minHeight: `${Math.max(...gameState.tableau.map(p => p.length)) * (window.innerWidth < 640 ? 16 : 22) + 80}px` }} />

        {/* No moves warning */}
        {noMoves && gameStatus === 'playing' && (
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 flex justify-center z-20 pointer-events-none">
            <div className="bg-red-900/90 text-red-100 px-6 py-3 rounded-lg shadow-lg text-center pointer-events-auto">
              <p className="font-semibold text-sm">No more moves available</p>
              <button
                onClick={handleNewGame}
                className="mt-2 px-4 py-1.5 text-xs rounded bg-red-700 hover:bg-red-600 transition-colors"
              >
                New Game
              </button>
            </div>
          </div>
        )}

        {/* Win overlay */}
        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            score={gameState.moves}
            message={`Completed in ${gameState.moves} moves`}
            onPlayAgain={handleNewGame}
          />
        )}
      </div>

      {/* Scoped styles */}
      <style>{`
        .card-slot {
          width: 3rem;
          height: 4.25rem;
          border-radius: 0.375rem;
          border: 1px dashed rgb(100 116 139 / 0.3);
          flex-shrink: 0;
        }
        .card-slot.empty {
          border-style: dashed;
        }
        @media (min-width: 640px) {
          .card-slot {
            width: 4rem;
            height: 5.625rem;
          }
        }
      `}</style>
    </GameLayout>
  )
}

