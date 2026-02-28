/**
 * Mahjong tile definitions — 36 unique tiles, 4 of each = 144 total.
 */

export interface TileDef {
  id: string
  suit: string
  value: string
  matchGroup: string // tiles with same matchGroup can pair
}

// Bamboo 1-9
const BAMBOO: TileDef[] = Array.from({ length: 9 }, (_, i) => ({
  id: `bamboo-${i + 1}`,
  suit: 'bamboo',
  value: String(i + 1),
  matchGroup: `bamboo-${i + 1}`,
}))

// Circle 1-9
const CIRCLE: TileDef[] = Array.from({ length: 9 }, (_, i) => ({
  id: `circle-${i + 1}`,
  suit: 'circle',
  value: String(i + 1),
  matchGroup: `circle-${i + 1}`,
}))

// Character 1-9
const CHARACTER: TileDef[] = Array.from({ length: 9 }, (_, i) => ({
  id: `char-${i + 1}`,
  suit: 'character',
  value: String(i + 1),
  matchGroup: `char-${i + 1}`,
}))

// Winds (4 unique, 4 copies each)
const WINDS: TileDef[] = ['N', 'S', 'E', 'W'].map(w => ({
  id: `wind-${w}`,
  suit: 'wind',
  value: w,
  matchGroup: `wind-${w}`,
}))

// Dragons (3 unique, 4 copies each)
const DRAGONS: TileDef[] = ['R', 'G', 'W'].map(d => ({
  id: `dragon-${d}`,
  suit: 'dragon',
  value: d,
  matchGroup: `dragon-${d}`,
}))

// Flowers (4 unique, but they all match each other)
const FLOWERS: TileDef[] = ['plum', 'orchid', 'chrysanthemum', 'bamboo'].map(f => ({
  id: `flower-${f}`,
  suit: 'flower',
  value: f,
  matchGroup: 'flower', // all flowers match each other
}))

// Seasons (4 unique, but they all match each other)
const SEASONS: TileDef[] = ['spring', 'summer', 'autumn', 'winter'].map(s => ({
  id: `season-${s}`,
  suit: 'season',
  value: s,
  matchGroup: 'season', // all seasons match each other
}))

/** All 36 unique tile definitions. */
export const UNIQUE_TILES: TileDef[] = [
  ...BAMBOO, ...CIRCLE, ...CHARACTER,
  ...WINDS, ...DRAGONS, ...FLOWERS, ...SEASONS,
]

/** Display characters for tiles. */
export const TILE_DISPLAY: Record<string, string> = {
  'bamboo-1': '🀇', 'bamboo-2': '🀈', 'bamboo-3': '🀉',
  'bamboo-4': '🀊', 'bamboo-5': '🀋', 'bamboo-6': '🀌',
  'bamboo-7': '🀍', 'bamboo-8': '🀎', 'bamboo-9': '🀏',
  'circle-1': '🀙', 'circle-2': '🀚', 'circle-3': '🀛',
  'circle-4': '🀜', 'circle-5': '🀝', 'circle-6': '🀞',
  'circle-7': '🀟', 'circle-8': '🀠', 'circle-9': '🀡',
  'char-1': '🀀', 'char-2': '🀁', 'char-3': '🀂',
  'char-4': '🀃', 'char-5': '🀄', 'char-6': '🀅',
  'char-7': '🀆', 'char-8': '🀇', 'char-9': '🀈',
  'wind-N': 'N', 'wind-S': 'S', 'wind-E': 'E', 'wind-W': 'W',
  'dragon-R': 'R', 'dragon-G': 'G', 'dragon-W': 'W',
  'flower-plum': '🌸', 'flower-orchid': '🌺',
  'flower-chrysanthemum': '🌻', 'flower-bamboo': '🎋',
  'season-spring': '🌱', 'season-summer': '☀',
  'season-autumn': '🍂', 'season-winter': '❄',
}
