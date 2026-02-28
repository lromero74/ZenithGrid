/**
 * Sudoku game — fill the 9x9 grid with logic.
 *
 * Features: 4 difficulty levels, notes mode, conflict highlighting,
 * peer highlighting, undo, hints, timer.
 */

import { useState, useCallback, useMemo } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import { useGameTimer } from '../../../hooks/useGameTimer'
import {
  generatePuzzle, cloneBoard, getConflicts,
  type SudokuBoard as Board,
  type Difficulty,
} from './sudokuEngine'
import { SudokuBoard } from './SudokuBoard'
import { SudokuControls } from './SudokuControls'
import type { GameStatus } from '../../../types'

interface PuzzleState {
  puzzle: Board
  solution: Board
  given: boolean[][]
}

function createPuzzleState(difficulty: Difficulty): PuzzleState {
  const { puzzle, solution } = generatePuzzle(difficulty)
  const given = puzzle.map(row => row.map(cell => cell !== 0))
  return { puzzle: cloneBoard(puzzle), solution, given }
}

export default function Sudoku() {
  const [difficulty, setDifficulty] = useState<Difficulty>('easy')
  const [puzzleState, setPuzzleState] = useState(() => createPuzzleState('easy'))
  const [board, setBoard] = useState<Board>(() => cloneBoard(puzzleState.puzzle))
  const [selected, setSelected] = useState<[number, number] | null>(null)
  const [notesMode, setNotesMode] = useState(false)
  const [notes, setNotes] = useState<Map<string, Set<number>>>(new Map())
  const [history, setHistory] = useState<Board[]>([])
  const [hints, setHints] = useState(3)
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const timer = useGameTimer()

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
    if (!timer.isRunning) timer.start()
    setSelected([r, c])
  }, [gameStatus, timer])

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
    setBoard(newBoard)

    // Clear notes for this cell
    setNotes(prev => {
      const newNotes = new Map(prev)
      newNotes.delete(`${r},${c}`)
      return newNotes
    })

    if (checkWin(newBoard)) {
      setGameStatus('won')
      timer.stop()
    }
  }, [selected, gameStatus, notesMode, board, puzzleState.given, checkWin, timer])

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
    }
  }, [hints, selected, gameStatus, board, puzzleState, checkWin, timer])

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
  }, [difficulty, timer])

  const controls = (
    <DifficultySelector
      value={difficulty}
      onChange={(d) => handleNewGame(d as Difficulty)}
      options={['easy', 'medium', 'hard', 'expert']}
    />
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
          />
        )}
      </div>
    </GameLayout>
  )
}
