/**
 * Hangman game — guess the word one letter at a time.
 *
 * Features: categorized word lists, SVG hangman, QWERTY keyboard, streak tracking.
 */

import { useState, useCallback, useEffect, useMemo, useRef} from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { HangmanDrawing } from './HangmanDrawing'
import { HangmanKeyboard } from './HangmanKeyboard'
import { selectWord, getDisplayWord, processGuess, isGameWon, isGameLost, getWrongGuesses } from './hangmanEngine'
import { CATEGORIES, MAX_WRONG_GUESSES } from './wordLists'
import { useKeyboard } from '../../../hooks/useKeyboard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { useGameSFX } from '../../../audio/useGameSFX'

interface HangmanSaved {
  category: string
  word: string
  guessedLetters: string[]
  gameStatus: GameStatus
  streak: number
}

export default function Hangman() {
  const { load, save, clear } = useGameState<HangmanSaved>('hangman')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('hangman'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('hangman')

  const [category, setCategory] = useState(saved?.category ?? CATEGORIES[0])
  const [word, setWord] = useState(() => saved?.word ?? selectWord(CATEGORIES[0]))
  const [guessedLetters, setGuessedLetters] = useState<Set<string>>(
    () => saved?.guessedLetters ? new Set(saved.guessedLetters) : new Set()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [streak, setStreak] = useState(saved?.streak ?? 0)

  // Persist state
  useEffect(() => {
    save({ category, word, guessedLetters: Array.from(guessedLetters), gameStatus, streak })
  }, [category, word, guessedLetters, gameStatus, streak, save])

  const wrongGuessCount = getWrongGuesses(word, guessedLetters)
  const correctLetters = new Set(
    [...guessedLetters].filter(l => word.includes(l))
  )

  const handleGuess = useCallback((letter: string) => {
    if (gameStatus !== 'playing' || guessedLetters.has(letter)) return
    music.init()
    sfx.init()
    music.start()
    const upper = letter.toUpperCase()
    if (!/^[A-Z]$/.test(upper)) return

    const newGuessed = new Set(guessedLetters)
    newGuessed.add(upper)
    setGuessedLetters(newGuessed)

    const isCorrect = processGuess(word, upper)

    if (isGameWon(word, newGuessed)) {
      sfx.play('win')
      setGameStatus('won')
      setStreak(s => s + 1)
    } else if (!isCorrect && isGameLost(getWrongGuesses(word, newGuessed))) {
      sfx.play('lose')
      setGameStatus('lost')
      setStreak(0)
    } else if (isCorrect) {
      sfx.play('correct')
    } else {
      sfx.play('wrong')
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
    music.start()
    clear()
  }, [category, music, clear])

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
      {/* Streak & Music */}
      <div className="flex items-center gap-2">
        {streak > 0 && (
          <p className="text-xs text-yellow-400">Streak: {streak}</p>
        )}
        <MusicToggle music={music} sfx={sfx} />
      </div>
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
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
