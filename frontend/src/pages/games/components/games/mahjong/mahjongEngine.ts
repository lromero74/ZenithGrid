/**
 * Mahjong Solitaire engine — pure logic, no React.
 *
 * Handles tile placement, free-tile detection, matching,
 * and game state management.
 */

import type { TilePosition } from './layouts'
import { UNIQUE_TILES } from './tileSet'

export interface GameTile {
  id: number
  tileDefId: string
  matchGroup: string
  row: number
  col: number
  layer: number
  removed: boolean
}

export interface GameState {
  tiles: GameTile[]
  shufflesRemaining: number
}

/** Check if two tiles can be matched (same matchGroup, both alive, different tiles). */
export function canMatch(t1: GameTile, t2: GameTile): boolean {
  if (t1.id === t2.id) return false
  if (t1.removed || t2.removed) return false
  return t1.matchGroup === t2.matchGroup
}

/**
 * Check if a tile is free (can be selected).
 *
 * A tile is free if:
 * 1. No tile on top of it (overlapping on a higher layer)
 * 2. At least one side (left or right) is open
 */
export function isTileFree(tile: GameTile, allTiles: GameTile[]): boolean {
  if (tile.removed) return false

  const alive = allTiles.filter(t => !t.removed && t.id !== tile.id)

  // Check if blocked from above (any tile on a higher layer that overlaps)
  const blockedFromAbove = alive.some(t =>
    t.layer > tile.layer &&
    Math.abs(t.row - tile.row) < 1 &&
    Math.abs(t.col - tile.col) < 1
  )
  if (blockedFromAbove) return false

  // Check side blocking (must have at least one side free)
  const blockedLeft = alive.some(t =>
    t.layer === tile.layer &&
    Math.abs(t.row - tile.row) < 1 &&
    t.col === tile.col - 1
  )
  const blockedRight = alive.some(t =>
    t.layer === tile.layer &&
    Math.abs(t.row - tile.row) < 1 &&
    t.col === tile.col + 1
  )

  return !blockedLeft || !blockedRight
}

/** Find all matchable pairs among free tiles. Returns pairs of tile IDs. */
export function findAllMatches(tiles: GameTile[]): [number, number][] {
  const freeTiles = tiles.filter(t => !t.removed && isTileFree(t, tiles))
  const matches: [number, number][] = []

  for (let i = 0; i < freeTiles.length; i++) {
    for (let j = i + 1; j < freeTiles.length; j++) {
      if (canMatch(freeTiles[i], freeTiles[j])) {
        matches.push([freeTiles[i].id, freeTiles[j].id])
      }
    }
  }

  return matches
}

/** Create a new game by assigning tiles to layout positions. */
export function createGame(layout: TilePosition[]): GameState {
  const count = layout.length
  // Ensure even count
  const pairCount = Math.floor(count / 2)

  // Create tile pool: pick pairCount unique tiles, each appearing twice
  const pool: { tileDefId: string; matchGroup: string }[] = []
  for (let i = 0; i < pairCount; i++) {
    const tileDef = UNIQUE_TILES[i % UNIQUE_TILES.length]
    pool.push({ tileDefId: tileDef.id, matchGroup: tileDef.matchGroup })
    pool.push({ tileDefId: tileDef.id, matchGroup: tileDef.matchGroup })
  }

  // Shuffle pool
  shuffle(pool)

  // Assign to positions
  const tiles: GameTile[] = layout.slice(0, pairCount * 2).map((pos, i) => ({
    id: i,
    tileDefId: pool[i].tileDefId,
    matchGroup: pool[i].matchGroup,
    row: pos.row,
    col: pos.col,
    layer: pos.layer,
    removed: false,
  }))

  return { tiles, shufflesRemaining: 3 }
}

/** Remove a pair of matched tiles. */
export function removePair(tiles: GameTile[], id1: number, id2: number): GameTile[] {
  return tiles.map(t => {
    if (t.id === id1 || t.id === id2) {
      return { ...t, removed: true }
    }
    return t
  })
}

/** Shuffle remaining tiles in-place (re-assign tile defs to positions). */
export function shuffleTiles(tiles: GameTile[]): GameTile[] {
  const remaining = tiles.filter(t => !t.removed)
  const defs = remaining.map(t => ({ tileDefId: t.tileDefId, matchGroup: t.matchGroup }))
  shuffle(defs)

  const newTiles = tiles.map(t => {
    if (t.removed) return t
    const idx = remaining.findIndex(r => r.id === t.id)
    return { ...t, tileDefId: defs[idx].tileDefId, matchGroup: defs[idx].matchGroup }
  })

  return newTiles
}

/** Check if the game is over (no remaining matches among free tiles). */
export function isGameOver(tiles: GameTile[]): boolean {
  const remaining = tiles.filter(t => !t.removed)
  if (remaining.length === 0) return true // won
  return findAllMatches(tiles).length === 0
}

/** Check if all tiles have been removed (win). */
export function isGameWon(tiles: GameTile[]): boolean {
  return tiles.every(t => t.removed)
}

function shuffle<T>(arr: T[]): T[] {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}
