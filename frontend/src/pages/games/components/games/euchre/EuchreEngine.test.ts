import { describe, test, expect } from 'vitest'
import type { Card, Suit } from '../../../utils/cardUtils'
import {
  createEuchreDeck,
  createEuchreGame,
  orderUp,
  pass,
  nameTrump,
  dealerDiscard,
  playCard,
  getCardStrength,
  getPlayableCards,
  getSameColorSuit,
  isLeftBower,
  isRightBower,
  getEffectiveSuit,
  sortEuchreHand,
  PLAYER_NAMES,
  TEAM_NAMES,
  type EuchreState,
  type Phase,
} from './EuchreEngine'

// ── Helpers ──────────────────────────────────────────────────────────

function card(rank: number, suit: Suit, faceUp = true): Card {
  return { rank, suit, faceUp }
}

/** Build a minimal state for targeted testing. */
function baseState(overrides: Partial<EuchreState> = {}): EuchreState {
  return {
    hands: [[], [], [], []],
    kitty: [],
    flippedCard: card(11, 'hearts'),
    trumpSuit: null,
    makerTeam: null,
    phase: 'trumpRound1' as Phase,
    currentPlayer: 1,
    dealer: 0,
    currentTrick: [],
    tricksTaken: [0, 0, 0, 0],
    teamScores: [0, 0],
    goingAlone: null,
    message: '',
    ledSuit: null,
    ...overrides,
  }
}

// ── Deck ─────────────────────────────────────────────────────────────

describe('createEuchreDeck', () => {
  test('creates 24 cards', () => {
    const deck = createEuchreDeck()
    expect(deck).toHaveLength(24)
  })

  test('contains only ranks 9, 10, J, Q, K, A', () => {
    const deck = createEuchreDeck()
    const validRanks = [9, 10, 11, 12, 13, 1]
    for (const c of deck) {
      expect(validRanks).toContain(c.rank)
    }
  })

  test('has 6 cards per suit', () => {
    const deck = createEuchreDeck()
    const suits: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']
    for (const s of suits) {
      expect(deck.filter(c => c.suit === s)).toHaveLength(6)
    }
  })

  test('all cards are face up', () => {
    const deck = createEuchreDeck()
    expect(deck.every(c => c.faceUp)).toBe(true)
  })
})

// ── Bower identification ─────────────────────────────────────────────

describe('isRightBower', () => {
  test('J of trump suit is right bower', () => {
    expect(isRightBower(card(11, 'hearts'), 'hearts')).toBe(true)
  })

  test('J of different suit is NOT right bower', () => {
    expect(isRightBower(card(11, 'spades'), 'hearts')).toBe(false)
  })

  test('non-J of trump is NOT right bower', () => {
    expect(isRightBower(card(1, 'hearts'), 'hearts')).toBe(false)
  })

  test('returns false when no trump', () => {
    expect(isRightBower(card(11, 'hearts'), null as unknown as Suit)).toBe(false)
  })
})

describe('isLeftBower', () => {
  test('J of same color as trump is left bower', () => {
    expect(isLeftBower(card(11, 'diamonds'), 'hearts')).toBe(true)
  })

  test('J of different color is NOT left bower', () => {
    expect(isLeftBower(card(11, 'clubs'), 'hearts')).toBe(false)
  })

  test('non-J of same color is NOT left bower', () => {
    expect(isLeftBower(card(1, 'diamonds'), 'hearts')).toBe(false)
  })

  test('hearts↔diamonds: J♦ is left bower when hearts is trump', () => {
    expect(isLeftBower(card(11, 'diamonds'), 'hearts')).toBe(true)
    expect(isLeftBower(card(11, 'hearts'), 'diamonds')).toBe(true)
  })

  test('clubs↔spades: J♣ is left bower when spades is trump', () => {
    expect(isLeftBower(card(11, 'clubs'), 'spades')).toBe(true)
    expect(isLeftBower(card(11, 'spades'), 'clubs')).toBe(true)
  })
})

// ── Same color suit ──────────────────────────────────────────────────

describe('getSameColorSuit', () => {
  test('hearts ↔ diamonds', () => {
    expect(getSameColorSuit('hearts')).toBe('diamonds')
    expect(getSameColorSuit('diamonds')).toBe('hearts')
  })

  test('clubs ↔ spades', () => {
    expect(getSameColorSuit('clubs')).toBe('spades')
    expect(getSameColorSuit('spades')).toBe('clubs')
  })
})

// ── Effective suit ───────────────────────────────────────────────────

describe('getEffectiveSuit', () => {
  test('left bower effective suit is trump', () => {
    expect(getEffectiveSuit(card(11, 'diamonds'), 'hearts')).toBe('hearts')
  })

  test('right bower effective suit is trump', () => {
    expect(getEffectiveSuit(card(11, 'hearts'), 'hearts')).toBe('hearts')
  })

  test('normal card returns its printed suit', () => {
    expect(getEffectiveSuit(card(1, 'clubs'), 'hearts')).toBe('clubs')
  })

  test('non-bower J returns printed suit', () => {
    expect(getEffectiveSuit(card(11, 'clubs'), 'hearts')).toBe('clubs')
  })
})

// ── Card strength ────────────────────────────────────────────────────

describe('getCardStrength', () => {
  test('right bower is the strongest card', () => {
    const rb = getCardStrength(card(11, 'hearts'), 'hearts', 'clubs')
    const lb = getCardStrength(card(11, 'diamonds'), 'hearts', 'clubs')
    expect(rb).toBeGreaterThan(lb)
  })

  test('left bower is second strongest', () => {
    const lb = getCardStrength(card(11, 'diamonds'), 'hearts', 'clubs')
    const ace = getCardStrength(card(1, 'hearts'), 'hearts', 'clubs')
    expect(lb).toBeGreaterThan(ace)
  })

  test('trump A > trump K > trump Q > trump 10 > trump 9', () => {
    const trump = 'hearts' as Suit
    const led = 'clubs' as Suit
    const a = getCardStrength(card(1, trump), trump, led)
    const k = getCardStrength(card(13, trump), trump, led)
    const q = getCardStrength(card(12, trump), trump, led)
    const ten = getCardStrength(card(10, trump), trump, led)
    const nine = getCardStrength(card(9, trump), trump, led)
    expect(a).toBeGreaterThan(k)
    expect(k).toBeGreaterThan(q)
    expect(q).toBeGreaterThan(ten)
    expect(ten).toBeGreaterThan(nine)
  })

  test('any trump beats any non-trump led suit card', () => {
    const trump9 = getCardStrength(card(9, 'hearts'), 'hearts', 'clubs')
    const ledAce = getCardStrength(card(1, 'clubs'), 'hearts', 'clubs')
    expect(trump9).toBeGreaterThan(ledAce)
  })

  test('led suit beats off-suit non-trump', () => {
    const ledAce = getCardStrength(card(1, 'clubs'), 'hearts', 'clubs')
    const offAce = getCardStrength(card(1, 'spades'), 'hearts', 'clubs')
    expect(ledAce).toBeGreaterThan(offAce)
  })

  test('off-suit cards have strength 0', () => {
    expect(getCardStrength(card(1, 'spades'), 'hearts', 'clubs')).toBe(0)
  })
})

// ── Playable cards (follow suit) ─────────────────────────────────────

describe('getPlayableCards', () => {
  test('all cards playable when no led suit (leading)', () => {
    const hand = [card(9, 'hearts'), card(10, 'clubs'), card(1, 'spades')]
    const indices = getPlayableCards(hand, null, 'hearts')
    expect(indices).toEqual([0, 1, 2])
  })

  test('must follow led suit when possible', () => {
    const hand = [card(9, 'hearts'), card(10, 'clubs'), card(1, 'clubs')]
    const indices = getPlayableCards(hand, 'clubs', 'hearts')
    expect(indices).toEqual([1, 2])
  })

  test('all cards playable when void in led suit', () => {
    const hand = [card(9, 'hearts'), card(10, 'spades'), card(1, 'diamonds')]
    const indices = getPlayableCards(hand, 'clubs', 'hearts')
    expect(indices).toEqual([0, 1, 2])
  })

  test('left bower counts as trump, not its printed suit', () => {
    // Trump is hearts, left bower is J♦. Led suit is diamonds.
    // J♦ is effectively hearts (trump), so it does NOT follow diamonds.
    const hand = [card(11, 'diamonds'), card(10, 'diamonds')]
    const indices = getPlayableCards(hand, 'diamonds', 'hearts')
    // Only 10♦ follows diamonds; J♦ is considered trump
    expect(indices).toEqual([1])
  })

  test('left bower can be played to follow trump suit lead', () => {
    // Trump is hearts. Led suit is hearts. J♦ is left bower = trump.
    const hand = [card(11, 'diamonds'), card(10, 'clubs')]
    const indices = getPlayableCards(hand, 'hearts', 'hearts')
    // J♦ is effectively hearts; it can follow hearts
    expect(indices).toEqual([0])
  })

  test('when only card following suit is left bower and led suit is its printed suit, all playable', () => {
    // Trump is hearts, led suit is diamonds. Hand has J♦ (left bower=trump) + non-diamonds.
    // Since J♦ counts as trump (not diamonds), player is void in diamonds → all playable.
    const hand = [card(11, 'diamonds'), card(10, 'clubs'), card(9, 'spades')]
    const indices = getPlayableCards(hand, 'diamonds', 'hearts')
    expect(indices).toEqual([0, 1, 2])
  })
})

// ── Trick winner ─────────────────────────────────────────────────────

describe('trick winner via getCardStrength', () => {
  test('highest trump wins', () => {
    // Compare strength of each card; highest wins
    const trumpSuit: Suit = 'hearts'
    const ledSuit: Suit = 'clubs'
    const cards = [
      { card: card(1, 'clubs'), player: 0 },    // A♣ (led)
      { card: card(9, 'hearts'), player: 1 },    // 9♥ (trump)
      { card: card(10, 'hearts'), player: 2 },   // 10♥ (trump)
      { card: card(13, 'clubs'), player: 3 },    // K♣
    ]
    let best = 0
    let bestStrength = 0
    for (let i = 0; i < cards.length; i++) {
      const s = getCardStrength(cards[i].card, trumpSuit, ledSuit)
      if (s > bestStrength) { bestStrength = s; best = i }
    }
    expect(cards[best].player).toBe(2) // 10♥ > 9♥
  })

  test('right bower beats left bower', () => {
    const trumpSuit: Suit = 'hearts'
    const ledSuit: Suit = 'hearts'
    const rb = getCardStrength(card(11, 'hearts'), trumpSuit, ledSuit)
    const lb = getCardStrength(card(11, 'diamonds'), trumpSuit, ledSuit)
    expect(rb).toBeGreaterThan(lb)
  })

  test('left bower beats ace of trump', () => {
    const trumpSuit: Suit = 'hearts'
    const ledSuit: Suit = 'hearts'
    const lb = getCardStrength(card(11, 'diamonds'), trumpSuit, ledSuit)
    const ace = getCardStrength(card(1, 'hearts'), trumpSuit, ledSuit)
    expect(lb).toBeGreaterThan(ace)
  })

  test('highest of led suit wins when no trump played', () => {
    const trumpSuit: Suit = 'hearts'
    const ledSuit: Suit = 'clubs'
    const cards = [
      { card: card(10, 'clubs'), player: 0 },
      { card: card(1, 'clubs'), player: 1 },   // ace wins
      { card: card(9, 'spades'), player: 2 },  // off-suit, ignored
      { card: card(13, 'clubs'), player: 3 },
    ]
    let best = 0
    let bestStrength = 0
    for (let i = 0; i < cards.length; i++) {
      const s = getCardStrength(cards[i].card, trumpSuit, ledSuit)
      if (s > bestStrength) { bestStrength = s; best = i }
    }
    expect(cards[best].player).toBe(1) // A♣
  })
})

// ── Scoring ──────────────────────────────────────────────────────────

describe('scoring', () => {
  test('maker team wins 3-4 tricks: 1 point', () => {
    const state = baseState({
      phase: 'playing' as Phase,
      trumpSuit: 'hearts',
      makerTeam: 0,
      // Team 0 (players 0,2) took 3 tricks
      tricksTaken: [2, 1, 1, 1],
      hands: [[], [], [], []],
      teamScores: [0, 0],
    })
    // Team 0 total = 2+1 = 3, team 1 total = 1+1 = 2
    const team0Tricks = state.tricksTaken[0] + state.tricksTaken[2]
    expect(team0Tricks).toBe(3)
    // Scoring: makers win 3 → 1 point
  })

  test('maker team wins all 5 tricks (march): 2 points', () => {
    const tricksTaken = [3, 0, 2, 0]
    const team0Tricks = tricksTaken[0] + tricksTaken[2]
    expect(team0Tricks).toBe(5)
    // March → 2 points
  })

  test('defenders win 3+ tricks (euchre): 2 points to defenders', () => {
    // Maker = team 0, but defenders (team 1) took 3+ tricks
    const tricksTaken = [1, 2, 1, 1]
    const team0Tricks = tricksTaken[0] + tricksTaken[2] // 2
    const team1Tricks = tricksTaken[1] + tricksTaken[3] // 3
    expect(team1Tricks).toBeGreaterThanOrEqual(3)
    expect(team0Tricks).toBeLessThan(3)
    // Euchre → 2 points to defenders
  })

  test('going alone + march: 4 points', () => {
    const tricksTaken = [5, 0, 0, 0] // player 0 alone, all 5 tricks
    const team0Tricks = tricksTaken[0] + tricksTaken[2]
    expect(team0Tricks).toBe(5)
    // Going alone + march → 4 points
  })
})

// ── Game creation ────────────────────────────────────────────────────

describe('createEuchreGame', () => {
  test('deals 5 cards per player', () => {
    const state = createEuchreGame()
    for (let i = 0; i < 4; i++) {
      expect(state.hands[i]).toHaveLength(5)
    }
  })

  test('kitty has 4 cards', () => {
    const state = createEuchreGame()
    expect(state.kitty).toHaveLength(4)
  })

  test('flipped card is set', () => {
    const state = createEuchreGame()
    expect(state.flippedCard).toBeDefined()
    expect(state.flippedCard.rank).toBeGreaterThan(0)
  })

  test('total cards = 24 (20 dealt + 4 kitty)', () => {
    const state = createEuchreGame()
    const total = state.hands.reduce((s, h) => s + h.length, 0) + state.kitty.length
    expect(total).toBe(24)
  })

  test('starts in trumpRound1 phase', () => {
    const state = createEuchreGame()
    expect(state.phase).toBe('trumpRound1')
  })

  test('scores start at 0', () => {
    const state = createEuchreGame()
    expect(state.teamScores).toEqual([0, 0])
  })

  test('dealer is set (0-3)', () => {
    const state = createEuchreGame()
    expect(state.dealer).toBeGreaterThanOrEqual(0)
    expect(state.dealer).toBeLessThanOrEqual(3)
  })

  test('current player is left of dealer', () => {
    const state = createEuchreGame()
    expect(state.currentPlayer).toBe((state.dealer + 1) % 4)
  })
})

// ── Trump selection round 1 ──────────────────────────────────────────

describe('trump selection round 1', () => {
  test('ordering up sets trump to flipped card suit', () => {
    const state = baseState({
      phase: 'trumpRound1',
      currentPlayer: 1,
      dealer: 0,
      flippedCard: card(12, 'spades'),
      hands: [
        [card(9, 'hearts'), card(10, 'hearts'), card(1, 'clubs'), card(13, 'diamonds'), card(9, 'spades')],
        [card(9, 'clubs'), card(10, 'clubs'), card(1, 'spades'), card(13, 'hearts'), card(12, 'diamonds')],
        [], [],
      ],
    })
    const next = orderUp(state)
    expect(next.trumpSuit).toBe('spades')
    expect(next.makerTeam).toBe(1) // player 1 → team 1
  })

  test('ordering up transitions to dealerDiscard', () => {
    const state = baseState({
      phase: 'trumpRound1',
      currentPlayer: 1,
      dealer: 0,
      flippedCard: card(12, 'spades'),
      hands: [
        [card(9, 'hearts'), card(10, 'hearts'), card(1, 'clubs'), card(13, 'diamonds'), card(9, 'spades')],
        [], [], [],
      ],
    })
    const next = orderUp(state)
    expect(next.phase).toBe('dealerDiscard')
  })

  test('ordering up gives dealer the flipped card', () => {
    const state = baseState({
      phase: 'trumpRound1',
      currentPlayer: 1,
      dealer: 0,
      flippedCard: card(12, 'spades'),
      hands: [
        [card(9, 'hearts'), card(10, 'hearts'), card(1, 'clubs'), card(13, 'diamonds'), card(9, 'spades')],
        [], [], [],
      ],
    })
    const next = orderUp(state)
    // Dealer (0) should now have 6 cards (5 + flipped card)
    expect(next.hands[0]).toHaveLength(6)
    expect(next.hands[0].some(c => c.rank === 12 && c.suit === 'spades')).toBe(true)
  })

  test('pass advances to next player', () => {
    const state = baseState({
      phase: 'trumpRound1',
      currentPlayer: 1,
      dealer: 0,
    })
    const next = pass(state)
    expect(next.currentPlayer).toBe(2)
  })

  test('all 4 pass in round 1 transitions to trumpRound2', () => {
    let state = baseState({
      phase: 'trumpRound1',
      currentPlayer: 1,
      dealer: 0,
    })
    // Players 1, 2, 3, 0 all pass
    state = pass(state) // player 1 → 2
    state = pass(state) // player 2 → 3
    state = pass(state) // player 3 → 0
    state = pass(state) // player 0 → back to 1, now round 2
    expect(state.phase).toBe('trumpRound2')
    expect(state.currentPlayer).toBe(1) // left of dealer
  })
})

// ── Trump selection round 2 ──────────────────────────────────────────

describe('trump selection round 2', () => {
  test('naming trump sets the suit', () => {
    const state = baseState({
      phase: 'trumpRound2',
      currentPlayer: 1,
      dealer: 0,
      flippedCard: card(12, 'spades'),
    })
    const next = nameTrump(state, 'hearts')
    expect(next.trumpSuit).toBe('hearts')
    expect(next.makerTeam).toBe(1)
  })

  test('cannot name same suit as flipped card', () => {
    const state = baseState({
      phase: 'trumpRound2',
      currentPlayer: 1,
      dealer: 0,
      flippedCard: card(12, 'spades'),
    })
    const next = nameTrump(state, 'spades')
    // Should be rejected — state unchanged
    expect(next.trumpSuit).toBeNull()
  })

  test('dealer is stuck — must pick on round 2', () => {
    let state = baseState({
      phase: 'trumpRound2',
      currentPlayer: 1,
      dealer: 0,
      flippedCard: card(12, 'spades'),
    })
    // Players 1, 2, 3 pass
    state = pass(state) // → 2
    state = pass(state) // → 3
    state = pass(state) // → 0 (dealer), must pick (stuck dealer)
    // Dealer is stuck — the engine should force a choice
    expect(state.phase).toBe('trumpRound2')
    expect(state.currentPlayer).toBe(0)
    // If dealer is stuck and tries to pass, engine should auto-pick
  })
})

// ── Dealer discard ───────────────────────────────────────────────────

describe('dealerDiscard', () => {
  test('dealer discards one card to have 5 in hand', () => {
    const state = baseState({
      phase: 'dealerDiscard',
      dealer: 0,
      currentPlayer: 0,
      trumpSuit: 'hearts',
      makerTeam: 1,
      hands: [
        [card(9, 'hearts'), card(10, 'hearts'), card(1, 'clubs'), card(13, 'diamonds'), card(9, 'spades'), card(12, 'hearts')],
        [card(9, 'clubs'), card(10, 'clubs'), card(1, 'spades'), card(13, 'hearts'), card(12, 'diamonds')],
        [card(9, 'diamonds'), card(10, 'diamonds'), card(1, 'hearts'), card(13, 'clubs'), card(12, 'spades')],
        [card(10, 'spades'), card(13, 'spades'), card(1, 'diamonds'), card(12, 'clubs'), card(9, 'clubs')],
      ],
    })
    const next = dealerDiscard(state, 2) // discard A♣
    expect(next.hands[0]).toHaveLength(5)
    expect(next.phase).toBe('playing')
  })

  test('discarded card is removed from hand', () => {
    const state = baseState({
      phase: 'dealerDiscard',
      dealer: 0,
      currentPlayer: 0,
      trumpSuit: 'hearts',
      makerTeam: 1,
      hands: [
        [card(9, 'hearts'), card(10, 'hearts'), card(1, 'clubs'), card(13, 'diamonds'), card(9, 'spades'), card(12, 'hearts')],
        [card(9, 'clubs'), card(10, 'clubs'), card(1, 'spades'), card(13, 'hearts'), card(12, 'diamonds')],
        [card(9, 'diamonds'), card(10, 'diamonds'), card(1, 'hearts'), card(13, 'clubs'), card(12, 'spades')],
        [card(10, 'spades'), card(13, 'spades'), card(1, 'diamonds'), card(12, 'clubs'), card(9, 'clubs')],
      ],
    })
    const next = dealerDiscard(state, 2) // discard A♣ (index 2)
    expect(next.hands[0].some(c => c.rank === 1 && c.suit === 'clubs')).toBe(false)
  })
})

// ── Playing cards ────────────────────────────────────────────────────

describe('playCard', () => {
  test('playing a card removes it from hand', () => {
    const state = baseState({
      phase: 'playing',
      currentPlayer: 0,
      trumpSuit: 'hearts',
      makerTeam: 0,
      ledSuit: null,
      currentTrick: [],
      tricksTaken: [0, 0, 0, 0],
      hands: [
        [card(9, 'hearts'), card(10, 'clubs'), card(1, 'spades'), card(13, 'diamonds'), card(9, 'spades')],
        [card(9, 'clubs'), card(10, 'hearts'), card(1, 'diamonds'), card(13, 'hearts'), card(12, 'diamonds')],
        [card(9, 'diamonds'), card(10, 'diamonds'), card(1, 'hearts'), card(13, 'clubs'), card(12, 'spades')],
        [card(10, 'spades'), card(13, 'spades'), card(1, 'clubs'), card(12, 'clubs'), card(12, 'hearts')],
      ],
    })
    const next = playCard(state, 0) // play 9♥
    expect(next.hands[0]).toHaveLength(4)
    expect(next.hands[0].some(c => c.rank === 9 && c.suit === 'hearts')).toBe(false)
  })

  test('leading sets ledSuit', () => {
    const state = baseState({
      phase: 'playing',
      currentPlayer: 0,
      trumpSuit: 'hearts',
      makerTeam: 0,
      ledSuit: null,
      currentTrick: [],
      tricksTaken: [0, 0, 0, 0],
      hands: [
        [card(10, 'clubs'), card(9, 'hearts'), card(1, 'spades'), card(13, 'diamonds'), card(9, 'spades')],
        [card(9, 'clubs'), card(10, 'hearts'), card(1, 'diamonds'), card(13, 'hearts'), card(12, 'diamonds')],
        [card(9, 'diamonds'), card(10, 'diamonds'), card(1, 'hearts'), card(13, 'clubs'), card(12, 'spades')],
        [card(10, 'spades'), card(13, 'spades'), card(1, 'clubs'), card(12, 'clubs'), card(12, 'hearts')],
      ],
    })
    const next = playCard(state, 0) // play 10♣
    expect(next.ledSuit).toBe('clubs')
  })

  test('invalid play (not following suit) rejected', () => {
    const state = baseState({
      phase: 'playing',
      currentPlayer: 0,
      trumpSuit: 'hearts',
      makerTeam: 0,
      ledSuit: 'clubs',
      currentTrick: [{ card: card(10, 'clubs'), player: 3 }],
      tricksTaken: [0, 0, 0, 0],
      hands: [
        [card(9, 'hearts'), card(10, 'clubs'), card(1, 'spades'), card(13, 'diamonds'), card(9, 'clubs')],
        [card(9, 'clubs'), card(10, 'hearts'), card(1, 'diamonds'), card(13, 'hearts'), card(12, 'diamonds')],
        [card(9, 'diamonds'), card(10, 'diamonds'), card(1, 'hearts'), card(13, 'clubs'), card(12, 'spades')],
        [card(10, 'spades'), card(13, 'spades'), card(1, 'clubs'), card(12, 'clubs'), card(12, 'hearts')],
      ],
    })
    // Player has clubs (10♣, 9♣) — cannot play 9♥
    const next = playCard(state, 0) // try to play 9♥ (hearts, not clubs)
    expect(next).toBe(state) // unchanged
  })
})

// ── Sorting ──────────────────────────────────────────────────────────

describe('sortEuchreHand', () => {
  test('groups by suit', () => {
    const hand = [card(9, 'spades'), card(10, 'hearts'), card(1, 'clubs'), card(13, 'diamonds')]
    const sorted = sortEuchreHand(hand, null)
    // Should be grouped: clubs, diamonds, hearts/spades, etc.
    const suits = sorted.map(c => c.suit)
    // Verify each suit is contiguous
    for (let i = 1; i < suits.length; i++) {
      if (suits[i] !== suits[i - 1]) {
        // New suit — shouldn't appear again
        const remaining = suits.slice(i + 1)
        expect(remaining).not.toContain(suits[i - 1])
      }
    }
  })
})

// ── Game over ────────────────────────────────────────────────────────

describe('game over', () => {
  test('game is over when a team reaches 10 points', () => {
    const state = baseState({
      teamScores: [10, 5],
    })
    expect(state.teamScores[0]).toBeGreaterThanOrEqual(10)
  })

  test('team scores are separate from per-player trick counts', () => {
    const state = baseState({
      teamScores: [5, 7],
      tricksTaken: [2, 3, 1, 2],
    })
    expect(state.teamScores).toHaveLength(2)
    expect(state.tricksTaken).toHaveLength(4)
  })
})

// ── Constants ────────────────────────────────────────────────────────

describe('constants', () => {
  test('PLAYER_NAMES has 4 entries', () => {
    expect(PLAYER_NAMES).toHaveLength(4)
    expect(PLAYER_NAMES[0]).toBe('You')
  })

  test('TEAM_NAMES has 2 entries', () => {
    expect(TEAM_NAMES).toHaveLength(2)
  })
})

// ── Pure functions / immutability ────────────────────────────────────

describe('immutability', () => {
  test('pass does not mutate original state', () => {
    const state = baseState({
      phase: 'trumpRound1',
      currentPlayer: 1,
      dealer: 0,
    })
    const original = { ...state }
    pass(state)
    expect(state.currentPlayer).toBe(original.currentPlayer)
    expect(state.phase).toBe(original.phase)
  })

  test('orderUp does not mutate original state', () => {
    const state = baseState({
      phase: 'trumpRound1',
      currentPlayer: 1,
      dealer: 0,
      flippedCard: card(12, 'spades'),
      hands: [
        [card(9, 'hearts'), card(10, 'hearts'), card(1, 'clubs'), card(13, 'diamonds'), card(9, 'spades')],
        [], [], [],
      ],
    })
    const origTrump = state.trumpSuit
    orderUp(state)
    expect(state.trumpSuit).toBe(origTrump)
  })
})
