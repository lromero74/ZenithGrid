/**
 * Sudoku controls — digit pad and toolbar buttons.
 */

import { Pencil, Undo2, Lightbulb, RotateCcw } from 'lucide-react'

interface SudokuControlsProps {
  onDigit: (num: number) => void
  onErase: () => void
  onUndo: () => void
  onHint: () => void
  onNoteToggle: () => void
  onNewGame: () => void
  notesMode: boolean
  hintsRemaining: number
  canUndo: boolean
}

export function SudokuControls({
  onDigit, onErase, onUndo, onHint, onNoteToggle, onNewGame,
  notesMode, hintsRemaining, canUndo,
}: SudokuControlsProps) {
  return (
    <div className="flex flex-col items-center space-y-3 w-full max-w-[315px] sm:max-w-[405px]">
      {/* Digit pad */}
      <div className="flex space-x-1 sm:space-x-1.5">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => (
          <button
            key={n}
            onClick={() => onDigit(n)}
            className="w-8 h-10 sm:w-10 sm:h-12 bg-slate-700 hover:bg-slate-600 text-white rounded font-bold text-sm sm:text-lg transition-colors"
          >
            {n}
          </button>
        ))}
      </div>

      {/* Toolbar */}
      <div className="flex items-center space-x-2 sm:space-x-3">
        <button
          onClick={onErase}
          className="px-2 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-xs sm:text-sm transition-colors"
        >
          Erase
        </button>
        <button
          onClick={onUndo}
          disabled={!canUndo}
          className="p-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded disabled:opacity-40 transition-colors"
          title="Undo"
        >
          <Undo2 className="w-4 h-4" />
        </button>
        <button
          onClick={onNoteToggle}
          className={`p-1.5 rounded transition-colors ${
            notesMode ? 'bg-blue-600 text-white' : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
          }`}
          title="Notes mode"
        >
          <Pencil className="w-4 h-4" />
        </button>
        <button
          onClick={onHint}
          disabled={hintsRemaining === 0}
          className="flex items-center space-x-1 px-2 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-xs disabled:opacity-40 transition-colors"
          title={`Hints: ${hintsRemaining}`}
        >
          <Lightbulb className="w-3.5 h-3.5" />
          <span>{hintsRemaining}</span>
        </button>
        <button
          onClick={onNewGame}
          className="p-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors"
          title="New Game"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
