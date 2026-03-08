/**
 * Spoons — grab a spoon before they run out!
 *
 * 3 players (1 human + 2 AI) pass cards trying to collect 4 of a kind.
 * When someone does, everyone races to grab a spoon.
 * Last player without a spoon gets a letter. Spell SPOONS and you're out!
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
import { MusicToggle } from '../../MusicToggle'
import {
  createSpoonsGame,
  drawCard,
  discardCard,
  grabSpoon,
  newRound,
  aiDiscard,
  getAiGrabDelays,
  type SpoonsState,
} from './spoonsEngine'

interface SavedState {
  gameState: SpoonsState
  gameStatus: GameStatus
}

const SPOONS_WORD = 'SPOONS'

export default function Spoons() {
  const { load, save, clear } = useGameState<SavedState>('spoons')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('spoons'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('spoons')

  const [gameState, setGameState] = useState<SpoonsState>(
    () => saved?.gameState ?? createSpoonsGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  // Persist state
  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost' && gameStatus !== 'draw') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Detect game over
  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const human = gameState.players[0]
      setGameStatus(human.eliminated ? 'lost' : 'won')
      clear()
    }
  }, [gameState, clear])

  // AI drawing + discarding
  useEffect(() => {
    if (gameState.phase !== 'drawing' && gameState.phase !== 'discarding') return
    if (gameState.players[gameState.currentPlayer]?.isHuman) return
    if (gameStatus !== 'playing') return

    const timer = setTimeout(() => {
      setGameState(prev => {
        if (prev.phase === 'drawing') {
          const afterDraw = drawCard(prev)
          // AI immediately discards
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
  }, [gameState.phase, gameState.currentPlayer, gameStatus, sfx])

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
  }, [gameState.phase, gameState.spoonGrabber, gameStatus, sfx])

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

  // New game
  const handleNewGame = useCallback(() => {
    setGameState(createSpoonsGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const humanPlayer = gameState.players[0]
  const humanIsCurrentAndDrawing = gameState.phase === 'drawing' && gameState.currentPlayer === 0
  const humanIsCurrentAndDiscarding = gameState.phase === 'discarding' && gameState.currentPlayer === 0
  const canGrabSpoon = gameState.phase === 'spoonGrab' && !humanPlayer.grabbedSpoon && !humanPlayer.eliminated

  const controls = (
    <div className="flex items-center justify-between text-xs w-full">
      <span className="text-slate-400">Round {gameState.roundNumber}</span>
      <MusicToggle music={music} sfx={sfx} />
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
        {(gameStatus === 'won' || gameStatus === 'lost') && (
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
    </GameLayout>
  )
}
