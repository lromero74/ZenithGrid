/**
 * Tic-Tac-Toe game — player (X) vs AI (O).
 *
 * Features: minimax AI, difficulty toggle, score tracking, animated winning line.
 */

import { useState, useCallback, useEffect, useMemo, useRef} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import { TicTacToeMultiplayer } from './TicTacToeMultiplayer'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { TicTacToeBoard } from './TicTacToeBoard'
import { useGameState } from '../../../hooks/useGameState'
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

interface TicTacToeSaved {
  board: Board
  gameStatus: GameStatus
  difficulty: Difficulty
  scores: Scores
}

function TicTacToeHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Tic-Tac-Toe</h2>
        <Sec title="Goal"><p>Get three of your marks (<B>X</B>) in a row — horizontally, vertically, or diagonally — before the AI (<B>O</B>).</p></Sec>
        <Sec title="How to Play"><ul className="space-y-1">
          <Li>You play as <B>X</B> and go first. Click any empty cell to place your mark.</Li>
          <Li>The AI plays as <B>O</B> and responds automatically.</Li>
          <Li>The game ends when someone gets three in a row, or all 9 cells are filled (draw).</Li>
        </ul></Sec>
        <Sec title="Difficulty"><ul className="space-y-1">
          <Li><B>Easy</B> — AI makes random moves.</Li>
          <Li><B>Medium</B> — AI plays reasonably but can be beaten.</Li>
          <Li><B>Hard</B> — AI plays optimally — best you can do is draw!</Li>
        </ul></Sec>
        <Sec title="Strategy Tips"><ul className="space-y-1">
          <Li>Take the center if it's open — it's part of the most winning lines.</Li>
          <Li>Corners are the next best — they create fork opportunities.</Li>
          <Li>On Hard difficulty, the AI is unbeatable. Play for the draw!</Li>
        </ul></Sec>
      </div>
    </div>
  )
}

function TicTacToeSinglePlayer({ onGameEnd, onStateChange: _onStateChange }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void } = {}) {
  const { load, save, clear } = useGameState<TicTacToeSaved>('tic-tac-toe')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('tic-tac-toe'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('tic-tac-toe')

  const [showHelp, setShowHelp] = useState(false)
  const [board, setBoard] = useState<Board>(() => saved?.board ?? createBoard())
  const [isPlayerTurn, setIsPlayerTurn] = useState(true)
  const [winResult, setWinResult] = useState<WinResult | null>(null)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [difficulty, setDifficulty] = useState<Difficulty>(saved?.difficulty ?? 'hard')
  const [scores, setScores] = useState<Scores>(saved?.scores ?? { x: 0, o: 0, draws: 0 })

  // Persist state
  useEffect(() => {
    save({ board, gameStatus, difficulty, scores })
  }, [board, gameStatus, difficulty, scores, save])

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
      onGameEnd?.('win')
      setScores(s => ({ ...s, x: s.x + 1 }))
      return
    }
    if (isBoardFull(newBoard)) {
      sfx.play('draw')
      setGameStatus('draw')
      onGameEnd?.('draw')
      setScores(s => ({ ...s, draws: s.draws + 1 }))
      return
    }

    setIsPlayerTurn(false)
  }, [board, isPlayerTurn, gameStatus, onGameEnd])

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
        onGameEnd?.('loss')
        setScores(s => ({ ...s, o: s.o + 1 }))
        return
      }
      if (isBoardFull(newBoard)) {
        sfx.play('draw')
        setGameStatus('draw')
        onGameEnd?.('draw')
        setScores(s => ({ ...s, draws: s.draws + 1 }))
        return
      }

      setIsPlayerTurn(true)
    }, 300)

    return () => clearTimeout(timer)
  }, [isPlayerTurn, gameStatus, board, difficulty, onGameEnd])

  const handlePlayAgain = useCallback(() => {
    setBoard(createBoard())
    setWinResult(null)
    setGameStatus('playing')
    setIsPlayerTurn(true)
    music.start()
    clear()
  }, [music, clear])

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
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play"><HelpCircle className="w-4 h-4 text-blue-400" /></button>
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
      {showHelp && <TicTacToeHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Multiplayer race wrapper ─────────────────────────────────────────
function TicTacToeRaceWrapper({ roomId, onLeave }: { roomId: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, opponentLevelUp, broadcastState, reportFinish, leaveRoom } = useRaceMode(roomId, 'first_to_win')
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
        onBackToLobby={onLeave}
        onLeaveGame={leaveRoom}
      />
      <TicTacToeSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} />
    </div>
  )
}

export default function TicTacToe() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'tic-tac-toe',
        gameName: 'Tic Tac Toe',
        modes: ['vs', 'first_to_win'],
        maxPlayers: 2,
        modeDescriptions: { first_to_win: 'First to beat the AI wins' },
      }}
      renderSinglePlayer={() => <TicTacToeSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, _roomConfig, onLeave) =>
        mode === 'vs'
          ? <TicTacToeMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
          : <TicTacToeRaceWrapper roomId={roomId} onLeave={onLeave} />
      }
    />
  )
}
