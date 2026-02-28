/**
 * Nonogram grid — renders the puzzle board with row/column clues.
 */

import type { Grid, CellState } from './nonogramEngine'

interface NonogramGridProps {
  grid: Grid
  rowClues: number[][]
  colClues: number[][]
  validatedRows: boolean[]
  validatedCols: boolean[]
  onCellClick: (row: number, col: number) => void
  onCellRightClick: (row: number, col: number) => void
}

const CELL_BG: Record<CellState, string> = {
  filled: 'bg-slate-200',
  empty: 'bg-slate-800',
  unknown: 'bg-slate-700 hover:bg-slate-600 cursor-pointer',
}

export function NonogramGrid({
  grid, rowClues, colClues, validatedRows, validatedCols,
  onCellClick, onCellRightClick,
}: NonogramGridProps) {
  const maxRowClueLen = Math.max(...rowClues.map(c => c.length))
  const maxColClueLen = Math.max(...colClues.map(c => c.length))

  return (
    <div className="inline-flex flex-col">
      {/* Column clues row */}
      <div className="flex">
        {/* Spacer for row clues area */}
        <div style={{ width: `${maxRowClueLen * 24}px` }} />
        {/* Column clue cells */}
        <div className="flex">
          {colClues.map((clue, c) => (
            <div
              key={c}
              className="flex flex-col items-center justify-end w-7 sm:w-8"
              style={{ height: `${maxColClueLen * 16 + 4}px` }}
            >
              {clue.map((n, i) => (
                <span
                  key={i}
                  className={`text-xs leading-tight ${
                    validatedCols[c] ? 'text-emerald-400' : 'text-slate-400'
                  }`}
                >
                  {n}
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Grid rows */}
      {grid.map((row, r) => (
        <div key={r} className="flex">
          {/* Row clues */}
          <div
            className="flex items-center justify-end space-x-1 pr-2"
            style={{ width: `${maxRowClueLen * 24}px` }}
          >
            {rowClues[r].map((n, i) => (
              <span
                key={i}
                className={`text-xs ${
                  validatedRows[r] ? 'text-emerald-400' : 'text-slate-400'
                }`}
              >
                {n}
              </span>
            ))}
          </div>
          {/* Grid cells */}
          <div className="flex">
            {row.map((cell, c) => (
              <button
                key={c}
                className={`w-7 h-7 sm:w-8 sm:h-8 border border-slate-600/50 transition-colors ${CELL_BG[cell]} ${
                  cell === 'empty' ? 'flex items-center justify-center' : ''
                }`}
                onClick={() => onCellClick(r, c)}
                onContextMenu={(e) => { e.preventDefault(); onCellRightClick(r, c) }}
              >
                {cell === 'empty' && (
                  <span className="text-red-400 text-xs font-bold">X</span>
                )}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
