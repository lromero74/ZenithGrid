import { useState, useCallback, useEffect, useRef } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import {
  createBoard, rollDice, getValidMoves, applyMove,
  hasValidMoves, checkWin, getAIMove,
  type BackgammonState,
} from './backgammonEngine'
import { BackgammonBoard } from './BackgammonBoard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus, Difficulty } from '../../../types'

interface SavedState {
  gameState: BackgammonState
  gameStatus: GameStatus
  difficulty: Difficulty
  scores: { white: number; brown: number }
}

export default function Backgammon() {
  const { load, save, clear } = useGameState<SavedState>('backgammon')
  const saved = useRef(load()).current

  const [gameState, setGameState] = useState<BackgammonState>(saved?.gameState ?? createBoard)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [difficulty, setDifficulty] = useState<Difficulty>(saved?.difficulty ?? 'medium')
  const [scores, setScores] = useState(saved?.scores ?? { white: 0, brown: 0 })
  const [selectedPoint, setSelectedPoint] = useState<number | 'bar' | null>(null)
  const [validMoves, setValidMoves] = useState<{ from: number | 'bar'; to: number | 'off' }[]>([])
  const aiThinking = useRef(false)

  // Persist state
  useEffect(() => {
    save({ gameState, gameStatus, difficulty, scores })
  }, [gameState, gameStatus, difficulty, scores, save])

  // Compute all valid moves for current dice
  const getAllCurrentMoves = useCallback((state: BackgammonState) => {
    const moves: { from: number | 'bar'; to: number | 'off'; dieIndex: number }[] = []
    for (let i = 0; i < state.dice.length; i++) {
      if (state.usedDice[i]) continue
      for (const m of getValidMoves(state, state.dice[i])) {
        moves.push({ ...m, dieIndex: i })
      }
    }
    return moves
  }, [])

  // After player or AI finishes their turn (all dice used or no moves), switch turns
  const finishTurn = useCallback((state: BackgammonState) => {
    const winner = checkWin(state)
    if (winner === 'white') {
      setGameStatus('won')
      setScores(s => ({ ...s, white: s.white + 1 }))
      setGameState({ ...state, gamePhase: 'gameOver' })
      return
    }
    if (winner === 'brown') {
      setGameStatus('lost')
      setScores(s => ({ ...s, brown: s.brown + 1 }))
      setGameState({ ...state, gamePhase: 'gameOver' })
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
  }, [])

  // Handle dice roll
  const handleRoll = useCallback(() => {
    if (gameState.gamePhase !== 'rolling' || gameStatus !== 'playing') return

    const dice = rollDice()
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

    const allMoves = getAllCurrentMoves(gameState)

    // If clicking on a source point (has valid moves from here)
    const movesFromPoint = allMoves.filter(m => m.from === point)
    if (movesFromPoint.length > 0) {
      setSelectedPoint(point)
      setValidMoves(movesFromPoint)
      return
    }

    // If a point is selected and clicking on a valid destination
    if (selectedPoint !== null) {
      const move = allMoves.find(m => m.from === selectedPoint && m.to === point)
      if (move) {
        const newState = applyMove(gameState, move.from, move.to as number, move.dieIndex)
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
  }, [clear])

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
          />
        )}
      </div>
    </GameLayout>
  )
}
