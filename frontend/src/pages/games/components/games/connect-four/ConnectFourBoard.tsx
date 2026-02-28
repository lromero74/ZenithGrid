/**
 * Connect Four board — renders the 6x7 grid with disc slots.
 */

import type { Board, WinResult } from './connectFourEngine'

interface ConnectFourBoardProps {
  board: Board
  winResult: WinResult | null
  onColumnClick: (col: number) => void
  disabled: boolean
  hoverCol: number | null
  currentPlayer: 'red' | 'yellow'
}

export function ConnectFourBoard({
  board, winResult, onColumnClick, disabled, hoverCol, currentPlayer,
}: ConnectFourBoardProps) {
  const winCells = new Set(winResult?.cells.map(([r, c]) => `${r},${c}`) ?? [])

  return (
    <div className="flex flex-col items-center">
      {/* Column hover indicators */}
      <div className="grid grid-cols-7 gap-1 sm:gap-1.5 mb-1">
        {Array.from({ length: 7 }, (_, c) => (
          <div
            key={c}
            className="w-10 h-10 sm:w-12 sm:h-12 flex items-center justify-center cursor-pointer"
            onClick={() => !disabled && onColumnClick(c)}
            onMouseEnter={() => {}} // handled by parent
          >
            {hoverCol === c && !disabled && (
              <div
                className={`w-8 h-8 sm:w-9 sm:h-9 rounded-full opacity-40 ${
                  currentPlayer === 'red' ? 'bg-red-500' : 'bg-yellow-400'
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Board */}
      <div
        className="grid grid-cols-7 gap-1 sm:gap-1.5 bg-blue-900 p-2 sm:p-3 rounded-lg"
        onMouseLeave={() => {}} // handled by parent
      >
        {board.map((row, r) =>
          row.map((cell, c) => {
            const isWin = winCells.has(`${r},${c}`)
            return (
              <button
                key={`${r}-${c}`}
                onClick={() => !disabled && onColumnClick(c)}
                className={`w-10 h-10 sm:w-12 sm:h-12 rounded-full transition-all duration-200 ${
                  cell === 'red'
                    ? `bg-red-500 ${isWin ? 'ring-2 ring-white animate-pulse' : ''}`
                    : cell === 'yellow'
                    ? `bg-yellow-400 ${isWin ? 'ring-2 ring-white animate-pulse' : ''}`
                    : 'bg-slate-800'
                }`}
                disabled={disabled}
              />
            )
          })
        )}
      </div>
    </div>
  )
}
