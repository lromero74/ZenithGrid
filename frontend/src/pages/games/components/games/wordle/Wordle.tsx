/**
 * Wordle game — guess the 5-letter word in 6 tries.
 *
 * Features: daily word mode, random mode, hard mode toggle,
 * keyboard coloring, share button, physical keyboard support.
 */

import { useState, useCallback, useEffect, useMemo, useRef} from 'react'
import { Share2 } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameState } from '../../../hooks/useGameState'
import {
  evaluateGuess, isValidWord, getDailyWord, updateKeyboardState, checkHardMode,
  type LetterResult, type KeyboardState,
} from './wordleEngine'
import { WordleBoard } from './WordleBoard'
import { WordleKeyboard } from './WordleKeyboard'
import { ANSWER_LIST } from './answerList'
import { VALID_GUESSES } from './validGuesses'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { useGameSFX } from '../../../audio/useGameSFX'

const MAX_GUESSES = 6

function getRandomWord(): string {
  return ANSWER_LIST[Math.floor(Math.random() * ANSWER_LIST.length)]
}

interface WordleSaved {
  mode: 'daily' | 'random'
  answer: string
  guesses: string[]
  evaluations: LetterResult[][]
  currentGuess: string
  gameStatus: GameStatus
  keyboardState: KeyboardState
  hardMode: boolean
}

export default function Wordle() {
  const { load, save, clear } = useGameState<WordleSaved>('wordle')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('wordle'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('wordle')

  const [mode, setMode] = useState<'daily' | 'random'>(saved?.mode ?? 'daily')
  const [answer, setAnswer] = useState(() =>
    saved?.answer ?? getDailyWord(ANSWER_LIST, new Date())
  )
  const [guesses, setGuesses] = useState<string[]>(saved?.guesses ?? [])
  const [evaluations, setEvaluations] = useState<LetterResult[][]>(saved?.evaluations ?? [])
  const [currentGuess, setCurrentGuess] = useState(saved?.currentGuess ?? '')
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [keyboardState, setKeyboardState] = useState<KeyboardState>(saved?.keyboardState ?? {})
  const [hardMode, setHardMode] = useState(saved?.hardMode ?? false)
  const [shake, setShake] = useState(false)
  const [toast, setToast] = useState('')

  // Persist state
  useEffect(() => {
    save({ mode, answer, guesses, evaluations, currentGuess, gameStatus, keyboardState, hardMode })
  }, [mode, answer, guesses, evaluations, currentGuess, gameStatus, keyboardState, hardMode, save])

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 2000)
  }, [])

  const triggerShake = useCallback(() => {
    setShake(true)
    setTimeout(() => setShake(false), 500)
  }, [])

  const handleKey = useCallback((key: string) => {
    if (gameStatus !== 'playing') return

    music.init()
    sfx.init()
    music.start()

    if (key === 'BACK') {
      setCurrentGuess(g => g.slice(0, -1))
      return
    }

    if (key === 'ENTER') {
      if (currentGuess.length !== 5) {
        showToast('Not enough letters')
        triggerShake()
        return
      }

      if (!isValidWord(currentGuess, VALID_GUESSES)) {
        sfx.play('invalid')
        showToast('Not a valid word')
        triggerShake()
        return
      }

      if (hardMode) {
        const prevGuesses = guesses.map((g, i) => ({
          guess: g,
          evaluation: evaluations[i],
        }))
        const error = checkHardMode(currentGuess, prevGuesses)
        if (error) {
          showToast(error)
          triggerShake()
          return
        }
      }

      const evaluation = evaluateGuess(currentGuess, answer)
      const newGuesses = [...guesses, currentGuess]
      const newEvals = [...evaluations, evaluation]
      setGuesses(newGuesses)
      setEvaluations(newEvals)
      setKeyboardState(s => updateKeyboardState(s, currentGuess, evaluation))
      setCurrentGuess('')

      if (evaluation.every(r => r === 'correct')) {
        sfx.play('win')
        setGameStatus('won')
      } else if (newGuesses.length >= MAX_GUESSES) {
        sfx.play('wrong')
        setGameStatus('lost')
      } else {
        sfx.play('wrong')
      }
      return
    }

    // Letter key
    if (currentGuess.length < 5 && /^[A-Z]$/.test(key)) {
      sfx.play('key')
      setCurrentGuess(g => g + key)
    }
  }, [gameStatus, currentGuess, guesses, evaluations, answer, hardMode, showToast, triggerShake])

  // Physical keyboard
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key === 'Enter') handleKey('ENTER')
      else if (e.key === 'Backspace') handleKey('BACK')
      else if (/^[a-zA-Z]$/.test(e.key)) handleKey(e.key.toUpperCase())
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [handleKey])

  const handleNewGame = useCallback(() => {
    const newAnswer = mode === 'daily'
      ? getDailyWord(ANSWER_LIST, new Date())
      : getRandomWord()
    setAnswer(newAnswer)
    setGuesses([])
    setEvaluations([])
    setCurrentGuess('')
    setGameStatus('playing')
    setKeyboardState({})
    music.start()
    clear()
  }, [mode, music])

  const handleModeChange = useCallback((newMode: 'daily' | 'random') => {
    setMode(newMode)
    const newAnswer = newMode === 'daily'
      ? getDailyWord(ANSWER_LIST, new Date())
      : getRandomWord()
    setAnswer(newAnswer)
    setGuesses([])
    setEvaluations([])
    setCurrentGuess('')
    setGameStatus('playing')
    setKeyboardState({})
  }, [])

  const handleShare = useCallback(() => {
    const grid = evaluations.map(row =>
      row.map(r => r === 'correct' ? '🟩' : r === 'present' ? '🟨' : '⬛').join('')
    ).join('\n')
    const text = `Wordle ${guesses.length}/${MAX_GUESSES}\n\n${grid}`
    navigator.clipboard.writeText(text)
    showToast('Copied to clipboard!')
  }, [evaluations, guesses, showToast])

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex space-x-2">
        <button
          onClick={() => handleModeChange('daily')}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            mode === 'daily' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
          }`}
        >
          Daily
        </button>
        <button
          onClick={() => handleModeChange('random')}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            mode === 'random' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
          }`}
        >
          Random
        </button>
      </div>
      <div className="flex items-center space-x-3">
        <MusicToggle music={music} sfx={sfx} />
        <label className="flex items-center space-x-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={hardMode}
            onChange={(e) => {
              if (guesses.length > 0) {
                showToast("Can't change mid-game")
                return
              }
              setHardMode(e.target.checked)
            }}
            className="w-3.5 h-3.5 rounded border-slate-500"
          />
          <span className="text-xs text-slate-400">Hard</span>
        </label>
        {gameStatus !== 'playing' && (
          <button
            onClick={handleShare}
            className="p-1 hover:bg-slate-700 rounded transition-colors"
            title="Share"
          >
            <Share2 className="w-4 h-4 text-slate-400" />
          </button>
        )}
      </div>
    </div>
  )

  return (
    <GameLayout title="Wordle" controls={controls}>
      <div className="relative flex flex-col items-center space-y-4">
        {/* Toast */}
        {toast && (
          <div className="absolute top-0 z-20 bg-slate-700 text-white text-sm px-4 py-2 rounded-lg shadow-lg">
            {toast}
          </div>
        )}

        <WordleBoard
          guesses={guesses}
          evaluations={evaluations}
          currentGuess={currentGuess}
          currentRow={guesses.length}
          maxGuesses={MAX_GUESSES}
          shake={shake}
        />

        <WordleKeyboard
          keyboardState={keyboardState}
          onKey={handleKey}
          disabled={gameStatus !== 'playing'}
        />

        {gameStatus !== 'playing' && gameStatus !== 'idle' && (
          <GameOverModal
            status={gameStatus}
            message={
              gameStatus === 'won'
                ? `Solved in ${guesses.length} ${guesses.length === 1 ? 'guess' : 'guesses'}!`
                : `The word was: ${answer}`
            }
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
