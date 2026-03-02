/**
 * Lode Runner level definitions — 10 progressive levels.
 *
 * Grid: 28 cols x 16 rows. Each character is a tile:
 *   . = empty       B = brick (diggable)     S = solid (indestructible)
 *   H = ladder      - = bar (monkey bar)     G = gold
 *   P = player      E = enemy start          T = hidden ladder (row 0 escape)
 *
 * Row 0 is always T (hidden escape ladders, revealed when all gold collected).
 * Row 15 (bottom) is always solid.
 * Every gold piece must be reachable. Every level must be completable.
 */

export type LevelDef = string[]

// Each level is exactly 16 rows x 28 cols.

const LEVEL_1: LevelDef = [
  // "First Steps" — 0 enemies, teaches movement + ladders + gold
  'TTTTTTTTTTTTTTTTTTTTTTTTTTTT', // 0: hidden escape
  '............................', // 1
  '............................', // 2
  '............................', // 3
  '...G........................', // 4
  '..HBBB...........G..........', // 5
  '..H..........BBBBBBB........', // 6
  '..H.........................', // 7
  '..H......G..........G.......', // 8
  '..H...HBBBBBB...BBBBHBB.....', // 9
  '..H...H.............H.......', // 10
  '..H...H.............H.......', // 11
  '..H...H.....G......H.......', // 12
  '..H...H..HBBBBBBB..H.......', // 13
  '..H...H..H..........H......', // 14
  'SSSSSSSSSSSSSSSSSSSSSSSSSSSS', // 15: solid floor
]

const LEVEL_2: LevelDef = [
  // "Dig It" — 0 enemies, teaches brick digging to reach gold below
  'TTTTTTTTTTTTTTTTTTTTTTTTTTTT',
  '............................',
  '............................',
  '..........G.......G.........',
  '........BBBBB...BBBBB.......',
  '.......H.............H......',
  '.......H.............H......',
  '..G....H.............H......',
  'BBHBB..H.............H......',
  '..H....H.............H......',
  '..H..BBHBBG...GBBBBBBH......',
  '..H....H.............H......',
  '..H....H.............H......',
  '..H..BBBBBBBGBBBBBBBBB......',
  '..H............................',
  'SSSSSSSSSSSSSSSSSSSSSSSSSSSS',
]

const LEVEL_3: LevelDef = [
  // "The Guard" — 1 enemy, teaches enemy avoidance + timing
  'TTTTTTTTTTTTTTTTTTTTTTTTTTTT',
  '............................',
  '............................',
  '............................',
  '....G.............E.........',
  '..HBBBBB.......BBBBBB.......',
  '..H..................H......',
  '..H..................H......',
  '..H.......G..........H......',
  '..H....HBBBBBBBB.....H......',
  '..H....H.........H...H......',
  '..H....H.........H...H......',
  '..H..G.H....G....H.G.H......',
  '..HBBBBBBBBBBBBBBBBBBBB......',
  '..H.........................',
  'SSSSSSSSSSSSSSSSSSSSSSSSSSSS',
]

const LEVEL_4: LevelDef = [
  // "Trap and Escape" — 1 enemy, dig-to-trap core mechanic
  'TTTTTTTTTTTTTTTTTTTTTTTTTTTT',
  '............................',
  '............................',
  '............................',
  '..P...........E.............',
  '..HBBBBBBBBBBBBBBBBH........',
  '..H................H........',
  '..H................H........',
  '..H......G.........H........',
  '..H....BBBBBBB.....H........',
  '..H................H........',
  '..H..G.............H........',
  '..HBBBBBBBBBBBBBBBBHB........',
  '..H..............G.H........',
  '..H................H........',
  'SSSSSSSSSSSSSSSSSSSSSSSSSSSS',
]

const LEVEL_5: LevelDef = [
  // "Monkey Bars" — 1 enemy, bar traversal over gaps
  'TTTTTTTTTTTTTTTTTTTTTTTTTTTT',
  '............................',
  '............................',
  '............................',
  '....G...........G...........',
  '..HBBBB.......BBBBH.........',
  '..H...............H.........',
  '..H...-----------.H.........',
  '..H...............H.........',
  '..H..HBBBB...BBBBHH.........',
  '..H..H...........HH.........',
  '..H..H....E......HH.........',
  '..H..H.G.........HH.........',
  '..HBBBBBBB--BBBBBHB.........',
  '..H............G.H..........',
  'SSSSSSSSSSSSSSSSSSSSSSSSSSSS',
]

const LEVEL_6: LevelDef = [
  // "The Pit" — 2 enemies, multi-level with strategic descent
  'TTTTTTTTTTTTTTTTTTTTTTTTTTTT',
  '............................',
  '....G..........G............',
  '..HBBBB....BBBBBBH..........',
  '..H..............H..........',
  '..H....E.........H..........',
  '..H..HBBBBBB.....H..........',
  '..H..H.......G...H..........',
  '..H..H..HBBBBBBBBH..........',
  '..H..H..H........H..........',
  '..H..H..H..E.....H..........',
  '..H..HBBBBBBBBBB.H..........',
  '..H..H........G..H..........',
  '..H..H...........H..........',
  '..HBBBBBBBBBBBBBBBBB.........',
  'SSSSSSSSSSSSSSSSSSSSSSSSSSSS',
]

const LEVEL_7: LevelDef = [
  // "Tower Climb" — 2 enemies, vertical level, scattered gold
  'TTTTTTTTTTTTTTTTTTTTTTTTTTTT',
  '...........G................',
  '.........HBBBB..............',
  '.........H....G.............',
  '.....HBBBBBBBBBBH............',
  '.....H..........H...........',
  '..G..H...E......H...........',
  'BBHBBBBBBBBB....H...........',
  '..H.........BBBBH...........',
  '..H.....G.......H...........',
  '..HBBBBBBBBB....H...........',
  '..H...........BHB...........',
  '..H....G.......H............',
  '..HBBBBBBBB..E.H............',
  '..H......G.....H............',
  'SSSSSSSSSSSSSSSSSSSSSSSSSSSS',
]

const LEVEL_8: LevelDef = [
  // "Bridge Run" — 2 enemies, brick bridges, dig to drop enemies
  'TTTTTTTTTTTTTTTTTTTTTTTTTTTT',
  '............................',
  '..G.......G.........G.......',
  'BBHBB...BBHBB.....BBHBB.....',
  '..H.......H.........H......',
  '..H.......H....E....H......',
  '..H..HBBBBBBBBBBBBBBBB......',
  '..H..H.................H....',
  '..H..H.................H....',
  '..HBBBBBB....BBBBBBBBHBH....',
  '..H......G.........E.H.H....',
  '..H..................H.H....',
  '..H..HBBBBBBBBBBBBBBB..H....',
  '..H..H..........G.....H....',
  '..H..H................H....',
  'SSSSSSSSSSSSSSSSSSSSSSSSSSSS',
]

const LEVEL_9: LevelDef = [
  // "The Maze" — 3 enemies, complex paths, dead ends
  'TTTTTTTTTTTTTTTTTTTTTTTTTTTT',
  '............................',
  '..G....G.......G....G.......',
  'BBHBBBBBBBH.HBBBBBBBHBB.....',
  '..H.......H.H.......H......',
  '..H..E....H.H..E....H......',
  '..HBBBH...H.H..HBBBHH......',
  '..H...H...H.H..H...HH......',
  '..H...HBBBB.BBBB...HH......',
  '..H...H.........H..HH......',
  '..HBBBB....G....BBBHH......',
  '..H......HBBBH.....HH......',
  '..H......H...H.....HH......',
  '..H....G.H.E.H..G..HH......',
  '..HBBBBBBBBBBBBBBBBBBH......',
  'SSSSSSSSSSSSSSSSSSSSSSSSSSSS',
]

const LEVEL_10: LevelDef = [
  // "Gauntlet" — 3 enemies, all mechanics combined
  'TTTTTTTTTTTTTTTTTTTTTTTTTTTT',
  '..G..........G..........G...',
  'BBHBB..----..BBBBH..HBBBH...',
  '..H..............H..H...H...',
  '..H.....E........H..H.G.H...',
  '..HBBBBBBBBBB..BBBBBBBBHH...',
  '..H..........H.........H...',
  '..H..G.......H...E.....H...',
  '..HBBBBBB----BBBBHBBBBBBH...',
  '..H..............H.........',
  '..H..HBBBH...G...H.........',
  '..H..H...H.HBBBBBB.........',
  '..H..H.G.H.H......E........',
  '..HBBBBBBBB.BBBBBBBBHBB.....',
  '..H.....G...........H......',
  'SSSSSSSSSSSSSSSSSSSSSSSSSSSS',
]

export const LEVELS: LevelDef[] = [
  LEVEL_1, LEVEL_2, LEVEL_3, LEVEL_4, LEVEL_5,
  LEVEL_6, LEVEL_7, LEVEL_8, LEVEL_9, LEVEL_10,
]

export const TOTAL_LEVELS = LEVELS.length

export const LEVEL_NAMES: string[] = [
  'First Steps',
  'Dig It',
  'The Guard',
  'Trap and Escape',
  'Monkey Bars',
  'The Pit',
  'Tower Climb',
  'Bridge Run',
  'The Maze',
  'Gauntlet',
]
