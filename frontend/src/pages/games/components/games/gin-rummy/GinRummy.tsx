/**
 * Gin Rummy — 2-player card game vs AI.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus, Difficulty } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import { GinRummyMultiplayer } from './GinRummyMultiplayer'
import {
  createGinRummyGame,
  drawFromPile,
  drawFromDiscard,
  discard,
  knock,
  newRound,
  canKnock,
  getPlayerDeadwood,
  findBestMelds,
  type GinRummyState,
} from './ginRummyEngine'

interface SavedState {
  gameState: GinRummyState
  gameStatus: GameStatus
}

// ── Help modal ───────────────────────────────────────────────────────

function GinRummyHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Gin Rummy</h2>

        {/* Goal */}
        <Sec title="Goal">
          Form <B>melds</B> (sets and runs) in your hand while minimizing
          your <B>deadwood</B> (unmatched cards). Be the first player to
          reach <B>100 points</B> across multiple rounds.
        </Sec>

        {/* Setup */}
        <Sec title="Setup">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>A standard <B>52-card deck</B> is used.</Li>
            <Li>Each player is dealt <B>10 cards</B>.</Li>
            <Li>One card is placed face-up to start the <B>discard pile</B>.</Li>
            <Li>The remaining cards form the <B>draw pile</B>.</Li>
          </ul>
        </Sec>

        {/* Melds */}
        <Sec title="Melds">
          There are two types of melds:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Sets</B> -- 3 or 4 cards of the <B>same rank</B> (e.g.,
              three 7s or four Kings).</Li>
            <Li><B>Runs</B> -- 3 or more <B>consecutive cards</B> of the
              same suit (e.g., 4-5-6 of hearts). Aces are low (A-2-3 is
              valid, but Q-K-A is not).</Li>
          </ul>
        </Sec>

        {/* How to Play */}
        <Sec title="How to Play">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li>On your turn, <B>draw one card</B> -- either the top card
              of the draw pile (face-down) or the top card of the discard
              pile (face-up). You will then have 11 cards.</li>
            <li><B>Discard one card</B> from your hand by clicking it. This
              brings you back to 10 cards and ends your turn.</li>
            <li>The AI takes its turn automatically, then play returns
              to you.</li>
          </ol>
        </Sec>

        {/* Deadwood */}
        <Sec title="Deadwood">
          Cards not part of any meld are called <B>deadwood</B>. Each has
          a point value:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Face cards (J, Q, K)</B> -- 10 points each.</Li>
            <Li><B>Number cards (2-10)</B> -- face value.</Li>
            <Li><B>Aces</B> -- 1 point each.</Li>
          </ul>
          <p className="mt-1.5 text-slate-400">
            Your current deadwood total is shown in the controls bar. The
            game automatically finds the best arrangement of melds to
            minimize your deadwood.
          </p>
        </Sec>

        {/* Knocking */}
        <Sec title="Knocking">
          <ul className="space-y-1 text-slate-300">
            <Li>During the discard phase (when you have 11 cards), if your
              deadwood total would be <B>10 or less</B> after discarding
              your worst deadwood card, you can <B>knock</B>.</Li>
            <Li>When you knock, your worst deadwood card is automatically
              discarded for you.</Li>
            <Li>The round then ends and hands are compared for scoring.</Li>
            <Li>The AI will also knock when its deadwood is low enough.</Li>
          </ul>
        </Sec>

        {/* Gin */}
        <Sec title="Going Gin">
          If your deadwood is exactly <B>0</B> (all 10 cards form melds),
          the knock button changes to <B>&quot;Gin!&quot;</B>. Going Gin earns a
          bonus -- the defender&apos;s deadwood plus a <B>25-point Gin
          bonus</B>.
        </Sec>

        {/* Scoring */}
        <Sec title="Scoring">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Normal knock</B> -- the knocker scores the difference
              between the defender&apos;s deadwood and the knocker&apos;s
              deadwood.</Li>
            <Li><B>Gin</B> -- the knocker scores the defender&apos;s full
              deadwood total <B>plus 25 bonus points</B>.</Li>
            <Li><B>Undercut</B> -- if the defender&apos;s deadwood is equal
              to or lower than the knocker&apos;s, the defender wins the
              round instead. The defender scores the difference <B>plus a
              25-point undercut bonus</B>.</Li>
          </ul>
        </Sec>

        {/* Draw */}
        <Sec title="Draw">
          If the draw pile runs out of cards and neither player has knocked,
          the round ends in a <B>draw</B> with no points awarded.
        </Sec>

        {/* Winning */}
        <Sec title="Winning the Game">
          <ul className="space-y-1 text-slate-300">
            <Li>Scores accumulate across rounds. After each round, a new
              hand is dealt while scores carry over.</Li>
            <Li>The first player to reach <B>100 points</B> wins the
              game.</Li>
          </ul>
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Watch the discard pile.</B> Drawing from the discard pile
              reveals information to your opponent -- only take it if it
              clearly helps form a meld.</Li>
            <Li><B>Discard high deadwood first.</B> Face cards (10 points)
              are costly if you get caught with them.</Li>
            <Li><B>Knock early when possible.</B> Waiting for Gin is risky
              -- the AI may knock first or undercut you.</Li>
            <Li><B>Think about runs and sets together.</B> A card like 7 of
              hearts could be part of a set (three 7s) or a run (6-7-8 of
              hearts). Keep your options open.</Li>
            <Li><B>Watch your deadwood total.</B> Getting to 10 or below
              lets you knock. Sometimes discarding a medium card to get
              under 10 is better than holding it for a potential meld.</Li>
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

function GinRummySinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<SavedState>('gin-rummy')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('gin-rummy'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('gin-rummy')

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

  const [gameState, setGameState] = useState<GinRummyState>(
    () => saved?.gameState ?? createGinRummyGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      if (gameState.playerScore >= gameState.targetScore) sfx.play('gin')
      const result = gameState.playerScore >= gameState.targetScore ? 'won' : 'lost'
      setGameStatus(result)
      onGameEnd?.(result === 'won' ? 'win' : 'loss')
      clear()
    }
  }, [gameState, clear, onGameEnd])

  const handleDrawPile = useCallback(() => { music.init(); sfx.init(); music.start(); sfx.play('draw'); setGameState(prev => drawFromPile(prev)) }, [])
  const handleDrawDiscard = useCallback(() => { music.init(); sfx.init(); music.start(); sfx.play('draw'); setGameState(prev => drawFromDiscard(prev)) }, [])
  const handleDiscard = useCallback((i: number) => { sfx.play('meld'); setGameState(prev => discard(prev, i)) }, [])
  const handleKnock = useCallback(() => { sfx.play('knock'); setGameState(prev => knock(prev)) }, [])
  const handleNewRound = useCallback(() => setGameState(prev => newRound(prev)), [])

  const handleNewGame = useCallback(() => {
    setGameState(createGinRummyGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const topDiscard = gameState.discardPile[gameState.discardPile.length - 1]
  const isDrawing = gameState.phase === 'drawing' && gameState.currentPlayer === 0
  const isDiscarding = gameState.phase === 'discarding' && gameState.currentPlayer === 0
  const showKnock = canKnock(gameState)
  const deadwood = gameState.phase === 'discarding' ? getPlayerDeadwood(gameState) : findBestMelds(gameState.playerHand).deadwoodTotal

  // Show AI hand face-up during scoring/gameOver
  const showAiCards = gameState.phase === 'scoring' || gameState.phase === 'gameOver' || gameState.phase === 'knocked'

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3 text-xs">
        <span className="text-white">You: {gameState.playerScore}</span>
        <span className="text-slate-400">AI: {gameState.aiScore}</span>
      </div>
      <span className="text-xs text-slate-400">Deadwood: {deadwood}</span>
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
    <GameLayout title="Gin Rummy" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* AI hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400 mb-1 block">AI ({gameState.aiHand.length} cards)</span>
          <div className="flex gap-1 justify-center flex-wrap">
            {gameState.aiHand.map((card, i) => (
              <div key={i} className={CARD_SIZE}>
                {showAiCards ? <CardFace card={{ ...card, faceUp: true }} /> : <CardBack />}
              </div>
            ))}
          </div>
        </div>

        {/* Draw pile + Discard pile */}
        <div className="flex gap-4 items-center justify-center">
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">Draw</span>
            <div
              className={`${CARD_SIZE} ${isDrawing ? 'cursor-pointer ring-2 ring-blue-400/50 rounded-md' : ''}`}
              onClick={isDrawing ? handleDrawPile : undefined}
            >
              {gameState.drawPile.length > 0 ? <CardBack /> : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">Empty</div>
              )}
            </div>
          </div>
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">Discard</span>
            <div
              className={`${CARD_SIZE} ${isDrawing && topDiscard ? 'cursor-pointer ring-2 ring-blue-400/50 rounded-md' : ''}`}
              onClick={isDrawing ? handleDrawDiscard : undefined}
            >
              {topDiscard ? <CardFace card={topDiscard} /> : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50" />
              )}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Knock button */}
        {showKnock && (
          <button
            onClick={handleKnock}
            className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            {deadwood === 0 ? 'Gin!' : `Knock (${deadwood} deadwood)`}
          </button>
        )}

        {/* Player hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400 mb-1 block">Your Hand</span>
          <div className="flex gap-1 justify-center flex-wrap">
            {gameState.playerHand.map((card, i) => (
              <div
                key={i}
                className={`${CARD_SIZE} transition-transform ${
                  isDiscarding ? 'cursor-pointer hover:-translate-y-1' : ''
                }`}
                onClick={() => isDiscarding && handleDiscard(i)}
              >
                <CardFace card={card} />
              </div>
            ))}
          </div>
        </div>

        {/* Round over */}
        {gameState.phase === 'scoring' && (
          <div className="text-center space-y-2">
            <p className="text-sm text-emerald-400">{gameState.roundMessage}</p>
            <button
              onClick={handleNewRound}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Next Round
            </button>
          </div>
        )}

        {(gameStatus === 'won' || gameStatus === 'lost') && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            score={gameState.playerScore}
            message={gameState.message}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>

      {/* Help modal */}
      {showHelp && <GinRummyHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-win against AI) ─────────────────────────

function GinRummyRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: Difficulty; onLeave?: () => void }) {
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
      <GinRummySinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function GinRummy() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'gin-rummy',
        gameName: 'Gin Rummy',
        modes: ['vs', 'first_to_win'],
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: { vs: 'Head-to-head card game', first_to_win: 'First to gin wins' },
      }}
      renderSinglePlayer={() => <GinRummySinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <GinRummyMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
        ) : (
          <GinRummyRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
        )
      }
    />
  )
}
