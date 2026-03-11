/**
 * Checkers game — classic board game against AI opponent.
 *
 * Features: AI with difficulty levels, mandatory captures,
 * multi-jump chains, king promotion, score tracking.
 */

import { useState, useCallback, useEffect, useRef, useMemo} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import {
  createBoard, getAllMoves, applyMove, promoteKings,
  checkGameOver, getAIMove, getCaptureMoves,
  type Board, type Move,
} from './checkersEngine'
import { CheckersBoard } from './CheckersBoard'
import { CheckersMultiplayer } from './CheckersMultiplayer'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus, Difficulty } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'

// ── Help modal ───────────────────────────────────────────────────────

function CheckersHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Checkers</h2>

        {/* Goal */}
        <Section title="Goal">
          Capture all of your opponent&apos;s pieces or block them so they
          have no valid moves. You play as <B>red</B> against a <B>black</B> AI opponent.
        </Section>

        {/* Setup */}
        <Section title="Setup">
          The game is played on an 8x8 board. Only the dark squares are used.
          Each player starts with <B>12 pieces</B> arranged on the three rows
          closest to their side. Red pieces start at the bottom; black pieces
          start at the top.
        </Section>

        {/* Piece movement */}
        <Section title="Piece Movement">
          <ul className="space-y-1 text-slate-300">
            <Li>Regular pieces move <B>diagonally forward</B> one square at a time.</Li>
            <Li>Red pieces move upward (toward the top of the board).</Li>
            <Li>Pieces can only land on <B>empty dark squares</B>.</Li>
          </ul>
        </Section>

        {/* Jumps / Captures */}
        <Section title="Jumps &amp; Captures">
          <ul className="space-y-1 text-slate-300">
            <Li>To capture an opponent&apos;s piece, jump over it diagonally
              to an empty square beyond it.</Li>
            <Li>The captured piece is <B>removed from the board</B>.</Li>
            <Li>Captures are <B>mandatory</B> — if a jump is available, you
              must take it. You cannot make a regular move instead.</Li>
          </ul>
        </Section>

        {/* Multi-jumps */}
        <Section title="Multi-Jumps">
          If after a capture your piece can immediately jump another
          opponent&apos;s piece, you <B>must continue jumping</B> with the
          same piece. A single turn can chain multiple captures across the board.
        </Section>

        {/* Kinging */}
        <Section title="Kinging">
          <ul className="space-y-1 text-slate-300">
            <Li>When a piece reaches the <B>far end of the board</B> (the
              opponent&apos;s back row), it is promoted to a <B>King</B>.</Li>
            <Li>Kings are marked with a crown symbol.</Li>
            <Li>Kings can move and capture <B>diagonally in all four
              directions</B> — both forward and backward.</Li>
          </ul>
        </Section>

        {/* Winning */}
        <Section title="Winning Conditions">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Capture all</B> of your opponent&apos;s pieces, or</Li>
            <Li><B>Block all</B> of your opponent&apos;s pieces so they have
              no legal moves on their turn.</Li>
          </ul>
        </Section>

        {/* AI */}
        <Section title="AI Opponent">
          <ul className="space-y-1 text-slate-300">
            <Li>The AI uses minimax search with alpha-beta pruning.</Li>
            <Li>Three difficulty levels control how far ahead the AI looks:</Li>
          </ul>
          <div className="mt-1.5 space-y-1 text-slate-300 pl-3">
            <div className="flex gap-1.5 text-xs">
              <span className="text-green-400 font-medium w-16">Easy</span>
              <span>— looks 2 moves ahead</span>
            </div>
            <div className="flex gap-1.5 text-xs">
              <span className="text-yellow-400 font-medium w-16">Medium</span>
              <span>— looks 4 moves ahead</span>
            </div>
            <div className="flex gap-1.5 text-xs">
              <span className="text-red-400 font-medium w-16">Hard</span>
              <span>— looks 6 moves ahead</span>
            </div>
          </div>
        </Section>

        {/* Controls */}
        <Section title="Controls">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Click</B> one of your red pieces to select it. Valid moves
              will be highlighted on the board.</Li>
            <Li><B>Click</B> a highlighted square to move or jump to it.</Li>
            <Li>Click a <B>different piece</B> to change your selection.</Li>
            <Li>Click an <B>invalid square</B> to deselect.</Li>
            <Li>Use the <B>difficulty selector</B> to change AI strength
              (starts a new game).</Li>
            <Li>Scores are tracked across games in your session.</Li>
          </ul>
        </Section>

        {/* Strategy tips */}
        <Section title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Control the center</B> — pieces in the middle of the board
              have more options than pieces on the edges.</Li>
            <Li><B>Protect your back row</B> — keeping pieces on your back
              row prevents the opponent from getting kings.</Li>
            <Li><B>Push for kings</B> — kings are far more powerful since they
              move in all directions. Advance pieces when safe.</Li>
            <Li><B>Force trades when ahead</B> — if you have more pieces,
              exchanging captures favors you.</Li>
            <Li><B>Watch for double jumps</B> — setting up multi-jump chains
              can swing the game in your favor.</Li>
            <Li><B>Avoid isolated pieces</B> — pieces that stray too far from
              support are easy targets for capture.</Li>
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
  return <li className="flex gap-1.5 text-xs"><span className="text-slate-600 mt-0.5">•</span><span>{children}</span></li>
}

function B({ children }: { children: React.ReactNode }) {
  return <span className="text-white font-medium">{children}</span>
}

const DIFFICULTY_DEPTH: Record<string, number> = {
  easy: 2, medium: 4, hard: 6,
}

interface CheckersState {
  board: Board
  gameStatus: GameStatus
  difficulty: Difficulty
  scores: { red: number; black: number; draw: number }
  isPlayerTurn: boolean
}

function CheckersSinglePlayer({ onGameEnd, onStateChange: _onStateChange }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void } = {}) {
  const { load, save, clear } = useGameState<CheckersState>('checkers')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('checkers'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('checkers')

  const [board, setBoard] = useState<Board>(saved?.board ?? createBoard)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedPiece, setSelectedPiece] = useState<[number, number] | null>(null)
  const [validMoves, setValidMoves] = useState<Move[]>([])
  const [lastMove, setLastMove] = useState<Move | null>(null)
  const [difficulty, setDifficulty] = useState<Difficulty>(saved?.difficulty ?? 'medium')
  const [scores, setScores] = useState(saved?.scores ?? { red: 0, black: 0, draw: 0 })
  const [isPlayerTurn, setIsPlayerTurn] = useState(saved?.isPlayerTurn ?? true)
  const aiThinking = useRef(false)

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

  // Persist state on changes
  useEffect(() => {
    save({ board, gameStatus, difficulty, scores, isPlayerTurn })
  }, [board, gameStatus, difficulty, scores, isPlayerTurn, save])

  /** Get all moves available for the player's piece at (r,c). */
  const getMovesForPiece = useCallback((board: Board, r: number, c: number): Move[] => {
    const allPlayerMoves = getAllMoves(board, 'red')
    return allPlayerMoves.filter(m => m.from[0] === r && m.from[1] === c)
  }, [])

  const handleSquareClick = useCallback((r: number, c: number) => {
    if (gameStatus !== 'playing' || !isPlayerTurn || aiThinking.current) return

    music.init()
    sfx.init()
    music.start()

    const piece = board[r][c]

    // If clicking on own piece, select it
    if (piece && piece.player === 'red') {
      const moves = getMovesForPiece(board, r, c)
      if (moves.length > 0) {
        setSelectedPiece([r, c])
        setValidMoves(moves)
      }
      return
    }

    // If a piece is selected and clicking on a valid target, make the move
    if (selectedPiece) {
      const move = validMoves.find(m => m.to[0] === r && m.to[1] === c)
      if (move) {
        let newBoard = applyMove(board, move)
        const wasKing = board[move.from[0]][move.from[1]]?.isKing
        newBoard = promoteKings(newBoard)
        if (move.captures.length > 0) { sfx.play('jump') } else { sfx.play('move') }
        if (!wasKing && newBoard[move.to[0]][move.to[1]]?.isKing) { sfx.play('king') }
        setBoard(newBoard)
        setLastMove(move)
        setSelectedPiece(null)
        setValidMoves([])

        // Check for multi-jump continuation
        if (move.captures.length > 0) {
          const furtherCaptures = getCaptureMoves(newBoard, move.to[0], move.to[1])
          if (furtherCaptures.length > 0) {
            // Must continue jumping with same piece
            setSelectedPiece(move.to)
            setValidMoves(furtherCaptures)
            return
          }
        }

        const winner = checkGameOver(newBoard)
        if (winner === 'red') {
          sfx.play('win')
          setGameStatus('won')
          onGameEnd?.('win')
          setScores(s => ({ ...s, red: s.red + 1 }))
        } else if (winner === 'black') {
          setGameStatus('lost')
          onGameEnd?.('loss')
          setScores(s => ({ ...s, black: s.black + 1 }))
        } else {
          setIsPlayerTurn(false)
        }
      } else {
        // Clicked invalid square, deselect
        setSelectedPiece(null)
        setValidMoves([])
      }
    }
  }, [board, gameStatus, isPlayerTurn, selectedPiece, validMoves, getMovesForPiece, onGameEnd])

  // AI turn
  useEffect(() => {
    if (isPlayerTurn || gameStatus !== 'playing') return
    aiThinking.current = true

    const timer = setTimeout(() => {
      const depth = DIFFICULTY_DEPTH[difficulty] || 4
      const aiMove = getAIMove(board, 'black', depth)
      if (!aiMove) {
        setGameStatus('won')
        onGameEnd?.('win')
        setScores(s => ({ ...s, red: s.red + 1 }))
        aiThinking.current = false
        return
      }

      let newBoard = applyMove(board, aiMove)
      newBoard = promoteKings(newBoard)
      setBoard(newBoard)
      setLastMove(aiMove)

      const winner = checkGameOver(newBoard)
      if (winner === 'black') {
        setGameStatus('lost')
        onGameEnd?.('loss')
        setScores(s => ({ ...s, black: s.black + 1 }))
      } else if (winner === 'red') {
        setGameStatus('won')
        onGameEnd?.('win')
        setScores(s => ({ ...s, red: s.red + 1 }))
      } else {
        setIsPlayerTurn(true)
      }
      aiThinking.current = false
    }, 300)

    return () => clearTimeout(timer)
  }, [isPlayerTurn, gameStatus, board, difficulty, onGameEnd])

  const handleNewGame = useCallback(() => {
    setBoard(createBoard())
    setGameStatus('playing')
    setSelectedPiece(null)
    setValidMoves([])
    setLastMove(null)
    setIsPlayerTurn(true)
    clear()
    music.start()
  }, [clear, music])

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <DifficultySelector
          value={difficulty}
          onChange={(d) => { setDifficulty(d); handleNewGame() }}
          options={['easy', 'medium', 'hard']}
        />
        <button
          onClick={handleNewGame}
          className="px-3 py-1 rounded text-sm font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          New Game
        </button>
      </div>
      <div className="flex items-center space-x-3 text-xs">
        <span className="text-red-400">You: {scores.red}</span>
        <span className="text-slate-500">Draw: {scores.draw}</span>
        <span className="text-slate-300">AI: {scores.black}</span>
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
    <GameLayout title="Checkers" controls={controls}>
      <div className="relative flex flex-col items-center space-y-2">
        <p className="text-sm text-slate-400">
          {gameStatus === 'playing' && (isPlayerTurn ? 'Your turn (red)' : 'AI thinking...')}
        </p>

        <CheckersBoard
          board={board}
          selectedPiece={selectedPiece}
          validMoves={validMoves}
          onSquareClick={handleSquareClick}
          disabled={gameStatus !== 'playing' || !isPlayerTurn}
          lastMove={lastMove}
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
      {showHelp && <CheckersHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Multiplayer race wrapper ─────────────────────────────────────────
function CheckersRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
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
        onDismiss={onLeave}
      />
      <CheckersSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} />
    </div>
  )
}

export default function Checkers() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'checkers',
        gameName: 'Checkers',
        modes: ['vs', 'first_to_win'],
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: { first_to_win: 'First to beat the AI wins' },
      }}
      renderSinglePlayer={() => <CheckersSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) => (
        mode === 'vs'
          ? <CheckersMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
          : <CheckersRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
      )}
    />
  )
}
