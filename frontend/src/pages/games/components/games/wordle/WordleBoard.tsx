/**
 * Wordle board — 6x5 grid of letter tiles with color coding.
 */

import type { LetterResult } from './wordleEngine'

interface WordleBoardProps {
  guesses: string[]
  evaluations: LetterResult[][]
  currentGuess: string
  currentRow: number
  maxGuesses: number
  shake: boolean
}

const RESULT_COLORS: Record<LetterResult, string> = {
  correct: 'bg-emerald-600 border-emerald-600 text-white',
  present: 'bg-yellow-600 border-yellow-600 text-white',
  absent: 'bg-slate-700 border-slate-700 text-white',
}

export function WordleBoard({ guesses, evaluations, currentGuess, currentRow, maxGuesses, shake }: WordleBoardProps) {
  const rows: React.ReactNode[] = []

  for (let row = 0; row < maxGuesses; row++) {
    const cells: React.ReactNode[] = []

    for (let col = 0; col < 5; col++) {
      let letter = ''
      let className = 'w-12 h-12 sm:w-14 sm:h-14 flex items-center justify-center text-lg sm:text-xl font-bold uppercase rounded transition-all duration-300 '

      if (row < currentRow) {
        // Submitted row
        letter = guesses[row]?.[col] ?? ''
        const result = evaluations[row]?.[col]
        className += result ? RESULT_COLORS[result] : 'border-2 border-slate-600'
      } else if (row === currentRow) {
        // Current typing row
        letter = currentGuess[col] ?? ''
        className += letter
          ? 'border-2 border-slate-400 text-white'
          : 'border-2 border-slate-600'
      } else {
        // Empty future row
        className += 'border-2 border-slate-700'
      }

      cells.push(
        <div key={col} className={className}>
          {letter}
        </div>
      )
    }

    rows.push(
      <div
        key={row}
        className={`flex space-x-1.5 ${row === currentRow && shake ? 'animate-shake' : ''}`}
      >
        {cells}
      </div>
    )
  }

  return <div className="flex flex-col space-x-0 space-y-1.5">{rows}</div>
}
