/**
 * 2048 game — slide and merge tiles to reach 2048.
 *
 * Features: arrow/WASD + swipe controls, undo, score tracking,
 * win detection with continue option.
 */

import { useState, useCallback, useEffect, useRef, useMemo} from 'react'
import { HelpCircle, Undo2, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameScores } from '../../../hooks/useGameScores'
import { useGameState } from '../../../hooks/useGameState'
import {
  createBoard, move, addRandomTile, hasValidMoves, isGameWon,
  type Board, type MoveDirection,
} from './twenFoEiEngine'
import { TileGrid } from './TileGrid'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

interface TFESaved {
  board: Board
  score: number
  gameStatus: GameStatus
  hasWon: boolean
}

function initBoard(): Board {
  return addRandomTile(addRandomTile(createBoard()))
}

function TwentyFortyEightHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play 2048</h2>
        <Sec title="Goal"><p>Slide tiles on a 4×4 grid to combine matching numbers. Reach the <B>2048 tile</B> to win! Keep going for an even higher score.</p></Sec>
        <Sec title="How to Play"><ul className="space-y-1">
          <Li><B>Swipe or use arrow keys</B> to slide all tiles in one direction.</Li>
          <Li>When two tiles with the <B>same number</B> collide, they merge into one tile with their sum.</Li>
          <Li>After each move, a new <B>2</B> (or occasionally <B>4</B>) tile appears randomly.</Li>
          <Li>The game ends when no more moves are possible.</Li>
        </ul></Sec>
        <Sec title="Controls"><ul className="space-y-1">
          <Li><B>Arrow keys / WASD</B> — Slide tiles.</Li>
          <Li><B>Swipe</B> — Touch controls on mobile.</Li>
          <Li><B>Undo</B> — Reverse the last move.</Li>
        </ul></Sec>
        <Sec title="Strategy Tips"><ul className="space-y-1">
          <Li>Keep your highest tile in a corner — never move it from there.</Li>
          <Li>Build a "snake" pattern along the edges for consistent merging.</Li>
          <Li>Avoid moving up if your highest tile is in the bottom corner.</Li>
          <Li>Plan two moves ahead — don't just react to the current board.</Li>
        </ul></Sec>
      </div>
    </div>
  )
}

function TwentyFortyEightSinglePlayer({ onGameEnd, onScoreUpdate, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw', score?: number) => void; onScoreUpdate?: (score: number) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<TFESaved>('2048')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('2048'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('2048')
  const [showHelp, setShowHelp] = useState(false)

  const [board, setBoard] = useState<Board>(() => saved?.board ?? initBoard())
  const [score, setScore] = useState(saved?.score ?? 0)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [hasWon, setHasWon] = useState(saved?.hasWon ?? false)
  const [history, setHistory] = useState<{ board: Board; score: number }[]>([])
  const { getHighScore, saveScore } = useGameScores()

  // Persist state
  useEffect(() => {
    save({ board, score, gameStatus, hasWon })
  }, [board, score, gameStatus, hasWon, save])
  const bestScore = getHighScore('2048') ?? 0
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)

  const handleMove = useCallback((direction: MoveDirection) => {
    if (gameStatus !== 'playing') return

    music.init()
    sfx.init()
    music.start()

    const result = move(board, direction)
    if (!result.moved) return

    sfx.play('slide')
    if (result.score > 0) { sfx.play('merge') }
    setHistory(prev => [...prev.slice(-20), { board, score }])
    const newScore = score + result.score
    const withTile = addRandomTile(result.board)
    setBoard(withTile)
    setScore(newScore)

    onScoreUpdate?.(newScore)

    if (isGameWon(withTile) && !hasWon) {
      setHasWon(true)
      sfx.play('win')
      setGameStatus('won')
      saveScore('2048', newScore)
      onGameEnd?.('win', newScore)
      return
    }

    if (!hasValidMoves(withTile)) {
      sfx.play('lose')
      setGameStatus('lost')
      saveScore('2048', newScore)
      onGameEnd?.('loss', newScore)
    }
  }, [board, score, gameStatus, hasWon, saveScore, onGameEnd, onScoreUpdate])

  const handleContinue = useCallback(() => {
    setGameStatus('playing')
  }, [])

  const handleUndo = useCallback(() => {
    if (history.length === 0) return
    const prev = history[history.length - 1]
    setBoard(prev.board)
    setScore(prev.score)
    setHistory(h => h.slice(0, -1))
  }, [history])

  const handleNewGame = useCallback(() => {
    setBoard(initBoard())
    setScore(0)
    setGameStatus('playing')
    setHasWon(false)
    setHistory([])
    music.start()
    clear()
  }, [music, clear])

  // Keyboard controls
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const map: Record<string, MoveDirection> = {
        ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
        w: 'up', s: 'down', a: 'left', d: 'right',
        W: 'up', S: 'down', A: 'left', D: 'right',
      }
      const dir = map[e.key]
      if (dir) { e.preventDefault(); handleMove(dir) }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [handleMove])

  // Touch/swipe controls
  useEffect(() => {
    const handleTouchStart = (e: TouchEvent) => {
      touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
    }
    const handleTouchEnd = (e: TouchEvent) => {
      if (!touchStartRef.current) return
      const dx = e.changedTouches[0].clientX - touchStartRef.current.x
      const dy = e.changedTouches[0].clientY - touchStartRef.current.y
      const minSwipe = 30
      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > minSwipe) {
        handleMove(dx > 0 ? 'right' : 'left')
      } else if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > minSwipe) {
        handleMove(dy > 0 ? 'down' : 'up')
      }
      touchStartRef.current = null
    }
    document.addEventListener('touchstart', handleTouchStart, { passive: true })
    document.addEventListener('touchend', handleTouchEnd, { passive: true })
    return () => {
      document.removeEventListener('touchstart', handleTouchStart)
      document.removeEventListener('touchend', handleTouchEnd)
    }
  }, [handleMove])

  const controls = (
    <div className="flex items-center justify-between">
      <button
        onClick={handleUndo}
        disabled={history.length === 0}
        className="flex items-center space-x-1 px-3 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        <Undo2 className="w-3 h-3" />
        <span>Undo</span>
      </button>
      <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play"><HelpCircle className="w-4 h-4 text-blue-400" /></button>
      <MusicToggle music={music} sfx={sfx} />
      <button
        onClick={handleNewGame}
        className="px-3 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
      >
        New Game
      </button>
    </div>
  )

  return (
    <GameLayout title="2048" score={score} bestScore={bestScore} controls={controls}>
      <div className="relative flex flex-col items-center space-y-4">
        <div style={{ touchAction: 'none' }}>
          <TileGrid board={board} />
        </div>

        <p className="text-xs text-slate-500 hidden sm:block">
          Arrow keys or WASD to move. Swipe on mobile.
        </p>

        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            score={score}
            bestScore={bestScore}
            message="You reached 2048!"
            onPlayAgain={handleContinue}
            playAgainText="Continue"
            music={music}
            sfx={sfx}
          />
        )}

        {gameStatus === 'lost' && !isMultiplayer && (
          <GameOverModal
            status="lost"
            score={score}
            bestScore={bestScore}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <TwentyFortyEightHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (best_score — highest score wins) ───────────────────

function TwentyFortyEightRaceWrapper({ roomId, onLeave }: { roomId: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, opponentLevelUp, reportScore, reportFinish } = useRaceMode(roomId, 'best_score')
  const finishedRef = useRef(false)

  const handleScoreUpdate = useCallback((score: number) => {
    reportScore(score)
  }, [reportScore])

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw', score?: number) => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish(result === 'draw' ? 'loss' : result, score)
  }, [reportFinish])

  return (
    <div className="relative">
      <RaceOverlay
        raceResult={raceResult}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
        onDismiss={onLeave}
      />
      <TwentyFortyEightSinglePlayer onGameEnd={handleGameEnd} onScoreUpdate={handleScoreUpdate} isMultiplayer />
    </div>
  )
}

// ── Default export with multiplayer wrapper ──────────────────────────

export default function TwentyFortyEight() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: '2048',
        gameName: '2048',
        modes: ['best_score'],
        maxPlayers: 2,
        modeDescriptions: { best_score: 'Highest score wins' },
      }}
      renderSinglePlayer={() => <TwentyFortyEightSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, _roomConfig, onLeave) =>
        <TwentyFortyEightRaceWrapper roomId={roomId} onLeave={onLeave} />
      }
    />
  )
}
