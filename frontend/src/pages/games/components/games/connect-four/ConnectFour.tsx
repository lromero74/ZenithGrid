/**
 * Connect Four game — drop discs to get four in a row.
 *
 * Features: AI opponent with difficulty levels, column hover preview,
 * win highlighting, score tracking.
 */

import { useState, useCallback, useEffect, useRef, useMemo} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import { useGameState } from '../../../hooks/useGameState'
import {
  createBoard, dropDisc, checkWinner, getValidColumns,
  isBoardFull, getAIMove,
  type Board, type Player, type WinResult,
} from './connectFourEngine'
import { ConnectFourBoard } from './ConnectFourBoard'
import type { GameStatus, Difficulty } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'

// ── Help modal ───────────────────────────────────────────────────────

function ConnectFourHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Connect Four</h2>

        {/* Goal */}
        <Section title="Goal">
          Be the first player to connect <B>four of your discs</B> in a row &mdash;
          horizontally, vertically, or diagonally &mdash; before the AI does.
        </Section>

        {/* Setup */}
        <Section title="Setup">
          The game is played on a <B>7-column by 6-row</B> vertical grid.
          You play as <B className="text-red-400">Red</B> and the AI plays as{' '}
          <B className="text-yellow-400">Yellow</B>. Red always goes first.
        </Section>

        {/* How to play */}
        <Section title="How to Play">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Click a column</B> (or hover to preview) to drop your disc into that column.</Li>
            <Li>Discs fall to the <B>lowest available row</B> in the chosen column, just like gravity.</Li>
            <Li>You and the AI take <B>alternating turns</B>. After your move, the AI responds automatically.</Li>
            <Li>If a column is full, you cannot drop a disc there.</Li>
          </ul>
        </Section>

        {/* Winning */}
        <Section title="Winning">
          Connect four discs in an unbroken line to win. Lines can be:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Horizontal</B> &mdash; four in a row across a single row.</Li>
            <Li><B>Vertical</B> &mdash; four stacked in the same column.</Li>
            <Li><B>Diagonal</B> &mdash; four in a row on either diagonal direction.</Li>
          </ul>
          <p className="mt-1.5 text-slate-400">
            Winning cells are <B>highlighted</B> when a line is completed.
          </p>
        </Section>

        {/* Draw */}
        <Section title="Draw">
          If all 42 cells are filled and neither player has four in a row,
          the game ends in a <B>draw</B>.
        </Section>

        {/* AI opponent */}
        <Section title="AI Opponent">
          The AI uses <B>minimax with alpha-beta pruning</B> to choose its moves.
          Select a difficulty before starting:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Easy</B> &mdash; the AI looks only 2 moves ahead. Good for learning.</Li>
            <Li><B>Medium</B> &mdash; the AI looks 4 moves ahead. A solid challenge.</Li>
            <Li><B>Hard</B> &mdash; the AI looks 6 moves ahead. Very difficult to beat.</Li>
          </ul>
        </Section>

        {/* Controls */}
        <Section title="Controls">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Click</B> a column to drop your disc.</Li>
            <Li><B>Hover</B> over the board to see which column you are targeting.</Li>
            <Li><B>Difficulty selector</B> (top-left) changes the AI strength and starts a new game.</Li>
            <Li><B>New Game</B> resets the board. Scores are preserved across games.</Li>
          </ul>
        </Section>

        {/* Strategy tips */}
        <Section title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Control the center.</B> The middle column participates in the most possible winning lines.</Li>
            <Li><B>Build threats in two directions</B> so the AI cannot block both at once.</Li>
            <Li><B>Look for forced wins</B> &mdash; create a position where you have two ways to complete four in a row.</Li>
            <Li><B>Watch for the AI&apos;s setups.</B> Block three-in-a-row threats before they become four.</Li>
            <Li><B>Plan vertically.</B> Stacking discs can create diagonal opportunities the opponent may miss.</Li>
            <Li><B>Think ahead.</B> Consider where your disc will land and what moves it enables for both players.</Li>
          </ul>
        </Section>

        <div className="mt-4 pt-3 border-t border-slate-700 text-center">
          <button onClick={onClose} className="px-6 py-2 text-sm rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors">
            Got it!
          </button>
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
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

function B({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={`font-medium ${className ?? 'text-white'}`}>{children}</span>
}

// ── Constants ─────────────────────────────────────────────────────────

const DIFFICULTY_DEPTH: Record<string, number> = {
  easy: 2, medium: 4, hard: 6,
}

interface ConnectFourSaved {
  board: Board
  currentPlayer: Player
  gameStatus: GameStatus
  difficulty: Difficulty
  scores: { red: number; yellow: number; draw: number }
}

export default function ConnectFour() {
  const { load, save, clear } = useGameState<ConnectFourSaved>('connect-four')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('connect-four'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('connect-four')

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

  const [board, setBoard] = useState<Board>(() => saved?.board ?? createBoard())
  const [currentPlayer, setCurrentPlayer] = useState<Player>(saved?.currentPlayer ?? 'red')
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [winResult, setWinResult] = useState<WinResult | null>(null)
  const [difficulty, setDifficulty] = useState<Difficulty>(saved?.difficulty ?? 'medium')
  const [scores, setScores] = useState(saved?.scores ?? { red: 0, yellow: 0, draw: 0 })
  const [hoverCol, setHoverCol] = useState<number | null>(null)
  const [droppingDisc, setDroppingDisc] = useState<{ row: number; col: number; player: 'red' | 'yellow' } | null>(null)
  const [naturalDrop, setNaturalDrop] = useState(true)
  const aiThinking = useRef(false)

  // Persist state
  useEffect(() => {
    save({ board, currentPlayer, gameStatus, difficulty, scores })
  }, [board, currentPlayer, gameStatus, difficulty, scores, save])

  const handleColumnClick = useCallback((col: number) => {
    if (gameStatus !== 'playing' || currentPlayer !== 'red' || aiThinking.current) return
    if (!getValidColumns(board).includes(col)) return

    music.init()
    sfx.init()
    music.start()

    const { board: newBoard, row } = dropDisc(board, col, 'red')
    if (row === -1) return

    sfx.play('drop')
    if (naturalDrop) setDroppingDisc({ row, col, player: 'red' })
    setBoard(newBoard)
    const winner = checkWinner(newBoard)
    if (winner) {
      setWinResult(winner)
      sfx.play('win')
      setGameStatus('won')
      setScores(s => ({ ...s, red: s.red + 1 }))
      return
    }
    if (isBoardFull(newBoard)) {
      sfx.play('draw')
      setGameStatus('draw')
      setScores(s => ({ ...s, draw: s.draw + 1 }))
      return
    }
    setCurrentPlayer('yellow')
  }, [board, gameStatus, currentPlayer])

  // AI turn
  useEffect(() => {
    if (currentPlayer !== 'yellow' || gameStatus !== 'playing') return
    aiThinking.current = true

    const timer = setTimeout(() => {
      const depth = DIFFICULTY_DEPTH[difficulty] || 4
      const col = getAIMove(board, 'yellow', depth)
      const { board: newBoard, row } = dropDisc(board, col, 'yellow')
      sfx.play('drop')
      if (naturalDrop) setDroppingDisc({ row, col, player: 'yellow' })
      setBoard(newBoard)

      const winner = checkWinner(newBoard)
      if (winner) {
        setWinResult(winner)
        setGameStatus('lost')
        setScores(s => ({ ...s, yellow: s.yellow + 1 }))
      } else if (isBoardFull(newBoard)) {
        setGameStatus('draw')
        setScores(s => ({ ...s, draw: s.draw + 1 }))
      } else {
        setCurrentPlayer('red')
      }
      aiThinking.current = false
    }, difficulty === 'easy' ? 400 : difficulty === 'medium' ? 700 : 1000)

    return () => clearTimeout(timer)
  }, [currentPlayer, gameStatus, board, difficulty])

  const handleNewGame = useCallback(() => {
    setBoard(createBoard())
    setCurrentPlayer('red')
    setGameStatus('playing')
    setWinResult(null)
    setHoverCol(null)
    setDroppingDisc(null)
    music.start()
    clear()
  }, [music, clear])

  const controls = (
    <div className="flex flex-col gap-1.5 sm:gap-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center justify-between sm:justify-start gap-2">
        <DifficultySelector
          value={difficulty}
          onChange={(d) => { setDifficulty(d); handleNewGame() }}
          options={['easy', 'medium', 'hard']}
        />
        <button
          onClick={() => setNaturalDrop(d => !d)}
          className={`px-2 py-1 rounded text-[0.6rem] font-medium transition-colors ${
            naturalDrop ? 'bg-blue-900/50 text-blue-400' : 'bg-slate-700 text-slate-400'
          }`}
          title={naturalDrop ? 'Gravity drop on' : 'Gravity drop off'}
        >
          {naturalDrop ? 'Drop' : 'Snap'}
        </button>
      </div>
      <div className="flex items-center justify-center sm:justify-end space-x-2 sm:space-x-3 text-xs">
        <span className="text-red-400">You: {scores.red}</span>
        <span className="text-slate-500">Draw: {scores.draw}</span>
        <span className="text-yellow-400">AI: {scores.yellow}</span>
        <button
          onClick={handleNewGame}
          className="px-2 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          New
        </button>
        <button
          onClick={() => setShowHelp(true)}
          className="p-1.5 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-white"
          title="How to play"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Connect Four" controls={controls}>
      <div
        className="relative flex flex-col items-center space-y-2"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect()
          const x = e.clientX - rect.left
          const colWidth = rect.width / 7
          setHoverCol(Math.min(6, Math.floor(x / colWidth)))
        }}
        onMouseLeave={() => setHoverCol(null)}
      >
        {/* Turn indicator */}
        <p className="text-sm text-slate-400">
          {gameStatus === 'playing' && (currentPlayer === 'red' ? 'Your turn' : 'AI thinking...')}
        </p>

        <ConnectFourBoard
          board={board}
          winResult={winResult}
          onColumnClick={handleColumnClick}
          disabled={gameStatus !== 'playing' || currentPlayer !== 'red'}
          hoverCol={hoverCol}
          currentPlayer={currentPlayer}
          droppingDisc={droppingDisc}
          onDropComplete={() => setDroppingDisc(null)}
        />

        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>

      {/* Help modal */}
      {showHelp && <ConnectFourHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}
