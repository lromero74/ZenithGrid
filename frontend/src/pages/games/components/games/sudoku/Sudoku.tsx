/**
 * Sudoku game — fill the 9x9 grid with logic.
 *
 * Features: 4 difficulty levels, notes mode, conflict highlighting,
 * peer highlighting, undo, hints, timer.
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import { useGameTimer } from '../../../hooks/useGameTimer'
import { useGameState } from '../../../hooks/useGameState'
import {
  generatePuzzle, cloneBoard, getConflicts,
  type SudokuBoard as Board,
  type Difficulty,
} from './sudokuEngine'
import { SudokuBoard } from './SudokuBoard'
import { SudokuControls } from './SudokuControls'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

interface PuzzleState {
  puzzle: Board
  solution: Board
  given: boolean[][]
}

interface SudokuSaved {
  difficulty: Difficulty
  puzzleState: PuzzleState
  board: Board
  notes: [string, number[]][]
  hints: number
  gameStatus: GameStatus
  notesMode: boolean
  elapsed: number
}

function createPuzzleState(difficulty: Difficulty): PuzzleState {
  const { puzzle, solution } = generatePuzzle(difficulty)
  const given = puzzle.map(row => row.map(cell => cell !== 0))
  return { puzzle: cloneBoard(puzzle), solution, given }
}

function SudokuHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Sudoku</h2>
        <Sec title="Goal"><p>Fill every cell in the 9×9 grid so that each <B>row</B>, <B>column</B>, and <B>3×3 box</B> contains the digits 1–9 exactly once.</p></Sec>
        <Sec title="How to Play"><ul className="space-y-1">
          <Li>Click a cell to select it, then enter a number 1–9.</Li>
          <Li><B>Given</B> cells (pre-filled) cannot be changed.</Li>
          <Li>Wrong numbers are highlighted — the solution is checked as you go.</Li>
        </ul></Sec>
        <Sec title="Difficulty"><ul className="space-y-1">
          <Li><B>Easy</B> — More givens, straightforward logic.</Li>
          <Li><B>Medium</B> — Fewer givens, requires more deduction.</Li>
          <Li><B>Hard</B> — Minimal givens, advanced techniques needed.</Li>
          <Li><B>Expert</B> — Very few givens, challenging puzzles.</Li>
        </ul></Sec>
        <Sec title="Strategy Tips"><ul className="space-y-1">
          <Li>Start with rows/columns/boxes that have the most filled cells.</Li>
          <Li>Use elimination — if 8 of 9 numbers are placed, the 9th is determined.</Li>
          <Li>Look for "naked pairs" — two cells in a unit with the same two candidates.</Li>
        </ul></Sec>
      </div>
    </div>
  )
}

function SudokuSinglePlayer({ onGameEnd, onStateChange: _onStateChange }: { onGameEnd?: (result: 'win' | 'loss' | 'draw', score?: number) => void; onStateChange?: (state: object) => void } = {}) {
  const { load, save, clear } = useGameState<SudokuSaved>('sudoku')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('sudoku'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('sudoku')

  const [showHelp, setShowHelp] = useState(false)
  const initPuzzle = saved?.puzzleState ?? createPuzzleState('easy')
  const [difficulty, setDifficulty] = useState<Difficulty>(saved?.difficulty ?? 'easy')
  const [puzzleState, setPuzzleState] = useState<PuzzleState>(() => initPuzzle)
  const [board, setBoard] = useState<Board>(() => saved?.board ?? cloneBoard(initPuzzle.puzzle))
  const [selected, setSelected] = useState<[number, number] | null>(null)
  const [notesMode, setNotesMode] = useState(saved?.notesMode ?? false)
  const [notes, setNotes] = useState<Map<string, Set<number>>>(() => {
    if (saved?.notes) return new Map(saved.notes.map(([k, v]) => [k, new Set(v)]))
    return new Map()
  })
  const [history, setHistory] = useState<Board[]>([])
  const [hints, setHints] = useState(saved?.hints ?? 3)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const timer = useGameTimer(saved?.elapsed)

  // Persist state
  useEffect(() => {
    save({
      difficulty, puzzleState, board, hints, gameStatus, notesMode,
      notes: Array.from(notes.entries()).map(([k, v]) => [k, Array.from(v)]),
      elapsed: timer.seconds,
    })
  }, [difficulty, puzzleState, board, hints, gameStatus, notesMode, notes, timer.seconds, save])

  // Compute conflicts for all cells
  const conflicts = useMemo(() => {
    const set = new Set<string>()
    for (let r = 0; r < 9; r++) {
      for (let c = 0; c < 9; c++) {
        if (board[r][c] > 0) {
          const cellConflicts = getConflicts(board, r, c)
          if (cellConflicts.length > 0) {
            set.add(`${r},${c}`)
            cellConflicts.forEach(([cr, cc]) => set.add(`${cr},${cc}`))
          }
        }
      }
    }
    return set
  }, [board])

  const checkWin = useCallback((b: Board) => {
    for (let r = 0; r < 9; r++) {
      for (let c = 0; c < 9; c++) {
        if (b[r][c] !== puzzleState.solution[r][c]) return false
      }
    }
    return true
  }, [puzzleState.solution])

  const handleCellClick = useCallback((r: number, c: number) => {
    if (gameStatus !== 'playing') return
    music.init()
    sfx.init()
    music.start()
    if (!timer.isRunning) timer.start()
    setSelected([r, c])
  }, [gameStatus, timer, music])

  const handleDigit = useCallback((num: number) => {
    if (!selected || gameStatus !== 'playing') return
    const [r, c] = selected
    if (puzzleState.given[r][c]) return

    if (notesMode) {
      setNotes(prev => {
        const key = `${r},${c}`
        const newNotes = new Map(prev)
        const cellNotes = new Set(prev.get(key) ?? [])
        if (cellNotes.has(num)) cellNotes.delete(num)
        else cellNotes.add(num)
        newNotes.set(key, cellNotes)
        return newNotes
      })
      return
    }

    setHistory(prev => [...prev.slice(-30), cloneBoard(board)])
    const newBoard = cloneBoard(board)
    newBoard[r][c] = num
    sfx.play('enter')
    setBoard(newBoard)

    // Clear notes for this cell
    setNotes(prev => {
      const newNotes = new Map(prev)
      newNotes.delete(`${r},${c}`)
      return newNotes
    })

    if (checkWin(newBoard)) {
      sfx.play('win')
      setGameStatus('won')
      timer.stop()
      onGameEnd?.('win', timer.seconds)
    }
  }, [selected, gameStatus, notesMode, board, puzzleState.given, checkWin, timer, onGameEnd])

  const handleErase = useCallback(() => {
    if (!selected || gameStatus !== 'playing') return
    const [r, c] = selected
    if (puzzleState.given[r][c]) return

    setHistory(prev => [...prev.slice(-30), cloneBoard(board)])
    const newBoard = cloneBoard(board)
    newBoard[r][c] = 0
    setBoard(newBoard)
    setNotes(prev => {
      const newNotes = new Map(prev)
      newNotes.delete(`${r},${c}`)
      return newNotes
    })
  }, [selected, gameStatus, board, puzzleState.given])

  const handleUndo = useCallback(() => {
    if (history.length === 0) return
    setBoard(history[history.length - 1])
    setHistory(h => h.slice(0, -1))
  }, [history])

  const handleHint = useCallback(() => {
    if (hints === 0 || !selected || gameStatus !== 'playing') return
    const [r, c] = selected
    if (puzzleState.given[r][c]) return

    const newBoard = cloneBoard(board)
    newBoard[r][c] = puzzleState.solution[r][c]
    setBoard(newBoard)
    setHints(h => h - 1)

    if (checkWin(newBoard)) {
      setGameStatus('won')
      timer.stop()
      onGameEnd?.('win', timer.seconds)
    }
  }, [hints, selected, gameStatus, board, puzzleState, checkWin, timer, onGameEnd])

  const handleNewGame = useCallback((diff?: Difficulty) => {
    const d = diff ?? difficulty
    const state = createPuzzleState(d)
    setPuzzleState(state)
    setBoard(cloneBoard(state.puzzle))
    setSelected(null)
    setNotesMode(false)
    setNotes(new Map())
    setHistory([])
    setHints(3)
    setGameStatus('playing')
    setDifficulty(d)
    timer.reset()
    music.start()
    clear()
  }, [difficulty, timer, music, clear])

  const controls = (
    <div className="flex items-center justify-between">
      <DifficultySelector
        value={difficulty}
        onChange={(d) => handleNewGame(d as Difficulty)}
        options={['easy', 'medium', 'hard', 'expert']}
      />
      <div className="flex items-center gap-2">
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play"><HelpCircle className="w-4 h-4 text-blue-400" /></button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Sudoku" timer={timer.formatted} controls={controls}>
      <div className="relative flex flex-col items-center space-y-4">
        <SudokuBoard
          board={board}
          solution={puzzleState.solution}
          given={puzzleState.given}
          selected={selected}
          conflicts={conflicts}
          notes={notes}
          onCellClick={handleCellClick}
        />

        <SudokuControls
          onDigit={handleDigit}
          onErase={handleErase}
          onUndo={handleUndo}
          onHint={handleHint}
          onNoteToggle={() => setNotesMode(m => !m)}
          onNewGame={() => handleNewGame()}
          notesMode={notesMode}
          hintsRemaining={hints}
          canUndo={history.length > 0}
        />

        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            message={`Completed in ${timer.formatted}`}
            onPlayAgain={() => handleNewGame()}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <SudokuHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (fastest solve time wins) ──────────────────────────

function SudokuRaceWrapper({ roomId, difficulty: _difficulty }: { roomId: string; difficulty?: string }) {
  const { opponentStatus, raceResult, opponentLevelUp, broadcastState, reportFinish } = useRaceMode(roomId, 'best_score')
  const finishedRef = useRef(false)

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw', score?: number) => {
    if (finishedRef.current) return
    finishedRef.current = true
    // Invert time so faster = higher score
    const invertedScore = score != null ? 999999 - score : 0
    reportFinish(result === 'draw' ? 'loss' : result, invertedScore)
  }, [reportFinish])

  return (
    <div className="relative">
      <RaceOverlay
        raceResult={raceResult}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
      />
      <SudokuSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} />
    </div>
  )
}

export default function Sudoku() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'sudoku',
        gameName: 'Sudoku',
        modes: ['race'],
        hasDifficulty: true,
        raceDescription: 'Fastest to solve the puzzle wins',
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <SudokuSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig) =>
        <SudokuRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} />
      }
    />
  )
}
