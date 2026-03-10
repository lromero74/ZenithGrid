/**
 * Theme-specific CSS backgrounds for the crossword puzzle.
 *
 * Each theme gets a gradient + optional pattern that evokes its mood.
 * Applied as a dimmed overlay behind the puzzle grid.
 */

interface ThemeBg {
  gradient: string   // CSS gradient
  emoji?: string     // Optional decorative emoji scattered as pseudo-content
  opacity?: number   // Override default 0.12 opacity
}

// Group themes by visual style to avoid 100 unique entries
const THEME_GROUPS: Record<string, ThemeBg> = {
  // ── Space & Sky ───────────────────────────────────────────────
  astronomy: {
    gradient: 'radial-gradient(ellipse at 20% 50%, #1a0533 0%, #0a0a2e 40%, #000010 100%)',
    emoji: '✨',
  },
  astronomy_advanced: {
    gradient: 'radial-gradient(ellipse at 80% 30%, #1a0533 0%, #0d0d35 50%, #000010 100%)',
    emoji: '🌌',
  },
  astronomy_solar: {
    gradient: 'radial-gradient(ellipse at 50% 50%, #2d1800 0%, #1a0f00 40%, #0a0500 100%)',
    emoji: '☀️',
  },
  space_exploration: {
    gradient: 'radial-gradient(ellipse at 30% 70%, #0a0a30 0%, #050520 50%, #000008 100%)',
    emoji: '🚀',
  },
  weather: {
    gradient: 'linear-gradient(180deg, #1a2a4a 0%, #2a3a5a 50%, #1a2a3a 100%)',
    emoji: '🌤️',
  },
  weather_extreme: {
    gradient: 'linear-gradient(180deg, #2a1a3a 0%, #3a2a2a 50%, #1a1a2a 100%)',
    emoji: '⛈️',
  },

  // ── Nature & Outdoors ─────────────────────────────────────────
  ocean: {
    gradient: 'linear-gradient(180deg, #0a1628 0%, #0d2137 40%, #0a1a2a 100%)',
    emoji: '🌊',
  },
  marine_life: {
    gradient: 'linear-gradient(180deg, #081a28 0%, #0a2535 40%, #061520 100%)',
    emoji: '🐠',
  },
  sailing: {
    gradient: 'linear-gradient(180deg, #0d1f33 0%, #15304a 50%, #0a1825 100%)',
    emoji: '⛵',
  },
  rivers: {
    gradient: 'linear-gradient(180deg, #0a1a20 0%, #102a30 50%, #081820 100%)',
    emoji: '🏞️',
  },
  fishing: {
    gradient: 'linear-gradient(180deg, #0d1f2a 0%, #153040 50%, #0a1820 100%)',
    emoji: '🎣',
  },
  botany: {
    gradient: 'linear-gradient(135deg, #0a1a0a 0%, #0d250d 50%, #0a1a0a 100%)',
    emoji: '🌿',
  },
  flowers: {
    gradient: 'linear-gradient(135deg, #1a0a1a 0%, #200d20 50%, #150a15 100%)',
    emoji: '🌸',
  },
  trees: {
    gradient: 'linear-gradient(180deg, #0a150a 0%, #0d200d 50%, #081408 100%)',
    emoji: '🌲',
  },
  gardening: {
    gradient: 'linear-gradient(180deg, #0a1508 0%, #152010 50%, #0a1508 100%)',
    emoji: '🌻',
  },
  jungle: {
    gradient: 'linear-gradient(180deg, #051208 0%, #0a1f0d 50%, #051208 100%)',
    emoji: '🌴',
  },
  farm: {
    gradient: 'linear-gradient(180deg, #151208 0%, #1f1a0a 50%, #151208 100%)',
    emoji: '🌾',
  },
  camping: {
    gradient: 'linear-gradient(180deg, #0a0f08 0%, #121a0d 50%, #0a0f08 100%)',
    emoji: '🏕️',
  },
  hiking: {
    gradient: 'linear-gradient(180deg, #0d100a 0%, #151a0d 50%, #0d100a 100%)',
    emoji: '🥾',
  },
  mountains: {
    gradient: 'linear-gradient(180deg, #1a1a2a 0%, #252535 50%, #15151f 100%)',
    emoji: '🏔️',
  },
  desert: {
    gradient: 'linear-gradient(180deg, #1a1508 0%, #2a200a 50%, #1a1508 100%)',
    emoji: '🏜️',
  },
  arctic: {
    gradient: 'linear-gradient(180deg, #0a1520 0%, #152535 50%, #0a1520 100%)',
    emoji: '❄️',
  },
  ecology: {
    gradient: 'linear-gradient(180deg, #081208 0%, #0d1a0d 50%, #081208 100%)',
    emoji: '♻️',
  },

  // ── Animals ───────────────────────────────────────────────────
  animals: {
    gradient: 'linear-gradient(135deg, #1a150a 0%, #201a0d 50%, #1a150a 100%)',
    emoji: '🦁',
  },
  birds: {
    gradient: 'linear-gradient(180deg, #151a25 0%, #1a2030 50%, #101520 100%)',
    emoji: '🦅',
  },
  insects: {
    gradient: 'linear-gradient(135deg, #0d150a 0%, #121a0d 50%, #0d150a 100%)',
    emoji: '🦋',
  },
  dinosaurs: {
    gradient: 'linear-gradient(180deg, #1a1208 0%, #251a0a 50%, #1a1208 100%)',
    emoji: '🦕',
  },
  pets: {
    gradient: 'linear-gradient(135deg, #1a1515 0%, #201a1a 50%, #1a1515 100%)',
    emoji: '🐾',
  },

  // ── Food & Drink ──────────────────────────────────────────────
  cooking: {
    gradient: 'linear-gradient(135deg, #1a1208 0%, #25180a 50%, #1a1208 100%)',
    emoji: '🍳',
  },
  baking: {
    gradient: 'linear-gradient(135deg, #1a150d 0%, #201a10 50%, #1a150d 100%)',
    emoji: '🧁',
  },
  desserts: {
    gradient: 'linear-gradient(135deg, #1a100d 0%, #25150f 50%, #1a100d 100%)',
    emoji: '🍰',
  },
  spices: {
    gradient: 'linear-gradient(135deg, #1a0d08 0%, #251008 50%, #1a0d08 100%)',
    emoji: '🌶️',
  },
  food_and_drink: {
    gradient: 'linear-gradient(135deg, #1a1510 0%, #201a12 50%, #1a1510 100%)',
    emoji: '🍕',
  },
  coffee_tea: {
    gradient: 'linear-gradient(135deg, #15100a 0%, #1a140d 50%, #15100a 100%)',
    emoji: '☕',
  },
  wine_beer: {
    gradient: 'linear-gradient(135deg, #200d0d 0%, #2a1010 50%, #200d0d 100%)',
    emoji: '🍷',
  },

  // ── Science & Tech ────────────────────────────────────────────
  chemistry: {
    gradient: 'linear-gradient(135deg, #0a1520 0%, #0d1a28 50%, #0a1520 100%)',
    emoji: '⚗️',
  },
  physics: {
    gradient: 'linear-gradient(135deg, #0d0d20 0%, #10102a 50%, #0d0d20 100%)',
    emoji: '⚛️',
  },
  mathematics: {
    gradient: 'linear-gradient(135deg, #101020 0%, #15152a 50%, #101020 100%)',
    emoji: '📐',
  },
  electricity: {
    gradient: 'linear-gradient(180deg, #0d0d1a 0%, #151528 50%, #0d0d1a 100%)',
    emoji: '⚡',
  },
  computers: {
    gradient: 'linear-gradient(135deg, #080d15 0%, #0a101a 50%, #080d15 100%)',
    emoji: '💻',
  },
  internet: {
    gradient: 'linear-gradient(135deg, #0a0d18 0%, #0d1020 50%, #0a0d18 100%)',
    emoji: '🌐',
  },
  technology: {
    gradient: 'linear-gradient(135deg, #0a0f18 0%, #0d1220 50%, #0a0f18 100%)',
    emoji: '📱',
  },
  robots: {
    gradient: 'linear-gradient(135deg, #0d1015 0%, #10151a 50%, #0d1015 100%)',
    emoji: '🤖',
  },
  video_games: {
    gradient: 'linear-gradient(135deg, #0d0a1a 0%, #120d22 50%, #0d0a1a 100%)',
    emoji: '🎮',
  },
  inventions: {
    gradient: 'linear-gradient(135deg, #151510 0%, #1a1a12 50%, #151510 100%)',
    emoji: '💡',
  },

  // ── Earth Sciences ────────────────────────────────────────────
  geology: {
    gradient: 'linear-gradient(180deg, #151008 0%, #1f180d 50%, #151008 100%)',
    emoji: '🪨',
  },
  gemstones: {
    gradient: 'linear-gradient(135deg, #150d1a 0%, #1a1020 50%, #150d1a 100%)',
    emoji: '💎',
  },
  volcanoes: {
    gradient: 'linear-gradient(180deg, #1a0a08 0%, #25100a 50%, #1a0a08 100%)',
    emoji: '🌋',
  },
  earthquakes: {
    gradient: 'linear-gradient(180deg, #15100a 0%, #1a150d 50%, #15100a 100%)',
    emoji: '🌍',
  },
  geography: {
    gradient: 'linear-gradient(180deg, #0d1510 0%, #101a15 50%, #0d1510 100%)',
    emoji: '🗺️',
  },
  maps_navigation: {
    gradient: 'linear-gradient(135deg, #10150d 0%, #151a10 50%, #10150d 100%)',
    emoji: '🧭',
  },

  // ── History & Culture ─────────────────────────────────────────
  history: {
    gradient: 'linear-gradient(135deg, #1a1510 0%, #201812 50%, #1a1510 100%)',
    emoji: '📜',
  },
  ancient_civilizations: {
    gradient: 'linear-gradient(135deg, #1a150a 0%, #251a0d 50%, #1a150a 100%)',
    emoji: '🏛️',
  },
  mythology: {
    gradient: 'linear-gradient(135deg, #15101a 0%, #1a1320 50%, #15101a 100%)',
    emoji: '⚔️',
  },
  mythology_greek: {
    gradient: 'linear-gradient(135deg, #151020 0%, #1a1328 50%, #151020 100%)',
    emoji: '🏺',
  },
  mythology_norse: {
    gradient: 'linear-gradient(180deg, #0d1018 0%, #101520 50%, #0d1018 100%)',
    emoji: '🪓',
  },
  mythology_egyptian: {
    gradient: 'linear-gradient(135deg, #1a1508 0%, #25200a 50%, #1a1508 100%)',
    emoji: '🔺',
  },
  knights: {
    gradient: 'linear-gradient(135deg, #10101a 0%, #151520 50%, #10101a 100%)',
    emoji: '🛡️',
  },
  castles: {
    gradient: 'linear-gradient(180deg, #121218 0%, #18181f 50%, #121218 100%)',
    emoji: '🏰',
  },
  pirates: {
    gradient: 'linear-gradient(135deg, #0d0d0d 0%, #151515 50%, #0d0d0d 100%)',
    emoji: '🏴‍☠️',
  },
  landmarks: {
    gradient: 'linear-gradient(180deg, #15151a 0%, #1a1a20 50%, #15151a 100%)',
    emoji: '🗽',
  },
  languages: {
    gradient: 'linear-gradient(135deg, #15101a 0%, #1a1520 50%, #15101a 100%)',
    emoji: '🗣️',
  },
  currencies: {
    gradient: 'linear-gradient(135deg, #0d1508 0%, #101a0a 50%, #0d1508 100%)',
    emoji: '💰',
  },

  // ── Arts & Entertainment ──────────────────────────────────────
  art: {
    gradient: 'linear-gradient(135deg, #1a0d15 0%, #200f1a 50%, #1a0d15 100%)',
    emoji: '🎨',
  },
  music: {
    gradient: 'linear-gradient(135deg, #0d0a1a 0%, #100d20 50%, #0d0a1a 100%)',
    emoji: '🎵',
  },
  dance: {
    gradient: 'linear-gradient(135deg, #1a0d15 0%, #200f1a 50%, #1a0d15 100%)',
    emoji: '💃',
  },
  theater: {
    gradient: 'linear-gradient(180deg, #1a0d0d 0%, #251010 50%, #1a0d0d 100%)',
    emoji: '🎭',
  },
  movies: {
    gradient: 'linear-gradient(180deg, #0d0d15 0%, #10101a 50%, #0d0d15 100%)',
    emoji: '🎬',
  },
  literature: {
    gradient: 'linear-gradient(135deg, #15120d 0%, #1a1510 50%, #15120d 100%)',
    emoji: '📚',
  },
  photography: {
    gradient: 'linear-gradient(135deg, #101010 0%, #181818 50%, #101010 100%)',
    emoji: '📷',
  },
  magic: {
    gradient: 'radial-gradient(ellipse at 50% 50%, #1a0d2a 0%, #100820 50%, #080515 100%)',
    emoji: '🪄',
  },
  fairy_tales: {
    gradient: 'linear-gradient(135deg, #150d1a 0%, #1a1020 50%, #150d1a 100%)',
    emoji: '🧚',
  },
  superheroes: {
    gradient: 'linear-gradient(135deg, #1a0a0a 0%, #200d15 50%, #1a0a0a 100%)',
    emoji: '🦸',
  },
  crime_mystery: {
    gradient: 'linear-gradient(180deg, #0d0d0d 0%, #151515 50%, #0a0a0a 100%)',
    emoji: '🔍',
  },

  // ── Sports & Games ────────────────────────────────────────────
  sports: {
    gradient: 'linear-gradient(135deg, #0d1a0d 0%, #102010 50%, #0d1a0d 100%)',
    emoji: '⚽',
  },
  board_games: {
    gradient: 'linear-gradient(135deg, #15120d 0%, #1a1510 50%, #15120d 100%)',
    emoji: '🎲',
  },
  card_games: {
    gradient: 'linear-gradient(135deg, #0d1518 0%, #101a20 50%, #0d1518 100%)',
    emoji: '🃏',
  },
  circus: {
    gradient: 'linear-gradient(135deg, #1a0d0d 0%, #201010 50%, #1a0d0d 100%)',
    emoji: '🎪',
  },

  // ── Professions & Tools ───────────────────────────────────────
  occupations: {
    gradient: 'linear-gradient(135deg, #121215 0%, #18181a 50%, #121215 100%)',
    emoji: '👷',
  },
  tools: {
    gradient: 'linear-gradient(135deg, #12100d 0%, #181510 50%, #12100d 100%)',
    emoji: '🔧',
  },
  medicine: {
    gradient: 'linear-gradient(135deg, #0d1518 0%, #101a20 50%, #0d1518 100%)',
    emoji: '🏥',
  },
  firefighting: {
    gradient: 'linear-gradient(180deg, #1a0d08 0%, #25100a 50%, #1a0d08 100%)',
    emoji: '🚒',
  },
  plumbing: {
    gradient: 'linear-gradient(135deg, #0d1215 0%, #10181a 50%, #0d1215 100%)',
    emoji: '🔩',
  },
  woodworking: {
    gradient: 'linear-gradient(135deg, #15100a 0%, #1a140d 50%, #15100a 100%)',
    emoji: '🪵',
  },

  // ── Transport & Vehicles ──────────────────────────────────────
  transportation: {
    gradient: 'linear-gradient(135deg, #10101a 0%, #151520 50%, #10101a 100%)',
    emoji: '🚗',
  },
  aviation: {
    gradient: 'linear-gradient(180deg, #0d1525 0%, #102030 50%, #0d1525 100%)',
    emoji: '✈️',
  },
  trains: {
    gradient: 'linear-gradient(180deg, #12100d 0%, #1a1510 50%, #12100d 100%)',
    emoji: '🚂',
  },
  bridges: {
    gradient: 'linear-gradient(180deg, #10121a 0%, #151820 50%, #10121a 100%)',
    emoji: '🌉',
  },

  // ── Seasons ───────────────────────────────────────────────────
  spring: {
    gradient: 'linear-gradient(180deg, #0d180d 0%, #102010 50%, #0d180d 100%)',
    emoji: '🌷',
  },
  summer: {
    gradient: 'linear-gradient(180deg, #1a1508 0%, #251d0a 50%, #1a1508 100%)',
    emoji: '☀️',
  },
  autumn: {
    gradient: 'linear-gradient(180deg, #1a1008 0%, #25150a 50%, #1a1008 100%)',
    emoji: '🍂',
  },
  winter: {
    gradient: 'linear-gradient(180deg, #0d1520 0%, #102030 50%, #0d1520 100%)',
    emoji: '⛄',
  },
  holidays: {
    gradient: 'linear-gradient(135deg, #1a0d0d 0%, #0d1a0d 50%, #1a0d0d 100%)',
    emoji: '🎄',
  },

  // ── Textiles & Fashion ────────────────────────────────────────
  fashion: {
    gradient: 'linear-gradient(135deg, #1a0d15 0%, #200f1a 50%, #1a0d15 100%)',
    emoji: '👗',
  },
  fabrics: {
    gradient: 'linear-gradient(135deg, #15100d 0%, #1a1510 50%, #15100d 100%)',
    emoji: '🧵',
  },
  colors: {
    gradient: 'linear-gradient(135deg, #150d15 0%, #1a101a 50%, #150d15 100%)',
    emoji: '🌈',
  },
  ceramics: {
    gradient: 'linear-gradient(135deg, #15100a 0%, #1a140d 50%, #15100a 100%)',
    emoji: '🏺',
  },

  // ── Music & Instruments ───────────────────────────────────────
  instruments: {
    gradient: 'linear-gradient(135deg, #1a150d 0%, #201a10 50%, #1a150d 100%)',
    emoji: '🎸',
  },

  // ── Time ──────────────────────────────────────────────────────
  clocks_time: {
    gradient: 'linear-gradient(135deg, #12120d 0%, #181810 50%, #12120d 100%)',
    emoji: '⏰',
  },

  // ── Architecture ──────────────────────────────────────────────
  architecture: {
    gradient: 'linear-gradient(180deg, #121215 0%, #18181a 50%, #121215 100%)',
    emoji: '🏗️',
  },

  // ── Words & Puzzles ───────────────────────────────────────────
  word: {
    gradient: 'linear-gradient(135deg, #12100d 0%, #181510 50%, #12100d 100%)',
    emoji: '✏️',
  },
  clue: {
    gradient: 'linear-gradient(135deg, #0d1015 0%, #10151a 50%, #0d1015 100%)',
    emoji: '🔎',
  },
}

// Default fallback
const DEFAULT_BG: ThemeBg = {
  gradient: 'linear-gradient(180deg, #0d0d15 0%, #121218 50%, #0d0d15 100%)',
  emoji: '📝',
}

/** Get background style for a given theme key. */
export function getThemeBackground(theme: string): { gradient: string; emoji: string; opacity: number } {
  const bg = THEME_GROUPS[theme] ?? DEFAULT_BG
  return {
    gradient: bg.gradient,
    emoji: bg.emoji ?? '📝',
    opacity: bg.opacity ?? 0.15,
  }
}
