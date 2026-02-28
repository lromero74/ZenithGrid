/**
 * Sudoku 9x9 board — renders cells with conflict/peer/selection highlighting.
 */

import type { SudokuBoard as Board } from './sudokuEngine'

interface SudokuBoardProps {
  board: Board
  solution: Board
  given: boolean[][] // true = pre-filled cell
  selected: [number, number] | null
  conflicts: Set<string>
  notes: Map<string, Set<number>>
  onCellClick: (row: number, col: number) => void
}

export function SudokuBoard({
  board, given, selected, conflicts, notes, onCellClick,
}: SudokuBoardProps) {
  const selectedVal = selected ? board[selected[0]][selected[1]] : 0

  return (
    <div className="grid grid-cols-9 border-2 border-slate-400 w-[315px] sm:w-[405px]">
      {board.map((row, r) =>
        row.map((cell, c) => {
          const isSelected = selected?.[0] === r && selected?.[1] === c
          const isGiven = given[r][c]
          const hasConflict = conflicts.has(`${r},${c}`)
          const isSameValue = cell > 0 && cell === selectedVal
          const isPeer = selected && isInPeerGroup(r, c, selected[0], selected[1])
          const cellNotes = notes.get(`${r},${c}`)

          // Border styles for 3x3 box separation
          let borderClass = 'border border-slate-700/50 '
          if (c % 3 === 0 && c !== 0) borderClass += 'border-l-2 border-l-slate-400 '
          if (r % 3 === 0 && r !== 0) borderClass += 'border-t-2 border-t-slate-400 '

          // Background
          let bgClass = 'bg-slate-800 '
          if (isSelected) bgClass = 'bg-blue-900/50 '
          else if (hasConflict) bgClass = 'bg-red-900/30 '
          else if (isSameValue) bgClass = 'bg-blue-900/20 '
          else if (isPeer) bgClass = 'bg-slate-700/40 '

          // Text color
          let textClass = isGiven ? 'text-slate-200 font-bold' : 'text-blue-400'
          if (hasConflict && !isGiven) textClass = 'text-red-400'

          return (
            <button
              key={`${r}-${c}`}
              onClick={() => onCellClick(r, c)}
              className={`w-[35px] h-[35px] sm:w-[45px] sm:h-[45px] flex items-center justify-center text-sm sm:text-lg transition-colors cursor-pointer ${borderClass}${bgClass}${textClass}`}
            >
              {cell > 0 ? (
                cell
              ) : cellNotes && cellNotes.size > 0 ? (
                <div className="grid grid-cols-3 gap-0 text-[7px] sm:text-[9px] text-slate-500 leading-tight">
                  {[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => (
                    <span key={n} className="text-center">
                      {cellNotes.has(n) ? n : ''}
                    </span>
                  ))}
                </div>
              ) : null}
            </button>
          )
        })
      )}
    </div>
  )
}

function isInPeerGroup(r: number, c: number, sr: number, sc: number): boolean {
  if (r === sr && c === sc) return false
  if (r === sr || c === sc) return true
  const boxR = Math.floor(r / 3)
  const boxC = Math.floor(c / 3)
  const sBoxR = Math.floor(sr / 3)
  const sBoxC = Math.floor(sc / 3)
  return boxR === sBoxR && boxC === sBoxC
}
