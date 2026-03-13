/**
 * Blackjack — 6-deck shoe, standard rules with split & double down.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
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
  createBlackjackGame,
  placeBet,
  hit,
  stand,
  doubleDown,
  split,
  newRound,
  scoreHand,
  canSplit,
  canDoubleDown,
  isGameOver,
  didPlayerWin,
  BET_SIZES,
  dealerStep,
  dealerMustHit,
  aiStep,
  takeInsurance,
  declineInsurance,
  takeEvenMoney,
  type BlackjackState,
  type Difficulty,
} from './blackjackEngine'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import { BlackjackMultiplayer } from './BlackjackMultiplayer'

interface SavedState {
  gameState: BlackjackState
  gameStatus: GameStatus
}

// ── Help modal ───────────────────────────────────────────────────────

function BlackjackHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Blackjack</h2>

        {/* Goal */}
        <Sec title="Goal">
          Beat the dealer by getting a hand value closer to <B>21</B> without
          going over. You don&apos;t play against other players at the table —
          only the dealer.
        </Sec>

        {/* Setup */}
        <Sec title="Setup">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>The game uses a <B>6-deck shoe</B> (312 cards). The shoe is
              reshuffled automatically when roughly 25% of the cards remain.</Li>
            <Li>You and the dealer each start with <B>1,000 chips</B>. The
              dealer&apos;s bank is 5x yours.</Li>
            <Li>Chip denominations for betting: <B>10, 25, 50, 100, 500</B>.</Li>
            <Li>You can add <B>1 or 2 AI opponents</B> who play alongside you
              against the dealer.</Li>
          </ul>
        </Sec>

        {/* Card Values */}
        <Sec title="Card Values">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Number cards (2-10)</B> — face value.</Li>
            <Li><B>Face cards (J, Q, K)</B> — worth <B>10</B>.</Li>
            <Li><B>Ace</B> — worth <B>11</B> or <B>1</B>. It counts as 11
              unless that would bust your hand, in which case it automatically
              counts as 1. A hand with an Ace valued at 11 is called a
              &quot;soft&quot; hand.</Li>
          </ul>
        </Sec>

        {/* How to Play */}
        <Sec title="How to Play">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li>Select a <B>chip amount</B> and click <B>Deal</B> to place
              your bet.</li>
            <li>You and the dealer each receive <B>2 cards</B>. Both of yours
              are face-up; the dealer has one face-up and one face-down (the
              &quot;hole card&quot;).</li>
            <li>Choose an action: <B>Hit</B>, <B>Stand</B>, <B>Double Down</B>,
              or <B>Split</B> (when available).</li>
            <li>After you finish, any AI opponents play, then the dealer
              reveals their hole card and draws according to the rules.</li>
          </ol>
        </Sec>

        {/* Actions */}
        <Sec title="Player Actions">
          <div className="space-y-3">
            <ActionItem color="text-blue-400" name="Hit">
              Draw one more card. You can hit as many times as you like. If
              your total exceeds 21, you <B>bust</B> and lose immediately.
            </ActionItem>
            <ActionItem color="text-slate-300" name="Stand">
              Keep your current hand and end your turn.
            </ActionItem>
            <ActionItem color="text-yellow-400" name="Double Down">
              Available only on your <B>first two cards</B>. Your bet is
              doubled, you receive <B>exactly one more card</B>, and your turn
              ends automatically. You must have enough chips to cover the
              additional bet.
            </ActionItem>
            <ActionItem color="text-purple-400" name="Split">
              Available when your first two cards have the <B>same rank</B>.
              The pair is separated into two independent hands, each receiving
              a new second card. Each hand plays with the original bet amount.
              You can split up to <B>4 hands</B> total. You must have enough
              chips to cover the new hand&apos;s bet.
            </ActionItem>
          </div>
        </Sec>

        {/* Blackjack */}
        <Sec title="Blackjack (Natural 21)">
          If your first two cards total exactly <B>21</B> (an Ace + a 10-value
          card), that&apos;s a <B>Blackjack</B>. It pays <B>3:2</B> (1.5x your
          bet). If the dealer also has Blackjack, it&apos;s a <B>push</B> (tie)
          and your bet is returned.
        </Sec>

        {/* Insurance & Even Money */}
        <Sec title="Insurance &amp; Even Money">
          <ul className="space-y-1 text-slate-300">
            <Li>When the dealer&apos;s face-up card is an <B>Ace</B>, you are
              offered <B>Insurance</B> before play continues.</Li>
            <Li>Insurance costs <B>half your original bet</B>. If the dealer has
              Blackjack, insurance pays <B>2:1</B>. If not, the insurance bet is
              lost and play continues normally.</Li>
            <Li>If you have a <B>natural Blackjack</B> and the dealer shows an
              Ace, you are offered <B>Even Money</B> instead — a guaranteed
              <B> 1:1 payout</B> on your bet, avoiding the risk of a push if the
              dealer also has Blackjack.</Li>
          </ul>
        </Sec>

        {/* Dealer Peek */}
        <Sec title="Dealer Peek">
          When the dealer&apos;s face-up card is an <B>Ace</B> or a <B>10-value
          card</B>, the dealer peeks at their hole card to check for Blackjack
          before you act. If the dealer has Blackjack, the hand ends immediately
          — you lose unless you also have Blackjack (push). This prevents you
          from splitting or doubling into a dealer Blackjack.
        </Sec>

        {/* Dealer Rules */}
        <Sec title="Dealer Rules">
          <ul className="space-y-1 text-slate-300">
            <Li>The dealer <B>must hit</B> on 16 or below.</Li>
            <Li>The dealer <B>stands</B> on 17 or above.</Li>
            <Li>On <B>Hard mode</B>, the dealer hits on a soft 17 (Ace + 6),
              making the game tougher.</Li>
            <Li>If the dealer busts, all remaining (non-busted) player hands
              win.</Li>
          </ul>
        </Sec>

        {/* Payouts */}
        <Sec title="Payouts">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Blackjack</B> — pays <B>3:2</B> (bet 100, win 150).</Li>
            <Li><B>Regular win</B> — pays <B>1:1</B> (bet 100, win 100).</Li>
            <Li><B>Push (tie)</B> — your bet is returned, no gain or loss.</Li>
            <Li><B>Lose / Bust</B> — you lose your bet.</Li>
            <Li><B>Insurance</B> — pays <B>2:1</B> if the dealer has Blackjack
              (bet 50 insurance, win 100).</Li>
            <Li><B>Even Money</B> — pays <B>1:1</B> guaranteed when you have
              Blackjack and dealer shows an Ace.</Li>
            <Li><B>Split bonus</B> — win <B>both</B> hands after a split and
              earn an extra <B>+100 chip bonus</B>.</Li>
          </ul>
        </Sec>

        {/* Difficulty */}
        <Sec title="Difficulty">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Easy</B> — dealer stands on all 17s (including soft 17).</Li>
            <Li><B>Hard</B> — dealer hits on soft 17, giving the house a
              stronger edge.</Li>
          </ul>
        </Sec>

        {/* Game Over */}
        <Sec title="Winning &amp; Losing">
          <ul className="space-y-1 text-slate-300">
            <Li>The game ends when either you or the dealer runs out of
              chips.</Li>
            <Li>If <B>you</B> hit 0 chips — you lose.</Li>
            <Li>If the <B>dealer</B> hits 0 chips — you broke the bank and
              win!</Li>
          </ul>
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Stand on 17+</B> — the odds of busting are high if you hit
              on 17 or above.</Li>
            <Li><B>Always split Aces and 8s.</B> Two hands starting with 11 or
              8 are much stronger than a 12 or 16.</Li>
            <Li><B>Never split 10s or 5s.</B> A 20 is almost unbeatable, and
              two 5s make a great double-down hand (10).</Li>
            <Li><B>Double down on 10 or 11</B> when the dealer shows a weak
              card (2-6). You have a strong chance of hitting 20 or 21.</Li>
            <Li><B>Hit on soft 17</B> (Ace + 6). You can&apos;t bust, and
              you&apos;ll likely improve.</Li>
            <Li><B>Assume the hole card is 10.</B> Since 10, J, Q, K all equal
              10, there are more 10-value cards in the deck than any other
              value.</Li>
            <Li><B>Manage your bets.</B> Bet small when losing, and increase
              bets when on a streak.</Li>
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

function ActionItem({ color, name, children }: { color: string; name: string; children: React.ReactNode }) {
  return (
    <div className="pl-3 border-l-2 border-slate-700">
      <div className={`text-xs font-bold ${color} mb-0.5`}>{name}</div>
      <div className="text-xs text-slate-400 leading-relaxed">{children}</div>
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

function BlackjackSinglePlayer({ onGameEnd, onScoreChange, onStateChange: _onStateChange, isMultiplayer }: {
  onGameEnd?: (result: 'win' | 'loss' | 'draw') => void
  onScoreChange?: (chips: number) => void
  onStateChange?: (state: object) => void
  isMultiplayer?: boolean
} = {}) {
  const { load, save, clear } = useGameState<SavedState>('blackjack')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('blackjack'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('blackjack')

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

  const [gameState, setGameState] = useState<BlackjackState>(
    () => {
      if (saved?.gameState) {
        const s = saved.gameState
        return {
          ...s,
          aiPlayers: s.aiPlayers ?? [],
          aiChips: s.aiChips ?? [],
          numOpponents: s.numOpponents ?? 0,
          activeAiIndex: s.activeAiIndex ?? 0,
          dealerChips: s.dealerChips ?? 5000,
          insuranceBet: s.insuranceBet ?? 0,
          playerHasEvenMoney: s.playerHasEvenMoney ?? false,
        }
      }
      return createBlackjackGame()
    }
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedBet, setSelectedBet] = useState(BET_SIZES[0])

  // Persist
  useEffect(() => {
    if (gameStatus !== 'lost' && gameStatus !== 'won') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // SFX on payout + report score
  useEffect(() => {
    if (gameState.phase === 'payout') {
      if (gameState.message.toLowerCase().includes('blackjack')) sfx.play('blackjack')
      else if (gameState.message.toLowerCase().includes('bust')) sfx.play('bust')
      onScoreChange?.(gameState.chips)
    }
  }, [gameState.phase])

  // Dealer draws one card at a time
  useEffect(() => {
    if (gameState.phase !== 'dealerTurn') return
    const delay = dealerMustHit(gameState) ? 800 : 600
    const timer = setTimeout(() => {
      setGameState(prev => {
        const next = dealerStep(prev)
        if (next.phase === 'payout') sfx.play(next.message.toLowerCase().includes('bust') ? 'bust' : 'deal')
        return next
      })
    }, delay)
    return () => clearTimeout(timer)
  }, [gameState.phase, gameState.dealerHand.length])

  // AI opponents play one step at a time
  useEffect(() => {
    if (gameState.phase !== 'aiTurn') return
    const timer = setTimeout(() => {
      setGameState(prev => aiStep(prev))
    }, 700)
    return () => clearTimeout(timer)
  }, [gameState.phase, gameState.activeAiIndex, gameState.aiPlayers])

  // Check for game over (player broke or dealer broke)
  useEffect(() => {
    if (isGameOver(gameState)) {
      const won = didPlayerWin(gameState)
      setGameStatus(won ? 'won' : 'lost')
      onGameEnd?.(won ? 'win' : 'loss')
      clear()
    }
  }, [gameState, clear, onGameEnd])

  const handleDifficulty = useCallback((d: string) => {
    const newState = createBlackjackGame(d as Difficulty, gameState.numOpponents)
    setGameState(newState)
    setGameStatus('playing')
    clear()
  }, [clear, gameState.numOpponents])

  const handlePlaceBet = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('bet')
    setGameState(prev => {
      const next = placeBet(prev, selectedBet)
      return next
    })
    sfx.play('deal')
  }, [selectedBet])

  const handleHit = useCallback(() => { sfx.play('hit'); setGameState(prev => hit(prev)) }, [])
  const handleStand = useCallback(() => setGameState(prev => stand(prev)), [])
  const handleDouble = useCallback(() => setGameState(prev => doubleDown(prev)), [])
  const handleSplit = useCallback(() => setGameState(prev => split(prev)), [])

  const handleInsurance = useCallback(() => { setGameState(prev => takeInsurance(prev)) }, [])
  const handleNoInsurance = useCallback(() => { setGameState(prev => declineInsurance(prev)) }, [])
  const handleEvenMoney = useCallback(() => { setGameState(prev => takeEvenMoney(prev)) }, [])

  const handleNextRound = useCallback(() => {
    setGameState(prev => newRound(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    const newState = createBlackjackGame(gameState.difficulty, gameState.numOpponents)
    setGameState(newState)
    setGameStatus('playing')
    clear()
  }, [gameState.difficulty, gameState.numOpponents, clear])

  const handleOpponents = useCallback((n: number) => {
    const newState = createBlackjackGame(gameState.difficulty, n)
    setGameState(newState)
    setGameStatus('playing')
    clear()
  }, [gameState.difficulty, clear])

  const dealerScore = scoreHand(gameState.dealerHand.filter(c => c.faceUp))
  const activeHand = gameState.playerHands[gameState.activeHandIndex]
  const activeScore = activeHand ? scoreHand(activeHand.cards) : null

  const controls = (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleDifficulty('easy')}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${gameState.difficulty === 'easy' ? 'bg-emerald-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'}`}
          >
            Easy
          </button>
          <button
            onClick={() => handleDifficulty('hard')}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${gameState.difficulty === 'hard' ? 'bg-red-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'}`}
          >
            Hard
          </button>
        </div>
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
      <div className="flex items-center justify-center gap-1">
        <span className="text-[0.6rem] text-slate-500">Players:</span>
        {[0, 1, 2].map(n => (
          <button
            key={n}
            onClick={() => handleOpponents(n)}
            className={`px-2 py-0.5 rounded text-[0.6rem] font-medium transition-colors ${gameState.numOpponents === n ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'}`}
          >
            {n + 1}
          </button>
        ))}
      </div>
    </div>
  )

  return (
    <GameLayout title="Blackjack" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-2 sm:space-y-4">
        {/* Dealer area */}
        <div className="text-center">
          <span className="text-[0.65rem] sm:text-xs text-slate-400 block">
            Dealer {gameState.phase === 'payout' || gameState.phase === 'dealerTurn' ? `(${scoreHand(gameState.dealerHand).total})` : dealerScore.total > 0 ? `(${dealerScore.total})` : ''}
          </span>
          <div className="text-[0.55rem] text-yellow-400">{gameState.dealerChips ?? 5000}</div>
          <div className="flex gap-1.5 sm:gap-2 justify-center min-h-[5rem] sm:min-h-[7rem]">
            {gameState.dealerHand.map((card, i) => (
              <div key={i} className={CARD_SIZE}>
                {card.faceUp ? <CardFace card={card} /> : <CardBack />}
              </div>
            ))}
          </div>
        </div>

        {/* Middle table: AI sidebars + center actions */}
        <div className="flex w-full items-start gap-2">
          {/* Left AI (P2) — cards rotated, tops pointing left */}
          {gameState.numOpponents >= 1 ? (() => {
            const ai = gameState.aiPlayers[0]
            if (!ai) return <div className="w-16 flex-shrink-0" />
            const aiScore = scoreHand(ai.cards)
            const isActive = gameState.phase === 'aiTurn' && gameState.activeAiIndex === 0
            return (
              <div className={`w-16 flex-shrink-0 text-center ${isActive ? '' : 'opacity-70'}`}>
                <span className="text-[0.6rem] text-slate-400 block">P2</span>
                <div className="text-[0.55rem] text-yellow-400">{gameState.aiChips[0] ?? 1000}</div>
                <span className="text-[0.6rem] text-slate-500 block">({aiScore.total}{aiScore.isBust ? ' BUST' : ''})</span>
                <div className="flex flex-col items-center gap-0.5 mt-0.5">
                  {ai.cards.map((card, ci) => (
                    <div key={ci} className="w-10 h-[1.75rem] sm:w-12 sm:h-8">
                      <CardFace card={card} mini textRotation={-90} />
                    </div>
                  ))}
                </div>
                {gameState.phase === 'payout' && ai.result && (
                  <span className={`text-[0.55rem] font-medium block mt-0.5 ${ai.result === 'win' ? 'text-green-400' : ai.result === 'lose' || ai.result === 'bust' ? 'text-red-400' : 'text-slate-400'}`}>
                    {ai.result === 'win' ? `+${ai.bet}` : ai.result === 'bust' ? 'Bust' : ai.result === 'lose' ? `-${ai.bet}` : 'Push'}
                  </span>
                )}
              </div>
            )
          })() : null}

          {/* Center — message + all action buttons */}
          <div className="flex-1 flex flex-col items-center gap-2">
            <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

            {/* Betting phase */}
            {gameState.phase === 'betting' && (
              <div className="flex flex-col items-center gap-2">
                <div className="flex gap-1.5">
                  {BET_SIZES.map(bet => (
                    <button
                      key={bet}
                      onClick={() => setSelectedBet(bet)}
                      disabled={bet > gameState.chips}
                      className={`px-2.5 py-1 text-xs rounded font-mono transition-colors ${
                        selectedBet === bet
                          ? 'bg-yellow-600 text-white'
                          : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                      } disabled:opacity-30 disabled:cursor-not-allowed`}
                    >
                      {bet}
                    </button>
                  ))}
                </div>
                <button
                  onClick={handlePlaceBet}
                  disabled={selectedBet > gameState.chips}
                  className="px-5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
                >
                  Deal ({selectedBet} chips)
                </button>
              </div>
            )}

            {/* Insurance / Even Money phase */}
            {gameState.phase === 'insurance' && (
              <div className="flex flex-wrap gap-1.5 justify-center">
                {gameState.playerHasEvenMoney ? (
                  <>
                    <button onClick={handleEvenMoney} className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm transition-colors">
                      Even Money
                    </button>
                    <button onClick={handleNoInsurance} className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition-colors">
                      No Thanks
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={handleInsurance}
                      disabled={Math.floor(gameState.playerHands[0]?.bet / 2) > gameState.chips}
                      className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Insurance ({Math.floor((gameState.playerHands[0]?.bet ?? 0) / 2)})
                    </button>
                    <button onClick={handleNoInsurance} className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition-colors">
                      No Insurance
                    </button>
                  </>
                )}
              </div>
            )}

            {/* Player turn actions */}
            {gameState.phase === 'playerTurn' && (
              <div className="flex flex-wrap gap-1.5 justify-center">
                <button onClick={handleHit} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition-colors">
                  Hit
                </button>
                <button onClick={handleStand} className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition-colors">
                  Stand
                </button>
                {canDoubleDown(gameState) && (
                  <button onClick={handleDouble} className="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg text-sm transition-colors">
                    Double
                  </button>
                )}
                {canSplit(gameState) && (
                  <button onClick={handleSplit} className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm transition-colors">
                    Split
                  </button>
                )}
              </div>
            )}

            {/* Payout — next round */}
            {gameState.phase === 'payout' && !isGameOver(gameState) && (
              <button
                onClick={handleNextRound}
                className="px-5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Next Hand
              </button>
            )}
          </div>

          {/* Right AI (P3) — cards rotated, tops pointing right */}
          {gameState.numOpponents >= 2 ? (() => {
            const ai = gameState.aiPlayers[1]
            if (!ai) return <div className="w-16 flex-shrink-0" />
            const aiScore = scoreHand(ai.cards)
            const isActive = gameState.phase === 'aiTurn' && gameState.activeAiIndex === 1
            return (
              <div className={`w-16 flex-shrink-0 text-center ${isActive ? '' : 'opacity-70'}`}>
                <span className="text-[0.6rem] text-slate-400 block">P3</span>
                <div className="text-[0.55rem] text-yellow-400">{gameState.aiChips[1] ?? 1000}</div>
                <span className="text-[0.6rem] text-slate-500 block">({aiScore.total}{aiScore.isBust ? ' BUST' : ''})</span>
                <div className="flex flex-col items-center gap-0.5 mt-0.5">
                  {ai.cards.map((card, ci) => (
                    <div key={ci} className="w-10 h-[1.75rem] sm:w-12 sm:h-8">
                      <CardFace card={card} mini textRotation={90} />
                    </div>
                  ))}
                </div>
                {gameState.phase === 'payout' && ai.result && (
                  <span className={`text-[0.55rem] font-medium block mt-0.5 ${ai.result === 'win' ? 'text-green-400' : ai.result === 'lose' || ai.result === 'bust' ? 'text-red-400' : 'text-slate-400'}`}>
                    {ai.result === 'win' ? `+${ai.bet}` : ai.result === 'bust' ? 'Bust' : ai.result === 'lose' ? `-${ai.bet}` : 'Push'}
                  </span>
                )}
              </div>
            )
          })() : null}
        </div>

        {/* Player hands (You — center bottom) */}
        <div className="text-center space-y-2">
          <div className="text-[0.55rem] text-yellow-400">{gameState.chips}</div>
          {gameState.playerHands.map((hand, hIdx) => {
            const hScore = scoreHand(hand.cards)
            const isActive = hIdx === gameState.activeHandIndex && gameState.phase === 'playerTurn'
            return (
              <div key={hIdx} className={`text-center ${isActive ? '' : 'opacity-60'}`}>
                {gameState.playerHands.length > 1 && (
                  <span className="text-xs text-slate-400 mb-1 block">
                    Hand {hIdx + 1} (Bet: {hand.bet}) — {hScore.total}{hScore.isSoft ? ' soft' : ''}{hScore.isBust ? ' BUST' : ''}
                  </span>
                )}
                <div className="flex gap-2 justify-center">
                  {hand.cards.map((card, ci) => (
                    <div key={ci} className={`${CARD_SIZE} ${isActive ? 'ring-1 ring-blue-400/40 rounded-md' : ''}`}>
                      <CardFace card={card} />
                    </div>
                  ))}
                </div>
                {/* Score + result shown during payout and single-hand play */}
                {hand.cards.length > 0 && (gameState.phase === 'payout' || gameState.phase === 'dealerTurn') && (
                  <div className="mt-0.5">
                    <span className="text-[0.6rem] text-slate-500">({hScore.total}{hScore.isBust ? ' BUST' : ''})</span>
                    {gameState.phase === 'payout' && hand.result && (
                      <span className={`text-[0.6rem] font-medium ml-1 ${hand.result === 'win' ? 'text-green-400' : hand.result === 'lose' || hand.result === 'bust' ? 'text-red-400' : 'text-slate-400'}`}>
                        {hand.result === 'win' ? `+${hand.bet}` : hand.result === 'bust' ? 'Bust' : hand.result === 'lose' ? `-${hand.bet}` : 'Push'}
                      </span>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Player score during play */}
        {activeScore && gameState.phase === 'playerTurn' && gameState.playerHands.length === 1 && (
          <p className="text-xs text-slate-400">
            {activeScore.total}{activeScore.isSoft ? ' (soft)' : ''}
          </p>
        )}

        {/* Game over */}
        {(gameStatus === 'lost' || gameStatus === 'won') && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            message={gameStatus === 'won' ? 'You broke the bank!' : "You're out of chips!"}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>

      {/* Help modal */}
      {showHelp && <BlackjackHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (best_score — highest chip count wins) ─────────────

function BlackjackRaceWrapper({ roomId, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, opponentLevelUp, broadcastState, reportFinish, reportScore, leaveRoom } =
    useRaceMode(roomId, 'best_score')
  const finishedRef = useRef(false)
  const latestChips = useRef(1000)

  const handleScoreChange = useCallback((chips: number) => {
    latestChips.current = chips
    reportScore(chips)
  }, [reportScore])

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw') => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish(result === 'draw' ? 'loss' : result, latestChips.current)
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
      <BlackjackSinglePlayer onGameEnd={handleGameEnd} onScoreChange={handleScoreChange} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function Blackjack() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'blackjack',
        gameName: 'Blackjack',
        modes: ['vs', 'best_score'],
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: {
          vs: 'Same table, same dealer',
          best_score: 'Highest chip count wins',
        },
      }}
      renderSinglePlayer={() => <BlackjackSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <BlackjackMultiplayer
            roomId={roomId}
            players={players}
            playerNames={playerNames}
            difficulty={roomConfig.difficulty as string}
            onLeave={onLeave}
          />
        ) : (
          <BlackjackRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
        )
      }
    />
  )
}
