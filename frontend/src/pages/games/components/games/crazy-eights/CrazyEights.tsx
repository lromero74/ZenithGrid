/**
 * Crazy Eights — match rank or suit, 8s are wild.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import { SUITS, getSuitSymbol, type Suit } from '../../../utils/cardUtils'
import type { GameStatus, Difficulty } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import {
  createCrazyEightsGame,
  playCard,
  drawCard,
  chooseSuit,
  newRound,
  getHumanPlayableCards,
  type CrazyEightsState,
} from './crazyEightsEngine'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import { CrazyEightsMultiplayer } from './CrazyEightsMultiplayer'

interface SavedState {
  gameState: CrazyEightsState
  gameStatus: GameStatus
}

// ── Help modal ───────────────────────────────────────────────────────

function CrazyEightsHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Crazy Eights</h2>

        {/* Goal */}
        <Sec title="Goal">
          Be the first player to <B>empty your hand</B> each round and score
          points from the cards left in your opponents&apos; hands. The first
          player to reach <B>200 points</B> wins the game.
        </Sec>

        {/* Setup */}
        <Sec title="Setup">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>A standard <B>52-card deck</B> is used.</Li>
            <Li>With <B>2 players</B>, each is dealt <B>7 cards</B>. With
              3 or 4 players, each is dealt <B>5 cards</B>.</Li>
            <Li>One card is placed face-up to start the <B>discard pile</B>.
              The starting card is never an 8.</Li>
            <Li>The remaining cards form the <B>draw pile</B>.</Li>
          </ul>
        </Sec>

        {/* How to Play */}
        <Sec title="How to Play">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li>On your turn, play a card from your hand that matches the
              top discard by <B>suit</B> or <B>rank</B> -- or play an 8
              (wild).</li>
            <li>If you have no playable card, click the <B>draw pile</B> to
              draw. If the drawn card is playable, you may play it
              immediately.</li>
            <li>If the draw pile is empty, the discard pile (except the top
              card) is reshuffled to form a new draw pile.</li>
            <li>The round ends when any player empties their hand.</li>
          </ol>
        </Sec>

        {/* Eights are Wild */}
        <Sec title="Eights are Wild">
          An <B>8</B> can be played on <B>any card</B>, regardless of suit
          or rank. When you play an 8, you choose the <B>new suit</B> that
          the next player must match. The current suit is shown in the
          controls area. AI opponents pick the suit they hold the most of.
        </Sec>

        {/* Matching Rules */}
        <Sec title="Matching Rules">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Match by suit</B> -- play any card of the current suit
              (shown in the controls bar).</Li>
            <Li><B>Match by rank</B> -- play a card of the same rank as the
              top discard, regardless of suit.</Li>
            <Li><B>Play an 8</B> -- always valid. You then choose the new
              suit.</Li>
          </ul>
          <p className="mt-1.5 text-slate-400">
            Playable cards in your hand are highlighted; non-playable cards
            are dimmed.
          </p>
        </Sec>

        {/* Scoring */}
        <Sec title="Scoring">
          When a player goes out, they earn points for every card remaining
          in all opponents&apos; hands:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>8s</B> -- <B>50 points</B> each (the most valuable).</Li>
            <Li><B>Face cards (J, Q, K) and Aces</B> -- <B>10 points</B> each.</Li>
            <Li><B>Number cards (2-7, 9, 10)</B> -- <B>face value</B> (e.g.,
              a 5 is worth 5 points).</Li>
          </ul>
        </Sec>

        {/* Winning */}
        <Sec title="Winning the Game">
          <ul className="space-y-1 text-slate-300">
            <Li>After each round, scores accumulate. A new round begins with
              a fresh deal.</Li>
            <Li>The first player to reach <B>200 points</B> wins the
              game.</Li>
            <Li>If an AI opponent reaches 200 first, you lose.</Li>
          </ul>
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Save your 8s.</B> They are wild and incredibly powerful --
              don&apos;t waste them early. Play non-8 cards when possible.</Li>
            <Li><B>Change the suit strategically.</B> When you play an 8,
              pick the suit you have the most of to maximize your future
              plays.</Li>
            <Li><B>Watch the draw pile.</B> When it runs low, the discard
              pile reshuffles. Plan accordingly.</Li>
            <Li><B>Go out fast.</B> Holding high-value cards (especially 8s
              at 50 points each) is risky -- if an opponent goes out, those
              cards count against you.</Li>
            <Li><B>Track what&apos;s been played.</B> If many cards of a suit
              have been discarded, switching to that suit may force opponents
              to draw.</Li>
          </ul>
        </Sec>

        <div className="mt-4 pt-3 border-t border-slate-700 text-center">
          <button onClick={onClose} className="px-6 py-2 text-sm rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors">
            Got it!
          </button>
        </div>
      </div>
    </div>
  )
}

function Sec({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="text-sm font-semibold text-slate-200 mb-1">{title}</h3>
      <div className="text-xs leading-relaxed text-slate-400">{children}</div>
    </div>
  )
}

function Li({ children }: { children: React.ReactNode }) {
  return <li className="flex gap-1.5 text-xs"><span className="text-slate-600 mt-0.5">&bull;</span><span>{children}</span></li>
}

function B({ children }: { children: React.ReactNode }) {
  return <span className="text-white font-medium">{children}</span>
}

// ── Component ────────────────────────────────────────────────────────

function CrazyEightsSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<SavedState>('crazy-eights')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('crazy-eights'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('crazy-eights')

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

  const [gameState, setGameState] = useState<CrazyEightsState>(
    () => saved?.gameState ?? createCrazyEightsGame(2)
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const humanWon = gameState.scores[0] >= gameState.targetScore
      if (humanWon) sfx.play('match')
      setGameStatus(humanWon ? 'won' : 'lost')
      onGameEnd?.(humanWon ? 'win' : 'loss')
      clear()
    }
  }, [gameState, clear])

  const handlePlay = useCallback((cardIdx: number) => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('play')
    setGameState(prev => playCard(prev, cardIdx))
  }, [])

  const handleDraw = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('draw')
    setGameState(prev => drawCard(prev))
  }, [])

  const handleChooseSuit = useCallback((suit: Suit) => {
    setGameState(prev => chooseSuit(prev, suit))
  }, [])

  const handleNewRound = useCallback(() => {
    setGameState(prev => newRound(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createCrazyEightsGame(gameState.playerCount))
    setGameStatus('playing')
    clear()
  }, [gameState.playerCount, clear])

  const playable = getHumanPlayableCards(gameState)
  const topDiscard = gameState.discardPile[gameState.discardPile.length - 1]

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-xs text-slate-400">
        {gameState.scores.map((s, i) => (
          <span key={i} className={i === 0 ? 'text-white' : ''}>
            {i === 0 ? 'You' : `P${i + 1}`}: {s}
          </span>
        ))}
      </div>
      <span className="text-xs text-slate-400">
        Current suit: <span className={`font-bold ${gameState.currentSuit === 'hearts' || gameState.currentSuit === 'diamonds' ? 'text-red-400' : 'text-white'}`}>
          {getSuitSymbol(gameState.currentSuit)}
        </span>
      </span>
      <div className="flex items-center gap-2">
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
    <GameLayout title="Crazy Eights" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* AI hands (card counts) */}
        <div className="flex gap-4 justify-center">
          {gameState.hands.slice(1).map((hand, i) => (
            <div key={i} className="text-center">
              <span className="text-xs text-slate-400">Player {i + 2}</span>
              <div className="flex gap-0.5 justify-center mt-1">
                {hand.slice(0, Math.min(hand.length, 7)).map((_, j) => (
                  <div key={j} className="w-6 h-9">
                    <CardBack />
                  </div>
                ))}
                {hand.length > 7 && (
                  <span className="text-xs text-slate-500 self-center ml-1">+{hand.length - 7}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Draw pile + Discard pile */}
        <div className="flex gap-4 items-center justify-center">
          <div
            className={`${CARD_SIZE} cursor-pointer`}
            onClick={handleDraw}
          >
            {gameState.drawPile.length > 0 ? (
              <CardBack />
            ) : (
              <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                Empty
              </div>
            )}
          </div>
          <div className={CARD_SIZE}>
            {topDiscard && <CardFace card={topDiscard} />}
          </div>
          <span className="text-xs text-slate-500">{gameState.drawPile.length} left</span>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Suit picker */}
        {gameState.phase === 'choosingSuit' && (
          <div className="flex gap-3 justify-center">
            {SUITS.map(suit => (
              <button
                key={suit}
                onClick={() => handleChooseSuit(suit)}
                className={`w-12 h-12 rounded-lg border-2 text-2xl flex items-center justify-center transition-colors ${
                  suit === 'hearts' || suit === 'diamonds'
                    ? 'border-red-500 hover:bg-red-500/20 text-red-400'
                    : 'border-slate-400 hover:bg-slate-600/40 text-white'
                }`}
              >
                {getSuitSymbol(suit)}
              </button>
            ))}
          </div>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1.5 justify-center max-w-md">
          {gameState.hands[0].map((card, i) => {
            const isPlayable = playable.includes(i)
            return (
              <div
                key={i}
                className={`${CARD_SIZE} transition-transform ${
                  isPlayable ? 'cursor-pointer hover:-translate-y-1' : 'opacity-50'
                }`}
                onClick={() => isPlayable && handlePlay(i)}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {/* Round over */}
        {gameState.phase === 'roundOver' && (
          <button
            onClick={handleNewRound}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Next Round
          </button>
        )}

        {(gameStatus === 'won' || gameStatus === 'lost') && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            score={gameState.scores[0]}
            message={gameState.message}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>

      {/* Help modal */}
      {showHelp && <CrazyEightsHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-win against AI) ─────────────────────────

function CrazyEightsRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: Difficulty; onLeave?: () => void }) {
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
      <CrazyEightsSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function CrazyEights() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'crazy-eights',
        gameName: 'Crazy Eights',
        modes: ['vs', 'first_to_win'],
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: { vs: 'Head-to-head card game', first_to_win: 'First to empty their hand wins' },
      }}
      renderSinglePlayer={() => <CrazyEightsSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <CrazyEightsMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
        ) : (
          <CrazyEightsRaceWrapper roomId={roomId} difficulty={roomConfig?.difficulty} onLeave={onLeave} />
        )
      }
    />
  )
}
