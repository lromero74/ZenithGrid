import { describe, it, expect } from 'vitest'
import {
  isPlayable,
  createSpeedGame,
  playCard,
  aiPlayCard,
  flipCenterCards,
  flipStartingCards,
  checkStalled,
  getPlayableMoves,
  getAiMove,
  getPlayerMoves,
  generateAiPlayDelay,
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
    replacementPiles: [[makeCard(1), makeCard(3)], [makeCard(9), makeCard(4)]],
    phase: 'playing' as Phase,
    message: '',
    difficulty: 'normal' as const,
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

  it('should deal 15 cards to each draw pile', () => {
    const state = createSpeedGame()
    expect(state.playerDrawPile).toHaveLength(15)
    expect(state.aiDrawPile).toHaveLength(15)
  })

  it('should have 1 card in each center pile', () => {
    const state = createSpeedGame()
    expect(state.centerPiles[0]).toHaveLength(1)
    expect(state.centerPiles[1]).toHaveLength(1)
  })

  it('should have 5 cards in each replacement pile', () => {
    const state = createSpeedGame()
    expect(state.replacementPiles[0]).toHaveLength(5)
    expect(state.replacementPiles[1]).toHaveLength(5)
  })

  it('should total 52 cards', () => {
    const state = createSpeedGame()
    const total = state.playerHand.length + state.playerDrawPile.length +
      state.aiHand.length + state.aiDrawPile.length +
      state.centerPiles[0].length + state.centerPiles[1].length +
      state.replacementPiles[0].length + state.replacementPiles[1].length
    expect(total).toBe(52)
  })

  it('should set phase to ready', () => {
    expect(createSpeedGame().phase).toBe('ready')
  })

  it('should have all cards face down before flip', () => {
    const state = createSpeedGame()
    expect(state.playerHand.every(c => !c.faceUp)).toBe(true)
    expect(state.aiHand.every(c => !c.faceUp)).toBe(true)
    expect(state.centerPiles[0].every(c => !c.faceUp)).toBe(true)
    expect(state.centerPiles[1].every(c => !c.faceUp)).toBe(true)
  })

  it('should default to normal difficulty', () => {
    expect(createSpeedGame().difficulty).toBe('normal')
  })

  it('should accept difficulty parameter', () => {
    expect(createSpeedGame('easy').difficulty).toBe('easy')
    expect(createSpeedGame('adept').difficulty).toBe('adept')
  })
})

// ── generateAiPlayDelay ─────────────────────────────────────────────

describe('generateAiPlayDelay', () => {
  it('should generate delays within human range', () => {
    for (let i = 0; i < 50; i++) {
      const delay = generateAiPlayDelay('normal')
      // Min: 80+60+40+60 = 240ms, Max: 250+200+150+180 = 780ms
      expect(delay).toBeGreaterThanOrEqual(180)
      expect(delay).toBeLessThanOrEqual(900)
    }
  })

  it('adept should tend to be faster than easy', () => {
    let adeptTotal = 0
    let easyTotal = 0
    const n = 100
    for (let i = 0; i < n; i++) {
      adeptTotal += generateAiPlayDelay('adept')
      easyTotal += generateAiPlayDelay('easy')
    }
    expect(adeptTotal / n).toBeLessThan(easyTotal / n)
  })
})

// ── flipStartingCards ───────────────────────────────────────────────

describe('flipStartingCards', () => {
  it('should transition from ready to playing', () => {
    const state = createSpeedGame()
    expect(state.phase).toBe('ready')
    const next = flipStartingCards(state)
    expect(next.phase).toBe('playing')
  })

  it('should reveal player hand, AI hand, and center cards', () => {
    const state = createSpeedGame()
    const next = flipStartingCards(state)
    expect(next.playerHand.every(c => c.faceUp)).toBe(true)
    expect(next.aiHand.every(c => c.faceUp)).toBe(true)
    expect(next.centerPiles[0].every(c => c.faceUp)).toBe(true)
    expect(next.centerPiles[1].every(c => c.faceUp)).toBe(true)
  })

  it('should not change state if phase is not ready', () => {
    const state = makeState({ phase: 'playing' })
    const next = flipStartingCards(state)
    expect(next).toBe(state)
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

  it('should detect stall when no moves remain and replacement piles exist', () => {
    const state = makeState({
      playerHand: [makeCard(8)],
      playerDrawPile: [makeCard(1)],
      aiHand: [makeCard(1)],
      aiDrawPile: [makeCard(1)],
      centerPiles: [[makeCard(7)], [makeCard(5, 'diamonds')]],
      replacementPiles: [[makeCard(10)], [makeCard(11)]],
    })
    const next = playCard(state, 0, 0)
    expect(next.phase).toBe('stalled')
  })

  it('should end game when stalled with empty replacement piles', () => {
    const state = makeState({
      playerHand: [makeCard(8)],
      playerDrawPile: [makeCard(1)],
      aiHand: [makeCard(1), makeCard(1, 'spades')],
      aiDrawPile: [makeCard(1, 'diamonds')],
      centerPiles: [[makeCard(7)], [makeCard(5, 'diamonds')]],
      replacementPiles: [[], []],
    })
    const next = playCard(state, 0, 0)
    // Stalled with no replacement piles → game over, player has fewer cards
    expect(next.phase).toBe('gameOver')
    expect(next.message).toContain('You win')
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
  it('should flip cards from replacement piles onto center', () => {
    const state = makeState({ phase: 'stalled' })
    const next = flipCenterCards(state)
    expect(next.centerPiles[0].length).toBe(state.centerPiles[0].length + 1)
    expect(next.centerPiles[1].length).toBe(state.centerPiles[1].length + 1)
    expect(next.replacementPiles[0].length).toBe(state.replacementPiles[0].length - 1)
    expect(next.replacementPiles[1].length).toBe(state.replacementPiles[1].length - 1)
    expect(next.phase).toBe('playing')
  })

  it('should not flip if phase is not stalled', () => {
    const state = makeState({ phase: 'playing' })
    const next = flipCenterCards(state)
    expect(next).toBe(state)
  })

  it('should handle empty replacement piles gracefully', () => {
    const state = makeState({
      phase: 'stalled',
      replacementPiles: [[], []],
      playerHand: [makeCard(5)],
      aiHand: [makeCard(5, 'spades')],
      centerPiles: [[makeCard(10)], [makeCard(10, 'diamonds')]],
    })
    const next = flipCenterCards(state)
    // No cards to flip, still stalled, replacement piles empty → game over
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
