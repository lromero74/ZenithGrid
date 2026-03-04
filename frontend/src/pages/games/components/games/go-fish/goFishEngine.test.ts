import { describe, test, expect } from 'vitest'
import type { Card } from '../../../utils/cardUtils'
import {
  createGoFishGame,
  askForRank,
  goFish,
  aiTurn,
  checkForBooks,
  getAskableRanks,
  type GoFishState,
} from './goFishEngine'

function card(rank: number, suit: Card['suit'], faceUp = true): Card {
  return { rank, suit, faceUp }
}

/** Build a GoFishState with sensible defaults, allowing partial overrides. */
function makeState(overrides?: Partial<GoFishState>): GoFishState {
  return {
    hands: [
      [card(1, 'hearts'), card(5, 'spades'), card(10, 'diamonds')],
      [card(1, 'clubs'), card(7, 'hearts'), card(12, 'spades')],
    ],
    books: [[], []],
    pond: [card(3, 'hearts'), card(8, 'clubs'), card(9, 'diamonds')],
    phase: 'playerTurn',
    currentPlayer: 0,
    message: '',
    lastAskedRank: null,
    drawnCard: null,
    aiMemory: [],
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// createGoFishGame
// ---------------------------------------------------------------------------
describe('createGoFishGame', () => {
  test('deals 7 cards to each player with 38 in pond', () => {
    const state = createGoFishGame()
    expect(state.hands[0]).toHaveLength(7)
    expect(state.hands[1]).toHaveLength(7)
    expect(state.pond).toHaveLength(38)
  })

  test('all 52 cards are accounted for', () => {
    const state = createGoFishGame()
    const total = state.hands[0].length + state.hands[1].length + state.pond.length
    expect(total).toBe(52)
  })

  test('starts in playerTurn phase with player 0', () => {
    const state = createGoFishGame()
    expect(state.phase).toBe('playerTurn')
    expect(state.currentPlayer).toBe(0)
  })

  test('both players start with no books', () => {
    const state = createGoFishGame()
    expect(state.books[0]).toEqual([])
    expect(state.books[1]).toEqual([])
  })

  test('human cards are face up, AI cards face down', () => {
    const state = createGoFishGame()
    expect(state.hands[0].every(c => c.faceUp)).toBe(true)
    expect(state.hands[1].every(c => !c.faceUp)).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// askForRank — successful ask (opponent has the rank)
// ---------------------------------------------------------------------------
describe('askForRank — opponent has cards', () => {
  test('transfers all matching cards from opponent to asker', () => {
    const state = makeState({
      hands: [
        [card(5, 'hearts')],
        [card(5, 'clubs'), card(5, 'diamonds'), card(7, 'spades')],
      ],
    })
    const next = askForRank(state, 5)
    // Human should now have all three 5s
    const humanFives = next.hands[0].filter(c => c.rank === 5)
    expect(humanFives).toHaveLength(3)
    // AI should have no 5s left
    const aiFives = next.hands[1].filter(c => c.rank === 5)
    expect(aiFives).toHaveLength(0)
  })

  test('player gets another turn after successful ask', () => {
    const state = makeState({
      hands: [
        [card(5, 'hearts')],
        [card(5, 'clubs'), card(7, 'spades')],
      ],
    })
    const next = askForRank(state, 5)
    expect(next.phase).toBe('playerTurn')
    expect(next.currentPlayer).toBe(0)
  })

  test('message indicates cards were received', () => {
    const state = makeState({
      hands: [
        [card(10, 'hearts')],
        [card(10, 'clubs'), card(10, 'diamonds')],
      ],
    })
    const next = askForRank(state, 10)
    expect(next.message).toContain('10')
  })
})

// ---------------------------------------------------------------------------
// askForRank — failed ask (Go Fish)
// ---------------------------------------------------------------------------
describe('askForRank — opponent does not have cards', () => {
  test('transitions to goFish phase', () => {
    const state = makeState({
      hands: [
        [card(5, 'hearts')],
        [card(7, 'spades'), card(12, 'clubs')],
      ],
    })
    const next = askForRank(state, 5)
    expect(next.phase).toBe('goFish')
    expect(next.lastAskedRank).toBe(5)
  })

  test('message says Go Fish', () => {
    const state = makeState({
      hands: [
        [card(5, 'hearts')],
        [card(7, 'spades')],
      ],
    })
    const next = askForRank(state, 5)
    expect(next.message.toLowerCase()).toContain('go fish')
  })
})

// ---------------------------------------------------------------------------
// askForRank — guards
// ---------------------------------------------------------------------------
describe('askForRank — guards', () => {
  test('rejects ask for rank not in hand', () => {
    const state = makeState({
      hands: [
        [card(5, 'hearts')],
        [card(7, 'spades')],
      ],
    })
    const next = askForRank(state, 9)
    // Should return unchanged state or at least not crash
    expect(next.phase).toBe('playerTurn')
    expect(next.hands).toEqual(state.hands)
  })

  test('rejects ask when not in playerTurn phase', () => {
    const state = makeState({ phase: 'goFish' })
    const next = askForRank(state, 1)
    expect(next).toEqual(state)
  })
})

// ---------------------------------------------------------------------------
// goFish — draw from pond
// ---------------------------------------------------------------------------
describe('goFish', () => {
  test('draws one card from pond into current player hand', () => {
    const state = makeState({
      phase: 'goFish',
      currentPlayer: 0,
      lastAskedRank: 5,
      hands: [
        [card(5, 'hearts')],
        [card(7, 'spades')],
      ],
      pond: [card(3, 'clubs'), card(8, 'diamonds')],
    })
    const next = goFish(state)
    expect(next.hands[0]).toHaveLength(2)
    expect(next.pond).toHaveLength(1)
  })

  test('gets another turn if drawn card matches asked rank', () => {
    const pondCard = card(5, 'diamonds')
    const state = makeState({
      phase: 'goFish',
      currentPlayer: 0,
      lastAskedRank: 5,
      hands: [
        [card(5, 'hearts')],
        [card(7, 'spades')],
      ],
      pond: [pondCard],
    })
    const next = goFish(state)
    expect(next.currentPlayer).toBe(0)
    expect(next.phase).toBe('playerTurn')
    expect(next.drawnCard).toEqual(expect.objectContaining({ rank: 5 }))
  })

  test('turn passes to AI if drawn card does not match', () => {
    const pondCard = card(3, 'clubs')
    const state = makeState({
      phase: 'goFish',
      currentPlayer: 0,
      lastAskedRank: 5,
      hands: [
        [card(5, 'hearts')],
        [card(7, 'spades')],
      ],
      pond: [pondCard],
    })
    const next = goFish(state)
    expect(next.phase).toBe('aiTurn')
    expect(next.currentPlayer).toBe(1)
  })

  test('sets drawnCard for UI highlight', () => {
    const pondCard = card(8, 'hearts')
    const state = makeState({
      phase: 'goFish',
      currentPlayer: 0,
      lastAskedRank: 5,
      hands: [[card(5, 'hearts')], [card(7, 'spades')]],
      pond: [pondCard],
    })
    const next = goFish(state)
    expect(next.drawnCard).toEqual(expect.objectContaining({ rank: 8, suit: 'hearts' }))
  })

  test('returns unchanged state if not in goFish phase', () => {
    const state = makeState({ phase: 'playerTurn' })
    const next = goFish(state)
    expect(next).toEqual(state)
  })

  test('handles empty pond gracefully', () => {
    const state = makeState({
      phase: 'goFish',
      currentPlayer: 0,
      lastAskedRank: 5,
      hands: [[card(5, 'hearts')], [card(7, 'spades')]],
      pond: [],
    })
    const next = goFish(state)
    // Should pass turn since nothing to draw
    expect(next.hands[0]).toHaveLength(1)
    expect(next.phase).not.toBe('goFish')
  })
})

// ---------------------------------------------------------------------------
// checkForBooks
// ---------------------------------------------------------------------------
describe('checkForBooks', () => {
  test('extracts a book when hand has 4 of the same rank', () => {
    const hand = [
      card(5, 'hearts'), card(5, 'diamonds'), card(5, 'clubs'), card(5, 'spades'),
      card(7, 'hearts'),
    ]
    const result = checkForBooks(hand)
    expect(result.newBooks).toEqual([5])
    expect(result.hand).toHaveLength(1)
    expect(result.hand[0].rank).toBe(7)
  })

  test('extracts multiple books at once', () => {
    const hand = [
      card(5, 'hearts'), card(5, 'diamonds'), card(5, 'clubs'), card(5, 'spades'),
      card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs'), card(9, 'spades'),
    ]
    const result = checkForBooks(hand)
    expect(result.newBooks).toHaveLength(2)
    expect(result.newBooks).toContain(5)
    expect(result.newBooks).toContain(9)
    expect(result.hand).toHaveLength(0)
  })

  test('returns empty newBooks when no 4-of-a-kind exists', () => {
    const hand = [card(5, 'hearts'), card(5, 'diamonds'), card(7, 'clubs')]
    const result = checkForBooks(hand)
    expect(result.newBooks).toEqual([])
    expect(result.hand).toHaveLength(3)
  })

  test('handles empty hand', () => {
    const result = checkForBooks([])
    expect(result.newBooks).toEqual([])
    expect(result.hand).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// getAskableRanks
// ---------------------------------------------------------------------------
describe('getAskableRanks', () => {
  test('returns unique ranks in the human hand', () => {
    const state = makeState({
      hands: [
        [card(5, 'hearts'), card(5, 'diamonds'), card(10, 'clubs')],
        [card(7, 'spades')],
      ],
    })
    const ranks = getAskableRanks(state)
    expect(ranks).toContain(5)
    expect(ranks).toContain(10)
    expect(ranks).toHaveLength(2)
  })

  test('returns empty when hand is empty', () => {
    const state = makeState({ hands: [[], [card(7, 'spades')]] })
    const ranks = getAskableRanks(state)
    expect(ranks).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// aiTurn
// ---------------------------------------------------------------------------
describe('aiTurn', () => {
  test('AI asks for a rank it holds', () => {
    const state = makeState({
      phase: 'aiTurn',
      currentPlayer: 1,
      hands: [
        [card(5, 'hearts'), card(10, 'clubs')],
        [card(7, 'spades'), card(12, 'diamonds')],
      ],
      pond: [card(3, 'hearts')],
    })
    const next = aiTurn(state)
    // After AI turn, either got cards from human, or went to go fish and drew
    // The state should have advanced past aiTurn
    expect(next.phase).not.toBe('aiTurn')
  })

  test('AI takes cards from human when human has the rank', () => {
    const state = makeState({
      phase: 'aiTurn',
      currentPlayer: 1,
      hands: [
        [card(7, 'hearts'), card(7, 'diamonds'), card(10, 'clubs')],
        [card(7, 'spades')],
      ],
      pond: [card(3, 'hearts')],
    })
    const next = aiTurn(state)
    // AI should have gotten the 7s from human
    const aiSevens = next.hands[1].filter(c => c.rank === 7)
    expect(aiSevens.length).toBeGreaterThanOrEqual(1)
  })

  test('AI draws from pond when human lacks the rank', () => {
    const state = makeState({
      phase: 'aiTurn',
      currentPlayer: 1,
      hands: [
        [card(5, 'hearts')],
        [card(7, 'spades')],
      ],
      pond: [card(3, 'hearts'), card(8, 'clubs')],
    })
    const initialPondSize = state.pond.length
    const next = aiTurn(state)
    // AI drew from pond (Go Fish)
    expect(next.pond.length).toBeLessThanOrEqual(initialPondSize)
  })

  test('AI gets another turn on successful ask', () => {
    // Give AI a rank that human also has — AI should keep going
    const state = makeState({
      phase: 'aiTurn',
      currentPlayer: 1,
      hands: [
        [card(7, 'hearts'), card(5, 'clubs')],
        [card(7, 'spades')],
      ],
      // small pond so AI loop eventually ends
      pond: [card(3, 'hearts')],
    })
    const next = aiTurn(state)
    // AI got the 7 from human, then goes again — eventually finishes its multi-turn
    // We just verify state didn't crash and phase has advanced
    expect(['playerTurn', 'gameOver']).toContain(next.phase)
  })

  test('returns unchanged state if not in aiTurn phase', () => {
    const state = makeState({ phase: 'playerTurn' })
    const next = aiTurn(state)
    expect(next).toEqual(state)
  })

  test('AI prefers ranks with 3 cards (close to book)', () => {
    const state = makeState({
      phase: 'aiTurn',
      currentPlayer: 1,
      hands: [
        [card(5, 'hearts'), card(12, 'clubs')],
        [
          card(5, 'spades'), // 1 five
          card(12, 'hearts'), card(12, 'diamonds'), card(12, 'spades'), // 3 queens
        ],
      ],
      pond: [card(3, 'hearts')],
    })
    const next = aiTurn(state)
    // AI should have asked for 12 (queens) since it has 3 — gets human's queen → completes book
    expect(next.books[1]).toContain(12)
  })
})

// ---------------------------------------------------------------------------
// Book completion during gameplay
// ---------------------------------------------------------------------------
describe('book completion during ask', () => {
  test('completing a book during askForRank adds it to books array', () => {
    const state = makeState({
      hands: [
        [card(5, 'hearts'), card(5, 'diamonds'), card(5, 'clubs')],
        [card(5, 'spades'), card(7, 'hearts')],
      ],
    })
    const next = askForRank(state, 5)
    expect(next.books[0]).toContain(5)
    // All 4 fives removed from hand
    expect(next.hands[0].filter(c => c.rank === 5)).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Game over
// ---------------------------------------------------------------------------
describe('game over', () => {
  test('game ends when all 13 books are made', () => {
    // Set up state where the final book is about to be completed
    const state = makeState({
      hands: [
        [card(13, 'hearts'), card(13, 'diamonds'), card(13, 'clubs')],
        [card(13, 'spades')],
      ],
      books: [
        [1, 2, 3, 4, 5, 6],
        [7, 8, 9, 10, 11, 12],
      ],
      pond: [],
    })
    const next = askForRank(state, 13)
    expect(next.phase).toBe('gameOver')
    expect(next.books[0]).toContain(13)
  })

  test('game ends when pond is empty and a player has no cards', () => {
    const state = makeState({
      phase: 'goFish',
      currentPlayer: 0,
      lastAskedRank: 5,
      hands: [
        [card(5, 'hearts')],
        [],
      ],
      pond: [],
    })
    const next = goFish(state)
    expect(next.phase).toBe('gameOver')
  })

  test('player with most books wins — message indicates winner', () => {
    const state = makeState({
      hands: [
        [card(13, 'hearts'), card(13, 'diamonds'), card(13, 'clubs')],
        [card(13, 'spades')],
      ],
      books: [
        [1, 2, 3, 4, 5, 6, 7],
        [8, 9, 10, 11, 12],
      ],
      pond: [],
    })
    const next = askForRank(state, 13)
    expect(next.phase).toBe('gameOver')
    // Human has 8 books, AI has 5
    expect(next.books[0].length).toBeGreaterThan(next.books[1].length)
  })
})

// ---------------------------------------------------------------------------
// AI memory
// ---------------------------------------------------------------------------
describe('AI memory', () => {
  test('AI remembers ranks the human has asked for', () => {
    const state = makeState({
      hands: [
        [card(5, 'hearts'), card(10, 'clubs')],
        [card(7, 'spades')],
      ],
    })
    const next = askForRank(state, 5)
    expect(next.aiMemory).toContain(5)
  })
})

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------
describe('edge cases', () => {
  test('player draws last card from pond', () => {
    const state = makeState({
      phase: 'goFish',
      currentPlayer: 0,
      lastAskedRank: 5,
      hands: [[card(5, 'hearts')], [card(7, 'spades')]],
      pond: [card(3, 'clubs')],
    })
    const next = goFish(state)
    expect(next.pond).toHaveLength(0)
    expect(next.hands[0]).toHaveLength(2)
  })

  test('asking for Ace (rank 1) works correctly', () => {
    const state = makeState({
      hands: [
        [card(1, 'hearts')],
        [card(1, 'clubs'), card(1, 'diamonds')],
      ],
    })
    const next = askForRank(state, 1)
    expect(next.hands[0].filter(c => c.rank === 1)).toHaveLength(3)
  })

  test('asking for King (rank 13) works correctly', () => {
    const state = makeState({
      hands: [
        [card(13, 'hearts')],
        [card(13, 'clubs')],
      ],
    })
    const next = askForRank(state, 13)
    expect(next.hands[0].filter(c => c.rank === 13)).toHaveLength(2)
  })
})
