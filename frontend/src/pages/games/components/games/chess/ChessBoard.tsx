/**
 * Chess board — renders the 8x8 grid with pieces, selection, move hints,
 * check highlighting, and smooth slide animation for piece movement.
 */

import { useEffect, useRef, useState } from 'react'
import { getPieceSymbol, type ChessState, type Move, type Piece } from './chessEngine'

interface ChessBoardProps {
  state: ChessState
  selectedSquare: [number, number] | null
  validMoves: Move[]
  onSquareClick: (row: number, col: number) => void
  disabled: boolean
  lastMove: Move | null
  inCheck: boolean
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

export function ChessBoard({
  state, selectedSquare, validMoves, onSquareClick, disabled, lastMove, inCheck,
}: ChessBoardProps) {
  const validTargets = new Set(validMoves.map(m => `${m.toRow},${m.toCol}`))
  const lastMoveSquares = lastMove
    ? new Set([`${lastMove.fromRow},${lastMove.fromCol}`, `${lastMove.toRow},${lastMove.toCol}`])
    : new Set<string>()

  const [slide, setSlide] = useState<SlideAnim | null>(null)
  const prevMoveRef = useRef<string | null>(null)
  const cellSize = getCellSize()
  const pieceSize = cellSize * 0.85

  // Find king position for check highlight
  const kingPos = inCheck
    ? (() => {
        for (let r = 0; r < 8; r++)
          for (let c = 0; c < 8; c++)
            if (state.board[r][c]?.type === 'king' && state.board[r][c]?.color === state.currentPlayer)
              return `${r},${c}`
        return ''
      })()
    : ''

  // Trigger slide animation when lastMove changes
  useEffect(() => {
    if (!lastMove) return
    const moveKey = `${lastMove.fromRow},${lastMove.fromCol}-${lastMove.toRow},${lastMove.toCol}`
    if (moveKey === prevMoveRef.current) return
    prevMoveRef.current = moveKey

    const piece = state.board[lastMove.toRow][lastMove.toCol]
    if (!piece) return

    setSlide({
      piece, fromRow: lastMove.fromRow, fromCol: lastMove.fromCol,
      toRow: lastMove.toRow, toCol: lastMove.toCol, phase: 'start',
    })

    const raf = requestAnimationFrame(() => {
      setSlide(s => s ? { ...s, phase: 'end' } : null)
    })

    const timer = setTimeout(() => setSlide(null), 300)
    return () => { cancelAnimationFrame(raf); clearTimeout(timer) }
  }, [lastMove, state.board])

  const renderPiece = (piece: Piece) => (
    <span
      className="select-none leading-none"
      style={{ fontSize: pieceSize * 0.65 }}
    >
      {getPieceSymbol(piece)}
    </span>
  )

  return (
    <div
      className="relative rounded-lg overflow-hidden border-2 border-slate-600"
      style={{ width: cellSize * 8, height: cellSize * 8 }}
    >
      {/* Squares */}
      {state.board.map((row, r) =>
        row.map((_, c) => {
          const isDark = (r + c) % 2 === 1
          const isSelected = selectedSquare && selectedSquare[0] === r && selectedSquare[1] === c
          const isLastMove = lastMoveSquares.has(`${r},${c}`)
          const isKingCheck = kingPos === `${r},${c}`
          const isValidTarget = validTargets.has(`${r},${c}`)
          const hasCapture = isValidTarget && state.board[r][c] !== null

          return (
            <div
              key={`sq-${r}-${c}`}
              className={`absolute flex items-center justify-center cursor-pointer
                ${isDark ? 'bg-emerald-800' : 'bg-amber-100'}
                ${isSelected ? 'ring-2 ring-inset ring-yellow-400' : ''}
                ${isLastMove && isDark ? 'bg-emerald-700' : ''}
                ${isLastMove && !isDark ? 'bg-amber-200' : ''}
                ${isKingCheck ? 'bg-red-500/40' : ''}
              `}
              style={{
                left: c * cellSize, top: r * cellSize,
                width: cellSize, height: cellSize,
              }}
              onClick={() => !disabled && onSquareClick(r, c)}
            >
              {/* Valid move dot */}
              {isValidTarget && !hasCapture && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-3 h-3 sm:w-4 sm:h-4 rounded-full bg-yellow-400/50" />
                </div>
              )}

              {/* Valid capture ring */}
              {hasCapture && (
                <div className="absolute inset-0 ring-2 ring-inset ring-yellow-400/60 rounded-sm" />
              )}
            </div>
          )
        })
      )}

      {/* Static pieces (skip the one being animated) */}
      {state.board.map((row, r) =>
        row.map((cell, c) => {
          if (!cell) return null
          if (slide && slide.toRow === r && slide.toCol === c) return null

          return (
            <div
              key={`p-${r}-${c}`}
              className="absolute flex items-center justify-center cursor-pointer pointer-events-none"
              style={{
                left: c * cellSize,
                top: r * cellSize,
                width: cellSize,
                height: cellSize,
              }}
            >
              {renderPiece(cell)}
            </div>
          )
        })
      )}

      {/* Animated sliding piece */}
      {slide && (
        <div
          className="absolute z-10 pointer-events-none flex items-center justify-center"
          style={{
            left: (slide.phase === 'start' ? slide.fromCol : slide.toCol) * cellSize,
            top: (slide.phase === 'start' ? slide.fromRow : slide.toRow) * cellSize,
            width: cellSize,
            height: cellSize,
            transition: slide.phase === 'end' ? 'left 250ms ease-out, top 250ms ease-out' : 'none',
          }}
        >
          {renderPiece(slide.piece)}
        </div>
      )}
    </div>
  )
}
