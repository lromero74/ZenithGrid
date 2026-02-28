/**
 * Sub-board — a single 3x3 tic-tac-toe board within the meta-board.
 */

import type { SubBoard as SubBoardType, MetaCell } from './ultimateEngine'

interface SubBoardProps {
  board: SubBoardType
  boardIndex: number
  metaStatus: MetaCell
  isActive: boolean
  onCellClick: (boardIndex: number, cellIndex: number) => void
  disabled: boolean
}

export function SubBoard({ board, boardIndex, metaStatus, isActive, onCellClick, disabled }: SubBoardProps) {
  const isWon = metaStatus === 'X' || metaStatus === 'O'
  const isDraw = metaStatus === 'draw'

  return (
    <div
      className={`relative grid grid-cols-3 gap-0 p-0.5 rounded transition-all ${
        isActive && !disabled ? 'ring-2 ring-blue-400 bg-blue-900/10' : ''
      } ${isDraw ? 'bg-slate-700/30' : ''}`}
    >
      {/* Won overlay */}
      {isWon && (
        <div className={`absolute inset-0 flex items-center justify-center rounded z-10 ${
          metaStatus === 'X' ? 'bg-blue-900/40' : 'bg-red-900/40'
        }`}>
          <span className={`text-3xl sm:text-4xl font-bold ${
            metaStatus === 'X' ? 'text-blue-400' : 'text-red-400'
          }`}>
            {metaStatus}
          </span>
        </div>
      )}

      {board.map((cell, i) => (
        <button
          key={i}
          onClick={() => onCellClick(boardIndex, i)}
          disabled={disabled || cell !== null || metaStatus !== null}
          className={`w-8 h-8 sm:w-10 sm:h-10 flex items-center justify-center text-sm sm:text-lg font-bold border border-slate-700/30 transition-colors ${
            cell === null && isActive && !disabled && metaStatus === null
              ? 'hover:bg-slate-700/50 cursor-pointer'
              : ''
          }`}
        >
          {cell && (
            <span className={cell === 'X' ? 'text-blue-400' : 'text-red-400'}>
              {cell}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
