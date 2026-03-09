/**
 * Texas Hold'em — poker with community cards.
 * Refined by David Greene: proper betting rounds, blind rotation, AI pacing, blind levels.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SIZE_LARGE } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import {
  createTexasHoldemGame,
  startHand,
  fold,
  check,
  call,
  raise as raiseAction,
  allIn,
  getValidActions,
  getMinRaise,
  aiAction,
  nextHand,
  setBlinds,
  type TexasHoldemState,
} from './TexasHoldemEngine'

interface SavedState {
  gameState: TexasHoldemState
  gameStatus: GameStatus
  gameStartTime: number
}

/** Format a lastAction string to use "P2/P3/P4" instead of "Player 1/2/3". */
function formatAction(action: string): string {
  return action.replace(/Player (\d+)/g, (_, n) => `P${Number(n) + 1}`)
}

// ── Help modal ───────────────────────────────────────────────────────

function HoldemHelp({ onClose }: { onClose: () => void }) {
  const Sec = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div className="mb-4">
      <h3 className="text-sm font-semibold text-slate-200 mb-1">{title}</h3>
      <div className="text-xs leading-relaxed text-slate-400">{children}</div>
    </div>
  )
  const B = ({ children }: { children: React.ReactNode }) => (
    <span className="text-white font-medium">{children}</span>
  )
  const Li = ({ children }: { children: React.ReactNode }) => (
    <li className="flex gap-1.5 text-xs"><span className="text-slate-600 mt-0.5">•</span><span>{children}</span></li>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Texas Hold&apos;em</h2>

        <Sec title="Overview">
          Texas Hold&apos;em is a poker game where you compete against 3 AI
          opponents. Each player gets 2 private <B>hole cards</B>, and 5
          shared <B>community cards</B> are dealt to the center of the
          table. Make the best 5-card hand using any combination of your
          hole cards and the community cards. The last player with chips
          wins the tournament.
        </Sec>

        <Sec title="Game Setup">
          <ul className="space-y-1 text-slate-300">
            <Li>4 players total — you (P1) and 3 AI opponents (P2, P3, P4).</Li>
            <Li>Everyone starts with <B>1,000 chips</B>.</Li>
            <Li>Blinds start at <B>10/20</B> and double every 10 minutes (20/40, 40/80, etc.).</Li>
            <Li>The <B>dealer button</B> (D) rotates each hand.</Li>
            <Li>The player left of the dealer posts the <B>small blind</B> (SB), and the next player posts the <B>big blind</B> (BB).</Li>
          </ul>
        </Sec>

        <Sec title="Betting Rounds">
          Each hand has up to 4 betting rounds:
          <ol className="mt-1.5 space-y-2 text-slate-300 list-decimal list-inside">
            <li><B>Pre-Flop</B> — After receiving your 2 hole cards. Action
              starts left of the big blind (Under-the-Gun). You must at
              least match the big blind to stay in.</li>
            <li><B>Flop</B> — 3 community cards are dealt face-up. A new
              betting round begins starting left of the dealer.</li>
            <li><B>Turn</B> — A 4th community card is dealt. Another betting
              round.</li>
            <li><B>River</B> — The 5th and final community card is dealt.
              Final betting round before showdown.</li>
          </ol>
        </Sec>

        <Sec title="Your Actions">
          On your turn, you can:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Check</B> — Pass without betting (only when no bet to
              match). Free to stay in the hand.</Li>
            <Li><B>Call</B> — Match the current bet to stay in the hand.</Li>
            <Li><B>Raise</B> — Increase the bet. Use the vertical slider to
              choose your raise amount. Minimum raise is the current bet
              plus one big blind.</Li>
            <Li><B>All-In</B> — Bet all your remaining chips. You stay in
              the hand for the showdown even if others bet more.</Li>
            <Li><B>Fold</B> — Surrender your cards and forfeit any chips
              already bet. You&apos;re out for this hand.</Li>
          </ul>
        </Sec>

        <Sec title="Showdown">
          After the river betting round, all remaining players reveal
          their hands. The best 5-card hand wins the pot. If two or
          more players tie, the pot is split equally.
          <p className="mt-1 text-slate-400">
            If only one player remains (everyone else folded), they win the
            pot without showing their cards.
          </p>
          <p className="mt-1 text-slate-400">
            If all active players are all-in, remaining community cards are
            dealt automatically and the hand goes straight to showdown.
          </p>
        </Sec>

        <Sec title="Hand Rankings (Best to Worst)">
          <div className="space-y-0.5 font-mono text-[0.7rem]">
            {[
              ['Royal Flush', 'A K Q J 10 — same suit'],
              ['Straight Flush', '5 cards in sequence — same suit'],
              ['Four of a Kind', '4 cards of the same rank'],
              ['Full House', '3 of a kind + a pair'],
              ['Flush', '5 cards of the same suit'],
              ['Straight', '5 cards in sequence (any suit)'],
              ['Three of a Kind', '3 cards of the same rank'],
              ['Two Pair', '2 different pairs'],
              ['Pair', '2 cards of the same rank'],
              ['High Card', 'Highest card when nothing else connects'],
            ].map(([name, desc], i) => (
              <div key={i} className="flex gap-2">
                <span className={`w-32 flex-shrink-0 ${i === 0 ? 'text-yellow-400' : i < 3 ? 'text-amber-300' : 'text-slate-300'}`}>{i + 1}. {name}</span>
                <span className="text-slate-500">{desc}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-slate-500 text-[0.65rem]">
            Ace can be high (A-K-Q-J-10) or low (A-2-3-4-5 &quot;wheel&quot;).
          </p>
        </Sec>

        <Sec title="Flop Bonus">
          When the 3-card flop is dealt, a <B>1,000 chip bonus</B> is
          added to the pot if the flop contains any of these patterns:
          <ul className="mt-1 space-y-0.5 text-slate-300">
            <Li><B>Three of a kind</B> — all 3 flop cards are the same rank.</Li>
            <Li><B>A run</B> — 3 consecutive ranks (e.g. 7-8-9).</Li>
            <Li><B>Suited</B> — all 3 flop cards are the same suit.</Li>
          </ul>
        </Sec>

        <Sec title="Bonus Hands">
          If you <B>win the pot</B> and your hole cards match one of
          these special combos, you earn an extra <B>1,000 chips</B> on
          top of the pot:
          <div className="mt-1.5 grid grid-cols-3 gap-1 text-center text-[0.7rem]">
            {[
              'J + J', '2 + 3', 'Q + 7', 'J + 2', 'J + 10', '3 + 5',
            ].map(h => (
              <span key={h} className="bg-slate-800 border border-slate-700 rounded px-2 py-0.5 text-amber-300">{h}</span>
            ))}
          </div>
          <p className="mt-1 text-slate-500 text-[0.65rem]">Suit doesn&apos;t matter — just the ranks.</p>
        </Sec>

        <Sec title="Elimination &amp; Winning">
          <ul className="space-y-1 text-slate-300">
            <Li>A player who runs out of chips is <B>eliminated</B>.</Li>
            <Li>If you can&apos;t cover a blind, you go all-in for whatever
              you have.</Li>
            <Li>The tournament ends when <B>one player has all the chips</B>.</Li>
            <Li>If you&apos;re the last one standing, you win!</Li>
          </ul>
        </Sec>

        <Sec title="AI Opponents">
          <p className="text-slate-300">
            AI players use a strategy based on hand strength, pot odds, and
            draw potential. They can check, call, raise, bluff, and fold.
            They think for ~2 seconds per action.
          </p>
        </Sec>

        <Sec title="Controls">
          <ul className="space-y-1 text-slate-300">
            <Li>Action buttons appear on <B>your turn only</B>.</Li>
            <Li>Use the <B>vertical slider</B> next to your cards to set raise amounts.</Li>
            <Li>Click <B>Next Hand</B> after each hand resolves.</Li>
            <Li><B>New Game</B> resets the tournament (slide to confirm).</Li>
            <Li>Winning hand cards are <B>highlighted in blue</B> at showdown.</Li>
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

// ── Component ────────────────────────────────────────────────────────

export default function TexasHoldem() {
  const { load, save, clear } = useGameState<SavedState>('texas-holdem')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('texas-holdem'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('texas-holdem')

  const [gameState, setGameState] = useState<TexasHoldemState>(() => {
    if (saved?.gameState) return saved.gameState
    return startHand(createTexasHoldemGame(4))
  })
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [raiseAmount, setRaiseAmount] = useState(40)
  const [gameStartTime, setGameStartTime] = useState(() => saved?.gameStartTime ?? Date.now())

  const [showHelp, setShowHelp] = useState(false)

  // Shows the last AI action text for 2 seconds
  const [aiActionText, setAiActionText] = useState<string | null>(null)
  const [showSlider, setShowSlider] = useState(false)
  const [slideVal, setSlideVal] = useState(0)
  const trackRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

  // Blinds increase every 10 minutes: level 0 = 10/20, level 1 = 20/40, etc.
  useEffect(() => {
    if (gameStatus !== 'playing') return
    const timer = setInterval(() => {
      const elapsed = Date.now() - gameStartTime
      const level = Math.floor(elapsed / (10 * 60 * 1000))
      setGameState(prev => {
        if (prev.blindLevel === level) return prev
        return setBlinds(prev, level)
      })
    }, 5000) // check every 5s
    return () => clearInterval(timer)
  }, [gameStartTime, gameStatus])

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus, gameStartTime })
    }
  }, [gameState, gameStatus, gameStartTime, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const humanWon = gameState.chips[0] > 0
      if (humanWon) sfx.play('win')
      setGameStatus(humanWon ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  // Auto-run AI turns — 2s delay, shows decision text
  useEffect(() => {
    if (gameState.currentPlayer !== 0 && gameState.phase !== 'handOver' && gameState.phase !== 'gameOver' && gameState.phase !== 'showdown') {
      const timer = setTimeout(() => {
        setGameState(prev => {
          const next = aiAction(prev)
          setAiActionText(formatAction(next.lastAction))
          return next
        })
      }, 2000)
      return () => clearTimeout(timer)
    }
  }, [gameState.currentPlayer, gameState.phase])

  // Clear AI action text after 2s (so it shows while next AI "thinks")
  useEffect(() => {
    if (!aiActionText) return
    // Clear when it becomes the human's turn or hand is over
    if (gameState.currentPlayer === 0 || gameState.phase === 'handOver' || gameState.phase === 'gameOver') {
      const timer = setTimeout(() => setAiActionText(null), 2000)
      return () => clearTimeout(timer)
    }
  }, [aiActionText, gameState.currentPlayer, gameState.phase])

  // SFX when community cards are revealed
  useEffect(() => {
    if (gameState.community.length > 0) sfx.play('reveal')
  }, [gameState.community.length])

  // Update raise slider min
  useEffect(() => {
    const min = getMinRaise(gameState)
    setRaiseAmount(Math.min(min, gameState.chips[0] + gameState.bets[0]))
  }, [gameState.phase, gameState.currentBet])

  const handleFold = useCallback(() => { music.init(); sfx.init(); music.start(); sfx.play('fold'); setGameState(prev => fold(prev)) }, [])
  const handleCheck = useCallback(() => { music.init(); sfx.init(); music.start(); setGameState(prev => check(prev)) }, [])
  const handleCall = useCallback(() => { music.init(); sfx.init(); music.start(); sfx.play('bet'); setGameState(prev => call(prev)) }, [])
  const handleRaise = useCallback(() => {
    sfx.play('bet')
    setGameState(prev => raiseAction(prev, raiseAmount))
  }, [raiseAmount])
  const handleAllIn = useCallback(() => setGameState(prev => allIn(prev)), [])
  const handleNextHand = useCallback(() => { sfx.play('deal'); setGameState(prev => nextHand(prev)) }, [])
  const handleNewGame = useCallback(() => {
    setGameState(startHand(createTexasHoldemGame(4)))
    setGameStatus('playing')
    setAiActionText(null)
    setGameStartTime(Date.now())
    clear()
  }, [clear])

  const startDrag = useCallback(() => { dragging.current = true }, [])
  const moveDrag = useCallback((clientX: number) => {
    if (!dragging.current || !trackRef.current) return
    const rect = trackRef.current.getBoundingClientRect()
    const pct = Math.max(0, Math.min(100, ((clientX - rect.left - 14) / (rect.width - 28)) * 100))
    setSlideVal(pct)
    if (pct >= 95) { dragging.current = false; setShowSlider(false); setSlideVal(0); handleNewGame() }
  }, [handleNewGame])
  const endDrag = useCallback(() => { dragging.current = false; setSlideVal(0) }, [])

  // Winning hand card keys for highlighting (all winners' cards in community)
  const winningCardKeys = useMemo(() => {
    const keys = new Set<string>()
    if (gameState.phase !== 'handOver' || !gameState.showdownResults) return keys
    // Find best hand rank among non-folded players
    let bestRank = 0
    for (let i = 0; i < gameState.showdownResults.length; i++) {
      if (!gameState.foldedPlayers[i] && gameState.showdownResults[i].rank > bestRank) {
        bestRank = gameState.showdownResults[i].rank
      }
    }
    // Collect cards from all players with the best rank
    for (let i = 0; i < gameState.showdownResults.length; i++) {
      if (!gameState.foldedPlayers[i] && gameState.showdownResults[i].rank === bestRank) {
        for (const c of gameState.showdownResults[i].cards) {
          keys.add(`${c.suit}-${c.rank}`)
        }
      }
    }
    return keys
  }, [gameState.phase, gameState.showdownResults, gameState.foldedPlayers])

  const validActions = gameState.currentPlayer === 0 ? getValidActions(gameState) : []
  const toCall = gameState.currentBet - gameState.bets[0]
  const isPlayerTurn = gameState.currentPlayer === 0 && gameState.phase !== 'handOver' && gameState.phase !== 'gameOver'

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <span className="text-slate-400">Pot: <span className="text-yellow-400 font-bold">{gameState.pot}</span></span>
      <span className="text-slate-400">Blinds: {gameState.smallBlind}/{gameState.bigBlind}</span>
      <div className="flex items-center gap-2">
        <button onClick={() => setShowHelp(true)} className="p-1 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-white" title="How to play">
          <HelpCircle className="w-4 h-4" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Texas Hold'em" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-xl space-y-3">
        {/* AI players */}
        <div className="flex gap-4 justify-center flex-wrap">
          {gameState.hands.slice(1).map((hand, i) => {
            const pi = i + 1
            const folded = gameState.foldedPlayers[pi]
            const isAllIn = gameState.allInPlayers[pi]
            const showCards = gameState.phase === 'handOver' && gameState.showdownResults && !folded
            const isDealer = gameState.dealerIdx === pi
            const isSB = gameState.sbIdx === pi
            const isBB = gameState.bbIdx === pi
            return (
              <div key={pi} className={`text-center ${folded ? 'opacity-40' : ''}`}>
                <div className="flex items-center justify-center gap-1 mb-0.5">
                  <span className="text-xs text-slate-400">
                    P{pi + 1}
                  </span>
                  {isDealer && <span className="text-[0.6rem] bg-white text-slate-900 font-bold rounded-full w-4 h-4 flex items-center justify-center">D</span>}
                  {isSB && <span className="text-[0.6rem] bg-blue-500 text-white font-bold rounded-full px-1">SB</span>}
                  {isBB && <span className="text-[0.6rem] bg-amber-500 text-white font-bold rounded-full px-1">BB</span>}
                  {isAllIn && <span className="text-[0.6rem] text-red-400">(All-In)</span>}
                  {folded && <span className="text-[0.6rem] text-slate-500">(Fold)</span>}
                </div>
                <div className="text-xs text-yellow-400">{gameState.chips[pi]}</div>
                <div className="flex gap-0.5 justify-center mt-1">
                  {hand.map((c, j) => {
                    const isWin = showCards && winningCardKeys.has(`${c.suit}-${c.rank}`)
                    return (
                      <div key={j} className={`w-10 h-14 sm:w-12 sm:h-[4rem] transition-transform ${isWin ? 'ring-2 ring-blue-400 rounded-md -translate-y-1' : ''}`}>
                        {showCards ? <CardFace card={c} mini /> : <CardBack />}
                      </div>
                    )
                  })}
                </div>
                {gameState.bets[pi] > 0 && (
                  <span className="text-xs text-blue-400">Bet: {gameState.bets[pi]}</span>
                )}
              </div>
            )
          })}
        </div>

        {/* Community cards */}
        <div className="flex gap-1.5 justify-center min-h-[7rem]">
          {gameState.community.map((card, i) => {
            const isWinning = winningCardKeys.has(`${card.suit}-${card.rank}`)
            return (
              <div key={i} className={`${CARD_SIZE_LARGE} transition-transform ${isWinning ? 'ring-2 ring-blue-400 rounded-lg -translate-y-2' : ''}`}>
                <CardFace card={card} large />
              </div>
            )
          })}
          {Array.from({ length: 5 - gameState.community.length }).map((_, i) => (
            <div key={`e${i}`} className={`${CARD_SIZE_LARGE} rounded-md border border-dashed border-slate-700/50`} />
          ))}
        </div>

        {/* AI action display */}
        {aiActionText && (
          <p className="text-sm text-blue-400 font-medium text-center">{aiActionText}</p>
        )}
        {gameState.currentPlayer !== 0 && gameState.phase !== 'handOver' && gameState.phase !== 'gameOver' && (
          <p className="text-xs text-slate-500 text-center animate-pulse">
            P{gameState.currentPlayer + 1} is thinking...
          </p>
        )}

        {/* Phase / status message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Player hand + raise slider */}
        <div className="flex items-center gap-3">
          <div className="flex flex-col items-center gap-1">
            {/* Player cards */}
            <div className="flex gap-2 justify-center">
              {gameState.hands[0].map((card, i) => {
                const isWinning = winningCardKeys.has(`${card.suit}-${card.rank}`)
                return (
                  <div key={i} className={`${CARD_SIZE} transition-transform ${isWinning ? 'ring-2 ring-blue-400 rounded-lg -translate-y-2' : ''}`}>
                    <CardFace card={card} />
                  </div>
                )
              })}
            </div>
            <div className="flex items-center justify-center gap-1.5 text-xs text-slate-400">
              <span>You</span>
              {gameState.dealerIdx === 0 && <span className="text-[0.6rem] bg-white text-slate-900 font-bold rounded-full w-4 h-4 flex items-center justify-center">D</span>}
              {gameState.sbIdx === 0 && <span className="text-[0.6rem] bg-blue-500 text-white font-bold rounded-full px-1">SB</span>}
              {gameState.bbIdx === 0 && <span className="text-[0.6rem] bg-amber-500 text-white font-bold rounded-full px-1">BB</span>}
              <span>— Chips: <span className="text-white font-bold">{gameState.chips[0]}</span></span>
              {gameState.bets[0] > 0 && <span>Bet: <span className="text-blue-400">{gameState.bets[0]}</span></span>}
            </div>

            {/* Action buttons */}
            {isPlayerTurn && !gameState.foldedPlayers[0] && (
              <div className="flex gap-2 flex-wrap justify-center">
                {validActions.includes('fold') && (
                  <button onClick={handleFold} className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white rounded-lg text-sm transition-colors">
                    Fold
                  </button>
                )}
                {validActions.includes('check') && (
                  <button onClick={handleCheck} className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition-colors">
                    Check
                  </button>
                )}
                {validActions.includes('call') && (
                  <button onClick={handleCall} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition-colors">
                    Call {toCall}
                  </button>
                )}
                {validActions.includes('raise') && (
                  <button onClick={handleRaise} className="px-3 py-1.5 bg-green-700 hover:bg-green-600 text-white rounded-lg text-sm transition-colors">
                    Raise {raiseAmount}
                  </button>
                )}
                {validActions.includes('allIn') && (
                  <button onClick={handleAllIn} className="px-3 py-1.5 bg-yellow-700 hover:bg-yellow-600 text-white rounded-lg text-sm transition-colors">
                    All-In
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Vertical raise slider spanning cards + buttons */}
          {isPlayerTurn && !gameState.foldedPlayers[0] && validActions.includes('raise') && (
            <div className="flex flex-col items-center gap-0.5 self-stretch">
              <span className="text-[0.5rem] text-slate-500">{gameState.chips[0] + gameState.bets[0]}</span>
              <input
                type="range"
                min={getMinRaise(gameState)}
                max={gameState.chips[0] + gameState.bets[0]}
                step={gameState.bigBlind}
                value={raiseAmount}
                onChange={e => setRaiseAmount(Number(e.target.value))}
                className="flex-1"
                style={{ writingMode: 'vertical-lr', direction: 'rtl' }}
              />
              <span className="text-[0.5rem] text-slate-500">{getMinRaise(gameState)}</span>
            </div>
          )}
        </div>

        {/* Hand over / New game */}
        <div className="flex gap-2 justify-center">
          {gameState.phase === 'handOver' && (
            <button
              onClick={handleNextHand}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Next Hand
            </button>
          )}
          {gameStatus === 'playing' && (
            showSlider ? (
              <div className="flex items-center gap-2">
                <div
                  ref={trackRef}
                  className="relative w-40 h-8 bg-slate-800 rounded-full border border-slate-600 select-none touch-none"
                  onMouseMove={e => moveDrag(e.clientX)}
                  onMouseUp={endDrag}
                  onMouseLeave={endDrag}
                  onTouchMove={e => moveDrag(e.touches[0].clientX)}
                  onTouchEnd={endDrag}
                >
                  <div className="absolute inset-0 flex items-center justify-end pr-3 pointer-events-none">
                    <span className="text-[0.6rem] text-red-400/70 font-medium">New Game &raquo;</span>
                  </div>
                  <div
                    className="absolute top-0.5 w-7 h-7 bg-slate-300 rounded-full flex items-center justify-center shadow-md cursor-grab active:cursor-grabbing"
                    style={{ left: `${slideVal / 100 * (160 - 28) + 2}px` }}
                    onMouseDown={startDrag}
                    onTouchStart={startDrag}
                  >
                    <span className="text-xs text-slate-700 font-bold">&raquo;</span>
                  </div>
                </div>
                <button onClick={() => { setShowSlider(false); setSlideVal(0) }} className="text-xs text-slate-500 hover:text-slate-300">&times;</button>
              </div>
            ) : (
              <button
                onClick={() => setShowSlider(true)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-xs transition-colors"
              >
                New Game
              </button>
            )
          )}
        </div>

        {(gameStatus === 'won' || gameStatus === 'lost') && (
          <GameOverModal
            status={gameStatus}
            score={gameState.chips[0]}
            message={gameState.message}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <HoldemHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}
