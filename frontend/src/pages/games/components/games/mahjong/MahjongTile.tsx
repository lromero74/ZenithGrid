/**
 * Mahjong tile — renders a single tile with depth effect and readable labels.
 */

import type { GameTile } from './mahjongEngine'
import { UNIQUE_TILES } from './tileSet'

interface MahjongTileProps {
  tile: GameTile
  isFree: boolean
  isSelected: boolean
  isHinted: boolean
  onClick: (id: number) => void
}

/** Suit colors for visual differentiation. */
const SUIT_COLORS: Record<string, string> = {
  bamboo: 'text-green-700',
  circle: 'text-blue-700',
  character: 'text-red-700',
  wind: 'text-slate-700',
  dragon: 'text-purple-700',
  flower: 'text-pink-600',
  season: 'text-amber-700',
}

/** Suit symbols (top line of tile). */
const SUIT_SYMBOLS: Record<string, string> = {
  bamboo: '竹',
  circle: '●',
  character: '万',
  wind: '風',
  dragon: '龍',
  flower: '花',
  season: '季',
}

/** Display labels for special tiles. */
const SPECIAL_LABELS: Record<string, string> = {
  'wind-N': '北',
  'wind-S': '南',
  'wind-E': '東',
  'wind-W': '西',
  'dragon-R': '中',
  'dragon-G': '發',
  'dragon-W': '白',
  'flower-plum': '梅',
  'flower-orchid': '蘭',
  'flower-chrysanthemum': '菊',
  'flower-bamboo': '竹',
  'season-spring': '春',
  'season-summer': '夏',
  'season-autumn': '秋',
  'season-winter': '冬',
}

/** Dragon-specific colors. */
const DRAGON_COLORS: Record<string, string> = {
  'dragon-R': 'text-red-600',
  'dragon-G': 'text-green-600',
  'dragon-W': 'text-slate-500',
}

export function MahjongTile({ tile, isFree, isSelected, isHinted, onClick }: MahjongTileProps) {
  const tileDef = UNIQUE_TILES.find(t => t.id === tile.tileDefId)
  const suit = tileDef?.suit || 'bamboo'
  const layerOffset = tile.layer * 2

  // Numbered suits show suit symbol + number
  const isNumbered = suit === 'bamboo' || suit === 'circle' || suit === 'character'
  const specialLabel = SPECIAL_LABELS[tile.tileDefId]
  const colorClass = DRAGON_COLORS[tile.tileDefId] || SUIT_COLORS[suit] || 'text-slate-700'

  return (
    <button
      onClick={() => isFree && onClick(tile.id)}
      className={`absolute w-9 h-12 sm:w-11 sm:h-[60px] rounded border flex flex-col items-center justify-center transition-all select-none leading-none ${
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
      {isNumbered ? (
        <>
          <span className={`text-[10px] sm:text-xs font-bold ${colorClass}`}>
            {SUIT_SYMBOLS[suit]}
          </span>
          <span className={`text-sm sm:text-lg font-bold ${colorClass}`}>
            {tileDef?.value}
          </span>
        </>
      ) : (
        <span className={`text-base sm:text-xl font-bold ${colorClass}`}>
          {specialLabel}
        </span>
      )}
    </button>
  )
}
