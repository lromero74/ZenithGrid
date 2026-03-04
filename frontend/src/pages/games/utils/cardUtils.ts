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

// ── Specialized deck creators ────────────────────────────────────────

/** Create a 24-card Euchre deck (9, 10, J, Q, K, A of each suit). */
export function createEuchreDeck(): Card[] {
  const deck: Card[] = []
  for (const suit of SUITS) {
    for (const rank of [9, 10, 11, 12, 13, 1]) {
      deck.push({ suit, rank, faceUp: true })
    }
  }
  return deck
}

/** Create a 108-card double deck with 4 jokers (for Canasta). Jokers use rank 0. */
export function createDoubleDeck(): Card[] {
  const cards: Card[] = []
  for (let d = 0; d < 2; d++) {
    for (const suit of SUITS) {
      for (let rank = 1; rank <= 13; rank++) {
        cards.push({ suit, rank, faceUp: true })
      }
    }
  }
  // 4 jokers (rank 0)
  cards.push({ suit: 'spades', rank: 0, faceUp: true })
  cards.push({ suit: 'spades', rank: 0, faceUp: true })
  cards.push({ suit: 'hearts', rank: 0, faceUp: true })
  cards.push({ suit: 'hearts', rank: 0, faceUp: true })
  return cards
}
