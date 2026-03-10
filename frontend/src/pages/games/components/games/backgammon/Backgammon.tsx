import { useState, useCallback, useEffect, useRef, useMemo} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import {
  createBoard, rollDice, getFilteredMoves, applyMove,
  hasValidMoves, checkWin, getAIMove,
  type BackgammonState,
} from './backgammonEngine'
import { BackgammonBoard } from './BackgammonBoard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus, Difficulty } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

// ── Help modal ───────────────────────────────────────────────────────

function BackgammonHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Backgammon</h2>

        {/* Goal */}
        <Section title="Goal">
          Be the first player to move all 15 of your checkers off the board
          (called <B>bearing off</B>). You play as <B>white</B> against
          a <B>brown</B> AI opponent.
        </Section>

        {/* Board Layout */}
        <Section title="Board Layout">
          <ul className="space-y-1 text-slate-300">
            <Li>The board has <B>24 narrow triangles</B> called points,
              numbered 1 through 24.</Li>
            <Li>Points are grouped into four quadrants of six points each.</Li>
            <Li>Your <B>home board</B> (points 1-6) is where you bear off.
              The AI&apos;s home board is on the opposite side.</Li>
            <Li>A center strip called the <B>bar</B> divides the board in half.</Li>
          </ul>
        </Section>

        {/* Starting Position */}
        <Section title="Starting Position">
          Each player begins with 15 checkers arranged in a fixed pattern:
          <ul className="space-y-1 text-slate-300 mt-1">
            <Li><B>2 checkers</B> on your farthest point from home</Li>
            <Li><B>5 checkers</B> on your opponent&apos;s side (middle area)</Li>
            <Li><B>3 checkers</B> near the midpoint</Li>
            <Li><B>5 checkers</B> in your home board area</Li>
          </ul>
        </Section>

        {/* Dice & Moving */}
        <Section title="Dice &amp; Moving">
          <ul className="space-y-1 text-slate-300">
            <Li>Click <B>Roll Dice</B> to roll two dice on your turn.</Li>
            <Li>Each die is a separate move &mdash; you must use both if
              possible.</Li>
            <Li>White moves from higher-numbered points toward point 1.
              Brown moves in the opposite direction.</Li>
            <Li><B>Doubles</B> are special: rolling the same number on both
              dice gives you <B>four moves</B> of that value instead of two.</Li>
            <Li>If only one die can be used, you must play the <B>larger
              value</B> when possible.</Li>
          </ul>
        </Section>

        {/* How to Move */}
        <Section title="How to Move">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Click</B> one of your white checkers to select it. Valid
              destinations will be highlighted.</Li>
            <Li><B>Click</B> a highlighted point to move there.</Li>
            <Li>You may land on any point that is <B>empty</B>, occupied by
              your own checkers, or occupied by <B>exactly one</B> opponent
              checker (a blot).</Li>
            <Li>You <B>cannot</B> land on a point held by two or more
              opponent checkers &mdash; it is blocked.</Li>
          </ul>
        </Section>

        {/* Hitting & the Bar */}
        <Section title="Hitting &amp; the Bar">
          <ul className="space-y-1 text-slate-300">
            <Li>A single checker sitting alone on a point is called
              a <B>blot</B>.</Li>
            <Li>If you land on an opponent&apos;s blot, that checker is <B>hit</B> and
              placed on the bar.</Li>
            <Li>A player with checkers on the bar <B>must re-enter them
              first</B> before making any other moves.</Li>
            <Li>Checkers re-enter in the opponent&apos;s home board using
              a die value. If all entry points are blocked, you lose
              your turn.</Li>
          </ul>
        </Section>

        {/* Bearing Off */}
        <Section title="Bearing Off">
          <ul className="space-y-1 text-slate-300">
            <Li>Once <B>all 15</B> of your checkers are in your home board
              (points 1-6), you may begin bearing off.</Li>
            <Li>Roll a die matching a point with your checker to remove
              it from the board.</Li>
            <Li>If you roll a number higher than your farthest checker,
              you may bear off the farthest checker instead.</Li>
            <Li>You <B>cannot</B> bear off while any of your checkers
              are on the bar or outside your home board.</Li>
            <Li>Click the <B>bear-off tray</B> after selecting a checker
              to remove it from the board.</Li>
          </ul>
        </Section>

        {/* AI Opponent */}
        <Section title="AI Opponent">
          <ul className="space-y-1 text-slate-300">
            <Li>The AI evaluates each possible move and picks the best
              one using a scoring system.</Li>
            <Li>It prioritizes: entering from the bar, bearing off,
              hitting your blots, building points (stacking two or more
              checkers), and advancing toward home.</Li>
            <Li>It avoids leaving its own blots exposed when possible.</Li>
          </ul>
        </Section>

        {/* Controls */}
        <Section title="Controls">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Roll Dice</B> &mdash; appears when it is your turn to roll.</Li>
            <Li><B>Click a checker</B> to select it, then click a highlighted
              point to move.</Li>
            <Li><B>Click the bear-off tray</B> to bear off a selected checker.</Li>
            <Li><B>New Game</B> &mdash; resets the board and starts fresh.</Li>
            <Li><B>Difficulty selector</B> &mdash; change AI strength (starts
              a new game).</Li>
            <Li>Scores are tracked across games: <B>W</B> (white/you)
              and <B>B</B> (brown/AI).</Li>
          </ul>
        </Section>

        {/* Strategy Tips */}
        <Section title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Build points</B> &mdash; stack two or more checkers on a
              point to block your opponent and protect your pieces.</Li>
            <Li><B>Create a prime</B> &mdash; six consecutive blocked points
              form an impassable wall the opponent cannot cross.</Li>
            <Li><B>Hit when safe</B> &mdash; send opponent checkers to the bar,
              but avoid leaving your own blots exposed in return.</Li>
            <Li><B>Avoid lonely checkers</B> &mdash; single checkers (blots) are
              vulnerable to being hit. Pair them up when possible.</Li>
            <Li><B>Race when ahead</B> &mdash; if your checkers are closer to
              home, focus on advancing rather than fighting.</Li>
            <Li><B>Control your home board</B> &mdash; the more points you hold
              in your home board, the harder it is for your opponent to
              re-enter from the bar.</Li>
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

interface SavedState {
  gameState: BackgammonState
  gameStatus: GameStatus
  difficulty: Difficulty
  scores: { white: number; brown: number }
}

function BackgammonSinglePlayer({ onGameEnd, onStateChange: _onStateChange }: { onGameEnd?: (result: 'win' | 'loss') => void; onStateChange?: (state: object) => void } = {}) {
  const { load, save, clear } = useGameState<SavedState>('backgammon')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('backgammon'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('backgammon')

  const [gameState, setGameState] = useState<BackgammonState>(saved?.gameState ?? createBoard)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [difficulty, setDifficulty] = useState<Difficulty>(saved?.difficulty ?? 'medium')
  const [scores, setScores] = useState(saved?.scores ?? { white: 0, brown: 0 })
  const [selectedPoint, setSelectedPoint] = useState<number | 'bar' | null>(null)
  const [validMoves, setValidMoves] = useState<{ from: number | 'bar'; to: number | 'off' }[]>([])
  const [showHelp, setShowHelp] = useState(false)
  const aiThinking = useRef(false)

  // Persist state
  useEffect(() => {
    save({ gameState, gameStatus, difficulty, scores })
  }, [gameState, gameStatus, difficulty, scores, save])

  // Compute obligation-filtered valid moves for current dice
  const getAllCurrentMoves = useCallback((state: BackgammonState) => {
    return getFilteredMoves(state)
  }, [])

  // After player or AI finishes their turn (all dice used or no moves), switch turns
  const finishTurn = useCallback((state: BackgammonState) => {
    const winner = checkWin(state)
    if (winner === 'white') {
      sfx.play('win')
      setGameStatus('won')
      setScores(s => ({ ...s, white: s.white + 1 }))
      setGameState({ ...state, gamePhase: 'gameOver' })
      onGameEnd?.('win')
      return
    }
    if (winner === 'brown') {
      setGameStatus('lost')
      setScores(s => ({ ...s, brown: s.brown + 1 }))
      setGameState({ ...state, gamePhase: 'gameOver' })
      onGameEnd?.('loss')
      return
    }

    // Switch to other player's rolling phase
    const nextPlayer = state.currentPlayer === 'white' ? 'brown' : 'white'
    setGameState({
      ...state,
      currentPlayer: nextPlayer,
      gamePhase: 'rolling',
      dice: [],
      usedDice: [],
    })
  }, [onGameEnd])

  // Handle dice roll
  const handleRoll = useCallback(() => {
    if (gameState.gamePhase !== 'rolling' || gameStatus !== 'playing') return

    music.init()
    sfx.init()
    music.start()

    const dice = rollDice()
    sfx.play('roll')
    const newState: BackgammonState = {
      ...gameState,
      dice,
      usedDice: dice.map(() => false),
      gamePhase: 'moving',
    }

    // Check if player has any moves
    if (!hasValidMoves(newState)) {
      finishTurn(newState)
      return
    }

    setGameState(newState)
    setSelectedPoint(null)
    setValidMoves([])
  }, [gameState, gameStatus, finishTurn])

  // Handle point click (select source or destination)
  const handlePointClick = useCallback((point: number | 'bar') => {
    if (gameStatus !== 'playing' || gameState.currentPlayer !== 'white' || disabled) return

    music.init()
    sfx.init()
    music.start()

    const allMoves = getAllCurrentMoves(gameState)

    // If a point is already selected, prioritize executing a move to the
    // clicked destination. Without this, clicking a destination that also
    // has your checkers would re-select it as a source instead of moving.
    if (selectedPoint !== null) {
      const move = allMoves.find(m => m.from === selectedPoint && m.to === point)
      if (move) {
        const newState = applyMove(gameState, move.from, move.to, move.dieIndex)
        sfx.play('move')
        setGameState(newState)
        setSelectedPoint(null)
        setValidMoves([])

        // Check if turn is over
        if (!hasValidMoves(newState)) {
          finishTurn(newState)
        }
        return
      }
    }

    // Select as source if it has valid moves from here
    const movesFromPoint = allMoves.filter(m => m.from === point)
    if (movesFromPoint.length > 0) {
      setSelectedPoint(point)
      setValidMoves(movesFromPoint)
      return
    }

    // Deselect
    setSelectedPoint(null)
    setValidMoves([])
  }, [gameState, gameStatus, selectedPoint, getAllCurrentMoves, finishTurn])

  // Handle bear-off click
  const handleBearOff = useCallback(() => {
    if (selectedPoint === null || gameStatus !== 'playing' || gameState.currentPlayer !== 'white') return

    const allMoves = getAllCurrentMoves(gameState)
    const move = allMoves.find(m => m.from === selectedPoint && m.to === 'off')
    if (!move) return

    const newState = applyMove(gameState, move.from, 'off', move.dieIndex)
    setGameState(newState)
    setSelectedPoint(null)
    setValidMoves([])

    if (!hasValidMoves(newState)) {
      finishTurn(newState)
    }
  }, [gameState, gameStatus, selectedPoint, getAllCurrentMoves, finishTurn])

  // AI turn
  useEffect(() => {
    if (gameState.currentPlayer !== 'brown' || gameStatus !== 'playing') return

    // AI rolling phase
    if (gameState.gamePhase === 'rolling') {
      aiThinking.current = true
      const timer = setTimeout(() => {
        handleRollForAI()
      }, 500)
      return () => clearTimeout(timer)
    }

    // AI moving phase
    if (gameState.gamePhase === 'moving') {
      aiThinking.current = true
      const timer = setTimeout(() => {
        const move = getAIMove(gameState)
        if (!move) {
          finishTurn(gameState)
          aiThinking.current = false
          return
        }

        const newState = applyMove(gameState, move.from, move.to as number, move.dieIndex)

        if (!hasValidMoves(newState)) {
          finishTurn(newState)
        } else {
          setGameState(newState)
        }
        aiThinking.current = false
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [gameState, gameStatus, finishTurn])

  // Separate function for AI roll to avoid stale closure
  const handleRollForAI = useCallback(() => {
    const dice = rollDice()
    const newState: BackgammonState = {
      ...gameState,
      dice,
      usedDice: dice.map(() => false),
      gamePhase: 'moving',
    }

    if (!hasValidMoves(newState)) {
      finishTurn(newState)
      aiThinking.current = false
      return
    }

    setGameState(newState)
    aiThinking.current = false
  }, [gameState, finishTurn])

  const handleNewGame = useCallback(() => {
    setGameState(createBoard())
    setGameStatus('playing')
    setSelectedPoint(null)
    setValidMoves([])
    clear()
    music.start()
  }, [clear, music])

  const disabled = gameStatus !== 'playing' ||
    gameState.currentPlayer !== 'white' ||
    gameState.gamePhase !== 'moving'

  const statusMessage = (() => {
    if (gameStatus !== 'playing') return ''
    if (gameState.currentPlayer === 'brown') return 'AI thinking...'
    if (gameState.gamePhase === 'rolling') return 'Roll the dice!'
    if (gameState.gamePhase === 'moving') {
      if (selectedPoint !== null) return 'Select destination'
      return 'Select a checker to move'
    }
    return ''
  })()

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
      <div className="flex items-center gap-3">
        {gameState.gamePhase === 'rolling' && gameState.currentPlayer === 'white' && gameStatus === 'playing' && (
          <button
            onClick={handleRoll}
            className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-medium transition-colors"
          >
            Roll Dice
          </button>
        )}
        <button
          onClick={() => setShowHelp(true)}
          className="p-1.5 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-white"
          title="How to play"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
        <span className="text-xs text-slate-400">W: {scores.white} B: {scores.brown}</span>
      </div>
    </div>
  )

  return (
    <GameLayout title="Backgammon" controls={controls}>
      <div className="relative flex flex-col items-center space-y-2">
        <p className="text-sm text-slate-400">{statusMessage}</p>

        <BackgammonBoard
          state={gameState}
          validMoves={validMoves}
          selectedPoint={selectedPoint}
          onPointClick={handlePointClick}
          onBearOff={handleBearOff}
          disabled={disabled}
        />

        {(gameStatus === 'won' || gameStatus === 'lost') && (
          <GameOverModal
            status={gameStatus}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>

      {/* Help modal */}
      {showHelp && <BackgammonHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Multiplayer race wrapper ─────────────────────────────────────────

function BackgammonRaceWrapper({ roomId, difficulty: _difficulty }: { roomId: string; difficulty?: string }) {
  const { opponentStatus, raceResult, opponentLevelUp, broadcastState, reportFinish } = useRaceMode(roomId, 'first_to_win')
  const finishedRef = useRef(false)

  const handleGameEnd = useCallback((result: 'win' | 'loss') => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish(result)
  }, [reportFinish])

  return (
    <div className="relative">
      <RaceOverlay
        raceResult={raceResult}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
      />
      <BackgammonSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} />
    </div>
  )
}

// ── Default export with multiplayer support ──────────────────────────

export default function Backgammon() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'backgammon',
        gameName: 'Backgammon',
        modes: ['race'],
        maxPlayers: 2,
        hasDifficulty: true,
        raceDescription: 'First to beat the AI wins',
      }}
      renderSinglePlayer={() => <BackgammonSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig) => (
        <BackgammonRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} />
      )}
    />
  )
}
