/**
 * Snake game — canvas-based arcade game.
 *
 * Features: keyboard + swipe + D-pad controls, wall/wrap modes,
 * speed progression, high score tracking.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Pause, Play } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import {
  getNextHead, moveSnake, checkWallCollision, checkSelfCollision,
  isOppositeDirection, wrapPosition, generateFood, getSpeed,
  type Position, type Direction,
} from './snakeEngine'
import type { GameStatus } from '../../../types'

const GRID_SIZE = 20
const CELL_SIZE_DESKTOP = 20
const CELL_SIZE_MOBILE = 16

function getCellSize() {
  return window.innerWidth < 640 ? CELL_SIZE_MOBILE : CELL_SIZE_DESKTOP
}

const INITIAL_SNAKE: Position[] = [
  { x: 10, y: 10 }, { x: 9, y: 10 }, { x: 8, y: 10 },
]

export default function Snake() {
  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [score, setScore] = useState(0)
  const [wallsMode, setWallsMode] = useState(true) // true = walls kill
  const { getHighScore, saveScore } = useGameScores()
  const bestScore = getHighScore('snake') ?? 0

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const snakeRef = useRef<Position[]>([...INITIAL_SNAKE])
  const directionRef = useRef<Direction>('RIGHT')
  const nextDirectionRef = useRef<Direction>('RIGHT')
  const foodRef = useRef<Position>(generateFood(INITIAL_SNAKE, GRID_SIZE))
  const scoreRef = useRef(0)
  const gameLoopRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const gameStatusRef = useRef<GameStatus>('idle')
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const cellSize = getCellSize()
    const canvasSize = GRID_SIZE * cellSize
    canvas.width = canvasSize
    canvas.height = canvasSize

    // Background
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, canvasSize, canvasSize)

    // Grid lines
    ctx.strokeStyle = '#1e293b'
    ctx.lineWidth = 0.5
    for (let i = 0; i <= GRID_SIZE; i++) {
      ctx.beginPath(); ctx.moveTo(i * cellSize, 0); ctx.lineTo(i * cellSize, canvasSize); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(0, i * cellSize); ctx.lineTo(canvasSize, i * cellSize); ctx.stroke()
    }

    // Food
    const food = foodRef.current
    ctx.fillStyle = '#f87171'
    ctx.beginPath()
    ctx.arc(food.x * cellSize + cellSize / 2, food.y * cellSize + cellSize / 2, cellSize / 2 - 1, 0, Math.PI * 2)
    ctx.fill()

    // Snake
    const snake = snakeRef.current
    snake.forEach((seg, i) => {
      const brightness = Math.max(0.4, 1 - i * 0.05)
      ctx.fillStyle = i === 0 ? '#34d399' : `rgba(16, 185, 129, ${brightness})`
      ctx.fillRect(seg.x * cellSize + 1, seg.y * cellSize + 1, cellSize - 2, cellSize - 2)
    })
  }, [])

  const gameOver = useCallback(() => {
    gameStatusRef.current = 'lost'
    setGameStatus('lost')
    if (gameLoopRef.current) clearTimeout(gameLoopRef.current)
    saveScore('snake', scoreRef.current)
  }, [saveScore])

  const tick = useCallback(() => {
    if (gameStatusRef.current !== 'playing') return

    directionRef.current = nextDirectionRef.current
    const newHead = getNextHead(snakeRef.current[0], directionRef.current)

    // Wall handling
    if (wallsMode) {
      if (checkWallCollision(newHead, GRID_SIZE)) { gameOver(); return }
    } else {
      const wrapped = wrapPosition(newHead, GRID_SIZE)
      newHead.x = wrapped.x; newHead.y = wrapped.y
    }

    const ateFood = newHead.x === foodRef.current.x && newHead.y === foodRef.current.y
    snakeRef.current = moveSnake(snakeRef.current, directionRef.current, ateFood)
    // Correct head position for wrap mode
    snakeRef.current[0] = newHead

    if (checkSelfCollision(snakeRef.current)) { gameOver(); return }

    if (ateFood) {
      scoreRef.current += 1
      setScore(scoreRef.current)
      foodRef.current = generateFood(snakeRef.current, GRID_SIZE)
    }

    draw()
    gameLoopRef.current = setTimeout(tick, getSpeed(scoreRef.current))
  }, [wallsMode, draw, gameOver])

  const startGame = useCallback(() => {
    snakeRef.current = [...INITIAL_SNAKE.map(p => ({ ...p }))]
    directionRef.current = 'RIGHT'
    nextDirectionRef.current = 'RIGHT'
    foodRef.current = generateFood(INITIAL_SNAKE, GRID_SIZE)
    scoreRef.current = 0
    setScore(0)
    gameStatusRef.current = 'playing'
    setGameStatus('playing')
    draw()
    gameLoopRef.current = setTimeout(tick, getSpeed(0))
  }, [draw, tick])

  const togglePause = useCallback(() => {
    if (gameStatusRef.current === 'playing') {
      gameStatusRef.current = 'idle'
      setGameStatus('idle')
      if (gameLoopRef.current) clearTimeout(gameLoopRef.current)
    } else if (gameStatusRef.current === 'idle' && scoreRef.current > 0) {
      gameStatusRef.current = 'playing'
      setGameStatus('playing')
      gameLoopRef.current = setTimeout(tick, getSpeed(scoreRef.current))
    }
  }, [tick])

  const changeDirection = useCallback((dir: Direction) => {
    if (!isOppositeDirection(directionRef.current, dir)) {
      nextDirectionRef.current = dir
    }
  }, [])

  // Keyboard controls
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const map: Record<string, Direction> = {
        ArrowUp: 'UP', ArrowDown: 'DOWN', ArrowLeft: 'LEFT', ArrowRight: 'RIGHT',
        w: 'UP', s: 'DOWN', a: 'LEFT', d: 'RIGHT',
        W: 'UP', S: 'DOWN', A: 'LEFT', D: 'RIGHT',
      }
      const dir = map[e.key]
      if (dir) { e.preventDefault(); changeDirection(dir) }
      if (e.key === ' ') { e.preventDefault(); togglePause() }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [changeDirection, togglePause])

  // Touch/swipe controls
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const handleTouchStart = (e: TouchEvent) => {
      const t = e.touches[0]
      touchStartRef.current = { x: t.clientX, y: t.clientY }
    }
    const handleTouchEnd = (e: TouchEvent) => {
      if (!touchStartRef.current) return
      const t = e.changedTouches[0]
      const dx = t.clientX - touchStartRef.current.x
      const dy = t.clientY - touchStartRef.current.y
      const minSwipe = 30
      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > minSwipe) {
        changeDirection(dx > 0 ? 'RIGHT' : 'LEFT')
      } else if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > minSwipe) {
        changeDirection(dy > 0 ? 'DOWN' : 'UP')
      }
      touchStartRef.current = null
    }
    canvas.addEventListener('touchstart', handleTouchStart, { passive: true })
    canvas.addEventListener('touchend', handleTouchEnd, { passive: true })
    return () => {
      canvas.removeEventListener('touchstart', handleTouchStart)
      canvas.removeEventListener('touchend', handleTouchEnd)
    }
  }, [changeDirection])

  // Initial draw
  useEffect(() => { draw() }, [draw])

  // Cleanup
  useEffect(() => {
    return () => { if (gameLoopRef.current) clearTimeout(gameLoopRef.current) }
  }, [])

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex space-x-2">
        <button
          onClick={() => setWallsMode(w => !w)}
          className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
            wallsMode ? 'bg-red-900/50 text-red-400' : 'bg-emerald-900/50 text-emerald-400'
          }`}
        >
          Walls: {wallsMode ? 'Kill' : 'Wrap'}
        </button>
      </div>
      <span className="text-xs text-slate-500">
        Level {Math.floor(score / 5) + 1}
      </span>
    </div>
  )

  const cellSize = getCellSize()
  const canvasSize = GRID_SIZE * cellSize

  return (
    <GameLayout title="Snake" score={score} bestScore={bestScore} controls={controls}>
      <div className="relative flex flex-col items-center space-y-4">
        <canvas
          ref={canvasRef}
          width={canvasSize}
          height={canvasSize}
          className="rounded-lg border border-slate-700"
          style={{ touchAction: 'none' }}
        />

        {/* Start / Pause overlay */}
        {gameStatus === 'idle' && score === 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/70 rounded-lg">
            <button
              onClick={startGame}
              className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold transition-colors"
            >
              Start Game
            </button>
          </div>
        )}

        {/* Mobile D-pad */}
        <div className="flex flex-col items-center space-y-1 sm:hidden">
          <button onClick={() => changeDirection('UP')} className="w-12 h-12 bg-slate-700 rounded-lg flex items-center justify-center active:bg-slate-600">
            <ArrowUp className="w-5 h-5 text-slate-300" />
          </button>
          <div className="flex space-x-1">
            <button onClick={() => changeDirection('LEFT')} className="w-12 h-12 bg-slate-700 rounded-lg flex items-center justify-center active:bg-slate-600">
              <ArrowLeft className="w-5 h-5 text-slate-300" />
            </button>
            <button onClick={togglePause} className="w-12 h-12 bg-slate-700 rounded-lg flex items-center justify-center active:bg-slate-600">
              {gameStatus === 'playing' ? <Pause className="w-5 h-5 text-slate-300" /> : <Play className="w-5 h-5 text-slate-300" />}
            </button>
            <button onClick={() => changeDirection('RIGHT')} className="w-12 h-12 bg-slate-700 rounded-lg flex items-center justify-center active:bg-slate-600">
              <ArrowRight className="w-5 h-5 text-slate-300" />
            </button>
          </div>
          <button onClick={() => changeDirection('DOWN')} className="w-12 h-12 bg-slate-700 rounded-lg flex items-center justify-center active:bg-slate-600">
            <ArrowDown className="w-5 h-5 text-slate-300" />
          </button>
        </div>

        {/* Desktop hint */}
        <p className="text-xs text-slate-500 hidden sm:block">
          Arrow keys or WASD to move. Space to pause.
        </p>

        {gameStatus === 'lost' && (
          <GameOverModal
            status="lost"
            score={score}
            bestScore={bestScore}
            onPlayAgain={startGame}
          />
        )}
      </div>
    </GameLayout>
  )
}
