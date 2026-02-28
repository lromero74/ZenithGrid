/**
 * Mahjong tile — renders a single tile with depth effect.
 */

import type { GameTile } from './mahjongEngine'
import { TILE_DISPLAY } from './tileSet'

interface MahjongTileProps {
  tile: GameTile
  isFree: boolean
  isSelected: boolean
  isHinted: boolean
  onClick: (id: number) => void
}

export function MahjongTile({ tile, isFree, isSelected, isHinted, onClick }: MahjongTileProps) {
  const display = TILE_DISPLAY[tile.tileDefId] || tile.tileDefId.split('-').pop()?.charAt(0).toUpperCase()
  const layerOffset = tile.layer * 2

  return (
    <button
      onClick={() => isFree && onClick(tile.id)}
      className={`absolute w-9 h-12 sm:w-10 sm:h-14 rounded border text-sm sm:text-base font-bold flex items-center justify-center transition-all select-none ${
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
      {display}
    </button>
  )
}
