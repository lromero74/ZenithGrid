/**
 * Cribbage — 2-player card game. First to 121 wins.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SIZE_XS } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import { getRankDisplay, getSuitSymbol } from '../../../utils/cardUtils'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import {
  createCribbageGame,
  toggleCribSelection,
  submitCrib,
  playPegCard,
  sayGo,
  continueScoring,
  newRound,
  getHumanPeggableCards,
  humanMustGo,
  isCardPlayed,
  type CribbageState,
} from './CribbageEngine'

interface SavedState {
  gameState: CribbageState
  gameStatus: GameStatus
}

// ── Help modal ───────────────────────────────────────────────────────

function CribbageHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Cribbage</h2>

        {/* Goal */}
        <Sec title="Goal">
          Be the first player to reach <B>121 points</B>. You play against one
          AI opponent. Points are scored through card combinations during both
          the pegging and hand-scoring phases.
        </Sec>

        {/* Card Values */}
        <Sec title="Card Values">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Ace</B> — worth <B>1</B>.</Li>
            <Li><B>Number cards (2-10)</B> — face value.</Li>
            <Li><B>Face cards (J, Q, K)</B> — worth <B>10</B>.</Li>
          </ul>
        </Sec>

        {/* Round Structure */}
        <Sec title="Round Structure">
          Each round has four stages:
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li><B>Deal</B> — each player receives 6 cards.</li>
            <li><B>Discard</B> — each player discards 2 cards to the <B>crib</B>
              (a bonus hand scored by the dealer). You keep 4 cards.</li>
            <li><B>Pegging</B> — players alternate playing cards, scoring points
              along the way.</li>
            <li><B>Hand Scoring</B> — each hand (and the crib) is scored for
              combinations.</li>
          </ol>
        </Sec>

        {/* The Cut */}
        <Sec title="The Cut">
          After discarding, a <B>starter card</B> (cut card) is turned up from
          the deck. This card is shared by all hands during scoring.
          If the cut card is a <B>Jack</B>, the dealer scores <B>2 points</B>
          immediately (&quot;His Heels&quot;).
        </Sec>

        {/* Pegging */}
        <Sec title="Pegging">
          The <B>non-dealer</B> plays first. Players alternate playing one card
          at a time, adding its value to a running count (max <B>31</B>).
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>If the count reaches exactly <B>15</B> — score <B>2 points</B>.</Li>
            <Li>If the count reaches exactly <B>31</B> — score <B>2 points</B>,
              and the count resets to 0.</Li>
            <Li><B>Pair</B> — playing a card of the same rank as the previous
              card scores <B>2 points</B>.</Li>
            <Li><B>Three of a kind</B> — three consecutive same-rank cards
              scores <B>6 points</B>.</Li>
            <Li><B>Four of a kind</B> — four consecutive same-rank cards
              scores <B>12 points</B>.</Li>
            <Li><B>Run</B> — if the last 3 or more cards played form a
              consecutive sequence (in any order), score <B>1 point per card</B>
              in the run.</Li>
          </ul>
        </Sec>

        {/* Go */}
        <Sec title="Go &amp; Last Card">
          <ul className="space-y-1 text-slate-300">
            <Li>If you cannot play without exceeding 31, you must say
              <B> Go</B>. The opponent continues playing until they also
              cannot play.</Li>
            <Li>The last player to play a card before the count resets scores
              <B> 1 point</B> for &quot;Go&quot; (unless they hit 31, which
              already scored 2).</Li>
            <Li>After a Go, the count resets to <B>0</B> and play continues
              with any remaining cards.</Li>
            <Li>The last card of the entire pegging round also scores
              <B> 1 point</B>.</Li>
          </ul>
        </Sec>

        {/* Hand Scoring */}
        <Sec title="Hand Scoring">
          After pegging, hands are scored using the 4 hand cards plus the
          cut card (5 cards total). The <B>non-dealer scores first</B> (an
          advantage if close to 121).
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Fifteens</B> — every combination of cards that totals 15
              scores <B>2 points</B>.</Li>
            <Li><B>Pairs</B> — each pair of same-rank cards scores
              <B> 2 points</B>. Three of a kind = 6, four of a kind = 12.</Li>
            <Li><B>Runs</B> — 3 or more cards in consecutive rank order score
              <B> 1 point per card</B>. Double runs (with a pair) count
              each combination separately.</Li>
            <Li><B>Flush</B> — all 4 hand cards of the same suit score
              <B> 4 points</B>. If the cut card also matches, score
              <B> 5 points</B>.</Li>
            <Li><B>Nobs</B> — a Jack in your hand that matches the suit of the
              cut card scores <B>1 point</B>.</Li>
          </ul>
        </Sec>

        {/* The Crib */}
        <Sec title="The Crib">
          <ul className="space-y-1 text-slate-300">
            <Li>The crib is scored last and belongs to the <B>dealer</B>.</Li>
            <Li>It uses the same scoring rules as a regular hand, except a
              <B> 4-card flush does not count</B> in the crib — all 5 cards
              (including the cut) must be the same suit for a flush.</Li>
            <Li>The dealer alternates each round, so the crib advantage
              switches back and forth.</Li>
          </ul>
        </Sec>

        {/* Scoring Order */}
        <Sec title="Scoring Order">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li>Non-dealer&apos;s hand</li>
            <li>Dealer&apos;s hand</li>
            <li>Dealer&apos;s crib</li>
          </ol>
          <p className="mt-1.5 text-slate-400 text-xs">
            This order matters: the non-dealer scores first. If they reach
            121 during hand scoring, they win — even if the dealer would have
            scored more.
          </p>
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Keep cards that work together</B> — pairs, runs, and
              cards that add to 15 are more valuable together.</Li>
            <Li><B>Watch what you send to the crib.</B> If you&apos;re the
              dealer, send cards that might score well. If not, avoid
              sending 5s, pairs, or cards that sum to 15.</Li>
            <Li><B>Fives are valuable</B> — they combine with 10-value cards
              to make 15. Keep them when possible; avoid discarding them to
              your opponent&apos;s crib.</Li>
            <Li><B>During pegging, avoid leaving the count at 21</B> — your
              opponent can play a 10-value card to hit 31 for 2 points.</Li>
            <Li><B>Lead with low cards</B> in pegging to keep your options
              open and avoid giving your opponent easy 15s.</Li>
            <Li><B>The non-dealer has a scoring advantage</B> — they count
              their hand first, which matters in close games near 121.</Li>
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

export default function Cribbage() {
  const { load, save, clear } = useGameState<SavedState>('cribbage')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('cribbage'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('cribbage')

  const [gameState, setGameState] = useState<CribbageState>(
    () => saved?.gameState ?? createCribbageGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [showHelp, setShowHelp] = useState(false)

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      setGameStatus(gameState.scores[0] >= 121 ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  const handleToggleSelect = useCallback((idx: number) => {
    music.init()
    sfx.init()
    music.start()
    setGameState(prev => toggleCribSelection(prev, idx))
  }, [])

  const handleSubmitCrib = useCallback(() => {
    sfx.play('play')
    setGameState(prev => submitCrib(prev))
  }, [])

  const handlePlayCard = useCallback((idx: number) => {
    sfx.play('play')
    setGameState(prev => playPegCard(prev, idx))
  }, [])

  const handleSayGo = useCallback(() => {
    sfx.play('go')
    setGameState(prev => sayGo(prev))
  }, [])

  const handleContinueScoring = useCallback(() => {
    sfx.play('peg')
    setGameState(prev => continueScoring(prev))
  }, [])

  const handleNewRound = useCallback(() => {
    setGameState(prev => newRound(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createCribbageGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const peggable = getHumanPeggableCards(gameState)
  const mustGo = humanMustGo(gameState)
  const isScoring = gameState.phase === 'scoring'
  const showAiCards = isScoring || gameState.phase === 'gameOver'

  // Score board display
  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-4 text-xs">
        <span className="text-white font-medium">
          You: <span className="text-blue-400">{gameState.scores[0]}</span>/121
        </span>
        <span className="text-slate-400">
          AI: <span className="text-red-400">{gameState.scores[1]}</span>/121
        </span>
      </div>
      <span className="text-xs text-slate-400">
        Dealer: {gameState.dealer === 0 ? 'You' : 'AI'}
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
    <GameLayout title="Cribbage" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">

        {/* Cribbage board (score visualization) */}
        <div className="w-full flex gap-2 items-center">
          <div className="flex-1">
            <div className="text-[0.6rem] text-blue-400 mb-0.5">You</div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, (gameState.scores[0] / 121) * 100)}%` }}
              />
            </div>
          </div>
          <div className="flex-1">
            <div className="text-[0.6rem] text-red-400 mb-0.5">AI</div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-red-500 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, (gameState.scores[1] / 121) * 100)}%` }}
              />
            </div>
          </div>
        </div>

        {/* AI hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400">AI Hand</span>
          <div className="flex gap-1 justify-center mt-1">
            {gameState.hands[1].map((card, i) => {
              const played = isCardPlayed(gameState, 1, i)
              return (
                <div
                  key={i}
                  className={`${CARD_SIZE} ${played ? 'opacity-30' : ''}`}
                >
                  {showAiCards ? <CardFace card={card} /> : <CardBack />}
                </div>
              )
            })}
          </div>
        </div>

        {/* Cut card + pegging area */}
        <div className="flex gap-4 items-start justify-center">
          {/* Cut card */}
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500">Cut</span>
            <div className={CARD_SIZE}>
              {gameState.cutCard ? (
                <CardFace card={gameState.cutCard} />
              ) : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                  --
                </div>
              )}
            </div>
          </div>

          {/* Pegging area */}
          {gameState.phase === 'pegging' && (
            <div className="text-center">
              <span className="text-[0.6rem] text-slate-500">
                Count: <span className="text-white font-bold">{gameState.pegTotal}</span>/31
              </span>
              <div className="flex gap-0.5 mt-1 flex-wrap justify-center max-w-[12rem]">
                {gameState.pegCards.map((pc, i) => (
                  <div
                    key={i}
                    className={`${CARD_SIZE_XS} ${
                      pc.player === 0 ? 'ring-1 ring-blue-500/50' : 'ring-1 ring-red-500/50'
                    } rounded`}
                  >
                    <CardFace card={pc.card} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Crib */}
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500">
              Crib ({gameState.dealer === 0 ? 'Yours' : "AI's"})
            </span>
            <div className={CARD_SIZE}>
              {gameState.crib.length > 0 ? (
                gameState.scoringStep === 'crib' || gameState.scoringStep === 'done' || gameState.phase === 'gameOver' ? (
                  <div className="flex -space-x-8">
                    {gameState.crib.slice(0, 2).map((c, i) => (
                      <div key={i} className={CARD_SIZE}>
                        <CardFace card={c} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <CardBack />
                )
              ) : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                  --
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center min-h-[2.5rem]">
          {gameState.message}
        </p>

        {/* Scoring breakdown */}
        {isScoring && gameState.lastScoreBreakdown && (
          <p className="text-xs text-slate-400 text-center">{gameState.lastScoreBreakdown}</p>
        )}

        {/* Action buttons */}
        <div className="flex gap-2 justify-center">
          {/* Send to Crib button */}
          {gameState.phase === 'discard' && gameState.selectedForCrib.length === 2 && (
            <button
              onClick={handleSubmitCrib}
              className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Send to Crib
            </button>
          )}

          {/* Go button */}
          {gameState.phase === 'pegging' && gameState.currentPlayer === 0 && mustGo && (
            <button
              onClick={handleSayGo}
              className="px-5 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Go
            </button>
          )}

          {/* Continue scoring */}
          {isScoring && gameState.scoringStep !== 'done' && (
            <button
              onClick={handleContinueScoring}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Continue
            </button>
          )}

          {/* Next Round */}
          {isScoring && gameState.scoringStep === 'done' && (
            <button
              onClick={handleNewRound}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Next Round
            </button>
          )}
        </div>

        {/* Peg history (scrollable) */}
        {gameState.phase === 'pegging' && gameState.pegHistory.length > 0 && (
          <div className="w-full">
            <span className="text-[0.6rem] text-slate-500">Pegging History</span>
            <div className="flex gap-0.5 overflow-x-auto py-1">
              {gameState.pegHistory.map((pc, i) => (
                <div
                  key={i}
                  className="flex-shrink-0 text-center"
                >
                  <div className={`text-[0.5rem] ${pc.player === 0 ? 'text-blue-400' : 'text-red-400'}`}>
                    {pc.player === 0 ? 'You' : 'AI'}
                  </div>
                  <div className="text-[0.6rem] text-white">
                    {getRankDisplay(pc.card.rank)}{getSuitSymbol(pc.card.suit)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Player hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400">Your Hand</span>
          <div className="flex flex-wrap gap-1.5 justify-center mt-1 max-w-md">
            {gameState.hands[0].map((card, i) => {
              const isSelected = gameState.selectedForCrib.includes(i)
              const isPlayable = peggable.includes(i)
              const played = isCardPlayed(gameState, 0, i)

              // During discard: all cards clickable for selection
              // During pegging: only playable cards clickable
              const clickable = gameState.phase === 'discard'
                ? true
                : gameState.phase === 'pegging' && isPlayable

              return (
                <div
                  key={i}
                  className={`${CARD_SIZE} transition-all duration-150 ${
                    played ? 'opacity-30 pointer-events-none' : ''
                  } ${
                    clickable && !played ? 'cursor-pointer hover:-translate-y-1' : ''
                  } ${
                    !clickable && !played && gameState.phase === 'pegging' ? 'opacity-50' : ''
                  } ${
                    isSelected ? '-translate-y-2' : ''
                  }`}
                  onClick={() => {
                    if (played) return
                    if (gameState.phase === 'discard') handleToggleSelect(i)
                    else if (gameState.phase === 'pegging' && isPlayable) handlePlayCard(i)
                  }}
                >
                  <CardFace card={card} selected={isSelected} />
                </div>
              )
            })}
          </div>
        </div>

        {/* Discard hint */}
        {gameState.phase === 'discard' && (
          <p className="text-xs text-slate-500 text-center">
            Select 2 cards to discard to the {gameState.dealer === 0 ? 'your' : "AI's"} crib
          </p>
        )}

        {/* Pegging value helper */}
        {gameState.phase === 'pegging' && gameState.currentPlayer === 0 && (
          <p className="text-xs text-slate-500 text-center">
            Click a card to play it. Need {31 - gameState.pegTotal} or less to play.
          </p>
        )}

        {/* Game Over Modal */}
        {(gameStatus === 'won' || gameStatus === 'lost') && (
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
      {showHelp && <CribbageHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}
