/**
 * Minesweeper game — reveal cells, avoid mines.
 *
 * Features: 3 difficulty levels, first-click safety, flood fill,
 * flagging (right-click / long-press), timer, mine counter.
 */

import { useState, useCallback, useRef, useMemo, useEffect} from 'react'
import { Bomb, HelpCircle, SmilePlus, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameTimer } from '../../../hooks/useGameTimer'
import { useGameScores } from '../../../hooks/useGameScores'
import { useGameState } from '../../../hooks/useGameState'
import {
  generateBoard, revealCell, toggleFlag, checkWin,
  type MineBoard,
} from './minesweeperEngine'
import { MinesweeperGrid } from './MinesweeperGrid'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import type { Difficulty } from '../../../types'

// ── Help modal ──────────────────────────────────────────────────────
function MinesweeperHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Minesweeper</h2>

        <Sec title="Goal">
          <p>Reveal all safe cells on the grid without clicking on a mine.</p>
        </Sec>

        <Sec title="How to Play">
          <ul className="space-y-1">
            <Li><B>Left-click</B> a cell to reveal it. If it has no adjacent mines, surrounding cells auto-reveal (flood fill).</Li>
            <Li><B>Right-click</B> (or long-press on mobile) to place a <B>flag</B> marking a suspected mine.</Li>
            <Li>Numbers show how many of the 8 surrounding cells contain mines.</Li>
            <Li>A blank revealed cell means zero adjacent mines.</Li>
          </ul>
        </Sec>

        <Sec title="First-Click Safety">
          <p>Your very first click is always safe — the board generates after your first reveal, ensuring that cell and its neighbors are mine-free.</p>
        </Sec>

        <Sec title="Difficulty Levels">
          <ul className="space-y-1">
            <Li><B>Beginner</B> — 9×9 grid, 10 mines</Li>
            <Li><B>Intermediate</B> — 16×16 grid, 40 mines</Li>
            <Li><B>Expert</B> — 16×30 grid, 99 mines (scrollable)</Li>
          </ul>
        </Sec>

        <Sec title="Winning & Losing">
          <ul className="space-y-1">
            <Li><B>Win</B> by revealing every non-mine cell. Flags are not required.</Li>
            <Li><B>Lose</B> by clicking a mine — all mines are revealed.</Li>
            <Li>Best times are saved per difficulty level.</Li>
          </ul>
        </Sec>

        <Sec title="Controls">
          <ul className="space-y-1">
            <Li><B>Left-click</B> — Reveal a cell</Li>
            <Li><B>Right-click / Long-press</B> — Toggle flag</Li>
            <Li><B>Smiley button</B> — Start a new game</Li>
            <Li>Mine counter shows remaining unflagged mines.</Li>
          </ul>
        </Sec>

        <Sec title="Strategy Tips">
          <ul className="space-y-1">
            <Li>Start with corners or edges — they touch fewer cells, giving clearer info.</Li>
            <Li>If a "1" cell has only one hidden neighbor, that neighbor is definitely a mine — flag it.</Li>
            <Li>Use the mine counter to track how many unflagged mines remain.</Li>
            <Li>Work the borders of revealed regions where numbers meet hidden cells.</Li>
          </ul>
        </Sec>
      </div>
    </div>
  )
}

interface DifficultyConfig {
  rows: number
  cols: number
  mines: number
  label: string
}

const DIFFICULTIES: Record<string, DifficultyConfig> = {
  beginner: { rows: 9, cols: 9, mines: 10, label: 'Beginner' },
  intermediate: { rows: 16, cols: 16, mines: 40, label: 'Intermediate' },
  expert: { rows: 16, cols: 30, mines: 99, label: 'Expert' },
}

interface MinesweeperSaved {
  diffKey: string
  board: MineBoard | null
  gameStatus: GameStatus
  explodedCell: [number, number] | null
  elapsed: number
  firstClick: boolean
}

function MinesweeperSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw', score?: number) => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<MinesweeperSaved>('minesweeper')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('minesweeper'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('minesweeper')

  const [showHelp, setShowHelp] = useState(false)
  const [diffKey, setDiffKey] = useState(saved?.diffKey ?? 'beginner')
  const diff = DIFFICULTIES[diffKey]
  const [board, setBoard] = useState<MineBoard | null>(saved?.board ?? null)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'idle')
  const [explodedCell, setExplodedCell] = useState<[number, number] | null>(saved?.explodedCell ?? null)
  const firstClick = useRef(saved?.firstClick ?? true)
  const timer = useGameTimer(saved?.elapsed)
  const { getHighScore, saveScore } = useGameScores()

  // Persist state
  useEffect(() => {
    save({ diffKey, board, gameStatus, explodedCell, elapsed: timer.seconds, firstClick: firstClick.current })
  }, [diffKey, board, gameStatus, explodedCell, timer.seconds, save])

  const flagCount = board?.flat().filter(c => c.isFlagged).length ?? 0
  const minesRemaining = diff.mines - flagCount

  const handleReveal = useCallback((row: number, col: number) => {
    if (gameStatus === 'won' || gameStatus === 'lost') return

    music.init()
    sfx.init()
    music.start()

    let currentBoard = board
    if (firstClick.current || !currentBoard) {
      // Generate board with first-click safety
      currentBoard = generateBoard(diff.rows, diff.cols, diff.mines, row, col)
      firstClick.current = false
      timer.start()
    }

    const result = revealCell(currentBoard, row, col)
    setBoard(result.board)

    if (result.hitMine) {
      sfx.play('mine')
      // Reveal all mines
      const revealedBoard = result.board.map(r =>
        r.map(c => c.isMine ? { ...c, isRevealed: true } : c)
      )
      setBoard(revealedBoard)
      setExplodedCell([row, col])
      setGameStatus('lost')
      timer.stop()
      onGameEnd?.('loss', timer.seconds)
      return
    }

    sfx.play('reveal')
    if (checkWin(result.board)) {
      sfx.play('win')
      setGameStatus('won')
      timer.stop()
      const bestKey = `minesweeper-${diffKey}`
      const best = getHighScore(bestKey)
      if (!best || timer.seconds < best) {
        saveScore(bestKey, timer.seconds)
      }
      onGameEnd?.('win', timer.seconds)
    }
  }, [board, gameStatus, diff, diffKey, timer, getHighScore, saveScore, onGameEnd])

  const handleFlag = useCallback((row: number, col: number) => {
    if (!board || gameStatus !== 'playing' && gameStatus !== 'idle') return
    if (firstClick.current) return // Can't flag before first reveal
    sfx.play('flag')
    setBoard(toggleFlag(board, row, col))
  }, [board, gameStatus])

  const handleNewGame = useCallback(() => {
    setBoard(null)
    setGameStatus('idle')
    setExplodedCell(null)
    firstClick.current = true
    timer.reset()
    clear()
  }, [timer, clear])

  const handleDifficulty = useCallback((key: string) => {
    setDiffKey(key)
    setBoard(null)
    setGameStatus('idle')
    setExplodedCell(null)
    firstClick.current = true
    timer.reset()
    clear()
  }, [timer, clear])

  // Create placeholder board for initial render
  const displayBoard = board ?? Array.from({ length: diff.rows }, () =>
    Array.from({ length: diff.cols }, () => ({
      isMine: false, isRevealed: false, isFlagged: false, adjacentMines: 0,
    }))
  )

  const isGameOver = gameStatus === 'won' || gameStatus === 'lost'

  const controls = (
    <div className="flex flex-col space-y-2">
      {/* Difficulty buttons */}
      <div className="flex space-x-2">
        {Object.entries(DIFFICULTIES).map(([key, cfg]) => (
          <button
            key={key}
            onClick={() => handleDifficulty(key)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              diffKey === key
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
          >
            {cfg.label}
          </button>
        ))}
      </div>
      {/* Status bar */}
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center space-x-1 text-red-400">
          <Bomb className="w-3.5 h-3.5" />
          <span>{minesRemaining}</span>
        </div>
        <button
          onClick={handleNewGame}
          className="p-1 hover:bg-slate-700 rounded transition-colors"
          title="New Game"
        >
          <SmilePlus className="w-5 h-5 text-yellow-400" />
        </button>
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play">
          <HelpCircle className="w-4 h-4 text-blue-400" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
        <span className="text-slate-400 font-mono text-xs">{timer.formatted}</span>
      </div>
    </div>
  )

  return (
    <GameLayout title="Minesweeper" controls={controls}>
      <div className="relative flex flex-col items-center">
        <div className={diffKey === 'expert' ? 'overflow-x-auto max-w-full' : ''}>
          <MinesweeperGrid
            board={displayBoard}
            onReveal={handleReveal}
            onFlag={handleFlag}
            gameOver={isGameOver}
            explodedCell={explodedCell}
          />
        </div>

        <p className="text-xs text-slate-500 mt-3 hidden sm:block">
          Left-click to reveal. Right-click to flag.
        </p>

        {isGameOver && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            message={gameStatus === 'won' ? `Cleared in ${timer.formatted}` : undefined}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <MinesweeperHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (best_score — fastest clear time wins) ─────────────

function MinesweeperRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: Difficulty; onLeave?: () => void }) {
  const { opponentStatus, raceResult, opponentLevelUp, broadcastState, reportFinish } = useRaceMode(roomId, 'best_score')
  const finishedRef = useRef(false)

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw', score?: number) => {
    if (finishedRef.current) return
    finishedRef.current = true
    // Invert score so faster times rank higher in best_score comparison
    const invertedScore = score != null ? Math.max(0, 999999 - score) : undefined
    reportFinish(result === 'loss' ? 'loss' : 'win', invertedScore)
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
      <MinesweeperSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

// ── Default export with multiplayer wrapper ─────────────────────────

export default function Minesweeper() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'minesweeper',
        gameName: 'Minesweeper',
        modes: ['best_score'],
        hasDifficulty: true,
        modeDescriptions: { best_score: 'Fastest to clear the board wins' },
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <MinesweeperSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig, onLeave) =>
        <MinesweeperRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
      }
    />
  )
}
