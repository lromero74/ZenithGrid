import { describe, test, expect } from 'vitest'
import {
  createSpadesGame, placeBid, BLIND_NIL_BONUS,
} from './spadesEngine'

describe('blind nil', () => {
  test('placeBid with blindNil=true sets bid type to blind', () => {
    const state = createSpadesGame()
    const next = placeBid(state, 0, true)
    expect(next.bids[0]).toBe(0)
    expect(next.bidTypes[0]).toBe('blind')
  })

  test('placeBid with blindNil=false (regular nil) sets bid type to regular', () => {
    const state = createSpadesGame()
    const next = placeBid(state, 0, false)
    expect(next.bids[0]).toBe(0)
    expect(next.bidTypes[0]).toBe('regular')
  })

  test('non-nil bid always sets type to regular', () => {
    const state = createSpadesGame()
    const next = placeBid(state, 3, true) // blindNil flag ignored for non-nil bids
    expect(next.bids[0]).toBe(3)
    expect(next.bidTypes[0]).toBe('regular')
  })

  test('BLIND_NIL_BONUS is 200', () => {
    expect(BLIND_NIL_BONUS).toBe(200)
  })

  test('createSpadesGame initializes bidTypes to all regular', () => {
    const state = createSpadesGame()
    expect(state.bidTypes).toEqual(['regular', 'regular', 'regular', 'regular'])
  })

  test('bid message indicates blind nil', () => {
    const state = createSpadesGame()
    const next = placeBid(state, 0, true)
    expect(next.message).toContain('Blind Nil')
  })
})
