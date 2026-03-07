/**
 * Tic-Tac-Toe game — player (X) vs AI (O).
 *
 * Features: minimax AI, difficulty toggle, score tracking, animated winning line.
 */

import { useState, useCallback, useEffect, useMemo} from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { TicTacToeBoard } from './TicTacToeBoard'
import {
  createBoard,
  checkWinner,
  isBoardFull,
  getAIMove,
  type Board,
  type WinResult,
  type Difficulty,
} from './ticTacToeEngine'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'

interface Scores {
  x: number
  o: number
  draws: number
}

export default function TicTacToe() {
  // Music
  const song = useMemo(() => getSongForGame('tic-tac-toe'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('tic-tac-toe')

  const [board, setBoard] = useState<Board>(createBoard)
  const [isPlayerTurn, setIsPlayerTurn] = useState(true)
  const [winResult, setWinResult] = useState<WinResult | null>(null)
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [difficulty, setDifficulty] = useState<Difficulty>('hard')
  const [scores, setScores] = useState<Scores>({ x: 0, o: 0, draws: 0 })

  const handleCellClick = useCallback((index: number) => {
    if (!isPlayerTurn || board[index] || gameStatus !== 'playing') return

    music.init()
    sfx.init()
    music.start()

    const newBoard = [...board]
    newBoard[index] = 'X'
    sfx.play('place')
    setBoard(newBoard)

    const result = checkWinner(newBoard)
    if (result) {
      setWinResult(result)
      sfx.play('win')
      setGameStatus('won')
      setScores(s => ({ ...s, x: s.x + 1 }))
      return
    }
    if (isBoardFull(newBoard)) {
      sfx.play('draw')
      setGameStatus('draw')
      setScores(s => ({ ...s, draws: s.draws + 1 }))
      return
    }

    setIsPlayerTurn(false)
  }, [board, isPlayerTurn, gameStatus])

  // AI move
  useEffect(() => {
    if (isPlayerTurn || gameStatus !== 'playing') return

    const timer = setTimeout(() => {
      const aiIndex = getAIMove(board, 'O', difficulty)
      if (aiIndex < 0) return

      const newBoard = [...board]
      newBoard[aiIndex] = 'O'
      setBoard(newBoard)

      const result = checkWinner(newBoard)
      if (result) {
        setWinResult(result)
        sfx.play('lose')
        setGameStatus('lost')
        setScores(s => ({ ...s, o: s.o + 1 }))
        return
      }
      if (isBoardFull(newBoard)) {
        sfx.play('draw')
        setGameStatus('draw')
        setScores(s => ({ ...s, draws: s.draws + 1 }))
        return
      }

      setIsPlayerTurn(true)
    }, 300)

    return () => clearTimeout(timer)
  }, [isPlayerTurn, gameStatus, board, difficulty])

  const handlePlayAgain = useCallback(() => {
    setBoard(createBoard())
    setWinResult(null)
    setGameStatus('playing')
    setIsPlayerTurn(true)
    music.start()
  }, [music])

  const controls = (
    <div className="flex items-center justify-between">
      {/* Difficulty toggle */}
      <div className="flex space-x-2">
        {(['easy', 'hard'] as const).map(d => (
          <button
            key={d}
            onClick={() => { setDifficulty(d); handlePlayAgain() }}
            className={`px-3 py-1 rounded text-sm font-medium capitalize transition-colors ${
              difficulty === d
                ? d === 'easy' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'
                : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
          >
            {d}
          </button>
        ))}
      </div>

      {/* Score display & music */}
      <div className="flex items-center space-x-3 text-sm">
        <span className="text-blue-400">X: {scores.x}</span>
        <span className="text-slate-500">Draw: {scores.draws}</span>
        <span className="text-red-400">O: {scores.o}</span>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Tic-Tac-Toe" controls={controls}>
      <div className="relative">
        {/* Turn indicator */}
        {gameStatus === 'playing' && (
          <p className="text-center text-sm mb-4 text-slate-400">
            {isPlayerTurn
              ? <span>Your turn (<span className="text-blue-400 font-bold">X</span>)</span>
              : <span>AI thinking (<span className="text-red-400 font-bold">O</span>)...</span>
            }
          </p>
        )}

        <TicTacToeBoard
          board={board}
          winResult={winResult}
          onCellClick={handleCellClick}
          disabled={!isPlayerTurn || gameStatus !== 'playing'}
        />

        {gameStatus !== 'playing' && gameStatus !== 'idle' && (
          <GameOverModal
            status={gameStatus}
            message={
              gameStatus === 'won' ? 'You beat the AI!'
                : gameStatus === 'lost' ? 'The AI wins this round.'
                : 'Nobody wins!'
            }
            onPlayAgain={handlePlayAgain}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
