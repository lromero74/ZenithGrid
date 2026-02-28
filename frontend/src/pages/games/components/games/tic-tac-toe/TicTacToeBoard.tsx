/**
 * Tic-Tac-Toe board rendering — 3x3 grid of clickable cells.
 */

import type { Board, WinResult } from './ticTacToeEngine'

interface TicTacToeBoardProps {
  board: Board
  winResult: WinResult | null
  onCellClick: (index: number) => void
  disabled: boolean
}

export function TicTacToeBoard({ board, winResult, onCellClick, disabled }: TicTacToeBoardProps) {
  const winningCells = winResult ? new Set(winResult.line) : new Set<number>()

  return (
    <div className="grid grid-cols-3 gap-1.5 sm:gap-2 w-[260px] sm:w-[320px]">
      {board.map((cell, i) => {
        const isWinning = winningCells.has(i)
        return (
          <button
            key={i}
            onClick={() => onCellClick(i)}
            disabled={disabled || cell !== null}
            className={`
              w-[82px] h-[82px] sm:w-[100px] sm:h-[100px]
              rounded-lg text-3xl sm:text-4xl font-bold
              transition-all duration-150
              flex items-center justify-center
              ${isWinning
                ? 'bg-emerald-900/40 border-2 border-emerald-500'
                : 'bg-slate-700 border-2 border-slate-600 hover:border-slate-500'
              }
              ${cell === null && !disabled
                ? 'cursor-pointer hover:bg-slate-600'
                : 'cursor-default'
              }
              ${cell === 'X' ? 'text-blue-400' : ''}
              ${cell === 'O' ? 'text-red-400' : ''}
            `}
          >
            {cell}
          </button>
        )
      })}
    </div>
  )
}
