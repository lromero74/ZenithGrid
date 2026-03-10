/**
 * Connect Four board — SVG mask cuts real circular holes in the blue frame.
 * Discs sit behind the frame and are visible through the holes.
 *
 * Physics: Holes are ~88% of disc diameter (disc rim hides behind frame).
 * Discs have slight lateral play in the track (~2.5% of cell width) and
 * settle with a small random horizontal offset. Drop animation uses
 * requestAnimationFrame with real gravity + coefficient of restitution
 * bounce (plastic-on-plastic ≈ 0.35).
 */

import { useEffect, useRef, useState, useLayoutEffect, useCallback } from 'react'
import type { Board, WinResult } from './connectFourEngine'

interface ConnectFourBoardProps {
  board: Board
  winResult: WinResult | null
  onColumnClick: (col: number) => void
  disabled: boolean
  hoverCol: number | null
  currentPlayer: 'red' | 'yellow'
  droppingDisc: { row: number; col: number; player: 'red' | 'yellow' } | null
  onDropComplete?: () => void
}

// ── Physics constants ──────────────────────────────────────────────────
const HOLE_RATIO = 0.88   // hole diameter / disc diameter (real ≈ 0.91–0.93, slightly exaggerated)
const MAX_JITTER = 0.025  // max horizontal offset as fraction of cell width (±2.5%)
const GRAVITY = 2500      // px/s² (tuned for visual feel on screen)
const COR = 0.35          // coefficient of restitution — plastic disc on plastic frame
const SETTLE_VEL = 20     // px/s — stop bouncing when velocity falls below this

/** Deterministic pseudo-random jitter for a given (row, col) so settled discs look natural but consistent. */
function discJitter(row: number, col: number, cellSize: number): number {
  const h = Math.sin(row * 131.7 + col * 97.3) * 43758.5453
  const norm = (h - Math.floor(h)) * 2 - 1 // [-1, 1]
  return norm * cellSize * MAX_JITTER
}

// ── Disc styling ───────────────────────────────────────────────────────
/**
 * Modeled after real Connect Four pieces:
 * raised outer rim, concave center, concentric groove, glossy plastic sheen.
 */
const DISC_STYLES = {
  red: {
    background: [
      'radial-gradient(circle at 32% 28%, rgba(255,255,255,0.45) 0%, rgba(255,255,255,0) 28%)',
      'radial-gradient(circle at 50% 50%, #f87171 0%, #ef4444 22%, #dc2626 40%,' +
        ' #991b1b 60%, #b91c1c 66%,' +
        ' #991b1b 78%, #7f1d1d 92%, #581c1c 100%)',
    ].join(', '),
    boxShadow: [
      'inset 0 2px 3px rgba(255,255,255,0.4)',
      'inset 0 -2px 4px rgba(0,0,0,0.5)',
      'inset 2px 0 3px rgba(255,255,255,0.1)',
      'inset -2px 0 3px rgba(0,0,0,0.15)',
      '0 2px 4px rgba(0,0,0,0.5)',
    ].join(', '),
  },
  yellow: {
    background: [
      'radial-gradient(circle at 32% 28%, rgba(255,255,255,0.5) 0%, rgba(255,255,255,0) 28%)',
      'radial-gradient(circle at 50% 50%, #fef08a 0%, #facc15 22%, #eab308 40%,' +
        ' #a16207 60%, #ca8a04 66%,' +
        ' #a16207 78%, #854d0e 92%, #713f12 100%)',
    ].join(', '),
    boxShadow: [
      'inset 0 2px 3px rgba(255,255,255,0.45)',
      'inset 0 -2px 4px rgba(0,0,0,0.45)',
      'inset 2px 0 3px rgba(255,255,255,0.12)',
      'inset -2px 0 3px rgba(0,0,0,0.12)',
      '0 2px 4px rgba(0,0,0,0.5)',
    ].join(', '),
  },
} as const

/** Groove ring overlays rendered inside each disc (placed and dropping). */
function DiscGrooves() {
  return <>
    <span className="absolute inset-[14%] rounded-full border border-black/20 pointer-events-none"
      style={{ boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.25), 0 1px 1px rgba(255,255,255,0.15)' }}
    />
    <span className="absolute inset-[28%] rounded-full border border-white/15 pointer-events-none"
      style={{ boxShadow: 'inset 0 2px 4px rgba(255,255,255,0.2), inset 0 -1px 3px rgba(0,0,0,0.15)' }}
    />
  </>
}

interface HolePos { cx: number; cy: number; r: number }

export function ConnectFourBoard({
  board, winResult, onColumnClick, disabled, hoverCol, currentPlayer, droppingDisc, onDropComplete,
}: ConnectFourBoardProps) {
  const winCells = new Set(winResult?.cells.map(([r, c]) => `${r},${c}`) ?? [])
  const gridRef = useRef<HTMLDivElement>(null)
  const dropDiscRef = useRef<HTMLDivElement>(null)
  const rafRef = useRef<number>(0)
  const [holes, setHoles] = useState<HolePos[]>([])
  const [gridSize, setGridSize] = useState({ w: 0, h: 0 })
  // Track whether a drop is active (for rendering the drop disc element)
  const [dropping, setDropping] = useState(false)

  // Measure cell positions for SVG mask holes (holes are HOLE_RATIO of cell size)
  const measureHoles = useCallback(() => {
    if (!gridRef.current) return
    const grid = gridRef.current
    setGridSize({ w: grid.offsetWidth, h: grid.offsetHeight })
    const newHoles: HolePos[] = []
    for (let i = 0; i < 42; i++) {
      const cell = grid.children[i] as HTMLElement
      if (!cell) continue
      const cx = cell.offsetLeft + cell.offsetWidth / 2
      const cy = cell.offsetTop + cell.offsetHeight / 2
      const r = (cell.offsetWidth / 2) * HOLE_RATIO
      newHoles.push({ cx, cy, r })
    }
    setHoles(newHoles)
  }, [])

  useLayoutEffect(() => {
    measureHoles()
    window.addEventListener('resize', measureHoles)
    return () => window.removeEventListener('resize', measureHoles)
  }, [measureHoles])

  // ── Physics-based drop animation ──────────────────────────────────────
  useEffect(() => {
    if (!droppingDisc || !gridRef.current) {
      setDropping(false)
      return
    }

    const cellIndex = droppingDisc.row * 7 + droppingDisc.col
    const cell = gridRef.current.children[cellIndex] as HTMLElement
    if (!cell) return

    const cellTop = cell.offsetTop
    const cellLeft = cell.offsetLeft
    const cellSize = cell.offsetWidth
    const fallPx = cellTop + cellSize // from above board to target row

    // Target horizontal jitter for this disc's resting position
    const targetJitter = discJitter(droppingDisc.row, droppingDisc.col, cellSize)

    // Position the drop disc element at target cell
    const el = dropDiscRef.current
    if (!el) return

    el.style.left = `${cellLeft}px`
    el.style.top = `${cellTop}px`
    el.style.width = `${cellSize}px`
    el.style.height = `${cellSize}px`
    setDropping(true)

    // Physics state: y is offset from target (negative = above, 0 = resting)
    let y = -fallPx
    let vy = 0
    let x = 0
    let lastTime = performance.now()

    el.style.transform = `translate(${x}px, ${y}px)`

    function step(time: number) {
      if (!el) return
      const dt = Math.min((time - lastTime) / 1000, 0.033) // cap delta for tab-away
      lastTime = time

      // Gravity
      vy += GRAVITY * dt
      y += vy * dt

      // Lerp horizontal toward target jitter (simulates disc finding its resting spot)
      x += (targetJitter - x) * 0.06

      // Bounce at target position (y = 0)
      if (y >= 0) {
        y = 0
        if (Math.abs(vy) * COR < SETTLE_VEL) {
          // Settled — snap to final position
          el.style.transform = `translate(${targetJitter}px, 0px)`
          setTimeout(() => {
            setDropping(false)
            onDropComplete?.()
          }, 30)
          return
        }
        vy = -vy * COR
      }

      el.style.transform = `translate(${x}px, ${y}px)`
      rafRef.current = requestAnimationFrame(step)
    }

    rafRef.current = requestAnimationFrame(step)

    return () => cancelAnimationFrame(rafRef.current)
  }, [droppingDisc, onDropComplete])

  return (
    <div className="flex flex-col items-center">
      {/* Column hover indicators — desktop only */}
      <div className="hidden sm:grid grid-cols-7 gap-2 mb-1" style={{ paddingLeft: 14, paddingRight: 14 }}>
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

      {/* Board — proportioned like real Connect Four:
           ~15% disc diameter gap between holes, ~20% border, bottom shelf */}
      <div className="relative rounded-xl overflow-hidden">

        {/* Disc grid — sits behind the blue frame.
            Gap & padding scaled to ~15% of cell size for realistic rib thickness. */}
        <div
          ref={gridRef}
          className="grid grid-cols-7 gap-[5px] sm:gap-2 rounded-xl relative"
          style={{ padding: '10px 10px 14px 10px' }}
        >
          {board.map((row, r) =>
            row.map((cell, c) => {
              const isWin = winCells.has(`${r},${c}`)
              const isDropping = droppingDisc?.row === r && droppingDisc?.col === c
              const discColor = cell === 'red' ? 'red' : cell === 'yellow' ? 'yellow' : null
              const showDisc = discColor && !isDropping

              // Settled disc gets a small horizontal jitter (track clearance)
              const jitterX = showDisc ? discJitter(r, c, 48) : 0 // 48px cell size approximation; transform is relative

              return (
                <div
                  key={`${r}-${c}`}
                  className={`w-[2.85rem] h-[2.85rem] sm:w-12 sm:h-12 rounded-full relative ${
                    isWin ? 'ring-2 ring-white animate-pulse' : ''
                  }`}
                  style={{
                    ...(showDisc ? DISC_STYLES[discColor] : undefined),
                    ...(showDisc ? { transform: `translateX(${jitterX}px)` } : undefined),
                  }}
                >
                  {showDisc && <DiscGrooves />}
                </div>
              )
            })
          )}

          {/* Dropping disc — physics-driven via ref */}
          <div
            ref={dropDiscRef}
            className="absolute rounded-full pointer-events-none"
            style={{
              display: dropping && droppingDisc ? 'block' : 'none',
              ...(droppingDisc ? DISC_STYLES[droppingDisc.player] : {}),
            }}
          >
            {dropping && droppingDisc && <DiscGrooves />}
          </div>
        </div>

        {/* Blue frame — SVG with masked holes, molded-plastic look */}
        {holes.length === 42 && (
          <svg
            className="absolute inset-0 pointer-events-none rounded-xl"
            width={gridSize.w}
            height={gridSize.h}
            style={{ zIndex: 10 }}
          >
            <defs>
              <mask id="connect4-holes">
                <rect width="100%" height="100%" fill="white" />
                {holes.map((h, i) => (
                  <circle key={i} cx={h.cx} cy={h.cy} r={h.r} fill="black" />
                ))}
              </mask>
              {/* 3D molded-plastic gradient for the blue frame */}
              <linearGradient id="frame-gradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2563eb" />
                <stop offset="8%" stopColor="#1e40af" />
                <stop offset="50%" stopColor="#1e3a8a" />
                <stop offset="92%" stopColor="#1e3a8a" />
                <stop offset="100%" stopColor="#172554" />
              </linearGradient>
            </defs>
            {/* Main blue frame with holes */}
            <rect
              width="100%"
              height="100%"
              rx="12"
              fill="url(#frame-gradient)"
              mask="url(#connect4-holes)"
            />
            {/* Raised rim around each hole — subtle highlight ring */}
            {holes.map((h, i) => (
              <circle key={`rim-${i}`} cx={h.cx} cy={h.cy} r={h.r + 1}
                fill="none" stroke="rgba(96,165,250,0.2)" strokeWidth="1.5"
              />
            ))}
            {/* Inner shadow ring (depth inside the hole) */}
            {holes.map((h, i) => (
              <circle key={`inner-${i}`} cx={h.cx} cy={h.cy} r={h.r - 0.5}
                fill="none" stroke="rgba(0,0,0,0.15)" strokeWidth="1"
              />
            ))}
            {/* Vertical column divider ridges (6 lines between 7 columns) */}
            {[0, 1, 2, 3, 4, 5].map(c => {
              const left = holes[c]   // row 0, col c
              const right = holes[c + 1] // row 0, col c+1
              const x = (left.cx + right.cx) / 2
              const top = holes[0].cy - holes[0].r - 4
              const bot = holes[35].cy + holes[35].r + 4 // row 5, col 0
              return <g key={`vdiv-${c}`}>
                <line x1={x - 0.5} y1={top} x2={x - 0.5} y2={bot}
                  stroke="rgba(96,165,250,0.12)" strokeWidth="1" mask="url(#connect4-holes)" />
                <line x1={x + 0.5} y1={top} x2={x + 0.5} y2={bot}
                  stroke="rgba(0,0,0,0.1)" strokeWidth="1" mask="url(#connect4-holes)" />
              </g>
            })}
            {/* Horizontal row divider ridges (5 lines between 6 rows) */}
            {[0, 1, 2, 3, 4].map(r => {
              const above = holes[r * 7]       // row r, col 0
              const below = holes[(r + 1) * 7] // row r+1, col 0
              const y = (above.cy + below.cy) / 2
              const left = holes[0].cx - holes[0].r - 4
              const right = holes[6].cx + holes[6].r + 4 // col 6
              return <g key={`hdiv-${r}`}>
                <line x1={left} y1={y - 0.5} x2={right} y2={y - 0.5}
                  stroke="rgba(96,165,250,0.08)" strokeWidth="1" mask="url(#connect4-holes)" />
                <line x1={left} y1={y + 0.5} x2={right} y2={y + 0.5}
                  stroke="rgba(0,0,0,0.08)" strokeWidth="1" mask="url(#connect4-holes)" />
              </g>
            })}
          </svg>
        )}

        {/* Click targets on top */}
        <div
          className="absolute inset-0 grid grid-cols-7 gap-[5px] sm:gap-2 rounded-xl"
          style={{ zIndex: 20, padding: '10px 10px 14px 10px' }}
        >
          {Array.from({ length: 42 }, (_, i) => (
            <button
              key={i}
              className="w-[2.85rem] h-[2.85rem] sm:w-12 sm:h-12 rounded-full bg-transparent cursor-pointer"
              onClick={() => !disabled && onColumnClick(i % 7)}
              disabled={disabled}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
