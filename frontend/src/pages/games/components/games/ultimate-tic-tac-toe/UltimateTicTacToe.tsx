/**
 * Ultimate Tic-Tac-Toe — 3x3 grid of tic-tac-toe boards.
 *
 * Features: active board highlighting, AI opponent,
 * meta-board progress, undo support.
 */

import { useState, useCallback, useEffect, useRef, useMemo} from 'react'
import { HelpCircle, Undo2, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameState } from '../../../hooks/useGameState'
import {
  createBoards, createMetaBoard, makeMove, getValidMoves, getAIMove,
  type SubBoard as SubBoardType, type MetaCell, type Player,
} from './ultimateEngine'
import { SubBoard } from './SubBoard'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

interface UTTTGameState {
  boards: SubBoardType[]
  meta: MetaCell[]
  activeBoard: number | null
  currentPlayer: Player
}

interface UTTTSaved {
  state: UTTTGameState
  gameStatus: GameStatus
}

function initialState(): UTTTGameState {
  return {
    boards: createBoards(),
    meta: createMetaBoard(),
    activeBoard: null,
    currentPlayer: 'X',
  }
}

function UTTTHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Ultimate Tic-Tac-Toe</h2>
        <Sec title="Goal"><p>Win three <B>sub-boards</B> in a row on the 3×3 meta-board to win the game.</p></Sec>
        <Sec title="The Twist"><ul className="space-y-1">
          <Li>The board is a 3×3 grid of <B>9 smaller tic-tac-toe boards</B>.</Li>
          <Li>Where you play in a sub-board determines which sub-board your opponent must play in next.</Li>
          <Li>For example: if you play in the top-right cell of any sub-board, your opponent must play in the <B>top-right sub-board</B>.</Li>
          <Li>If the target sub-board is already won or full, your opponent can play in <B>any open sub-board</B>.</Li>
        </ul></Sec>
        <Sec title="Winning a Sub-Board"><p>Win a sub-board by getting three in a row within it — just like regular tic-tac-toe. The sub-board is then claimed by that player.</p></Sec>
        <Sec title="Winning the Game"><p>Win three sub-boards in a row (horizontally, vertically, or diagonally) on the meta-board.</p></Sec>
        <Sec title="Controls"><ul className="space-y-1">
          <Li><B>Click</B> an empty cell in a highlighted (valid) sub-board.</Li>
          <Li><B>Undo</B> — Reverse the last move.</Li>
          <Li>Valid sub-boards are highlighted with a colored border.</Li>
        </ul></Sec>
        <Sec title="Strategy Tips"><ul className="space-y-1">
          <Li>Think about where your move sends the opponent — avoid giving them a free choice.</Li>
          <Li>Winning a corner sub-board is powerful — it contributes to multiple lines.</Li>
          <Li>Sometimes it's better to sacrifice a sub-board to control where the opponent plays.</Li>
        </ul></Sec>
      </div>
    </div>
  )
}

function UltimateTicTacToeSinglePlayer({ onGameEnd, onStateChange: _onStateChange }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void } = {}) {
  const { load, save, clear } = useGameState<UTTTSaved>('ultimate-tic-tac-toe')
  const savedData = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('ultimate-tic-tac-toe'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('ultimate-tic-tac-toe')
  const [showHelp, setShowHelp] = useState(false)

  const [state, setState] = useState<UTTTGameState>(() => savedData?.state ?? initialState())
  const [gameStatus, setGameStatus] = useState<GameStatus>(savedData?.gameStatus ?? 'playing')
  const [history, setHistory] = useState<UTTTGameState[]>([])
  const aiThinking = useRef(false)

  // Persist state
  useEffect(() => {
    save({ state, gameStatus })
  }, [state, gameStatus, save])

  const handleCellClick = useCallback((boardIndex: number, cellIndex: number) => {
    if (gameStatus !== 'playing' || state.currentPlayer !== 'X' || aiThinking.current) return

    music.init()
    sfx.init()
    music.start()

    const validMoves = getValidMoves(state.boards, state.meta, state.activeBoard)
    if (!validMoves.some(([b, c]) => b === boardIndex && c === cellIndex)) return

    setHistory(prev => [...prev.slice(-20), state])
    sfx.play('place')
    const result = makeMove(state.boards, state.meta, boardIndex, cellIndex, 'X')

    // Check if a sub-board was just won
    if (result.meta.some((m, i) => m !== null && state.meta[i] === null)) {
      sfx.play('board_won')
    }

    if (result.winner) {
      sfx.play('win')
      setState({ boards: result.boards, meta: result.meta, activeBoard: null, currentPlayer: 'X' })
      setGameStatus('won')
      onGameEnd?.('win')
      return
    }
    if (result.isDraw) {
      setState({ boards: result.boards, meta: result.meta, activeBoard: null, currentPlayer: 'X' })
      setGameStatus('draw')
      onGameEnd?.('draw')
      return
    }

    setState({
      boards: result.boards,
      meta: result.meta,
      activeBoard: result.nextActiveBoard,
      currentPlayer: 'O',
    })
  }, [state, gameStatus, onGameEnd])

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
        onGameEnd?.('loss')
      } else if (result.isDraw) {
        setState({ boards: result.boards, meta: result.meta, activeBoard: null, currentPlayer: 'O' })
        setGameStatus('draw')
        onGameEnd?.('draw')
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
  }, [state, gameStatus, onGameEnd])

  const handleUndo = useCallback(() => {
    if (history.length === 0 || aiThinking.current) return
    setState(history[history.length - 1])
    setHistory(h => h.slice(0, -1))
  }, [history])

  const handleNewGame = useCallback(() => {
    setState(initialState())
    setGameStatus('playing')
    setHistory([])
    music.start()
    clear()
  }, [music, clear])

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
      <div className="flex items-center gap-2">
        <p className="text-xs text-slate-400">
          {gameStatus === 'playing' && (state.currentPlayer === 'X' ? 'Your turn (X)' : 'AI thinking...')}
        </p>
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play"><HelpCircle className="w-4 h-4 text-blue-400" /></button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
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
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <UTTTHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Multiplayer race wrapper ─────────────────────────────────────────
function UltimateTicTacToeRaceWrapper({ roomId, difficulty: _difficulty }: { roomId: string; difficulty?: string }) {
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
      <UltimateTicTacToeSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} />
    </div>
  )
}

export default function UltimateTicTacToe() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'ultimate-tic-tac-toe',
        gameName: 'Ultimate Tic Tac Toe',
        modes: ['race'],
        maxPlayers: 2,
        hasDifficulty: true,
        raceDescription: 'First to beat the AI wins',
      }}
      renderSinglePlayer={() => <UltimateTicTacToeSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig) => (
        <UltimateTicTacToeRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} />
      )}
    />
  )
}
