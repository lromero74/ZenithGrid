/**
 * Go Fish — ask for ranks, collect books of four.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import { getRankDisplay } from '../../../utils/cardUtils'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import { GoFishMultiplayer } from './GoFishMultiplayer'
import {
  createGoFishGame,
  askForRank,
  goFish,
  aiTurn,
  getAskableRanks,
  type GoFishState,
} from './goFishEngine'

interface SavedState {
  gameState: GoFishState
  gameStatus: GameStatus
}

// ── Help modal ───────────────────────────────────────────────────────

function GoFishHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Go Fish</h2>

        {/* Goal */}
        <Sec title="Goal">
          Collect the most <B>books</B> (sets of four cards of the same rank).
          There are <B>13 possible books</B> in a standard deck (one for each
          rank from Ace through King). The player with the most books when all
          13 have been collected wins.
        </Sec>

        {/* Setup */}
        <Sec title="Setup">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>A standard <B>52-card deck</B> is used.</Li>
            <Li>Each player is dealt <B>7 cards</B>.</Li>
            <Li>The remaining <B>38 cards</B> form the <B>pond</B> (draw pile).</Li>
            <Li>You go first.</Li>
          </ul>
        </Sec>

        {/* How to Play */}
        <Sec title="How to Play">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li>On your turn, <B>tap a card</B> in your hand to ask the AI for
              all cards of that rank. You must hold at least one card of the
              rank you ask for.</li>
            <li>If the AI has any cards of that rank, they are <B>transferred
              to your hand</B> and you get <B>another turn</B>.</li>
            <li>If the AI has none, it says <B>&quot;Go Fish!&quot;</B> and you
              must draw a card from the pond.</li>
            <li>If the card you draw matches the rank you asked for, you get
              <B> another turn</B>. Otherwise, the turn passes to the AI.</li>
          </ol>
        </Sec>

        {/* Books */}
        <Sec title="Books">
          <ul className="space-y-1 text-slate-300">
            <Li>When you collect all <B>4 cards of the same rank</B>, a book
              is automatically formed and those cards are removed from your
              hand.</Li>
            <Li>Your completed books are shown below the pond. The AI&apos;s
              books are shown above.</Li>
            <Li>Both players&apos; book counts are displayed in the controls
              bar at the top.</Li>
          </ul>
        </Sec>

        {/* The Pond */}
        <Sec title="The Pond">
          <ul className="space-y-1 text-slate-300">
            <Li>The pond is the central draw pile. Its card count is shown
              next to it.</Li>
            <Li>When you hear &quot;Go Fish!&quot;, tap the <B>pond card</B> or
              the <B>Go Fish! button</B> to draw.</Li>
            <Li>If the pond runs out and a player has no cards, the game
              ends.</Li>
          </ul>
        </Sec>

        {/* AI Behavior */}
        <Sec title="AI Opponent">
          <ul className="space-y-1 text-slate-300">
            <Li>The AI takes its turn automatically after a short delay.</Li>
            <Li>It prioritizes asking for ranks where it already holds <B>3
              cards</B> (close to a book), then <B>2 cards</B>.</Li>
            <Li>It <B>remembers ranks you have asked for</B> and may ask for
              those if it holds a matching card.</Li>
            <Li>If the AI successfully gets cards from you, it gets another
              turn -- it may chain several asks in a row.</Li>
            <Li>If it draws the rank it asked for from the pond, it also
              gets another turn.</Li>
          </ul>
        </Sec>

        {/* Empty Hand */}
        <Sec title="Running Out of Cards">
          <ul className="space-y-1 text-slate-300">
            <Li>If your hand is emptied (by books or transfers), you
              automatically <B>draw a card</B> from the pond if any remain.</Li>
            <Li>If the pond is also empty, the turn passes.</Li>
          </ul>
        </Sec>

        {/* Game Over */}
        <Sec title="Game Over">
          <ul className="space-y-1 text-slate-300">
            <Li>The game ends when all <B>13 books</B> have been collected, or
              the pond is empty and a player has no cards.</Li>
            <Li>The player with the <B>most books wins</B>. If both have the
              same number, it is a <B>tie</B>.</Li>
          </ul>
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Ask for ranks you hold multiples of.</B> If you have 2 or 3
              of a rank, asking for it maximizes your chance of completing a
              book.</Li>
            <Li><B>Pay attention to AI asks.</B> When the AI asks for a rank,
              you know it holds at least one -- ask for it back on your next
              turn if you have one.</Li>
            <Li><B>Track the books.</B> Once a rank is booked, no one can ask
              for it. Focus on the remaining ranks.</Li>
            <Li><B>Lucky draws matter.</B> Drawing the rank you asked for
              gives you an extra turn -- ask for ranks where there are still
              cards unaccounted for.</Li>
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

function GoFishSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<SavedState>('go-fish')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('go-fish'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('go-fish')

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

  const [gameState, setGameState] = useState<GoFishState>(
    () => saved?.gameState ?? createGoFishGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const humanWon = gameState.books[0].length > gameState.books[1].length
      const tied = gameState.books[0].length === gameState.books[1].length
      if (humanWon) sfx.play('match')
      const result = tied ? 'draw' : humanWon ? 'won' : 'lost'
      setGameStatus(result)
      onGameEnd?.(tied ? 'draw' : humanWon ? 'win' : 'loss')
      clear()
    }
  }, [gameState, clear])

  // Auto-run AI turn
  useEffect(() => {
    if (gameState.phase === 'aiTurn') {
      const timer = setTimeout(() => {
        setGameState(prev => aiTurn(prev))
      }, 800)
      return () => clearTimeout(timer)
    }
  }, [gameState.phase])

  const handleAsk = useCallback((rank: number) => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('play')
    setGameState(prev => askForRank(prev, rank))
  }, [])

  const handleGoFish = useCallback(() => {
    sfx.play('draw')
    setGameState(prev => goFish(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createGoFishGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const askable = getAskableRanks(gameState)

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3 text-xs text-slate-400">
        <span className="text-white">You: {gameState.books[0].length} books</span>
        <span>AI: {gameState.books[1].length} books</span>
      </div>
      <span className="text-xs text-slate-400">
        Pond: {gameState.pond.length} cards
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
    <GameLayout title="Go Fish" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* AI hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400">AI ({gameState.hands[1].length} cards)</span>
          <div className="flex gap-0.5 justify-center mt-1">
            {gameState.hands[1].slice(0, Math.min(gameState.hands[1].length, 7)).map((_, j) => (
              <div key={j} className="w-6 h-9">
                <CardBack />
              </div>
            ))}
            {gameState.hands[1].length > 7 && (
              <span className="text-xs text-slate-500 self-center ml-1">+{gameState.hands[1].length - 7}</span>
            )}
          </div>
          {gameState.books[1].length > 0 && (
            <div className="text-xs text-slate-400 mt-1">
              Books: {gameState.books[1].map(r => getRankDisplay(r)).join(', ')}
            </div>
          )}
        </div>

        {/* Pond */}
        <div className="flex gap-3 items-center justify-center">
          <div
            className={`${CARD_SIZE} ${gameState.phase === 'goFish' ? 'cursor-pointer' : ''}`}
            onClick={gameState.phase === 'goFish' ? handleGoFish : undefined}
          >
            {gameState.pond.length > 0 ? (
              <CardBack />
            ) : (
              <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                Empty
              </div>
            )}
          </div>
          <span className="text-xs text-slate-500">{gameState.pond.length} left</span>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Go Fish button */}
        {gameState.phase === 'goFish' && (
          <button
            onClick={handleGoFish}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Go Fish!
          </button>
        )}

        {/* Player books */}
        {gameState.books[0].length > 0 && (
          <div className="text-xs text-emerald-400">
            Your Books: {gameState.books[0].map(r => getRankDisplay(r)).join(', ')}
          </div>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1.5 justify-center max-w-md">
          {gameState.hands[0].map((card, i) => {
            const isAskable = gameState.phase === 'playerTurn' && askable.includes(card.rank)
            return (
              <div
                key={i}
                className={`${CARD_SIZE} transition-transform ${
                  isAskable ? 'cursor-pointer hover:-translate-y-1' : 'opacity-60'
                }`}
                onClick={() => isAskable && handleAsk(card.rank)}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            score={gameState.books[0].length}
            message={gameState.message}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <GoFishHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-win against AI) ─────────────────────────

function GoFishRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, localScore, opponentLevelUp, broadcastState, reportFinish, leaveRoom } = useRaceMode(roomId, 'first_to_win')
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
        localScore={localScore}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
        onDismiss={onLeave}
        onBackToLobby={onLeave}
        onLeaveGame={leaveRoom}
      />
      <GoFishSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function GoFish() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'go-fish',
        gameName: 'Go Fish',
        modes: ['vs', 'first_to_win'],
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: { vs: 'Head-to-head card game', first_to_win: 'First to collect the most sets wins' },
      }}
      renderSinglePlayer={() => <GoFishSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <GoFishMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
        ) : (
          <GoFishRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
        )
      }
    />
  )
}
