import { useMemo } from 'react'
import type { BackgammonState, Player } from './backgammonEngine'

interface BackgammonBoardProps {
  state: BackgammonState
  validMoves: { from: number | 'bar'; to: number | 'off' }[]
  selectedPoint: number | 'bar' | null
  onPointClick: (point: number | 'bar') => void
  onBearOff: () => void
  disabled: boolean
}

// Responsive board dimensions
const BOARD_W_MOBILE = 340
const BOARD_W_DESKTOP = 500

function getBoardWidth() {
  return typeof window !== 'undefined' && window.innerWidth < 640
    ? BOARD_W_MOBILE
    : BOARD_W_DESKTOP
}

// Dice face component
function DieFace({ value, size }: { value: number; size: number }) {
  const dotSize = Math.round(size * 0.16)
  const dotPositions: Record<number, [number, number][]> = {
    1: [[50, 50]],
    2: [[28, 28], [72, 72]],
    3: [[28, 28], [50, 50], [72, 72]],
    4: [[28, 28], [72, 28], [28, 72], [72, 72]],
    5: [[28, 28], [72, 28], [50, 50], [28, 72], [72, 72]],
    6: [[28, 28], [72, 28], [28, 50], [72, 50], [28, 72], [72, 72]],
  }

  return (
    <div
      className="relative rounded-md bg-white shadow-md border border-slate-300"
      style={{ width: size, height: size }}
    >
      {(dotPositions[value] ?? []).map(([x, y], i) => (
        <div
          key={i}
          className="absolute rounded-full bg-slate-800"
          style={{
            width: dotSize,
            height: dotSize,
            left: `${x}%`,
            top: `${y}%`,
            transform: 'translate(-50%, -50%)',
          }}
        />
      ))}
    </div>
  )
}

// Checker (single piece)
function Checker({ player, size }: { player: Player; size: number }) {
  return (
    <div
      className={`rounded-full border-2 shadow-sm flex-shrink-0 ${
        player === 'white'
          ? 'bg-white border-slate-300'
          : 'bg-amber-700 border-amber-900'
      }`}
      style={{ width: size, height: size }}
    />
  )
}

export function BackgammonBoard({
  state, validMoves, selectedPoint, onPointClick, onBearOff, disabled,
}: BackgammonBoardProps) {
  const boardWidth = getBoardWidth()
  const barWidth = Math.round(boardWidth * 0.06)
  const bearOffWidth = Math.round(boardWidth * 0.06)
  const playableWidth = boardWidth - barWidth - bearOffWidth * 2
  const pointWidth = Math.round(playableWidth / 12)
  const boardHeight = Math.round(boardWidth * 0.72)
  const halfHeight = Math.round(boardHeight / 2)
  const triangleHeight = Math.round(halfHeight * 0.82)
  const checkerSize = Math.round(pointWidth * 0.8)
  const checkerGap = 2

  const validTargetSet = useMemo(
    () => new Set(validMoves.map(m => String(m.to))),
    [validMoves],
  )

  const validFromSet = useMemo(
    () => new Set(validMoves.map(m => String(m.from))),
    [validMoves],
  )

  const dieSize = Math.round(boardWidth * 0.06)

  // Build layout: which points go where
  // Top row (left to right): 12,13,14,15,16,17 | BAR | 18,19,20,21,22,23
  // Bot row (left to right): 11,10,9,8,7,6     | BAR | 5,4,3,2,1,0
  const topPoints = [12, 13, 14, 15, 16, 17, -1, 18, 19, 20, 21, 22, 23] // -1 = bar
  const botPoints = [11, 10, 9, 8, 7, 6, -1, 5, 4, 3, 2, 1, 0]

  function renderTriangle(
    pointIndex: number,
    position: number,
    isTop: boolean,
    leftOffset: number,
  ) {
    const pt = state.points[pointIndex]
    const isEven = position % 2 === 0
    const color1 = 'rgb(6, 95, 70)' // emerald-800
    const color2 = 'rgb(127, 29, 29)' // red-900
    const triangleColor = isEven ? color1 : color2

    const isSelected = selectedPoint === pointIndex
    const isValidTarget = validTargetSet.has(String(pointIndex))
    const isValidSource = validFromSet.has(String(pointIndex))

    // Render triangle using CSS clip-path
    const clipPath = isTop
      ? 'polygon(0% 0%, 100% 0%, 50% 100%)'
      : 'polygon(50% 0%, 100% 100%, 0% 100%)'

    // Stack checkers from the edge inward
    const maxVisible = 5
    const visible = Math.min(pt.count, maxVisible)

    return (
      <div
        key={`pt-${pointIndex}`}
        className="absolute cursor-pointer"
        style={{
          left: leftOffset,
          top: isTop ? 0 : halfHeight,
          width: pointWidth,
          height: halfHeight,
        }}
        onClick={() => !disabled && onPointClick(pointIndex)}
      >
        {/* Triangle wedge */}
        <div
          className={`absolute ${isSelected ? 'opacity-90' : ''}`}
          style={{
            left: 0,
            top: isTop ? 0 : halfHeight - triangleHeight,
            width: pointWidth,
            height: triangleHeight,
            clipPath,
            backgroundColor: triangleColor,
          }}
        />

        {/* Selection highlight */}
        {isSelected && (
          <div
            className="absolute border-2 border-yellow-400 rounded-sm z-10"
            style={{ left: 0, top: 0, width: pointWidth, height: halfHeight }}
          />
        )}

        {/* Valid move indicator */}
        {isValidTarget && !isSelected && (
          <div
            className="absolute z-10 flex items-center justify-center"
            style={{
              left: (pointWidth - checkerSize) / 2,
              [isTop ? 'top' : 'bottom']: 4,
              width: checkerSize,
              height: checkerSize,
            }}
          >
            <div
              className="rounded-full bg-yellow-400/50"
              style={{ width: checkerSize * 0.5, height: checkerSize * 0.5 }}
            />
          </div>
        )}

        {/* Checkers */}
        {pt.player && Array.from({ length: visible }).map((_, i) => {
          const offset = isTop
            ? i * (checkerSize + checkerGap)
            : halfHeight - (i + 1) * (checkerSize + checkerGap)
          return (
            <div
              key={i}
              className={`absolute z-20 transition-transform duration-300 ease-out ${
                isValidSource && !disabled ? 'hover:scale-110' : ''
              }`}
              style={{
                left: (pointWidth - checkerSize) / 2,
                top: offset,
              }}
            >
              <Checker player={pt.player!} size={checkerSize} />
            </div>
          )
        })}

        {/* Count badge for 6+ */}
        {pt.count > maxVisible && pt.player && (
          <div
            className="absolute z-30 flex items-center justify-center text-xs font-bold bg-slate-900 text-white rounded-full border border-slate-600"
            style={{
              width: checkerSize * 0.6,
              height: checkerSize * 0.6,
              left: (pointWidth - checkerSize * 0.6) / 2,
              [isTop ? 'top' : 'bottom']: (maxVisible - 1) * (checkerSize + checkerGap) + checkerSize * 0.2,
            }}
          >
            {pt.count}
          </div>
        )}

        {/* Point number label */}
        <div
          className="absolute text-slate-500 text-xs text-center select-none"
          style={{
            width: pointWidth,
            left: 0,
            [isTop ? 'bottom' : 'top']: -16,
          }}
        >
          {pointIndex}
        </div>
      </div>
    )
  }

  function renderBar() {
    const barLeft = bearOffWidth + 6 * pointWidth
    const whiteOnBar = state.bar.white
    const brownOnBar = state.bar.brown

    return (
      <div
        className="absolute bg-amber-800 z-10"
        style={{
          left: barLeft,
          top: 0,
          width: barWidth,
          height: boardHeight,
        }}
      >
        {/* Brown checkers on bar (top half) */}
        {brownOnBar > 0 && (
          <div
            className={`absolute cursor-pointer ${selectedPoint === 'bar' && state.currentPlayer === 'brown' ? 'ring-2 ring-yellow-400 rounded' : ''}`}
            style={{ left: (barWidth - checkerSize) / 2, top: 8 }}
            onClick={() => !disabled && state.currentPlayer === 'brown' && onPointClick('bar')}
          >
            <Checker player="brown" size={checkerSize} />
            {brownOnBar > 1 && (
              <div className="absolute -top-1 -right-1 w-4 h-4 bg-slate-900 text-white text-xs rounded-full flex items-center justify-center border border-slate-600">
                {brownOnBar}
              </div>
            )}
          </div>
        )}

        {/* White checkers on bar (bottom half) */}
        {whiteOnBar > 0 && (
          <div
            className={`absolute cursor-pointer ${selectedPoint === 'bar' && state.currentPlayer === 'white' ? 'ring-2 ring-yellow-400 rounded' : ''}`}
            style={{ left: (barWidth - checkerSize) / 2, bottom: 8 }}
            onClick={() => !disabled && state.currentPlayer === 'white' && onPointClick('bar')}
          >
            <Checker player="white" size={checkerSize} />
            {whiteOnBar > 1 && (
              <div className="absolute -top-1 -right-1 w-4 h-4 bg-slate-900 text-white text-xs rounded-full flex items-center justify-center border border-slate-600">
                {whiteOnBar}
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  function renderBearOff() {
    const canBearOffNow = validTargetSet.has('off')
    const rightEdge = boardWidth - bearOffWidth

    return (
      <>
        {/* Right bear-off tray (brown bears off at top-right, white at bot-right) */}
        <div
          className={`absolute bg-amber-950 border-l border-amber-700 flex flex-col items-center justify-end pb-1 gap-0.5
            ${canBearOffNow && state.currentPlayer === 'brown' ? 'cursor-pointer ring-2 ring-yellow-400 ring-inset' : ''}
          `}
          style={{ left: rightEdge, top: 0, width: bearOffWidth, height: halfHeight }}
          onClick={() => canBearOffNow && state.currentPlayer === 'brown' && !disabled && onBearOff()}
        >
          {state.borneOff.brown > 0 && (
            <div className="text-xs text-amber-300 font-bold">{state.borneOff.brown}</div>
          )}
        </div>
        <div
          className={`absolute bg-amber-950 border-l border-amber-700 flex flex-col items-center justify-start pt-1 gap-0.5
            ${canBearOffNow && state.currentPlayer === 'white' ? 'cursor-pointer ring-2 ring-yellow-400 ring-inset' : ''}
          `}
          style={{ left: rightEdge, top: halfHeight, width: bearOffWidth, height: halfHeight }}
          onClick={() => canBearOffNow && state.currentPlayer === 'white' && !disabled && onBearOff()}
        >
          {state.borneOff.white > 0 && (
            <div className="text-xs text-white font-bold">{state.borneOff.white}</div>
          )}
        </div>
      </>
    )
  }

  // Dice display
  const unusedDice = state.dice.filter((_, i) => !state.usedDice[i])

  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className="relative rounded-lg overflow-hidden border-2 border-amber-700 bg-amber-900"
        style={{ width: boardWidth, height: boardHeight }}
      >
        {/* Left bear-off tray (decorative, scoring area) */}
        <div
          className="absolute bg-amber-950 border-r border-amber-700"
          style={{ left: 0, top: 0, width: bearOffWidth, height: boardHeight }}
        />

        {/* Render triangles - top row */}
        {topPoints.map((ptIdx, pos) => {
          if (ptIdx === -1) return null // skip bar placeholder
          const adjustedPos = pos > 6 ? pos - 1 : pos // adjust for bar gap
          const leftOffset = bearOffWidth + adjustedPos * pointWidth + (pos > 6 ? barWidth : 0)
          return renderTriangle(ptIdx, pos, true, leftOffset)
        })}

        {/* Render triangles - bottom row */}
        {botPoints.map((ptIdx, pos) => {
          if (ptIdx === -1) return null
          const adjustedPos = pos > 6 ? pos - 1 : pos
          const leftOffset = bearOffWidth + adjustedPos * pointWidth + (pos > 6 ? barWidth : 0)
          return renderTriangle(ptIdx, pos, false, leftOffset)
        })}

        {/* Bar */}
        {renderBar()}

        {/* Bear-off trays */}
        {renderBearOff()}

        {/* Center line */}
        <div
          className="absolute bg-amber-800/50"
          style={{ left: bearOffWidth, top: halfHeight - 1, width: playableWidth + barWidth, height: 2 }}
        />
      </div>

      {/* Dice display */}
      {unusedDice.length > 0 && state.gamePhase === 'moving' && (
        <div className="flex gap-2 items-center">
          {unusedDice.map((die, i) => (
            <DieFace key={i} value={die} size={dieSize} />
          ))}
        </div>
      )}
    </div>
  )
}
