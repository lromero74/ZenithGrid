/**
 * Plinko game — canvas-based ball-drop arcade game.
 *
 * Features: click/tap to drop balls, risk level selector,
 * multiple simultaneous balls, balance/bet system, color-coded slots.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import {
  generatePegLayout, getMultipliers, createBall, stepPhysics,
  checkPegCollision, resolveCollision, checkBallCollision, resolveBallCollision,
  checkRailCollision, resolveRailCollision, isRailPeg,
  getSlotIndex,
  type Ball, type Peg, type RiskLevel, type PegLayout,
  PEG_RADIUS, BALL_RADIUS, BOARD_WIDTH, BOARD_HEIGHT, SLOT_COUNT,
} from './plinkoEngine'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { useGameSFX } from '../../../audio/useGameSFX'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

// ── Help modal ──────────────────────────────────────────────────────
function PlinkoHelp({ onClose }: { onClose: () => void }) {
  const Sec = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div className="mb-4"><h3 className="text-sm font-semibold text-slate-200 mb-1">{title}</h3><div className="text-xs leading-relaxed text-slate-400">{children}</div></div>
  )
  const Li = ({ children }: { children: React.ReactNode }) => (
    <li className="flex gap-1.5 text-xs"><span className="text-slate-600 mt-0.5">&bull;</span><span>{children}</span></li>
  )
  const B = ({ children }: { children: React.ReactNode }) => <span className="text-white font-medium">{children}</span>

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6" onClick={e => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white"><X className="w-5 h-5" /></button>
        <h2 className="text-lg font-bold text-white mb-4">How to Play Plinko</h2>

        <Sec title="Goal">
          <p>Drop balls from the top of the board and watch them bounce through pegs into multiplier slots at the bottom. Maximize your balance by landing on high-value slots.</p>
        </Sec>

        <Sec title="How to Play">
          <ul className="space-y-1">
            <Li><B>Click or tap</B> the board to drop a ball from the center (with slight random variance).</Li>
            <Li>Each drop costs your current <B>bet amount</B>, deducted from your balance.</Li>
            <Li>The ball bounces off pegs and lands in a <B>multiplier slot</B> at the bottom.</Li>
            <Li>Your payout is <B>bet × slot multiplier</B>.</Li>
            <Li>You can drop multiple balls at once — they even collide with each other!</Li>
          </ul>
        </Sec>

        <Sec title="Risk Levels">
          <ul className="space-y-1">
            <Li><B>Low</B> — Multipliers range 0.3× to 1.5×. Safer, smaller swings.</Li>
            <Li><B>Medium</B> — Multipliers range 0.2× to 3×. Balanced risk/reward.</Li>
            <Li><B>High</B> — Multipliers range 0.2× to 10×. High variance, big potential wins.</Li>
          </ul>
          <p className="mt-1">Edge slots pay the most; center slots pay the least (bell-curve distribution).</p>
        </Sec>

        <Sec title="Board Layouts">
          <ul className="space-y-1">
            <Li><B>Classic</B> — Slot-aligned pegs, natural stagger for even distribution.</Li>
            <Li><B>Pyramid</B> — Fewer pegs at top, expanding toward bottom with edge rails.</Li>
          </ul>
        </Sec>

        <Sec title="Betting">
          <ul className="space-y-1">
            <Li>Set your bet using the input field or the <B>½×</B>, <B>2×</B>, <B>Max</B> buttons.</Li>
            <Li>Minimum bet is <B>10</B>. You start with a balance of <B>1,000</B>.</Li>
            <Li>When your balance drops below your bet, the game ends — click <B>New Game</B> to reset.</Li>
          </ul>
        </Sec>

        <Sec title="Strategy Tips">
          <ul className="space-y-1">
            <Li>Low risk is great for steady play — you rarely lose big.</Li>
            <Li>High risk is boom-or-bust — edge slots pay 10× but the center is 0.2×.</Li>
            <Li>The Classic layout gives the most predictable distribution.</Li>
            <Li>Dropping multiple balls at once doesn't change odds — each bounce is independent.</Li>
          </ul>
        </Sec>
      </div>
    </div>
  )
}

const MIN_BET = 10
const INITIAL_BALANCE = 1000
const SLOT_HEIGHT = 30
const PEG_LAYOUTS: { value: PegLayout; label: string }[] = [
  { value: 'classic', label: 'Classic' },
  { value: 'pyramid', label: 'Pyramid' },
]

interface PegFlash {
  pegIdx: number
  frame: number
}

interface SlotLanding {
  slotIdx: number
  frame: number       // countdown frames (total ~40 = ~0.67s at 60fps)
  totalFrames: number  // starting frame count for easing
}

interface PlinkoState {
  balance: number
  bet: number
  risk: RiskLevel
  layout: PegLayout
  lastWin: { amount: number; multiplier: number } | null
}

function getSlotColor(multiplier: number): string {
  if (multiplier >= 3) return '#facc15'   // gold
  if (multiplier >= 1) return '#22c55e'   // green
  return '#ef4444'                         // red
}

function getScaleForContainer(containerWidth: number): number {
  // Fit within both container width and available viewport height
  const widthScale = containerWidth / BOARD_WIDTH
  // Reserve ~260px for header, controls, and bottom text
  const availableHeight = window.innerHeight - 260
  const heightScale = availableHeight / (BOARD_HEIGHT + SLOT_HEIGHT)
  return Math.min(1, widthScale, heightScale)
}

function PlinkoSinglePlayer({ onGameEnd }: {
  onGameEnd?: (result: 'win' | 'loss' | 'draw', score?: number) => void
} = {}) {
  const { load, save, clear } = useGameState<PlinkoState>('plinko')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('plinko'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('plinko')

  const [gameStatus, setGameStatus] = useState<GameStatus>(saved ? 'playing' : 'idle')
  const [balance, setBalance] = useState(saved?.balance ?? INITIAL_BALANCE)
  const [bet, setBet] = useState(saved?.bet ?? MIN_BET)
  const [risk, setRisk] = useState<RiskLevel>(saved?.risk ?? 'medium')
  const [layout, setLayout] = useState<PegLayout>(saved?.layout ?? 'classic')
  const [lastWin, setLastWin] = useState<{ amount: number; multiplier: number } | null>(saved?.lastWin ?? null)
  const [ballsActive, setBallsActive] = useState(false)
  const [showHelp, setShowHelp] = useState(false)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const ballsRef = useRef<Ball[]>([])
  const flashesRef = useRef<PegFlash[]>([])
  const slotLandingsRef = useRef<SlotLanding[]>([])
  const pegsRef = useRef<Peg[]>(generatePegLayout(saved?.layout ?? 'classic'))
  const balanceRef = useRef(saved?.balance ?? INITIAL_BALANCE)
  const betRef = useRef(saved?.bet ?? MIN_BET)
  const riskRef = useRef<RiskLevel>(saved?.risk ?? 'medium')
  const animFrameRef = useRef<number>(0)
  const scaleRef = useRef(1)

  // Keep refs in sync
  useEffect(() => { betRef.current = bet }, [bet])
  useEffect(() => { riskRef.current = risk }, [risk])

  // Persist state on changes
  useEffect(() => {
    save({ balance, bet, risk, layout, lastWin })
  }, [balance, bet, risk, layout, lastWin, save])

  const drawBoard = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const scale = scaleRef.current
    const w = BOARD_WIDTH * scale
    const h = (BOARD_HEIGHT + SLOT_HEIGHT) * scale

    canvas.width = w
    canvas.height = h

    ctx.save()
    ctx.scale(scale, scale)

    // Background
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, BOARD_WIDTH, BOARD_HEIGHT + SLOT_HEIGHT)

    // Drop zone indicator at top center
    ctx.fillStyle = '#f97316'
    ctx.globalAlpha = 0.3
    ctx.beginPath()
    ctx.moveTo(BOARD_WIDTH / 2 - 20, 5)
    ctx.lineTo(BOARD_WIDTH / 2 + 20, 5)
    ctx.lineTo(BOARD_WIDTH / 2, 20)
    ctx.closePath()
    ctx.fill()
    ctx.globalAlpha = 1

    // Pegs (circular) and rails (angled deflectors)
    const flashSet = new Set(flashesRef.current.map(f => f.pegIdx))
    pegsRef.current.forEach((peg, idx) => {
      const flashing = flashSet.has(idx)
      if (isRailPeg(peg)) {
        ctx.beginPath()
        ctx.moveTo(peg.x, peg.y)
        ctx.lineTo(peg.railEndX!, peg.railEndY!)
        ctx.strokeStyle = flashing ? '#fbbf24' : '#94a3b8'
        ctx.lineWidth = PEG_RADIUS * 2
        ctx.lineCap = 'round'
        ctx.stroke()
      } else {
        ctx.beginPath()
        ctx.arc(peg.x, peg.y, PEG_RADIUS, 0, Math.PI * 2)
        ctx.fillStyle = flashing ? '#fbbf24' : '#64748b'
        ctx.fill()
      }
    })

    // Slot separator pegs — small pegs at slot boundaries to guide balls
    const slotWidth = BOARD_WIDTH / SLOT_COUNT
    const separatorRadius = PEG_RADIUS * 0.8
    const separatorY = BOARD_HEIGHT - 5
    for (let i = 0; i <= SLOT_COUNT; i++) {
      const sx = i * slotWidth
      ctx.beginPath()
      ctx.arc(sx, separatorY, separatorRadius, 0, Math.PI * 2)
      ctx.fillStyle = '#94a3b8'
      ctx.fill()
    }

    // Slot dividers and labels
    const multipliers = getMultipliers(riskRef.current)
    const landingSet = new Map<number, SlotLanding>()
    for (const sl of slotLandingsRef.current) landingSet.set(sl.slotIdx, sl)

    for (let i = 0; i < SLOT_COUNT; i++) {
      const sx = i * slotWidth
      let sy = BOARD_HEIGHT
      const m = multipliers[i]
      const landing = landingSet.get(i)

      ctx.save()

      // Spring push-down + flash effect when ball lands
      if (landing) {
        const progress = 1 - landing.frame / landing.totalFrames // 0→1
        // Damped spring: push down then bounce back
        const spring = Math.sin(progress * Math.PI) * Math.exp(-progress * 2)
        const pushDown = spring * 4  // max 4px push
        sy += pushDown

        // Glow/flash effect — bright at start, fading out
        const flashAlpha = (1 - progress) * 0.6
        ctx.fillStyle = getSlotColor(m)
        ctx.globalAlpha = flashAlpha
        ctx.fillRect(sx, sy - 2, slotWidth, SLOT_HEIGHT + 4)
        ctx.globalAlpha = 1
      }

      // Slot background
      ctx.fillStyle = getSlotColor(m)
      ctx.globalAlpha = landing ? 0.5 : 0.25
      ctx.fillRect(sx, sy, slotWidth, SLOT_HEIGHT)
      ctx.globalAlpha = 1

      // Slot border
      ctx.strokeStyle = getSlotColor(m)
      ctx.lineWidth = landing ? 2 : 1
      ctx.strokeRect(sx, sy, slotWidth, SLOT_HEIGHT)

      // Multiplier label
      ctx.fillStyle = '#fff'
      ctx.font = landing ? 'bold 11px sans-serif' : 'bold 10px sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(`${m}x`, sx + slotWidth / 2, sy + SLOT_HEIGHT / 2)

      ctx.restore()
    }

    // Balls with trail effect
    for (const ball of ballsRef.current) {
      // Trail
      ctx.beginPath()
      ctx.arc(ball.x, ball.y - 2, BALL_RADIUS * 0.7, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(249, 115, 22, 0.3)'
      ctx.fill()

      // Main ball
      ctx.beginPath()
      ctx.arc(ball.x, ball.y, BALL_RADIUS, 0, Math.PI * 2)
      ctx.fillStyle = '#f97316'
      ctx.fill()
    }

    ctx.restore()
  }, [])

  // Regenerate pegs when layout changes and redraw immediately
  useEffect(() => {
    pegsRef.current = generatePegLayout(layout)
    drawBoard()
  }, [layout, drawBoard])

  // Redraw when risk changes so slot multiplier labels update immediately
  useEffect(() => {
    drawBoard()
  }, [risk, drawBoard])

  const tick = useCallback(() => {
    // Decay flashes
    flashesRef.current = flashesRef.current
      .map(f => ({ ...f, frame: f.frame - 1 }))
      .filter(f => f.frame > 0)

    // Decay slot landing animations
    slotLandingsRef.current = slotLandingsRef.current
      .map(sl => ({ ...sl, frame: sl.frame - 1 }))
      .filter(sl => sl.frame > 0)

    // Update each ball
    const landed: { slotIdx: number; bet: number }[] = []
    const activeBalls: Ball[] = []

    for (let ball of ballsRef.current) {
      ball = stepPhysics(ball)

      // Collision with pegs and rails
      const currentPegs = pegsRef.current
      for (let pi = 0; pi < currentPegs.length; pi++) {
        const p = currentPegs[pi]
        const hit = isRailPeg(p)
          ? checkRailCollision(ball, p)
          : checkPegCollision(ball, p)
        if (hit) {
          ball = isRailPeg(p)
            ? resolveRailCollision(ball, p)
            : resolveCollision(ball, p)
          // Flash peg/rail
          if (!flashesRef.current.some(f => f.pegIdx === pi)) {
            flashesRef.current.push({ pegIdx: pi, frame: 8 })
            sfx.play('bounce')
          }
        }
      }

      // Collision with slot separator pegs at the bottom
      const sepSlotWidth = BOARD_WIDTH / SLOT_COUNT
      const sepY = BOARD_HEIGHT - 5
      const sepRadius = PEG_RADIUS * 0.8
      for (let si = 0; si <= SLOT_COUNT; si++) {
        const sepPeg: Peg = { x: si * sepSlotWidth, y: sepY, row: -1 }
        const dx = ball.x - sepPeg.x
        const dy = ball.y - sepPeg.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist <= BALL_RADIUS + sepRadius) {
          ball = resolveCollision(ball, sepPeg)
        }
      }

      // Clamp horizontal bounds
      if (ball.x < BALL_RADIUS) {
        ball = { ...ball, x: BALL_RADIUS, vx: Math.abs(ball.vx) * 0.5 }
      } else if (ball.x > BOARD_WIDTH - BALL_RADIUS) {
        ball = { ...ball, x: BOARD_WIDTH - BALL_RADIUS, vx: -Math.abs(ball.vx) * 0.5 }
      }

      // Check if reached bottom
      if (ball.y >= BOARD_HEIGHT - 10) {
        const slotIdx = getSlotIndex(ball.x, BOARD_WIDTH)
        sfx.play('land')
        landed.push({ slotIdx, bet: ball.bet })
      } else {
        activeBalls.push(ball)
      }
    }

    // Ball-to-ball collisions (check each pair)
    for (let i = 0; i < activeBalls.length; i++) {
      for (let j = i + 1; j < activeBalls.length; j++) {
        if (checkBallCollision(activeBalls[i], activeBalls[j])) {
          const [newA, newB] = resolveBallCollision(activeBalls[i], activeBalls[j])
          activeBalls[i] = newA
          activeBalls[j] = newB
        }
      }
    }

    ballsRef.current = activeBalls

    // Process landings
    if (landed.length > 0) {
      const multipliers = getMultipliers(riskRef.current)
      let totalWin = 0
      let lastMultiplier = 0
      for (const { slotIdx, bet: ballBet } of landed) {
        const m = multipliers[slotIdx]
        const win = Math.round(ballBet * m)
        totalWin += win
        lastMultiplier = m
        // Trigger slot landing spring animation
        const landingFrames = 40
        if (!slotLandingsRef.current.some(sl => sl.slotIdx === slotIdx)) {
          slotLandingsRef.current.push({ slotIdx, frame: landingFrames, totalFrames: landingFrames })
        } else {
          // Reset the animation if same slot hit again
          const existing = slotLandingsRef.current.find(sl => sl.slotIdx === slotIdx)!
          existing.frame = landingFrames
        }
      }
      balanceRef.current += totalWin
      setBalance(balanceRef.current)
      setLastWin({ amount: totalWin, multiplier: lastMultiplier })
      if (lastMultiplier >= 1) {
        sfx.play('win')
      }
      // Report current balance as score for race mode
      onGameEnd?.('win', balanceRef.current)
    }

    drawBoard()

    // Keep animating if there are active balls or landing animations still playing
    if (activeBalls.length > 0 || slotLandingsRef.current.length > 0) {
      animFrameRef.current = requestAnimationFrame(tick)
    } else {
      setBallsActive(false)
      // Auto-adjust bet down if balance dropped below current bet but is still playable
      if (balanceRef.current < betRef.current && balanceRef.current >= MIN_BET) {
        betRef.current = balanceRef.current
        setBet(balanceRef.current)
      }
    }
  }, [drawBoard])

  const dropBall = useCallback(() => {
    if (betRef.current < MIN_BET || balanceRef.current < betRef.current) return

    music.init()
    sfx.init()
    music.start()

    // Ball drops from center with small random variance (±15px)
    // Pegs create the randomness, not the click position
    const variance = (Math.random() - 0.5) * 30
    const dropX = BOARD_WIDTH / 2 + variance

    // Deduct bet
    balanceRef.current -= betRef.current
    setBalance(balanceRef.current)
    setGameStatus('playing')
    setBallsActive(true)

    sfx.play('drop')
    const ball = createBall(dropX, betRef.current)
    ballsRef.current.push(ball)

    // Start animation if not already running
    if (ballsRef.current.length === 1) {
      animFrameRef.current = requestAnimationFrame(tick)
    }
  }, [tick])

  const handleDrop = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    dropBall()
  }, [dropBall])

  // Resize observer for responsive canvas
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const updateScale = () => {
      const w = container.clientWidth
      scaleRef.current = getScaleForContainer(w)
      drawBoard()
    }

    updateScale()
    const observer = new ResizeObserver(updateScale)
    observer.observe(container)
    return () => observer.disconnect()
  }, [drawBoard])

  // Initial draw
  useEffect(() => { drawBoard() }, [drawBoard])

  // Cleanup animation frame
  useEffect(() => {
    return () => { cancelAnimationFrame(animFrameRef.current) }
  }, [])

  const resetGame = useCallback(() => {
    ballsRef.current = []
    flashesRef.current = []
    slotLandingsRef.current = []
    balanceRef.current = INITIAL_BALANCE
    setBalance(INITIAL_BALANCE)
    setLastWin(null)
    setGameStatus('idle')
    cancelAnimationFrame(animFrameRef.current)
    clear()
    drawBoard()
  }, [drawBoard, clear])

  const handleBetChange = useCallback((value: string) => {
    const num = parseInt(value, 10)
    if (!isNaN(num) && num >= MIN_BET) {
      setBet(num)
    }
  }, [])

  const controls = (
    <div className="flex flex-col gap-2.5">
      {/* Row 1: Risk + Layout */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400 w-10">Risk</span>
          {(['low', 'medium', 'high'] as RiskLevel[]).map(level => (
            <button
              key={level}
              onClick={() => setRisk(level)}
              disabled={ballsActive}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors capitalize ${
                risk === level
                  ? level === 'low' ? 'bg-emerald-900/50 text-emerald-400'
                    : level === 'medium' ? 'bg-yellow-900/50 text-yellow-400'
                    : 'bg-red-900/50 text-red-400'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
              } ${ballsActive ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {level}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400 w-12">Board</span>
          {PEG_LAYOUTS.map(l => (
            <button
              key={l.value}
              onClick={() => setLayout(l.value)}
              disabled={ballsActive}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                layout === l.value
                  ? 'bg-blue-900/50 text-blue-400'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
              } ${ballsActive ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>

      {/* Row 2: Bet input + multiplier buttons */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400 w-10">Bet</span>
          <input
            type="number"
            min={MIN_BET}
            max={balance}
            value={bet}
            onChange={e => handleBetChange(e.target.value)}
            className="w-20 px-2 py-1 rounded text-xs font-mono bg-slate-700 text-white border border-slate-600 text-right"
          />
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setBet(b => Math.max(MIN_BET, Math.floor(b / 2)))}
            className="px-2 py-1 rounded text-xs font-medium bg-slate-700/50 text-slate-400 hover:bg-slate-700 transition-colors"
          >
            ½×
          </button>
          <button
            onClick={() => setBet(b => Math.min(balance, b * 2))}
            className="px-2 py-1 rounded text-xs font-medium bg-slate-700/50 text-slate-400 hover:bg-slate-700 transition-colors"
          >
            2×
          </button>
          <button
            onClick={() => setBet(balance)}
            className="px-2 py-1 rounded text-xs font-medium bg-slate-700/50 text-slate-400 hover:bg-slate-700 transition-colors"
          >
            Max
          </button>
        </div>
      </div>

      {/* Row 3: Balance + last win + New Game */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">
          Balance: <span className="text-white font-mono">{balance.toLocaleString()}</span>
          <span className="text-slate-500 ml-1">(min {MIN_BET})</span>
        </span>
        <div className="flex items-center gap-2">
          {lastWin && (
            <span className={lastWin.multiplier >= 1 ? 'text-emerald-400' : 'text-red-400'}>
              {lastWin.multiplier >= 1 ? '+' : ''}{lastWin.amount} ({lastWin.multiplier}x)
            </span>
          )}
          <button
            onClick={resetGame}
            className="px-2 py-0.5 rounded text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
          >
            New Game
          </button>
          <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play">
            <HelpCircle className="w-4 h-4 text-blue-400" />
          </button>
          <MusicToggle music={music} sfx={sfx} />
        </div>
      </div>
    </div>
  )

  return (
    <GameLayout title="Plinko" score={balance} controls={controls}>
      <div className="relative flex flex-col items-center space-y-4" ref={containerRef}>
        <canvas
          ref={canvasRef}
          className="rounded-lg border border-slate-700 cursor-pointer max-w-full"
          style={{ touchAction: 'none' }}
          onPointerDown={handleDrop}
        />

        {/* Start overlay */}
        {gameStatus === 'idle' && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/70 rounded-lg">
            <div className="text-center space-y-3">
              <p className="text-white font-semibold">Click or tap to drop a ball</p>
              <button
                onPointerDown={() => {
                  setGameStatus('playing')
                  dropBall()
                }}
                className="px-6 py-3 bg-orange-600 hover:bg-orange-500 text-white rounded-lg font-semibold transition-colors"
              >
                Drop Ball
              </button>
            </div>
          </div>
        )}

        {/* Out of funds — only when balance is truly below minimum bet */}
        {balance < MIN_BET && ballsRef.current.length === 0 && gameStatus === 'playing' && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/70 rounded-lg">
            <div className="text-center space-y-3">
              <p className="text-white font-semibold">Out of funds!</p>
              <p className="text-slate-400 text-sm">Final balance: {balance}</p>
              <button
                onClick={resetGame}
                className="px-6 py-3 bg-orange-600 hover:bg-orange-500 text-white rounded-lg font-semibold transition-colors"
              >
                Play Again
              </button>
            </div>
          </div>
        )}

        <p className="text-xs text-slate-500">
          Click the board to drop a ball. Pegs bounce it randomly into a slot.
        </p>
      </div>
      {showHelp && <PlinkoHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper ──────────────────────────────────────────────────

function PlinkoRaceWrapper({ roomId, onLeave }: { roomId: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, localScore, opponentLevelUp, broadcastState: _broadcastState, reportScore, reportFinish, leaveRoom } =
    useRaceMode(roomId, 'best_score')
  const finishedRef = useRef(false)
  const bestScoreRef = useRef(0)

  const handleGameEnd = useCallback((_result: 'win' | 'loss' | 'draw', score?: number) => {
    const currentScore = score ?? 0
    if (currentScore > bestScoreRef.current) {
      bestScoreRef.current = currentScore
      reportScore(currentScore)
    }
  }, [reportScore])

  // Report finish when component unmounts (user leaves) or on explicit end
  useEffect(() => {
    return () => {
      if (!finishedRef.current) {
        finishedRef.current = true
        reportFinish('win', bestScoreRef.current)
      }
    }
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
        onBackToLobby={onLeave}
        onLeaveGame={leaveRoom}
      />
      <PlinkoSinglePlayer onGameEnd={handleGameEnd} />
    </div>
  )
}

export default function Plinko() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'plinko',
        gameName: 'Plinko',
        modes: ['best_score'],
        maxPlayers: 2,
        hasDifficulty: false,
        modeDescriptions: { best_score: 'Highest balance wins' },
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <PlinkoSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, _roomConfig, onLeave) =>
        <PlinkoRaceWrapper roomId={roomId} onLeave={onLeave} />
      }
    />
  )
}
