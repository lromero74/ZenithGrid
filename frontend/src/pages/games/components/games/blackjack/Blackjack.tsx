/**
 * Blackjack — 6-deck shoe, standard rules with split & double down.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
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
  type BlackjackState,
  type Difficulty,
} from './blackjackEngine'

interface SavedState {
  gameState: BlackjackState
  gameStatus: GameStatus
}

export default function Blackjack() {
  const { load, save, clear } = useGameState<SavedState>('blackjack')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('blackjack'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('blackjack')

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

  // SFX on payout
  useEffect(() => {
    if (gameState.phase === 'payout') {
      if (gameState.message.toLowerCase().includes('blackjack')) sfx.play('blackjack')
      else if (gameState.message.toLowerCase().includes('bust')) sfx.play('bust')
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
      setGameStatus(didPlayerWin(gameState) ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

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
        <MusicToggle music={music} sfx={sfx} />
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
        {(gameStatus === 'lost' || gameStatus === 'won') && (
          <GameOverModal
            status={gameStatus}
            message={gameStatus === 'won' ? 'You broke the bank!' : "You're out of chips!"}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
