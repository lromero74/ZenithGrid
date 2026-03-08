import { describe, test, expect } from 'vitest'
import type { Card } from '../../../utils/cardUtils'
import {
  evaluateHand,
  createTexasHoldemGame,
  startHand,
  fold,
  check,
  call,
  raise,
  allIn,
  advancePhase,
  showdown,
  getValidActions,
  getMinRaise,
  setBlinds,
  type TexasHoldemState,
  type HandResult,
  type Phase,
} from './TexasHoldemEngine'

// Helper: create a face-up card
function card(rank: number, suit: Card['suit']): Card {
  return { rank, suit, faceUp: true }
}

// Helper: build a partial game state with defaults
function makeState(overrides: Partial<TexasHoldemState> = {}): TexasHoldemState {
  return {
    hands: [
      [card(14, 'hearts'), card(13, 'hearts')],
      [card(2, 'clubs'), card(3, 'clubs')],
    ],
    community: [],
    deck: [],
    pot: 30,
    bets: [20, 20],
    chips: [980, 980],
    phase: 'preflop' as Phase,
    currentPlayer: 0,
    dealerIdx: 0,
    smallBlind: 10,
    bigBlind: 20,
    foldedPlayers: [false, false],
    allInPlayers: [false, false],
    currentBet: 20,
    message: '',
    lastAction: '',
    roundBets: [20, 20],
    showdownResults: null,
    actedThisRound: [false, false],
    sbIdx: 0,
    bbIdx: 1,
    blindLevel: 0,
    ...overrides,
  }
}

// ─── Hand Evaluator Tests ───────────────────────────────────────────────

describe('evaluateHand', () => {
  describe('Royal Flush', () => {
    test('detects royal flush', () => {
      const cards = [
        card(1, 'spades'),  // Ace
        card(13, 'spades'), // King
        card(12, 'spades'), // Queen
        card(11, 'spades'), // Jack
        card(10, 'spades'), // 10
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(10)
      expect(result.name).toBe('Royal Flush')
      expect(result.tiebreaker).toEqual([])
    })

    test('finds royal flush from 7 cards', () => {
      const cards = [
        card(1, 'hearts'),
        card(13, 'hearts'),
        card(12, 'hearts'),
        card(11, 'hearts'),
        card(10, 'hearts'),
        card(2, 'clubs'),
        card(5, 'diamonds'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(10)
      expect(result.name).toBe('Royal Flush')
    })
  })

  describe('Straight Flush', () => {
    test('detects straight flush', () => {
      const cards = [
        card(9, 'hearts'),
        card(8, 'hearts'),
        card(7, 'hearts'),
        card(6, 'hearts'),
        card(5, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(9)
      expect(result.name).toBe('Straight Flush')
      expect(result.tiebreaker).toEqual([9])
    })

    test('detects wheel straight flush (A-2-3-4-5)', () => {
      const cards = [
        card(1, 'diamonds'),
        card(2, 'diamonds'),
        card(3, 'diamonds'),
        card(4, 'diamonds'),
        card(5, 'diamonds'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(9)
      expect(result.name).toBe('Straight Flush')
      expect(result.tiebreaker).toEqual([5]) // 5-high, not ace-high
    })
  })

  describe('Four of a Kind', () => {
    test('detects four of a kind', () => {
      const cards = [
        card(8, 'hearts'),
        card(8, 'diamonds'),
        card(8, 'clubs'),
        card(8, 'spades'),
        card(13, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(8)
      expect(result.name).toBe('Four of a Kind')
      expect(result.tiebreaker).toEqual([8, 13])
    })

    test('four aces with kicker', () => {
      const cards = [
        card(1, 'hearts'),
        card(1, 'diamonds'),
        card(1, 'clubs'),
        card(1, 'spades'),
        card(13, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(8)
      expect(result.tiebreaker).toEqual([14, 13]) // Ace = 14 for comparison
    })
  })

  describe('Full House', () => {
    test('detects full house', () => {
      const cards = [
        card(10, 'hearts'),
        card(10, 'diamonds'),
        card(10, 'clubs'),
        card(4, 'spades'),
        card(4, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(7)
      expect(result.name).toBe('Full House')
      expect(result.tiebreaker).toEqual([10, 4])
    })

    test('aces full of kings', () => {
      const cards = [
        card(1, 'hearts'),
        card(1, 'diamonds'),
        card(1, 'clubs'),
        card(13, 'spades'),
        card(13, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(7)
      expect(result.tiebreaker).toEqual([14, 13])
    })

    test('picks best full house from 7 cards', () => {
      // Two possible full houses: KKK-QQ or QQQ-KK — KKK is better
      const cards = [
        card(13, 'hearts'),
        card(13, 'diamonds'),
        card(13, 'clubs'),
        card(12, 'spades'),
        card(12, 'hearts'),
        card(12, 'diamonds'),
        card(2, 'clubs'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(7)
      expect(result.tiebreaker).toEqual([13, 12])
    })
  })

  describe('Flush', () => {
    test('detects flush', () => {
      const cards = [
        card(1, 'clubs'),
        card(10, 'clubs'),
        card(7, 'clubs'),
        card(4, 'clubs'),
        card(2, 'clubs'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(6)
      expect(result.name).toBe('Flush')
      expect(result.tiebreaker).toEqual([14, 10, 7, 4, 2])
    })

    test('flush beats straight', () => {
      // 7 cards containing both a straight and a flush
      const cards = [
        card(1, 'hearts'),
        card(9, 'hearts'),
        card(7, 'hearts'),
        card(5, 'hearts'),
        card(3, 'hearts'),
        card(6, 'clubs'),
        card(4, 'diamonds'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(6) // Flush, not straight
    })
  })

  describe('Straight', () => {
    test('detects straight', () => {
      const cards = [
        card(9, 'hearts'),
        card(8, 'clubs'),
        card(7, 'diamonds'),
        card(6, 'spades'),
        card(5, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(5)
      expect(result.name).toBe('Straight')
      expect(result.tiebreaker).toEqual([9])
    })

    test('detects broadway straight (A-K-Q-J-10)', () => {
      const cards = [
        card(1, 'hearts'),
        card(13, 'clubs'),
        card(12, 'diamonds'),
        card(11, 'spades'),
        card(10, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(5)
      expect(result.tiebreaker).toEqual([14])
    })

    test('detects wheel straight (A-2-3-4-5)', () => {
      const cards = [
        card(1, 'hearts'),
        card(2, 'clubs'),
        card(3, 'diamonds'),
        card(4, 'spades'),
        card(5, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(5)
      expect(result.name).toBe('Straight')
      expect(result.tiebreaker).toEqual([5]) // 5-high, ace is low
    })

    test('straight from 7 cards', () => {
      const cards = [
        card(10, 'hearts'),
        card(9, 'clubs'),
        card(8, 'diamonds'),
        card(7, 'spades'),
        card(6, 'hearts'),
        card(2, 'clubs'),
        card(3, 'diamonds'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(5)
      expect(result.tiebreaker).toEqual([10])
    })
  })

  describe('Three of a Kind', () => {
    test('detects three of a kind', () => {
      const cards = [
        card(7, 'hearts'),
        card(7, 'diamonds'),
        card(7, 'clubs'),
        card(13, 'spades'),
        card(2, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(4)
      expect(result.name).toBe('Three of a Kind')
      expect(result.tiebreaker).toEqual([7, 13, 2])
    })
  })

  describe('Two Pair', () => {
    test('detects two pair', () => {
      const cards = [
        card(11, 'hearts'),
        card(11, 'diamonds'),
        card(4, 'clubs'),
        card(4, 'spades'),
        card(13, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(3)
      expect(result.name).toBe('Two Pair')
      expect(result.tiebreaker).toEqual([11, 4, 13])
    })

    test('picks best two pair from 7 cards with 3 pairs', () => {
      const cards = [
        card(13, 'hearts'),
        card(13, 'diamonds'),
        card(9, 'clubs'),
        card(9, 'spades'),
        card(5, 'hearts'),
        card(5, 'diamonds'),
        card(2, 'clubs'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(3)
      // Should pick KK and 99 (top two pairs), kicker is 5
      expect(result.tiebreaker).toEqual([13, 9, 5])
    })
  })

  describe('One Pair', () => {
    test('detects one pair', () => {
      const cards = [
        card(10, 'hearts'),
        card(10, 'diamonds'),
        card(1, 'clubs'),
        card(8, 'spades'),
        card(4, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(2)
      expect(result.name).toBe('Pair')
      expect(result.tiebreaker).toEqual([10, 14, 8, 4])
    })
  })

  describe('High Card', () => {
    test('detects high card', () => {
      const cards = [
        card(1, 'hearts'),
        card(10, 'clubs'),
        card(7, 'diamonds'),
        card(4, 'spades'),
        card(2, 'hearts'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(1)
      expect(result.name).toBe('High Card')
      expect(result.tiebreaker).toEqual([14, 10, 7, 4, 2])
    })
  })

  describe('Tiebreakers', () => {
    test('pair of kings beats pair of queens', () => {
      const kings = evaluateHand([
        card(13, 'hearts'), card(13, 'diamonds'),
        card(9, 'clubs'), card(5, 'spades'), card(2, 'hearts'),
      ])
      const queens = evaluateHand([
        card(12, 'hearts'), card(12, 'diamonds'),
        card(9, 'clubs'), card(5, 'spades'), card(2, 'hearts'),
      ])
      expect(kings.rank).toBe(queens.rank) // Both pairs
      expect(kings.tiebreaker[0]).toBeGreaterThan(queens.tiebreaker[0])
    })

    test('same pair, higher kicker wins', () => {
      const highKicker = evaluateHand([
        card(10, 'hearts'), card(10, 'diamonds'),
        card(1, 'clubs'), card(5, 'spades'), card(2, 'hearts'),
      ])
      const lowKicker = evaluateHand([
        card(10, 'clubs'), card(10, 'spades'),
        card(9, 'diamonds'), card(5, 'hearts'), card(2, 'clubs'),
      ])
      expect(highKicker.rank).toBe(lowKicker.rank)
      expect(highKicker.tiebreaker[0]).toBe(lowKicker.tiebreaker[0]) // Same pair
      expect(highKicker.tiebreaker[1]).toBeGreaterThan(lowKicker.tiebreaker[1]) // Higher kicker
    })

    test('higher flush beats lower flush', () => {
      const highFlush = evaluateHand([
        card(1, 'hearts'), card(13, 'hearts'),
        card(10, 'hearts'), card(7, 'hearts'), card(3, 'hearts'),
      ])
      const lowFlush = evaluateHand([
        card(12, 'clubs'), card(10, 'clubs'),
        card(8, 'clubs'), card(5, 'clubs'), card(3, 'clubs'),
      ])
      expect(highFlush.rank).toBe(6)
      expect(lowFlush.rank).toBe(6)
      expect(highFlush.tiebreaker[0]).toBeGreaterThan(lowFlush.tiebreaker[0])
    })

    test('higher straight flush beats lower', () => {
      const high = evaluateHand([
        card(10, 'spades'), card(9, 'spades'),
        card(8, 'spades'), card(7, 'spades'), card(6, 'spades'),
      ])
      const low = evaluateHand([
        card(7, 'hearts'), card(6, 'hearts'),
        card(5, 'hearts'), card(4, 'hearts'), card(3, 'hearts'),
      ])
      expect(high.rank).toBe(9)
      expect(low.rank).toBe(9)
      expect(high.tiebreaker[0]).toBeGreaterThan(low.tiebreaker[0])
    })
  })

  describe('Best 5 from 7', () => {
    test('finds hidden straight in 7 cards', () => {
      const cards = [
        card(1, 'hearts'),  // Ace
        card(13, 'clubs'),
        card(12, 'diamonds'),
        card(11, 'spades'),
        card(10, 'hearts'),
        card(4, 'clubs'),
        card(2, 'diamonds'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(5) // Straight (A-K-Q-J-10 = broadway)
      expect(result.tiebreaker).toEqual([14])
    })

    test('finds flush hidden among 7 mixed cards', () => {
      const cards = [
        card(1, 'spades'),
        card(11, 'spades'),
        card(8, 'spades'),
        card(5, 'spades'),
        card(3, 'spades'),
        card(13, 'hearts'),
        card(12, 'diamonds'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(6) // Flush
    })

    test('four of a kind from 7 cards picks best kicker', () => {
      const cards = [
        card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs'), card(9, 'spades'),
        card(1, 'hearts'), card(13, 'clubs'), card(7, 'diamonds'),
      ]
      const result = evaluateHand(cards)
      expect(result.rank).toBe(8)
      expect(result.tiebreaker).toEqual([9, 14]) // Ace is the best kicker
    })
  })
})

// ─── Game Creation & Setup ──────────────────────────────────────────────

describe('createTexasHoldemGame', () => {
  test('creates game with default 4 players', () => {
    const state = createTexasHoldemGame()
    expect(state.hands).toHaveLength(4)
    expect(state.chips).toHaveLength(4)
    expect(state.chips.every(c => c === 1000)).toBe(true)
    expect(state.phase).toBe('preflop')
    expect(state.dealerIdx).toBe(0)
  })

  test('creates game with custom player count', () => {
    const state = createTexasHoldemGame(2)
    expect(state.hands).toHaveLength(2)
    expect(state.chips).toHaveLength(2)
  })

  test('initializes empty community cards', () => {
    const state = createTexasHoldemGame()
    expect(state.community).toHaveLength(0)
  })

  test('initializes blinds correctly', () => {
    const state = createTexasHoldemGame()
    expect(state.smallBlind).toBe(10)
    expect(state.bigBlind).toBe(20)
  })
})

describe('startHand', () => {
  test('deals 2 cards to each player', () => {
    const state = createTexasHoldemGame(4)
    const dealt = startHand(state)
    for (const hand of dealt.hands) {
      expect(hand).toHaveLength(2)
    }
  })

  test('posts small and big blinds', () => {
    const state = createTexasHoldemGame(4)
    const dealt = startHand(state)
    // dealer=0: SB=player 1, BB=player 2
    expect(dealt.bets[1]).toBe(10) // small blind
    expect(dealt.bets[2]).toBe(20) // big blind
    expect(dealt.chips[1]).toBe(990) // 1000 - 10
    expect(dealt.chips[2]).toBe(980) // 1000 - 20
    expect(dealt.pot).toBe(30)
    expect(dealt.currentBet).toBe(20)
  })

  test('clears community cards', () => {
    const state = createTexasHoldemGame(4)
    const dealt = startHand(state)
    expect(dealt.community).toHaveLength(0)
  })

  test('resets fold and all-in status', () => {
    const state = createTexasHoldemGame(4)
    const dealt = startHand(state)
    expect(dealt.foldedPlayers.every(f => !f)).toBe(true)
    expect(dealt.allInPlayers.every(a => !a)).toBe(true)
  })

  test('sets current player to left of big blind (UTG)', () => {
    const state = createTexasHoldemGame(4)
    const dealt = startHand(state)
    // dealer=0, SB=1, BB=2, UTG=3
    expect(dealt.currentPlayer).toBe(3)
  })

  test('skips eliminated players for blinds', () => {
    const state = createTexasHoldemGame(4)
    state.chips = [1000, 0, 1000, 1000] // player 1 eliminated
    const dealt = startHand(state)
    // dealer=0, SB=2 (skip 1), BB=3
    expect(dealt.bets[2]).toBe(10)
    expect(dealt.bets[3]).toBe(20)
  })
})

// ─── Player Actions ─────────────────────────────────────────────────────

describe('fold', () => {
  test('marks player as folded', () => {
    const state = makeState({ currentPlayer: 0 })
    const result = fold(state)
    expect(result.foldedPlayers[0]).toBe(true)
  })

  test('ends hand when only one player remains', () => {
    const state = makeState({ currentPlayer: 0 })
    const result = fold(state)
    // In a 2-player game, fold ends the hand
    expect(result.phase).toBe('handOver')
  })

  test('last remaining player wins pot if all others fold', () => {
    const state = makeState({
      currentPlayer: 0,
      foldedPlayers: [false, false],
      pot: 100,
      chips: [980, 980],
    })
    const result = fold(state)
    // Player 0 folds, player 1 wins
    expect(result.foldedPlayers[0]).toBe(true)
    expect(result.phase).toBe('handOver')
    expect(result.chips[1]).toBe(980 + 100)
  })
})

describe('check', () => {
  test('advances to next player without adding to pot', () => {
    const state = makeState({
      currentPlayer: 0,
      bets: [20, 20],
      currentBet: 20,
      pot: 40,
      actedThisRound: [false, false],
    })
    const result = check(state)
    expect(result.pot).toBe(40) // unchanged
    // Player 0 checked; player 1 hasn't acted yet, so it should be their turn
    expect(result.currentPlayer).toBe(1)
  })
})

describe('call', () => {
  test('matches current bet and deducts chips', () => {
    // Use 3 players so round doesn't auto-complete after call
    const state = makeState({
      currentPlayer: 0,
      hands: [
        [card(14, 'hearts'), card(13, 'hearts')],
        [card(2, 'clubs'), card(3, 'clubs')],
        [card(7, 'diamonds'), card(8, 'diamonds')],
      ],
      bets: [0, 40, 0],
      roundBets: [0, 40, 0],
      currentBet: 40,
      chips: [1000, 960, 1000],
      foldedPlayers: [false, false, false],
      allInPlayers: [false, false, false],
      actedThisRound: [false, true, false],
      pot: 40,
    })
    const result = call(state)
    expect(result.chips[0]).toBe(960) // 1000 - 40
  })

  test('call with insufficient chips goes all-in', () => {
    const state = makeState({
      currentPlayer: 0,
      hands: [
        [card(14, 'hearts'), card(13, 'hearts')],
        [card(2, 'clubs'), card(3, 'clubs')],
        [card(7, 'diamonds'), card(8, 'diamonds')],
      ],
      bets: [0, 100, 0],
      roundBets: [0, 100, 0],
      currentBet: 100,
      chips: [50, 900, 1000],
      foldedPlayers: [false, false, false],
      allInPlayers: [false, false, false],
      actedThisRound: [false, true, false],
      pot: 100,
    })
    const result = call(state)
    expect(result.chips[0]).toBe(0)
    expect(result.allInPlayers[0]).toBe(true)
  })
})

describe('raise', () => {
  test('raises to specified amount', () => {
    const state = makeState({
      currentPlayer: 0,
      bets: [20, 20],
      currentBet: 20,
      chips: [980, 980],
      pot: 40,
    })
    const result = raise(state, 60) // raise to 60
    expect(result.bets[0]).toBe(60)
    expect(result.chips[0]).toBe(940) // 980 - (60 - 20)
    expect(result.currentBet).toBe(60)
    expect(result.pot).toBe(80) // 40 + 40 additional
  })

  test('raise must be at least min raise', () => {
    const state = makeState({
      currentPlayer: 0,
      bets: [0, 40],
      currentBet: 40,
      chips: [1000, 960],
      pot: 40,
    })
    // Min raise = current bet + (current bet - last raise) = at least 2x the bet
    const minRaise = getMinRaise(state)
    expect(minRaise).toBeGreaterThanOrEqual(40)
  })
})

describe('allIn', () => {
  test('puts all remaining chips in', () => {
    const state = makeState({
      currentPlayer: 0,
      bets: [20, 20],
      chips: [980, 980],
      pot: 40,
      currentBet: 20,
    })
    const result = allIn(state)
    expect(result.chips[0]).toBe(0)
    expect(result.allInPlayers[0]).toBe(true)
    expect(result.bets[0]).toBe(1000) // 20 + 980
    expect(result.pot).toBe(1020) // 40 + 980
  })
})

// ─── Betting Round Completion ────────────────────────────────────────────

describe('betting round requires all players to act', () => {
  test('flop betting does not skip players when currentBet is 0', () => {
    // 4-player game, flop phase, bets all 0, nobody acted yet
    const state = makeState({
      phase: 'flop' as Phase,
      hands: [
        [card(14, 'hearts'), card(13, 'hearts')],
        [card(2, 'clubs'), card(3, 'clubs')],
        [card(7, 'diamonds'), card(8, 'diamonds')],
        [card(9, 'spades'), card(10, 'spades')],
      ],
      bets: [0, 0, 0, 0],
      currentBet: 0,
      chips: [980, 980, 980, 980],
      foldedPlayers: [false, false, false, false],
      allInPlayers: [false, false, false, false],
      actedThisRound: [false, false, false, false],
      roundBets: [0, 0, 0, 0],
      currentPlayer: 1,
      community: [card(5, 'hearts'), card(6, 'clubs'), card(2, 'diamonds')],
      deck: Array.from({ length: 10 }, (_, i) => card((i % 13) + 1, 'hearts')),
      pot: 80,
    })
    // Player 1 checks — should NOT advance phase, players 2 and 3 haven't acted
    const after1 = check(state)
    expect(after1.phase).toBe('flop')
    expect(after1.currentPlayer).toBe(2)

    // Player 2 checks — still waiting on players 3 and 0
    const after2 = check(after1)
    expect(after2.phase).toBe('flop')
    expect(after2.currentPlayer).toBe(3)

    // Player 3 checks — still waiting on player 0
    const after3 = check(after2)
    expect(after3.phase).toBe('flop')
    expect(after3.currentPlayer).toBe(0)

    // Player 0 checks — all have acted, should advance to turn
    const after4 = check(after3)
    expect(after4.phase).toBe('turn')
    expect(after4.community).toHaveLength(4)
  })

  test('raise resets acted flags so all must respond', () => {
    const state = makeState({
      phase: 'flop' as Phase,
      hands: [
        [card(14, 'hearts'), card(13, 'hearts')],
        [card(2, 'clubs'), card(3, 'clubs')],
        [card(7, 'diamonds'), card(8, 'diamonds')],
      ],
      bets: [0, 0, 0],
      currentBet: 0,
      chips: [980, 980, 980],
      foldedPlayers: [false, false, false],
      allInPlayers: [false, false, false],
      actedThisRound: [false, false, false],
      roundBets: [0, 0, 0],
      currentPlayer: 1,
      community: [card(5, 'hearts'), card(6, 'clubs'), card(2, 'diamonds')],
      deck: Array.from({ length: 10 }, (_, i) => card((i % 13) + 1, 'hearts')),
      pot: 60,
      bigBlind: 20,
    })
    // Player 1 checks
    const after1 = check(state)
    expect(after1.phase).toBe('flop')

    // Player 2 raises — resets acted for others
    const after2 = raise(after1, 40)
    expect(after2.phase).toBe('flop')
    expect(after2.currentBet).toBe(40)

    // Player 0 must respond (call)
    const after3 = call(after2)
    expect(after3.phase).toBe('flop') // Player 1 hasn't responded to raise yet

    // Player 1 calls the raise — now all have acted
    const after4 = call(after3)
    expect(after4.phase).toBe('turn')
  })
})

// ─── Phase Progression ──────────────────────────────────────────────────

describe('advancePhase', () => {
  test('preflop to flop deals 3 community cards', () => {
    const game = createTexasHoldemGame(2)
    const dealt = startHand(game)
    const flopState = { ...dealt, phase: 'preflop' as Phase }
    const result = advancePhase(flopState)
    expect(result.phase).toBe('flop')
    expect(result.community).toHaveLength(3)
  })

  test('flop to turn deals 1 community card', () => {
    const state = makeState({
      phase: 'flop',
      community: [card(10, 'hearts'), card(5, 'clubs'), card(3, 'diamonds')],
      deck: [card(8, 'spades'), card(7, 'hearts'), card(6, 'clubs')],
    })
    const result = advancePhase(state)
    expect(result.phase).toBe('turn')
    expect(result.community).toHaveLength(4)
  })

  test('turn to river deals 1 community card', () => {
    const state = makeState({
      phase: 'turn',
      community: [card(10, 'hearts'), card(5, 'clubs'), card(3, 'diamonds'), card(8, 'spades')],
      deck: [card(7, 'hearts'), card(6, 'clubs')],
    })
    const result = advancePhase(state)
    expect(result.phase).toBe('river')
    expect(result.community).toHaveLength(5)
  })

  test('river advances to handOver (showdown resolves immediately)', () => {
    const state = makeState({
      phase: 'river',
      community: [
        card(10, 'hearts'), card(5, 'clubs'), card(3, 'diamonds'),
        card(8, 'spades'), card(7, 'hearts'),
      ],
    })
    const result = advancePhase(state)
    // showdown() evaluates hands and returns handOver with results
    expect(result.phase).toBe('handOver')
    expect(result.showdownResults).not.toBeNull()
  })

  test('resets current round bets when advancing', () => {
    const state = makeState({
      phase: 'preflop',
      bets: [40, 40],
      currentBet: 40,
      deck: Array.from({ length: 20 }, (_, i) => card((i % 13) + 1, 'hearts')),
    })
    const result = advancePhase(state)
    expect(result.bets.every(b => b === 0)).toBe(true)
    expect(result.currentBet).toBe(0)
  })
})

// ─── Showdown ───────────────────────────────────────────────────────────

describe('showdown', () => {
  test('awards pot to player with best hand', () => {
    const state = makeState({
      phase: 'showdown',
      hands: [
        [card(1, 'hearts'), card(13, 'hearts')],  // Ace-King
        [card(2, 'clubs'), card(7, 'diamonds')],   // 2-7 offsuit
      ],
      community: [
        card(1, 'diamonds'), card(13, 'clubs'), card(5, 'spades'),
        card(9, 'hearts'), card(3, 'diamonds'),
      ],
      pot: 200,
      chips: [900, 900],
      foldedPlayers: [false, false],
    })
    const result = showdown(state)
    expect(result.phase).toBe('handOver')
    expect(result.showdownResults).not.toBeNull()
    // Player 0 has two pair (AA + KK), player 1 has nothing much
    expect(result.chips[0]).toBeGreaterThan(900)
  })

  test('splits pot on tie', () => {
    const state = makeState({
      phase: 'showdown',
      hands: [
        [card(2, 'hearts'), card(3, 'hearts')],
        [card(2, 'clubs'), card(3, 'clubs')],
      ],
      community: [
        card(1, 'diamonds'), card(13, 'spades'), card(12, 'diamonds'),
        card(11, 'hearts'), card(10, 'clubs'),
      ],
      pot: 200,
      chips: [900, 900],
      foldedPlayers: [false, false],
    })
    const result = showdown(state)
    // Both players play the board (A-K-Q-J-10 straight), split pot
    expect(result.chips[0]).toBe(1000)
    expect(result.chips[1]).toBe(1000)
  })

  test('skips folded players', () => {
    const state = makeState({
      phase: 'showdown',
      hands: [
        [card(2, 'hearts'), card(3, 'hearts')],
        [card(1, 'spades'), card(1, 'clubs')],
      ],
      community: [
        card(5, 'diamonds'), card(8, 'spades'), card(10, 'diamonds'),
        card(11, 'hearts'), card(4, 'clubs'),
      ],
      pot: 200,
      chips: [900, 900],
      foldedPlayers: [true, false], // Player 0 folded
    })
    const result = showdown(state)
    expect(result.chips[1]).toBe(1100) // Player 1 gets all
  })
})

// ─── Valid Actions ──────────────────────────────────────────────────────

describe('getValidActions', () => {
  test('can fold, call, raise when facing a bet', () => {
    const state = makeState({
      currentPlayer: 0,
      bets: [0, 40],
      currentBet: 40,
      chips: [1000, 960],
    })
    const actions = getValidActions(state)
    expect(actions).toContain('fold')
    expect(actions).toContain('call')
    expect(actions).toContain('raise')
    expect(actions).not.toContain('check')
  })

  test('can check when no bet to call', () => {
    const state = makeState({
      currentPlayer: 0,
      bets: [20, 20],
      currentBet: 20,
      chips: [980, 980],
    })
    const actions = getValidActions(state)
    expect(actions).toContain('check')
    expect(actions).not.toContain('call')
  })

  test('can go all-in', () => {
    const state = makeState({
      currentPlayer: 0,
      bets: [0, 40],
      currentBet: 40,
      chips: [1000, 960],
    })
    const actions = getValidActions(state)
    expect(actions).toContain('allIn')
  })

  test('only fold and all-in when chips less than call amount', () => {
    const state = makeState({
      currentPlayer: 0,
      bets: [0, 200],
      currentBet: 200,
      chips: [30, 800],
    })
    const actions = getValidActions(state)
    expect(actions).toContain('fold')
    expect(actions).toContain('allIn')
    expect(actions).not.toContain('raise')
  })
})

describe('getMinRaise', () => {
  test('min raise is at least current bet + big blind', () => {
    const state = makeState({
      currentPlayer: 0,
      bets: [0, 20],
      currentBet: 20,
      bigBlind: 20,
    })
    const min = getMinRaise(state)
    expect(min).toBe(40) // current bet (20) + big blind (20)
  })
})

// ─── Blind Levels ──────────────────────────────────────────────────────

describe('setBlinds', () => {
  test('level 0 is 10/20', () => {
    const state = makeState()
    const result = setBlinds(state, 0)
    expect(result.smallBlind).toBe(10)
    expect(result.bigBlind).toBe(20)
    expect(result.blindLevel).toBe(0)
  })

  test('level 1 is 20/40', () => {
    const result = setBlinds(makeState(), 1)
    expect(result.smallBlind).toBe(20)
    expect(result.bigBlind).toBe(40)
    expect(result.blindLevel).toBe(1)
  })

  test('level 2 is 40/80', () => {
    const result = setBlinds(makeState(), 2)
    expect(result.smallBlind).toBe(40)
    expect(result.bigBlind).toBe(80)
  })

  test('level 3 is 80/160', () => {
    const result = setBlinds(makeState(), 3)
    expect(result.smallBlind).toBe(80)
    expect(result.bigBlind).toBe(160)
  })
})

// ─── Full Hand End-to-End ──────────────────────────────────────────────

describe('full hand flow: preflop → flop → turn → river → showdown', () => {
  test('all 5 stages execute with proper betting rounds', () => {
    // 4-player game
    const game = createTexasHoldemGame(4)
    let state = startHand(game)

    // ── Stage 1: Pre-flop ──
    expect(state.phase).toBe('preflop')
    expect(state.community).toHaveLength(0)
    expect(state.hands.every(h => h.length === 2)).toBe(true)
    // Blinds posted: SB=P1(10), BB=P2(20), UTG=P3 acts first
    expect(state.currentPlayer).toBe(3)
    expect(state.currentBet).toBe(20)

    // Everyone calls the big blind
    state = call(state) // P3 calls
    expect(state.phase).toBe('preflop')
    state = call(state) // P0 calls
    expect(state.phase).toBe('preflop')
    state = call(state) // P1 (SB) calls 10 more
    expect(state.phase).toBe('preflop')
    state = check(state) // P2 (BB) checks — all matched, round complete

    // ── Stage 2: Flop ──
    expect(state.phase).toBe('flop')
    expect(state.community).toHaveLength(3)
    expect(state.currentBet).toBe(0)
    expect(state.bets.every(b => b === 0)).toBe(true)

    // All players check through the flop
    const flopFirstPlayer = state.currentPlayer
    state = check(state) // 1st player
    expect(state.phase).toBe('flop') // must NOT advance yet
    state = check(state) // 2nd player
    expect(state.phase).toBe('flop')
    state = check(state) // 3rd player
    expect(state.phase).toBe('flop')
    state = check(state) // 4th player — NOW it advances

    // ── Stage 3: Turn ──
    expect(state.phase).toBe('turn')
    expect(state.community).toHaveLength(4)
    expect(state.currentBet).toBe(0)

    // All players check through the turn
    state = check(state)
    expect(state.phase).toBe('turn')
    state = check(state)
    expect(state.phase).toBe('turn')
    state = check(state)
    expect(state.phase).toBe('turn')
    state = check(state)

    // ── Stage 4: River ──
    expect(state.phase).toBe('river')
    expect(state.community).toHaveLength(5)
    expect(state.currentBet).toBe(0)

    // All players check through the river
    state = check(state)
    expect(state.phase).toBe('river')
    state = check(state)
    expect(state.phase).toBe('river')
    state = check(state)
    expect(state.phase).toBe('river')
    state = check(state)

    // ── Stage 5: Showdown ──
    expect(state.phase).toBe('handOver')
    expect(state.showdownResults).not.toBeNull()
    expect(state.showdownResults!.length).toBe(4)
    // Pot was distributed to winner(s)
    expect(state.pot).toBe(0)
    expect(state.chips.reduce((a, b) => a + b, 0)).toBe(4000) // total chips conserved
  })

  test('fold during flop ends hand early without dealing turn/river', () => {
    const game = createTexasHoldemGame(2)
    let state = startHand(game)
    expect(state.phase).toBe('preflop')

    // Both players see flop
    state = call(state) // one player calls
    // After call in 2-player: SB called, BB checks to complete preflop
    if (state.phase === 'preflop') state = check(state)

    expect(state.phase).toBe('flop')
    expect(state.community).toHaveLength(3)

    // One player folds on the flop
    state = fold(state)
    expect(state.phase).toBe('handOver')
    // No turn or river dealt — still only 3 community cards
    expect(state.community).toHaveLength(3)
  })
})
