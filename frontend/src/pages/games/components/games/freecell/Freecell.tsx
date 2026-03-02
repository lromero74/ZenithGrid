/**
 * Freecell — all cards face-up solitaire variant.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import { getSuitSymbol, type Suit } from '../../../utils/cardUtils'
import type { GameStatus } from '../../../types'
import {
  dealFreecell,
  moveToFreecell,
  moveFromFreecell,
  moveTableauToFoundation,
  moveTableauStack,
  checkWin,
  getHint,
  type FreecellState,
  type FreecellHint,
} from './freecellEngine'

interface SavedState {
  gameState: FreecellState
  gameStatus: GameStatus
}

interface Selection {
  type: 'tableau' | 'freecell'
  colOrCell: number
  cardIndex?: number
}

const FOUNDATION_SUITS: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']

export default function Freecell() {
  const { load, save, clear } = useGameState<SavedState>('freecell')
  const saved = useRef(load()).current

  const [gameState, setGameState] = useState<FreecellState>(
    () => saved?.gameState ?? dealFreecell()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selection, setSelection] = useState<Selection | null>(null)
  const [undoStack, setUndoStack] = useState<FreecellState[]>([])
  // activeHint used to highlight hint targets when Hint button pressed
  const [, setActiveHint] = useState<FreecellHint | null>(null)

  useEffect(() => {
    if (gameStatus !== 'won') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (checkWin(gameState)) {
      setGameStatus('won')
      setSelection(null)
      clear()
    }
  }, [gameState, clear])

  useEffect(() => { setActiveHint(null) }, [gameState])

  const pushUndo = useCallback((state: FreecellState) => {
    setUndoStack([state])
  }, [])

  const handleUndo = useCallback(() => {
    if (undoStack.length === 0) return
    setGameState(undoStack[0])
    setUndoStack([])
    setSelection(null)
  }, [undoStack])

  const handleHintClick = useCallback(() => {
    if (gameStatus !== 'playing') return
    const hint = getHint(gameState)
    if (hint) {
      setActiveHint(hint)
      setSelection(null)
    }
  }, [gameState, gameStatus])

  const handleNewGame = useCallback(() => {
    setGameState(dealFreecell())
    setGameStatus('playing')
    setSelection(null)
    setUndoStack([])
    setActiveHint(null)
    clear()
  }, [clear])

  // Click on a freecell slot
  const handleFreecellClick = useCallback((cellIdx: number) => {
    if (gameStatus !== 'playing') return
    const card = gameState.freecells[cellIdx]

    if (selection) {
      // Try to move selected to this freecell (only if empty)
      if (!card && selection.type === 'tableau') {
        const result = moveToFreecell(gameState, selection.colOrCell)
        if (result) {
          pushUndo(gameState)
          setGameState(result)
        }
      } else if (card && !selection) {
        // Select this freecell card
        setSelection({ type: 'freecell', colOrCell: cellIdx })
        return
      }
      setSelection(null)
      return
    }

    if (card) {
      setSelection({ type: 'freecell', colOrCell: cellIdx })
    }
  }, [gameState, gameStatus, selection, pushUndo])

  // Click on a foundation slot
  const handleFoundationClick = useCallback((fIdx: number) => {
    if (gameStatus !== 'playing' || !selection) return

    if (selection.type === 'freecell') {
      const result = moveFromFreecell(gameState, selection.colOrCell, 'foundation', fIdx)
      if (result) {
        pushUndo(gameState)
        setGameState(result)
      }
    } else if (selection.type === 'tableau') {
      const result = moveTableauToFoundation(gameState, selection.colOrCell)
      if (result) {
        pushUndo(gameState)
        setGameState(result)
      }
    }
    setSelection(null)
  }, [gameState, gameStatus, selection, pushUndo])

  // Click on tableau column/card
  const handleTableauClick = useCallback((colIdx: number, cardIdx?: number) => {
    if (gameStatus !== 'playing') return
    const col = gameState.tableau[colIdx]

    if (selection) {
      // Try to move selected cards here
      if (selection.type === 'freecell') {
        const result = moveFromFreecell(gameState, selection.colOrCell, 'tableau', colIdx)
        if (result) {
          pushUndo(gameState)
          setGameState(result)
          setSelection(null)
          return
        }
      } else if (selection.type === 'tableau') {
        const srcIdx = selection.cardIndex ?? (gameState.tableau[selection.colOrCell].length - 1)
        const result = moveTableauStack(gameState, selection.colOrCell, srcIdx, colIdx)
        if (result) {
          pushUndo(gameState)
          setGameState(result)
          setSelection(null)
          return
        }
      }

      // If click is on a card in this column, re-select
      if (cardIdx !== undefined && col[cardIdx]) {
        setSelection({ type: 'tableau', colOrCell: colIdx, cardIndex: cardIdx })
        return
      }
      setSelection(null)
      return
    }

    // Nothing selected — select this card
    if (cardIdx !== undefined && col[cardIdx]) {
      setSelection({ type: 'tableau', colOrCell: colIdx, cardIndex: cardIdx })
    }
  }, [gameState, gameStatus, selection, pushUndo])

  // Double-click on tableau card → try foundation
  const handleTableauDoubleClick = useCallback((colIdx: number) => {
    if (gameStatus !== 'playing') return
    const result = moveTableauToFoundation(gameState, colIdx)
    if (result) {
      pushUndo(gameState)
      setGameState(result)
      setSelection(null)
    }
  }, [gameState, gameStatus, pushUndo])

  const isSelected = useCallback((type: 'tableau' | 'freecell', colOrCell: number, cardIdx?: number) => {
    if (!selection || selection.type !== type || selection.colOrCell !== colOrCell) return false
    if (type === 'freecell') return true
    if (cardIdx === undefined) return false
    return cardIdx >= (selection.cardIndex ?? gameState.tableau[selection.colOrCell].length - 1)
  }, [selection, gameState])

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <button onClick={handleUndo} disabled={undoStack.length === 0}
          className="px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          Undo
        </button>
        <button onClick={handleHintClick} disabled={gameStatus !== 'playing'}
          className="px-3 py-1.5 text-xs rounded bg-emerald-700 text-emerald-100 hover:bg-emerald-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          Hint
        </button>
        <button onClick={handleNewGame}
          className="px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors">
          New Game
        </button>
      </div>
      <span className="text-xs text-slate-400">Moves: {gameState.moves}</span>
    </div>
  )

  return (
    <GameLayout title="Freecell" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-xl space-y-3">
        {/* Top row: Free cells | Foundations */}
        <div className="flex w-full justify-between gap-1">
          {/* Free cells */}
          <div className="flex gap-1 sm:gap-2">
            {gameState.freecells.map((card, i) => (
              <div
                key={`fc-${i}`}
                onClick={() => handleFreecellClick(i)}
                className={`w-11 h-[4.25rem] sm:w-14 sm:h-[5.625rem] rounded-md border border-dashed border-slate-600/50 cursor-pointer ${
                  isSelected('freecell', i) ? 'ring-2 ring-yellow-400' : ''
                }`}
              >
                {card && <CardFace card={card} selected={isSelected('freecell', i)} />}
              </div>
            ))}
          </div>

          {/* Foundations */}
          <div className="flex gap-1 sm:gap-2">
            {FOUNDATION_SUITS.map((suit, f) => (
              <div
                key={suit}
                onClick={() => handleFoundationClick(f)}
                className="w-11 h-[4.25rem] sm:w-14 sm:h-[5.625rem] rounded-md border border-dashed border-slate-600/50 cursor-pointer"
              >
                {gameState.foundations[f].length > 0 ? (
                  <CardFace card={gameState.foundations[f][gameState.foundations[f].length - 1]} />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <span className={`text-lg opacity-20 ${suit === 'hearts' || suit === 'diamonds' ? 'text-red-400' : 'text-slate-400'}`}>
                      {getSuitSymbol(suit)}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Tableau — 8 columns */}
        <div className="flex w-full gap-1 sm:gap-1.5">
          {gameState.tableau.map((col, colIdx) => (
            <div
              key={colIdx}
              className="flex-1 relative min-h-[5.5rem] sm:min-h-[6.5rem]"
              onClick={() => col.length === 0 && handleTableauClick(colIdx)}
            >
              {col.length === 0 && (
                <div className="absolute inset-x-0 top-0 h-[4.25rem] sm:h-[5.625rem] rounded-md border border-dashed border-slate-600/30" />
              )}
              {col.map((card, cardIdx) => (
                <div
                  key={cardIdx}
                  className="absolute left-0 right-0 h-[4.25rem] sm:h-[5.625rem]"
                  style={{ top: `${cardIdx * (window.innerWidth < 640 ? 16 : 22)}px` }}
                  onClick={(e) => { e.stopPropagation(); handleTableauClick(colIdx, cardIdx) }}
                  onDoubleClick={(e) => { e.stopPropagation(); handleTableauDoubleClick(colIdx) }}
                >
                  <CardFace card={card} selected={isSelected('tableau', colIdx, cardIdx)} />
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Spacer */}
        <div style={{ minHeight: `${Math.max(...gameState.tableau.map(c => c.length)) * (window.innerWidth < 640 ? 16 : 22) + 80}px` }} />

        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            score={gameState.moves}
            message={`Completed in ${gameState.moves} moves`}
            onPlayAgain={handleNewGame}
          />
        )}
      </div>
    </GameLayout>
  )
}
