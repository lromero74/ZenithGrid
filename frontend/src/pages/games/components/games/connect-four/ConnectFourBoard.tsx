/**
 * Connect Four board — renders the 6x7 grid with disc slots.
 * Discs animate falling under gravity with a bounce on landing.
 */

import { useEffect, useRef } from 'react'
import type { Board, WinResult } from './connectFourEngine'

interface ConnectFourBoardProps {
  board: Board
  winResult: WinResult | null
  onColumnClick: (col: number) => void
  disabled: boolean
  hoverCol: number | null
  currentPlayer: 'red' | 'yellow'
  droppingDisc: { row: number; col: number; player: 'red' | 'yellow' } | null
}

export function ConnectFourBoard({
  board, winResult, onColumnClick, disabled, hoverCol, currentPlayer, droppingDisc,
}: ConnectFourBoardProps) {
  const winCells = new Set(winResult?.cells.map(([r, c]) => `${r},${c}`) ?? [])
  const prevBoardRef = useRef<Board>(board)

  useEffect(() => {
    prevBoardRef.current = board
  }, [board])

  return (
    <div className="flex flex-col items-center">
      {/* Column hover indicators — desktop only */}
      <div className="hidden sm:grid grid-cols-7 gap-1.5 mb-1">
        {Array.from({ length: 7 }, (_, c) => (
          <div
            key={c}
            className="w-12 h-12 flex items-center justify-center cursor-pointer"
            onClick={() => !disabled && onColumnClick(c)}
          >
            {hoverCol === c && !disabled && (
              <div
                className="w-9 h-9 rounded-full opacity-50"
                style={{
                  background: currentPlayer === 'red'
                    ? 'radial-gradient(circle at 38% 35%, #ff8a8a, #ef4444 50%, #b91c1c)'
                    : 'radial-gradient(circle at 38% 35%, #fef08a, #facc15 50%, #ca8a04)',
                }}
              />
            )}
          </div>
        ))}
      </div>

      {/* Board */}
      <div
        className="grid grid-cols-7 gap-[3px] sm:gap-1.5 bg-blue-900 p-1.5 sm:p-3 rounded-lg relative"
      >
        {board.map((row, r) =>
          row.map((cell, c) => {
            const isWin = winCells.has(`${r},${c}`)
            const isDropping = droppingDisc?.row === r && droppingDisc?.col === c

            // Calculate drop distance in cell units for the animation
            const dropDistance = isDropping ? r + 1 : 0
            // Duration scales with distance for realistic gravity feel
            const dropDuration = isDropping ? 0.12 + dropDistance * 0.06 : 0

            const discStyle: React.CSSProperties = cell === 'red' ? {
              background: 'radial-gradient(circle at 38% 35%, #ff8a8a 0%, #ef4444 40%, #b91c1c 85%, #7f1d1d 100%)',
              boxShadow: 'inset 0 2px 4px rgba(255,255,255,0.25), inset 0 -2px 4px rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.4)',
            } : cell === 'yellow' ? {
              background: 'radial-gradient(circle at 38% 35%, #fef08a 0%, #facc15 40%, #ca8a04 85%, #a16207 100%)',
              boxShadow: 'inset 0 2px 4px rgba(255,255,255,0.3), inset 0 -2px 4px rgba(0,0,0,0.25), 0 1px 3px rgba(0,0,0,0.4)',
            } : {}

            const animStyle: React.CSSProperties = isDropping ? {
              animation: `disc-drop ${dropDuration}s cubic-bezier(0.2, 0, 0.8, 1) forwards`,
              ['--drop-from' as string]: `-${dropDistance * 100}%`,
            } : {}

            return (
              <button
                key={`${r}-${c}`}
                onClick={() => !disabled && onColumnClick(c)}
                className={`w-[2.85rem] h-[2.85rem] sm:w-12 sm:h-12 rounded-full relative ${
                  cell
                    ? `${isWin ? 'ring-2 ring-white animate-pulse' : ''}`
                    : 'bg-slate-800'
                }`}
                style={{ ...discStyle, ...animStyle }}
                disabled={disabled}
              >
                {cell && (
                  <span className="absolute inset-[22%] rounded-full border border-white/10 pointer-events-none"
                    style={{ boxShadow: 'inset 0 1px 2px rgba(255,255,255,0.15)' }}
                  />
                )}
              </button>
            )
          })
        )}
      </div>

      {/* Drop animation keyframes */}
      <style>{`
        @keyframes disc-drop {
          0% {
            transform: translateY(var(--drop-from));
            opacity: 0.8;
          }
          60% {
            transform: translateY(0);
            opacity: 1;
          }
          75% {
            transform: translateY(-8%);
          }
          90% {
            transform: translateY(0);
          }
          95% {
            transform: translateY(-3%);
          }
          100% {
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  )
}
