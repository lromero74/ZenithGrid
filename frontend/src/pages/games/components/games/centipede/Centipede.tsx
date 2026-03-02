/**
 * Centipede game -- canvas-based arcade game.
 *
 * Features: keyboard + touch controls, auto-fire, responsive scaling,
 * progressive difficulty, high score tracking.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import {
  createInitialState, updateGame, movePlayer, fireBullet,
  nextLevel, isLevelClear,
  GAME_WIDTH, GAME_HEIGHT, CELL_SIZE, FIRE_COOLDOWN,
  PLAYER_ZONE_ROWS,
  type GameState, type CentipedeSegment, type Mushroom,
  type Spider, type Player,
} from './centipedeEngine'
import type { GameStatus } from '../../../types'

// ---------------------------------------------------------------------------
// Drawing helpers
// ---------------------------------------------------------------------------

function drawBackground(ctx: CanvasRenderingContext2D): void {
  ctx.fillStyle = '#0f172a'
  ctx.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT)

  // Subtle grid lines
  ctx.strokeStyle = '#1e293b'
  ctx.lineWidth = 0.5
  const cols = GAME_WIDTH / CELL_SIZE
  const rows = GAME_HEIGHT / CELL_SIZE
  for (let c = 0; c <= cols; c++) {
    ctx.beginPath()
    ctx.moveTo(c * CELL_SIZE, 0)
    ctx.lineTo(c * CELL_SIZE, GAME_HEIGHT)
    ctx.stroke()
  }
  for (let r = 0; r <= rows; r++) {
    ctx.beginPath()
    ctx.moveTo(0, r * CELL_SIZE)
    ctx.lineTo(GAME_WIDTH, r * CELL_SIZE)
    ctx.stroke()
  }

  // Player zone divider
  const zoneY = GAME_HEIGHT - PLAYER_ZONE_ROWS * CELL_SIZE
  ctx.strokeStyle = '#334155'
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  ctx.beginPath()
  ctx.moveTo(0, zoneY)
  ctx.lineTo(GAME_WIDTH, zoneY)
  ctx.stroke()
  ctx.setLineDash([])
}

function drawMushroom(ctx: CanvasRenderingContext2D, m: Mushroom): void {
  const half = CELL_SIZE / 2 - 1
  const x = m.x - half
  const y = m.y - half
  const size = half * 2
  const r = 3 // corner radius

  // Color darkens as HP decreases
  const colors = ['#166534', '#15803d', '#22c55e', '#4ade80']
  ctx.fillStyle = colors[m.hp - 1] ?? colors[0]

  // Fraction remaining for visual damage
  const fraction = m.hp / 4

  ctx.beginPath()
  ctx.roundRect(x, y + size * (1 - fraction), size, size * fraction, r)
  ctx.fill()

  // Border
  ctx.strokeStyle = '#14532d'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.roundRect(x, y, size, size, r)
  ctx.stroke()
}

function drawPlayerShip(
  ctx: CanvasRenderingContext2D,
  p: Player,
  invulnerable: boolean
): void {
  const half = CELL_SIZE / 2
  ctx.save()

  if (invulnerable) {
    ctx.globalAlpha = 0.5 + 0.3 * Math.sin(Date.now() / 80)
  }

  // Ship body (triangle pointing up)
  ctx.fillStyle = '#34d399'
  ctx.beginPath()
  ctx.moveTo(p.x, p.y - half)
  ctx.lineTo(p.x - half, p.y + half)
  ctx.lineTo(p.x + half, p.y + half)
  ctx.closePath()
  ctx.fill()

  // Cockpit
  ctx.fillStyle = '#6ee7b7'
  ctx.beginPath()
  ctx.arc(p.x, p.y + 2, 3, 0, Math.PI * 2)
  ctx.fill()

  ctx.restore()
}

function drawCentipedeSegment(
  ctx: CanvasRenderingContext2D,
  seg: CentipedeSegment
): void {
  const radius = CELL_SIZE / 2 - 1

  // Body circle
  ctx.fillStyle = seg.isHead ? '#ef4444' : '#dc2626'
  ctx.beginPath()
  ctx.arc(seg.x, seg.y, radius, 0, Math.PI * 2)
  ctx.fill()

  // Darker ring
  ctx.strokeStyle = '#991b1b'
  ctx.lineWidth = 1
  ctx.stroke()

  if (seg.isHead) {
    // Eyes
    const eyeOffset = 3
    const eyeR = 2
    ctx.fillStyle = '#fff'
    ctx.beginPath()
    ctx.arc(seg.x - eyeOffset, seg.y - eyeOffset, eyeR, 0, Math.PI * 2)
    ctx.fill()
    ctx.beginPath()
    ctx.arc(seg.x + eyeOffset, seg.y - eyeOffset, eyeR, 0, Math.PI * 2)
    ctx.fill()

    // Pupils
    ctx.fillStyle = '#000'
    ctx.beginPath()
    ctx.arc(
      seg.x - eyeOffset + seg.dx, seg.y - eyeOffset, 1,
      0, Math.PI * 2
    )
    ctx.fill()
    ctx.beginPath()
    ctx.arc(
      seg.x + eyeOffset + seg.dx, seg.y - eyeOffset, 1,
      0, Math.PI * 2
    )
    ctx.fill()
  }
}

function drawSpider(ctx: CanvasRenderingContext2D, spider: Spider): void {
  const { x, y } = spider
  const bodyR = CELL_SIZE / 2 - 2

  // Legs (4 pairs)
  ctx.strokeStyle = '#f97316'
  ctx.lineWidth = 1.5
  for (let side = -1; side <= 1; side += 2) {
    for (let i = 0; i < 4; i++) {
      const angle = (Math.PI / 5) * (i - 1.5)
      const legLen = bodyR + 4
      const midX = x + side * Math.cos(angle) * (legLen * 0.5)
      const midY = y + Math.sin(angle) * (legLen * 0.5)
      const endX = x + side * Math.cos(angle) * legLen
      const endY = y + Math.sin(angle) * legLen
      ctx.beginPath()
      ctx.moveTo(x, y)
      ctx.quadraticCurveTo(midX, midY - 2, endX, endY)
      ctx.stroke()
    }
  }

  // Body
  ctx.fillStyle = '#ea580c'
  ctx.beginPath()
  ctx.arc(x, y, bodyR, 0, Math.PI * 2)
  ctx.fill()

  // Head spot
  ctx.fillStyle = '#f97316'
  ctx.beginPath()
  ctx.arc(x, y - 2, bodyR * 0.5, 0, Math.PI * 2)
  ctx.fill()

  // Eyes
  ctx.fillStyle = '#fff'
  ctx.beginPath()
  ctx.arc(x - 2, y - 3, 1.5, 0, Math.PI * 2)
  ctx.fill()
  ctx.beginPath()
  ctx.arc(x + 2, y - 3, 1.5, 0, Math.PI * 2)
  ctx.fill()
}

function drawBullet(
  ctx: CanvasRenderingContext2D,
  bx: number,
  by: number
): void {
  ctx.fillStyle = '#facc15'
  ctx.fillRect(bx - 1.5, by - 4, 3, 8)
}

function drawHUD(
  ctx: CanvasRenderingContext2D,
  gs: GameState
): void {
  // Score
  ctx.fillStyle = '#fff'
  ctx.font = 'bold 12px sans-serif'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'top'
  ctx.fillText(`Score: ${gs.score}`, 6, 4)

  // Level
  ctx.textAlign = 'center'
  ctx.fillText(`Level ${gs.level}`, GAME_WIDTH / 2, 4)

  // Lives
  ctx.textAlign = 'right'
  const livesText = '\u25B2'.repeat(gs.lives) // triangle characters
  ctx.fillStyle = '#34d399'
  ctx.fillText(livesText, GAME_WIDTH - 6, 4)
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Centipede() {
  const { getHighScore, saveScore } = useGameScores()
  const bestScore = getHighScore('centipede') ?? 0

  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [score, setScore] = useState(0)
  const [level, setLevel] = useState(1)
  const [lives, setLives] = useState(3)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const scaleRef = useRef(1)

  const gsRef = useRef<GameState>(createInitialState())
  const gameStatusRef = useRef<GameStatus>('idle')
  const animFrameRef = useRef(0)
  const lastTimeRef = useRef(0)

  // Keyboard held-key tracking
  const keysRef = useRef<Set<string>>(new Set())
  const fireTimerRef = useRef(0)

  // Touch/pointer tracking
  const pointerDownRef = useRef(false)
  const pointerPosRef = useRef<{ x: number; y: number } | null>(null)

  // -------------------------------------------------------------------------
  // Draw
  // -------------------------------------------------------------------------

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const scale = scaleRef.current
    canvas.width = GAME_WIDTH * scale
    canvas.height = GAME_HEIGHT * scale

    ctx.save()
    ctx.scale(scale, scale)

    const gs = gsRef.current

    drawBackground(ctx)

    // Mushrooms
    for (const m of gs.mushrooms) {
      drawMushroom(ctx, m)
    }

    // Centipedes
    for (const chain of gs.centipedes) {
      // Draw body segments first, then heads on top
      for (let i = chain.length - 1; i >= 0; i--) {
        drawCentipedeSegment(ctx, chain[i])
      }
      // Draw connectors between segments
      if (chain.length > 1) {
        ctx.strokeStyle = '#b91c1c'
        ctx.lineWidth = 3
        ctx.beginPath()
        ctx.moveTo(chain[0].x, chain[0].y)
        for (let i = 1; i < chain.length; i++) {
          ctx.lineTo(chain[i].x, chain[i].y)
        }
        ctx.stroke()
        // Redraw bodies on top of connectors
        for (let i = chain.length - 1; i >= 0; i--) {
          drawCentipedeSegment(ctx, chain[i])
        }
      }
    }

    // Spider
    if (gs.spider) {
      drawSpider(ctx, gs.spider)
    }

    // Bullets
    for (const b of gs.bullets) {
      drawBullet(ctx, b.x, b.y)
    }

    // Player
    drawPlayerShip(ctx, gs.player, gs.invulnerable > 0)

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

    let gs = gsRef.current

    // Handle held keys for movement
    const keys = keysRef.current
    const moveSpeed = 200 // pixels/second
    let dx = 0
    let dy = 0
    if (keys.has('ArrowLeft') || keys.has('a') || keys.has('A')) dx -= 1
    if (keys.has('ArrowRight') || keys.has('d') || keys.has('D')) dx += 1
    if (keys.has('ArrowUp') || keys.has('w') || keys.has('W')) dy -= 1
    if (keys.has('ArrowDown') || keys.has('s') || keys.has('S')) dy += 1
    if (dx !== 0 || dy !== 0) {
      gs = movePlayer(
        gs,
        gs.player.x + dx * moveSpeed * dt,
        gs.player.y + dy * moveSpeed * dt
      )
    }

    // Handle pointer-based movement (touch / mouse drag)
    if (pointerDownRef.current && pointerPosRef.current) {
      gs = movePlayer(gs, pointerPosRef.current.x, pointerPosRef.current.y)
    }

    // Auto-fire
    fireTimerRef.current -= dt
    const shouldFire =
      keys.has(' ') || keys.has('Space') || pointerDownRef.current
    if (shouldFire && fireTimerRef.current <= 0) {
      gs = fireBullet(gs)
      fireTimerRef.current = FIRE_COOLDOWN
    }

    // Update game logic
    gs = updateGame(gs, dt)
    gsRef.current = gs

    // Sync React state for UI
    setScore(gs.score)
    setLevel(gs.level)
    setLives(gs.lives)

    // Check game over
    if (gs.gameOver) {
      gameStatusRef.current = 'lost'
      setGameStatus('lost')
      saveScore('centipede', gs.score)
      draw()
      return
    }

    // Check level clear
    if (isLevelClear(gs)) {
      gsRef.current = nextLevel(gs)
      setLevel(gsRef.current.level)
    }

    draw()
    animFrameRef.current = requestAnimationFrame(tick)
  }, [draw, saveScore])

  // -------------------------------------------------------------------------
  // Start / restart
  // -------------------------------------------------------------------------

  const startGame = useCallback(() => {
    gsRef.current = createInitialState()
    setScore(0)
    setLevel(1)
    setLives(3)
    gameStatusRef.current = 'playing'
    setGameStatus('playing')
    fireTimerRef.current = 0
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
        'w', 'a', 's', 'd', 'W', 'A', 'S', 'D', ' ',
      ]
      if (gameKeys.includes(e.key)) {
        e.preventDefault()
        keysRef.current.add(e.key)
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
  // Pointer (touch + mouse) controls
  // -------------------------------------------------------------------------

  const canvasToGame = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    const scale = scaleRef.current
    const gx = (clientX - rect.left) / scale
    const gy = (clientY - rect.top) / scale
    return { x: gx, y: gy }
  }, [])

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      e.preventDefault()
      const pos = canvasToGame(e.clientX, e.clientY)
      if (!pos) return
      pointerDownRef.current = true
      pointerPosRef.current = pos
      // Capture so we get move/up even outside canvas
      ;(e.target as HTMLCanvasElement).setPointerCapture(e.pointerId)
    },
    [canvasToGame]
  )

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      if (!pointerDownRef.current) return
      const pos = canvasToGame(e.clientX, e.clientY)
      if (pos) pointerPosRef.current = pos
    },
    [canvasToGame]
  )

  const handlePointerUp = useCallback(() => {
    pointerDownRef.current = false
    pointerPosRef.current = null
  }, [])

  // -------------------------------------------------------------------------
  // Responsive scaling via ResizeObserver
  // -------------------------------------------------------------------------

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const updateScale = () => {
      const w = container.clientWidth
      const availableHeight = window.innerHeight - 260
      scaleRef.current = Math.min(
        1,
        w / GAME_WIDTH,
        availableHeight / GAME_HEIGHT
      )
      draw()
    }
    updateScale()
    const observer = new ResizeObserver(updateScale)
    observer.observe(container)
    return () => observer.disconnect()
  }, [draw])

  // Initial draw
  useEffect(() => { draw() }, [draw])

  // Cleanup animation frame on unmount
  useEffect(() => {
    return () => { cancelAnimationFrame(animFrameRef.current) }
  }, [])

  // -------------------------------------------------------------------------
  // Controls bar
  // -------------------------------------------------------------------------

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center space-x-2">
        {/* Lives as small ship icons */}
        {Array.from({ length: lives }).map((_, i) => (
          <svg key={i} width="14" height="14" viewBox="0 0 14 14">
            <polygon
              points="7,1 1,13 13,13"
              fill="#34d399"
              stroke="#065f46"
              strokeWidth="1"
            />
          </svg>
        ))}
      </div>
      <span className="text-xs text-slate-400">Level {level}</span>
      <button
        onClick={startGame}
        className="px-2 py-0.5 rounded text-xs font-medium
          bg-slate-700 text-slate-300 hover:bg-slate-600
          transition-colors"
      >
        New Game
      </button>
    </div>
  )

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <GameLayout
      title="Centipede"
      score={score}
      bestScore={bestScore}
      controls={controls}
    >
      <div
        className="relative flex flex-col items-center space-y-4"
        ref={containerRef}
      >
        <canvas
          ref={canvasRef}
          className="rounded-lg border border-slate-700 cursor-crosshair"
          style={{ touchAction: 'none' }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        />

        {/* Idle overlay */}
        {gameStatus === 'idle' && (
          <div
            className="absolute inset-0 flex items-center justify-center
              bg-slate-900/70 rounded-lg"
          >
            <button
              onClick={startGame}
              className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500
                text-white rounded-lg font-semibold transition-colors"
            >
              Start Game
            </button>
          </div>
        )}

        {/* Game over modal */}
        {gameStatus === 'lost' && (
          <GameOverModal
            status="lost"
            score={score}
            bestScore={bestScore}
            message={`You reached level ${level}`}
            onPlayAgain={startGame}
          />
        )}

        {/* Controls hint */}
        <p className="text-xs text-slate-500 hidden sm:block">
          Arrow keys / WASD to move. Space to shoot.
          Touch and drag on mobile.
        </p>
      </div>
    </GameLayout>
  )
}
