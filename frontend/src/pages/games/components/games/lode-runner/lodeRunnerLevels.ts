/**
 * Lode Runner level definitions — Classic Apple II (1983) levels 1-10.
 *
 * Grid: 28 cols x 16 rows. Each character is a tile:
 *   . = empty       B = brick (diggable)     S = solid (indestructible)
 *   H = ladder      - = bar (monkey bar)     G = gold
 *   P = player      E = enemy start          T = hidden ladder (escape)
 *   X = trap brick (looks like brick but entities fall through)
 *
 * Bottom of screen acts as floor (out-of-bounds = solid).
 * Hidden ladders (T) appear when all gold is collected.
 */

export type LevelDef = string[]

// Each level is exactly 16 rows x 28 cols.

const LEVEL_1: LevelDef = [
  // Classic Level 1: "The Beginning"
  '..................T.........',
  '....G.............T.........',
  'BBBBBBBHBBBBBBB...T.........',
  '.......H----------T....G....',
  '.......H....BBH...BBBBBBBHBB',
  '.......H....BBH..........H..',
  '.....E.H....BBH.......GE.H..',
  'BBHBBBBB....BBBBBBBBHBBBBBBB',
  '..H.................H.......',
  '..H...........E.....H.......',
  'BBBBBBBBBHBBBBBBBBBBH.......',
  '.........H..........H.......',
  '.......G.H----------H...G...',
  '....HBBBBBB.........BBBBBBBH',
  '....H.........P..G.........H',
  'BBBBBBBBBBBBBBBBBBBBBBBBBBBB',
]

const LEVEL_2: LevelDef = [
  // Classic Level 2: "Getaway"
  '...G.......................H',
  'HSSBSSH...........G........H',
  'H.....H....HBBBBBBBBBH.G...H',
  'H.G.E.H....H.........HBBBBXH',
  'HBSBSBH....H.........H.....T',
  'H.....H----H------..EH.....T',
  'H.....H....H.....HBBBSSSSSSH',
  'H.....H....H..G..H.........H',
  'H...E.H.G..HBBBBBH.........H',
  'SBBBSBBSBBSH.........HBBBHBB',
  'SBBBS......H.........H...H..',
  'SG..S......H...------H...H.G',
  'BBBBBBBBHBBBSSSS.....H..BBBB',
  '........H............H......',
  '........H...P........H......',
  'BBBBBBBBBBBBBBBBBBBBBBBBBBBB',
]

const LEVEL_3: LevelDef = [
  // Classic Level 3: "The Abyss"
  '...........................T',
  '----------....G............T',
  'H.G......HBBBBBBBBBBH......T',
  'BBBBBH...H..........HSSSSSSS',
  '.....H.E.H.....G....H.......',
  '.....HBBBBBBHBBBBBHBB.......',
  '..G..H......H.....H..--.....',
  'BBBBHB......H..E..H....--...',
  '....H....HBBBBBBHBB......--G',
  '....H----H......H..E.......B',
  '....H.......HBBBBBBBBBH.....',
  '....H.......HBBBBBBBBBH.....',
  'BBBHBBBBBBBBBB...G...BBBBBHB',
  'BBBHBBBBBBBBBB.HBBBH.BBBBBHB',
  '...H......P....HBBBH...G..H.',
  'BBBBBBBBBBBBBBBBBBBBBBBBBBBB',
]

const LEVEL_4: LevelDef = [
  // Classic Level 4: "Pyramid"
  'T...........................',
  'T-----------................',
  'H.....H.....B.G.B.....H.....',
  'H.G..HHH..G.BBBBB.G..HHH..G.',
  'H.HH..H..HH.......HH..H..HH.',
  'H.H.HHHHH.H.......H.HHHHH.H.',
  'H.H..GEG..H...H...H..GEG..H.',
  'H..HBBBBBH...HHH...HBBBBBH..',
  'H...HHHHH.HH..H..HH.HHHHH...',
  'H.........H.HHHHH.H.........',
  'H....G....H..GEG..H.....G...',
  'HBBBBBBH...HBBBBBH..HBBBBBBB',
  'H......H....HHHHH...H.......',
  'H......H............H.......',
  'H......H.......G..P.H.......',
  'BBBBBBBBBBBBBBBBBBBBBBBBBBBB',
]

const LEVEL_5: LevelDef = [
  // Classic Level 5: "Stairway"
  '.........T..................',
  '.........T.......G......E...',
  'BBB......T......BBBBHBBBBBBB',
  '..BB.....T.....BB...H.......',
  '...BB....T....BB....H.......',
  'GE.BBB...T..GBBB....H...G...',
  'BBHBBBB..T..BBBBHBBBHBBBBBBB',
  '..H...BB.T.BB...H...........',
  '..HGE..BBHBB....H.....G.....',
  'HBBBH....H.....BHBBHBBB.....',
  'H...H..............H........',
  'H...H....G.....E...H........',
  'H...HBBBBBBBHBBBBBBHBBBBBHBB',
  'H...........H............H..',
  'H...........H..P.........H..',
  'BBBBBBBBBBBBBBBBBBBBBBBBBBBB',
]

const LEVEL_6: LevelDef = [
  // Classic Level 6: "The Dungeon"
  'BBBBBBBBBBBBBBBBBBTBBBBBBBBB',
  'B.G...............TB.E.G...B',
  'BXBBBHBBBBH...G...TBBBBBBBHB',
  'BXBBBHBBBBBBBBBBBBBB.BBB..HB',
  'B....H..G.E.....BBBB.BBB..HB',
  'BHBBBBBBBBBHBBBBBBBB.BBB..HB',
  'BH...BBBBBBHBBBBBGGB.BBBG.HB',
  'BH...BBBBBBHBBBBBBBBBBBBBBHB',
  'BH...B....GH....G..E...G.BHB',
  'BH...BBBHBBBBBBBHBBBBBBBHBHB',
  'BH..GBBBH.......HBBBBBBBHBHB',
  'BHBBXB..H....P..H..BB...HBHB',
  'BHBBXBHBBBBBHBBBBBBBBGG.HBHB',
  'BHBBXBHBBBBBHBBBBBBGBBBBBBHB',
  'BHE...HBBGBBH....G..E.....HB',
  'BBBBBBBBBBBBBBBBBBBBBBBBBBBB',
]

const LEVEL_7: LevelDef = [
  // Classic Level 7: "Long Way Up"
  '..T.........................',
  '..T.................--------',
  '..T..........E......H......H',
  'BBBBBHB....BHBBB...EH....G.H',
  '.....H......H....BBBHBBBBBBB',
  '..E..H...G..H.......H.......',
  'BBBBBHBBBB..H.......H.......',
  '.....H......H.......H.......',
  '..G..H...G..H.......H.......',
  'BBHBBBBBBBBBBBBH....H.BBBB.H',
  '..H............H.G..H.BBBB.H',
  '..H..G.........H----H.B.GB.H',
  'BBBBBBBH............H.BBBBBH',
  '.......H............H......H',
  '.......H.P........G.H..E...H',
  'BBBBBBBBBBBBBBBBBBBBBBBBBBBB',
]

const LEVEL_8: LevelDef = [
  // Classic Level 8: "The Towers"
  '...........T....T...........',
  '...........T....T...........',
  '...G.E...HBT....TBH...E.G...',
  'HBBBBBH--HBT....TBH--HBBBBBH',
  'HB...BH...BT....TB...HB...BH',
  'HB...BH...BT....TB...HB...BH',
  'HB.G.BH...BT....TB...HB.G.BH',
  'HBBBBBH...BT....TB...HBBBBBH',
  'HB...BH...BT....TB...HB...BH',
  'HB...BH---BHBBBBHB---HB...BH',
  'HB...B...HBH....HBH...B...BH',
  'HBEG.B...HBH..GEHBH...B.GEBH',
  'HBBXBB...HBSSSSSSBH...BBXBBH',
  'H.....X..H........H..X.....H',
  'H......XEH....P...H.X......H',
  'BBBBBBBBBBBBBBBBBBBBBBBBBBBB',
]

const LEVEL_9: LevelDef = [
  // Classic Level 9: "The Fortress"
  'T...........................',
  'T---------------------------',
  'HB.E...B.............B.....B',
  'H.BBBBB...............BBBBB.',
  'H.B.BBB...............BGBBB.',
  'H.BBBBB.E....E......E.BBBBB.',
  'H.BBB.BXBBBBBBBBBBBBBBBBB.B.',
  'H.BBBBBXBBB.GBB.GBBBBBBBBHB.',
  'H.BBBBBXBBBBBBBBBBBBBBBBBHB.',
  'H.BBBBBXBBBBBBBBBBBBBBBBBHB.',
  'H.BBBBBXBBBB....BBBBBBBBBHB.',
  'H.BBBBBXBBBB....BBBBBBBBBHB.',
  'H.BBBBBXBBBB...GHBBBBBBBBHB.',
  'H...........BBBBH--------H..',
  'H..........SSSS.............',
  'H......P..SSSS......E.......',
]

const LEVEL_10: LevelDef = [
  // Classic Level 10: "Mountain"
  '..........G..............T..',
  '........HBBBBBBB..G......T..',
  '....G...H......BBBBBB....T..',
  'BBBBBBBBBBH.........G....T..',
  '..........HBBBBBBTBBBBBHBB..',
  'E.........H......T.....H....',
  'BBBBBBBBBBH......T.E...H...G',
  'BBBBBBBBBBHBBBBBBBSS...HBBBB',
  'BBBBBBBBBBH............H....',
  'BBBBBBBBBBH.......G.---H....',
  'BB......BBH.......BB...H....',
  'BB..GG..BBH.....G......H....',
  'BBBBBBBBBBBHBBBBBBBH...H....',
  '...........H.......BBBBBBBBH',
  '....G....P.H...............H',
  'BBBBBBBBBBBBBBBBBBBBBBBBBBBB',
]

export const LEVELS: LevelDef[] = [
  LEVEL_1, LEVEL_2, LEVEL_3, LEVEL_4, LEVEL_5,
  LEVEL_6, LEVEL_7, LEVEL_8, LEVEL_9, LEVEL_10,
]

export const TOTAL_LEVELS = LEVELS.length

export const LEVEL_NAMES: string[] = [
  'The Beginning',
  'Getaway',
  'The Abyss',
  'Pyramid',
  'Stairway',
  'The Dungeon',
  'Long Way Up',
  'The Towers',
  'The Fortress',
  'Mountain',
]
