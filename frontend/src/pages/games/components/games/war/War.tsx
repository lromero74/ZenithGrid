/**
 * War — 2-player card game. Flip cards, higher rank wins.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import {
  createWarGame,
  flipCards,
  resolveCompare,
  resolveWar,
  type WarState,
} from './WarEngine'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import { WarMultiplayer } from './WarMultiplayer'

interface SavedState {
  gameState: WarState
  gameStatus: GameStatus
}

function WarHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play War</h2>
        <Sec title="Goal"><p>Capture all 52 cards from your opponent.</p></Sec>
        <Sec title="How to Play"><ul className="space-y-1">
          <Li>Both players flip their top card simultaneously.</Li>
          <Li>The <B>higher card</B> wins — the winner takes both cards.</Li>
          <Li>Ace is the highest card, 2 is the lowest.</Li>
        </ul></Sec>
        <Sec title="War!"><ul className="space-y-1">
          <Li>When both cards are the <B>same rank</B>, it's <B>War!</B></Li>
          <Li>Each player places cards face-down, then flips one more card.</Li>
          <Li>The higher new card wins <B>all</B> the cards from the war.</Li>
          <Li>If it's a tie again, war continues!</Li>
        </ul></Sec>
        <Sec title="Controls"><ul className="space-y-1">
          <Li><B>Click your deck</B> or press <B>Space</B> to flip.</Li>
          <Li><B>Auto mode</B> — Plays automatically so you can watch.</Li>
        </ul></Sec>
      </div>
    </div>
  )
}

function WarSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<SavedState>('war')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('war'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('war')
  const [showHelp, setShowHelp] = useState(false)

  const [gameState, setGameState] = useState<WarState>(
    () => saved?.gameState ?? createWarGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [autoPlay, setAutoPlay] = useState(false)
  const autoPlayRef = useRef(autoPlay)
  autoPlayRef.current = autoPlay

  // Persist state
  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost' && gameStatus !== 'draw') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Detect game over
  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const pCount = gameState.playerDeck.length
      const aCount = gameState.aiDeck.length
      if (pCount > aCount) {
        setGameStatus('won')
        onGameEnd?.('win')
      } else if (aCount > pCount) {
        setGameStatus('lost')
        onGameEnd?.('loss')
      } else {
        setGameStatus('draw')
        onGameEnd?.('draw')
      }
      clear()
      setAutoPlay(false)
    }
  }, [gameState, clear, onGameEnd])

  // Auto-advance: compare → resolve, war → resolve
  useEffect(() => {
    if (gameState.phase === 'compare') {
      sfx.play('flip')
      const timer = setTimeout(() => {
        setGameState(prev => {
          const next = resolveCompare(prev)
          if (next.phase === 'ready') sfx.play('win_round')
          if (next.phase === 'war') sfx.play('war')
          return next
        })
      }, 800)
      return () => clearTimeout(timer)
    }
    if (gameState.phase === 'war') {
      const timer = setTimeout(() => {
        setGameState(prev => {
          const next = resolveWar(prev)
          sfx.play('win_round')
          return next
        })
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [gameState.phase])

  // Auto-play: auto-flip when in ready phase
  useEffect(() => {
    if (autoPlayRef.current && gameState.phase === 'ready' && gameStatus === 'playing') {
      const timer = setTimeout(() => {
        if (autoPlayRef.current) {
          setGameState(prev => flipCards(prev))
        }
      }, 600)
      return () => clearTimeout(timer)
    }
  }, [gameState.phase, gameState.round, gameStatus])

  const handleFlip = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('flip')
    setGameState(prev => flipCards(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createWarGame())
    setGameStatus('playing')
    setAutoPlay(false)
    clear()
  }, [clear])

  const toggleAutoPlay = useCallback(() => {
    setAutoPlay(prev => !prev)
  }, [])

  const controls = (
    <div className="flex items-center justify-between text-xs w-full">
      <span className="text-slate-400">Round {gameState.round}/{gameState.maxRounds}</span>
      <button
        onClick={toggleAutoPlay}
        className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
          autoPlay ? 'bg-amber-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
        }`}
      >
        {autoPlay ? 'Auto: ON' : 'Auto: OFF'}
      </button>
      <div className="flex items-center gap-2">
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play"><HelpCircle className="w-4 h-4 text-blue-400" /></button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="War" controls={controls}>
      <div className="flex flex-col items-center w-full max-w-sm space-y-4">
        {/* AI deck */}
        <div className="text-center">
          <span className="text-xs text-slate-400 mb-1 block">AI ({gameState.aiDeck.length} cards)</span>
          <div className="flex justify-center">
            {gameState.aiDeck.length > 0 ? (
              <div className={`${CARD_SIZE} relative`}>
                <CardBack />
                {gameState.aiDeck.length > 1 && (
                  <div className={`absolute -top-0.5 -left-0.5 ${CARD_SIZE} -z-10`}>
                    <CardBack />
                  </div>
                )}
              </div>
            ) : (
              <div className={`${CARD_SIZE} border border-dashed border-slate-600 rounded-lg`} />
            )}
          </div>
        </div>

        {/* Battle area */}
        <div className="flex items-center gap-6 py-3">
          {/* Player's flipped card */}
          <div className={CARD_SIZE}>
            {gameState.playerCard ? (
              <CardFace card={gameState.playerCard} />
            ) : (
              <div className="w-full h-full border border-dashed border-slate-600 rounded-lg flex items-center justify-center">
                <span className="text-[0.5rem] text-slate-500">You</span>
              </div>
            )}
          </div>

          {/* War pile indicator */}
          {gameState.warPile.length > 0 && (
            <div className="flex flex-col items-center gap-1">
              <div className="flex gap-0.5">
                {gameState.warPile.slice(0, 3).map((_, i) => (
                  <div key={i} className="w-6 h-9">
                    <CardBack />
                  </div>
                ))}
              </div>
              <span className="text-[0.6rem] text-amber-400">{gameState.warPile.length} cards</span>
            </div>
          )}

          {/* VS indicator */}
          {gameState.warPile.length === 0 && (
            <span className="text-lg font-bold text-slate-500">VS</span>
          )}

          {/* AI's flipped card */}
          <div className={CARD_SIZE}>
            {gameState.aiCard ? (
              <CardFace card={gameState.aiCard} />
            ) : (
              <div className="w-full h-full border border-dashed border-slate-600 rounded-lg flex items-center justify-center">
                <span className="text-[0.5rem] text-slate-500">AI</span>
              </div>
            )}
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center min-h-[1.25rem]">
          {gameState.message}
        </p>

        {/* Flip button */}
        {gameState.phase === 'ready' && gameStatus === 'playing' && !autoPlay && (
          <button
            onClick={handleFlip}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors active:scale-95"
          >
            Flip!
          </button>
        )}

        {/* Player deck */}
        <div className="text-center">
          <div className="flex justify-center">
            {gameState.playerDeck.length > 0 ? (
              <div className={`${CARD_SIZE} relative`}>
                <CardBack />
                {gameState.playerDeck.length > 1 && (
                  <div className={`absolute -top-0.5 -left-0.5 ${CARD_SIZE} -z-10`}>
                    <CardBack />
                  </div>
                )}
              </div>
            ) : (
              <div className={`${CARD_SIZE} border border-dashed border-slate-600 rounded-lg`} />
            )}
          </div>
          <span className="text-xs text-slate-400 mt-1 block">You ({gameState.playerDeck.length} cards)</span>
        </div>

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            score={gameState.playerDeck.length}
            message={gameState.message}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <WarHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-win against AI) ─────────────────────────

function WarRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
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
      <WarSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function War() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'war',
        gameName: 'War',
        modes: ['vs', 'first_to_win'],
        maxPlayers: 2,
        hasDifficulty: false,
        modeDescriptions: { vs: 'Head-to-head card war', first_to_win: 'First to win the war wins' },
      }}
      renderSinglePlayer={() => <WarSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs'
          ? <WarMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
          : <WarRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
      }
    />
  )
}
