/**
 * On-screen QWERTY keyboard for Hangman.
 *
 * Keys color-code based on whether the guess was correct or wrong.
 */

const ROWS = [
  ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
  ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
  ['Z', 'X', 'C', 'V', 'B', 'N', 'M'],
]

interface HangmanKeyboardProps {
  guessedLetters: Set<string>
  correctLetters: Set<string>
  onGuess: (letter: string) => void
  disabled: boolean
}

export function HangmanKeyboard({ guessedLetters, correctLetters, onGuess, disabled }: HangmanKeyboardProps) {
  return (
    <div className="flex flex-col items-center space-y-1.5">
      {ROWS.map((row, i) => (
        <div key={i} className="flex space-x-1 sm:space-x-1.5">
          {row.map(letter => {
            const isGuessed = guessedLetters.has(letter)
            const isCorrect = correctLetters.has(letter)

            let className = 'w-7 h-9 sm:w-8 sm:h-10 rounded text-xs sm:text-sm font-bold transition-colors '
            if (!isGuessed) {
              className += 'bg-slate-600 text-white hover:bg-slate-500 cursor-pointer'
            } else if (isCorrect) {
              className += 'bg-emerald-700 text-emerald-200 cursor-default'
            } else {
              className += 'bg-red-900/50 text-slate-600 cursor-default'
            }

            return (
              <button
                key={letter}
                onClick={() => onGuess(letter)}
                disabled={disabled || isGuessed}
                className={className}
              >
                {letter}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
