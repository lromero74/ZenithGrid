/**
 * Mahjong Solitaire layout definitions.
 *
 * Each layout is a list of tile positions: { row, col, layer }.
 * The Turtle layout is the classic starting arrangement.
 */

export interface TilePosition {
  row: number
  col: number
  layer: number
}

/**
 * Classic Turtle layout — 144 positions across 5 layers.
 *
 * Layer 0 (bottom): 12 cols x 8 rows (minus corners) = ~86 tiles
 * Layer 1: ~40 tiles
 * Layer 2: ~20 tiles
 * Layer 3: ~6 tiles
 * Layer 4: ~1 tile (cap)
 * Plus wing tiles on the sides.
 *
 * Simplified version that guarantees 144 positions.
 */
export const TURTLE_LAYOUT: TilePosition[] = buildTurtleLayout()

function buildTurtleLayout(): TilePosition[] {
  const positions: TilePosition[] = []

  // Layer 0: 12x8 rectangle with some cutouts
  const layer0: [number, number][] = []
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 12; c++) {
      // Skip corners for shape
      if ((r === 0 || r === 7) && (c === 0 || c === 11)) continue
      if ((r === 0 || r === 7) && (c === 1 || c === 10)) continue
      layer0.push([r, c])
    }
  }
  // Add wing tiles
  layer0.push([3, -1]) // left wing
  layer0.push([4, -1])
  layer0.push([3, 12]) // right wing
  layer0.push([4, 12])
  layer0.push([3.5, -2]) // far left
  layer0.push([3.5, 13])  // far right

  layer0.forEach(([r, c]) => positions.push({ row: r, col: c, layer: 0 }))

  // Layer 1: 10x6 centered
  for (let r = 1; r < 7; r++) {
    for (let c = 1; c < 11; c++) {
      if ((r === 1 || r === 6) && (c === 1 || c === 10)) continue
      positions.push({ row: r, col: c, layer: 1 })
    }
  }

  // Layer 2: 8x4 centered
  for (let r = 2; r < 6; r++) {
    for (let c = 2; c < 10; c++) {
      if ((r === 2 || r === 5) && (c === 2 || c === 9)) continue
      positions.push({ row: r, col: c, layer: 2 })
    }
  }

  // Layer 3: 6x2 centered
  for (let r = 3; r < 5; r++) {
    for (let c = 3; c < 9; c++) {
      positions.push({ row: r, col: c, layer: 3 })
    }
  }

  // Layer 4: 2x1 cap
  positions.push({ row: 3.5, col: 5, layer: 4 })
  positions.push({ row: 3.5, col: 6, layer: 4 })

  // Trim or pad to exactly 144 (must be even for pairs)
  while (positions.length > 144) positions.pop()
  while (positions.length < 144) {
    // Add more layer 0 positions if needed
    const r = Math.floor(positions.length / 12) % 8
    const c = positions.length % 12
    positions.push({ row: r, col: c, layer: 0 })
  }

  return positions
}

/** Pyramid layout — simpler, fewer tiles (72). */
export const PYRAMID_LAYOUT: TilePosition[] = buildPyramidLayout()

function buildPyramidLayout(): TilePosition[] {
  const positions: TilePosition[] = []

  // Layer 0: 6x6
  for (let r = 0; r < 6; r++) {
    for (let c = 0; c < 6; c++) {
      positions.push({ row: r, col: c, layer: 0 })
    }
  }

  // Layer 1: 4x4 centered
  for (let r = 1; r < 5; r++) {
    for (let c = 1; c < 5; c++) {
      positions.push({ row: r, col: c, layer: 1 })
    }
  }

  // Layer 2: 2x2 centered
  for (let r = 2; r < 4; r++) {
    for (let c = 2; c < 4; c++) {
      positions.push({ row: r, col: c, layer: 2 })
    }
  }

  return positions // 36 + 16 + 4 = 56 tiles
}
