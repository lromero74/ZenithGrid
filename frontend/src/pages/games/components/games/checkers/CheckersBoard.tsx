/**
 * Checkers board — renders the 8x8 grid with pieces, selection, and move hints.
 */

import type { Board, Move } from './checkersEngine'

interface CheckersBoardProps {
  board: Board
  selectedPiece: [number, number] | null
  validMoves: Move[]
  onSquareClick: (row: number, col: number) => void
  disabled: boolean
  lastMove: Move | null
}

export function CheckersBoard({
  board, selectedPiece, validMoves, onSquareClick, disabled, lastMove,
}: CheckersBoardProps) {
  const validTargets = new Set(validMoves.map(m => `${m.to[0]},${m.to[1]}`))
  const lastMoveSquares = lastMove
    ? new Set([`${lastMove.from[0]},${lastMove.from[1]}`, `${lastMove.to[0]},${lastMove.to[1]}`])
    : new Set<string>()

  return (
    <div className="grid grid-cols-8 gap-0 rounded-lg overflow-hidden border-2 border-slate-600">
      {board.map((row, r) =>
        row.map((cell, c) => {
          const isDark = (r + c) % 2 === 1
          const isSelected = selectedPiece && selectedPiece[0] === r && selectedPiece[1] === c
          const isValidTarget = validTargets.has(`${r},${c}`)
          const isLastMove = lastMoveSquares.has(`${r},${c}`)

          return (
            <button
              key={`${r}-${c}`}
              onClick={() => !disabled && onSquareClick(r, c)}
              className={`w-10 h-10 sm:w-12 sm:h-12 flex items-center justify-center relative transition-all duration-150
                ${isDark ? 'bg-emerald-800' : 'bg-amber-100'}
                ${isLastMove && isDark ? 'bg-emerald-700' : ''}
                ${!disabled && isDark ? 'cursor-pointer' : 'cursor-default'}
              `}
              disabled={disabled && !cell}
            >
              {/* Valid move dot */}
              {isValidTarget && !cell && (
                <div className="w-3 h-3 sm:w-4 sm:h-4 rounded-full bg-yellow-400/50" />
              )}

              {/* Valid capture target (piece present = capture hint) */}
              {isValidTarget && cell && (
                <div className="absolute inset-0 ring-2 ring-inset ring-yellow-400/60 rounded-sm" />
              )}

              {/* Piece */}
              {cell && (
                <div
                  className={`w-8 h-8 sm:w-9 sm:h-9 rounded-full border-2 flex items-center justify-center
                    transition-transform duration-150
                    ${cell.player === 'red'
                      ? 'bg-red-500 border-red-700 shadow-md shadow-red-900/50'
                      : 'bg-slate-800 border-slate-600 shadow-md shadow-black/50'
                    }
                    ${isSelected ? 'ring-2 ring-yellow-400 scale-110' : ''}
                  `}
                >
                  {cell.isKing && (
                    <span className="text-yellow-400 text-xs sm:text-sm font-bold">&#9813;</span>
                  )}
                </div>
              )}
            </button>
          )
        })
      )}
    </div>
  )
}
