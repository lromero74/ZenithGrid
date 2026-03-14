/**
 * Daily Crossword Puzzle — themed crossword with easy/medium/hard difficulty.
 *
 * One puzzle per day per difficulty. Algorithmically generated from themed word banks.
 */

import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import { MusicToggle } from '../../MusicToggle'
import { useGameState } from '../../../hooks/useGameState'
import { useGameTimer } from '../../../hooks/useGameTimer'
import { useGameMusic } from '../../../audio/useGameMusic'
import { getSongForGame } from '../../../audio/songRegistry'
import { useGameSFX } from '../../../audio/useGameSFX'
import type { Difficulty as SharedDifficulty, GameStatus } from '../../../types'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import { getThemeBackground } from './crosswordBackgrounds'
import {
  generatePuzzle,
  createEmptyUserGrid,
  isPuzzleComplete,
  getWordCells,
  getWordsAtCell,
  getTodayString,
  type CrosswordPuzzle,
  type PlacedWord,
  type Difficulty,
  type Direction,
} from './crosswordEngine'
import { CROSSWORD_THEMES } from './crosswordThemes'

// ── Leaderboard ─────────────────────────────────────────────────────

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}


// ── Saved state ─────────────────────────────────────────────────────

interface CrosswordSaved {
  dateStr: string
  difficulty: Difficulty
  userGrid: string[][]
  gameStatus: GameStatus
  elapsed: number
  completedDifficulties: Record<string, Difficulty[]>
}

// ── Keyboard rows ───────────────────────────────────────────────────

const KB_ROWS = [
  ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
  ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
  ['Z', 'X', 'C', 'V', 'B', 'N', 'M'],
]

// ── Help modal ──────────────────────────────────────────────────────

function CrosswordHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Crossword</h2>

        {/* Goal */}
        <Sec title="Goal">
          Fill every white cell with the correct letter to complete all
          intersecting words. Each puzzle is built around a <B>daily theme</B> and
          generated fresh every day.
        </Sec>

        {/* Daily puzzle */}
        <Sec title="Daily Puzzle">
          <ul className="space-y-1 text-slate-300">
            <Li>A new puzzle is generated each day using a <B>seeded random
              algorithm</B>, so everyone gets the same puzzle on the same day.</Li>
            <Li>Puzzles are drawn from a bank of <B>100 themed categories</B> (astronomy,
              music, mythology, cuisine, and more).</Li>
            <Li>Your progress is <B>saved automatically</B> so you can close the
              page and resume later.</Li>
          </ul>
        </Sec>

        {/* Difficulty */}
        <Sec title="Difficulty Levels">
          <div className="space-y-1.5 text-slate-300">
            <div className="flex gap-1.5 text-xs">
              <span className="text-green-400 font-medium w-16">Easy</span>
              <span>5-7 words, 3-6 letters each</span>
            </div>
            <div className="flex gap-1.5 text-xs">
              <span className="text-yellow-400 font-medium w-16">Medium</span>
              <span>7-10 words, 4-8 letters each</span>
            </div>
            <div className="flex gap-1.5 text-xs">
              <span className="text-red-400 font-medium w-16">Hard</span>
              <span>10-14 words, 4-12 letters each</span>
            </div>
          </div>
          <p className="text-slate-400 text-xs mt-1.5">
            Each difficulty has its own independent puzzle for the day. Complete
            all three to earn a checkmark on each.
          </p>
        </Sec>

        {/* Navigation */}
        <Sec title="Navigation &amp; Input">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Click a cell</B> to select it. The active word and its clue
              are highlighted.</Li>
            <Li><B>Click the same cell again</B> to toggle direction between
              Across and Down.</Li>
            <Li><B>Type a letter</B> using your physical keyboard or the
              on-screen keyboard to fill the selected cell.</Li>
            <Li>After typing, the cursor <B>auto-advances</B> to the next cell
              in the current direction.</Li>
            <Li><B>Backspace / DEL</B> clears the current cell; if already empty,
              it moves back one cell.</Li>
            <Li>Press <B>Tab</B> to switch direction (Across / Down) without
              moving the cursor.</Li>
            <Li><B>Click a clue</B> in the clue panel to jump to that word on
              the grid.</Li>
          </ul>
        </Sec>

        {/* Tools */}
        <Sec title="Check &amp; Reveal">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Check</B> scans every filled cell and marks incorrect letters
              in <span className="text-red-400">red</span>. Re-typing a letter
              clears the error mark.</Li>
            <Li><B>Reveal</B> fills the currently selected cell with the correct
              letter, shown in <span className="text-yellow-400">yellow</span>.
              Useful when you are stuck on a single crossing.</Li>
          </ul>
        </Sec>

        {/* Visual cues */}
        <Sec title="Visual Cues">
          <ul className="space-y-1 text-slate-300">
            <Li>The <B>selected cell</B> has a bright blue background.</Li>
            <Li>Other cells in the <B>active word</B> have a subtle blue tint.</Li>
            <Li>Completed clues show a <span className="text-emerald-400">green
              strikethrough</span> in the clue list.</Li>
            <Li>Black cells are empty spacers and cannot be clicked.</Li>
            <Li>Clue numbers appear in the <B>top-left corner</B> of cells where
              words begin.</Li>
          </ul>
        </Sec>

        {/* Winning */}
        <Sec title="Winning">
          <ul className="space-y-1 text-slate-300">
            <Li>The puzzle is solved when every white cell matches the
              solution. Completion is checked <B>automatically</B> after each
              letter you type.</Li>
            <Li>Your solve time is displayed in the victory screen.</Li>
            <Li>After winning, the completed grid is shown in green for
              review. Use the difficulty buttons to try the next level.</Li>
          </ul>
        </Sec>

        {/* Strategy */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Start with short words</B> — they have fewer possibilities and
              their crossings help unlock longer words.</Li>
            <Li><B>Use the theme</B> — knowing the theme narrows down likely
              answers. The theme name is shown above the grid.</Li>
            <Li><B>Work the crossings</B> — letters shared between Across and
              Down words give you two chances to figure them out.</Li>
            <Li><B>Check sparingly</B> — use the Check button to verify a section
              when you are unsure, rather than guessing blindly.</Li>
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

// ── Component ───────────────────────────────────────────────────────

function CrosswordSinglePlayer({ onGameEnd }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void } = {}) {
  const { load, save, clear } = useGameState<CrosswordSaved>('crossword')
  const savedRef = useRef(load())
  const saved = savedRef.current
  const today = getTodayString()

  // Audio
  const song = useMemo(() => getSongForGame('crossword'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('crossword')

  // Core state
  const [difficulty, setDifficulty] = useState<Difficulty>(
    saved?.dateStr === today ? saved.difficulty : 'easy',
  )
  const [completedDifficulties, setCompletedDifficulties] = useState<Record<string, Difficulty[]>>(
    saved?.completedDifficulties ?? {},
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>('idle')
  const [puzzle, setPuzzle] = useState<CrosswordPuzzle | null>(null)
  const [userGrid, setUserGrid] = useState<string[][]>([])
  const [selectedCell, setSelectedCell] = useState<[number, number] | null>(null)
  const [selectedDirection, setSelectedDirection] = useState<Direction>('across')
  const [checkedCells, setCheckedCells] = useState<Set<string>>(new Set())
  const [revealedCells, setRevealedCells] = useState<Set<string>>(new Set())
  const timer = useGameTimer(
    saved?.dateStr === today && saved?.difficulty === difficulty ? saved.elapsed : 0,
  )
  const [showHelp, setShowHelp] = useState(false)
  const [lastWinSeconds, setLastWinSeconds] = useState(0)

  // Is today's puzzle at current difficulty already completed?
  const isCompleted = useMemo(() => {
    return (completedDifficulties[today] ?? []).includes(difficulty)
  }, [completedDifficulties, today, difficulty])

  // Generate puzzle on difficulty change or mount
  useEffect(() => {
    const newPuzzle = generatePuzzle(today, difficulty, CROSSWORD_THEMES)

    if (isCompleted) {
      // Show completed puzzle with solution filled in (read-only)
      setPuzzle(newPuzzle)
      setUserGrid(newPuzzle.grid.map(row => row.map(cell => cell.isBlack ? '' : cell.letter)))
      setGameStatus('idle')
      setSelectedCell(null)
      return
    }

    // Restore saved state if it matches today + difficulty
    if (saved?.dateStr === today && saved?.difficulty === difficulty && saved?.gameStatus === 'playing') {
      setPuzzle(newPuzzle)
      setUserGrid(saved.userGrid)
      setGameStatus('playing')
      return
    }

    setPuzzle(newPuzzle)
    setUserGrid(createEmptyUserGrid(newPuzzle))
    setGameStatus('playing')
    setSelectedCell(null)
    setCheckedCells(new Set())
    setRevealedCells(new Set())
    timer.reset()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [difficulty, today, isCompleted])

  // Persist state
  useEffect(() => {
    if (gameStatus === 'playing' && puzzle) {
      save({
        dateStr: today,
        difficulty,
        userGrid,
        gameStatus,
        elapsed: timer.seconds,
        completedDifficulties,
      })
    }
  }, [userGrid, gameStatus, timer.seconds, today, difficulty, completedDifficulties, puzzle, save])

  // Active word based on selection
  const activeWord = useMemo(() => {
    if (!puzzle || !selectedCell) return null
    const words = getWordsAtCell(puzzle, selectedCell[0], selectedCell[1])
    return words.find(w => w.direction === selectedDirection) ?? words[0] ?? null
  }, [puzzle, selectedCell, selectedDirection])

  const activeWordCells = useMemo(() => {
    if (!activeWord) return new Set<string>()
    return new Set(getWordCells(activeWord).map(([r, c]) => `${r},${c}`))
  }, [activeWord])

  // Clue lists
  const acrossClues = useMemo(() =>
    puzzle?.placedWords.filter(w => w.direction === 'across').sort((a, b) => a.number - b.number) ?? [],
  [puzzle])
  const downClues = useMemo(() =>
    puzzle?.placedWords.filter(w => w.direction === 'down').sort((a, b) => a.number - b.number) ?? [],
  [puzzle])

  // ── Handlers ────────────────────────────────────────────────────

  const initAudio = useCallback(() => {
    music.init(); sfx.init(); music.start()
  }, [music, sfx])

  const handleCellClick = useCallback((row: number, col: number) => {
    if (!puzzle) return
    if (puzzle.grid[row][col].isBlack) return
    if (gameStatus === 'playing') {
      initAudio()
      if (!timer.isRunning) timer.start()
    }

    if (selectedCell?.[0] === row && selectedCell?.[1] === col) {
      setSelectedDirection(d => d === 'across' ? 'down' : 'across')
    } else {
      setSelectedCell([row, col])
      // Auto-set direction to match the word at this cell
      const words = getWordsAtCell(puzzle, row, col)
      if (words.length === 1) setSelectedDirection(words[0].direction)
    }
  }, [puzzle, gameStatus, selectedCell, timer, initAudio])

  const checkCompletion = useCallback((grid: string[][]) => {
    if (!puzzle) return
    if (isPuzzleComplete(puzzle, grid)) {
      timer.stop()
      const seconds = timer.seconds
      setLastWinSeconds(seconds)
      setCompletedDifficulties(prev => {
        const todayList = prev[today] ?? []
        if (todayList.includes(difficulty)) return prev
        const next = { ...prev, [today]: [...todayList, difficulty] }
        save({ dateStr: today, difficulty, userGrid: grid, gameStatus: 'won', elapsed: seconds, completedDifficulties: next })
        return next
      })
      clear()
      setGameStatus('won')
      onGameEnd?.('win')
    }
  }, [puzzle, timer, today, difficulty, save, clear, onGameEnd])

  const handleLetterInput = useCallback((letter: string) => {
    if (!puzzle || !selectedCell || gameStatus !== 'playing') return
    const [r, c] = selectedCell
    if (puzzle.grid[r][c].isBlack) return

    initAudio()
    if (!timer.isRunning) timer.start()

    const newGrid = userGrid.map(row => [...row])
    newGrid[r][c] = letter.toUpperCase()
    setUserGrid(newGrid)

    // Clear checked/revealed status for this cell
    const key = `${r},${c}`
    if (checkedCells.has(key)) setCheckedCells(prev => { const s = new Set(prev); s.delete(key); return s })

    // Auto-advance to next cell in current direction
    const nextR = selectedDirection === 'down' ? r + 1 : r
    const nextC = selectedDirection === 'across' ? c + 1 : c
    if (nextR < puzzle.height && nextC < puzzle.width && !puzzle.grid[nextR][nextC].isBlack) {
      setSelectedCell([nextR, nextC])
    }

    checkCompletion(newGrid)
  }, [puzzle, selectedCell, selectedDirection, gameStatus, userGrid, timer, initAudio, checkedCells, checkCompletion])

  const handleBackspace = useCallback(() => {
    if (!puzzle || !selectedCell || gameStatus !== 'playing') return
    const [r, c] = selectedCell

    const newGrid = userGrid.map(row => [...row])
    if (newGrid[r][c] !== '') {
      newGrid[r][c] = ''
      setUserGrid(newGrid)
    } else {
      const prevR = selectedDirection === 'down' ? r - 1 : r
      const prevC = selectedDirection === 'across' ? c - 1 : c
      if (prevR >= 0 && prevC >= 0 && !puzzle.grid[prevR]?.[prevC]?.isBlack) {
        setSelectedCell([prevR, prevC])
        newGrid[prevR][prevC] = ''
        setUserGrid(newGrid)
      }
    }
  }, [puzzle, selectedCell, selectedDirection, gameStatus, userGrid])

  // Physical keyboard
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (gameStatus !== 'playing') return
      if (/^[a-zA-Z]$/.test(e.key)) { e.preventDefault(); handleLetterInput(e.key) }
      else if (e.key === 'Backspace') { e.preventDefault(); handleBackspace() }
      else if (e.key === 'Tab') { e.preventDefault(); setSelectedDirection(d => d === 'across' ? 'down' : 'across') }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [handleLetterInput, handleBackspace, gameStatus])

  const handleCheck = useCallback(() => {
    if (!puzzle || gameStatus !== 'playing') return
    const newChecked = new Set(checkedCells)
    for (let r = 0; r < puzzle.height; r++) {
      for (let c = 0; c < puzzle.width; c++) {
        if (puzzle.grid[r][c].isBlack || userGrid[r][c] === '') continue
        if (userGrid[r][c].toUpperCase() !== puzzle.grid[r][c].letter) {
          newChecked.add(`${r},${c}`)
        }
      }
    }
    setCheckedCells(newChecked)
  }, [puzzle, gameStatus, userGrid, checkedCells])

  const handleReveal = useCallback(() => {
    if (!puzzle || !selectedCell || gameStatus !== 'playing') return
    const [r, c] = selectedCell
    if (puzzle.grid[r][c].isBlack) return
    const newGrid = userGrid.map(row => [...row])
    newGrid[r][c] = puzzle.grid[r][c].letter
    setUserGrid(newGrid)
    setRevealedCells(prev => new Set(prev).add(`${r},${c}`))
    checkCompletion(newGrid)
  }, [puzzle, selectedCell, gameStatus, userGrid, checkCompletion])

  const handleClueClick = useCallback((word: PlacedWord) => {
    if (gameStatus === 'playing') {
      initAudio()
      if (!timer.isRunning) timer.start()
    }
    setSelectedCell([word.row, word.col])
    setSelectedDirection(word.direction)
  }, [gameStatus, initAudio, timer])

  const handleDifficultyChange = useCallback((d: SharedDifficulty) => {
    setDifficulty(d as Difficulty)
    savedRef.current = null // Don't restore when switching difficulty
  }, [])

  const isWordComplete = useCallback((word: PlacedWord): boolean => {
    return getWordCells(word).every(([r, c]) => userGrid[r]?.[c] !== '')
  }, [userGrid])

  // Theme display name & background
  const themeDisplay = puzzle?.theme.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) ?? ''
  const themeBg = useMemo(() => puzzle ? getThemeBackground(puzzle.theme) : null, [puzzle])

  // Dynamic cell size — shrink for wider grids so they don't overflow
  // Max grid width ~320px mobile, ~400px desktop; cells should never be smaller than 24px
  const cellSize = useMemo(() => {
    if (!puzzle) return 40
    const maxGridPx = 360 // conservative mobile width
    return Math.max(24, Math.min(40, Math.floor(maxGridPx / puzzle.width)))
  }, [puzzle])

  // ── Controls toolbar ──────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between flex-wrap gap-2">
      <DifficultySelector
        value={difficulty}
        onChange={handleDifficultyChange}
        options={['easy', 'medium', 'hard']}
      />
      <div className="flex items-center space-x-2">
        <button
          onClick={() => setShowHelp(true)}
          className="p-1.5 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-white"
          title="How to play"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
        {gameStatus === 'playing' && (
          <>
            <button
              onClick={handleCheck}
              className="px-2.5 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
            >
              Check
            </button>
            <button
              onClick={handleReveal}
              className="px-2.5 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
              title="Reveal selected cell"
            >
              Reveal
            </button>
          </>
        )}
      </div>
    </div>
  )

  // ── Render ────────────────────────────────────────────────────

  return (
    <GameLayout title="Crossword" controls={controls}>
      <div className="flex flex-col items-center space-y-4 w-full max-w-3xl">

        {/* Completed banner */}
        {isCompleted && gameStatus === 'idle' && (
          <div className="text-center p-4 bg-emerald-900/30 rounded-lg border border-emerald-700/50 w-full">
            <p className="text-emerald-400 font-bold mb-2">
              Completed today&apos;s {difficulty} puzzle!
            </p>
            <div className="flex gap-2 justify-center">
              {(['easy', 'medium', 'hard'] as Difficulty[]).map(d => {
                const done = (completedDifficulties[today] ?? []).includes(d)
                return (
                  <button
                    key={d}
                    onClick={() => handleDifficultyChange(d)}
                    className={`px-3 py-1.5 rounded text-sm font-medium capitalize transition-colors ${
                      done
                        ? 'bg-emerald-900/50 text-emerald-400 cursor-default'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    {d} {done ? '\u2713' : ''}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Not enough words fallback */}
        {puzzle && puzzle.placedWords.length < 3 && gameStatus === 'playing' && (
          <div className="text-center p-4 bg-slate-800 rounded-lg border border-slate-600">
            <p className="text-yellow-400 text-sm">Puzzle generation produced a small grid. Try a different difficulty!</p>
          </div>
        )}

        {/* Game area — shown when playing or viewing completed puzzle */}
        {puzzle && puzzle.placedWords.length >= 3 && (gameStatus === 'playing' || (isCompleted && gameStatus === 'idle')) && (
          <>
            {/* Theme badge */}
            <div className="text-center">
              <span className="text-xs text-slate-500 uppercase tracking-wider">Theme</span>
              <p className="text-sm font-medium text-slate-300">{themeDisplay}</p>
            </div>

            <div className="flex flex-col lg:flex-row items-center lg:items-start justify-center gap-3 w-full">
              {/* Grid */}
              <div className="relative border-2 border-slate-500 mx-auto shrink-0 p-[2px] overflow-hidden">
                {/* Theme background inside grid frame */}
                {themeBg && (
                  <>
                    <div
                      className="absolute inset-0 pointer-events-none z-0"
                      style={{ background: themeBg.gradient, opacity: themeBg.opacity, filter: 'blur(1px)' }}
                    />
                    <div
                      className="absolute inset-0 pointer-events-none opacity-[0.25] z-0"
                      style={{ filter: 'blur(2px)' }}
                    >
                      {[
                        { top: '-15%', left: '-10%', rot: -18, size: '16rem' },
                        { top: '15%', left: '30%', rot: 12, size: '18rem' },
                        { top: '50%', left: '-5%', rot: -6, size: '15rem' },
                      ].map((pos, i) => (
                        <span
                          key={i}
                          className="absolute select-none"
                          style={{
                            top: pos.top, left: pos.left,
                            fontSize: pos.size,
                            transform: `rotate(${pos.rot}deg)`,
                          }}
                        >
                          {themeBg.emoji}
                        </span>
                      ))}
                    </div>
                  </>
                )}
                <div
                  className="relative z-10 grid gap-0"
                  style={{ gridTemplateColumns: `repeat(${puzzle.width}, ${cellSize}px)` }}
                >
                {puzzle.grid.map((row, r) =>
                  row.map((cell, c) => {
                    if (cell.isBlack) {
                      return <div key={`${r}-${c}`} className="bg-slate-950/80" style={{ width: cellSize, height: cellSize }} />
                    }

                    const viewing = isCompleted && gameStatus === 'idle'
                    const isSelected = selectedCell?.[0] === r && selectedCell?.[1] === c
                    const isInWord = activeWordCells.has(`${r},${c}`)
                    const userLetter = userGrid[r]?.[c] ?? ''
                    const cellKey = `${r},${c}`
                    const isWrong = !viewing && checkedCells.has(cellKey) && userLetter.toUpperCase() !== cell.letter
                    const isRevealed = !viewing && revealedCells.has(cellKey)

                    let bgClass = viewing ? 'bg-emerald-950/30' : 'bg-slate-800/70'
                    if (isSelected) bgClass = viewing ? 'bg-emerald-800/40' : 'bg-blue-700/50'
                    else if (isInWord) bgClass = viewing ? 'bg-emerald-900/25' : 'bg-blue-900/30'

                    // Scale font for smaller cells
                    const fontSize = cellSize >= 36 ? 'text-base' : cellSize >= 28 ? 'text-sm' : 'text-xs'
                    const numSize = cellSize >= 36 ? 'text-[9px]' : 'text-[7px]'

                    return (
                      <div
                        key={`${r}-${c}`}
                        onClick={() => handleCellClick(r, c)}
                        className={`relative border border-slate-600 ${bgClass} flex items-center justify-center cursor-pointer transition-colors`}
                        style={{ width: cellSize, height: cellSize }}
                      >
                        {cell.number !== null && (
                          <span className={`absolute top-0 left-0.5 ${numSize} text-slate-500 leading-none select-none`}>
                            {cell.number}
                          </span>
                        )}
                        <span className={`${fontSize} font-bold select-none ${
                          viewing ? 'text-emerald-400' : isWrong ? 'text-red-400' : isRevealed ? 'text-yellow-400' : 'text-white'
                        }`}>
                          {userLetter}
                        </span>
                      </div>
                    )
                  }),
                )}
                </div>
              </div>

              {/* Clues panel */}
              <div className="flex flex-col gap-3 max-h-[400px] overflow-y-auto pr-1 w-full lg:w-56 text-left">
                {acrossClues.length > 0 && (
                  <div>
                    <h3 className="text-sm font-bold text-slate-300 mb-1">Across</h3>
                    <div className="space-y-0.5">
                      {acrossClues.map(w => {
                        const isActive = activeWord === w
                        const complete = isWordComplete(w)
                        return (
                          <button
                            key={`a-${w.number}`}
                            onClick={() => handleClueClick(w)}
                            className={`w-full text-left px-2 py-1 rounded text-xs transition-colors ${
                              isActive
                                ? 'bg-blue-900/40 text-blue-300'
                                : complete
                                  ? 'text-emerald-400/70 line-through'
                                  : 'text-slate-400 hover:bg-slate-700/50'
                            }`}
                          >
                            <span className="font-mono font-bold mr-1">{w.number}.</span>
                            {w.clue}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
                {downClues.length > 0 && (
                  <div>
                    <h3 className="text-sm font-bold text-slate-300 mb-1">Down</h3>
                    <div className="space-y-0.5">
                      {downClues.map(w => {
                        const isActive = activeWord === w
                        const complete = isWordComplete(w)
                        return (
                          <button
                            key={`d-${w.number}`}
                            onClick={() => handleClueClick(w)}
                            className={`w-full text-left px-2 py-1 rounded text-xs transition-colors ${
                              isActive
                                ? 'bg-blue-900/40 text-blue-300'
                                : complete
                                  ? 'text-emerald-400/70 line-through'
                                  : 'text-slate-400 hover:bg-slate-700/50'
                            }`}
                          >
                            <span className="font-mono font-bold mr-1">{w.number}.</span>
                            {w.clue}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* On-screen keyboard — only when actively playing */}
            {gameStatus === 'playing' && <div className="flex flex-col items-center gap-1 pt-2">
              {KB_ROWS.map((row, ri) => (
                <div key={ri} className="flex gap-1">
                  {row.map(key => (
                    <button
                      key={key}
                      onClick={() => handleLetterInput(key)}
                      className="w-8 h-10 sm:w-9 sm:h-11 rounded bg-slate-700 text-white text-sm font-medium
                        hover:bg-slate-600 active:bg-slate-500 transition-colors select-none"
                    >
                      {key}
                    </button>
                  ))}
                  {ri === 2 && (
                    <button
                      onClick={handleBackspace}
                      className="w-12 h-10 sm:w-14 sm:h-11 rounded bg-slate-700 text-white text-xs font-medium
                        hover:bg-slate-600 active:bg-slate-500 transition-colors select-none"
                    >
                      DEL
                    </button>
                  )}
                </div>
              ))}
            </div>}
          </>
        )}

        {/* Game over modal */}
        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            message={`Solved in ${formatTime(lastWinSeconds)}! Theme: ${themeDisplay}`}
            onPlayAgain={() => setGameStatus('idle')}
            playAgainText="View Puzzle"
            music={music}
            sfx={sfx}
          />
        )}

      </div>

      {showHelp && <CrosswordHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first_to_win — first to complete wins) ─────────────

function CrosswordRaceWrapper({ roomId, onLeave }: { roomId: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, localScore, opponentLevelUp, reportFinish, leaveRoom } = useRaceMode(roomId, 'first_to_win')
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
        localScore={localScore}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
        onDismiss={onLeave}
        onBackToLobby={onLeave}
        onLeaveGame={leaveRoom}
      />
      <CrosswordSinglePlayer onGameEnd={handleGameEnd} />
    </div>
  )
}

// ── Default export with multiplayer wrapper ──────────────────────────

export default function Crossword() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'crossword',
        gameName: 'Crossword',
        modes: ['first_to_win'],
        maxPlayers: 2,
        modeDescriptions: { first_to_win: 'First to complete the crossword wins' },
      }}
      renderSinglePlayer={() => <CrosswordSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, _roomConfig, onLeave) =>
        <CrosswordRaceWrapper roomId={roomId} onLeave={onLeave} />
      }
    />
  )
}
