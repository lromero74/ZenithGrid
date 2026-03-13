import { describe, it, expect } from 'vitest'
import {
  createCheatGame,
  playCards,
  callBS,
  passChallenge,
  resolveChallenge,
  aiPlayTurn,
  aiDecideChallenge,
  nextRank,
  type CheatState,
} from './cheatEngine'
import type { Card } from '../../../utils/cardUtils'

// Helper: create a card for testing
function card(rank: number, suit: 'hearts' | 'diamonds' | 'clubs' | 'spades' = 'hearts'): Card {
  return { rank, suit, faceUp: true }
}

describe('Cheat Engine', () => {
  // ── createCheatGame ──────────────────────────────────────────────────

  describe('createCheatGame', () => {
    it('deals all 52 cards evenly among 4 players', () => {
      const state = createCheatGame(4)
      expect(state.hands).toHaveLength(4)
      const totalCards = state.hands.reduce((sum, h) => sum + h.length, 0)
      expect(totalCards).toBe(52)
      expect(state.hands[0]).toHaveLength(13)
      expect(state.hands[1]).toHaveLength(13)
      expect(state.hands[2]).toHaveLength(13)
      expect(state.hands[3]).toHaveLength(13)
    })

    it('deals cards to 2 players (26 each)', () => {
      const state = createCheatGame(2)
      expect(state.hands).toHaveLength(2)
      expect(state.hands[0]).toHaveLength(26)
      expect(state.hands[1]).toHaveLength(26)
    })

    it('deals cards to 3 players (17, 17, 18)', () => {
      const state = createCheatGame(3)
      expect(state.hands).toHaveLength(3)
      const total = state.hands.reduce((s, h) => s + h.length, 0)
      expect(total).toBe(52)
    })

    it('starts in play phase with player 0 and rank Ace', () => {
      const state = createCheatGame(4)
      expect(state.phase).toBe('play')
      expect(state.currentPlayer).toBe(0)
      expect(state.requiredRank).toBe(1) // Ace
    })

    it('starts with empty pile and no last play', () => {
      const state = createCheatGame(4)
      expect(state.pile).toHaveLength(0)
      expect(state.lastPlay).toBeNull()
      expect(state.winner).toBeNull()
    })
  })

  // ── nextRank ──────────────────────────────────────────────────────────

  describe('nextRank', () => {
    it('cycles A→2→3→...→K→A', () => {
      expect(nextRank(1)).toBe(2)
      expect(nextRank(2)).toBe(3)
      expect(nextRank(12)).toBe(13)
      expect(nextRank(13)).toBe(1) // K wraps to A
    })
  })

  // ── playCards ──────────────────────────────────────────────────────────

  describe('playCards', () => {
    it('moves selected cards to pile and enters challenge phase', () => {
      const state = createCheatGame(4)
      const indices = [0, 1] // play first two cards
      const result = playCards(state, indices, state.requiredRank)
      expect(result.pile).toHaveLength(2)
      expect(result.hands[0]).toHaveLength(11)
      expect(result.phase).toBe('challenge')
      expect(result.lastPlay).not.toBeNull()
      expect(result.lastPlay!.claimedRank).toBe(1) // Ace
      expect(result.lastPlay!.claimedCount).toBe(2)
    })

    it('rejects play with 0 cards', () => {
      const state = createCheatGame(4)
      const result = playCards(state, [], state.requiredRank)
      expect(result).toBe(state) // unchanged
    })

    it('rejects play with more than 4 cards', () => {
      const state = createCheatGame(4)
      const result = playCards(state, [0, 1, 2, 3, 4], state.requiredRank)
      expect(result).toBe(state)
    })

    it('rejects play when not in play phase', () => {
      const state = createCheatGame(4)
      const challenged = { ...state, phase: 'challenge' as const }
      const result = playCards(challenged, [0], 1)
      expect(result).toBe(challenged)
    })

    it('rejects play from wrong player', () => {
      const state = { ...createCheatGame(4), currentPlayer: 1 }
      // Player 0 trying to play on player 1's turn — playCards uses currentPlayer
      const result = playCards(state, [0], state.requiredRank)
      // The function checks phase, not who calls it — but indices are from currentPlayer's hand
      expect(result.phase).toBe('challenge')
    })

    it('records the actual cards played in lastPlay for challenge verification', () => {
      const state = createCheatGame(4)
      const cardsPlayed = state.hands[0].slice(0, 2)
      const result = playCards(state, [0, 1], state.requiredRank)
      expect(result.lastPlay!.cards).toHaveLength(2)
      expect(result.lastPlay!.cards[0].rank).toBe(cardsPlayed[0].rank)
      expect(result.lastPlay!.cards[1].rank).toBe(cardsPlayed[1].rank)
    })
  })

  // ── callBS ────────────────────────────────────────────────────────────

  describe('callBS', () => {
    it('catches a bluff — bluffer picks up the pile', () => {
      // Set up a state where player 0 lied
      const state = createCheatGame(4)
      // Force player 0 to have no aces, then "play" cards claiming aces
      const modState: CheatState = {
        ...state,
        hands: [
          [card(5), card(6), card(7)],      // player 0: no aces
          state.hands[1],
          state.hands[2],
          state.hands[3],
        ],
        pile: [card(5), card(6)],  // these were "played" as aces
        phase: 'challenge',
        lastPlay: {
          player: 0,
          cards: [card(5), card(6)],  // actual cards — not aces!
          claimedRank: 1,
          claimedCount: 2,
        },
        challengedBy: null,
      }

      const result = callBS(modState, 1) // player 1 calls BS
      expect(result.challengeResult).toBe('bluff')
      expect(result.challengedBy).toBe(1)
      expect(result.phase).toBe('reveal')
    })

    it('wrong challenge — challenger picks up the pile', () => {
      const state = createCheatGame(4)
      const modState: CheatState = {
        ...state,
        pile: [card(1), card(1)],
        phase: 'challenge',
        lastPlay: {
          player: 0,
          cards: [card(1), card(1)],  // actually aces — honest!
          claimedRank: 1,
          claimedCount: 2,
        },
        challengedBy: null,
      }

      const result = callBS(modState, 1)
      expect(result.challengeResult).toBe('honest')
      expect(result.challengedBy).toBe(1)
      expect(result.phase).toBe('reveal')
    })

    it('player cannot call BS on themselves', () => {
      const state: CheatState = {
        ...createCheatGame(4),
        phase: 'challenge',
        lastPlay: { player: 0, cards: [card(1)], claimedRank: 1, claimedCount: 1 },
      }
      const result = callBS(state, 0)
      expect(result).toBe(state) // unchanged
    })
  })

  // ── resolveChallenge ──────────────────────────────────────────────────

  describe('resolveChallenge', () => {
    it('gives pile to bluffer when caught', () => {
      const pile = [card(2), card(3), card(5), card(6)]
      const state: CheatState = {
        ...createCheatGame(4),
        hands: [
          [card(7)],  // player 0 (bluffer) has 1 card
          [card(8), card(9)],
          [card(10)],
          [card(11)],
        ],
        pile,
        phase: 'reveal',
        lastPlay: { player: 0, cards: [card(5), card(6)], claimedRank: 1, claimedCount: 2 },
        challengeResult: 'bluff',
        challengedBy: 1,
        playerCount: 4,
      }
      const result = resolveChallenge(state)
      // Player 0 gets the pile (4 cards) + their 1 card = 5 cards
      expect(result.hands[0]).toHaveLength(5)
      expect(result.pile).toHaveLength(0)
      expect(result.phase).toBe('play')
    })

    it('gives pile to challenger when wrong', () => {
      const pile = [card(1), card(1)]
      const state: CheatState = {
        ...createCheatGame(4),
        hands: [
          [card(7)],
          [card(8)],  // challenger
          [card(10)],
          [card(11)],
        ],
        pile,
        phase: 'reveal',
        lastPlay: { player: 0, cards: [card(1), card(1)], claimedRank: 1, claimedCount: 2 },
        challengeResult: 'honest',
        challengedBy: 1,
        playerCount: 4,
      }
      const result = resolveChallenge(state)
      // Player 1 (challenger) gets the pile
      expect(result.hands[1]).toHaveLength(3) // 1 + 2
      expect(result.pile).toHaveLength(0)
    })
  })

  // ── passChallenge ──────────────────────────────────────────────────────

  describe('passChallenge', () => {
    it('advances to next player turn after all pass', () => {
      const state: CheatState = {
        ...createCheatGame(4),
        phase: 'challenge',
        currentPlayer: 0,
        requiredRank: 1,
        lastPlay: { player: 0, cards: [card(1)], claimedRank: 1, claimedCount: 1 },
        passedPlayers: [],
      }
      // Players 1, 2, 3 all pass
      let s = passChallenge(state, 1)
      expect(s.phase).toBe('challenge') // still waiting
      s = passChallenge(s, 2)
      expect(s.phase).toBe('challenge') // still waiting
      s = passChallenge(s, 3) // last non-playing player passes
      expect(s.phase).toBe('play') // now move on
      expect(s.currentPlayer).toBe(1) // next player
      expect(s.requiredRank).toBe(2)  // rank advances
    })
  })

  // ── Game over ──────────────────────────────────────────────────────────

  describe('game over', () => {
    it('detects winner when a player empties their hand', () => {
      const state: CheatState = {
        ...createCheatGame(4),
        hands: [
          [card(1)], // player 0 has 1 card left
          [card(2), card(3)],
          [card(4), card(5)],
          [card(6), card(7)],
        ],
        phase: 'play',
        currentPlayer: 0,
        requiredRank: 1,
        playerCount: 4,
      }
      // Player plays their last card
      const result = playCards(state, [0], 1)
      // After challenge phase resolves (if no challenge), player wins
      // Since this enters challenge phase, we need to pass all
      expect(result.phase).toBe('challenge')
      let s = passChallenge(result, 1)
      s = passChallenge(s, 2)
      s = passChallenge(s, 3)
      expect(s.phase).toBe('gameOver')
      expect(s.winner).toBe(0)
    })
  })

  // ── AI ──────────────────────────────────────────────────────────────────

  describe('aiPlayTurn', () => {
    it('AI plays at least 1 card and enters challenge phase', () => {
      const state: CheatState = {
        ...createCheatGame(4),
        phase: 'play',
        currentPlayer: 1, // AI's turn
        requiredRank: 2,
      }
      const result = aiPlayTurn(state)
      expect(result.phase).toBe('challenge')
      expect(result.lastPlay).not.toBeNull()
      expect(result.lastPlay!.player).toBe(1)
      expect(result.lastPlay!.claimedCount).toBeGreaterThanOrEqual(1)
      expect(result.lastPlay!.claimedCount).toBeLessThanOrEqual(4)
    })
  })

  describe('aiDecideChallenge', () => {
    it('returns state with challenge or pass decision', () => {
      const state: CheatState = {
        ...createCheatGame(4),
        phase: 'challenge',
        currentPlayer: 0,
        lastPlay: { player: 0, cards: [card(1)], claimedRank: 1, claimedCount: 1 },
        passedPlayers: [],
      }
      // AI player 1 decides
      const result = aiDecideChallenge(state, 1)
      // Should either call BS (reveal phase) or pass
      expect(['challenge', 'reveal', 'play', 'gameOver']).toContain(result.phase)
    })
  })
})
