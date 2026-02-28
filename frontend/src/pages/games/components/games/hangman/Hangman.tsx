/**
 * Hangman game — guess the word one letter at a time.
 *
 * Features: categorized word lists, SVG hangman, QWERTY keyboard, streak tracking.
 */

import { useState, useCallback, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { HangmanDrawing } from './HangmanDrawing'
import { HangmanKeyboard } from './HangmanKeyboard'
import { selectWord, getDisplayWord, processGuess, isGameWon, isGameLost, getWrongGuesses } from './hangmanEngine'
import { CATEGORIES, MAX_WRONG_GUESSES } from './wordLists'
import { useKeyboard } from '../../../hooks/useKeyboard'
import type { GameStatus } from '../../../types'

export default function Hangman() {
  const [category, setCategory] = useState(CATEGORIES[0])
  const [word, setWord] = useState(() => selectWord(CATEGORIES[0]))
  const [guessedLetters, setGuessedLetters] = useState<Set<string>>(new Set())
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [streak, setStreak] = useState(0)

  const wrongGuessCount = getWrongGuesses(word, guessedLetters)
  const correctLetters = new Set(
    [...guessedLetters].filter(l => word.includes(l))
  )

  const handleGuess = useCallback((letter: string) => {
    if (gameStatus !== 'playing' || guessedLetters.has(letter)) return
    const upper = letter.toUpperCase()
    if (!/^[A-Z]$/.test(upper)) return

    const newGuessed = new Set(guessedLetters)
    newGuessed.add(upper)
    setGuessedLetters(newGuessed)

    const isCorrect = processGuess(word, upper)

    if (isGameWon(word, newGuessed)) {
      setGameStatus('won')
      setStreak(s => s + 1)
    } else if (!isCorrect && isGameLost(getWrongGuesses(word, newGuessed))) {
      setGameStatus('lost')
      setStreak(0)
    }
  }, [gameStatus, guessedLetters, word])

  // Physical keyboard support
  useKeyboard((e) => {
    if (e.key.length === 1 && /[a-zA-Z]/.test(e.key)) {
      handleGuess(e.key.toUpperCase())
    }
  }, gameStatus === 'playing')

  const handleNewGame = useCallback((newCategory?: string) => {
    const cat = newCategory || category
    setCategory(cat)
    setWord(selectWord(cat))
    setGuessedLetters(new Set())
    setGameStatus('playing')
  }, [category])

  // Reset when category changes via button
  useEffect(() => {
    // Don't reset on initial render — only when user clicks a category button
  }, [])

  const controls = (
    <div className="flex flex-col space-y-2">
      {/* Category pills */}
      <div className="flex flex-wrap gap-1.5">
        {CATEGORIES.map(cat => (
          <button
            key={cat}
            onClick={() => handleNewGame(cat)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium capitalize transition-colors ${
              category === cat
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>
      {/* Streak */}
      {streak > 0 && (
        <p className="text-xs text-yellow-400">Streak: {streak}</p>
      )}
    </div>
  )

  return (
    <GameLayout title="Hangman" controls={controls}>
      <div className="relative w-full max-w-md">
        <div className="flex flex-col items-center space-y-4">
          {/* Hangman drawing */}
          <HangmanDrawing wrongGuesses={wrongGuessCount} />

          {/* Wrong guess counter */}
          <p className="text-sm text-slate-400">
            Wrong: {wrongGuessCount} / {MAX_WRONG_GUESSES}
          </p>

          {/* Word display */}
          <p className="text-2xl sm:text-3xl font-mono tracking-widest text-white text-center min-h-[40px]">
            {getDisplayWord(word, guessedLetters)}
          </p>

          {/* Keyboard */}
          <HangmanKeyboard
            guessedLetters={guessedLetters}
            correctLetters={correctLetters}
            onGuess={handleGuess}
            disabled={gameStatus !== 'playing'}
          />
        </div>

        {gameStatus !== 'playing' && gameStatus !== 'idle' && (
          <GameOverModal
            status={gameStatus}
            message={
              gameStatus === 'won'
                ? `You got it!`
                : `The word was: ${word}`
            }
            onPlayAgain={() => handleNewGame()}
          />
        )}
      </div>
    </GameLayout>
  )
}
