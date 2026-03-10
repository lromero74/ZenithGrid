/**
 * Hangman game — guess the word one letter at a time.
 *
 * Features: categorized word lists, SVG hangman, QWERTY keyboard, streak tracking.
 */

import { useState, useCallback, useEffect, useMemo, useRef} from 'react'
import { HelpCircle, X } from 'lucide-react'
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
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

// ── Help modal ───────────────────────────────────────────────────────

function HangmanHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Hangman</h2>

        {/* Goal */}
        <Sec title="Goal">
          Guess the hidden word one letter at a time before the hangman is
          fully drawn. You have <B>{MAX_WRONG_GUESSES} wrong guesses</B> before
          the game is over.
        </Sec>

        {/* How It Works */}
        <Sec title="How It Works">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li>A secret word is chosen from the selected <B>category</B>.</li>
            <li>The word is displayed as <B>underscores</B> &mdash; one for each letter.</li>
            <li>Guess letters using the <B>on-screen keyboard</B> or your
              <B> physical keyboard</B> (A-Z).</li>
            <li>Correct guesses <B>reveal</B> all instances of that letter in
              the word.</li>
            <li>Wrong guesses add a body part to the <B>hangman drawing</B>.</li>
            <li>Reveal the entire word before running out of guesses to <B>win</B>!</li>
          </ol>
        </Sec>

        {/* The Drawing */}
        <Sec title="The Hangman Drawing">
          Each wrong guess draws one body part in this order:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>1st wrong</B> &mdash; Head</Li>
            <Li><B>2nd wrong</B> &mdash; Body</Li>
            <Li><B>3rd wrong</B> &mdash; Left arm</Li>
            <Li><B>4th wrong</B> &mdash; Right arm</Li>
            <Li><B>5th wrong</B> &mdash; Left leg</Li>
            <Li><B>6th wrong</B> &mdash; Right leg (game over!)</Li>
          </ul>
        </Sec>

        {/* Keyboard Colors */}
        <Sec title="Keyboard Colors">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Gray</B> &mdash; Letter has not been guessed yet.</Li>
            <Li><B>Green</B> &mdash; Correct guess &mdash; the letter is in the word.</Li>
            <Li><B>Red</B> &mdash; Wrong guess &mdash; the letter is not in the word.</Li>
          </ul>
        </Sec>

        {/* Categories */}
        <Sec title="Word Categories">
          Choose a category to change the theme of the words. Selecting a new
          category starts a <B>new game</B> with a random word from that
          category. Available categories:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Crypto</B> &mdash; Coins, protocols, and blockchain terms.</Li>
            <Li><B>Trading</B> &mdash; Market, finance, and investing vocabulary.</Li>
            <Li><B>Animals</B> &mdash; Creatures from around the world.</Li>
            <Li><B>Countries</B> &mdash; Nations across the globe.</Li>
            <Li><B>Movies</B> &mdash; Popular film titles.</Li>
            <Li><B>Food</B> &mdash; Dishes, ingredients, and treats.</Li>
            <Li><B>Science</B> &mdash; Scientific terms and concepts.</Li>
          </ul>
        </Sec>

        {/* Streak */}
        <Sec title="Win Streak">
          Consecutive wins build a <B>streak counter</B> displayed below the
          category buttons. A single loss resets the streak to zero. Changing
          categories does <B>not</B> reset your streak &mdash; only losing does.
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Start with common letters</B> &mdash; E, T, A, O, I, N, S,
              and R are the most frequent letters in English.</Li>
            <Li><B>Look at word length</B> &mdash; short words (3-4 letters) have
              fewer possibilities; longer words give more clues as letters are
              revealed.</Li>
            <Li><B>Think about the category</B> &mdash; knowing the theme narrows
              your guesses significantly.</Li>
            <Li><B>Watch the pattern</B> &mdash; as letters are revealed, the
              positions and gaps often suggest the word.</Li>
            <Li><B>Avoid uncommon letters early</B> &mdash; save Q, X, Z, and J
              for when you have a strong hunch.</Li>
          </ul>
        </Sec>

        {/* Saving */}
        <Sec title="Game State">
          Your current game &mdash; including the word, guessed letters, and
          streak &mdash; is <B>saved automatically</B>. You can close the browser
          and come back to continue where you left off.
        </Sec>

        <div className="mt-4 pt-3 border-t border-slate-700 text-center">
          <button onClick={onClose} className="px-6 py-2 text-sm rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors">
            Got it!
          </button>
        </div>
      </div>
    </div>
  )
}

function Sec({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="text-sm font-semibold text-slate-200 mb-1">{title}</h3>
      <div className="text-xs leading-relaxed text-slate-400">{children}</div>
    </div>
  )
}

function Li({ children }: { children: React.ReactNode }) {
  return <li className="flex gap-1.5 text-xs"><span className="text-slate-600 mt-0.5">&bull;</span><span>{children}</span></li>
}

function B({ children }: { children: React.ReactNode }) {
  return <span className="text-white font-medium">{children}</span>
}

// ── Component ────────────────────────────────────────────────────────

interface HangmanSaved {
  category: string
  word: string
  guessedLetters: string[]
  gameStatus: GameStatus
  streak: number
}

function HangmanSinglePlayer({ onGameEnd, onStateChange: _onStateChange }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void } = {}) {
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
  const [showHelp, setShowHelp] = useState(false)

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
      onGameEnd?.('win')
    } else if (!isCorrect && isGameLost(getWrongGuesses(word, newGuessed))) {
      sfx.play('lose')
      setGameStatus('lost')
      setStreak(0)
      onGameEnd?.('loss')
    } else if (isCorrect) {
      sfx.play('correct')
    } else {
      sfx.play('wrong')
    }
  }, [gameStatus, guessedLetters, word, onGameEnd])

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
        <button
          onClick={() => setShowHelp(true)}
          className="p-1.5 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-white"
          title="How to Play"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
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
      {showHelp && <HangmanHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-solve against opponent) ──────────────────

function HangmanRaceWrapper({ roomId, difficulty: _difficulty }: { roomId: string; difficulty?: string }) {
  const { opponentStatus, raceResult, opponentLevelUp, broadcastState, reportFinish } = useRaceMode(roomId, 'first_to_win')
  const finishedRef = useRef(false)

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw') => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish(result === 'draw' ? 'loss' : result)
  }, [reportFinish])

  return (
    <div className="relative">
      <RaceOverlay
        raceResult={raceResult}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
      />
      <HangmanSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} />
    </div>
  )
}

export default function Hangman() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'hangman',
        gameName: 'Hangman',
        modes: ['race'],
        maxPlayers: 2,
        hasDifficulty: true,
        raceDescription: 'First to solve the word wins',
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <HangmanSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig) =>
        <HangmanRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} />
      }
    />
  )
}
