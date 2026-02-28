/**
 * Checkers board — renders the 8x8 grid with pieces, selection, move hints,
 * and smooth slide animation for piece movement.
 */

import { useEffect, useRef, useState } from 'react'
import type { Board, Move, Piece } from './checkersEngine'

interface CheckersBoardProps {
  board: Board
  selectedPiece: [number, number] | null
  validMoves: Move[]
  onSquareClick: (row: number, col: number) => void
  disabled: boolean
  lastMove: Move | null
}

const CELL_MOBILE = 40
const CELL_DESKTOP = 48

function getCellSize() {
  return typeof window !== 'undefined' && window.innerWidth < 640 ? CELL_MOBILE : CELL_DESKTOP
}

interface SlideAnim {
  piece: Piece
  fromRow: number
  fromCol: number
  toRow: number
  toCol: number
  phase: 'start' | 'end'
}

export function CheckersBoard({
  board, selectedPiece, validMoves, onSquareClick, disabled, lastMove,
}: CheckersBoardProps) {
  const validTargets = new Set(validMoves.map(m => `${m.to[0]},${m.to[1]}`))
  const lastMoveSquares = lastMove
    ? new Set([`${lastMove.from[0]},${lastMove.from[1]}`, `${lastMove.to[0]},${lastMove.to[1]}`])
    : new Set<string>()

  const [slide, setSlide] = useState<SlideAnim | null>(null)
  const prevMoveRef = useRef<string | null>(null)
  const cellSize = getCellSize()
  const pieceSize = cellSize * 0.8
  const pieceOffset = (cellSize - pieceSize) / 2

  // Trigger slide animation when lastMove changes
  useEffect(() => {
    if (!lastMove) return
    const moveKey = `${lastMove.from}-${lastMove.to}`
    if (moveKey === prevMoveRef.current) return
    prevMoveRef.current = moveKey

    const piece = board[lastMove.to[0]][lastMove.to[1]]
    if (!piece) return

    // Phase 1: render at "from" position
    setSlide({
      piece, fromRow: lastMove.from[0], fromCol: lastMove.from[1],
      toRow: lastMove.to[0], toCol: lastMove.to[1], phase: 'start',
    })

    // Phase 2: after a frame, transition to "to" position
    const raf = requestAnimationFrame(() => {
      setSlide(s => s ? { ...s, phase: 'end' } : null)
    })

    // Phase 3: clear after transition
    const timer = setTimeout(() => setSlide(null), 300)
    return () => { cancelAnimationFrame(raf); clearTimeout(timer) }
  }, [lastMove, board])

  const renderPiece = (piece: Piece, isSelected: boolean) => (
    <div
      className={`rounded-full border-2 flex items-center justify-center
        ${piece.player === 'red'
          ? 'bg-red-500 border-red-700 shadow-md shadow-red-900/50'
          : 'bg-slate-800 border-slate-600 shadow-md shadow-black/50'
        }
        ${isSelected ? 'ring-2 ring-yellow-400 scale-110' : ''}
      `}
      style={{ width: pieceSize, height: pieceSize }}
    >
      {piece.isKing && (
        <span className="text-yellow-400 text-xs sm:text-sm font-bold">&#9813;</span>
      )}
    </div>
  )

  return (
    <div
      className="relative rounded-lg overflow-hidden border-2 border-slate-600"
      style={{ width: cellSize * 8, height: cellSize * 8 }}
    >
      {/* Squares */}
      {board.map((row, r) =>
        row.map((_, c) => {
          const isDark = (r + c) % 2 === 1
          const isLastMoveSquare = lastMoveSquares.has(`${r},${c}`)
          return (
            <div
              key={`sq-${r}-${c}`}
              className={`absolute
                ${isDark ? 'bg-emerald-800' : 'bg-amber-100'}
                ${isLastMoveSquare && isDark ? 'bg-emerald-700' : ''}
              `}
              style={{
                left: c * cellSize, top: r * cellSize,
                width: cellSize, height: cellSize,
              }}
              onClick={() => !disabled && onSquareClick(r, c)}
            >
              {/* Valid move dot */}
              {validTargets.has(`${r},${c}`) && !board[r][c] && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-3 h-3 sm:w-4 sm:h-4 rounded-full bg-yellow-400/50" />
                </div>
              )}

              {/* Valid capture ring */}
              {validTargets.has(`${r},${c}`) && board[r][c] && (
                <div className="absolute inset-0 ring-2 ring-inset ring-yellow-400/60" />
              )}
            </div>
          )
        })
      )}

      {/* Static pieces (skip the one being animated) */}
      {board.map((row, r) =>
        row.map((cell, c) => {
          if (!cell) return null
          // Hide destination piece while animating (the anim layer renders it)
          if (slide && slide.toRow === r && slide.toCol === c) return null

          const isSelected = !!(selectedPiece && selectedPiece[0] === r && selectedPiece[1] === c)

          return (
            <div
              key={`p-${r}-${c}`}
              className="absolute cursor-pointer"
              style={{
                left: c * cellSize + pieceOffset,
                top: r * cellSize + pieceOffset,
              }}
              onClick={() => !disabled && onSquareClick(r, c)}
            >
              {renderPiece(cell, isSelected)}
            </div>
          )
        })
      )}

      {/* Animated sliding piece */}
      {slide && (
        <div
          className="absolute z-10 pointer-events-none"
          style={{
            left: (slide.phase === 'start' ? slide.fromCol : slide.toCol) * cellSize + pieceOffset,
            top: (slide.phase === 'start' ? slide.fromRow : slide.toRow) * cellSize + pieceOffset,
            transition: slide.phase === 'end' ? 'left 250ms ease-out, top 250ms ease-out' : 'none',
          }}
        >
          {renderPiece(slide.piece, false)}
        </div>
      )}
    </div>
  )
}
