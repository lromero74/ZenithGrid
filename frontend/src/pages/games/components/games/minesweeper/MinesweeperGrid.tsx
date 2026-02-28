/**
 * Minesweeper grid — renders the mine board with colored numbers.
 */

import { Flag, Bomb } from 'lucide-react'
import type { MineBoard } from './minesweeperEngine'

const NUMBER_COLORS: Record<number, string> = {
  1: 'text-blue-400',
  2: 'text-green-400',
  3: 'text-red-400',
  4: 'text-blue-700',
  5: 'text-red-800',
  6: 'text-cyan-400',
  7: 'text-slate-300',
  8: 'text-slate-500',
}

interface MinesweeperGridProps {
  board: MineBoard
  onReveal: (row: number, col: number) => void
  onFlag: (row: number, col: number) => void
  gameOver: boolean
  explodedCell: [number, number] | null
}

export function MinesweeperGrid({ board, onReveal, onFlag, gameOver, explodedCell }: MinesweeperGridProps) {
  const cols = board[0]?.length ?? 0
  const longPressRef = { timer: null as ReturnType<typeof setTimeout> | null, fired: false }

  const handleContextMenu = (e: React.MouseEvent, r: number, c: number) => {
    e.preventDefault()
    if (!gameOver) onFlag(r, c)
  }

  const handleTouchStart = (r: number, c: number) => {
    longPressRef.fired = false
    longPressRef.timer = setTimeout(() => {
      longPressRef.fired = true
      if (!gameOver) onFlag(r, c)
    }, 300)
  }

  const handleTouchEnd = (r: number, c: number) => {
    if (longPressRef.timer) clearTimeout(longPressRef.timer)
    if (!longPressRef.fired && !gameOver) onReveal(r, c)
  }

  return (
    <div
      className="inline-grid gap-0 border border-slate-600 rounded"
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
    >
      {board.map((row, r) =>
        row.map((cell, c) => {
          const isExploded = explodedCell?.[0] === r && explodedCell?.[1] === c

          let content: React.ReactNode = null
          let className = 'w-7 h-7 sm:w-8 sm:h-8 flex items-center justify-center text-xs sm:text-sm font-bold border border-slate-700/50 transition-colors select-none '

          if (cell.isRevealed) {
            if (cell.isMine) {
              className += isExploded ? 'bg-red-700' : 'bg-slate-700'
              content = <Bomb className="w-3.5 h-3.5 text-slate-200" />
            } else {
              className += 'bg-slate-800'
              if (cell.adjacentMines > 0) {
                content = <span className={NUMBER_COLORS[cell.adjacentMines]}>{cell.adjacentMines}</span>
              }
            }
          } else if (cell.isFlagged) {
            className += 'bg-slate-600 cursor-pointer'
            content = <Flag className="w-3.5 h-3.5 text-red-400" />
          } else {
            className += 'bg-slate-600 hover:bg-slate-500 cursor-pointer'
          }

          return (
            <button
              key={`${r}-${c}`}
              className={className}
              onClick={() => !gameOver && !cell.isFlagged && onReveal(r, c)}
              onContextMenu={(e) => handleContextMenu(e, r, c)}
              onTouchStart={() => handleTouchStart(r, c)}
              onTouchEnd={(e) => { e.preventDefault(); handleTouchEnd(r, c) }}
              disabled={gameOver}
            >
              {content}
            </button>
          )
        })
      )}
    </div>
  )
}
