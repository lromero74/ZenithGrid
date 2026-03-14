/**
 * Memory card matching game — flip cards to find matching pairs.
 *
 * Features: three difficulty levels (4x3, 4x4, 6x4 grids), flip animations,
 * move counter, timer, best score tracking, state persistence.
 */

import { useState, useCallback, useEffect, useRef, useMemo} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import {
  createDeck, flipCard, checkMatch, checkGameComplete,
  getGridDimensions, countMoves,
  type Card, type GridSize,
} from './memoryEngine'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus, Difficulty } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import { MemoryMultiplayer } from './MemoryMultiplayer'

interface MemoryState {
  cards: Card[]
  gameStatus: GameStatus
  difficulty: Difficulty
  moves: number
  totalFlips: number
  elapsed: number
  bestMoves: Record<string, number>
}

// ── Help modal ───────────────────────────────────────────────────────

function MemoryHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Memory</h2>

        {/* Goal */}
        <Sec title="Goal">
          Find all matching pairs of cards by flipping them two at a time.
          Complete the board in as few <B>moves</B> as possible.
        </Sec>

        {/* How It Works */}
        <Sec title="How It Works">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li>All cards start <B>face-down</B>, showing a &ldquo;?&rdquo; symbol.</li>
            <li>Click a card to <B>flip</B> it and reveal the emoji underneath.</li>
            <li>Flip a <B>second card</B> to check for a match.</li>
            <li>If the two cards have the <B>same emoji</B>, they stay face-up and
              are marked as matched.</li>
            <li>If they <B>don&rsquo;t match</B>, both cards flip back face-down after
              a brief delay.</li>
            <li>The game is <B>won</B> when every pair has been found.</li>
          </ol>
        </Sec>

        {/* Moves & Timer */}
        <Sec title="Moves & Timer">
          <ul className="space-y-1 text-slate-300">
            <Li>Every <B>two flips</B> count as one move.</Li>
            <Li>A <B>timer</B> starts on your first flip and stops when you win.</Li>
            <Li>Your <B>best score</B> (fewest moves) is tracked per difficulty level.</Li>
          </ul>
        </Sec>

        {/* Difficulty Levels */}
        <Sec title="Difficulty Levels">
          Choose a grid size before starting:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Easy</B> &mdash; 3 &times; 4 grid (6 pairs, 12 cards).</Li>
            <Li><B>Medium</B> &mdash; 4 &times; 4 grid (8 pairs, 16 cards).</Li>
            <Li><B>Hard</B> &mdash; 4 &times; 6 grid (12 pairs, 24 cards).</Li>
          </ul>
          Changing difficulty starts a <B>new game</B>.
        </Sec>

        {/* Card Appearance */}
        <Sec title="Card Appearance">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Face-down</B> &mdash; Dark card with a &ldquo;?&rdquo; symbol.</Li>
            <Li><B>Flipped</B> &mdash; White card showing the emoji.</Li>
            <Li><B>Matched</B> &mdash; Green-bordered card with a slightly faded emoji.</Li>
          </ul>
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Remember positions</B> &mdash; pay attention to every card you flip,
              even when it doesn&rsquo;t match.</Li>
            <Li><B>Work systematically</B> &mdash; scan a row or column at a time
              rather than flipping randomly.</Li>
            <Li><B>Use mismatches</B> &mdash; a failed flip reveals useful information
              for future turns.</Li>
          </ul>
        </Sec>

        {/* Game State */}
        <Sec title="Game State">
          Your current game &mdash; including card positions, moves, timer, and
          best scores &mdash; is <B>saved automatically</B>. You can close the
          browser and come back to continue where you left off.
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

const GRID_COLS: Record<GridSize, number> = { easy: 4, medium: 4, hard: 6 }

function MemorySinglePlayer({ onGameEnd, onMove, onStateChange: _onStateChange }: {
  onGameEnd?: (result: 'win' | 'loss' | 'draw', moveCount?: number) => void
  onMove?: (moveCount: number) => void
  onStateChange?: (state: object) => void
} = {}) {
  const { load, save, clear } = useGameState<MemoryState>('memory')
  const saved = useRef(load()).current

  const difficulty = saved?.difficulty ?? 'easy'
  const gridSize = difficulty as GridSize
  const { pairs } = getGridDimensions(gridSize)

  // Music
  const song = useMemo(() => getSongForGame('memory'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('memory')

  const [cards, setCards] = useState<Card[]>(() => saved?.cards ?? createDeck(pairs))
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'idle')
  const [currentDifficulty, setCurrentDifficulty] = useState<Difficulty>(difficulty)
  const [totalFlips, setTotalFlips] = useState(saved?.totalFlips ?? 0)
  const [elapsed, setElapsed] = useState(saved?.elapsed ?? 0)
  const [bestMoves, setBestMoves] = useState<Record<string, number>>(saved?.bestMoves ?? {})
  const [showHelp, setShowHelp] = useState(false)

  const flippedIndices = useRef<number[]>([])
  const lockRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const moves = countMoves(totalFlips)

  // Persist state on changes
  useEffect(() => {
    save({ cards, gameStatus, difficulty: currentDifficulty, moves, totalFlips, elapsed, bestMoves })
  }, [cards, gameStatus, currentDifficulty, moves, totalFlips, elapsed, bestMoves, save])

  // Timer: runs while playing
  useEffect(() => {
    if (gameStatus === 'playing') {
      timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [gameStatus])

  const handleCardClick = useCallback((index: number) => {
    if (lockRef.current) return
    if (gameStatus === 'won') return

    music.init()
    sfx.init()
    music.start()

    const card = cards[index]
    if (card.matched || card.flipped) return

    // Start game on first flip
    const newStatus = gameStatus === 'idle' ? 'playing' : gameStatus
    if (newStatus !== gameStatus) setGameStatus(newStatus)

    // Flip the card
    sfx.play('flip')
    const newCards = flipCard(cards, index)
    setCards(newCards)
    setTotalFlips(f => f + 1)
    flippedIndices.current.push(index)

    // After 2 cards flipped, check match
    if (flippedIndices.current.length === 2) {
      lockRef.current = true
      const [first, second] = flippedIndices.current
      const card1 = newCards[first]
      const card2 = newCards[second]
      const currentMoveCount = countMoves(totalFlips + 1)
      onMove?.(currentMoveCount)

      if (checkMatch(card1, card2)) {
        sfx.play('match')
        // Mark as matched
        const matched = newCards.map((c, i) =>
          i === first || i === second ? { ...c, matched: true } : c
        )
        setCards(matched)
        flippedIndices.current = []
        lockRef.current = false

        // Check win
        if (checkGameComplete(matched)) {
          sfx.play('win')
          setGameStatus('won')
          const finalMoves = currentMoveCount
          setBestMoves(prev => {
            const key = currentDifficulty
            const current = prev[key]
            if (current === undefined || finalMoves < current) {
              return { ...prev, [key]: finalMoves }
            }
            return prev
          })
          onGameEnd?.('win', finalMoves)
        }
      } else {
        sfx.play('mismatch')
        // No match — flip both back after delay
        setTimeout(() => {
          setCards(prev => prev.map((c, i) =>
            i === first || i === second ? { ...c, flipped: false } : c
          ))
          flippedIndices.current = []
          lockRef.current = false
        }, 800)
      }
    }
  }, [cards, gameStatus, totalFlips, currentDifficulty, onGameEnd, onMove])

  const startNewGame = useCallback((diff?: Difficulty) => {
    const d = diff ?? currentDifficulty
    const size = d as GridSize
    const { pairs: p } = getGridDimensions(size)
    setCards(createDeck(p))
    setGameStatus('idle')
    setCurrentDifficulty(d)
    setTotalFlips(0)
    setElapsed(0)
    flippedIndices.current = []
    lockRef.current = false
    clear()
  }, [currentDifficulty, clear])

  const timerStr = `${Math.floor(elapsed / 60)}:${(elapsed % 60).toString().padStart(2, '0')}`
  const cols = GRID_COLS[currentDifficulty as GridSize] ?? 4
  const best = bestMoves[currentDifficulty]

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <DifficultySelector
          value={currentDifficulty}
          onChange={(d) => startNewGame(d)}
          options={['easy', 'medium', 'hard']}
        />
        <button
          onClick={() => startNewGame()}
          className="px-3 py-1 rounded text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          New Game
        </button>
      </div>
      <div className="flex items-center space-x-3 text-xs">
        <span className="text-slate-400">Moves: <span className="text-white font-mono">{moves}</span></span>
        {best !== undefined && (
          <span className="text-yellow-400">Best: {best}</span>
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
    <GameLayout title="Memory" timer={timerStr} controls={controls}>
      <div className="relative">
        {/* Card grid */}
        <div
          className="grid gap-2"
          style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}
        >
          {cards.map((card, index) => {
            const isRevealed = card.flipped || card.matched
            return (
              <div
                key={card.id}
                className="cursor-pointer select-none"
                style={{ perspective: '600px' }}
                onClick={() => handleCardClick(index)}
              >
                <div
                  className="relative w-16 h-20 sm:w-20 sm:h-24"
                  style={{
                    transformStyle: 'preserve-3d',
                    transform: isRevealed ? 'rotateY(180deg)' : 'none',
                    transition: 'transform 0.4s',
                  }}
                >
                  {/* Back face (hidden side — shows ?) */}
                  <div
                    className={`absolute inset-0 rounded-lg flex items-center justify-center border-2
                      bg-slate-700 border-slate-600 hover:border-slate-500 transition-colors`}
                    style={{ backfaceVisibility: 'hidden' }}
                  >
                    <span className="text-slate-500 text-xl">?</span>
                  </div>
                  {/* Front face (revealed side — shows emoji) */}
                  <div
                    className={`absolute inset-0 rounded-lg flex items-center justify-center border-2
                      ${card.matched
                        ? 'bg-emerald-900/30 border-emerald-500'
                        : 'bg-white border-slate-300'
                      }`}
                    style={{
                      backfaceVisibility: 'hidden',
                      transform: 'rotateY(180deg)',
                    }}
                  >
                    <span className={`text-3xl ${card.matched ? 'opacity-70' : ''}`}>
                      {card.symbol}
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Game over modal */}
        {gameStatus === 'won' && (
          <GameOverModal
            status="won"
            score={moves}
            bestScore={best}
            message={`Completed in ${moves} moves (${timerStr})`}
            onPlayAgain={() => startNewGame()}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <MemoryHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper ──────────────────────────────────────────────────

function MemoryRaceWrapper({ roomId, raceType = 'best_score', onLeave }: { roomId: string; difficulty?: string; raceType?: 'first_to_win' | 'best_score'; onLeave?: () => void }) {
  const { opponentStatus, raceResult, localScore, opponentLevelUp, broadcastState, reportScore, reportFinish, leaveRoom } =
    useRaceMode(roomId, raceType)
  const finishedRef = useRef(false)

  const handleMove = useCallback((moveCount: number) => {
    reportScore(moveCount)
  }, [reportScore])

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw', moveCount?: number) => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish(result === 'draw' ? 'loss' : result, moveCount)
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
      <MemorySinglePlayer onGameEnd={handleGameEnd} onMove={handleMove} onStateChange={broadcastState} />
    </div>
  )
}

export default function Memory() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'memory',
        gameName: 'Memory',
        modes: ['vs', 'first_to_win', 'best_score'],
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: {
          vs: 'Take turns finding pairs',
          first_to_win: 'First to finish wins',
          best_score: 'Fewest moves wins',
        },
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <MemorySinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <MemoryMultiplayer
            roomId={roomId}
            players={players}
            playerNames={playerNames}
            difficulty={roomConfig.difficulty as string}
            onLeave={onLeave}
          />
        ) : (
          <MemoryRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} raceType={(roomConfig.race_type as 'first_to_win' | 'best_score') || 'best_score'} onLeave={onLeave} />
        )
      }
    />
  )
}
