/**
 * Wordle game — guess the 5-letter word in 6 tries.
 *
 * Features: daily word mode, random mode, hard mode toggle,
 * keyboard coloring, share button, physical keyboard support,
 * multiplayer race mode.
 */

import { useState, useCallback, useEffect, useMemo, useRef} from 'react'
import { HelpCircle, Share2, X } from 'lucide-react'
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
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

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

function WordleHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Wordle</h2>
        <Sec title="Goal"><p>Guess the hidden 5-letter word in <B>6 tries</B> or fewer.</p></Sec>
        <Sec title="How to Play"><ul className="space-y-1">
          <Li>Type a valid 5-letter word and press <B>Enter</B> to submit.</Li>
          <Li>After each guess, tiles change color to show how close you are.</Li>
        </ul></Sec>
        <Sec title="Color Clues"><ul className="space-y-1">
          <Li><span className="inline-block w-4 h-4 rounded bg-green-600 align-middle mr-1"></span> <B>Green</B> — Correct letter in the correct position.</Li>
          <Li><span className="inline-block w-4 h-4 rounded bg-yellow-600 align-middle mr-1"></span> <B>Yellow</B> — Correct letter but in the wrong position.</Li>
          <Li><span className="inline-block w-4 h-4 rounded bg-slate-700 align-middle mr-1"></span> <B>Gray</B> — Letter is not in the word.</Li>
        </ul></Sec>
        <Sec title="Modes"><ul className="space-y-1">
          <Li><B>Daily</B> — Everyone gets the same word each day.</Li>
          <Li><B>Random</B> — A new random word each game.</Li>
          <Li><B>Hard Mode</B> — Revealed hints must be used in subsequent guesses.</Li>
        </ul></Sec>
        <Sec title="Strategy Tips"><ul className="space-y-1">
          <Li>Start with words that have common letters: E, A, R, S, T, O.</Li>
          <Li>Use your second guess to test new letters, not repeat confirmed ones.</Li>
          <Li>Pay attention to the keyboard colors — they track all your guesses.</Li>
        </ul></Sec>
      </div>
    </div>
  )
}

function WordleSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw', score?: number) => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
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
  const [showHelp, setShowHelp] = useState(false)

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
        onGameEnd?.('win', newGuesses.length)
      } else if (newGuesses.length >= MAX_GUESSES) {
        sfx.play('wrong')
        setGameStatus('lost')
        onGameEnd?.('loss', MAX_GUESSES)
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
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play"><HelpCircle className="w-4 h-4 text-blue-400" /></button>
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

        {gameStatus !== 'playing' && gameStatus !== 'idle' && !isMultiplayer && (
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
      {showHelp && <WordleHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (fewest guesses wins) ──────────────────────────────

function WordleRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, localScore, opponentLevelUp, broadcastState, reportFinish, leaveRoom } = useRaceMode(roomId, 'best_score')
  const finishedRef = useRef(false)

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw', score?: number) => {
    if (finishedRef.current) return
    finishedRef.current = true
    // Invert guess count so fewer guesses = higher score (7 - guessCount)
    const invertedScore = score != null ? (MAX_GUESSES + 1) - score : 0
    reportFinish(result === 'loss' ? 'loss' : 'win', invertedScore)
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
      <WordleSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function Wordle() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'wordle',
        gameName: 'Wordle',
        modes: ['best_score'],
        hasDifficulty: false,
        modeDescriptions: { best_score: 'Fewest guesses wins' },
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <WordleSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig, onLeave) =>
        <WordleRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty as string | undefined} onLeave={onLeave} />
      }
    />
  )
}
