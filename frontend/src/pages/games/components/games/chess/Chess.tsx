/**
 * Chess game — classic chess against AI opponent.
 *
 * Features: AI with difficulty levels (minimax + alpha-beta pruning),
 * full rules (castling, en passant, promotion), check/checkmate/stalemate,
 * captured pieces display, score tracking, state persistence.
 */

import { useState, useCallback, useEffect, useRef, useMemo} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { DifficultySelector } from '../../DifficultySelector'
import {
  createBoard, getValidMoves, isInCheck, isCheckmate, isStalemate, isDraw,
  applyMove, getAIMove, getPieceSymbol,
  type ChessState, type Move, type PieceType,
} from './chessEngine'
import { ChessBoard } from './ChessBoard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus, Difficulty } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

// ── Help modal ───────────────────────────────────────────────────────

function ChessHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Chess</h2>

        {/* Goal */}
        <Section title="Goal">
          Checkmate your opponent&apos;s king. A king is in checkmate when it is
          under attack (in check) and has no legal move to escape.
        </Section>

        {/* Piece Movement */}
        <Section title="Piece Movement">
          <div className="space-y-3">
            <PieceInfo symbol="♔" name="King">
              Moves one square in any direction (horizontally, vertically, or
              diagonally). Cannot move into a square attacked by an opponent&apos;s piece.
            </PieceInfo>
            <PieceInfo symbol="♕" name="Queen">
              Moves any number of squares horizontally, vertically, or diagonally.
              The most powerful piece on the board.
            </PieceInfo>
            <PieceInfo symbol="♖" name="Rook">
              Moves any number of squares horizontally or vertically.
            </PieceInfo>
            <PieceInfo symbol="♗" name="Bishop">
              Moves any number of squares diagonally. Each bishop stays on its
              starting color for the entire game.
            </PieceInfo>
            <PieceInfo symbol="♘" name="Knight">
              Moves in an &quot;L&quot; shape: two squares in one direction and one
              square perpendicular. The only piece that can jump over other pieces.
            </PieceInfo>
            <PieceInfo symbol="♙" name="Pawn">
              Moves forward one square, or two squares from its starting position.
              Captures diagonally one square forward. Cannot move backward.
            </PieceInfo>
          </div>
        </Section>

        {/* Special Moves */}
        <Section title="Special Moves">
          <div className="space-y-3">
            <SpecialMove name="Castling">
              A combined king-and-rook move. The king moves two squares toward a rook,
              and the rook jumps to the other side of the king. Only allowed if neither
              piece has moved, the squares between them are empty, and the king is not
              in check and does not pass through or land on an attacked square.
            </SpecialMove>
            <SpecialMove name="En Passant">
              If a pawn advances two squares from its starting position and lands
              beside an opponent&apos;s pawn, the opponent can capture it as if it
              had only moved one square. This must be done on the very next move or
              the opportunity is lost.
            </SpecialMove>
            <SpecialMove name="Pawn Promotion">
              When a pawn reaches the opposite end of the board, it must be promoted
              to a queen, rook, bishop, or knight. A dialog will appear for you to
              choose the piece.
            </SpecialMove>
          </div>
        </Section>

        {/* Check, Checkmate, Stalemate */}
        <Section title="Check, Checkmate &amp; Draws">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Check</B> — your king is under attack. You must get out of check on your next move.</Li>
            <Li><B>Checkmate</B> — your king is in check and there is no legal move to escape. The game is over.</Li>
            <Li><B>Stalemate</B> — it is your turn but you have no legal moves and your king is not in check. The game is a draw.</Li>
            <Li><B>Fifty-move rule</B> — if 50 moves pass with no capture and no pawn move, the game is drawn.</Li>
            <Li><B>Threefold repetition</B> — if the same board position occurs three times, the game is drawn.</Li>
          </ul>
        </Section>

        {/* AI Opponent */}
        <Section title="AI Opponent">
          <ul className="space-y-1 text-slate-300">
            <Li>You play as <B>white</B> (bottom). The AI plays as <B>black</B> (top).</Li>
            <Li>Three difficulty levels control how far ahead the AI looks:</Li>
          </ul>
          <ul className="mt-1.5 ml-3 space-y-1 text-slate-300">
            <Li><B>Easy</B> — thinks 2 moves ahead.</Li>
            <Li><B>Medium</B> — thinks 3 moves ahead.</Li>
            <Li><B>Hard</B> — thinks 4 moves ahead (may take a moment to calculate).</Li>
          </ul>
          <p className="text-slate-400 text-[0.7rem] mt-1.5">
            The AI uses minimax search with alpha-beta pruning and evaluates piece
            values plus positional bonuses.
          </p>
        </Section>

        {/* Controls */}
        <Section title="Controls">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Click</B> one of your pieces to select it. Valid destination squares will be highlighted.</Li>
            <Li><B>Click</B> a highlighted square to move the selected piece there.</Li>
            <Li>Click a different one of your pieces to change your selection.</Li>
            <Li>Click any non-highlighted square to deselect.</Li>
            <Li>Use the <B>difficulty selector</B> to change the AI strength (starts a new game).</Li>
            <Li><B>New Game</B> resets the board.</Li>
          </ul>
        </Section>

        {/* Strategy Tips */}
        <Section title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li>Control the <B>center</B> of the board (d4, d5, e4, e5) with pawns and pieces early on.</Li>
            <Li>Develop your <B>knights and bishops</B> before moving the queen or advancing edge pawns.</Li>
            <Li><B>Castle early</B> to protect your king and connect your rooks.</Li>
            <Li>Avoid moving the same piece twice in the opening unless necessary.</Li>
            <Li>Keep an eye on <B>piece values</B>: Queen (9), Rook (5), Bishop (3), Knight (3), Pawn (1).</Li>
            <Li>Look for <B>forks</B> (one piece attacking two), <B>pins</B>, and <B>skewers</B> to win material.</Li>
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

function PieceInfo({ symbol, name, children }: { symbol: string; name: string; children: React.ReactNode }) {
  return (
    <div className="pl-3 border-l-2 border-slate-700">
      <div className="text-xs font-bold text-white mb-0.5">
        <span className="mr-1.5 text-sm">{symbol}</span>{name}
      </div>
      <div className="text-xs text-slate-400 leading-relaxed">{children}</div>
    </div>
  )
}

function SpecialMove({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="pl-3 border-l-2 border-slate-700">
      <div className="text-xs font-bold text-amber-400 mb-0.5">{name}</div>
      <div className="text-xs text-slate-400 leading-relaxed">{children}</div>
    </div>
  )
}

function Li({ children }: { children: React.ReactNode }) {
  return <li className="flex gap-1.5 text-xs"><span className="text-slate-600 mt-0.5">•</span><span>{children}</span></li>
}

function B({ children }: { children: React.ReactNode }) {
  return <span className="text-white font-medium">{children}</span>
}

// ── Constants ────────────────────────────────────────────────────────

const DIFFICULTY_DEPTH: Record<string, number> = {
  easy: 2, medium: 3, hard: 4,
}

interface ChessSavedState {
  chessState: ChessState
  gameStatus: GameStatus
  difficulty: Difficulty
  scores: { white: number; black: number; draw: number }
  isPlayerTurn: boolean
}

function ChessSinglePlayer({ onGameEnd, onStateChange: _onStateChange }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void } = {}) {
  const { load, save, clear } = useGameState<ChessSavedState>('chess')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('chess'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('chess')

  const [chessState, setChessState] = useState<ChessState>(saved?.chessState ?? createBoard)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedSquare, setSelectedSquare] = useState<[number, number] | null>(null)
  const [validMoves, setValidMoves] = useState<Move[]>([])
  const [lastMove, setLastMove] = useState<Move | null>(null)
  const [difficulty, setDifficulty] = useState<Difficulty>(saved?.difficulty ?? 'medium')
  const [scores, setScores] = useState(saved?.scores ?? { white: 0, black: 0, draw: 0 })
  const [isPlayerTurn, setIsPlayerTurn] = useState(saved?.isPlayerTurn ?? true)
  const [promotionMove, setPromotionMove] = useState<Move | null>(null)
  const [showHelp, setShowHelp] = useState(false)
  const aiThinking = useRef(false)

  // Persist state on changes
  useEffect(() => {
    save({ chessState, gameStatus, difficulty, scores, isPlayerTurn })
  }, [chessState, gameStatus, difficulty, scores, isPlayerTurn, save])

  const checkGameEnd = useCallback((state: ChessState) => {
    const nextPlayer = state.currentPlayer
    if (isCheckmate(state, nextPlayer)) {
      sfx.play('checkmate')
      if (nextPlayer === 'black') {
        setGameStatus('won')
        onGameEnd?.('win')
        setScores(s => ({ ...s, white: s.white + 1 }))
      } else {
        setGameStatus('lost')
        onGameEnd?.('loss')
        setScores(s => ({ ...s, black: s.black + 1 }))
      }
      return true
    }
    if (isStalemate(state, nextPlayer) || isDraw(state)) {
      setGameStatus('draw')
      onGameEnd?.('draw')
      setScores(s => ({ ...s, draw: s.draw + 1 }))
      return true
    }
    return false
  }, [onGameEnd])

  const handleSquareClick = useCallback((r: number, c: number) => {
    if (gameStatus !== 'playing' || !isPlayerTurn || aiThinking.current) return

    music.init()
    sfx.init()
    music.start()

    const piece = chessState.board[r][c]

    // If clicking on own piece, select it
    if (piece && piece.color === 'white') {
      const moves = getValidMoves(chessState, r, c)
      if (moves.length > 0) {
        setSelectedSquare([r, c])
        setValidMoves(moves)
      }
      return
    }

    // If a piece is selected and clicking on a valid target, make the move
    if (selectedSquare) {
      const move = validMoves.find(m => m.toRow === r && m.toCol === c)
      if (move) {
        // Check for pawn promotion
        const movingPiece = chessState.board[move.fromRow][move.fromCol]
        if (movingPiece?.type === 'pawn' && (move.toRow === 0 || move.toRow === 7) && !move.promotion) {
          // Show promotion dialog
          setPromotionMove(move)
          return
        }

        const newState = applyMove(chessState, move)
        if (chessState.board[r][c]) { sfx.play('capture') } else { sfx.play('move') }
        setChessState(newState)
        setLastMove(move)
        setSelectedSquare(null)
        setValidMoves([])

        if (!checkGameEnd(newState)) {
          if (isInCheck(newState, 'black')) { sfx.play('check') }
          setIsPlayerTurn(false)
        }
      } else {
        setSelectedSquare(null)
        setValidMoves([])
      }
    }
  }, [chessState, gameStatus, isPlayerTurn, selectedSquare, validMoves, checkGameEnd])

  const handlePromotion = useCallback((pieceType: PieceType) => {
    if (!promotionMove) return
    const move: Move = { ...promotionMove, promotion: pieceType }
    const newState = applyMove(chessState, move)
    sfx.play('move')
    setChessState(newState)
    setLastMove(move)
    setSelectedSquare(null)
    setValidMoves([])
    setPromotionMove(null)

    if (!checkGameEnd(newState)) {
      setIsPlayerTurn(false)
    }
  }, [chessState, promotionMove, checkGameEnd])

  // AI turn
  useEffect(() => {
    if (isPlayerTurn || gameStatus !== 'playing') return
    aiThinking.current = true

    const timer = setTimeout(() => {
      const depth = DIFFICULTY_DEPTH[difficulty] || 3
      const aiMove = getAIMove(chessState, depth)
      if (!aiMove) {
        // No moves available — check why
        if (isInCheck(chessState, 'black')) {
          setGameStatus('won')
          onGameEnd?.('win')
          setScores(s => ({ ...s, white: s.white + 1 }))
        } else {
          setGameStatus('draw')
          onGameEnd?.('draw')
          setScores(s => ({ ...s, draw: s.draw + 1 }))
        }
        aiThinking.current = false
        return
      }

      const newState = applyMove(chessState, aiMove)
      if (chessState.board[aiMove.toRow][aiMove.toCol]) { sfx.play('capture') } else { sfx.play('move') }
      setChessState(newState)
      setLastMove(aiMove)

      if (!checkGameEnd(newState)) {
        if (isInCheck(newState, 'white')) { sfx.play('check') }
        setIsPlayerTurn(true)
      }
      aiThinking.current = false
    }, 300)

    return () => clearTimeout(timer)
  }, [isPlayerTurn, gameStatus, chessState, difficulty, checkGameEnd])

  const handleNewGame = useCallback(() => {
    setChessState(createBoard())
    setGameStatus('playing')
    setSelectedSquare(null)
    setValidMoves([])
    setLastMove(null)
    setIsPlayerTurn(true)
    setPromotionMove(null)
    clear()
    music.start()
  }, [clear, music])

  const playerCheck = isPlayerTurn && isInCheck(chessState, 'white')
  const aiCheck = !isPlayerTurn && isInCheck(chessState, 'black')

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
        <span className="text-white">You: {scores.white}</span>
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
    <GameLayout title="Chess" controls={controls}>
      <div className="relative flex flex-col items-center space-y-2">
        {/* Captured by black (white pieces taken) */}
        <div className="flex gap-0.5 text-sm min-h-[20px] text-slate-400">
          {chessState.capturedPieces.black.map((type, i) => (
            <span key={i}>{getPieceSymbol({ type, color: 'white' })}</span>
          ))}
        </div>

        <p className="text-sm text-slate-400">
          {gameStatus === 'playing' && (
            isPlayerTurn
              ? `Your turn (white)${playerCheck ? ' — Check!' : ''}`
              : `AI thinking...${aiCheck ? ' — Check!' : ''}`
          )}
        </p>

        <ChessBoard
          state={chessState}
          selectedSquare={selectedSquare}
          validMoves={validMoves}
          onSquareClick={handleSquareClick}
          disabled={gameStatus !== 'playing' || !isPlayerTurn}
          lastMove={lastMove}
          inCheck={playerCheck || aiCheck}
        />

        {/* Captured by white (black pieces taken) */}
        <div className="flex gap-0.5 text-sm min-h-[20px] text-slate-400">
          {chessState.capturedPieces.white.map((type, i) => (
            <span key={i}>{getPieceSymbol({ type, color: 'black' })}</span>
          ))}
        </div>

        {/* Promotion modal */}
        {promotionMove && (
          <div className="absolute inset-0 bg-slate-900/70 flex items-center justify-center z-50 rounded-lg">
            <div className="bg-slate-800 border border-slate-600 rounded-lg p-4">
              <p className="text-white text-sm mb-2 text-center">Promote pawn to:</p>
              <div className="flex gap-2">
                {(['queen', 'rook', 'bishop', 'knight'] as PieceType[]).map(type => (
                  <button
                    key={type}
                    onClick={() => handlePromotion(type)}
                    className="w-12 h-12 bg-slate-700 hover:bg-slate-600 rounded-lg text-2xl flex items-center justify-center transition-colors"
                  >
                    {getPieceSymbol({ type, color: 'white' })}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

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
      {showHelp && <ChessHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Multiplayer race wrapper ─────────────────────────────────────────
function ChessRaceWrapper({ roomId, difficulty: _difficulty }: { roomId: string; difficulty?: string }) {
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
      <ChessSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} />
    </div>
  )
}

export default function Chess() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'chess',
        gameName: 'Chess',
        modes: ['race'],
        maxPlayers: 2,
        hasDifficulty: true,
        raceDescription: 'First to beat the AI wins',
      }}
      renderSinglePlayer={() => <ChessSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig) => (
        <ChessRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} />
      )}
    />
  )
}
