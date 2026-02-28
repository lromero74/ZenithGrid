/**
 * Mahjong tile — renders a single tile with depth effect.
 * Supports two visual themes: "classic" (Unicode/emoji) and "kanji" (CJK characters).
 */

import type { GameTile } from './mahjongEngine'
import { TILE_DISPLAY, UNIQUE_TILES } from './tileSet'

export type TileTheme = 'classic' | 'kanji'

interface MahjongTileProps {
  tile: GameTile
  isFree: boolean
  isSelected: boolean
  isHinted: boolean
  theme: TileTheme
  onClick: (id: number) => void
}

// ── Classic theme: high-contrast colors for Unicode/emoji on amber tiles ──

const CLASSIC_COLORS: Record<string, string> = {
  bamboo: 'text-emerald-800',
  circle: 'text-indigo-800',
  character: 'text-rose-800',
  wind: 'text-slate-900',
  dragon: 'text-slate-900',
  flower: 'text-fuchsia-800',
  season: 'text-cyan-800',
}

const CLASSIC_DRAGON_COLORS: Record<string, string> = {
  'dragon-R': 'text-red-700',
  'dragon-G': 'text-emerald-800',
  'dragon-W': 'text-indigo-700',
}

// ── Kanji theme: suit-coded two-line display ──

const KANJI_COLORS: Record<string, string> = {
  bamboo: 'text-green-700',
  circle: 'text-blue-700',
  character: 'text-red-700',
  wind: 'text-slate-700',
  dragon: 'text-purple-700',
  flower: 'text-pink-600',
  season: 'text-amber-700',
}

const KANJI_DRAGON_COLORS: Record<string, string> = {
  'dragon-R': 'text-red-600',
  'dragon-G': 'text-green-600',
  'dragon-W': 'text-slate-500',
}

const SUIT_SYMBOLS: Record<string, string> = {
  bamboo: '竹', circle: '●', character: '万',
  wind: '風', dragon: '龍', flower: '花', season: '季',
}

const SPECIAL_LABELS: Record<string, string> = {
  'wind-N': '北', 'wind-S': '南', 'wind-E': '東', 'wind-W': '西',
  'dragon-R': '中', 'dragon-G': '發', 'dragon-W': '白',
  'flower-plum': '梅', 'flower-orchid': '蘭',
  'flower-chrysanthemum': '菊', 'flower-bamboo': '竹',
  'season-spring': '春', 'season-summer': '夏',
  'season-autumn': '秋', 'season-winter': '冬',
}

export function MahjongTile({ tile, isFree, isSelected, isHinted, theme, onClick }: MahjongTileProps) {
  const tileDef = UNIQUE_TILES.find(t => t.id === tile.tileDefId)
  const suit = tileDef?.suit || 'bamboo'
  const layerOffset = tile.layer * 2

  return (
    <button
      onClick={() => isFree && onClick(tile.id)}
      className={`absolute w-9 h-12 sm:w-11 sm:h-[60px] rounded border flex flex-col items-center justify-center transition-all select-none leading-none overflow-hidden ${
        isSelected
          ? 'ring-2 ring-yellow-400 bg-amber-100 border-amber-600 z-50'
          : isHinted
          ? 'ring-2 ring-emerald-400 bg-amber-50 border-amber-600 z-40 animate-pulse'
          : isFree
          ? 'bg-amber-50 border-amber-800 hover:bg-amber-100 cursor-pointer shadow-md'
          : 'bg-amber-100/60 border-amber-800/50 opacity-60 cursor-default shadow'
      }`}
      style={{
        left: `${tile.col * 40 + layerOffset + 60}px`,
        top: `${tile.row * 52 + layerOffset + 20}px`,
        zIndex: tile.layer * 10 + Math.floor(tile.row),
      }}
      disabled={!isFree}
    >
      {theme === 'classic'
        ? <ClassicContent tileDefId={tile.tileDefId} suit={suit} />
        : <KanjiContent tileDefId={tile.tileDefId} suit={suit} value={tileDef?.value} />
      }
    </button>
  )
}

/** Classic theme: Unicode mahjong chars + emoji with high-contrast colors, sized to fill tile. */
function ClassicContent({ tileDefId, suit }: { tileDefId: string; suit: string }) {
  const display = TILE_DISPLAY[tileDefId]
  const colorClass = CLASSIC_DRAGON_COLORS[tileDefId] || CLASSIC_COLORS[suit] || 'text-slate-900'
  const isEmoji = suit === 'flower' || suit === 'season'

  return (
    <span
      className={`font-bold leading-none ${colorClass} ${
        isEmoji ? 'text-2xl sm:text-3xl' : 'text-[28px] sm:text-[38px]'
      }`}
    >
      {display}
    </span>
  )
}

/** Kanji theme: suit symbol + number for numbered suits, CJK for specials. */
function KanjiContent({ tileDefId, suit, value }: { tileDefId: string; suit: string; value?: string }) {
  const isNumbered = suit === 'bamboo' || suit === 'circle' || suit === 'character'
  const colorClass = KANJI_DRAGON_COLORS[tileDefId] || KANJI_COLORS[suit] || 'text-slate-700'

  if (isNumbered) {
    return (
      <>
        <span className={`text-[10px] sm:text-xs font-bold ${colorClass}`}>
          {SUIT_SYMBOLS[suit]}
        </span>
        <span className={`text-sm sm:text-lg font-bold ${colorClass}`}>
          {value}
        </span>
      </>
    )
  }

  return (
    <span className={`text-base sm:text-xl font-bold ${colorClass}`}>
      {SPECIAL_LABELS[tileDefId]}
    </span>
  )
}
