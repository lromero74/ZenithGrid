/**
 * Snake game — canvas-based arcade game.
 *
 * Features: keyboard + swipe + D-pad controls, wall/wrap modes,
 * speed progression, high score tracking.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { ArrowUp, ArrowDown, ArrowLeft, ArrowRight, HelpCircle, Pause, Play, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import { useGameState } from '../../../hooks/useGameState'
import {
  getNextHead, moveSnake, checkWallCollision, checkSelfCollision,
  isOppositeDirection, wrapPosition, generateFood, getSpeed,
  type Position, type Direction,
} from './snakeEngine'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { useGameSFX } from '../../../audio/useGameSFX'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

const GRID_SIZE = 20
const CELL_SIZE_DESKTOP = 20
const CELL_SIZE_MOBILE = 14

function getCellSize() {
  return window.innerWidth < 640 ? CELL_SIZE_MOBILE : CELL_SIZE_DESKTOP
}

const INITIAL_SNAKE: Position[] = [
  { x: 10, y: 10 }, { x: 9, y: 10 }, { x: 8, y: 10 },
]

// ── Help modal ──────────────────────────────────────────────────────
function SnakeHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Snake</h2>

        <Sec title="Goal">
          <p>Guide the snake to eat food and grow as long as possible without crashing.</p>
        </Sec>

        <Sec title="How to Play">
          <ul className="space-y-1">
            <Li>The snake moves continuously in the current direction.</Li>
            <Li>Eat the <B>food</B> (colored dot) to grow longer and score a point.</Li>
            <Li>Every <B>5 points</B> the level increases and the snake speeds up.</Li>
            <Li>You cannot reverse direction — turning 180° into yourself isn't allowed.</Li>
          </ul>
        </Sec>

        <Sec title="Wall Modes">
          <ul className="space-y-1">
            <Li><B>Walls: Kill</B> — Hitting the edge ends the game.</Li>
            <Li><B>Walls: Wrap</B> — The snake wraps around to the opposite side.</Li>
          </ul>
        </Sec>

        <Sec title="Controls">
          <ul className="space-y-1">
            <Li><B>Arrow keys / WASD</B> — Change direction.</Li>
            <Li><B>Space / P</B> — Pause/resume.</Li>
            <Li><B>On-screen arrows</B> — Tap for mobile/touch control.</Li>
          </ul>
        </Sec>

        <Sec title="Strategy Tips">
          <ul className="space-y-1">
            <Li>Stay in the center when short — more escape routes.</Li>
            <Li>As you grow, trace a pattern along the edges to avoid trapping yourself.</Li>
            <Li>Wrap mode is more forgiving — use it to learn, then switch to Kill mode for a challenge.</Li>
          </ul>
        </Sec>
      </div>
    </div>
  )
}

interface SnakeSaved { wallsMode: boolean }

function SnakeSinglePlayer({ onGameEnd, onScoreChange, onStateChange: _onStateChange }: { onGameEnd?: (score: number) => void; onScoreChange?: (score: number, level: number) => void; onStateChange?: (state: object, intervalMs?: number) => void } = {}) {
  const { load, save } = useGameState<SnakeSaved>('snake')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('snake'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('snake')

  const [showHelp, setShowHelp] = useState(false)
  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [score, setScore] = useState(0)
  const [wallsMode, setWallsMode] = useState(saved?.wallsMode ?? true)
  const { getHighScore, saveScore } = useGameScores()

  // Persist settings
  useEffect(() => { save({ wallsMode }) }, [wallsMode, save])
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
    sfx.play('die')
    onGameEnd?.(scoreRef.current)
  }, [saveScore, onGameEnd])

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
      sfx.play('eat')
      scoreRef.current += 1
      setScore(scoreRef.current)
      const newLevel = Math.floor(scoreRef.current / 5) + 1
      onScoreChange?.(scoreRef.current, newLevel)
      foodRef.current = generateFood(snakeRef.current, GRID_SIZE)
    }

    draw()
    gameLoopRef.current = setTimeout(tick, getSpeed(scoreRef.current))
  }, [wallsMode, draw, gameOver, onScoreChange])

  const startGame = useCallback(() => {
    snakeRef.current = [...INITIAL_SNAKE.map(p => ({ ...p }))]
    directionRef.current = 'RIGHT'
    nextDirectionRef.current = 'RIGHT'
    foodRef.current = generateFood(INITIAL_SNAKE, GRID_SIZE)
    scoreRef.current = 0
    setScore(0)
    gameStatusRef.current = 'playing'
    setGameStatus('playing')
    music.init()
    sfx.init()
    music.start()
    draw()
    gameLoopRef.current = setTimeout(tick, getSpeed(0))
  }, [draw, tick, music])

  const pausedRef = useRef(false)

  const togglePause = useCallback(() => {
    if (gameStatusRef.current === 'playing') {
      gameStatusRef.current = 'idle'
      setGameStatus('idle')
      pausedRef.current = true
      if (gameLoopRef.current) clearTimeout(gameLoopRef.current)
    } else if (gameStatusRef.current === 'idle' && pausedRef.current) {
      gameStatusRef.current = 'playing'
      setGameStatus('playing')
      pausedRef.current = false
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

  // Touch/swipe controls — use touchmove for immediate response
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const handleTouchStart = (e: TouchEvent) => {
      const t = e.touches[0]
      touchStartRef.current = { x: t.clientX, y: t.clientY }
    }
    const handleTouchMove = (e: TouchEvent) => {
      if (!touchStartRef.current) return
      const t = e.touches[0]
      const dx = t.clientX - touchStartRef.current.x
      const dy = t.clientY - touchStartRef.current.y
      const minSwipe = 20
      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > minSwipe) {
        changeDirection(dx > 0 ? 'RIGHT' : 'LEFT')
        touchStartRef.current = { x: t.clientX, y: t.clientY }
      } else if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > minSwipe) {
        changeDirection(dy > 0 ? 'DOWN' : 'UP')
        touchStartRef.current = { x: t.clientX, y: t.clientY }
      }
    }
    const handleTouchEnd = () => { touchStartRef.current = null }
    canvas.addEventListener('touchstart', handleTouchStart, { passive: true })
    canvas.addEventListener('touchmove', handleTouchMove, { passive: true })
    canvas.addEventListener('touchend', handleTouchEnd, { passive: true })
    return () => {
      canvas.removeEventListener('touchstart', handleTouchStart)
      canvas.removeEventListener('touchmove', handleTouchMove)
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
      <div className="flex items-center gap-2">
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play">
          <HelpCircle className="w-4 h-4 text-blue-400" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
        <span className="text-xs text-slate-500">
          Level {Math.floor(score / 5) + 1}
        </span>
      </div>
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

        {/* Start overlay — only before game begins */}
        {gameStatus === 'idle' && !pausedRef.current && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/70 rounded-lg">
            <button
              onClick={startGame}
              className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold transition-colors"
            >
              Start Game
            </button>
          </div>
        )}

        {/* Pause overlay */}
        {gameStatus === 'idle' && pausedRef.current && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/70 rounded-lg">
            <button
              onClick={togglePause}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-semibold transition-colors"
            >
              Resume
            </button>
          </div>
        )}

        {/* Mobile D-pad — onTouchStart for instant response */}
        <div className="flex flex-col items-center space-y-0.5 sm:hidden mt-1">
          <button onTouchStart={(e) => { e.preventDefault(); changeDirection('UP') }} onClick={() => changeDirection('UP')} className="w-10 h-10 bg-slate-700 rounded-lg flex items-center justify-center active:bg-slate-600">
            <ArrowUp className="w-5 h-5 text-slate-300" />
          </button>
          <div className="flex space-x-0.5">
            <button onTouchStart={(e) => { e.preventDefault(); changeDirection('LEFT') }} onClick={() => changeDirection('LEFT')} className="w-10 h-10 bg-slate-700 rounded-lg flex items-center justify-center active:bg-slate-600">
              <ArrowLeft className="w-5 h-5 text-slate-300" />
            </button>
            <button onTouchStart={(e) => { e.preventDefault(); togglePause() }} onClick={togglePause} className="w-10 h-10 bg-slate-700 rounded-lg flex items-center justify-center active:bg-slate-600">
              {gameStatus === 'playing' ? <Pause className="w-5 h-5 text-slate-300" /> : <Play className="w-5 h-5 text-slate-300" />}
            </button>
            <button onTouchStart={(e) => { e.preventDefault(); changeDirection('RIGHT') }} onClick={() => changeDirection('RIGHT')} className="w-10 h-10 bg-slate-700 rounded-lg flex items-center justify-center active:bg-slate-600">
              <ArrowRight className="w-5 h-5 text-slate-300" />
            </button>
          </div>
          <button onTouchStart={(e) => { e.preventDefault(); changeDirection('DOWN') }} onClick={() => changeDirection('DOWN')} className="w-10 h-10 bg-slate-700 rounded-lg flex items-center justify-center active:bg-slate-600">
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
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <SnakeHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Multiplayer race wrapper ──────────────────────────────────────────
function SnakeRaceWrapper({ roomId }: { roomId: string }) {
  const { opponentStatus, raceResult, opponentLevelUp, throttledBroadcast, reportFinish, reportScore, reportLevel } = useRaceMode(roomId, 'best_score')
  const finishedRef = useRef(false)
  const lastLevelRef = useRef(1)

  const handleGameEnd = useCallback((score: number) => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish('loss', score)
  }, [reportFinish])

  const handleScoreChange = useCallback((score: number, level: number) => {
    reportScore(score)
    if (level > lastLevelRef.current) {
      lastLevelRef.current = level
      reportLevel(level, `Snake length: ${level * 5}`)
    }
  }, [reportScore, reportLevel])

  return (
    <div className="relative">
      <RaceOverlay
        raceResult={raceResult}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
      />
      <SnakeSinglePlayer onGameEnd={handleGameEnd} onScoreChange={handleScoreChange} onStateChange={throttledBroadcast} />
    </div>
  )
}

// ── Default export with multiplayer support ───────────────────────────
export default function Snake() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'snake',
        gameName: 'Snake',
        modes: ['race'],
        maxPlayers: 2,
        raceDescription: 'Longest snake wins',
      }}
      renderSinglePlayer={() => <SnakeSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, _roomConfig) => (
        <SnakeRaceWrapper roomId={roomId} />
      )}
    />
  )
}
