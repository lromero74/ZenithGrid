/**
 * Freecell engine — pure logic, no React.
 *
 * All 52 cards dealt face-up across 8 columns.
 * 4 free cells for temporary storage, 4 foundations built up by suit.
 */

import { createDeck, shuffleDeck, getCardColor, type Card } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export interface FreecellState {
  tableau: Card[][]       // 8 columns, all face-up
  foundations: Card[][]   // 4 foundations (one per suit)
  freecells: (Card | null)[] // 4 free cells
  moves: number
}

// ── Deal ─────────────────────────────────────────────────────────────

export function dealFreecell(): FreecellState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const tableau: Card[][] = [[], [], [], [], [], [], [], []]

  for (let i = 0; i < 52; i++) {
    tableau[i % 8].push(deck[i])
  }

  return {
    tableau,
    foundations: [[], [], [], []],
    freecells: [null, null, null, null],
    moves: 0,
  }
}

// ── Helpers ──────────────────────────────────────────────────────────

function cloneState(state: FreecellState): FreecellState {
  return {
    tableau: state.tableau.map(col => col.map(c => ({ ...c }))),
    foundations: state.foundations.map(f => f.map(c => ({ ...c }))),
    freecells: state.freecells.map(c => c ? { ...c } : null),
    moves: state.moves,
  }
}

export function canMoveToFoundation(card: Card, foundation: Card[]): boolean {
  if (foundation.length === 0) return card.rank === 1
  const top = foundation[foundation.length - 1]
  return card.suit === top.suit && card.rank === top.rank + 1
}

export function canMoveToTableau(card: Card, column: Card[]): boolean {
  if (column.length === 0) return true
  const top = column[column.length - 1]
  return getCardColor(card) !== getCardColor(top) && card.rank === top.rank - 1
}

/** Max cards that can be moved as a stack. */
export function maxMovableCards(state: FreecellState): number {
  const emptyFreecells = state.freecells.filter(c => c === null).length
  const emptyColumns = state.tableau.filter(col => col.length === 0).length
  return (emptyFreecells + 1) * Math.pow(2, emptyColumns)
}

/** Check if a run of cards at the bottom of a column forms a valid sequence. */
function getValidRunLength(column: Card[]): number {
  if (column.length === 0) return 0
  let len = 1
  for (let i = column.length - 2; i >= 0; i--) {
    const below = column[i]
    const above = column[i + 1]
    if (getCardColor(below) !== getCardColor(above) && below.rank === above.rank + 1) {
      len++
    } else {
      break
    }
  }
  return len
}

// ── Moves ────────────────────────────────────────────────────────────

export function moveToFreecell(state: FreecellState, fromCol: number): FreecellState | null {
  const column = state.tableau[fromCol]
  if (column.length === 0) return null

  const freecellIdx = state.freecells.indexOf(null)
  if (freecellIdx === -1) return null

  const next = cloneState(state)
  const card = next.tableau[fromCol].pop()!
  next.freecells[freecellIdx] = card
  next.moves++
  return next
}

export function moveFromFreecell(state: FreecellState, cellIdx: number, toDest: 'tableau' | 'foundation', destIdx: number): FreecellState | null {
  const card = state.freecells[cellIdx]
  if (!card) return null

  if (toDest === 'foundation') {
    if (!canMoveToFoundation(card, state.foundations[destIdx])) return null
    const next = cloneState(state)
    next.freecells[cellIdx] = null
    next.foundations[destIdx].push({ ...card })
    next.moves++
    return next
  }

  if (!canMoveToTableau(card, state.tableau[destIdx])) return null
  const next = cloneState(state)
  next.freecells[cellIdx] = null
  next.tableau[destIdx].push({ ...card })
  next.moves++
  return next
}

export function moveTableauToFoundation(state: FreecellState, fromCol: number): FreecellState | null {
  const column = state.tableau[fromCol]
  if (column.length === 0) return null
  const card = column[column.length - 1]

  for (let f = 0; f < 4; f++) {
    if (canMoveToFoundation(card, state.foundations[f])) {
      const next = cloneState(state)
      next.tableau[fromCol].pop()
      next.foundations[f].push({ ...card })
      next.moves++
      return next
    }
  }
  return null
}

export function moveTableauStack(state: FreecellState, fromCol: number, cardIdx: number, toCol: number): FreecellState | null {
  if (fromCol === toCol) return null
  const column = state.tableau[fromCol]
  if (cardIdx < 0 || cardIdx >= column.length) return null

  const count = column.length - cardIdx
  if (count > maxMovableCards(state)) return null

  // Check the run is valid (alternating colors, descending)
  for (let i = cardIdx; i < column.length - 1; i++) {
    if (getCardColor(column[i]) === getCardColor(column[i + 1]) || column[i].rank !== column[i + 1].rank + 1) {
      return null
    }
  }

  const movingCard = column[cardIdx]
  if (!canMoveToTableau(movingCard, state.tableau[toCol])) return null

  const next = cloneState(state)
  const cards = next.tableau[fromCol].splice(cardIdx)
  next.tableau[toCol].push(...cards)
  next.moves++
  return next
}

// ── Win & Hint ───────────────────────────────────────────────────────

export function checkWin(state: FreecellState): boolean {
  return state.foundations.every(f => f.length === 13)
}

export interface FreecellHint {
  type: 'tableau-to-foundation' | 'freecell-to-foundation' | 'tableau-to-tableau' | 'to-freecell'
  fromCol?: number
  fromCell?: number
  toCol?: number
}

export function getHint(state: FreecellState): FreecellHint | null {
  // 1. Tableau → foundation
  for (let c = 0; c < 8; c++) {
    if (moveTableauToFoundation(state, c)) {
      return { type: 'tableau-to-foundation', fromCol: c }
    }
  }

  // 2. Freecell → foundation
  for (let i = 0; i < 4; i++) {
    const card = state.freecells[i]
    if (!card) continue
    for (let f = 0; f < 4; f++) {
      if (canMoveToFoundation(card, state.foundations[f])) {
        return { type: 'freecell-to-foundation', fromCell: i }
      }
    }
  }

  // 3. Tableau → tableau (expose longest run)
  for (let c = 0; c < 8; c++) {
    const col = state.tableau[c]
    if (col.length === 0) continue
    const runLen = getValidRunLength(col)
    const startIdx = col.length - runLen
    const card = col[startIdx]
    for (let dest = 0; dest < 8; dest++) {
      if (dest === c) continue
      if (moveTableauStack(state, c, startIdx, dest)) {
        // Skip moving king to empty column if it's already at bottom
        if (card.rank === 13 && startIdx === 0 && state.tableau[dest].length === 0) continue
        return { type: 'tableau-to-tableau', fromCol: c, toCol: dest }
      }
    }
  }

  // 4. Move to freecell
  for (let c = 0; c < 8; c++) {
    if (state.tableau[c].length > 0 && state.freecells.some(fc => fc === null)) {
      return { type: 'to-freecell', fromCol: c }
    }
  }

  return null
}
