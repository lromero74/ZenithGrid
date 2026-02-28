/**
 * 2048 tile grid — renders the 4x4 board with colored tiles.
 */

import type { Board } from './twenFoEiEngine'

const TILE_COLORS: Record<number, string> = {
  0: 'bg-slate-700/50',
  2: 'bg-amber-100 text-slate-800',
  4: 'bg-amber-200 text-slate-800',
  8: 'bg-orange-400 text-white',
  16: 'bg-orange-500 text-white',
  32: 'bg-red-400 text-white',
  64: 'bg-red-600 text-white',
  128: 'bg-yellow-400 text-slate-800',
  256: 'bg-yellow-500 text-slate-800',
  512: 'bg-yellow-600 text-white',
  1024: 'bg-amber-500 text-white',
  2048: 'bg-amber-400 text-white font-bold',
}

function getTileClass(value: number): string {
  return TILE_COLORS[value] || 'bg-purple-600 text-white font-bold'
}

function getFontSize(value: number): string {
  if (value >= 1024) return 'text-lg sm:text-xl'
  if (value >= 128) return 'text-xl sm:text-2xl'
  return 'text-2xl sm:text-3xl'
}

interface TileGridProps {
  board: Board
}

export function TileGrid({ board }: TileGridProps) {
  return (
    <div className="grid grid-cols-4 gap-2 sm:gap-3 bg-slate-800 p-2 sm:p-3 rounded-lg w-[280px] sm:w-[340px]">
      {board.flat().map((value, i) => (
        <div
          key={i}
          className={`flex items-center justify-center h-[60px] sm:h-[72px] rounded-md font-bold transition-all duration-100 ${getTileClass(value)} ${getFontSize(value)}`}
        >
          {value > 0 ? value : ''}
        </div>
      ))}
    </div>
  )
}
