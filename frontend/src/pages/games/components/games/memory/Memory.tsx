/**
 * Memory card matching game — flip cards to find matching pairs.
 *
 * Features: three difficulty levels (4x3, 4x4, 6x4 grids), flip animations,
 * move counter, timer, best score tracking, state persistence.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
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

interface MemoryState {
  cards: Card[]
  gameStatus: GameStatus
  difficulty: Difficulty
  moves: number
  totalFlips: number
  elapsed: number
  bestMoves: Record<string, number>
}

const GRID_COLS: Record<GridSize, number> = { easy: 4, medium: 4, hard: 6 }

export default function Memory() {
  const { load, save, clear } = useGameState<MemoryState>('memory')
  const saved = useRef(load()).current

  const difficulty = saved?.difficulty ?? 'easy'
  const gridSize = difficulty as GridSize
  const { pairs } = getGridDimensions(gridSize)

  const [cards, setCards] = useState<Card[]>(() => saved?.cards ?? createDeck(pairs))
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'idle')
  const [currentDifficulty, setCurrentDifficulty] = useState<Difficulty>(difficulty)
  const [totalFlips, setTotalFlips] = useState(saved?.totalFlips ?? 0)
  const [elapsed, setElapsed] = useState(saved?.elapsed ?? 0)
  const [bestMoves, setBestMoves] = useState<Record<string, number>>(saved?.bestMoves ?? {})

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

    const card = cards[index]
    if (card.matched || card.flipped) return

    // Start game on first flip
    const newStatus = gameStatus === 'idle' ? 'playing' : gameStatus
    if (newStatus !== gameStatus) setGameStatus(newStatus)

    // Flip the card
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

      if (checkMatch(card1, card2)) {
        // Mark as matched
        const matched = newCards.map((c, i) =>
          i === first || i === second ? { ...c, matched: true } : c
        )
        setCards(matched)
        flippedIndices.current = []
        lockRef.current = false

        // Check win
        if (checkGameComplete(matched)) {
          setGameStatus('won')
          const finalMoves = countMoves(totalFlips + 1)
          setBestMoves(prev => {
            const key = currentDifficulty
            const current = prev[key]
            if (current === undefined || finalMoves < current) {
              return { ...prev, [key]: finalMoves }
            }
            return prev
          })
        }
      } else {
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
  }, [cards, gameStatus, totalFlips, currentDifficulty])

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
          />
        )}
      </div>
    </GameLayout>
  )
}
