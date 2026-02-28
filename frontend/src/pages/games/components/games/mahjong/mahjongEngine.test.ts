/**
 * Tests for Mahjong Solitaire engine.
 */

import { describe, test, expect } from 'vitest'
import {
  canMatch,
  isTileFree,
  findAllMatches,
  createGame,
  removePair,
  type GameTile,
} from './mahjongEngine'
import { PYRAMID_LAYOUT } from './layouts'

describe('canMatch', () => {
  test('tiles with same matchGroup can match', () => {
    const t1: GameTile = { id: 0, tileDefId: 'bamboo-1', matchGroup: 'bamboo-1', row: 0, col: 0, layer: 0, removed: false }
    const t2: GameTile = { id: 1, tileDefId: 'bamboo-1', matchGroup: 'bamboo-1', row: 1, col: 1, layer: 0, removed: false }
    expect(canMatch(t1, t2)).toBe(true)
  })

  test('tiles with different matchGroup cannot match', () => {
    const t1: GameTile = { id: 0, tileDefId: 'bamboo-1', matchGroup: 'bamboo-1', row: 0, col: 0, layer: 0, removed: false }
    const t2: GameTile = { id: 1, tileDefId: 'bamboo-2', matchGroup: 'bamboo-2', row: 1, col: 1, layer: 0, removed: false }
    expect(canMatch(t1, t2)).toBe(false)
  })

  test('same tile cannot match itself', () => {
    const t1: GameTile = { id: 0, tileDefId: 'bamboo-1', matchGroup: 'bamboo-1', row: 0, col: 0, layer: 0, removed: false }
    expect(canMatch(t1, t1)).toBe(false)
  })

  test('removed tile cannot match', () => {
    const t1: GameTile = { id: 0, tileDefId: 'bamboo-1', matchGroup: 'bamboo-1', row: 0, col: 0, layer: 0, removed: true }
    const t2: GameTile = { id: 1, tileDefId: 'bamboo-1', matchGroup: 'bamboo-1', row: 1, col: 1, layer: 0, removed: false }
    expect(canMatch(t1, t2)).toBe(false)
  })
})

describe('isTileFree', () => {
  test('tile with nothing on top or to sides is free', () => {
    const tiles: GameTile[] = [
      { id: 0, tileDefId: 'a', matchGroup: 'a', row: 0, col: 0, layer: 0, removed: false },
    ]
    expect(isTileFree(tiles[0], tiles)).toBe(true)
  })

  test('tile blocked by tile on top is not free', () => {
    const tiles: GameTile[] = [
      { id: 0, tileDefId: 'a', matchGroup: 'a', row: 0, col: 0, layer: 0, removed: false },
      { id: 1, tileDefId: 'b', matchGroup: 'b', row: 0, col: 0, layer: 1, removed: false },
    ]
    expect(isTileFree(tiles[0], tiles)).toBe(false)
  })

  test('tile blocked on both sides is not free', () => {
    const tiles: GameTile[] = [
      { id: 0, tileDefId: 'a', matchGroup: 'a', row: 0, col: 1, layer: 0, removed: false },
      { id: 1, tileDefId: 'b', matchGroup: 'b', row: 0, col: 0, layer: 0, removed: false }, // left
      { id: 2, tileDefId: 'c', matchGroup: 'c', row: 0, col: 2, layer: 0, removed: false }, // right
    ]
    expect(isTileFree(tiles[0], tiles)).toBe(false)
  })

  test('tile with one side open is free', () => {
    const tiles: GameTile[] = [
      { id: 0, tileDefId: 'a', matchGroup: 'a', row: 0, col: 1, layer: 0, removed: false },
      { id: 1, tileDefId: 'b', matchGroup: 'b', row: 0, col: 0, layer: 0, removed: false }, // left only
    ]
    expect(isTileFree(tiles[0], tiles)).toBe(true)
  })

  test('removed tiles do not block', () => {
    const tiles: GameTile[] = [
      { id: 0, tileDefId: 'a', matchGroup: 'a', row: 0, col: 0, layer: 0, removed: false },
      { id: 1, tileDefId: 'b', matchGroup: 'b', row: 0, col: 0, layer: 1, removed: true }, // removed
    ]
    expect(isTileFree(tiles[0], tiles)).toBe(true)
  })
})

describe('findAllMatches', () => {
  test('finds matching pairs among free tiles', () => {
    const tiles: GameTile[] = [
      { id: 0, tileDefId: 'a', matchGroup: 'a', row: 0, col: 0, layer: 0, removed: false },
      { id: 1, tileDefId: 'a', matchGroup: 'a', row: 0, col: 5, layer: 0, removed: false },
    ]
    const matches = findAllMatches(tiles)
    expect(matches).toHaveLength(1)
    expect(matches[0]).toEqual([0, 1])
  })

  test('returns empty when no matches', () => {
    const tiles: GameTile[] = [
      { id: 0, tileDefId: 'a', matchGroup: 'a', row: 0, col: 0, layer: 0, removed: false },
      { id: 1, tileDefId: 'b', matchGroup: 'b', row: 0, col: 5, layer: 0, removed: false },
    ]
    expect(findAllMatches(tiles)).toHaveLength(0)
  })
})

describe('createGame', () => {
  test('creates game with correct number of tiles', () => {
    const game = createGame(PYRAMID_LAYOUT)
    expect(game.tiles).toHaveLength(PYRAMID_LAYOUT.length)
  })

  test('all tiles start as not removed', () => {
    const game = createGame(PYRAMID_LAYOUT)
    game.tiles.forEach(t => expect(t.removed).toBe(false))
  })

  test('tile count is even', () => {
    const game = createGame(PYRAMID_LAYOUT)
    expect(game.tiles.length % 2).toBe(0)
  })
})

describe('removePair', () => {
  test('marks both tiles as removed', () => {
    const game = createGame(PYRAMID_LAYOUT)
    const id0 = game.tiles[0].id
    const matchGroup = game.tiles[0].matchGroup
    const partner = game.tiles.find(t => t.id !== id0 && t.matchGroup === matchGroup)
    if (partner) {
      const updated = removePair(game.tiles, id0, partner.id)
      expect(updated.find(t => t.id === id0)!.removed).toBe(true)
      expect(updated.find(t => t.id === partner.id)!.removed).toBe(true)
    }
  })
})
