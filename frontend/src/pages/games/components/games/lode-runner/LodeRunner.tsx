/**
 * Lode Runner — canvas-based puzzle-platformer.
 *
 * Features: keyboard + mobile d-pad controls, 10 progressive levels,
 * gold collection, brick digging, guard AI, responsive scaling.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import {
  loadLevel, updateGame, nextLevel,
  GAME_WIDTH, GAME_HEIGHT, CELL, COLS, ROWS,
  Tile,
  type GameState, type Input, type Player, type Guard,
} from './lodeRunnerEngine'
import { LEVEL_NAMES } from './lodeRunnerLevels'
import type { GameStatus } from '../../../types'

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

const C_BG = '#0a0a1a'
const C_BRICK = '#8b5e3c'
const C_BRICK_MORTAR = '#6b4226'
const C_SOLID = '#4a4a5a'
const C_SOLID_EDGE = '#3a3a4a'
const C_LADDER = '#c89632'
const C_BAR = '#9ca3af'
const C_GOLD = '#fbbf24'
const C_GOLD_SHINE = '#fde68a'
const C_PLAYER = '#3b82f6'
const C_PLAYER_LIGHT = '#60a5fa'
const C_GUARD = '#ef4444'
const C_GUARD_DARK = '#b91c1c'
const C_HIDDEN = '#22c55e'
const C_HUD = '#ffffff'

// ---------------------------------------------------------------------------
// Drawing helpers
// ---------------------------------------------------------------------------

function drawBackground(ctx: CanvasRenderingContext2D): void {
  ctx.fillStyle = C_BG
  ctx.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT)
}

function drawTiles(ctx: CanvasRenderingContext2D, gs: GameState): void {
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const tile = gs.grid[r][c]
      const x = c * CELL
      const y = r * CELL

      switch (tile) {
        case Tile.Brick: {
          // Check if dug
          const dug = gs.dugBricks.find(db => db.col === c && db.row === r)
          if (dug) {
            if (dug.phase === 'filling') {
              // Partially filling in
              const frac = 1 - dug.timer / 0.6
              ctx.fillStyle = C_BRICK
              ctx.fillRect(x, y + CELL * (1 - frac), CELL, CELL * frac)
            }
            // Open dug hole — draw nothing (empty)
          } else {
            // Normal brick
            ctx.fillStyle = C_BRICK
            ctx.fillRect(x, y, CELL, CELL)
            // Mortar lines
            ctx.strokeStyle = C_BRICK_MORTAR
            ctx.lineWidth = 1
            ctx.strokeRect(x + 0.5, y + 0.5, CELL - 1, CELL - 1)
            // Horizontal mortar
            ctx.beginPath()
            ctx.moveTo(x, y + CELL / 2)
            ctx.lineTo(x + CELL, y + CELL / 2)
            ctx.stroke()
          }
          break
        }
        case Tile.Solid:
          ctx.fillStyle = C_SOLID
          ctx.fillRect(x, y, CELL, CELL)
          ctx.strokeStyle = C_SOLID_EDGE
          ctx.lineWidth = 1
          ctx.strokeRect(x + 0.5, y + 0.5, CELL - 1, CELL - 1)
          // Cross pattern
          ctx.beginPath()
          ctx.moveTo(x, y)
          ctx.lineTo(x + CELL, y + CELL)
          ctx.moveTo(x + CELL, y)
          ctx.lineTo(x, y + CELL)
          ctx.stroke()
          break
        case Tile.Ladder:
          ctx.strokeStyle = C_LADDER
          ctx.lineWidth = 2
          // Sides
          ctx.beginPath()
          ctx.moveTo(x + 4, y)
          ctx.lineTo(x + 4, y + CELL)
          ctx.moveTo(x + CELL - 4, y)
          ctx.lineTo(x + CELL - 4, y + CELL)
          ctx.stroke()
          // Rungs
          ctx.lineWidth = 1.5
          for (let ry = 4; ry < CELL; ry += 6) {
            ctx.beginPath()
            ctx.moveTo(x + 4, y + ry)
            ctx.lineTo(x + CELL - 4, y + ry)
            ctx.stroke()
          }
          break
        case Tile.Bar:
          ctx.strokeStyle = C_BAR
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.moveTo(x, y + CELL / 3)
          ctx.lineTo(x + CELL, y + CELL / 3)
          ctx.stroke()
          // Grip dots
          ctx.fillStyle = C_BAR
          ctx.beginPath()
          ctx.arc(x + CELL / 2, y + CELL / 3, 2, 0, Math.PI * 2)
          ctx.fill()
          break
        case Tile.Hidden:
          if (gs.escapeRevealed) {
            // Flashing green ladder
            const alpha = 0.6 + 0.4 * Math.sin(gs.animTime * 6)
            ctx.strokeStyle = C_HIDDEN
            ctx.globalAlpha = alpha
            ctx.lineWidth = 2
            ctx.beginPath()
            ctx.moveTo(x + 4, y)
            ctx.lineTo(x + 4, y + CELL)
            ctx.moveTo(x + CELL - 4, y)
            ctx.lineTo(x + CELL - 4, y + CELL)
            ctx.stroke()
            ctx.lineWidth = 1.5
            for (let ry = 4; ry < CELL; ry += 6) {
              ctx.beginPath()
              ctx.moveTo(x + 4, y + ry)
              ctx.lineTo(x + CELL - 4, y + ry)
              ctx.stroke()
            }
            ctx.globalAlpha = 1
          }
          break
      }
    }
  }
}

function drawGold(ctx: CanvasRenderingContext2D, gs: GameState): void {
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      if (!gs.goldMap[r][c]) continue
      const cx = c * CELL + CELL / 2
      const cy = r * CELL + CELL / 2
      const sz = CELL / 2 - 2
      // Gold nugget
      ctx.fillStyle = C_GOLD
      ctx.beginPath()
      ctx.moveTo(cx, cy - sz)
      ctx.lineTo(cx + sz, cy)
      ctx.lineTo(cx, cy + sz)
      ctx.lineTo(cx - sz, cy)
      ctx.closePath()
      ctx.fill()
      // Shine
      ctx.fillStyle = C_GOLD_SHINE
      ctx.beginPath()
      ctx.arc(cx - 2, cy - 2, 2, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}

function drawPlayer(ctx: CanvasRenderingContext2D, p: Player): void {
  if (!p.alive) return
  const half = CELL / 2 - 2
  ctx.save()

  // Body
  ctx.fillStyle = C_PLAYER
  ctx.fillRect(p.x - half, p.y - half, half * 2, half * 2)

  // Head
  ctx.fillStyle = C_PLAYER_LIGHT
  ctx.beginPath()
  ctx.arc(p.x, p.y - half - 3, 4, 0, Math.PI * 2)
  ctx.fill()

  // Direction indicator (small arm)
  const armDir = p.facingLeft ? -1 : 1
  ctx.strokeStyle = C_PLAYER_LIGHT
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(p.x, p.y)
  ctx.lineTo(p.x + armDir * (half + 2), p.y - 2)
  ctx.stroke()

  ctx.restore()
}

function drawGuard(ctx: CanvasRenderingContext2D, g: Guard, animTime: number): void {
  if (g.state === 'dead') return
  const half = CELL / 2 - 2

  ctx.save()

  if (g.state === 'trapped') {
    // Flash when trapped
    ctx.globalAlpha = 0.5 + 0.3 * Math.sin(animTime * 8)
  }

  // Body
  ctx.fillStyle = C_GUARD
  ctx.fillRect(g.x - half, g.y - half, half * 2, half * 2)

  // Head
  ctx.fillStyle = C_GUARD_DARK
  ctx.beginPath()
  ctx.arc(g.x, g.y - half - 3, 4, 0, Math.PI * 2)
  ctx.fill()

  // Eyes
  ctx.fillStyle = '#fff'
  ctx.beginPath()
  ctx.arc(g.x - 2, g.y - half - 3, 1.5, 0, Math.PI * 2)
  ctx.fill()
  ctx.beginPath()
  ctx.arc(g.x + 2, g.y - half - 3, 1.5, 0, Math.PI * 2)
  ctx.fill()

  // Gold indicator
  if (g.carriesGold) {
    ctx.fillStyle = C_GOLD
    ctx.beginPath()
    ctx.arc(g.x, g.y + half + 2, 3, 0, Math.PI * 2)
    ctx.fill()
  }

  ctx.restore()
}

function drawHUD(ctx: CanvasRenderingContext2D, gs: GameState): void {
  ctx.fillStyle = C_HUD
  ctx.font = 'bold 11px monospace'
  ctx.textBaseline = 'top'

  // Score
  ctx.textAlign = 'left'
  ctx.fillText(`SCORE ${gs.score}`, 4, 2)

  // Level
  ctx.textAlign = 'center'
  ctx.fillText(`LVL ${gs.level}`, GAME_WIDTH / 2, 2)

  // Gold remaining
  ctx.textAlign = 'right'
  ctx.fillStyle = C_GOLD
  ctx.fillText(`${'*'.repeat(Math.min(gs.goldRemaining, 10))}`, GAME_WIDTH - 40, 2)

  // Lives
  ctx.fillStyle = C_PLAYER
  ctx.fillText(`${'@'.repeat(gs.lives)}`, GAME_WIDTH - 4, 2)
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const emptyInput: Input = {
  left: false, right: false, up: false, down: false,
  digLeft: false, digRight: false,
}

export default function LodeRunner() {
  const { getHighScore, saveScore } = useGameScores()
  const bestScore = getHighScore('lode-runner') ?? 0

  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [score, setScore] = useState(0)
  const [level, setLevel] = useState(1)
  const [lives, setLives] = useState(3)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const scaleRef = useRef(1)

  const gsRef = useRef<GameState>(loadLevel(1))
  const gameStatusRef = useRef<GameStatus>('idle')
  const animFrameRef = useRef(0)
  const lastTimeRef = useRef(0)

  // Input tracking
  const keysRef = useRef<Set<string>>(new Set())
  // Track single-press dig actions (consumed once per press)
  const digLeftPressedRef = useRef(false)
  const digRightPressedRef = useRef(false)
  // Mobile d-pad input
  const mobileInputRef = useRef<Input>({ ...emptyInput })

  // -------------------------------------------------------------------------
  // Draw
  // -------------------------------------------------------------------------

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const scale = scaleRef.current
    canvas.width = Math.floor(GAME_WIDTH * scale)
    canvas.height = Math.floor(GAME_HEIGHT * scale)

    ctx.save()
    ctx.scale(scale, scale)

    const gs = gsRef.current

    drawBackground(ctx)
    drawTiles(ctx, gs)
    drawGold(ctx, gs)

    // Draw guards
    for (const g of gs.guards) {
      drawGuard(ctx, g, gs.animTime)
    }

    // Draw player
    drawPlayer(ctx, gs.player)

    // HUD
    drawHUD(ctx, gs)

    ctx.restore()
  }, [])

  // -------------------------------------------------------------------------
  // Game loop
  // -------------------------------------------------------------------------

  const tick = useCallback((timestamp: number) => {
    if (gameStatusRef.current !== 'playing') return

    const dt = Math.min((timestamp - lastTimeRef.current) / 1000, 0.05)
    lastTimeRef.current = timestamp

    // Build input from keyboard + mobile
    const keys = keysRef.current
    const mobile = mobileInputRef.current
    const input: Input = {
      left: keys.has('ArrowLeft') || keys.has('a') || keys.has('A') || mobile.left,
      right: keys.has('ArrowRight') || keys.has('d') || keys.has('D') || mobile.right,
      up: keys.has('ArrowUp') || keys.has('w') || keys.has('W') || mobile.up,
      down: keys.has('ArrowDown') || keys.has('s') || keys.has('S') || mobile.down,
      digLeft: digLeftPressedRef.current || mobile.digLeft,
      digRight: digRightPressedRef.current || mobile.digRight,
    }
    // Consume dig presses (keyboard only — mobile is held)
    digLeftPressedRef.current = false
    digRightPressedRef.current = false

    let gs = updateGame(gsRef.current, dt, input)
    gsRef.current = gs

    // Sync React state
    setScore(gs.score)
    setLevel(gs.level)
    setLives(gs.lives)

    // Check game over
    if (gs.gameOver) {
      gameStatusRef.current = 'lost'
      setGameStatus('lost')
      saveScore('lode-runner', gs.score)
      draw()
      return
    }

    // Check level complete
    if (gs.levelComplete) {
      const next = nextLevel(gs)
      gsRef.current = next
      if (next.won) {
        gameStatusRef.current = 'won'
        setGameStatus('won')
        saveScore('lode-runner', next.score)
        draw()
        return
      }
      setLevel(next.level)
    }

    draw()
    animFrameRef.current = requestAnimationFrame(tick)
  }, [draw, saveScore])

  // -------------------------------------------------------------------------
  // Start / restart
  // -------------------------------------------------------------------------

  const startGame = useCallback(() => {
    gsRef.current = loadLevel(1)
    setScore(0)
    setLevel(1)
    setLives(3)
    keysRef.current.clear()
    digLeftPressedRef.current = false
    digRightPressedRef.current = false
    mobileInputRef.current = { ...emptyInput }

    gameStatusRef.current = 'playing'
    setGameStatus('playing')
    lastTimeRef.current = performance.now()
    draw()
    animFrameRef.current = requestAnimationFrame(tick)
  }, [draw, tick])

  // -------------------------------------------------------------------------
  // Keyboard controls
  // -------------------------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const gameKeys = [
        'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
        'w', 'a', 's', 'd', 'W', 'A', 'S', 'D',
        'q', 'Q', 'z', 'Z', 'e', 'E', 'x', 'X',
      ]
      if (gameKeys.includes(e.key)) {
        e.preventDefault()
        keysRef.current.add(e.key)
      }

      // Dig actions — single press
      if ((e.key === 'q' || e.key === 'Q' || e.key === 'z' || e.key === 'Z') && !e.repeat) {
        digLeftPressedRef.current = true
      }
      if ((e.key === 'e' || e.key === 'E' || e.key === 'x' || e.key === 'X') && !e.repeat) {
        digRightPressedRef.current = true
      }
    }
    const handleKeyUp = (e: KeyboardEvent) => {
      keysRef.current.delete(e.key)
    }
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('keyup', handleKeyUp)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('keyup', handleKeyUp)
    }
  }, [])

  // -------------------------------------------------------------------------
  // Responsive scaling
  // -------------------------------------------------------------------------

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const updateScale = () => {
      const w = container.clientWidth
      const availableHeight = window.innerHeight - 320
      scaleRef.current = Math.min(1, w / GAME_WIDTH, availableHeight / GAME_HEIGHT)
      draw()
    }
    updateScale()
    const observer = new ResizeObserver(updateScale)
    observer.observe(container)
    return () => observer.disconnect()
  }, [draw])

  // Initial draw
  useEffect(() => { draw() }, [draw])

  // Cleanup
  useEffect(() => {
    return () => { cancelAnimationFrame(animFrameRef.current) }
  }, [])

  // -------------------------------------------------------------------------
  // Mobile d-pad helpers
  // -------------------------------------------------------------------------

  const setMobileKey = useCallback((key: keyof Input, active: boolean) => {
    mobileInputRef.current = { ...mobileInputRef.current, [key]: active }
  }, [])

  const dpadBtn = (label: string, key: keyof Input, extraClass: string = '') => (
    <button
      className={`w-12 h-12 rounded-lg bg-slate-700/80 active:bg-slate-600
        text-slate-300 font-bold text-lg select-none touch-none ${extraClass}`}
      onPointerDown={(e) => { e.preventDefault(); setMobileKey(key, true) }}
      onPointerUp={() => setMobileKey(key, false)}
      onPointerLeave={() => setMobileKey(key, false)}
      onPointerCancel={() => setMobileKey(key, false)}
    >
      {label}
    </button>
  )

  // -------------------------------------------------------------------------
  // Controls bar
  // -------------------------------------------------------------------------

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center space-x-2">
        <span className="text-xs text-slate-400">Lives:</span>
        <div className="flex space-x-1">
          {Array.from({ length: lives }).map((_, i) => (
            <span key={i} className="text-blue-400 text-sm font-bold">@</span>
          ))}
        </div>
      </div>
      <span className="text-xs text-slate-400">
        Lvl {level}: {LEVEL_NAMES[level - 1] ?? ''}
      </span>
      <button
        onClick={startGame}
        className="px-3 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300
                   hover:bg-slate-600 transition-colors"
      >
        New Game
      </button>
    </div>
  )

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <GameLayout title="Lode Runner" score={score} bestScore={bestScore} controls={controls}>
      <div className="relative flex flex-col items-center space-y-3" ref={containerRef}>
        <canvas
          ref={canvasRef}
          className="rounded-lg border border-slate-700 max-w-full"
          style={{ touchAction: 'none' }}
        />

        {/* Mobile d-pad — visible on small screens */}
        {gameStatus === 'playing' && (
          <div className="flex sm:hidden items-center justify-between w-full max-w-xs px-2">
            {/* Dig left */}
            <div className="flex flex-col items-center space-y-1">
              {dpadBtn('DL', 'digLeft', 'w-11 h-11 text-sm bg-amber-800/60 active:bg-amber-700')}
              <span className="text-[10px] text-slate-500">Dig L</span>
            </div>

            {/* D-pad cross */}
            <div className="flex flex-col items-center">
              <div className="flex justify-center">
                {dpadBtn('\u25B2', 'up')}
              </div>
              <div className="flex space-x-1">
                {dpadBtn('\u25C0', 'left')}
                <div className="w-12 h-12" /> {/* spacer */}
                {dpadBtn('\u25B6', 'right')}
              </div>
              <div className="flex justify-center">
                {dpadBtn('\u25BC', 'down')}
              </div>
            </div>

            {/* Dig right */}
            <div className="flex flex-col items-center space-y-1">
              {dpadBtn('DR', 'digRight', 'w-11 h-11 text-sm bg-amber-800/60 active:bg-amber-700')}
              <span className="text-[10px] text-slate-500">Dig R</span>
            </div>
          </div>
        )}

        {/* Idle overlay */}
        {gameStatus === 'idle' && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/70 rounded-lg">
            <div className="text-center">
              <button
                onClick={startGame}
                className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white
                           rounded-lg font-semibold transition-colors"
              >
                Start Game
              </button>
              <p className="text-xs text-slate-400 mt-3">
                Collect all gold, then escape at the top!
              </p>
            </div>
          </div>
        )}

        {/* Game over */}
        {gameStatus === 'lost' && (
          <GameOverModal
            status="lost"
            score={score}
            bestScore={bestScore}
            message={`Reached level ${level}: ${LEVEL_NAMES[level - 1] ?? ''}`}
            onPlayAgain={startGame}
          />
        )}

        {/* Victory */}
        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            score={score}
            bestScore={bestScore}
            message="All 10 levels completed!"
            onPlayAgain={startGame}
          />
        )}

        {/* Controls hint */}
        <p className="text-xs text-slate-500 hidden sm:block">
          Arrow keys / WASD to move. Q/Z dig left. E/X dig right.
        </p>
      </div>
    </GameLayout>
  )
}
