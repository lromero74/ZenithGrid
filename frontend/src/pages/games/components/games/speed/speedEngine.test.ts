import { describe, it, expect } from 'vitest'
import {
  isPlayable,
  createSpeedGame,
  playCard,
  aiPlayCard,
  flipCenterCards,
  checkStalled,
  getPlayableMoves,
  getAiMove,
  getPlayerMoves,
  type SpeedState,
  type Phase,
} from './speedEngine'
import type { Card } from '../../../utils/cardUtils'

// ── Helpers ─────────────────────────────────────────────────────────

function makeCard(rank: number, suit: Card['suit'] = 'hearts', faceUp = true): Card {
  return { rank, suit, faceUp }
}

function makeState(overrides: Partial<SpeedState> = {}): SpeedState {
  return {
    playerHand: [makeCard(5), makeCard(8), makeCard(11)],
    playerDrawPile: [makeCard(2), makeCard(9)],
    aiHand: [makeCard(6), makeCard(10), makeCard(3)],
    aiDrawPile: [makeCard(4), makeCard(7)],
    centerPiles: [[makeCard(7)], [makeCard(12)]],
    phase: 'playing' as Phase,
    message: '',
    ...overrides,
  }
}

// ── isPlayable ──────────────────────────────────────────────────────

describe('isPlayable', () => {
  it('should allow rank +1', () => {
    expect(isPlayable(makeCard(8), makeCard(7))).toBe(true)
  })

  it('should allow rank -1', () => {
    expect(isPlayable(makeCard(6), makeCard(7))).toBe(true)
  })

  it('should reject same rank', () => {
    expect(isPlayable(makeCard(7), makeCard(7))).toBe(false)
  })

  it('should reject rank difference > 1', () => {
    expect(isPlayable(makeCard(3), makeCard(7))).toBe(false)
  })

  it('should wrap Ace to King (Ace on King)', () => {
    expect(isPlayable(makeCard(1), makeCard(13))).toBe(true)
  })

  it('should wrap King to Ace (King on Ace)', () => {
    expect(isPlayable(makeCard(13), makeCard(1))).toBe(true)
  })

  it('should allow Ace on 2', () => {
    expect(isPlayable(makeCard(1), makeCard(2))).toBe(true)
  })

  it('should allow 2 on Ace', () => {
    expect(isPlayable(makeCard(2), makeCard(1))).toBe(true)
  })
})

// ── createSpeedGame ─────────────────────────────────────────────────

describe('createSpeedGame', () => {
  it('should deal 5 cards to each hand', () => {
    const state = createSpeedGame()
    expect(state.playerHand).toHaveLength(5)
    expect(state.aiHand).toHaveLength(5)
  })

  it('should deal 20 cards to each draw pile', () => {
    const state = createSpeedGame()
    expect(state.playerDrawPile).toHaveLength(20)
    expect(state.aiDrawPile).toHaveLength(20)
  })

  it('should have 1 card in each center pile', () => {
    const state = createSpeedGame()
    expect(state.centerPiles[0]).toHaveLength(1)
    expect(state.centerPiles[1]).toHaveLength(1)
  })

  it('should total 52 cards', () => {
    const state = createSpeedGame()
    const total = state.playerHand.length + state.playerDrawPile.length +
      state.aiHand.length + state.aiDrawPile.length +
      state.centerPiles[0].length + state.centerPiles[1].length
    expect(total).toBe(52)
  })

  it('should set phase to playing', () => {
    expect(createSpeedGame().phase).toBe('playing')
  })

  it('should have all hand cards face up', () => {
    const state = createSpeedGame()
    expect(state.playerHand.every(c => c.faceUp)).toBe(true)
    expect(state.aiHand.every(c => c.faceUp)).toBe(true)
  })
})

// ── getPlayableMoves ────────────────────────────────────────────────

describe('getPlayableMoves', () => {
  it('should find moves for adjacent ranks', () => {
    const hand = [makeCard(8), makeCard(3)]
    const piles: [Card[], Card[]] = [[makeCard(7)], [makeCard(12)]]
    const moves = getPlayableMoves(hand, piles)
    // Card 8 can play on pile 0 (top=7), card 3 cannot play anywhere
    expect(moves).toEqual([{ handIndex: 0, pileIndex: 0 }])
  })

  it('should return multiple moves when card fits both piles', () => {
    const hand = [makeCard(8)]
    const piles: [Card[], Card[]] = [[makeCard(7)], [makeCard(9)]]
    const moves = getPlayableMoves(hand, piles)
    expect(moves).toHaveLength(2)
  })

  it('should return empty array when no moves available', () => {
    const hand = [makeCard(5)]
    const piles: [Card[], Card[]] = [[makeCard(10)], [makeCard(2)]]
    const moves = getPlayableMoves(hand, piles)
    expect(moves).toHaveLength(0)
  })
})

// ── playCard ────────────────────────────────────────────────────────

describe('playCard', () => {
  it('should play valid card onto center pile', () => {
    // playerHand[1] = 8, center pile 0 top = 7 → playable
    const state = makeState()
    const next = playCard(state, 1, 0)
    // Card should be on pile, hand should be refilled
    expect(next.centerPiles[0][next.centerPiles[0].length - 1].rank).toBe(8)
    expect(next.playerHand).toHaveLength(4) // was 3, removed 1, drew 2 (draw pile had 2)
  })

  it('should reject invalid move (wrong rank)', () => {
    // playerHand[0] = 5, center pile 0 top = 7 → not playable
    const state = makeState()
    const next = playCard(state, 0, 0)
    expect(next).toBe(state) // unchanged
  })

  it('should reject if phase is not playing', () => {
    const state = makeState({ phase: 'stalled' })
    const next = playCard(state, 1, 0)
    expect(next).toBe(state)
  })

  it('should refill hand from draw pile', () => {
    const state = makeState({
      playerHand: [makeCard(8)],
      playerDrawPile: [makeCard(2), makeCard(3), makeCard(4), makeCard(9)],
      centerPiles: [[makeCard(7)], [makeCard(12)]],
    })
    const next = playCard(state, 0, 0)
    // Played 1, should draw up to 4 from pile (min(4, pile size))
    expect(next.playerHand.length + next.playerDrawPile.length).toBe(4) // total preserved
  })

  it('should detect win when hand and draw pile are empty', () => {
    const state = makeState({
      playerHand: [makeCard(8)],
      playerDrawPile: [],
      centerPiles: [[makeCard(7)], [makeCard(12)]],
    })
    const next = playCard(state, 0, 0)
    expect(next.phase).toBe('gameOver')
    expect(next.message).toContain('You win')
  })

  it('should detect stall when no moves remain', () => {
    // After playing, create a state where no one can move
    const state = makeState({
      playerHand: [makeCard(8)],
      playerDrawPile: [makeCard(1)],
      aiHand: [makeCard(1)],
      aiDrawPile: [makeCard(1)],
      centerPiles: [[makeCard(7)], [makeCard(5, 'diamonds')]],
    })
    const next = playCard(state, 0, 0)
    // After playing 8 on 7, center piles are [8] and [5]
    // Player hand: [1], AI hand: [1] — 1 is not ±1 of 8 or 5
    // Wait: 1 (Ace) wraps. diff(1,8)=7, diff(1,5)=4. Neither is 1 or 12. So stalled.
    // Actually no: Ace wraps to King (diff 12). Let me reconsider.
    // isPlayable(1, 8): diff = |1-8| = 7, not 1 or 12. Not playable.
    // isPlayable(1, 5): diff = |1-5| = 4, not 1 or 12. Not playable.
    // Yes, stalled.
    expect(next.phase).toBe('stalled')
  })
})

// ── aiPlayCard ──────────────────────────────────────────────────────

describe('aiPlayCard', () => {
  it('should play valid AI card onto center pile', () => {
    // aiHand[0] = 6, center pile 0 top = 7 → playable
    const state = makeState()
    const next = aiPlayCard(state, 0, 0)
    expect(next.centerPiles[0][next.centerPiles[0].length - 1].rank).toBe(6)
  })

  it('should refill AI hand from draw pile', () => {
    const state = makeState()
    const before = state.aiHand.length + state.aiDrawPile.length
    const next = aiPlayCard(state, 0, 0)
    // Total AI cards should decrease by 1 (one played to center)
    const after = next.aiHand.length + next.aiDrawPile.length
    expect(after).toBe(before - 1)
  })

  it('should detect AI win', () => {
    const state = makeState({
      aiHand: [makeCard(6)],
      aiDrawPile: [],
      centerPiles: [[makeCard(7)], [makeCard(12)]],
    })
    const next = aiPlayCard(state, 0, 0)
    expect(next.phase).toBe('gameOver')
    expect(next.message).toContain('AI wins')
  })
})

// ── flipCenterCards ─────────────────────────────────────────────────

describe('flipCenterCards', () => {
  it('should flip cards from draw piles onto center', () => {
    const state = makeState({ phase: 'stalled' })
    const next = flipCenterCards(state)
    expect(next.centerPiles[0].length).toBe(state.centerPiles[0].length + 1)
    expect(next.centerPiles[1].length).toBe(state.centerPiles[1].length + 1)
    expect(next.phase).toBe('playing')
  })

  it('should not flip if phase is not stalled', () => {
    const state = makeState({ phase: 'playing' })
    const next = flipCenterCards(state)
    expect(next).toBe(state)
  })

  it('should handle empty draw piles gracefully', () => {
    const state = makeState({
      phase: 'stalled',
      playerDrawPile: [],
      aiDrawPile: [],
      playerHand: [makeCard(5)],
      aiHand: [makeCard(5, 'spades')],
      centerPiles: [[makeCard(10)], [makeCard(10, 'diamonds')]],
    })
    const next = flipCenterCards(state)
    // No cards to flip, still stalled, both draw piles empty → game over
    expect(next.phase).toBe('gameOver')
  })
})

// ── checkStalled ────────────────────────────────────────────────────

describe('checkStalled', () => {
  it('should return false when player has moves', () => {
    const state = makeState() // playerHand[1]=8 plays on centerPile[0] top=7
    expect(checkStalled(state)).toBe(false)
  })

  it('should return true when neither player has moves', () => {
    const state = makeState({
      playerHand: [makeCard(5)],
      aiHand: [makeCard(5, 'spades')],
      centerPiles: [[makeCard(10)], [makeCard(10, 'diamonds')]],
    })
    expect(checkStalled(state)).toBe(true)
  })

  it('should return false when only AI has moves', () => {
    const state = makeState({
      playerHand: [makeCard(5)],
      aiHand: [makeCard(11)],
      centerPiles: [[makeCard(10)], [makeCard(2)]],
    })
    // AI hand: 11 is ±1 of 10 → not stalled
    expect(checkStalled(state)).toBe(false)
  })
})

// ── getAiMove ───────────────────────────────────────────────────────

describe('getAiMove', () => {
  it('should return a valid move when one exists', () => {
    const state = makeState() // aiHand[0]=6 plays on centerPile[0] top=7
    const move = getAiMove(state)
    expect(move).not.toBeNull()
    expect(move!.pileIndex).toBeGreaterThanOrEqual(0)
    expect(move!.handIndex).toBeGreaterThanOrEqual(0)
  })

  it('should return null when no moves available', () => {
    const state = makeState({
      aiHand: [makeCard(5)],
      centerPiles: [[makeCard(10)], [makeCard(10, 'diamonds')]],
    })
    expect(getAiMove(state)).toBeNull()
  })

  it('should return null when phase is not playing', () => {
    const state = makeState({ phase: 'gameOver' })
    expect(getAiMove(state)).toBeNull()
  })
})

// ── getPlayerMoves ──────────────────────────────────────────────────

describe('getPlayerMoves', () => {
  it('should return moves during playing phase', () => {
    const state = makeState()
    const moves = getPlayerMoves(state)
    expect(moves.length).toBeGreaterThan(0)
  })

  it('should return empty array when not playing', () => {
    const state = makeState({ phase: 'stalled' })
    expect(getPlayerMoves(state)).toEqual([])
  })
})
