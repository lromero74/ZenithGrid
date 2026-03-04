/**
 * Dino Runner — canvas-based pixel-art endless runner.
 *
 * Features: keyboard + touch controls, variable-height jumps, ducking,
 * day/night cycle, progressive speed, high score tracking.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import {
  createGame, update, getDinoSprite, getObstacleSprite, getSpriteSize,
  CANVAS_WIDTH, CANVAS_HEIGHT, PIXEL_SCALE, GROUND_Y, PALETTE, CLOUD,
  type GameState, type InputState,
} from './dinoRunnerEngine'
import type { GameStatus } from '../../../types'

// ---------------------------------------------------------------------------
// Render helpers
// ---------------------------------------------------------------------------

/** Draw a sprite (2D number array) at (x, y) using the color palette. */
function drawSprite(
  ctx: CanvasRenderingContext2D,
  sprite: number[][],
  x: number,
  y: number,
  scale: number = PIXEL_SCALE,
): void {
  for (let row = 0; row < sprite.length; row++) {
    for (let col = 0; col < sprite[row].length; col++) {
      const color = sprite[row][col]
      if (color === 0) continue
      ctx.fillStyle = PALETTE[color] || '#ff00ff'
      ctx.fillRect(
        Math.floor(x + col * scale),
        Math.floor(y + row * scale),
        scale,
        scale,
      )
    }
  }
}

/** Interpolate between two hex colors. t in [0,1]. */
function lerpColor(a: string, b: string, t: number): string {
  const pa = parseInt(a.slice(1), 16)
  const pb = parseInt(b.slice(1), 16)
  const r = Math.round(((pa >> 16) & 0xff) * (1 - t) + ((pb >> 16) & 0xff) * t)
  const g = Math.round(((pa >> 8) & 0xff) * (1 - t) + ((pb >> 8) & 0xff) * t)
  const bl = Math.round((pa & 0xff) * (1 - t) + (pb & 0xff) * t)
  return `#${((r << 16) | (g << 8) | bl).toString(16).padStart(6, '0')}`
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DinoRunner() {
  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [displayScore, setDisplayScore] = useState(0)
  const [displayHigh, setDisplayHigh] = useState(0)
  const { getHighScore, saveScore } = useGameScores()
  const bestScore = getHighScore('dino-runner') ?? 0

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef<GameState>(createGame(bestScore))
  const inputRef = useRef<InputState>({ jump: false, duck: false })
  const rafRef = useRef<number>(0)
  const gameStatusRef = useRef<GameStatus>('idle')
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  const render = useCallback((state: GameState) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const { nightTransition: nt } = state

    // --- Background ---
    const bgDay = '#f7f7f7'
    const bgNight = '#1a1a2e'
    ctx.fillStyle = lerpColor(bgDay, bgNight, nt)
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)

    // --- Stars (night only) ---
    if (nt > 0) {
      ctx.globalAlpha = nt
      ctx.fillStyle = '#ffffff'
      for (const star of state.stars) {
        ctx.fillRect(star.x, star.y, 2, 2)
      }
      ctx.globalAlpha = 1
    }

    // --- Clouds ---
    const cloudAlpha = 1 - nt * 0.6
    ctx.globalAlpha = cloudAlpha
    for (const cloud of state.clouds) {
      drawSprite(ctx, CLOUD, cloud.x, cloud.y, 2)
    }
    ctx.globalAlpha = 1

    // --- Ground ---
    const groundColor = lerpColor('#8b7355', '#4a4a5a', nt)
    const groundHighlight = lerpColor('#c4a055', '#6a6a7a', nt)
    ctx.fillStyle = groundColor
    ctx.fillRect(0, GROUND_Y + PIXEL_SCALE, CANVAS_WIDTH, CANVAS_HEIGHT - GROUND_Y)

    // Ground texture (repeating bumps)
    ctx.fillStyle = groundHighlight
    for (let x = -state.ground.offset; x < CANVAS_WIDTH; x += 12) {
      ctx.fillRect(x, GROUND_Y + PIXEL_SCALE, 4, 2)
      ctx.fillRect(x + 7, GROUND_Y + PIXEL_SCALE + 4, 2, 2)
    }

    // Ground line
    const lineColor = lerpColor('#5c3d1a', '#3a3a4a', nt)
    ctx.fillStyle = lineColor
    ctx.fillRect(0, GROUND_Y + PIXEL_SCALE - 1, CANVAS_WIDTH, 1)

    // --- Obstacles ---
    for (const obs of state.obstacles) {
      const sprite = getObstacleSprite(obs)
      const size = getSpriteSize(sprite)
      drawSprite(ctx, sprite, obs.x, obs.y - size.h * PIXEL_SCALE, PIXEL_SCALE)
    }

    // --- Dino ---
    const dinoSprite = getDinoSprite(state.dino)
    const dinoSize = getSpriteSize(dinoSprite)
    drawSprite(
      ctx,
      dinoSprite,
      state.dino.x,
      state.dino.y - dinoSize.h * PIXEL_SCALE + PIXEL_SCALE,
      PIXEL_SCALE,
    )

    // --- Score ---
    const scoreColor = lerpColor('#535353', '#cccccc', nt)
    ctx.fillStyle = scoreColor
    ctx.font = 'bold 14px monospace'
    ctx.textAlign = 'right'
    const scoreText = String(Math.floor(state.score)).padStart(5, '0')
    const hiText = `HI ${String(Math.floor(state.highScore)).padStart(5, '0')}`

    // Milestone flash
    if (state.milestoneFlash > 0 && state.milestoneFlash % 4 < 2) {
      ctx.fillStyle = 'transparent'
    }
    ctx.fillText(scoreText, CANVAS_WIDTH - 10, 24)
    ctx.fillStyle = lerpColor('#757575', '#999999', nt)
    ctx.fillText(hiText, CANVAS_WIDTH - 80, 24)

    // --- Waiting overlay ---
    if (state.phase === 'waiting') {
      ctx.fillStyle = lerpColor('#535353', '#cccccc', nt)
      ctx.font = 'bold 16px monospace'
      ctx.textAlign = 'center'
      ctx.fillText('Press SPACE to Start', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 - 10)
      ctx.font = '12px monospace'
      ctx.fillText('SPACE / Tap = Jump  |  DOWN = Duck', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 + 15)
    }

    // --- Game over overlay ---
    if (state.phase === 'dead') {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.3)'
      ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
      ctx.fillStyle = '#ffffff'
      ctx.font = 'bold 20px monospace'
      ctx.textAlign = 'center'
      ctx.fillText('GAME OVER', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 - 10)
      ctx.font = '13px monospace'
      ctx.fillText('Press SPACE to restart', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2 + 15)
    }
  }, [])

  // -----------------------------------------------------------------------
  // Game loop
  // -----------------------------------------------------------------------

  const gameLoop = useCallback(() => {
    const state = stateRef.current
    const next = update(state, inputRef.current)
    stateRef.current = next

    // Sync React state only when needed
    if (next.phase !== state.phase) {
      if (next.phase === 'dead') {
        gameStatusRef.current = 'lost'
        setGameStatus('lost')
        saveScore('dino-runner', Math.floor(next.score))
      } else if (next.phase === 'playing' && state.phase === 'waiting') {
        gameStatusRef.current = 'playing'
        setGameStatus('playing')
      }
    }
    // Update score display periodically (every 5 frames to reduce renders)
    if (next.frameCount % 5 === 0 || next.phase === 'dead') {
      setDisplayScore(Math.floor(next.score))
      setDisplayHigh(Math.floor(next.highScore))
    }

    render(next)
    rafRef.current = requestAnimationFrame(gameLoop)
  }, [render, saveScore])

  const restartGame = useCallback(() => {
    const hi = Math.max(bestScore, Math.floor(stateRef.current.highScore))
    stateRef.current = createGame(hi)
    inputRef.current = { jump: false, duck: false }
    gameStatusRef.current = 'playing'
    setGameStatus('playing')
    setDisplayScore(0)
    // Immediately start with a jump
    inputRef.current.jump = true
  }, [bestScore])

  // -----------------------------------------------------------------------
  // Keyboard controls
  // -----------------------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'ArrowUp') {
        e.preventDefault()
        if (gameStatusRef.current === 'lost') {
          restartGame()
          return
        }
        inputRef.current.jump = true
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        inputRef.current.duck = true
      }
    }
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'ArrowUp') {
        inputRef.current.jump = false
      }
      if (e.key === 'ArrowDown') {
        inputRef.current.duck = false
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('keyup', handleKeyUp)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('keyup', handleKeyUp)
    }
  }, [restartGame])

  // -----------------------------------------------------------------------
  // Touch controls
  // -----------------------------------------------------------------------

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const handleTouchStart = (e: TouchEvent) => {
      e.preventDefault()
      const t = e.touches[0]
      touchStartRef.current = { x: t.clientX, y: t.clientY }

      if (gameStatusRef.current === 'lost') {
        restartGame()
        return
      }
      inputRef.current.jump = true
    }
    const handleTouchEnd = (e: TouchEvent) => {
      if (touchStartRef.current && e.changedTouches.length > 0) {
        const t = e.changedTouches[0]
        const dy = t.clientY - touchStartRef.current.y
        // Swipe down = duck (release jump)
        if (dy > 30) {
          inputRef.current.duck = true
          setTimeout(() => { inputRef.current.duck = false }, 300)
        }
      }
      inputRef.current.jump = false
      touchStartRef.current = null
    }

    canvas.addEventListener('touchstart', handleTouchStart, { passive: false })
    canvas.addEventListener('touchend', handleTouchEnd, { passive: true })
    return () => {
      canvas.removeEventListener('touchstart', handleTouchStart)
      canvas.removeEventListener('touchend', handleTouchEnd)
    }
  }, [restartGame])

  // -----------------------------------------------------------------------
  // Animation frame loop
  // -----------------------------------------------------------------------

  useEffect(() => {
    render(stateRef.current)
    rafRef.current = requestAnimationFrame(gameLoop)
    return () => cancelAnimationFrame(rafRef.current)
  }, [gameLoop, render])

  // -----------------------------------------------------------------------
  // Responsive canvas scaling
  // -----------------------------------------------------------------------

  const controls = (
    <div className="flex items-center justify-between">
      <span className="text-xs text-slate-500">
        Speed: {stateRef.current.speed.toFixed(1)}
      </span>
      <span className="text-xs text-slate-500">
        Space / Tap = Jump  |  Down = Duck
      </span>
    </div>
  )

  return (
    <GameLayout title="Dino Runner" score={displayScore} bestScore={displayHigh} controls={controls}>
      <div className="relative flex flex-col items-center space-y-4">
        <canvas
          ref={canvasRef}
          width={CANVAS_WIDTH}
          height={CANVAS_HEIGHT}
          className="rounded-lg border border-slate-700 w-full"
          style={{
            maxWidth: CANVAS_WIDTH,
            touchAction: 'none',
            imageRendering: 'pixelated',
          }}
        />

        {/* Mobile hint */}
        <p className="text-xs text-slate-500 sm:hidden">
          Tap to jump. Swipe down to duck.
        </p>

        {gameStatus === 'lost' && (
          <GameOverModal
            status="lost"
            score={displayScore}
            bestScore={displayHigh}
            onPlayAgain={restartGame}
          />
        )}
      </div>
    </GameLayout>
  )
}
