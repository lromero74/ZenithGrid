/**
 * Nonogram (Picross) game — fill cells to match clue patterns.
 *
 * Features: multiple puzzle sizes, click/right-click controls,
 * row/column validation feedback, puzzle selection.
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { RotateCcw } from 'lucide-react'
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

type SizeFilter = '5x5' | '10x10' | '15x15'

interface NonogramState {
  sizeFilter: SizeFilter
  puzzleIndex: number
  gameStatus: GameStatus
  grid: Grid
  elapsed: number
}

export default function Nonogram() {
  const { load, save, clear } = useGameState<NonogramState>('nonogram')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('nonogram'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('nonogram')

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
    }
  }, [grid, gameStatus, clues, timer])

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
    </GameLayout>
  )
}
