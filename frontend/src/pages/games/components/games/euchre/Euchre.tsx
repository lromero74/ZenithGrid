/**
 * Euchre — 4-player partnership trick-taking card game.
 *
 * 24-card deck, bowers (J of trump & same-color J), trump selection via two rounds.
 * Teams: You+North vs East+West. First to 10 points wins.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SLOT_V, CARD_SLOT_H } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { getSuitSymbol } from '../../../utils/cardUtils'
import type { Suit } from '../../../utils/cardUtils'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { EuchreMultiplayer } from './EuchreMultiplayer'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import {
  createEuchreGame,
  orderUp,
  pass,
  nameTrump,
  dealerDiscard,
  playCard,
  advanceAi,
  getPlayableCards,
  aiTrumpSelection,
  aiDealerDiscard,
  nextHand,
  PLAYER_NAMES,
  TEAM_NAMES,
  type EuchreState,
} from './EuchreEngine'

interface SavedState {
  gameState: EuchreState
  gameStatus: GameStatus
}

const SUIT_OPTIONS: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']

const AI_DELAY = 600

// ── Help modal ─────────────────────────────────────────────────────

function EuchreHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Euchre</h2>

        {/* Overview */}
        <Sec title="Goal">
          Be the first team to reach <B>10 points</B>. Euchre is a 4-player
          partnership trick-taking game. You are paired with <B>North</B> against
          <B> East</B> and <B>West</B>.
        </Sec>

        {/* The Deck */}
        <Sec title="The Deck">
          Euchre uses a <B>24-card deck</B> consisting of 9, 10, Jack, Queen,
          King, and Ace in each of the four suits. Lower cards (2-8) are not used.
        </Sec>

        {/* Dealing */}
        <Sec title="Dealing">
          Each player is dealt <B>5 cards</B>. The remaining 4 cards form the
          <B> kitty</B>, and the top card is flipped face-up. The dealer rotates
          clockwise each hand. Play always begins with the player to the
          left of the dealer.
        </Sec>

        {/* Trump Selection */}
        <Sec title="Trump Selection">
          Trump is chosen in two rounds:
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li><B>Round 1</B> — each player (starting left of dealer) may
              <B> order up</B> the flipped card&apos;s suit as trump, or
              <B> pass</B>. If someone orders up, the dealer picks up the
              flipped card and discards one card from their hand.</li>
            <li><B>Round 2</B> — if all players pass in round 1, each player
              may <B>name any suit except</B> the flipped card&apos;s suit as
              trump, or pass. The dealer <B>cannot pass</B> in round 2 (they
              are &quot;stuck&quot; and must name a suit).</li>
          </ol>
        </Sec>

        {/* Bowers */}
        <Sec title="Bowers (Highest Cards)">
          The two Jacks of the trump color are the most powerful cards:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Right Bower</B> — the Jack of the trump suit. This is the
              <B> highest card in the game</B>.</Li>
            <Li><B>Left Bower</B> — the Jack of the same color as trump (e.g.,
              if hearts is trump, the Jack of diamonds is the Left Bower). This
              is the <B>second highest card</B> and counts as a trump card, not
              its printed suit.</Li>
          </ul>
        </Sec>

        {/* Card Ranking */}
        <Sec title="Card Ranking">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Trump suit</B> (highest to lowest): Right Bower, Left Bower,
              Ace, King, Queen, 10, 9.</Li>
            <Li><B>Non-trump suits</B> (highest to lowest): Ace, King, Queen,
              Jack, 10, 9.</Li>
          </ul>
        </Sec>

        {/* Playing Tricks */}
        <Sec title="Playing Tricks">
          The player to the left of the dealer leads the first trick.
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>The lead player plays any card. The suit of that card becomes the
              <B> led suit</B> for the trick.</Li>
            <Li>Other players <B>must follow the led suit</B> if they have a card
              of that suit (the Left Bower counts as trump, not its printed suit).</Li>
            <Li>If you have no cards of the led suit, you may play <B>any card</B>,
              including trump.</Li>
            <Li>The highest trump card wins the trick. If no trump was played,
              the highest card of the led suit wins.</Li>
            <Li>The trick winner leads the next trick.</Li>
          </ul>
        </Sec>

        {/* Scoring */}
        <Sec title="Scoring">
          After all 5 tricks are played, the hand is scored. The team that called
          trump is the <B>making team</B>.
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>3 or 4 tricks</B> by the makers — <B>1 point</B>.</Li>
            <Li><B>All 5 tricks (march)</B> by the makers — <B>2 points</B>.</Li>
            <Li><B>Euchre</B> — if the makers win fewer than 3 tricks, the
              defending team scores <B>2 points</B>.</Li>
            <Li><B>Lone march</B> — if a player goes alone and takes all 5
              tricks, their team scores <B>4 points</B>.</Li>
          </ul>
        </Sec>

        {/* Going Alone */}
        <Sec title="Going Alone">
          When calling trump, a player may choose to <B>go alone</B>, meaning
          their partner sits out the hand. If the lone player takes all 5 tricks,
          their team earns <B>4 points</B> instead of 2. If they take 3 or 4,
          they still earn 1 point. Going alone is a high-risk, high-reward play.
        </Sec>

        {/* Dealer Discard */}
        <Sec title="Dealer Discard">
          When trump is ordered up in round 1, the dealer <B>picks up the
          flipped card</B> and adds it to their hand (giving them 6 cards).
          The dealer must then <B>discard one card</B> to return to 5 cards
          before play begins.
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Count your trump</B> — with 3 or more trump cards (including
              bowers), consider ordering up or naming trump.</Li>
            <Li><B>Lead with your Right Bower</B> — it cannot be beaten and
              forces opponents to lose trump cards.</Li>
            <Li><B>Lead off-suit Aces</B> — they win tricks without spending
              trump.</Li>
            <Li><B>Watch your partner</B> — if your partner is winning the
              trick, play your lowest card to save strong cards for later.</Li>
            <Li><B>Be careful calling trump as the maker</B> — getting euchred
              gives your opponents 2 points.</Li>
            <Li><B>Remember the Left Bower</B> — it belongs to the trump suit,
              not its printed suit. This affects which cards you must follow
              with.</Li>
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

function EuchreSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<SavedState>('euchre')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('euchre'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('euchre')

  const [gameState, setGameState] = useState<EuchreState>(
    () => saved?.gameState ?? createEuchreGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [showHelp, setShowHelp] = useState(false)
  const aiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // SFX on trick completion
  const prevTrickLen = useRef(0)
  useEffect(() => {
    if (prevTrickLen.current > 0 && gameState.currentTrick.length === 0) sfx.play('trick_won')
    prevTrickLen.current = gameState.currentTrick.length
  }, [gameState.currentTrick.length])

  // Persist state
  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Detect game over
  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const result = gameState.teamScores[0] > gameState.teamScores[1] ? 'won' : 'lost'
      setGameStatus(result)
      onGameEnd?.(result === 'won' ? 'win' : 'loss')
      clear()
    }
  }, [gameState, clear, onGameEnd])

  // AI auto-advance: trump selection, dealer discard, and playing
  useEffect(() => {
    if (gameState.phase === 'gameOver' || gameState.phase === 'handOver') return
    if (gameState.currentPlayer === 0) return

    // AI needs to act
    aiTimerRef.current = setTimeout(() => {
      setGameState(prev => {
        if (prev.currentPlayer === 0) return prev

        if (prev.phase === 'trumpRound1' || prev.phase === 'trumpRound2') {
          return aiTrumpSelection(prev)
        }

        if (prev.phase === 'dealerDiscard') {
          return aiDealerDiscard(prev)
        }

        if (prev.phase === 'playing') {
          return advanceAi(prev)
        }

        return prev
      })
    }, AI_DELAY)

    return () => {
      if (aiTimerRef.current) clearTimeout(aiTimerRef.current)
    }
  }, [gameState.currentPlayer, gameState.phase, gameState.currentTrick.length])

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (aiTimerRef.current) clearTimeout(aiTimerRef.current)
    }
  }, [])

  const handleOrderUp = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    setGameState(prev => orderUp(prev))
  }, [])

  const handlePass = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    setGameState(prev => pass(prev))
  }, [])

  const handleNameTrump = useCallback((suit: Suit) => {
    setGameState(prev => nameTrump(prev, suit))
  }, [])

  const handleDealerDiscard = useCallback((i: number) => {
    setGameState(prev => dealerDiscard(prev, i))
  }, [])

  const handlePlay = useCallback((i: number) => {
    sfx.play('play')
    setGameState(prev => playCard(prev, i))
  }, [])

  const handleNextHand = useCallback(() => {
    sfx.play('hand_won')
    setGameState(prev => nextHand(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createEuchreGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const isHumanTurn = gameState.currentPlayer === 0
  const isPlaying = gameState.phase === 'playing' && isHumanTurn
  const isTrumpRound1 = gameState.phase === 'trumpRound1' && isHumanTurn
  const isTrumpRound2 = gameState.phase === 'trumpRound2' && isHumanTurn
  const isDealerDiscard = gameState.phase === 'dealerDiscard' && isHumanTurn

  const playableIndices = isPlaying
    ? getPlayableCards(gameState.hands[0], gameState.ledSuit, gameState.trumpSuit!)
    : []

  // Use original hand for play/discard indices (unsorted in state)
  const humanHand = gameState.hands[0]

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex gap-3">
        <span className="text-blue-400">{TEAM_NAMES[0]}: {gameState.teamScores[0]}</span>
        <span className="text-red-400">{TEAM_NAMES[1]}: {gameState.teamScores[1]}</span>
      </div>
      <div className="flex gap-2 text-slate-400">
        {gameState.trumpSuit && (
          <span className="text-yellow-400">
            Trump: {getSuitSymbol(gameState.trumpSuit)}
          </span>
        )}
        <span>Dealer: {PLAYER_NAMES[gameState.dealer]}</span>
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
  )

  return (
    <GameLayout title="Euchre" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* North (Partner) */}
        <div className="text-center">
          <span className="text-xs text-blue-400">North (Partner) ({gameState.hands[2].length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[2].map((_, i) => (
              <div key={i} className={CARD_SLOT_V}><CardBack /></div>
            ))}
          </div>
        </div>

        {/* West + Trick area + East */}
        <div className="flex w-full items-center gap-2">
          {/* West (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">West ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>

          {/* Trick area + flipped card */}
          <div className="flex-1 relative h-36 sm:h-48">
            {/* Flipped card during trump selection */}
            {(gameState.phase === 'trumpRound1' || gameState.phase === 'trumpRound2') && (
              <div className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 ${CARD_SIZE}`}>
                {gameState.phase === 'trumpRound1' ? (
                  <CardFace card={gameState.flippedCard} />
                ) : (
                  <CardBack />
                )}
              </div>
            )}

            {/* Current trick cards */}
            {gameState.phase === 'playing' && gameState.currentTrick.map((play) => {
              const positions = [
                'bottom-0 left-1/2 -translate-x-1/2',  // South (You)
                'right-0 top-1/2 -translate-y-1/2',     // East
                'top-0 left-1/2 -translate-x-1/2',      // North
                'left-0 top-1/2 -translate-y-1/2',      // West
              ]
              return (
                <div key={`${play.player}-${play.card.rank}-${play.card.suit}`}
                  className={`absolute ${positions[play.player]} ${CARD_SIZE}`}
                >
                  <CardFace card={play.card} />
                </div>
              )
            })}

            {/* Trump indicator in center during play */}
            {gameState.phase === 'playing' && gameState.trumpSuit && gameState.currentTrick.length === 0 && (
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
                <span className="text-2xl">
                  {getSuitSymbol(gameState.trumpSuit)}
                </span>
                <p className="text-[0.6rem] text-slate-500 mt-0.5">Trump</p>
              </div>
            )}

            {/* Trick counts during play */}
            {gameState.phase === 'playing' && (
              <div className="absolute bottom-0 right-0 text-[0.55rem] text-slate-500">
                {PLAYER_NAMES.map((name, i) => (
                  <span key={i} className="mr-1">{name.charAt(0)}:{gameState.tricksTaken[i]}</span>
                ))}
              </div>
            )}
          </div>

          {/* East (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">East ({gameState.hands[1].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[1].map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Trump Round 1 controls */}
        {isTrumpRound1 && (
          <div className="flex gap-2">
            <button
              onClick={handleOrderUp}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Order Up ({getSuitSymbol(gameState.flippedCard.suit)})
            </button>
            <button
              onClick={handlePass}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium transition-colors"
            >
              Pass
            </button>
          </div>
        )}

        {/* Trump Round 2 controls — suit picker */}
        {isTrumpRound2 && (
          <div className="flex flex-col items-center gap-2">
            <span className="text-xs text-slate-400">
              Name trump (not {getSuitSymbol(gameState.flippedCard.suit)} {gameState.flippedCard.suit})
            </span>
            <div className="flex gap-2">
              {SUIT_OPTIONS.filter(s => s !== gameState.flippedCard.suit).map(suit => (
                <button
                  key={suit}
                  onClick={() => handleNameTrump(suit)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    suit === 'hearts' || suit === 'diamonds'
                      ? 'bg-red-700 hover:bg-red-600 text-white'
                      : 'bg-slate-700 hover:bg-slate-600 text-white'
                  }`}
                >
                  {getSuitSymbol(suit)} {suit}
                </button>
              ))}
            </div>
            {gameState.currentPlayer !== gameState.dealer && (
              <button
                onClick={handlePass}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium transition-colors"
              >
                Pass
              </button>
            )}
          </div>
        )}

        {/* Dealer discard prompt */}
        {isDealerDiscard && (
          <span className="text-xs text-yellow-400">Click a card to discard</span>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {humanHand.map((card, i) => {
            const isValid = isPlaying
              ? playableIndices.includes(i)
              : isDealerDiscard
            return (
              <div
                key={`${card.rank}-${card.suit}-${i}`}
                className={`${CARD_SIZE} transition-transform ${
                  isValid ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
                }`}
                onClick={() => {
                  if (isPlaying && playableIndices.includes(i)) handlePlay(i)
                  else if (isDealerDiscard) handleDealerDiscard(i)
                }}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {/* Hand over — next hand */}
        {gameState.phase === 'handOver' && (
          <button
            onClick={handleNextHand}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Next Hand
          </button>
        )}

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost') && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            score={gameState.teamScores[0]}
            message={gameState.message}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>

      {/* Help modal */}
      {showHelp && <EuchreHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-win against AI) ─────────────────────────

function EuchreRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
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
      <EuchreSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function Euchre() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'euchre',
        gameName: 'Euchre',
        modes: ['vs', 'first_to_win'],
        hasDifficulty: true,
        modeDescriptions: {
          vs: '2 humans + 2 AI partnerships',
          first_to_win: 'First to win a round wins',
        },
      }}
      renderSinglePlayer={() => <EuchreSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <EuchreMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
        ) : (
          <EuchreRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
        )
      }
    />
  )
}
