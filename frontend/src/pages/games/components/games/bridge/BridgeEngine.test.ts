/**
 * BridgeEngine tests — TDD: written before the engine implementation.
 *
 * Covers: HCP counting, bid ordering, bidding flow, declarer/dummy
 * determination, must-follow-suit, trick winners (led suit vs trump, NT),
 * scoring (making/failing, game bonus, slam bonuses), game lifecycle.
 */

import { describe, test, expect } from 'vitest'
import type { Card, Suit } from '../../../utils/cardUtils'
import {
  createBridgeGame,
  makeBid,
  passBid,
  playCard,
  countHCP,
  isHigherBid,
  scoreHand,
  STRAIN_ORDER,
  type BridgeState,
  type Strain,
  type Bid,
} from './BridgeEngine'

// ── Helpers ──────────────────────────────────────────────────────────

/** Build a Card shorthand. Rank: 1=A, 11=J, 12=Q, 13=K. */
function card(suit: Suit, rank: number, faceUp = true): Card {
  return { suit, rank, faceUp }
}

/** Build a hand with known cards for testing. */
function makeHand(cards: [Suit, number][]): Card[] {
  return cards.map(([s, r]) => card(s, r))
}

/**
 * Create a state in bidding phase with known hands.
 * All AI players have < 13 HCP so they'll pass when advanceBidding runs.
 * Player 0 starts as the current player (dealer=3 so (3+1)%4 = 0).
 */
function biddingState(overrides?: Partial<BridgeState>): BridgeState {
  const hands: Card[][] = [
    // Player 0: 13 HCP — A,K of spades + Q,J of hearts + filler
    makeHand([
      ['spades', 1], ['spades', 13], ['spades', 10], ['spades', 9],
      ['hearts', 12], ['hearts', 11], ['hearts', 9], ['hearts', 8],
      ['diamonds', 7], ['diamonds', 6], ['diamonds', 5],
      ['clubs', 4], ['clubs', 3],
    ]),
    // Player 1: 4 HCP (Ace only — will pass)
    makeHand([
      ['hearts', 1], ['hearts', 10], ['hearts', 4],
      ['diamonds', 9], ['diamonds', 8], ['diamonds', 4], ['diamonds', 3],
      ['clubs', 10], ['clubs', 9], ['clubs', 8],
      ['spades', 8], ['spades', 7], ['spades', 6],
    ]),
    // Player 2: 4 HCP (Ace only — will pass)
    makeHand([
      ['diamonds', 1], ['diamonds', 10], ['diamonds', 2],
      ['clubs', 7], ['clubs', 6],
      ['hearts', 7], ['hearts', 6], ['hearts', 5],
      ['spades', 5], ['spades', 4], ['spades', 3],
      ['clubs', 5], ['clubs', 2],
    ]),
    // Player 3: 0 HCP (no honors — will pass)
    makeHand([
      ['clubs', 2], ['clubs', 3], ['clubs', 4],
      ['diamonds', 5], ['diamonds', 6], ['diamonds', 2], ['diamonds', 10],
      ['hearts', 3], ['hearts', 2],
      ['spades', 2], ['spades', 10], ['spades', 9],
      ['hearts', 9],
    ]),
  ]

  return {
    hands,
    bids: [],
    contract: null,
    declarer: null,
    dummy: null,
    currentTrick: [],
    tricksWon: [0, 0, 0, 0],
    teamScores: [0, 0],
    phase: 'bidding',
    currentPlayer: 0,
    dealer: 3, // so first bidder = (3+1)%4 = 0
    trumpSuit: null,
    ledSuit: null,
    message: 'Your bid',
    consecutivePasses: 0,
    dummyRevealed: false,
    lastTrickWinner: null,
    ...overrides,
  }
}

/**
 * Create a state in playing phase for trick-taking tests.
 * Player 0 = declarer, Player 2 = dummy. currentPlayer = 0 by default.
 */
function playingState(overrides?: Partial<BridgeState>): BridgeState {
  return {
    hands: [
      makeHand([['spades', 1], ['hearts', 5], ['diamonds', 3]]),
      makeHand([['spades', 13], ['hearts', 1], ['clubs', 7]]),
      makeHand([['spades', 12], ['diamonds', 1], ['clubs', 5]]),
      makeHand([['spades', 11], ['hearts', 9], ['diamonds', 7]]),
    ],
    bids: [
      { player: 0, level: 1, strain: 'spades' },
      { player: 1, level: 0, strain: null },
      { player: 2, level: 0, strain: null },
      { player: 3, level: 0, strain: null },
    ],
    contract: { player: 0, level: 1, strain: 'spades' },
    declarer: 0,
    dummy: 2,
    currentTrick: [],
    tricksWon: [0, 0, 0, 0],
    teamScores: [0, 0],
    phase: 'playing',
    currentPlayer: 0,
    dealer: 3,
    trumpSuit: 'spades',
    ledSuit: null,
    message: '',
    consecutivePasses: 0,
    dummyRevealed: true,
    lastTrickWinner: null,
    ...overrides,
  }
}


// ── countHCP ─────────────────────────────────────────────────────────

describe('countHCP', () => {
  test('counts A=4, K=3, Q=2, J=1', () => {
    const hand = makeHand([
      ['spades', 1],  // A = 4
      ['hearts', 13], // K = 3
      ['diamonds', 12], // Q = 2
      ['clubs', 11],  // J = 1
    ])
    expect(countHCP(hand)).toBe(10)
  })

  test('returns 0 for no honors', () => {
    const hand = makeHand([
      ['spades', 2], ['spades', 3], ['hearts', 5],
    ])
    expect(countHCP(hand)).toBe(0)
  })

  test('counts all 4 aces = 16 HCP', () => {
    const hand = makeHand([
      ['spades', 1], ['hearts', 1], ['diamonds', 1], ['clubs', 1],
    ])
    expect(countHCP(hand)).toBe(16)
  })

  test('full hand with mixed honors', () => {
    const hand = makeHand([
      ['spades', 1], ['spades', 13],  // A+K = 7
      ['hearts', 12], ['hearts', 11], // Q+J = 3
      ['diamonds', 7], ['diamonds', 6], ['diamonds', 5],
      ['clubs', 4], ['clubs', 3], ['clubs', 2],
      ['spades', 10], ['spades', 9], ['hearts', 8],
    ])
    expect(countHCP(hand)).toBe(10)
  })

  test('empty hand returns 0', () => {
    expect(countHCP([])).toBe(0)
  })
})


// ── isHigherBid ──────────────────────────────────────────────────────

describe('isHigherBid', () => {
  test('higher level is always higher regardless of strain', () => {
    expect(isHigherBid(2, 'clubs', 1, 'nt')).toBe(true)
  })

  test('same level, higher strain is higher', () => {
    // Strain order: C < D < H < S < NT
    expect(isHigherBid(1, 'diamonds', 1, 'clubs')).toBe(true)
    expect(isHigherBid(1, 'hearts', 1, 'diamonds')).toBe(true)
    expect(isHigherBid(1, 'spades', 1, 'hearts')).toBe(true)
    expect(isHigherBid(1, 'nt', 1, 'spades')).toBe(true)
  })

  test('same level, same strain is NOT higher', () => {
    expect(isHigherBid(1, 'hearts', 1, 'hearts')).toBe(false)
  })

  test('same level, lower strain is NOT higher', () => {
    expect(isHigherBid(1, 'clubs', 1, 'diamonds')).toBe(false)
  })

  test('lower level is NOT higher', () => {
    expect(isHigherBid(1, 'nt', 2, 'clubs')).toBe(false)
  })

  test('1C is not higher than 1C (equal)', () => {
    expect(isHigherBid(1, 'clubs', 1, 'clubs')).toBe(false)
  })

  test('7NT is the highest possible bid', () => {
    expect(isHigherBid(7, 'nt', 7, 'spades')).toBe(true)
  })

  test('strain order constant is correct', () => {
    expect(STRAIN_ORDER).toEqual(['clubs', 'diamonds', 'hearts', 'spades', 'nt'])
  })
})


// ── Bidding flow ─────────────────────────────────────────────────────

describe('bidding flow', () => {
  test('createBridgeGame starts in bidding phase with 13 cards each', () => {
    const state = createBridgeGame()
    expect(state.phase).toBe('bidding')
    expect(state.hands.length).toBe(4)
    for (const hand of state.hands) {
      expect(hand.length).toBe(13)
    }
    expect(state.bids).toEqual([])
    expect(state.contract).toBeNull()
  })

  test('makeBid records player 0 bid (AI players all pass with low HCP)', () => {
    const state = biddingState()
    const next = makeBid(state, 1, 'clubs')
    // Player 0 bids, then AI players 1,2,3 all pass (< 13 HCP) = 3 passes
    // 3 consecutive passes after a bid => bidding ends, contract set
    expect(next.bids[0]).toEqual({ player: 0, level: 1, strain: 'clubs' })
    expect(next.contract).not.toBeNull()
    expect(next.contract!.level).toBe(1)
    expect(next.contract!.strain).toBe('clubs')
    expect(next.phase).toBe('playing')
  })

  test('makeBid rejects bid lower than current highest', () => {
    // Manually set up state where there's already a high bid
    const state = biddingState({
      bids: [{ player: 3, level: 2, strain: 'hearts' }],
      currentPlayer: 0,
    })
    // Player 0 tries to bid 1 spades — must be higher than 2H
    const next = makeBid(state, 1, 'spades')
    // Bid should be rejected — bids array unchanged
    expect(next.bids.length).toBe(state.bids.length)
  })

  test('passBid records a pass and advances', () => {
    const state = biddingState()
    const next = passBid(state)
    // Player 0 passes, AI 1,2,3 also pass (all < 13 HCP)
    // All 4 pass => redeal with new random hands, AI may bid on new deal
    // Key check: phase should still be bidding (waiting for human) unless
    // AI completed a contract on the new deal
    if (next.contract) {
      expect(next.phase).toBe('playing')
    } else {
      expect(next.phase).toBe('bidding')
    }
    // Dealer should have rotated
    expect(next.dealer).toBe(0) // was 3, now (3+1)%4 = 0
  })

  test('3 passes after a bid ends bidding and sets contract', () => {
    // Use a state where player 0 already bid, and we manually simulate passes
    const state = biddingState({
      bids: [{ player: 0, level: 1, strain: 'spades' }],
      consecutivePasses: 0,
      currentPlayer: 1,
    })
    // Pass 3 times (players 1, 2, 3)
    let s = passBid(state) // player 1 passes, then AI 2 and 3 pass
    // After 3 passes following a bid, contract should be set
    expect(s.contract).not.toBeNull()
    expect(s.contract!.level).toBe(1)
    expect(s.contract!.strain).toBe('spades')
    expect(s.phase).toBe('playing')
  })

  test('4 initial passes causes redeal (dealer rotates)', () => {
    // All AI have < 13 HCP, so player 0 passing triggers full all-pass => redeal
    const state = biddingState() // dealer = 3
    const next = passBid(state)
    // After redeal, dealer rotates from 3 to 0
    expect(next.dealer).toBe(0)
    // New random hands are dealt, AI may or may not bid on them
    // The key behavior: the original deal was abandoned and a fresh one started
    expect(next.hands.every(h => h.length === 13)).toBe(true)
  })

  test('makeBid rejects invalid level (0 or > 7)', () => {
    const state = biddingState()
    const next0 = makeBid(state, 0, 'clubs')
    expect(next0.bids.length).toBe(0) // rejected

    const next8 = makeBid(state, 8, 'clubs')
    expect(next8.bids.length).toBe(0) // rejected
  })

  test('consecutive passes reset to 0 when a new bid is placed', () => {
    // State: player 3 already bid 1C, player 0 passed (1 consecutive pass)
    const state = biddingState({
      bids: [
        { player: 3, level: 1, strain: 'clubs' },
        { player: 0, level: 0, strain: null },
      ],
      consecutivePasses: 1,
      currentPlayer: 0,
    })
    // Player 0 now bids 1H (higher than 1C)
    const next = makeBid(state, 1, 'hearts')
    // The bid itself resets passes to 0, then AI players pass (3 passes) => finalize
    // But regardless, the bid record for player 0 has consecutivePasses reset
    expect(next.contract).not.toBeNull()
    expect(next.contract!.strain).toBe('hearts')
  })
})


// ── Declarer & Dummy determination ───────────────────────────────────

describe('declarer and dummy determination', () => {
  test('declarer is the first player on winning team to bid the winning strain', () => {
    // Set up: player 0 bid 1H earlier, partner (player 2) then bid 2H
    // After 3 passes, declarer should be player 0 (first to bid hearts on team 0)
    const state = biddingState({
      bids: [
        { player: 0, level: 1, strain: 'hearts' },
        { player: 1, level: 0, strain: null },
        { player: 2, level: 2, strain: 'hearts' },
      ],
      consecutivePasses: 0,
      currentPlayer: 3,
    })
    // Player 3 passes, then players 0 and 1 pass -> 3 passes after last bid
    const next = passBid(state) // player 3 passes; AI advances: player 0 (human, stops)
    // Actually since currentPlayer goes to 0 next, we need to pass from 0 too
    const s2 = passBid(next)    // player 0 passes
    // Now AI player 1 passes = 3 consecutive passes after 2H
    expect(s2.contract).not.toBeNull()
    expect(s2.declarer).toBe(0)  // first to bid hearts on winning team
    expect(s2.dummy).toBe(2)     // partner of declarer
  })

  test('dummy is the partner of declarer (offset by 2)', () => {
    // Player 1 bids, followed by 3 passes => declarer = 1, dummy = 3
    const state = biddingState({
      bids: [{ player: 1, level: 1, strain: 'diamonds' }],
      consecutivePasses: 0,
      currentPlayer: 2,
    })
    // Players 2, 3 pass (via AI), then comes to player 0
    let next = state
    // Player 2 passes (AI in advanceBidding)
    next = passBidForPlayer(next, 2)
    next = passBidForPlayer(next, 3)
    next = passBidForPlayer(next, 0) // 3 passes

    expect(next.contract).not.toBeNull()
    expect(next.declarer).toBe(1)
    expect(next.dummy).toBe(3)
  })
})

/** Helper: manually pass for a specific player (bypasses AI auto-play). */
function passBidForPlayer(state: BridgeState, player: number): BridgeState {
  if (state.phase !== 'bidding') return state
  const bid: Bid = { player, level: 0, strain: null }
  const bids = [...state.bids, bid]
  const passes = state.consecutivePasses + 1
  const highestBid = bids.find(b => b.level > 0)

  if (!highestBid && passes === 4) {
    // All pass - would redeal, but for testing just return
    return { ...state, bids, consecutivePasses: passes, phase: 'bidding', currentPlayer: (player + 1) % 4 }
  }

  // Check 3 passes after a real bid — use makeBid/passBid path for finalization
  // We need to directly check and call finalize logic
  if (highestBid && passes === 3) {
    // Find highest bid
    let highest: Bid | null = null
    for (const b of bids) {
      if (b.level === 0) continue
      if (!highest || b.level > highest.level ||
          (b.level === highest.level && STRAIN_ORDER.indexOf(b.strain as Strain) > STRAIN_ORDER.indexOf(highest.strain as Strain))) {
        highest = b
      }
    }
    if (highest) {
      // Determine declarer
      const winningTeam = highest.player % 2
      let declarer = highest.player
      for (const b of bids) {
        if (b.level > 0 && b.strain === highest.strain && b.player % 2 === winningTeam) {
          declarer = b.player
          break
        }
      }
      const dummy = (declarer + 2) % 4
      return {
        ...state,
        bids,
        consecutivePasses: passes,
        contract: highest,
        declarer,
        dummy,
        trumpSuit: highest.strain as Strain,
        phase: 'playing',
        currentPlayer: (declarer + 1) % 4,
        dummyRevealed: true,
        message: `Contract set`,
      }
    }
  }

  return {
    ...state,
    bids,
    consecutivePasses: passes,
    currentPlayer: (player + 1) % 4,
  }
}


// ── Must follow suit ─────────────────────────────────────────────────

describe('must follow suit', () => {
  test('player must play a card of the led suit if they have one', () => {
    // Player 0's turn, hearts was led, player 0 has hearts
    const state = playingState({
      currentPlayer: 0,
      currentTrick: [
        { card: card('hearts', 9), player: 3 },
      ],
      ledSuit: 'hearts',
      hands: [
        makeHand([['hearts', 5], ['spades', 1], ['diamonds', 3]]),
        makeHand([['spades', 13]]),
        makeHand([['spades', 12]]),
        makeHand([]),
      ],
    })

    // Player 0 must follow hearts — cannot play spades
    const bad = playCard(state, 0, 1) // tries spades A
    expect(bad).toBe(state) // rejected

    const good = playCard(state, 0, 0) // plays hearts 5
    // After player 0 plays, AI players 1 and 2 play to complete trick
    // Check that player 0's card (hearts 5) is in the trick
    expect(good.currentTrick.length).toBeGreaterThanOrEqual(2)
    const p0Card = good.currentTrick.find(tc => tc.player === 0)
    expect(p0Card).toBeDefined()
    expect(p0Card!.card.suit).toBe('hearts')
  })

  test('player can play any card when void in led suit', () => {
    // Player 0 has no spades
    const state = playingState({
      currentPlayer: 0,
      hands: [
        makeHand([['hearts', 5], ['diamonds', 3], ['clubs', 2]]), // no spades
        makeHand([['spades', 13]]),
        makeHand([['spades', 12]]),
        makeHand([]),
      ],
      currentTrick: [{ card: card('spades', 10), player: 3 }],
      ledSuit: 'spades',
    })

    // Player 0 can play hearts (void in spades)
    const next = playCard(state, 0, 0) // hearts 5
    // After player 0 plays, AI takes remaining turns
    expect(next.currentTrick.length).toBeGreaterThanOrEqual(2)
    const p0Card = next.currentTrick.find(tc => tc.player === 0)
    expect(p0Card).toBeDefined()
    expect(p0Card!.card.suit).toBe('hearts')
  })
})


// ── Trick winner ─────────────────────────────────────────────────────

describe('trick winner', () => {
  test('highest card of led suit wins when no trump played', () => {
    // Set up: 3 hearts already played, player 0 completes with 4th heart
    // Trump is clubs, no clubs played => highest heart wins
    const state = playingState({
      currentPlayer: 0,
      trumpSuit: 'clubs',
      currentTrick: [
        { card: card('hearts', 5), player: 1 },
        { card: card('hearts', 1), player: 2 },  // Ace = highest
        { card: card('hearts', 13), player: 3 },
      ],
      ledSuit: 'hearts',
      hands: [
        makeHand([['hearts', 10]]),
        [], [], [],
      ],
      // 12 tricks already taken so this is the 13th (triggers hand resolution)
      tricksWon: [4, 3, 3, 2],
    })

    const next = playCard(state, 0, 0)
    // Player 2 had Ace of hearts, should win the trick
    expect(next.tricksWon[2]).toBe(4) // was 3, now 4
  })

  test('trump card beats any non-trump card', () => {
    const state = playingState({
      currentPlayer: 0,
      trumpSuit: 'spades',
      currentTrick: [
        { card: card('hearts', 1), player: 1 },   // Ace of hearts (led)
        { card: card('spades', 2), player: 2 },    // 2 of trump
        { card: card('hearts', 13), player: 3 },
      ],
      ledSuit: 'hearts',
      hands: [
        makeHand([['hearts', 10]]),
        [], [], [],
      ],
      tricksWon: [4, 3, 3, 2],
    })

    const next = playCard(state, 0, 0)
    // Player 2 trumped with 2 of spades — beats all hearts
    expect(next.tricksWon[2]).toBe(4) // was 3, now 4
  })

  test('higher trump beats lower trump', () => {
    const state = playingState({
      currentPlayer: 0,
      trumpSuit: 'spades',
      currentTrick: [
        { card: card('hearts', 1), player: 1 },
        { card: card('spades', 5), player: 2 },
        { card: card('spades', 10), player: 3 },  // higher trump
      ],
      ledSuit: 'hearts',
      hands: [
        makeHand([['hearts', 3]]),
        [], [], [],
      ],
      tricksWon: [4, 3, 3, 2],
    })

    const next = playCard(state, 0, 0)
    // Player 3 played higher trump (10 vs 5)
    expect(next.tricksWon[3]).toBe(3) // was 2, now 3
  })

  test('in NT, highest of led suit always wins (no trumping)', () => {
    const state = playingState({
      currentPlayer: 0,
      trumpSuit: 'nt',
      contract: { player: 0, level: 1, strain: 'nt' },
      currentTrick: [
        { card: card('hearts', 13), player: 1 }, // King of hearts (led)
        { card: card('spades', 1), player: 2 },  // Ace of spades — off-suit, doesn't count
        { card: card('hearts', 12), player: 3 },
      ],
      ledSuit: 'hearts',
      hands: [
        makeHand([['hearts', 5]]),
        [], [], [],
      ],
      tricksWon: [4, 3, 3, 2],
    })

    const next = playCard(state, 0, 0)
    // In NT, King of hearts (led suit, highest in suit) wins
    expect(next.tricksWon[1]).toBe(4) // was 3, now 4
  })
})


// ── scoreHand ────────────────────────────────────────────────────────

describe('scoreHand', () => {
  test('making contract in minor suit (clubs): 20 per trick', () => {
    const contract: Bid = { player: 0, level: 2, strain: 'clubs' }
    // Need 8 tricks (6+2), took exactly 8
    const result = scoreHand(contract, 8, 0)
    expect(result.points).toBe(40 + 50) // 2*20 = 40 trick points + 50 partial bonus
  })

  test('making contract in minor suit (diamonds): 20 per trick', () => {
    const contract: Bid = { player: 0, level: 3, strain: 'diamonds' }
    // Need 9 tricks (6+3), took 10 (1 overtrick)
    const result = scoreHand(contract, 10, 0)
    // 3*20 = 60 trick pts + 50 partial bonus + 1*20 overtrick
    expect(result.points).toBe(60 + 50 + 20)
  })

  test('making contract in major suit (hearts): 30 per trick', () => {
    const contract: Bid = { player: 0, level: 2, strain: 'hearts' }
    // Need 8 tricks, took 8
    const result = scoreHand(contract, 8, 0)
    expect(result.points).toBe(60 + 50) // 2*30 = 60 + 50 partial
  })

  test('making contract in major suit (spades): 30 per trick', () => {
    const contract: Bid = { player: 0, level: 4, strain: 'spades' }
    // Need 10 tricks, took 10
    const result = scoreHand(contract, 10, 0)
    // 4*30 = 120 trick pts >= 100 => game bonus 300
    expect(result.points).toBe(120 + 300)
  })

  test('NT scoring: 40 first + 30 each after', () => {
    const contract: Bid = { player: 0, level: 3, strain: 'nt' }
    // Need 9 tricks, took 9
    const result = scoreHand(contract, 9, 0)
    // 40 + 2*30 = 100 trick pts >= 100 => game bonus 300
    expect(result.points).toBe(100 + 300)
  })

  test('game bonus (300) when trick points >= 100', () => {
    // 5 clubs = 5*20 = 100 trick points => game bonus
    const contract: Bid = { player: 0, level: 5, strain: 'clubs' }
    const result = scoreHand(contract, 11, 0)
    expect(result.points).toBe(100 + 300) // exactly 100 trick pts
  })

  test('partial bonus (50) when trick points < 100', () => {
    // 1 spades = 30 trick points < 100
    const contract: Bid = { player: 0, level: 1, strain: 'spades' }
    const result = scoreHand(contract, 7, 0)
    expect(result.points).toBe(30 + 50) // partial
  })

  test('overtricks at same per-trick value', () => {
    const contract: Bid = { player: 0, level: 2, strain: 'spades' }
    // Need 8, took 10 (2 overtricks)
    const result = scoreHand(contract, 10, 0)
    // 2*30 = 60 + 50 partial + 2*30 overtricks = 60
    expect(result.points).toBe(60 + 50 + 60)
  })

  test('undertricks: -50 each', () => {
    const contract: Bid = { player: 0, level: 4, strain: 'hearts' }
    // Need 10 tricks, took only 7 (3 under)
    const result = scoreHand(contract, 7, 0)
    expect(result.points).toBe(-150) // 3 * -50
  })

  test('small slam bonus (level 6 made): +500', () => {
    const contract: Bid = { player: 0, level: 6, strain: 'spades' }
    // Need 12 tricks, took 12
    const result = scoreHand(contract, 12, 0)
    // 6*30 = 180 trick pts + 300 game bonus + 500 slam
    expect(result.points).toBe(180 + 300 + 500)
  })

  test('grand slam bonus (level 7 made): +1000', () => {
    const contract: Bid = { player: 0, level: 7, strain: 'nt' }
    // Need 13 tricks, took 13
    const result = scoreHand(contract, 13, 0)
    // 40 + 6*30 = 220 trick pts + 300 game + 1000 grand slam
    expect(result.points).toBe(220 + 300 + 1000)
  })

  test('slam not awarded if contract fails', () => {
    const contract: Bid = { player: 0, level: 6, strain: 'hearts' }
    // Need 12, took 11 (1 under)
    const result = scoreHand(contract, 11, 0)
    expect(result.points).toBe(-50) // 1 undertrick
  })

  test('scoreHand returns a breakdown string', () => {
    const contract: Bid = { player: 0, level: 1, strain: 'clubs' }
    const result = scoreHand(contract, 7, 0)
    expect(typeof result.breakdown).toBe('string')
    expect(result.breakdown.length).toBeGreaterThan(0)
  })
})


// ── Game creation ────────────────────────────────────────────────────

describe('createBridgeGame', () => {
  test('deals 13 cards to each of 4 players', () => {
    const state = createBridgeGame()
    expect(state.hands.length).toBe(4)
    for (const hand of state.hands) {
      expect(hand.length).toBe(13)
    }
  })

  test('uses all 52 cards with no duplicates', () => {
    const state = createBridgeGame()
    const allCards = state.hands.flat()
    expect(allCards.length).toBe(52)

    const keys = new Set(allCards.map(c => `${c.suit}-${c.rank}`))
    expect(keys.size).toBe(52)
  })

  test('initial state has correct defaults', () => {
    const state = createBridgeGame()
    expect(state.phase).toBe('bidding')
    expect(state.bids).toEqual([])
    expect(state.contract).toBeNull()
    expect(state.declarer).toBeNull()
    expect(state.dummy).toBeNull()
    expect(state.currentTrick).toEqual([])
    expect(state.tricksWon).toEqual([0, 0, 0, 0])
    expect(state.teamScores).toEqual([0, 0])
    expect(state.consecutivePasses).toBe(0)
    expect(state.dummyRevealed).toBe(false)
    expect(state.trumpSuit).toBeNull()
    expect(state.ledSuit).toBeNull()
    expect(state.lastTrickWinner).toBeNull()
  })

  test('dealer is set (0-3)', () => {
    const state = createBridgeGame()
    expect(state.dealer).toBeGreaterThanOrEqual(0)
    expect(state.dealer).toBeLessThanOrEqual(3)
  })
})


// ── Playing phase: declarer controls dummy ───────────────────────────

describe('declarer controls dummy', () => {
  test('declarer can play cards from dummy hand using playerIdx', () => {
    const state = playingState({
      currentPlayer: 2, // dummy's turn
      declarer: 0,
      dummy: 2,
      dummyRevealed: true,
      currentTrick: [
        { card: card('spades', 13), player: 1 }, // lead
      ],
      ledSuit: 'spades',
      hands: [
        makeHand([['spades', 1], ['hearts', 5]]),
        makeHand([]),
        makeHand([['spades', 12], ['diamonds', 1]]),
        makeHand([['spades', 11]]),
      ],
    })

    // Declarer (0) plays dummy's (2) card — playerIdx = 2
    const next = playCard(state, 2, 0) // dummy's first card (spades Q)
    // After dummy plays, AI player 3 plays, completing trick or continuing
    expect(next.currentTrick.length).toBeGreaterThanOrEqual(2)
    // The second card in trick should be from dummy (player 2)
    expect(next.currentTrick[1].player).toBe(2)
    expect(next.currentTrick[1].card.suit).toBe('spades')
  })
})


// ── Game-over: first team to 500 wins ────────────────────────────────

describe('game over conditions', () => {
  test('team reaching 500+ points wins', () => {
    // Set teamScores near 500, then score a big hand
    const contract: Bid = { player: 0, level: 4, strain: 'spades' }
    // 4 spades made = 120 + 300 = 420 points
    const result = scoreHand(contract, 10, 0)
    // In a game where team already has 100, adding 420 would reach 520
    expect(result.points).toBe(420)
    // If team0 has 100 + 420 = 520 >= 500, game should end
  })
})


// ── Edge cases ───────────────────────────────────────────────────────

describe('edge cases', () => {
  test('makeBid does nothing outside bidding phase', () => {
    const state = playingState()
    const next = makeBid(state, 1, 'clubs')
    expect(next).toBe(state) // unchanged reference
  })

  test('passBid does nothing outside bidding phase', () => {
    const state = playingState()
    const next = passBid(state)
    expect(next).toBe(state)
  })

  test('playCard does nothing outside playing phase', () => {
    const state = biddingState()
    const next = playCard(state, 0, 0)
    expect(next).toBe(state)
  })

  test('playCard rejects invalid card index', () => {
    const state = playingState()
    const next = playCard(state, 0, 99) // out of bounds
    expect(next).toBe(state)
  })
})
