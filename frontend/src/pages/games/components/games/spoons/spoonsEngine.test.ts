import { describe, it, expect } from 'vitest'
import {
  hasFourOfAKind,
  createSpoonsGame,
  drawCard,
  discardCard,
  grabSpoon,
  newRound,
  aiDiscard,
  getAiGrabDelays,
  getActiveCount,
  getNextActive,
  isHumanTurn,
  type SpoonsState,
  type PlayerInfo,
  type Phase,
} from './spoonsEngine'
import type { Card } from '../../../utils/cardUtils'

// ── Helpers ─────────────────────────────────────────────────────────

function makeCard(rank: number, suit: Card['suit'] = 'hearts'): Card {
  return { rank, suit, faceUp: true }
}

function makePlayer(overrides: Partial<PlayerInfo> = {}): PlayerInfo {
  return {
    hand: [makeCard(5), makeCard(8), makeCard(11), makeCard(3)],
    letters: '',
    eliminated: false,
    isHuman: false,
    name: 'Bot',
    grabbedSpoon: false,
    reactionTime: 500,
    ...overrides,
  }
}

function makeState(overrides: Partial<SpoonsState> = {}): SpoonsState {
  return {
    players: [
      makePlayer({ isHuman: true, name: 'You', reactionTime: 0 }),
      makePlayer({ name: 'Bot 1', reactionTime: 500 }),
      makePlayer({ name: 'Bot 2', reactionTime: 800 }),
    ],
    drawPile: [makeCard(2), makeCard(9), makeCard(7), makeCard(4), makeCard(6)],
    discardPile: [],
    passedCard: null,
    currentPlayer: 0,
    dealer: 0,
    spoonsRemaining: 2,
    phase: 'drawing' as Phase,
    message: '',
    spoonGrabber: null,
    roundLoser: null,
    roundNumber: 1,
    ...overrides,
  }
}

// ── hasFourOfAKind ──────────────────────────────────────────────────

describe('hasFourOfAKind', () => {
  it('should detect 4 of a kind', () => {
    const hand = [
      makeCard(7, 'hearts'),
      makeCard(7, 'diamonds'),
      makeCard(7, 'clubs'),
      makeCard(7, 'spades'),
    ]
    expect(hasFourOfAKind(hand)).toBe(true)
  })

  it('should return false for 3 of a kind', () => {
    const hand = [
      makeCard(7, 'hearts'),
      makeCard(7, 'diamonds'),
      makeCard(7, 'clubs'),
      makeCard(5, 'spades'),
    ]
    expect(hasFourOfAKind(hand)).toBe(false)
  })

  it('should return false for all different ranks', () => {
    const hand = [makeCard(1), makeCard(2), makeCard(3), makeCard(4)]
    expect(hasFourOfAKind(hand)).toBe(false)
  })

  it('should detect 4 of a kind in a 5-card hand', () => {
    const hand = [
      makeCard(9, 'hearts'),
      makeCard(3, 'clubs'),
      makeCard(9, 'diamonds'),
      makeCard(9, 'clubs'),
      makeCard(9, 'spades'),
    ]
    expect(hasFourOfAKind(hand)).toBe(true)
  })
})

// ── createSpoonsGame ────────────────────────────────────────────────

describe('createSpoonsGame', () => {
  it('should create 3 players', () => {
    const state = createSpoonsGame()
    expect(state.players).toHaveLength(3)
  })

  it('should deal 4 cards to each player', () => {
    const state = createSpoonsGame()
    for (const p of state.players) {
      expect(p.hand).toHaveLength(4)
    }
  })

  it('should have player 0 as human', () => {
    const state = createSpoonsGame()
    expect(state.players[0].isHuman).toBe(true)
    expect(state.players[0].name).toBe('You')
  })

  it('should have 2 spoons (players - 1)', () => {
    const state = createSpoonsGame()
    expect(state.spoonsRemaining).toBe(2)
  })

  it('should total 52 cards across all locations', () => {
    const state = createSpoonsGame()
    const total = state.players.reduce((s, p) => s + p.hand.length, 0) +
      state.drawPile.length + state.discardPile.length
    expect(total).toBe(52)
  })

  it('should start in drawing phase', () => {
    const state = createSpoonsGame()
    expect(state.phase).toBe('drawing')
  })

  it('should have no eliminated players', () => {
    const state = createSpoonsGame()
    expect(state.players.every(p => !p.eliminated)).toBe(true)
  })
})

// ── drawCard ────────────────────────────────────────────────────────

describe('drawCard', () => {
  it('should draw from draw pile when current player is dealer', () => {
    const state = makeState({ dealer: 0, currentPlayer: 0 })
    const next = drawCard(state)
    expect(next.players[0].hand).toHaveLength(5)
    expect(next.drawPile.length).toBe(state.drawPile.length - 1)
    expect(next.phase).toBe('discarding')
  })

  it('should pick up passed card when not dealer', () => {
    const passed = makeCard(10, 'diamonds')
    const state = makeState({
      dealer: 0,
      currentPlayer: 1,
      passedCard: passed,
    })
    const next = drawCard(state)
    expect(next.players[1].hand).toHaveLength(5)
    expect(next.passedCard).toBeNull()
    expect(next.phase).toBe('discarding')
  })

  it('should not draw if phase is not drawing', () => {
    const state = makeState({ phase: 'discarding' })
    const next = drawCard(state)
    expect(next).toBe(state)
  })
})

// ── discardCard ─────────────────────────────────────────────────────

describe('discardCard', () => {
  it('should discard a card and pass to next player', () => {
    const state = makeState({
      phase: 'discarding',
      currentPlayer: 0,
      dealer: 0,
      players: [
        makePlayer({ isHuman: true, name: 'You', hand: [makeCard(1), makeCard(2), makeCard(3), makeCard(4), makeCard(5)] }),
        makePlayer({ name: 'Bot 1' }),
        makePlayer({ name: 'Bot 2' }),
      ],
    })
    const next = discardCard(state, 4)
    expect(next.players[0].hand).toHaveLength(4)
    expect(next.currentPlayer).toBe(1)
    expect(next.passedCard).not.toBeNull()
    expect(next.phase).toBe('drawing')
  })

  it('should send discard to discard pile when last player discards', () => {
    // Last player is the one before dealer in the circle
    // With dealer=0, players 0→1→2, last player is 2
    const state = makeState({
      phase: 'discarding',
      currentPlayer: 2,
      dealer: 0,
      players: [
        makePlayer({ isHuman: true, name: 'You' }),
        makePlayer({ name: 'Bot 1' }),
        makePlayer({
          name: 'Bot 2',
          hand: [makeCard(1), makeCard(2), makeCard(3), makeCard(4), makeCard(5)],
        }),
      ],
    })
    const next = discardCard(state, 0)
    expect(next.discardPile.length).toBe(state.discardPile.length + 1)
    expect(next.passedCard).toBeNull()
    expect(next.currentPlayer).toBe(0) // Back to dealer
    expect(next.phase).toBe('drawing')
  })

  it('should trigger spoon grab when player gets 4 of a kind', () => {
    const state = makeState({
      phase: 'discarding',
      currentPlayer: 0,
      players: [
        makePlayer({
          isHuman: true,
          name: 'You',
          hand: [
            makeCard(7, 'hearts'),
            makeCard(7, 'diamonds'),
            makeCard(7, 'clubs'),
            makeCard(7, 'spades'),
            makeCard(3, 'hearts'),
          ],
        }),
        makePlayer({ name: 'Bot 1' }),
        makePlayer({ name: 'Bot 2' }),
      ],
    })
    // Discard the 3, keeping four 7s
    const next = discardCard(state, 4)
    expect(next.phase).toBe('spoonGrab')
    expect(next.spoonGrabber).toBe(0)
  })

  it('should not discard if phase is wrong', () => {
    const state = makeState({ phase: 'drawing' })
    expect(discardCard(state, 0)).toBe(state)
  })

  it('should reject invalid card index', () => {
    const state = makeState({ phase: 'discarding' })
    expect(discardCard(state, -1)).toBe(state)
    expect(discardCard(state, 99)).toBe(state)
  })
})

// ── grabSpoon ───────────────────────────────────────────────────────

describe('grabSpoon', () => {
  it('should let player grab a spoon', () => {
    const state = makeState({ phase: 'spoonGrab', spoonsRemaining: 2 })
    const next = grabSpoon(state, 0)
    expect(next.players[0].grabbedSpoon).toBe(true)
    expect(next.spoonsRemaining).toBe(1)
  })

  it('should assign letter when last spoon grabbed', () => {
    const state = makeState({
      phase: 'spoonGrab',
      spoonsRemaining: 1,
      players: [
        makePlayer({ isHuman: true, name: 'You', grabbedSpoon: true }),
        makePlayer({ name: 'Bot 1', grabbedSpoon: false }),
        makePlayer({ name: 'Bot 2', grabbedSpoon: false }),
      ],
    })
    // Bot 1 grabs the last spoon → Bot 2 loses
    const next = grabSpoon(state, 1)
    expect(next.phase).toBe('roundOver')
    expect(next.players[2].letters).toBe('S')
    expect(next.roundLoser).toBe(2)
  })

  it('should eliminate player who spells SPOONS', () => {
    const state = makeState({
      phase: 'spoonGrab',
      spoonsRemaining: 1,
      players: [
        makePlayer({ isHuman: true, name: 'You', grabbedSpoon: true }),
        makePlayer({ name: 'Bot 1', grabbedSpoon: false, letters: 'SPOON' }),
        makePlayer({ name: 'Bot 2', grabbedSpoon: false }),
      ],
    })
    // Bot 2 grabs last spoon → Bot 1 gets 'S' (completing SPOONS) → eliminated
    const next = grabSpoon(state, 2)
    expect(next.players[1].letters).toBe('SPOONS')
    expect(next.players[1].eliminated).toBe(true)
  })

  it('should end game when only 1 player remains', () => {
    const state = makeState({
      phase: 'spoonGrab',
      spoonsRemaining: 1,
      players: [
        makePlayer({ isHuman: true, name: 'You', grabbedSpoon: true }),
        makePlayer({ name: 'Bot 1', letters: 'SPOON', grabbedSpoon: false }),
        makePlayer({ name: 'Bot 2', eliminated: true }),
      ],
    })
    // No one else to grab — Bot 1 will get their 6th letter
    // But we need someone to grab the last spoon. Actually there's only 1 spoon left
    // and only 2 active players. You already grabbed. So this is the losing scenario.
    // Let's fix: there's 1 spoon remaining. Someone grabs it.
    // Actually player 0 already grabbed. spoonsRemaining=1.
    // We can't call grabSpoon for a player who already grabbed.
    // The scenario is: 2 active players, 1 spoon. Player 0 grabbed it.
    // Bot 1 is the loser. But grabSpoon is called when another player tries...
    // Let me re-think: when spoonsRemaining drops to 0, loser is detected.
    // Player 0 already has their spoon. Let's have a fresh scenario.

    // Re-setup: 2 active players (You + Bot 1), Bot 2 eliminated, 1 spoon
    const state2 = makeState({
      phase: 'spoonGrab',
      spoonsRemaining: 1,
      players: [
        makePlayer({ isHuman: true, name: 'You', grabbedSpoon: false }),
        makePlayer({ name: 'Bot 1', letters: 'SPOON', grabbedSpoon: false }),
        makePlayer({ name: 'Bot 2', eliminated: true }),
      ],
    })
    // You grab the spoon → Bot 1 loses, completes SPOONS, eliminated → only you left
    const next2 = grabSpoon(state2, 0)
    expect(next2.phase).toBe('gameOver')
    expect(next2.players[1].eliminated).toBe(true)
  })

  it('should not let eliminated player grab', () => {
    const state = makeState({
      phase: 'spoonGrab',
      players: [
        makePlayer({ isHuman: true, name: 'You' }),
        makePlayer({ name: 'Bot 1', eliminated: true }),
        makePlayer({ name: 'Bot 2' }),
      ],
    })
    const next = grabSpoon(state, 1)
    expect(next).toBe(state)
  })

  it('should not let player grab twice', () => {
    const state = makeState({
      phase: 'spoonGrab',
      players: [
        makePlayer({ isHuman: true, name: 'You', grabbedSpoon: true }),
        makePlayer({ name: 'Bot 1' }),
        makePlayer({ name: 'Bot 2' }),
      ],
    })
    const next = grabSpoon(state, 0)
    expect(next).toBe(state)
  })
})

// ── newRound ────────────────────────────────────────────────────────

describe('newRound', () => {
  it('should deal 4 cards to active players only', () => {
    const state = makeState({
      phase: 'roundOver',
      players: [
        makePlayer({ isHuman: true, name: 'You' }),
        makePlayer({ name: 'Bot 1', eliminated: true }),
        makePlayer({ name: 'Bot 2' }),
      ],
    })
    const next = newRound(state)
    expect(next.players[0].hand).toHaveLength(4)
    expect(next.players[1].hand).toHaveLength(0) // eliminated
    expect(next.players[2].hand).toHaveLength(4)
  })

  it('should reset spoons to active players - 1', () => {
    const state = makeState({
      phase: 'roundOver',
      players: [
        makePlayer({ isHuman: true, name: 'You' }),
        makePlayer({ name: 'Bot 1', eliminated: true }),
        makePlayer({ name: 'Bot 2' }),
      ],
    })
    const next = newRound(state)
    expect(next.spoonsRemaining).toBe(1) // 2 active - 1
  })

  it('should rotate dealer', () => {
    const state = makeState({ phase: 'roundOver', dealer: 0 })
    const next = newRound(state)
    expect(next.dealer).toBe(1)
  })

  it('should reset grabbedSpoon for all players', () => {
    const state = makeState({
      phase: 'roundOver',
      players: [
        makePlayer({ isHuman: true, name: 'You', grabbedSpoon: true }),
        makePlayer({ name: 'Bot 1', grabbedSpoon: true }),
        makePlayer({ name: 'Bot 2', grabbedSpoon: false }),
      ],
    })
    const next = newRound(state)
    expect(next.players.every(p => !p.grabbedSpoon)).toBe(true)
  })

  it('should not start new round if not roundOver', () => {
    const state = makeState({ phase: 'drawing' })
    expect(newRound(state)).toBe(state)
  })

  it('should increment round number', () => {
    const state = makeState({ phase: 'roundOver', roundNumber: 3 })
    const next = newRound(state)
    expect(next.roundNumber).toBe(4)
  })
})

// ── aiDiscard ───────────────────────────────────────────────────────

describe('aiDiscard', () => {
  it('should keep cards of the most frequent rank', () => {
    const hand = [
      makeCard(7, 'hearts'),
      makeCard(7, 'diamonds'),
      makeCard(7, 'clubs'),
      makeCard(3, 'spades'),
      makeCard(5, 'hearts'),
    ]
    const idx = aiDiscard(hand)
    // Should discard 3 or 5, not a 7
    expect(hand[idx].rank).not.toBe(7)
  })

  it('should discard the least frequent rank', () => {
    const hand = [
      makeCard(7, 'hearts'),
      makeCard(7, 'diamonds'),
      makeCard(3, 'clubs'),
      makeCard(3, 'spades'),
      makeCard(5, 'hearts'),
    ]
    const idx = aiDiscard(hand)
    // 7 appears 2x, 3 appears 2x, 5 appears 1x → discard 5
    expect(hand[idx].rank).toBe(5)
  })

  it('should return a valid index', () => {
    const hand = [makeCard(1), makeCard(2), makeCard(3), makeCard(4), makeCard(5)]
    const idx = aiDiscard(hand)
    expect(idx).toBeGreaterThanOrEqual(0)
    expect(idx).toBeLessThan(hand.length)
  })
})

// ── getAiGrabDelays ─────────────────────────────────────────────────

describe('getAiGrabDelays', () => {
  it('should return only AI players that haven\'t grabbed', () => {
    const state = makeState({
      phase: 'spoonGrab',
      players: [
        makePlayer({ isHuman: true, name: 'You' }),
        makePlayer({ name: 'Bot 1', reactionTime: 500 }),
        makePlayer({ name: 'Bot 2', reactionTime: 300 }),
      ],
    })
    const delays = getAiGrabDelays(state)
    expect(delays).toHaveLength(2)
    // Should be sorted by delay (fastest first)
    expect(delays[0].delay).toBeLessThanOrEqual(delays[1].delay)
  })

  it('should exclude eliminated players', () => {
    const state = makeState({
      phase: 'spoonGrab',
      players: [
        makePlayer({ isHuman: true, name: 'You' }),
        makePlayer({ name: 'Bot 1', eliminated: true }),
        makePlayer({ name: 'Bot 2' }),
      ],
    })
    const delays = getAiGrabDelays(state)
    expect(delays).toHaveLength(1)
    expect(delays[0].playerIndex).toBe(2)
  })
})

// ── Utility helpers ─────────────────────────────────────────────────

describe('getActiveCount', () => {
  it('should count non-eliminated players', () => {
    const players = [
      makePlayer({ eliminated: false }),
      makePlayer({ eliminated: true }),
      makePlayer({ eliminated: false }),
    ]
    expect(getActiveCount(players)).toBe(2)
  })
})

describe('getNextActive', () => {
  it('should skip eliminated players', () => {
    const players = [
      makePlayer({ eliminated: false }),
      makePlayer({ eliminated: true }),
      makePlayer({ eliminated: false }),
    ]
    expect(getNextActive(players, 0)).toBe(2)
  })

  it('should wrap around', () => {
    const players = [
      makePlayer({ eliminated: false }),
      makePlayer({ eliminated: false }),
      makePlayer({ eliminated: false }),
    ]
    expect(getNextActive(players, 2)).toBe(0)
  })
})

describe('isHumanTurn', () => {
  it('should return true during spoon grab phase', () => {
    const state = makeState({ phase: 'spoonGrab', currentPlayer: 1 })
    expect(isHumanTurn(state)).toBe(true)
  })

  it('should return true when current player is human', () => {
    const state = makeState({ phase: 'drawing', currentPlayer: 0 })
    expect(isHumanTurn(state)).toBe(true)
  })

  it('should return false when current player is AI', () => {
    const state = makeState({ phase: 'drawing', currentPlayer: 1 })
    expect(isHumanTurn(state)).toBe(false)
  })
})
