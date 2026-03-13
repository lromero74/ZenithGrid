/**
 * Spoons — grab a spoon before they run out!
 * Contributed by Shantina Jackson-Romero.
 *
 * 3 players (1 human + 2 AI) pass cards trying to collect 4 of a kind.
 * When someone does, everyone races to grab a spoon.
 * Last player without a spoon gets a letter. Spell SPOONS and you're out!
 *
 * Two modes:
 *   Turn-based — sequential draw/discard (classic digital adaptation)
 *   Real-time  — all players act simultaneously with human-modeled AI timing
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SIZE_MINI } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { HelpCircle, X } from 'lucide-react'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import {
  createSpoonsGame,
  drawCard,
  discardCard,
  grabSpoon,
  newRound,
  aiDiscard,
  getAiGrabDelays,
  type SpoonsState,
  type GameMode,
  type AiDifficulty,
} from './spoonsEngine'

interface SavedState {
  gameState: SpoonsState
  gameStatus: GameStatus
}

const SPOONS_WORD = 'SPOONS'

// ── Mode selection screen ───────────────────────────────────────────

function ModeSelect({ onStart }: { onStart: (mode: GameMode, difficulty: AiDifficulty) => void }) {
  const [mode, setMode] = useState<GameMode>('turn-based')
  const [difficulty, setDifficulty] = useState<AiDifficulty>('normal')

  return (
    <div className="flex flex-col items-center gap-6 py-4">
      {/* Mode selection */}
      <div className="text-center">
        <h3 className="text-sm font-medium text-slate-300 mb-3 uppercase tracking-wider">Game Mode</h3>
        <div className="flex gap-2">
          <button
            onClick={() => setMode('turn-based')}
            className={`px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
              mode === 'turn-based'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/40'
                : 'bg-slate-700/60 text-slate-400 hover:bg-slate-700'
            }`}
          >
            Turn-Based
          </button>
          <button
            onClick={() => setMode('real-time')}
            className={`px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
              mode === 'real-time'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/40'
                : 'bg-slate-700/60 text-slate-400 hover:bg-slate-700'
            }`}
          >
            Real-Time
          </button>
        </div>
        <p className="text-xs text-slate-500 mt-2 max-w-xs">
          {mode === 'turn-based'
            ? 'Players take turns drawing and discarding cards.'
            : 'All players act simultaneously — be quick!'}
        </p>
      </div>

      {/* Difficulty selection */}
      <div className="text-center">
        <h3 className="text-sm font-medium text-slate-300 mb-3 uppercase tracking-wider">AI Difficulty</h3>
        <div className="flex gap-2">
          {(['easy', 'normal', 'adept'] as const).map(d => (
            <button
              key={d}
              onClick={() => setDifficulty(d)}
              className={`px-4 py-2.5 rounded-lg text-sm font-medium transition-all capitalize ${
                difficulty === d
                  ? d === 'easy' ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/40'
                    : d === 'normal' ? 'bg-amber-600 text-white shadow-lg shadow-amber-900/40'
                    : 'bg-red-600 text-white shadow-lg shadow-red-900/40'
                  : 'bg-slate-700/60 text-slate-400 hover:bg-slate-700'
              }`}
            >
              {d}
            </button>
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-2 max-w-xs">
          {difficulty === 'easy' ? 'AI reacts like an average human — room to breathe.'
            : difficulty === 'normal' ? 'AI is competent — occasionally catches you off guard.'
            : 'AI has fast reflexes — top 10% reaction speed.'}
        </p>
      </div>

      {/* Start button */}
      <button
        onClick={() => onStart(mode, difficulty)}
        className="mt-2 px-10 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl
          text-lg font-bold transition-all active:scale-95 shadow-lg shadow-emerald-900/50"
      >
        Deal Cards
      </button>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────

// ── Help modal ──────────────────────────────────────────────────────
function SpoonsHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Spoons</h2>

        <Sec title="Goal">
          <p>Collect four of a kind, then grab a spoon before everyone else. Last player without a spoon gets a letter. Spell <B>S-P-O-O-N-S</B> and you're eliminated!</p>
        </Sec>

        <Sec title="Gameplay">
          <ul className="space-y-1">
            <Li>Each player holds <B>4 cards</B>. Cards are passed around the table.</Li>
            <Li>Draw a card, decide to keep or discard. You must always have exactly 4.</Li>
            <Li>When someone gets <B>four of a kind</B>, they grab a spoon.</Li>
            <Li>Once any spoon is grabbed, everyone races to grab the remaining spoons.</Li>
            <Li>There's always one fewer spoon than players — someone gets a letter!</Li>
          </ul>
        </Sec>

        <Sec title="Game Modes">
          <ul className="space-y-1">
            <Li><B>Turn-based</B> — Classic sequential draw/discard. Strategic and thoughtful.</Li>
            <Li><B>Real-time</B> — Simultaneous card passing. Fast and frantic!</Li>
          </ul>
        </Sec>

        <Sec title="Elimination">
          <ul className="space-y-1">
            <Li>Each round the loser gains a letter: S → P → O → O → N → S.</Li>
            <Li>Spell SPOONS and you're out. Last player standing wins!</Li>
          </ul>
        </Sec>

        <Sec title="Strategy Tips">
          <ul className="space-y-1">
            <Li>Focus on collecting one rank — don't spread too thin.</Li>
            <Li>Watch the spoon area closely — you might miss a grab!</Li>
            <Li>In real-time mode, speed is everything.</Li>
          </ul>
        </Sec>
      </div>
    </div>
  )
}

function SpoonsSinglePlayer({ onGameEnd, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss') => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<SavedState>('spoons')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('spoons'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('spoons')

  const [showHelp, setShowHelp] = useState(false)
  const [showModeSelect, setShowModeSelect] = useState<boolean>(() => {
    const s = saved?.gameState
    return !(s && s.mode && s.difficulty)
  })
  const [gameState, setGameState] = useState<SpoonsState>(
    () => {
      const s = saved?.gameState
      if (s && s.mode && s.difficulty) return s
      return createSpoonsGame()
    }
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  // Persist state
  useEffect(() => {
    if (showModeSelect) return
    if (gameStatus !== 'won' && gameStatus !== 'lost' && gameStatus !== 'draw') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Detect game over
  useEffect(() => {
    if (showModeSelect) return
    if (gameState.phase === 'gameOver') {
      const human = gameState.players[0]
      const result = human.eliminated ? 'lost' : 'won'
      setGameStatus(result)
      onGameEnd?.(human.eliminated ? 'loss' : 'win')
      clear()
    }
  }, [gameState, clear, onGameEnd])

  // ── Turn-based AI: draw + discard ─────────────────────────────────
  useEffect(() => {
    if (showModeSelect) return
    if (gameState.mode !== 'turn-based') return
    if (gameState.phase !== 'drawing' && gameState.phase !== 'discarding') return
    if (gameState.players[gameState.currentPlayer]?.isHuman) return
    if (gameStatus !== 'playing') return

    const timer = setTimeout(() => {
      setGameState(prev => {
        if (prev.phase === 'drawing') {
          const afterDraw = drawCard(prev)
          const idx = aiDiscard(afterDraw.players[afterDraw.currentPlayer].hand)
          sfx.play('discard')
          return discardCard(afterDraw, idx)
        }
        if (prev.phase === 'discarding') {
          const idx = aiDiscard(prev.players[prev.currentPlayer].hand)
          sfx.play('discard')
          return discardCard(prev, idx)
        }
        return prev
      })
    }, 300)
    return () => clearTimeout(timer)
  }, [gameState.phase, gameState.currentPlayer, gameState.mode, gameStatus, sfx, showModeSelect])

  // ── Real-time AI: draw + discard with human-modeled delays ────────
  useEffect(() => {
    if (showModeSelect) return
    if (gameState.mode !== 'real-time') return
    if (gameState.phase !== 'drawing' && gameState.phase !== 'discarding') return
    if (gameState.players[gameState.currentPlayer]?.isHuman) return
    if (gameStatus !== 'playing') return

    const player = gameState.players[gameState.currentPlayer]
    const delay = player.cardEvalDelay || 500

    const timer = setTimeout(() => {
      setGameState(prev => {
        if (prev.phase === 'drawing') {
          const afterDraw = drawCard(prev)
          const idx = aiDiscard(afterDraw.players[afterDraw.currentPlayer].hand)
          sfx.play('discard')
          return discardCard(afterDraw, idx)
        }
        if (prev.phase === 'discarding') {
          const idx = aiDiscard(prev.players[prev.currentPlayer].hand)
          sfx.play('discard')
          return discardCard(prev, idx)
        }
        return prev
      })
    }, delay)
    return () => clearTimeout(timer)
  }, [gameState.phase, gameState.currentPlayer, gameState.mode, gameStatus, sfx, showModeSelect])

  // Auto-draw for human when it's their turn (dealer draws from pile)
  const handleDraw = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('play')
    setGameState(prev => drawCard(prev))
  }, [music, sfx])

  // Human discards a card
  const handleDiscard = useCallback((cardIndex: number) => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('discard')
    setGameState(prev => discardCard(prev, cardIndex))
  }, [music, sfx])

  // AI spoon grab timers
  useEffect(() => {
    if (showModeSelect) return
    if (gameState.phase !== 'spoonGrab') return
    if (gameStatus !== 'playing') return

    const aiGrabs = getAiGrabDelays(gameState)
    const timers = aiGrabs.map(({ playerIndex, delay }) =>
      setTimeout(() => {
        sfx.play('grab')
        setGameState(prev => grabSpoon(prev, playerIndex))
      }, delay)
    )
    return () => timers.forEach(clearTimeout)
  }, [gameState.phase, gameState.spoonGrabber, gameStatus, sfx, showModeSelect])

  // Human grabs spoon
  const handleGrabSpoon = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('grab')
    setGameState(prev => grabSpoon(prev, 0))
  }, [music, sfx])

  // Start next round
  const handleNextRound = useCallback(() => {
    setGameState(prev => newRound(prev))
  }, [])

  // New game (back to mode select)
  const handleNewGame = useCallback(() => {
    setShowModeSelect(true)
    setGameStatus('playing')
    clear()
  }, [clear])

  // Start game from mode select
  const handleStart = useCallback((mode: GameMode, difficulty: AiDifficulty) => {
    music.init()
    sfx.init()
    music.start()
    setGameState(createSpoonsGame(mode, difficulty))
    setGameStatus('playing')
    setShowModeSelect(false)
  }, [music, sfx])

  // ── Mode selection screen ─────────────────────────────────────────
  if (showModeSelect) {
    return (
      <GameLayout title="Spoons" controls={<MusicToggle music={music} sfx={sfx} />}>
        <ModeSelect onStart={handleStart} />
      </GameLayout>
    )
  }

  // ── Game screen ───────────────────────────────────────────────────
  const humanPlayer = gameState.players[0]
  const humanIsCurrentAndDrawing = gameState.phase === 'drawing' && gameState.currentPlayer === 0
  const humanIsCurrentAndDiscarding = gameState.phase === 'discarding' && gameState.currentPlayer === 0
  const canGrabSpoon = gameState.phase === 'spoonGrab' && !humanPlayer.grabbedSpoon && !humanPlayer.eliminated

  const difficultyLabel = gameState.difficulty === 'easy' ? 'Easy' : gameState.difficulty === 'normal' ? 'Normal' : 'Adept'
  const modeLabel = gameState.mode === 'turn-based' ? 'Turn' : 'RT'

  const controls = (
    <div className="flex items-center justify-between text-xs w-full">
      <div className="flex items-center gap-2">
        <button
          onClick={handleNewGame}
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          New Game
        </button>
        <span className="text-slate-500">{modeLabel} · {difficultyLabel}</span>
        <span className="text-slate-400">Rd {gameState.roundNumber}</span>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play">
          <HelpCircle className="w-4 h-4 text-blue-400" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Spoons" controls={controls}>
      <div className="flex flex-col items-center w-full max-w-lg space-y-3">
        {/* AI players */}
        <div className="flex justify-center gap-6 w-full">
          {gameState.players.slice(1).map((player, i) => (
            <div key={i + 1} className={`text-center ${player.eliminated ? 'opacity-30' : ''}`}>
              <div className="flex items-center justify-center gap-1 mb-1">
                <span className="text-xs font-medium text-slate-300">{player.name}</span>
                {player.grabbedSpoon && gameState.phase === 'spoonGrab' && (
                  <span className="text-xs">🥄</span>
                )}
              </div>
              {/* Letter display */}
              <div className="flex justify-center gap-0.5 mb-1.5">
                {SPOONS_WORD.split('').map((letter, li) => (
                  <span
                    key={li}
                    className={`text-[0.6rem] font-mono w-3 text-center ${
                      li < player.letters.length ? 'text-red-400 font-bold' : 'text-slate-700'
                    }`}
                  >
                    {letter}
                  </span>
                ))}
              </div>
              {/* AI cards */}
              <div className="flex justify-center gap-0.5">
                {player.hand.map((_, ci) => (
                  <div key={ci} className={CARD_SIZE_MINI}>
                    <CardBack />
                  </div>
                ))}
              </div>
              {/* Turn indicator */}
              {gameState.currentPlayer === i + 1 && gameState.phase !== 'spoonGrab' &&
                gameState.phase !== 'roundOver' && gameState.phase !== 'gameOver' && (
                <div className="w-1.5 h-1.5 bg-blue-400 rounded-full mx-auto mt-1 animate-pulse" />
              )}
            </div>
          ))}
        </div>

        {/* Spoons in center */}
        <div className="flex items-center justify-center gap-3 py-2">
          {Array.from({ length: gameState.spoonsRemaining }).map((_, i) => (
            <span key={i} className="text-2xl sm:text-3xl">🥄</span>
          ))}
          {gameState.spoonsRemaining === 0 && gameState.phase === 'spoonGrab' && (
            <span className="text-slate-500 text-sm">No spoons left!</span>
          )}
        </div>

        {/* Grab spoon button */}
        {canGrabSpoon && (
          <button
            onClick={handleGrabSpoon}
            className="px-8 py-3 bg-red-600 hover:bg-red-500 text-white rounded-xl
              text-lg font-bold transition-all active:scale-90 animate-bounce shadow-lg shadow-red-900/50"
          >
            GRAB SPOON!
          </button>
        )}

        {/* Message */}
        <p className="text-sm text-white font-medium text-center min-h-[1.25rem]">
          {gameState.message}
        </p>

        {/* Draw button for human (when dealer) */}
        {humanIsCurrentAndDrawing && (
          <button
            onClick={handleDraw}
            className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg
              text-sm font-medium transition-colors active:scale-95"
          >
            Draw Card
          </button>
        )}

        {/* Next round button */}
        {gameState.phase === 'roundOver' && (
          <button
            onClick={handleNextRound}
            className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg
              text-sm font-medium transition-colors active:scale-95"
          >
            Next Round
          </button>
        )}

        {/* Human's hand */}
        <div className="text-center w-full">
          {/* Letter display */}
          <div className="flex justify-center gap-0.5 mb-2">
            {SPOONS_WORD.split('').map((letter, li) => (
              <span
                key={li}
                className={`text-xs font-mono w-4 text-center ${
                  li < humanPlayer.letters.length ? 'text-red-400 font-bold' : 'text-slate-600'
                }`}
              >
                {letter}
              </span>
            ))}
          </div>
          <div className="flex justify-center gap-1.5">
            {humanPlayer.hand.map((card, i) => (
              <button
                key={`${card.suit}-${card.rank}-${i}`}
                onClick={() => humanIsCurrentAndDiscarding && handleDiscard(i)}
                disabled={!humanIsCurrentAndDiscarding}
                className={`${CARD_SIZE} transition-all ${
                  humanIsCurrentAndDiscarding
                    ? 'hover:-translate-y-1 cursor-pointer hover:ring-2 hover:ring-red-400 rounded-lg'
                    : ''
                }`}
              >
                <CardFace card={card} />
              </button>
            ))}
          </div>
          <div className="flex items-center justify-center gap-1 mt-1">
            <span className="text-xs text-slate-400">{humanPlayer.name}</span>
            {humanPlayer.grabbedSpoon && gameState.phase === 'spoonGrab' && (
              <span className="text-xs">🥄</span>
            )}
          </div>
          {humanIsCurrentAndDiscarding && (
            <p className="text-xs text-amber-400 mt-1">Tap a card to discard it</p>
          )}
        </div>

        {/* Draw pile info */}
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>Draw pile: {gameState.drawPile.length}</span>
          <span>|</span>
          <span>Discard: {gameState.discardPile.length}</span>
        </div>

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost') && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            score={gameState.roundNumber}
            message={gameState.message}
            onPlayAgain={handleNewGame}
            playAgainText="New Game"
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <SpoonsHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-win against opponent) ──────────────────

function SpoonsRaceWrapper({ roomId, onLeave }: { roomId: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, opponentLevelUp, reportFinish, leaveRoom } = useRaceMode(roomId, 'first_to_win')
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
        onDismiss={onLeave}
        onBackToLobby={onLeave}
        onLeaveGame={leaveRoom}
      />
      <SpoonsSinglePlayer onGameEnd={handleGameEnd} isMultiplayer />
    </div>
  )
}

export default function Spoons() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'spoons',
        gameName: 'Spoons',
        modes: ['first_to_win'],
        maxPlayers: 2,
        hasDifficulty: false,
        modeDescriptions: { first_to_win: 'First to beat the AI wins' },
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <SpoonsSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, _roomConfig, onLeave) =>
        <SpoonsRaceWrapper roomId={roomId} onLeave={onLeave} />
      }
    />
  )
}
