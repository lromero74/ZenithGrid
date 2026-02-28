/**
 * Wordle game engine — pure logic, no React.
 *
 * Handles guess evaluation, keyboard state, hard mode checking,
 * and daily word selection.
 */

export type LetterResult = 'correct' | 'present' | 'absent'
export type KeyboardState = Record<string, LetterResult>

export interface PreviousGuess {
  guess: string
  evaluation: LetterResult[]
}

/**
 * Evaluate a guess against the answer.
 * Returns array of 5 LetterResults.
 *
 * Algorithm:
 * 1. First pass: mark correct letters and track remaining answer letters
 * 2. Second pass: mark present/absent from remaining
 */
export function evaluateGuess(guess: string, answer: string): LetterResult[] {
  const result: LetterResult[] = Array(5).fill('absent')
  const remaining: (string | null)[] = answer.split('')
  const guessArr = guess.split('')

  // First pass: find correct (exact matches)
  for (let i = 0; i < 5; i++) {
    if (guessArr[i] === remaining[i]) {
      result[i] = 'correct'
      remaining[i] = null
      guessArr[i] = ''
    }
  }

  // Second pass: find present (right letter, wrong position)
  for (let i = 0; i < 5; i++) {
    if (guessArr[i] === '') continue
    const idx = remaining.indexOf(guessArr[i])
    if (idx !== -1) {
      result[i] = 'present'
      remaining[idx] = null
    }
  }

  return result
}

/** Check if a word is in the dictionary. Case-insensitive. */
export function isValidWord(word: string, dictionary: string[]): boolean {
  return dictionary.includes(word.toUpperCase())
}

/** Get the daily word based on date. Deterministic selection. */
export function getDailyWord(answerList: string[], date: Date): string {
  // Days since epoch
  const epochMs = date.getTime()
  const daysSinceEpoch = Math.floor(epochMs / 86400000)
  return answerList[daysSinceEpoch % answerList.length]
}

/**
 * Update keyboard state after a guess.
 * Priority: correct > present > absent (never downgrade).
 */
export function updateKeyboardState(
  state: KeyboardState,
  guess: string,
  evaluation: LetterResult[]
): KeyboardState {
  const newState = { ...state }
  const priority: Record<LetterResult, number> = { correct: 3, present: 2, absent: 1 }

  for (let i = 0; i < 5; i++) {
    const letter = guess[i]
    const result = evaluation[i]
    const current = newState[letter]
    if (!current || priority[result] > priority[current]) {
      newState[letter] = result
    }
  }

  return newState
}

/**
 * Check hard mode constraints.
 * Returns null if valid, or an error message string.
 *
 * Rules:
 * - Any letter marked 'correct' in previous guesses must be in the same position
 * - Any letter marked 'present' in previous guesses must appear somewhere
 */
export function checkHardMode(guess: string, previousGuesses: PreviousGuess[]): string | null {
  for (const prev of previousGuesses) {
    for (let i = 0; i < 5; i++) {
      if (prev.evaluation[i] === 'correct' && guess[i] !== prev.guess[i]) {
        return `Position ${i + 1} must be ${prev.guess[i]}`
      }
    }
    for (let i = 0; i < 5; i++) {
      if (prev.evaluation[i] === 'present' && !guess.includes(prev.guess[i])) {
        return `Guess must contain ${prev.guess[i]}`
      }
    }
  }
  return null
}
