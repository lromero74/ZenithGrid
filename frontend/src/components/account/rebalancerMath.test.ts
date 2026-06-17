import { describe, it, expect } from 'vitest'
import { redistributeSlots, type RebalancerSlot } from './rebalancerMath'

function makeSlots(values: number[], overrides: Partial<RebalancerSlot>[] = []): RebalancerSlot[] {
  return values.map((target_pct, idx) => ({
    bot_id: idx + 1,
    enabled: true,
    target_pct,
    locked: false,
    bound: false,
    ...overrides[idx],
  }))
}

function pctById(slots: RebalancerSlot[]): Record<number, number> {
  return Object.fromEntries(slots.map((s) => [s.bot_id, s.target_pct]))
}

describe('redistributeSlots', () => {
  it('dragging one slider down leaves the other bots alone', () => {
    const slots = makeSlots([50, 30, 20])
    const result = redistributeSlots(slots, 100, 1, 25)

    expect(pctById(result)).toEqual({ 1: 25, 2: 30, 3: 20 })
  })

  it('dragging one slider up is allowed while total stays under max', () => {
    const slots = makeSlots([40, 30, 20])
    const result = redistributeSlots(slots, 100, 1, 50)

    expect(pctById(result)).toEqual({ 1: 50, 2: 30, 3: 20 })
  })

  it('dragging up beyond max steals from the bot with the most allocation first', () => {
    // Bot 1 is dragged from 30 to 90. Max is 100, locked total is 0.
    // The other bots total 70 (40 + 30). To get to 90, we need 60 more.
    // Bot 2 has 40 (most to give) → loses 40. Bot 3 has 30 → loses remaining 20.
    const slots = makeSlots([30, 40, 30])
    const result = redistributeSlots(slots, 100, 1, 90)

    expect(pctById(result)).toEqual({ 1: 90, 2: 0, 3: 10 })
  })

  it('locked bots are never adjusted by redistribution', () => {
    const slots = makeSlots([30, 40, 30], [
      {},
      { locked: true },
      {},
    ])
    const result = redistributeSlots(slots, 100, 1, 80)

    // Locked bot 2 stays at 40. Bot 1 can only reach 60 because 40 is reserved.
    // Bot 3 (unlocked, smallest among victims) gives up its 30 to make room.
    expect(pctById(result)).toEqual({ 1: 60, 2: 40, 3: 0 })
  })

  it('bound bots move together when one is dragged', () => {
    const slots = makeSlots([20, 20, 40, 20], [
      { bound: true },
      { bound: true },
      {},
      {},
    ])
    const result = redistributeSlots(slots, 100, 1, 30)

    // Bound group (bots 1+2) each gets 30, using 60 total.
    // Locked = 0. Remaining room = 40. Victims sorted by size: bot 3 (40), bot 4 (20).
    // Need dragged total 60, room 40, overage 20. Bot 3 gives 20, leaving 20.
    expect(pctById(result)).toEqual({ 1: 30, 2: 30, 3: 20, 4: 20 })
  })

  it('cannot exceed max_total_pct even when all other bots are drained', () => {
    const slots = makeSlots([30, 30, 30])
    const result = redistributeSlots(slots, 80, 1, 100)

    expect(pctById(result)).toEqual({ 1: 80, 2: 0, 3: 0 })
  })

  it('returns unchanged state when the dragged bot is disabled', () => {
    const slots = makeSlots([50, 50], [{ enabled: false }, {}])
    const result = redistributeSlots(slots, 100, 1, 25)

    expect(pctById(result)).toEqual({ 1: 50, 2: 50 })
  })

  it('handles 300% max_total_pct correctly', () => {
    const slots = makeSlots([120, 90, 60])
    const result = redistributeSlots(slots, 300, 1, 200)

    // Dragged bot 1 to 200. Total others = 150. New total = 350, overage = 50.
    // Bot 2 (90) gives 50, bot 3 untouched.
    expect(pctById(result)).toEqual({ 1: 200, 2: 40, 3: 60 })
  })
})
