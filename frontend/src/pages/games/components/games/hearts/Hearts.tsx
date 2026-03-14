/**
 * Hearts — 4-player trick-taking card game.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE_COMPACT, CARD_SLOT_V, CARD_SLOT_H } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus, Difficulty } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { HeartsMultiplayer } from './HeartsMultiplayer'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import {
  createHeartsGame,
  togglePassCard,
  confirmPass,
  playCard,
  nextRound,
  getValidPlays,
  PLAYER_NAMES,
  type HeartsState,
} from './heartsEngine'

// ── Help modal ─────────────────────────────────────────────────────

function HeartsHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Hearts</h2>

        {/* Overview */}
        <Sec title="Goal">
          Have the <B>lowest score</B> when any player reaches <B>100 points</B>.
          Hearts is a 4-player trick-taking game where you try to avoid taking
          hearts and the Queen of Spades.
        </Sec>

        {/* The Deck */}
        <Sec title="The Deck">
          Hearts uses a standard <B>52-card deck</B>. All cards are dealt out
          evenly — each player receives <B>13 cards</B>.
        </Sec>

        {/* Card Ranking */}
        <Sec title="Card Ranking">
          Cards rank from highest to lowest: <B>Ace, King, Queen, Jack, 10,
          9, 8, 7, 6, 5, 4, 3, 2</B>. There is no trump suit — only the led
          suit matters for winning a trick.
        </Sec>

        {/* Passing */}
        <Sec title="Passing Cards">
          Before each round begins, you select <B>3 cards</B> to pass to
          another player. The passing direction rotates each round:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Round 1</B> — pass to the <B>left</B>.</Li>
            <Li><B>Round 2</B> — pass to the <B>right</B>.</Li>
            <Li><B>Round 3</B> — pass <B>across</B>.</Li>
            <Li><B>Round 4</B> — <B>no passing</B> (keep your hand).</Li>
          </ul>
          This cycle repeats every 4 rounds.
        </Sec>

        {/* Leading & Following */}
        <Sec title="Playing Tricks">
          The player holding the <B>2 of Clubs</B> leads the first trick.
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>The lead player plays any legal card. That card&apos;s suit is the
              <B> led suit</B> for the trick.</Li>
            <Li>Other players <B>must follow the led suit</B> if they can.</Li>
            <Li>If you have no cards of the led suit, you may play <B>any
              card</B> (this is called sloughing or discarding).</Li>
            <Li>The <B>highest card of the led suit</B> wins the trick. Off-suit
              cards (including hearts) never win.</Li>
            <Li>The trick winner leads the next trick.</Li>
          </ul>
        </Sec>

        {/* First Trick Restrictions */}
        <Sec title="First Trick Restrictions">
          On the very first trick of a round:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>The <B>2 of Clubs</B> must be led.</Li>
            <Li>You <B>cannot play hearts</B> or the <B>Queen of Spades</B> on
              the first trick, unless you have no other legal option.</Li>
          </ul>
        </Sec>

        {/* Breaking Hearts */}
        <Sec title="Breaking Hearts">
          Hearts <B>cannot be led</B> until they have been &quot;broken&quot; —
          meaning a heart has been played on a previous trick (usually by
          discarding when void in the led suit). Once hearts are broken, they
          may be led freely. If your hand contains <B>only hearts</B>, you may
          lead one even if hearts haven&apos;t been broken.
        </Sec>

        {/* Point Cards */}
        <Sec title="Point Cards">
          <ul className="space-y-1 text-slate-300">
            <Li>Each <B>heart</B> is worth <B>1 point</B> (13 total).</Li>
            <Li>The <B>Queen of Spades</B> is worth <B>13 points</B>.</Li>
            <Li>All other cards are worth <B>0 points</B>.</Li>
            <Li>There are <B>26 total points</B> each round.</Li>
          </ul>
        </Sec>

        {/* Shoot the Moon */}
        <Sec title="Shoot the Moon">
          If a single player takes <B>all 26 points</B> in a round (every heart
          plus the Queen of Spades), they <B>&quot;shoot the moon&quot;</B>.
          Instead of receiving 26 points, they receive <B>0</B> and every other
          player receives <B>26 points</B>. This is a high-risk, high-reward
          strategy.
        </Sec>

        {/* Scoring & Game Over */}
        <Sec title="Scoring &amp; Game Over">
          Points accumulate across rounds. The game ends when any player&apos;s
          score reaches <B>100 or more</B>. The player with the <B>lowest
          score</B> at that point wins.
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Pass dangerous cards</B> — high hearts, the Queen/Ace/King
              of spades are good candidates to pass away.</Li>
            <Li><B>Void a suit early</B> — being void in a suit lets you dump
              point cards when others lead that suit.</Li>
            <Li><B>Lead low cards</B> — leading low minimizes your chances of
              winning tricks with point cards.</Li>
            <Li><B>Watch the Queen of Spades</B> — if you hold the Ace or King
              of spades without many low spades, consider passing them to avoid
              being forced to take the Queen.</Li>
            <Li><B>Count points taken</B> — keep track of who has taken hearts
              and the Queen. If one player is close to shooting the moon, try to
              take at least one point card to stop them.</Li>
            <Li><B>Save high cards</B> — high off-suit cards can help you win
              late tricks when fewer point cards remain.</Li>
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

interface SavedState {
  gameState: HeartsState
  gameStatus: GameStatus
}

function HeartsSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<SavedState>('hearts')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('hearts'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('hearts')

  const [gameState, setGameState] = useState<HeartsState>(
    () => saved?.gameState ?? createHeartsGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [showHelp, setShowHelp] = useState(false)

  // SFX on trick completion
  const prevTrickLen = useRef(0)
  useEffect(() => {
    if (prevTrickLen.current > 0 && gameState.currentTrick.length === 0) sfx.play('trick_won')
    prevTrickLen.current = gameState.currentTrick.length
  }, [gameState.currentTrick.length])

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const humanScore = gameState.scores[0]
      const minScore = Math.min(...gameState.scores)
      const result = humanScore === minScore ? 'won' : 'lost'
      setGameStatus(result)
      onGameEnd?.(result === 'won' ? 'win' : 'loss')
      clear()
    }
  }, [gameState, clear, onGameEnd])

  const handleTogglePass = useCallback((i: number) => {
    music.init()
    sfx.init()
    music.start()
    setGameState(prev => togglePassCard(prev, i))
  }, [])

  const handleConfirmPass = useCallback(() => {
    sfx.play('play')
    setGameState(prev => confirmPass(prev))
  }, [])

  const handlePlay = useCallback((i: number) => {
    sfx.play('play')
    setGameState(prev => playCard(prev, i))
  }, [])

  const handleNextRound = useCallback(() => {
    sfx.play('hand_won')
    setGameState(prev => nextRound(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createHeartsGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const validPlays = getValidPlays(gameState)
  const isPassing = gameState.phase === 'passing'
  const isPlaying = gameState.phase === 'playing' && gameState.currentPlayer === 0

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex gap-3">
        {PLAYER_NAMES.map((name, i) => (
          <span key={i} className={i === 0 ? 'text-white' : 'text-slate-400'}>
            {name}: {gameState.scores[i]}
            {gameState.roundScores[i] > 0 ? ` (+${gameState.roundScores[i]})` : ''}
          </span>
        ))}
      </div>
      {gameState.heartsBroken && (
        <span className="text-red-400 text-xs">Hearts broken</span>
      )}
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
    <GameLayout title="Hearts" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* North (AI) */}
        <div className="text-center">
          <span className="text-xs text-slate-400">North ({gameState.hands[2].length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[2].slice(0, 7).map((_, i) => (
              <div key={i} className={CARD_SLOT_V}><CardBack /></div>
            ))}
            {gameState.hands[2].length > 7 && <span className="text-[0.6rem] text-slate-500 self-center">+{gameState.hands[2].length - 7}</span>}
          </div>
        </div>

        {/* West + Trick area + East */}
        <div className="flex w-full items-center gap-2">
          {/* West */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-slate-400">West ({gameState.hands[1].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[1].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>

          {/* Trick area */}
          <div className="flex-1 relative h-36 sm:h-48">
            {/* Center trick cards */}
            {gameState.currentTrick.map((play) => {
              const positions = [
                'bottom-0 left-1/2 -translate-x-1/2',  // South (0)
                'left-0 top-1/2 -translate-y-1/2',     // West (1)
                'top-0 left-1/2 -translate-x-1/2',     // North (2)
                'right-0 top-1/2 -translate-y-1/2',    // East (3)
              ]
              return (
                <div key={`${play.player}-${play.card.rank}-${play.card.suit}`}
                  className={`absolute ${positions[play.player]} ${CARD_SIZE_COMPACT}`}
                >
                  <CardFace card={play.card} />
                </div>
              )
            })}
          </div>

          {/* East */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-slate-400">East ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Passing controls */}
        {isPassing && (
          <button
            onClick={handleConfirmPass}
            disabled={gameState.selectedCards.length !== 3}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Pass 3 Cards {gameState.passDirection}
          </button>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {gameState.hands[0].map((card, i) => {
            const isValid = isPassing || validPlays.includes(i)
            const isSelected = gameState.selectedCards.includes(i)
            return (
              <div
                key={`${card.rank}-${card.suit}`}
                className={`${CARD_SIZE_COMPACT} transition-transform ${
                  isValid ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
                } ${isSelected ? '-translate-y-2' : ''}`}
                onClick={() => {
                  if (isPassing) handleTogglePass(i)
                  else if (isPlaying && validPlays.includes(i)) handlePlay(i)
                }}
              >
                <CardFace card={card} selected={isSelected} />
              </div>
            )
          })}
        </div>

        {/* Round over */}
        {gameState.phase === 'roundOver' && (
          <button
            onClick={handleNextRound}
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
      {showHelp && <HeartsHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-win against AI) ─────────────────────────

function HeartsRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: Difficulty; onLeave?: () => void }) {
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
      <HeartsSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function Hearts() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'hearts',
        gameName: 'Hearts',
        modes: ['vs', 'first_to_win'],
        hasDifficulty: true,
        modeDescriptions: {
          vs: '2 humans + 2 AI at one table',
          first_to_win: 'First to win a hand wins',
        },
      }}
      renderSinglePlayer={() => <HeartsSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <HeartsMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
        ) : (
          <HeartsRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
        )
      }
    />
  )
}
