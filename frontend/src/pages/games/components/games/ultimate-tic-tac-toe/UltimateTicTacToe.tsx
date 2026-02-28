/**
 * Ultimate Tic-Tac-Toe — 3x3 grid of tic-tac-toe boards.
 *
 * Features: active board highlighting, AI opponent,
 * meta-board progress, undo support.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { Undo2 } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import {
  createBoards, createMetaBoard, makeMove, getValidMoves, getAIMove,
  type SubBoard as SubBoardType, type MetaCell, type Player,
} from './ultimateEngine'
import { SubBoard } from './SubBoard'
import type { GameStatus } from '../../../types'

interface GameState {
  boards: SubBoardType[]
  meta: MetaCell[]
  activeBoard: number | null
  currentPlayer: Player
}

function initialState(): GameState {
  return {
    boards: createBoards(),
    meta: createMetaBoard(),
    activeBoard: null,
    currentPlayer: 'X',
  }
}

export default function UltimateTicTacToe() {
  const [state, setState] = useState<GameState>(initialState)
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [history, setHistory] = useState<GameState[]>([])
  const aiThinking = useRef(false)

  const handleCellClick = useCallback((boardIndex: number, cellIndex: number) => {
    if (gameStatus !== 'playing' || state.currentPlayer !== 'X' || aiThinking.current) return

    const validMoves = getValidMoves(state.boards, state.meta, state.activeBoard)
    if (!validMoves.some(([b, c]) => b === boardIndex && c === cellIndex)) return

    setHistory(prev => [...prev.slice(-20), state])
    const result = makeMove(state.boards, state.meta, boardIndex, cellIndex, 'X')

    if (result.winner) {
      setState({ boards: result.boards, meta: result.meta, activeBoard: null, currentPlayer: 'X' })
      setGameStatus('won')
      return
    }
    if (result.isDraw) {
      setState({ boards: result.boards, meta: result.meta, activeBoard: null, currentPlayer: 'X' })
      setGameStatus('draw')
      return
    }

    setState({
      boards: result.boards,
      meta: result.meta,
      activeBoard: result.nextActiveBoard,
      currentPlayer: 'O',
    })
  }, [state, gameStatus])

  // AI turn
  useEffect(() => {
    if (state.currentPlayer !== 'O' || gameStatus !== 'playing') return
    aiThinking.current = true

    const timer = setTimeout(() => {
      const aiMove = getAIMove(state.boards, state.meta, state.activeBoard, 'O')
      if (!aiMove) {
        aiThinking.current = false
        return
      }

      const [boardIdx, cellIdx] = aiMove
      const result = makeMove(state.boards, state.meta, boardIdx, cellIdx, 'O')

      if (result.winner) {
        setState({ boards: result.boards, meta: result.meta, activeBoard: null, currentPlayer: 'O' })
        setGameStatus('lost')
      } else if (result.isDraw) {
        setState({ boards: result.boards, meta: result.meta, activeBoard: null, currentPlayer: 'O' })
        setGameStatus('draw')
      } else {
        setState({
          boards: result.boards,
          meta: result.meta,
          activeBoard: result.nextActiveBoard,
          currentPlayer: 'X',
        })
      }
      aiThinking.current = false
    }, 300)

    return () => clearTimeout(timer)
  }, [state, gameStatus])

  const handleUndo = useCallback(() => {
    if (history.length === 0 || aiThinking.current) return
    setState(history[history.length - 1])
    setHistory(h => h.slice(0, -1))
  }, [history])

  const handleNewGame = useCallback(() => {
    setState(initialState())
    setGameStatus('playing')
    setHistory([])
  }, [])

  const validMoves = getValidMoves(state.boards, state.meta, state.activeBoard)
  const activeBoardIndices = new Set(validMoves.map(([b]) => b))

  const controls = (
    <div className="flex items-center justify-between">
      <button
        onClick={handleUndo}
        disabled={history.length === 0}
        className="flex items-center space-x-1 px-3 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40 transition-colors"
      >
        <Undo2 className="w-3 h-3" />
        <span>Undo</span>
      </button>
      <p className="text-xs text-slate-400">
        {gameStatus === 'playing' && (state.currentPlayer === 'X' ? 'Your turn (X)' : 'AI thinking...')}
      </p>
    </div>
  )

  return (
    <GameLayout title="Ultimate Tic-Tac-Toe" controls={controls}>
      <div className="relative flex flex-col items-center space-y-4">
        {/* Meta-board: 3x3 grid of sub-boards */}
        <div className="grid grid-cols-3 gap-1 sm:gap-2 bg-slate-800 p-2 sm:p-3 rounded-lg border-2 border-slate-600">
          {state.boards.map((board, i) => (
            <SubBoard
              key={i}
              board={board}
              boardIndex={i}
              metaStatus={state.meta[i]}
              isActive={activeBoardIndices.has(i)}
              onCellClick={handleCellClick}
              disabled={gameStatus !== 'playing' || state.currentPlayer !== 'X'}
            />
          ))}
        </div>

        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            onPlayAgain={handleNewGame}
          />
        )}
      </div>
    </GameLayout>
  )
}
