/**
 * Shared card utilities — types and pure functions used by all card games.
 *
 * Extracted from solitaireEngine.ts to avoid duplication across
 * Solitaire, Blackjack, Hearts, Spades, Freecell, etc.
 */

// ── Types ────────────────────────────────────────────────────────────

export type Suit = 'hearts' | 'diamonds' | 'clubs' | 'spades'
export type Color = 'red' | 'black'

export interface Card {
  suit: Suit
  rank: number  // 1=Ace, 2-10, 11=Jack, 12=Queen, 13=King
  faceUp: boolean
}

// ── Constants ────────────────────────────────────────────────────────

export const SUITS: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']

export const SUIT_SYMBOLS: Record<Suit, string> = {
  hearts: '\u2665',
  diamonds: '\u2666',
  clubs: '\u2663',
  spades: '\u2660',
}

// ── Deck creation & shuffling ────────────────────────────────────────

/** Create a standard 52-card deck, all face-down. */
export function createDeck(): Card[] {
  const deck: Card[] = []
  for (const suit of SUITS) {
    for (let rank = 1; rank <= 13; rank++) {
      deck.push({ suit, rank, faceUp: false })
    }
  }
  return deck
}

/** Fisher-Yates shuffle — returns a new array (immutable). */
export function shuffleDeck(deck: Card[]): Card[] {
  const shuffled = deck.map(c => ({ ...c }))
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
  }
  return shuffled
}

/** Create a multi-deck shoe (e.g., 6 decks for Blackjack). */
export function createShoe(deckCount: number): Card[] {
  const shoe: Card[] = []
  for (let d = 0; d < deckCount; d++) {
    shoe.push(...createDeck())
  }
  return shuffleDeck(shoe)
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
