/**
 * Solitaire (Klondike) engine — pure logic, no React.
 *
 * All functions are pure and return new objects (never mutate).
 */

// ── Types ────────────────────────────────────────────────────────────

export type Suit = 'hearts' | 'diamonds' | 'clubs' | 'spades'
export type Color = 'red' | 'black'

export interface Card {
  suit: Suit
  rank: number  // 1=Ace, 2-10, 11=Jack, 12=Queen, 13=King
  faceUp: boolean
}

export interface SolitaireState {
  tableau: Card[][]     // 7 piles
  foundations: Card[][] // 4 piles (one per suit)
  stock: Card[]         // draw pile
  waste: Card[]         // flipped from stock
  moves: number
}

// ── Constants ────────────────────────────────────────────────────────

const SUITS: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']

const SUIT_SYMBOLS: Record<Suit, string> = {
  hearts: '♥',
  diamonds: '♦',
  clubs: '♣',
  spades: '♠',
}

// ── Deck creation & shuffling ────────────────────────────────────────

export function createDeck(): Card[] {
  const deck: Card[] = []
  for (const suit of SUITS) {
    for (let rank = 1; rank <= 13; rank++) {
      deck.push({ suit, rank, faceUp: false })
    }
  }
  return deck
}

export function shuffleDeck(deck: Card[]): Card[] {
  const shuffled = deck.map(c => ({ ...c }))
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
  }
  return shuffled
}

// ── Dealing ──────────────────────────────────────────────────────────

export function deal(deck: Card[]): SolitaireState {
  const cards = deck.map(c => ({ ...c }))
  const tableau: Card[][] = [[], [], [], [], [], [], []]
  let idx = 0

  for (let col = 0; col < 7; col++) {
    for (let row = 0; row <= col; row++) {
      const card = { ...cards[idx++] }
      card.faceUp = row === col // only top card face-up
      tableau[col].push(card)
    }
  }

  const stock = cards.slice(idx).map(c => ({ ...c, faceUp: false }))

  return {
    tableau,
    foundations: [[], [], [], []],
    stock,
    waste: [],
    moves: 0,
  }
}

// ── Card helpers ─────────────────────────────────────────────────────

export function getCardColor(card: Card): Color {
  return card.suit === 'hearts' || card.suit === 'diamonds' ? 'red' : 'black'
}

export function getRankDisplay(rank: number): string {
  if (rank === 1) return 'A'
  if (rank === 11) return 'J'
  if (rank === 12) return 'Q'
  if (rank === 13) return 'K'
  return String(rank)
}

export function getSuitSymbol(suit: Suit): string {
  return SUIT_SYMBOLS[suit]
}

// ── Move validation ──────────────────────────────────────────────────

export function canMoveToTableau(card: Card, targetPile: Card[]): boolean {
  if (targetPile.length === 0) {
    return card.rank === 13 // only Kings on empty piles
  }
  const topCard = targetPile[targetPile.length - 1]
  return getCardColor(card) !== getCardColor(topCard) && topCard.rank === card.rank + 1
}

export function canMoveToFoundation(card: Card, foundation: Card[]): boolean {
  if (foundation.length === 0) {
    return card.rank === 1 // only Aces on empty foundations
  }
  const topCard = foundation[foundation.length - 1]
  return card.suit === topCard.suit && card.rank === topCard.rank + 1
}

// ── State helpers ────────────────────────────────────────────────────

function cloneState(state: SolitaireState): SolitaireState {
  return {
    tableau: state.tableau.map(pile => pile.map(c => ({ ...c }))),
    foundations: state.foundations.map(pile => pile.map(c => ({ ...c }))),
    stock: state.stock.map(c => ({ ...c })),
    waste: state.waste.map(c => ({ ...c })),
    moves: state.moves,
  }
}

function flipTopCard(pile: Card[]): void {
  if (pile.length > 0 && !pile[pile.length - 1].faceUp) {
    pile[pile.length - 1].faceUp = true
  }
}

// ── Moves ────────────────────────────────────────────────────────────

export function moveToTableau(
  state: SolitaireState,
  fromType: 'tableau' | 'waste',
  fromIndex: number,
  toIndex: number,
  count: number,
): SolitaireState {
  const next = cloneState(state)

  if (fromType === 'waste') {
    const card = next.waste.pop()!
    next.tableau[toIndex].push(card)
  } else {
    const fromPile = next.tableau[fromIndex]
    const moved = fromPile.splice(fromPile.length - count, count)
    next.tableau[toIndex].push(...moved)
    flipTopCard(fromPile)
  }

  next.moves++
  return next
}

export function moveToFoundation(
  state: SolitaireState,
  fromType: 'tableau' | 'waste',
  fromIndex: number,
  foundationIndex: number,
): SolitaireState {
  const next = cloneState(state)

  if (fromType === 'waste') {
    const card = next.waste.pop()!
    next.foundations[foundationIndex].push(card)
  } else {
    const fromPile = next.tableau[fromIndex]
    const card = fromPile.pop()!
    next.foundations[foundationIndex].push(card)
    flipTopCard(fromPile)
  }

  next.moves++
  return next
}

export function drawFromStock(state: SolitaireState): SolitaireState {
  const next = cloneState(state)

  if (next.stock.length > 0) {
    const card = next.stock.pop()!
    card.faceUp = true
    next.waste.push(card)
  } else {
    // Recycle waste → stock (reversed, all face-down)
    next.stock = next.waste.reverse().map(c => ({ ...c, faceUp: false }))
    next.waste = []
  }

  next.moves++
  return next
}

// ── Hint / no-moves detection ───────────────────────────────────────

export interface Hint {
  type: 'waste-to-foundation' | 'waste-to-tableau' | 'tableau-to-foundation' | 'tableau-to-tableau' | 'draw-stock'
  fromPile?: number    // source tableau pile index
  fromCard?: number    // card index within source pile (for stacks)
  toPile?: number      // destination pile/foundation index
}

/**
 * Find the best available move. Returns null when no moves remain.
 *
 * Priority: foundation moves > tableau-to-tableau (exposing hidden cards) >
 * waste-to-tableau > draw from stock / recycle waste.
 */
export function getHint(state: SolitaireState): Hint | null {
  // 1. Tableau top → foundation (always beneficial)
  for (let t = 0; t < 7; t++) {
    const pile = state.tableau[t]
    if (pile.length === 0) continue
    const card = pile[pile.length - 1]
    if (!card.faceUp) continue
    for (let f = 0; f < 4; f++) {
      if (canMoveToFoundation(card, state.foundations[f])) {
        return { type: 'tableau-to-foundation', fromPile: t, toPile: f }
      }
    }
  }

  // 2. Waste top → foundation
  if (state.waste.length > 0) {
    const card = state.waste[state.waste.length - 1]
    for (let f = 0; f < 4; f++) {
      if (canMoveToFoundation(card, state.foundations[f])) {
        return { type: 'waste-to-foundation', toPile: f }
      }
    }
  }

  // 3. Tableau → tableau (move deepest face-up run)
  for (let t = 0; t < 7; t++) {
    const pile = state.tableau[t]
    if (pile.length === 0) continue

    // Find the deepest face-up card in this pile
    let startIdx = pile.length - 1
    while (startIdx > 0 && pile[startIdx - 1].faceUp) startIdx--

    const card = pile[startIdx]
    if (!card.faceUp) continue

    for (let dest = 0; dest < 7; dest++) {
      if (dest === t) continue
      if (canMoveToTableau(card, state.tableau[dest])) {
        // Skip pointless King-to-empty-pile moves (King already at bottom)
        if (card.rank === 13 && startIdx === 0 && state.tableau[dest].length === 0) continue
        return { type: 'tableau-to-tableau', fromPile: t, fromCard: startIdx, toPile: dest }
      }
    }
  }

  // 4. Waste top → tableau
  if (state.waste.length > 0) {
    const card = state.waste[state.waste.length - 1]
    for (let t = 0; t < 7; t++) {
      if (canMoveToTableau(card, state.tableau[t])) {
        return { type: 'waste-to-tableau', toPile: t }
      }
    }
  }

  // 5. Draw from stock or recycle waste
  if (state.stock.length > 0 || state.waste.length > 0) {
    return { type: 'draw-stock' }
  }

  return null
}

// ── Win detection ────────────────────────────────────────────────────

export function checkWin(state: SolitaireState): boolean {
  return state.foundations.every(f => f.length === 13)
}

export function canAutoComplete(state: SolitaireState): boolean {
  if (state.stock.length > 0 || state.waste.length > 0) return false
  return state.tableau.every(pile => pile.every(card => card.faceUp))
}

export function autoComplete(state: SolitaireState): SolitaireState {
  let current = cloneState(state)

  // Keep moving cards to foundations until no more moves possible
  let moved = true
  while (moved) {
    moved = false
    for (let t = 0; t < 7; t++) {
      const pile = current.tableau[t]
      if (pile.length === 0) continue
      const card = pile[pile.length - 1]
      for (let f = 0; f < 4; f++) {
        if (canMoveToFoundation(card, current.foundations[f])) {
          pile.pop()
          current.foundations[f].push(card)
          current.moves++
          moved = true
          break
        }
      }
    }
  }

  return current
}
