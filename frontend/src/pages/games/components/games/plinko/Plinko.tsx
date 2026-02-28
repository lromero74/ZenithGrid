/**
 * Plinko game — canvas-based ball-drop arcade game.
 *
 * Features: click/tap to drop balls, risk level selector,
 * multiple simultaneous balls, balance/bet system, color-coded slots.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import {
  generatePegLayout, getMultipliers, createBall, stepPhysics,
  checkPegCollision, resolveCollision, getSlotIndex,
  type Ball, type RiskLevel,
  PEG_RADIUS, BALL_RADIUS, BOARD_WIDTH, BOARD_HEIGHT, SLOT_COUNT,
} from './plinkoEngine'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'

const BET_OPTIONS = [10, 25, 50, 100]
const INITIAL_BALANCE = 1000
const SLOT_HEIGHT = 30
const pegs = generatePegLayout()

interface PegFlash {
  pegIdx: number
  frame: number
}

interface PlinkoState {
  balance: number
  bet: number
  risk: RiskLevel
  lastWin: { amount: number; multiplier: number } | null
}

function getSlotColor(multiplier: number): string {
  if (multiplier >= 3) return '#facc15'   // gold
  if (multiplier >= 1) return '#22c55e'   // green
  return '#ef4444'                         // red
}

function getScaleForContainer(containerWidth: number): number {
  return Math.min(1, containerWidth / BOARD_WIDTH)
}

export default function Plinko() {
  const { load, save, clear } = useGameState<PlinkoState>('plinko')
  const saved = useRef(load()).current

  const [gameStatus, setGameStatus] = useState<GameStatus>(saved ? 'playing' : 'idle')
  const [balance, setBalance] = useState(saved?.balance ?? INITIAL_BALANCE)
  const [bet, setBet] = useState(saved?.bet ?? BET_OPTIONS[0])
  const [risk, setRisk] = useState<RiskLevel>(saved?.risk ?? 'medium')
  const [lastWin, setLastWin] = useState<{ amount: number; multiplier: number } | null>(saved?.lastWin ?? null)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const ballsRef = useRef<Ball[]>([])
  const flashesRef = useRef<PegFlash[]>([])
  const balanceRef = useRef(saved?.balance ?? INITIAL_BALANCE)
  const betRef = useRef(saved?.bet ?? BET_OPTIONS[0])
  const riskRef = useRef<RiskLevel>(saved?.risk ?? 'medium')
  const animFrameRef = useRef<number>(0)
  const scaleRef = useRef(1)

  // Keep refs in sync
  useEffect(() => { betRef.current = bet }, [bet])
  useEffect(() => { riskRef.current = risk }, [risk])

  // Persist state on changes
  useEffect(() => {
    save({ balance, bet, risk, lastWin })
  }, [balance, bet, risk, lastWin, save])

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

    // Pegs
    const flashSet = new Set(flashesRef.current.map(f => f.pegIdx))
    pegs.forEach((peg, idx) => {
      ctx.beginPath()
      ctx.arc(peg.x, peg.y, PEG_RADIUS, 0, Math.PI * 2)
      ctx.fillStyle = flashSet.has(idx) ? '#fbbf24' : '#64748b'
      ctx.fill()
    })

    // Slot dividers and labels
    const multipliers = getMultipliers(riskRef.current)
    const slotWidth = BOARD_WIDTH / SLOT_COUNT
    for (let i = 0; i < SLOT_COUNT; i++) {
      const sx = i * slotWidth
      const sy = BOARD_HEIGHT
      const m = multipliers[i]

      // Slot background
      ctx.fillStyle = getSlotColor(m)
      ctx.globalAlpha = 0.25
      ctx.fillRect(sx, sy, slotWidth, SLOT_HEIGHT)
      ctx.globalAlpha = 1

      // Slot border
      ctx.strokeStyle = getSlotColor(m)
      ctx.lineWidth = 1
      ctx.strokeRect(sx, sy, slotWidth, SLOT_HEIGHT)

      // Multiplier label
      ctx.fillStyle = '#fff'
      ctx.font = 'bold 10px sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(`${m}x`, sx + slotWidth / 2, sy + SLOT_HEIGHT / 2)
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

  const tick = useCallback(() => {
    // Decay flashes
    flashesRef.current = flashesRef.current
      .map(f => ({ ...f, frame: f.frame - 1 }))
      .filter(f => f.frame > 0)

    // Update each ball
    const landed: { slotIdx: number }[] = []
    const activeBalls: Ball[] = []

    for (let ball of ballsRef.current) {
      ball = stepPhysics(ball)

      // Collision with pegs
      for (let pi = 0; pi < pegs.length; pi++) {
        if (checkPegCollision(ball, pegs[pi])) {
          ball = resolveCollision(ball, pegs[pi])
          // Flash peg
          if (!flashesRef.current.some(f => f.pegIdx === pi)) {
            flashesRef.current.push({ pegIdx: pi, frame: 8 })
          }
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
        landed.push({ slotIdx })
      } else {
        activeBalls.push(ball)
      }
    }

    ballsRef.current = activeBalls

    // Process landings
    if (landed.length > 0) {
      const multipliers = getMultipliers(riskRef.current)
      let totalWin = 0
      let lastMultiplier = 0
      for (const { slotIdx } of landed) {
        const m = multipliers[slotIdx]
        const win = Math.round(betRef.current * m)
        totalWin += win
        lastMultiplier = m
      }
      balanceRef.current += totalWin
      setBalance(balanceRef.current)
      setLastWin({ amount: totalWin, multiplier: lastMultiplier })
    }

    drawBoard()

    if (activeBalls.length > 0) {
      animFrameRef.current = requestAnimationFrame(tick)
    }
  }, [drawBoard])

  const dropBall = useCallback((clientX: number) => {
    const canvas = canvasRef.current
    if (!canvas) return

    if (balanceRef.current < betRef.current) return

    const rect = canvas.getBoundingClientRect()
    const scale = scaleRef.current
    const x = (clientX - rect.left) / scale

    // Clamp x within board
    const clampedX = Math.max(BALL_RADIUS + 10, Math.min(BOARD_WIDTH - BALL_RADIUS - 10, x))

    // Deduct bet
    balanceRef.current -= betRef.current
    setBalance(balanceRef.current)
    setGameStatus('playing')

    const ball = createBall(clampedX)
    ballsRef.current.push(ball)

    // Start animation if not already running
    if (ballsRef.current.length === 1) {
      animFrameRef.current = requestAnimationFrame(tick)
    }
  }, [tick])

  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    dropBall(e.clientX)
  }, [dropBall])

  const handleCanvasTouch = useCallback((e: React.TouchEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    const touch = e.touches[0]
    if (touch) dropBall(touch.clientX)
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
    balanceRef.current = INITIAL_BALANCE
    setBalance(INITIAL_BALANCE)
    setLastWin(null)
    setGameStatus('idle')
    cancelAnimationFrame(animFrameRef.current)
    clear()
    drawBoard()
  }, [drawBoard, clear])

  const controls = (
    <div className="flex flex-col gap-3">
      {/* Risk level */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">Risk</span>
        <div className="flex gap-1">
          {(['low', 'medium', 'high'] as RiskLevel[]).map(level => (
            <button
              key={level}
              onClick={() => setRisk(level)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors capitalize ${
                risk === level
                  ? level === 'low' ? 'bg-emerald-900/50 text-emerald-400'
                    : level === 'medium' ? 'bg-yellow-900/50 text-yellow-400'
                    : 'bg-red-900/50 text-red-400'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
              }`}
            >
              {level}
            </button>
          ))}
        </div>
      </div>

      {/* Bet selector */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">Bet</span>
        <div className="flex gap-1">
          {BET_OPTIONS.map(b => (
            <button
              key={b}
              onClick={() => setBet(b)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                bet === b
                  ? 'bg-orange-900/50 text-orange-400'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
              }`}
            >
              {b}
            </button>
          ))}
        </div>
      </div>

      {/* Balance + last win */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">
          Balance: <span className="text-white font-mono">{balance.toLocaleString()}</span>
        </span>
        {lastWin && (
          <span className={lastWin.multiplier >= 1 ? 'text-emerald-400' : 'text-red-400'}>
            {lastWin.multiplier >= 1 ? '+' : ''}{lastWin.amount} ({lastWin.multiplier}x)
          </span>
        )}
      </div>
    </div>
  )

  return (
    <GameLayout title="Plinko" score={balance} controls={controls}>
      <div className="relative flex flex-col items-center space-y-4" ref={containerRef}>
        <canvas
          ref={canvasRef}
          className="rounded-lg border border-slate-700 cursor-pointer"
          style={{ touchAction: 'none' }}
          onClick={handleCanvasClick}
          onTouchStart={handleCanvasTouch}
        />

        {/* Start overlay */}
        {gameStatus === 'idle' && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/70 rounded-lg">
            <div className="text-center space-y-3">
              <p className="text-white font-semibold">Click or tap to drop a ball</p>
              <button
                onClick={() => {
                  setGameStatus('playing')
                  dropBall(BOARD_WIDTH / 2 * scaleRef.current + (canvasRef.current?.getBoundingClientRect().left ?? 0))
                }}
                className="px-6 py-3 bg-orange-600 hover:bg-orange-500 text-white rounded-lg font-semibold transition-colors"
              >
                Drop Ball
              </button>
            </div>
          </div>
        )}

        {/* Out of funds */}
        {balance < bet && ballsRef.current.length === 0 && gameStatus === 'playing' && (
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
          Click anywhere on the board to drop a ball. Choose your risk and bet amount above.
        </p>
      </div>
    </GameLayout>
  )
}
