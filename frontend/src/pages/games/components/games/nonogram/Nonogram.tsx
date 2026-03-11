/**
 * Nonogram (Picross) game — fill cells to match clue patterns.
 *
 * Features: multiple puzzle sizes, click/right-click controls,
 * row/column validation feedback, puzzle selection.
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { HelpCircle, RotateCcw, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameTimer } from '../../../hooks/useGameTimer'
import { useGameState } from '../../../hooks/useGameState'
import {
  generateClues, createGrid, setCell, validateRow, validateColumn,
  isPuzzleComplete,
  type Grid, type CellState,
} from './nonogramEngine'
import { NonogramGrid } from './NonogramGrid'
import { PUZZLES_5X5, PUZZLES_10X10, PUZZLES_15X15 } from './puzzles'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

// ── Help modal ──────────────────────────────────────────────────────
function NonogramHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Nonogram</h2>

        <Sec title="Goal">
          <p>Fill in cells on the grid to reveal a hidden picture. Use the number clues along each row and column to determine which cells to fill.</p>
        </Sec>

        <Sec title="Reading Clues">
          <ul className="space-y-1">
            <Li>Each row and column has a set of numbers — these are <B>run lengths</B>.</Li>
            <Li>A clue like <B>3 1</B> means there's a group of 3 filled cells, then at least one gap, then 1 filled cell.</Li>
            <Li>A clue of <B>0</B> means the entire row/column is empty.</Li>
            <Li>Clues turn <B>green</B> when the row or column is correctly completed.</Li>
          </ul>
        </Sec>

        <Sec title="Controls">
          <ul className="space-y-1">
            <Li><B>Left-click</B> — Fill a cell (click again to clear).</Li>
            <Li><B>Right-click</B> — Mark a cell with X (to remember it's empty). Click again to clear.</Li>
            <Li><B>Reset button</B> — Clear the grid and start over.</Li>
            <Li><B>Next Puzzle</B> — Skip to a different puzzle.</Li>
          </ul>
        </Sec>

        <Sec title="Puzzle Sizes">
          <ul className="space-y-1">
            <Li><B>5×5</B> — Small, beginner-friendly puzzles.</Li>
            <Li><B>10×10</B> — Medium puzzles with more detail.</Li>
            <Li><B>15×15</B> — Large, challenging puzzles.</Li>
          </ul>
        </Sec>

        <Sec title="Winning">
          <p>Complete the puzzle by filling all the correct cells. The timer tracks your solve time — try to beat your best!</p>
        </Sec>

        <Sec title="Strategy Tips">
          <ul className="space-y-1">
            <Li>Start with rows/columns that have the largest clues — they're the most constrained.</Li>
            <Li>If a clue fills more than half the row, some cells can be determined by overlap.</Li>
            <Li>Use X marks to track cells you've confirmed as empty — this prevents mistakes.</Li>
            <Li>A clue of <B>0</B> means every cell in that row/column should be marked X.</Li>
            <Li>Work back and forth between rows and columns — solving one often reveals info for the other.</Li>
          </ul>
        </Sec>
      </div>
    </div>
  )
}

type SizeFilter = '5x5' | '10x10' | '15x15'

interface NonogramState {
  sizeFilter: SizeFilter
  puzzleIndex: number
  gameStatus: GameStatus
  grid: Grid
  elapsed: number
}

function NonogramSinglePlayer({ onGameEnd }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void } = {}) {
  const { load, save, clear } = useGameState<NonogramState>('nonogram')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('nonogram'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('nonogram')

  const [showHelp, setShowHelp] = useState(false)
  const [sizeFilter, setSizeFilter] = useState<SizeFilter>(saved?.sizeFilter ?? '5x5')
  const [puzzleIndex, setPuzzleIndex] = useState(saved?.puzzleIndex ?? 0)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const timer = useGameTimer(saved?.elapsed)

  const filteredPuzzles = useMemo(() => {
    if (sizeFilter === '5x5') return PUZZLES_5X5
    if (sizeFilter === '10x10') return PUZZLES_10X10
    return PUZZLES_15X15
  }, [sizeFilter])

  const puzzle = filteredPuzzles[puzzleIndex % filteredPuzzles.length]
  const clues = useMemo(() => generateClues(puzzle.solution), [puzzle])
  const rows = puzzle.solution.length
  const cols = puzzle.solution[0].length

  const [grid, setGrid] = useState<Grid>(() => saved?.grid ?? createGrid(rows, cols))

  // Persist state
  useEffect(() => {
    save({ sizeFilter, puzzleIndex, gameStatus, grid, elapsed: timer.seconds })
  }, [sizeFilter, puzzleIndex, gameStatus, grid, timer.seconds, save])

  const validatedRows = useMemo(
    () => grid.map((row, r) => validateRow(row, clues.rowClues[r])),
    [grid, clues]
  )
  const validatedCols = useMemo(
    () => Array.from({ length: cols }, (_, c) => validateColumn(grid, c, clues.colClues[c])),
    [grid, cols, clues]
  )

  const handleCellClick = useCallback((r: number, c: number) => {
    if (gameStatus !== 'playing') return
    music.init()
    sfx.init()
    music.start()
    if (!timer.isRunning) timer.start()

    const current = grid[r][c]
    const next: CellState = current === 'unknown' ? 'filled' : current === 'filled' ? 'unknown' : 'unknown'
    if (next === 'filled') { sfx.play('fill') }
    const newGrid = setCell(grid, r, c, next)
    setGrid(newGrid)

    if (isPuzzleComplete(newGrid, clues.rowClues, clues.colClues)) {
      sfx.play('win')
      setGameStatus('won')
      timer.stop()
      onGameEnd?.('win')
    }
  }, [grid, gameStatus, clues, timer, onGameEnd])

  const handleCellRightClick = useCallback((r: number, c: number) => {
    if (gameStatus !== 'playing') return
    if (!timer.isRunning) timer.start()

    const current = grid[r][c]
    const next: CellState = current === 'unknown' ? 'empty' : current === 'empty' ? 'unknown' : 'unknown'
    if (next === 'empty') { sfx.play('mark') }
    setGrid(setCell(grid, r, c, next))
  }, [grid, gameStatus, timer])

  const handleReset = useCallback(() => {
    setGrid(createGrid(rows, cols))
    setGameStatus('playing')
    timer.reset()
    clear()
  }, [rows, cols, timer, clear])

  const handleNextPuzzle = useCallback(() => {
    const nextIdx = (puzzleIndex + 1) % filteredPuzzles.length
    setPuzzleIndex(nextIdx)
    const nextPuzzle = filteredPuzzles[nextIdx]
    setGrid(createGrid(nextPuzzle.solution.length, nextPuzzle.solution[0].length))
    setGameStatus('playing')
    timer.reset()
    music.start()
  }, [puzzleIndex, filteredPuzzles, timer, music])

  const handleSizeChange = useCallback((size: SizeFilter) => {
    setSizeFilter(size)
    setPuzzleIndex(0)
    const puzzles = size === '5x5' ? PUZZLES_5X5 : size === '10x10' ? PUZZLES_10X10 : PUZZLES_15X15
    const p = puzzles[0]
    setGrid(createGrid(p.solution.length, p.solution[0].length))
    setGameStatus('playing')
    timer.reset()
  }, [timer])

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex space-x-1.5">
        {(['5x5', '10x10', '15x15'] as SizeFilter[]).map(size => (
          <button
            key={size}
            onClick={() => handleSizeChange(size)}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              sizeFilter === size
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
          >
            {size}
          </button>
        ))}
      </div>
      <div className="flex items-center space-x-2">
        <span className="text-xs text-slate-500">{puzzle.name}</span>
        <button
          onClick={handleReset}
          className="p-1 hover:bg-slate-700 rounded transition-colors"
          title="Reset"
        >
          <RotateCcw className="w-4 h-4 text-slate-400" />
        </button>
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play">
          <HelpCircle className="w-4 h-4 text-blue-400" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Nonogram" timer={timer.formatted} controls={controls}>
      <div className="relative flex flex-col items-center space-y-4">
        <NonogramGrid
          grid={grid}
          rowClues={clues.rowClues}
          colClues={clues.colClues}
          validatedRows={validatedRows}
          validatedCols={validatedCols}
          onCellClick={handleCellClick}
          onCellRightClick={handleCellRightClick}
        />

        <div className="flex space-x-3">
          <button
            onClick={handleNextPuzzle}
            className="px-3 py-1.5 rounded text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
          >
            Next Puzzle
          </button>
        </div>

        <p className="text-xs text-slate-500 hidden sm:block">
          Left-click to fill. Right-click to mark X.
        </p>

        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            message={`Completed "${puzzle.name}" in ${timer.formatted}`}
            onPlayAgain={handleNextPuzzle}
            playAgainText="Next Puzzle"
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <NonogramHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first_to_win — first to solve wins) ────────────────

function NonogramRaceWrapper({ roomId, onLeave }: { roomId: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, opponentLevelUp, reportFinish } = useRaceMode(roomId, 'first_to_win')
  const finishedRef = useRef(false)

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw') => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish(result === 'draw' ? 'loss' : result)
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
      <NonogramSinglePlayer onGameEnd={handleGameEnd} />
    </div>
  )
}

// ── Default export with multiplayer wrapper ──────────────────────────

export default function Nonogram() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'nonogram',
        gameName: 'Nonogram',
        modes: ['first_to_win'],
        hasDifficulty: true,
        maxPlayers: 2,
        modeDescriptions: { first_to_win: 'First to solve the puzzle wins' },
      }}
      renderSinglePlayer={() => <NonogramSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, _roomConfig, onLeave) =>
        <NonogramRaceWrapper roomId={roomId} onLeave={onLeave} />
      }
    />
  )
}
