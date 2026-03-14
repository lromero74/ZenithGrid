/**
 * Centipede game -- canvas-based arcade game.
 *
 * Features: keyboard + touch controls, auto-fire, responsive scaling,
 * progressive difficulty, high score tracking.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
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
import { useGameMusic } from '../../../audio/useGameMusic'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { useGameSFX } from '../../../audio/useGameSFX'
import { MultiplayerWrapper, type RoomConfig } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay, CountdownOverlay } from '../../multiplayer/RaceOverlay'

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
// Help modal
// ---------------------------------------------------------------------------

function CentipedeHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Centipede</h2>

        {/* Goal */}
        <Sec title="Goal">
          Destroy the centipede as it winds its way down the screen. Shoot every
          segment before it reaches your ship at the bottom. Survive as long as
          possible and rack up the highest score.
        </Sec>

        {/* Player Movement */}
        <Sec title="Player Movement">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Your ship (the green triangle) can move freely within the
              <B> bottom 5 rows</B> of the field.</Li>
            <Li>Use <B>arrow keys</B> or <B>WASD</B> to move on desktop.</Li>
            <Li>On mobile, <B>touch and drag</B> anywhere on the canvas to move
              your ship to that position.</Li>
          </ul>
        </Sec>

        {/* Shooting */}
        <Sec title="Shooting">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Press <B>Space</B> to fire on desktop, or simply <B>touch the
              canvas</B> on mobile.</Li>
            <Li>Your ship <B>auto-fires</B> while the fire key/touch is held
              down.</Li>
            <Li>Only <B>one bullet</B> can be on screen at a time &mdash; wait
              for it to hit something or leave the screen before the next shot
              fires.</Li>
          </ul>
        </Sec>

        {/* Centipede */}
        <Sec title="The Centipede">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>The centipede starts as a chain of <B>12 segments</B> entering
              from the top-left corner.</Li>
            <Li>It moves <B>horizontally</B> across the grid. When it hits a
              wall or a mushroom, it <B>drops down one row</B> and reverses
              direction.</Li>
            <Li>When the centipede reaches the bottom, it reverses vertically
              and begins <B>climbing back up</B>.</Li>
            <Li>Shooting a segment <B>splits</B> the chain &mdash; each
              remaining piece becomes an independent centipede with its own
              head.</Li>
            <Li>A destroyed segment leaves a <B>mushroom</B> behind at its
              position.</Li>
          </ul>
        </Sec>

        {/* Mushrooms */}
        <Sec title="Mushrooms">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>The field starts with <B>35 randomly placed mushrooms</B>.</Li>
            <Li>Mushrooms have <B>4 hit points</B>. Each shot reduces their HP
              by 1 &mdash; they visually shrink as they take damage.</Li>
            <Li>Mushrooms <B>block the centipede</B>, causing it to drop and
              reverse just like a wall.</Li>
            <Li>Destroying a mushroom scores <B>1 point</B>.</Li>
            <Li>When a new level begins, all damaged mushrooms are <B>restored
              to full HP</B>.</Li>
          </ul>
        </Sec>

        {/* Spider */}
        <Sec title="The Spider">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>A spider appears every <B>5 seconds</B> and roams the bottom
              portion of the field for <B>5 seconds</B> before leaving.</Li>
            <Li>It bounces diagonally around the player zone and can
              <B> eat mushrooms</B> it touches.</Li>
            <Li>Touching the spider <B>kills your ship</B> (unless
              invulnerable).</Li>
            <Li>Shooting the spider awards <B>300, 600, or 900 points</B>
              (random each spawn).</Li>
          </ul>
        </Sec>

        {/* Lives & Respawn */}
        <Sec title="Lives &amp; Respawn">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>You start with <B>3 lives</B> (shown as green triangles).</Li>
            <Li>Touching a centipede segment or the spider costs a life.</Li>
            <Li>After losing a life, your ship respawns at the bottom center
              with <B>2 seconds of invulnerability</B> (ship blinks).</Li>
            <Li>When all lives are lost, the game is over.</Li>
          </ul>
        </Sec>

        {/* Scoring */}
        <Sec title="Scoring">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Head segment</B> &mdash; 100 points.</Li>
            <Li><B>Body segment</B> &mdash; 10 points.</Li>
            <Li><B>Spider</B> &mdash; 300, 600, or 900 points.</Li>
            <Li><B>Mushroom destroyed</B> &mdash; 1 point.</Li>
          </ul>
        </Sec>

        {/* Level Progression */}
        <Sec title="Level Progression">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Clear all centipede segments to advance to the next level.</Li>
            <Li>Each new level spawns a fresh centipede that moves <B>faster</B>
              &mdash; speed increases with every level.</Li>
            <Li>Damaged mushrooms are restored, and you receive a brief moment
              of invulnerability.</Li>
          </ul>
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Target the head.</B> Destroying the head is worth 10x more
              than a body segment and prevents the chain from advancing.</Li>
            <Li><B>Clear mushroom paths.</B> Removing mushrooms near the bottom
              gives the centipede fewer reasons to drop down quickly.</Li>
            <Li><B>Watch for splits.</B> Each destroyed mid-chain segment creates
              a new independent centipede &mdash; multiple small chains can be
              harder to dodge than one long one.</Li>
            <Li><B>Use invulnerability wisely.</B> After respawning, you have 2
              seconds to reposition safely.</Li>
            <Li><B>Keep an eye on the spider.</B> It can sneak up from the side
              and eat useful mushroom barriers.</Li>
            <Li><B>Stay mobile.</B> Sitting still makes you an easy target
              &mdash; keep moving laterally while firing.</Li>
          </ul>
        </Sec>

        <div className="mt-4 pt-3 border-t border-slate-700 text-center">
          <button onClick={onClose} className="px-6 py-2 text-sm rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors">
            Got it!
          </button>
        </div>
      </div>
    </div>
  )
}

function Sec({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="text-sm font-semibold text-slate-200 mb-1">{title}</h3>
      <div className="text-xs leading-relaxed text-slate-400">{children}</div>
    </div>
  )
}

function Li({ children }: { children: React.ReactNode }) {
  return <li className="flex gap-1.5 text-xs"><span className="text-slate-600 mt-0.5">&bull;</span><span>{children}</span></li>
}

function B({ children }: { children: React.ReactNode }) {
  return <span className="text-white font-medium">{children}</span>
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CentipedeSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer, inputBlocked, autoStart }: { onGameEnd?: (result: 'win' | 'loss' | 'draw', score?: number) => void; onStateChange?: (state: object, intervalMs?: number) => void; isMultiplayer?: boolean; inputBlocked?: boolean; autoStart?: boolean } = {}) {
  const { getHighScore, saveScore } = useGameScores()
  const bestScore = getHighScore('centipede') ?? 0

  // Music
  const song = useMemo(() => getSongForGame('centipede'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('centipede')

  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [showHelp, setShowHelp] = useState(false)
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

  // Input blocking for sync-start multiplayer
  const inputBlockedRef = useRef(!!inputBlocked)
  inputBlockedRef.current = !!inputBlocked

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

    // Handle held keys for movement (suppressed when input is blocked)
    if (!inputBlockedRef.current) {
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
        sfx.play('fire')
        gs = fireBullet(gs)
        fireTimerRef.current = FIRE_COOLDOWN
      }
    }

    // Update game logic
    const prevScore = gs.score
    gs = updateGame(gs, dt)
    gsRef.current = gs

    // Detect enemy hit (score increased after update)
    if (gs.score > prevScore) {
      sfx.play('hit')
    }

    // Sync React state for UI
    setScore(gs.score)
    setLevel(gs.level)
    setLives(gs.lives)

    // Check game over
    if (gs.gameOver) {
      gameStatusRef.current = 'lost'
      setGameStatus('lost')
      saveScore('centipede', gs.score)
      sfx.play('die')
      onGameEnd?.('loss', gs.score)
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
  }, [draw, saveScore, onGameEnd])

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
    music.init()
    sfx.init()
    music.start()
    fireTimerRef.current = 0
    lastTimeRef.current = performance.now()
    draw()
    animFrameRef.current = requestAnimationFrame(tick)
  }, [draw, tick, music])

  // Auto-start when countdown finishes (multiplayer sync-start)
  useEffect(() => {
    if (autoStart && gameStatusRef.current === 'idle') {
      startGame()
    }
  }, [autoStart, startGame])

  // -------------------------------------------------------------------------
  // Keyboard controls
  // -------------------------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (inputBlockedRef.current) return
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
      if (inputBlockedRef.current) return
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
      const chromeOffset = window.innerWidth < 640 ? 320 : 260
      const availableHeight = window.innerHeight - chromeOffset
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
      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowHelp(true)}
          className="p-1.5 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-white"
          title="How to Play"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
        <button
          onClick={startGame}
          className="px-2 py-0.5 rounded text-xs font-medium
            bg-slate-700 text-slate-300 hover:bg-slate-600
            transition-colors"
        >
          New Game
        </button>
      </div>
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
        {gameStatus === 'lost' && !isMultiplayer && (
          <GameOverModal
            status="lost"
            score={score}
            bestScore={bestScore}
            message={`You reached level ${level}`}
            onPlayAgain={startGame}
            music={music}
            sfx={sfx}
          />
        )}

        {/* Controls hint */}
        <p className="text-xs text-slate-500 hidden sm:block">
          Arrow keys / WASD to move. Space to shoot.
          Touch and drag on mobile.
        </p>
      </div>

      {/* Help modal */}
      {showHelp && <CentipedeHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ---------------------------------------------------------------------------
// Race wrapper (survival or best_score — last alive or highest score wins)
// ---------------------------------------------------------------------------

function CentipedeRaceWrapper({ roomId, roomConfig, onLeave }: { roomId: string; roomConfig: RoomConfig; onLeave?: () => void }) {
  const raceType = (roomConfig.race_type as 'survival' | 'best_score') || 'survival'
  const {
    opponentStatus, raceResult, localScore, opponentLevelUp, throttledBroadcast, reportFinish, leaveRoom,
    gameStarted, countdownValue, localReady, sendReady,
  } = useRaceMode(roomId, raceType, { syncStart: true })
  const finishedRef = useRef(false)

  const handleGameEnd = useCallback((_result: 'win' | 'loss' | 'draw', score?: number) => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish('loss', score ?? 0)
  }, [reportFinish])

  return (
    <div className="relative">
      <RaceOverlay
        raceResult={raceResult}
        localScore={localScore}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
        onDismiss={onLeave}
        onLeaveGame={leaveRoom}
        onBackToLobby={onLeave}
      />
      {!gameStarted && (
        <CountdownOverlay countdownValue={countdownValue} localReady={localReady} onReady={sendReady} onLeave={leaveRoom} onBackToLobby={onLeave} />
      )}
      <CentipedeSinglePlayer onGameEnd={handleGameEnd} onStateChange={throttledBroadcast} isMultiplayer inputBlocked={!gameStarted} autoStart={gameStarted} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Default export — multiplayer wrapper
// ---------------------------------------------------------------------------

export default function Centipede() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'centipede',
        gameName: 'Centipede',
        modes: ['survival', 'best_score'],
        maxPlayers: 2,
        hasDifficulty: false,
        modeDescriptions: { survival: 'Last player alive wins', best_score: 'Highest score wins' },
      }}
      renderSinglePlayer={() => <CentipedeSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig, onLeave) => (
        <CentipedeRaceWrapper roomId={roomId} roomConfig={roomConfig} onLeave={onLeave} />
      )}
    />
  )
}
