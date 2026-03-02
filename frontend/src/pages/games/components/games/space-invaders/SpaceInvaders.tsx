/**
 * Space Invaders — canvas-based arcade game.
 *
 * Features: keyboard + pointer/touch controls, classic alien formations,
 * bunkers, UFO bonus, wave progression, high score tracking.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import {
  createInitialState, updateGame, firePlayerBullet, getAliveCount,
  GAME_WIDTH, GAME_HEIGHT,
  type GameState, type Player, type Alien, type Bullet,
  type BunkerBlock, type UFO,
} from './spaceInvadersEngine'
import type { GameStatus } from '../../../types'

// ---------------------------------------------------------------------------
// Drawing helpers
// ---------------------------------------------------------------------------

const COLOR_PLAYER = '#22c55e'
const COLOR_BUNKER = '#22c55e'
const COLOR_PLAYER_BULLET = '#ffffff'
const COLOR_ALIEN_BULLET = '#facc15'
const COLOR_UFO = '#ef4444'
const COLOR_BG = '#000000'
const COLOR_HUD = '#ffffff'

const ALIEN_COLORS: string[][] = [
  ['#ffffff', '#67e8f9'], // type 0 — squid (white/cyan)
  ['#67e8f9', '#3b82f6'], // type 1 — crab (cyan/blue)
  ['#67e8f9', '#3b82f6'], // type 2 — crab
  ['#22c55e', '#4ade80'], // type 3 — octopus (green)
  ['#22c55e', '#4ade80'], // type 4 — octopus
]

function drawPlayer(ctx: CanvasRenderingContext2D, p: Player) {
  ctx.save()
  ctx.fillStyle = COLOR_PLAYER

  // Flat base rectangle
  const baseH = 8
  ctx.fillRect(p.x, p.y + p.height - baseH, p.width, baseH)

  // Turret body
  const turretW = 20
  const turretH = 8
  const turretX = p.x + (p.width - turretW) / 2
  ctx.fillRect(turretX, p.y + p.height - baseH - turretH, turretW, turretH)

  // Cannon tip (triangle)
  const tipW = 4
  const tipH = 6
  ctx.beginPath()
  ctx.moveTo(p.x + p.width / 2 - tipW / 2, p.y + p.height - baseH - turretH)
  ctx.lineTo(p.x + p.width / 2 + tipW / 2, p.y + p.height - baseH - turretH)
  ctx.lineTo(p.x + p.width / 2, p.y + p.height - baseH - turretH - tipH)
  ctx.closePath()
  ctx.fill()

  ctx.restore()
}

function drawAlien(ctx: CanvasRenderingContext2D, a: Alien) {
  if (!a.alive) return
  ctx.save()
  const cx = a.x + a.width / 2
  const cy = a.y + a.height / 2
  const colors = ALIEN_COLORS[a.type]
  ctx.fillStyle = colors[a.frame]

  if (a.type === 0) {
    // Squid — small body, antennae
    const bw = 12
    const bh = 10
    ctx.fillRect(cx - bw / 2, cy - bh / 2 + 2, bw, bh)
    // Head bump
    ctx.fillRect(cx - 4, cy - bh / 2 - 2, 8, 6)
    if (a.frame === 0) {
      // Antennae up-outward
      ctx.fillRect(cx - 8, cy - bh / 2 - 4, 3, 4)
      ctx.fillRect(cx + 5, cy - bh / 2 - 4, 3, 4)
      // Legs down
      ctx.fillRect(cx - 7, cy + bh / 2 + 1, 3, 4)
      ctx.fillRect(cx + 4, cy + bh / 2 + 1, 3, 4)
    } else {
      // Antennae outward-down
      ctx.fillRect(cx - 10, cy - bh / 2, 3, 4)
      ctx.fillRect(cx + 7, cy - bh / 2, 3, 4)
      // Legs spread
      ctx.fillRect(cx - 9, cy + bh / 2 - 1, 3, 4)
      ctx.fillRect(cx + 6, cy + bh / 2 - 1, 3, 4)
    }
    // Eyes
    ctx.fillStyle = COLOR_BG
    ctx.fillRect(cx - 4, cy - 1, 2, 2)
    ctx.fillRect(cx + 2, cy - 1, 2, 2)
  } else if (a.type <= 2) {
    // Crab — medium, distinct arms
    const bw = 16
    const bh = 10
    ctx.fillRect(cx - bw / 2, cy - bh / 2 + 1, bw, bh)
    // Top protrusions
    ctx.fillRect(cx - 5, cy - bh / 2 - 2, 4, 4)
    ctx.fillRect(cx + 1, cy - bh / 2 - 2, 4, 4)
    if (a.frame === 0) {
      // Arms up
      ctx.fillRect(cx - bw / 2 - 4, cy - 3, 4, 6)
      ctx.fillRect(cx + bw / 2, cy - 3, 4, 6)
      // Legs inward
      ctx.fillRect(cx - 5, cy + bh / 2, 3, 4)
      ctx.fillRect(cx + 2, cy + bh / 2, 3, 4)
    } else {
      // Arms down
      ctx.fillRect(cx - bw / 2 - 4, cy + 1, 4, 6)
      ctx.fillRect(cx + bw / 2, cy + 1, 4, 6)
      // Legs outward
      ctx.fillRect(cx - 8, cy + bh / 2, 3, 4)
      ctx.fillRect(cx + 5, cy + bh / 2, 3, 4)
    }
    // Eyes
    ctx.fillStyle = COLOR_BG
    ctx.fillRect(cx - 4, cy, 2, 2)
    ctx.fillRect(cx + 2, cy, 2, 2)
  } else {
    // Octopus — large, tentacle-like legs
    const bw = 18
    const bh = 12
    // Rounded top
    ctx.beginPath()
    ctx.arc(cx, cy - bh / 2 + 4, bw / 2, Math.PI, 0)
    ctx.fill()
    ctx.fillRect(cx - bw / 2, cy - bh / 2 + 4, bw, bh - 4)
    if (a.frame === 0) {
      // Tentacles splayed out
      ctx.fillRect(cx - 10, cy + bh / 2 - 2, 3, 5)
      ctx.fillRect(cx - 5, cy + bh / 2, 3, 4)
      ctx.fillRect(cx + 2, cy + bh / 2, 3, 4)
      ctx.fillRect(cx + 7, cy + bh / 2 - 2, 3, 5)
    } else {
      // Tentacles curled inward
      ctx.fillRect(cx - 8, cy + bh / 2, 3, 4)
      ctx.fillRect(cx - 3, cy + bh / 2 - 2, 3, 5)
      ctx.fillRect(cx + 1, cy + bh / 2 - 2, 3, 5)
      ctx.fillRect(cx + 6, cy + bh / 2, 3, 4)
    }
    // Eyes
    ctx.fillStyle = COLOR_BG
    ctx.fillRect(cx - 5, cy - 1, 3, 3)
    ctx.fillRect(cx + 2, cy - 1, 3, 3)
  }

  ctx.restore()
}

function drawBullet(
  ctx: CanvasRenderingContext2D,
  b: Bullet,
  isAlien: boolean,
) {
  ctx.save()
  if (isAlien) {
    // Zigzag lightning bolt pattern
    ctx.strokeStyle = COLOR_ALIEN_BULLET
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(b.x + b.width / 2, b.y)
    ctx.lineTo(b.x + b.width, b.y + b.height * 0.33)
    ctx.lineTo(b.x, b.y + b.height * 0.66)
    ctx.lineTo(b.x + b.width / 2, b.y + b.height)
    ctx.stroke()
  } else {
    ctx.fillStyle = COLOR_PLAYER_BULLET
    ctx.fillRect(b.x, b.y, b.width, b.height)
  }
  ctx.restore()
}

function drawBunkerBlocks(
  ctx: CanvasRenderingContext2D,
  bunkers: BunkerBlock[][],
) {
  ctx.save()
  ctx.fillStyle = COLOR_BUNKER
  for (const bunker of bunkers) {
    for (const bl of bunker) {
      if (bl.alive) {
        ctx.fillRect(bl.x, bl.y, bl.width, bl.height)
      }
    }
  }
  ctx.restore()
}

function drawUFO(ctx: CanvasRenderingContext2D, ufo: UFO) {
  if (!ufo.alive) return
  ctx.save()
  const cx = ufo.x + 18
  const cy = ufo.y + 8

  // Saucer body (ellipse)
  ctx.fillStyle = COLOR_UFO
  ctx.beginPath()
  ctx.ellipse(cx, cy + 2, 18, 6, 0, 0, Math.PI * 2)
  ctx.fill()

  // Dome
  ctx.fillStyle = '#f87171'
  ctx.beginPath()
  ctx.ellipse(cx, cy - 2, 10, 6, 0, Math.PI, 0)
  ctx.fill()

  // Lights
  ctx.fillStyle = '#fbbf24'
  ctx.fillRect(cx - 12, cy + 2, 3, 2)
  ctx.fillRect(cx - 2, cy + 3, 3, 2)
  ctx.fillRect(cx + 8, cy + 2, 3, 2)

  ctx.restore()
}

function drawPlayerLifeIcon(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
) {
  ctx.save()
  ctx.fillStyle = COLOR_PLAYER
  // Mini cannon: base + turret + tip
  ctx.fillRect(x, y + 6, 16, 4)
  ctx.fillRect(x + 4, y + 3, 8, 4)
  ctx.fillRect(x + 7, y, 2, 4)
  ctx.restore()
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SpaceInvaders() {
  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [score, setScore] = useState(0)
  const [lives, setLives] = useState(3)
  const [wave, setWave] = useState(1)
  const { getHighScore, saveScore } = useGameScores()
  const bestScore = getHighScore('space-invaders') ?? 0

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const stateRef = useRef<GameState>(createInitialState())
  const gameStatusRef = useRef<GameStatus>('idle')
  const animFrameRef = useRef<number>(0)
  const lastTimeRef = useRef<number>(0)
  const scaleRef = useRef(1)

  // Key tracking for continuous movement
  const keysRef = useRef<Set<string>>(new Set())
  // Pointer tracking for mobile
  const pointerActiveRef = useRef(false)
  const pointerXRef = useRef(GAME_WIDTH / 2)
  const autoFireIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Invulnerability after death
  const invulnTimerRef = useRef(0)
  // Track last score for carry-over between waves
  const carryScoreRef = useRef(0)

  // -----------------------------------------------------------------------
  // Draw
  // -----------------------------------------------------------------------
  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const scale = scaleRef.current
    const w = Math.floor(GAME_WIDTH * scale)
    const h = Math.floor(GAME_HEIGHT * scale)
    canvas.width = w
    canvas.height = h

    ctx.save()
    ctx.scale(scale, scale)

    // Background
    ctx.fillStyle = COLOR_BG
    ctx.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT)

    const gs = stateRef.current

    // HUD: Score + Lives + Wave (top bar)
    ctx.fillStyle = COLOR_HUD
    ctx.font = 'bold 14px monospace'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'top'
    ctx.fillText(`SCORE ${gs.score}`, 8, 6)

    ctx.textAlign = 'center'
    ctx.fillText(`WAVE ${gs.wave}`, GAME_WIDTH / 2, 6)

    // Lives as ship icons on right
    ctx.textAlign = 'right'
    ctx.fillText(`${gs.lives}`, GAME_WIDTH - 8, 6)
    for (let i = 0; i < gs.lives - 1; i++) {
      drawPlayerLifeIcon(ctx, GAME_WIDTH - 32 - i * 22, 4)
    }

    // Separator line below HUD
    ctx.strokeStyle = '#22c55e33'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(0, 26)
    ctx.lineTo(GAME_WIDTH, 26)
    ctx.stroke()

    // Bottom line (above which aliens must not pass in the classic game)
    ctx.strokeStyle = '#22c55e33'
    ctx.beginPath()
    ctx.moveTo(0, GAME_HEIGHT - 20)
    ctx.lineTo(GAME_WIDTH, GAME_HEIGHT - 20)
    ctx.stroke()

    // UFO
    if (gs.ufo) drawUFO(ctx, gs.ufo)

    // Aliens
    for (const a of gs.aliens) {
      drawAlien(ctx, a)
    }

    // Bunkers
    drawBunkerBlocks(ctx, gs.bunkers)

    // Player (blink if invulnerable)
    const showPlayer = invulnTimerRef.current <= 0
      || Math.floor(invulnTimerRef.current * 10) % 2 === 0
    if (showPlayer) {
      drawPlayer(ctx, gs.player)
    }

    // Player bullets
    for (const b of gs.playerBullets) {
      drawBullet(ctx, b, false)
    }

    // Alien bullets
    for (const b of gs.alienBullets) {
      drawBullet(ctx, b, true)
    }

    ctx.restore()
  }, [])

  // -----------------------------------------------------------------------
  // Game loop
  // -----------------------------------------------------------------------
  const tick = useCallback((timestamp: number) => {
    if (gameStatusRef.current !== 'playing') return

    const dt = Math.min((timestamp - lastTimeRef.current) / 1000, 0.05)
    lastTimeRef.current = timestamp

    // Determine player movement direction from held keys or pointer
    let playerDx = 0
    if (pointerActiveRef.current) {
      // Move toward pointer X
      const gs = stateRef.current
      const targetX = pointerXRef.current - gs.player.width / 2
      const diff = targetX - gs.player.x
      if (Math.abs(diff) > 2) {
        playerDx = diff > 0 ? 1 : -1
      }
    } else {
      if (keysRef.current.has('ArrowLeft') || keysRef.current.has('a') || keysRef.current.has('A')) {
        playerDx -= 1
      }
      if (keysRef.current.has('ArrowRight') || keysRef.current.has('d') || keysRef.current.has('D')) {
        playerDx += 1
      }
    }

    // Invulnerability countdown
    if (invulnTimerRef.current > 0) {
      invulnTimerRef.current -= dt
    }

    // Store pre-update lives to detect death
    const prevLives = stateRef.current.lives

    // Update game state
    let nextState = updateGame(stateRef.current, dt, playerDx)

    // Detect if player just lost a life
    if (nextState.lives < prevLives && !nextState.gameOver) {
      invulnTimerRef.current = 2.0 // 2 seconds invulnerability
    }

    // Carry over score from previous waves
    if (nextState.score === 0 && carryScoreRef.current > 0) {
      nextState = { ...nextState, score: carryScoreRef.current }
    }

    stateRef.current = nextState

    // Sync React state
    setScore(nextState.score)
    setLives(nextState.lives)

    // Check wave clear
    if (getAliveCount(nextState.aliens) === 0 && !nextState.gameOver) {
      const nextWave = nextState.wave + 1
      carryScoreRef.current = nextState.score
      const fresh = createInitialState(nextWave)
      stateRef.current = {
        ...fresh,
        score: nextState.score,
        lives: nextState.lives,
      }
      setWave(nextWave)
      draw()
      animFrameRef.current = requestAnimationFrame(tick)
      return
    }

    // Check game over
    if (nextState.gameOver) {
      gameStatusRef.current = 'lost'
      setGameStatus('lost')
      saveScore('space-invaders', nextState.score)
      draw()
      return
    }

    draw()
    animFrameRef.current = requestAnimationFrame(tick)
  }, [draw, saveScore])

  // -----------------------------------------------------------------------
  // Start / restart
  // -----------------------------------------------------------------------
  const startGame = useCallback(() => {
    const initial = createInitialState(1)
    stateRef.current = initial
    carryScoreRef.current = 0
    invulnTimerRef.current = 0
    keysRef.current.clear()
    pointerActiveRef.current = false

    setScore(0)
    setLives(3)
    setWave(1)
    gameStatusRef.current = 'playing'
    setGameStatus('playing')

    lastTimeRef.current = performance.now()
    draw()
    animFrameRef.current = requestAnimationFrame(tick)
  }, [draw, tick])

  // -----------------------------------------------------------------------
  // Keyboard controls
  // -----------------------------------------------------------------------
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const movementKeys = [
        'ArrowLeft', 'ArrowRight', 'a', 'A', 'd', 'D', ' ',
      ]
      if (movementKeys.includes(e.key)) {
        e.preventDefault()
      }

      keysRef.current.add(e.key)

      if (e.key === ' ' && gameStatusRef.current === 'playing') {
        stateRef.current = firePlayerBullet(stateRef.current)
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

  // -----------------------------------------------------------------------
  // Pointer/touch controls
  // -----------------------------------------------------------------------
  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    if (gameStatusRef.current !== 'playing') return

    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const scale = scaleRef.current
    const gameX = (e.clientX - rect.left) / scale

    pointerActiveRef.current = true
    pointerXRef.current = Math.max(0, Math.min(GAME_WIDTH, gameX))

    // Fire immediately
    stateRef.current = firePlayerBullet(stateRef.current)

    // Start auto-fire interval
    if (autoFireIntervalRef.current) clearInterval(autoFireIntervalRef.current)
    autoFireIntervalRef.current = setInterval(() => {
      if (gameStatusRef.current === 'playing') {
        stateRef.current = firePlayerBullet(stateRef.current)
      }
    }, 250)
  }, [])

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!pointerActiveRef.current) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const scale = scaleRef.current
    const gameX = (e.clientX - rect.left) / scale
    pointerXRef.current = Math.max(0, Math.min(GAME_WIDTH, gameX))
  }, [])

  const handlePointerUp = useCallback(() => {
    pointerActiveRef.current = false
    if (autoFireIntervalRef.current) {
      clearInterval(autoFireIntervalRef.current)
      autoFireIntervalRef.current = null
    }
  }, [])

  // -----------------------------------------------------------------------
  // Responsive scaling
  // -----------------------------------------------------------------------
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const updateScale = () => {
      const w = container.clientWidth
      const availableHeight = window.innerHeight - 260
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
    return () => {
      cancelAnimationFrame(animFrameRef.current)
      if (autoFireIntervalRef.current) clearInterval(autoFireIntervalRef.current)
    }
  }, [])

  // -----------------------------------------------------------------------
  // Controls bar
  // -----------------------------------------------------------------------
  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center space-x-2">
        <span className="text-xs text-slate-400">Lives:</span>
        <div className="flex space-x-1">
          {Array.from({ length: lives }).map((_, i) => (
            <svg key={i} width="16" height="12" viewBox="0 0 16 12">
              <rect x="0" y="7" width="16" height="5" fill={COLOR_PLAYER} />
              <rect x="4" y="4" width="8" height="4" fill={COLOR_PLAYER} />
              <rect x="7" y="0" width="2" height="5" fill={COLOR_PLAYER} />
            </svg>
          ))}
        </div>
      </div>
      <span className="text-xs text-slate-400">Wave {wave}</span>
      <button
        onClick={startGame}
        className="px-3 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300
                   hover:bg-slate-600 transition-colors"
      >
        New Game
      </button>
    </div>
  )

  return (
    <GameLayout title="Space Invaders" score={score} bestScore={bestScore} controls={controls}>
      <div className="relative flex flex-col items-center space-y-4" ref={containerRef}>
        <canvas
          ref={canvasRef}
          className="rounded-lg border border-slate-700 cursor-crosshair max-w-full"
          style={{ touchAction: 'none' }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
          onPointerCancel={handlePointerUp}
        />

        {/* Idle overlay */}
        {gameStatus === 'idle' && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/70 rounded-lg">
            <button
              onClick={startGame}
              className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white
                         rounded-lg font-semibold transition-colors"
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
            message={`You reached wave ${wave}`}
            onPlayAgain={startGame}
          />
        )}

        {/* Controls hint */}
        <p className="text-xs text-slate-500 hidden sm:block">
          Arrow keys or A/D to move. Space to shoot. Touch/click and drag on mobile.
        </p>
      </div>
    </GameLayout>
  )
}
