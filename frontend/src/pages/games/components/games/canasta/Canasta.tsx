/**
 * Canasta — 4-player partnership card game with melds and canastas.
 *
 * Double deck (108 cards), 2v2 teams. Meld groups of same rank.
 * Canasta = 7+ cards. First team to 5000 wins.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SLOT_V, CARD_SLOT_H } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import type { Card } from '../../../utils/cardUtils'
import { getRankDisplay, getSuitSymbol, getCardColor } from '../../../utils/cardUtils'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import {
  createCanastaGame,
  drawFromStock,
  pickupDiscardPile,
  meldCards,
  discard,
  goOut,
  aiTurn,
  newRound,
  isWild,
  TEAM_NAMES,
  type CanastaState,
  type CanastaMeld,
} from './CanastaEngine'

// ── Types ────────────────────────────────────────────────────────────

interface SavedState {
  gameState: CanastaState
  gameStatus: GameStatus
}

// ── JokerCard ────────────────────────────────────────────────────────

function JokerCard() {
  return (
    <div className="w-full h-full rounded-md bg-slate-50 border border-slate-300 shadow-md flex flex-col items-center justify-center select-none">
      <span className="text-purple-600 font-bold text-xs">JKR</span>
      <span className="text-2xl">{'\uD83C\uDCCF'}</span>
    </div>
  )
}

// ── Card renderer ────────────────────────────────────────────────────

function GameCard({ card, selected, onClick, disabled }: {
  card: Card
  selected?: boolean
  onClick?: () => void
  disabled?: boolean
}) {
  return (
    <div
      className={`${CARD_SIZE} transition-transform ${
        !disabled ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
      } ${selected ? '-translate-y-2' : ''}`}
      onClick={disabled ? undefined : onClick}
    >
      {card.rank === 0 ? <JokerCard /> : (
        <CardFace card={card} selected={selected} />
      )}
    </div>
  )
}

// ── Meld display ─────────────────────────────────────────────────────

function MeldDisplay({ meld }: { meld: CanastaMeld }) {
  const borderClass = meld.isCanasta
    ? meld.isNatural
      ? 'border-yellow-400 bg-yellow-400/10'   // Gold for natural canasta
      : 'border-slate-400 bg-slate-400/10'      // Silver for mixed canasta
    : 'border-slate-600 bg-slate-800/50'

  return (
    <div className={`inline-flex items-center gap-0.5 p-1 rounded border ${borderClass}`}>
      {meld.cards.slice(0, 4).map((card, i) => (
        <div key={i} className="w-6 h-9 flex-shrink-0">
          {card.rank === 0 ? (
            <div className="w-full h-full rounded-sm bg-slate-50 border border-slate-300 flex items-center justify-center">
              <span className="text-[0.4rem] text-purple-600 font-bold">JKR</span>
            </div>
          ) : (
            <div className={`w-full h-full rounded-sm bg-slate-50 border border-slate-300 flex items-center justify-center text-[0.5rem] font-bold ${
              getCardColor(card) === 'red' ? 'text-red-500' : 'text-slate-900'
            }`}>
              {getRankDisplay(card.rank)}{getSuitSymbol(card.suit)}
            </div>
          )}
        </div>
      ))}
      {meld.cards.length > 4 && (
        <span className="text-[0.5rem] text-slate-400 px-0.5">+{meld.cards.length - 4}</span>
      )}
      {meld.isCanasta && (
        <span className={`text-[0.5rem] font-bold px-0.5 ${
          meld.isNatural ? 'text-yellow-400' : 'text-slate-300'
        }`}>
          {meld.isNatural ? 'NAT' : 'MIX'}
        </span>
      )}
    </div>
  )
}

// ── Help modal ──────────────────────────────────────────────────────

function CanastaHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Canasta</h2>

        {/* Goal */}
        <Sec title="Goal">
          Be the first team to reach <B>5,000 points</B> across multiple rounds.
          You play with a partner (North) against two opponents (East &amp; West).
          Score points by forming <B>melds</B> (groups of same-rank cards) and
          completing <B>canastas</B> (melds of 7 or more cards).
        </Sec>

        {/* Setup */}
        <Sec title="Setup">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Uses a <B>double deck</B> (108 cards) including <B>4 jokers</B>.</Li>
            <Li><B>4 players</B> in 2 teams: You &amp; North vs East &amp; West.</Li>
            <Li>Each player is dealt <B>11 cards</B>. One card starts the discard pile.</Li>
            <Li><B>Red 3s</B> are automatically played to the table and replaced from the stock.</Li>
          </ul>
        </Sec>

        {/* Card Values */}
        <Sec title="Card Point Values">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Jokers</B> — <B>50</B> points (wild).</Li>
            <Li><B>Aces &amp; 2s</B> — <B>20</B> points. 2s are wild.</Li>
            <Li><B>8 through King</B> — <B>10</B> points each.</Li>
            <Li><B>4 through 7</B> — <B>5</B> points each.</Li>
            <Li><B>Black 3s</B> — <B>5</B> points. Cannot be melded (but block pile pickup when discarded).</Li>
            <Li><B>Red 3s</B> — <B>100</B> point bonus each (or penalty if your team has no melds). All 4 = <B>800</B>.</Li>
          </ul>
        </Sec>

        {/* Wild Cards */}
        <Sec title="Wild Cards">
          <B>Jokers</B> and <B>2s</B> are wild and can substitute for natural cards
          in melds. A meld can have at most <B>3 wild cards</B> and must always
          contain more natural cards than wilds.
        </Sec>

        {/* Melds & Canastas */}
        <Sec title="Melds &amp; Canastas">
          <ul className="space-y-1 text-slate-300">
            <Li>A <B>meld</B> is 3 or more cards of the same rank (no runs/sequences).</Li>
            <Li>Must contain <B>more natural cards than wild cards</B>, with a max of 3 wilds.</Li>
            <Li>A <B>canasta</B> is a meld with <B>7 or more</B> cards.</Li>
            <Li>A <B>natural canasta</B> (no wilds) earns a <B>500-point</B> bonus — shown with a gold border.</Li>
            <Li>A <B>mixed canasta</B> (contains wilds) earns a <B>300-point</B> bonus — shown with a silver border.</Li>
            <Li>Both partners contribute to the same team melds.</Li>
          </ul>
        </Sec>

        {/* Initial Meld */}
        <Sec title="Initial Meld Requirement">
          Your team&apos;s <B>first meld</B> of each round must meet a minimum point
          threshold based on your team&apos;s total score:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Score under 1,500 — first meld needs <B>50+ points</B>.</Li>
            <Li>Score 1,500 to 2,999 — first meld needs <B>90+ points</B>.</Li>
            <Li>Score 3,000+ — first meld needs <B>120+ points</B>.</Li>
          </ul>
        </Sec>

        {/* How to Play */}
        <Sec title="How to Play">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li><B>Draw</B> — take <B>2 cards</B> from the stock, or pick up the
              entire discard pile (if allowed).</li>
            <li><B>Meld</B> — optionally play melds from your hand (select cards,
              then click &quot;Meld Selected&quot;). You can meld multiple times per turn.</li>
            <li><B>Discard</B> — end your turn by discarding <B>1 card</B> to the
              discard pile.</li>
          </ol>
        </Sec>

        {/* Picking Up the Pile */}
        <Sec title="Picking Up the Discard Pile">
          <ul className="space-y-1 text-slate-300">
            <Li>Select <B>2 cards</B> from your hand that form a valid meld with the
              top card, then click &quot;Pick Up Pile.&quot;</Li>
            <Li>You get <B>all cards</B> from the pile added to your hand (the top
              card goes into the new meld).</Li>
            <Li>If the pile is <B>frozen</B>, you need <B>2 natural cards</B> matching
              the top card (no wilds).</Li>
            <Li>If your team hasn&apos;t melded yet, you also need a natural pair and
              must meet the initial meld requirement.</Li>
            <Li>Cannot pick up the pile if the top card is a <B>black 3</B>.</Li>
          </ul>
        </Sec>

        {/* Freezing */}
        <Sec title="Freezing the Discard Pile">
          The pile becomes <B>frozen</B> (shown with a cyan border) when:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>A <B>wild card</B> (joker or 2) is discarded.</Li>
            <Li>The pile starts frozen if the initial top card is wild or a red 3.</Li>
          </ul>
          A frozen pile can only be picked up with a <B>natural pair</B> matching the
          top card — no wilds allowed.
        </Sec>

        {/* Going Out */}
        <Sec title="Going Out">
          <ul className="space-y-1 text-slate-300">
            <Li>To go out, you must have <B>no cards left</B> in your hand and your
              team must have at least <B>one canasta</B>.</Li>
            <Li>Going out earns a <B>100-point bonus</B>.</Li>
            <Li>If neither team goes out, the round ends when the <B>stock is exhausted</B>.</Li>
          </ul>
        </Sec>

        {/* Scoring */}
        <Sec title="End-of-Round Scoring">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Meld card points</B> — sum of point values of all melded cards.</Li>
            <Li><B>Natural canasta bonus</B> — <B>+500</B> per natural canasta.</Li>
            <Li><B>Mixed canasta bonus</B> — <B>+300</B> per mixed canasta.</Li>
            <Li><B>Going out bonus</B> — <B>+100</B>.</Li>
            <Li><B>Red 3 bonus</B> — <B>+100</B> each (or <B>+800</B> for all 4), but becomes a
              <B> penalty</B> if your team has no melds.</Li>
            <Li><B>Unmelded cards</B> — point values of cards left in hand are <B>subtracted</B>.</Li>
          </ul>
        </Sec>

        {/* AI */}
        <Sec title="AI Opponents">
          Your three AI opponents (East, North, West) play automatically:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>They draw from the stock (never pick up the pile).</Li>
            <Li>They meld when they have 3+ cards of the same rank, prioritizing additions
              to existing melds.</Li>
            <Li>They discard black 3s first (to block you), then low-value singletons,
              keeping pairs and potential melds.</Li>
          </ul>
        </Sec>

        {/* Controls */}
        <Sec title="Controls">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Click cards</B> to select/deselect them (they rise when selected).</Li>
            <Li><B>Draw 2</B> — draw 2 cards from the stock.</Li>
            <Li><B>Pick Up Pile</B> — pick up the discard pile (select 2 matching cards first).</Li>
            <Li><B>Meld Selected</B> — meld your selected cards.</Li>
            <Li><B>Discard</B> — discard your single selected card to end your turn.</Li>
            <Li><B>Go Out</B> — appears when your hand is empty and your team has a canasta.</Li>
          </ul>
        </Sec>

        {/* Tips */}
        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Build toward canastas</B> — you cannot go out without one, and they
              earn big bonuses.</Li>
            <Li><B>Hold wild cards</B> — they are worth 20-50 points and freeze the pile
              if discarded. Use them to complete canastas.</Li>
            <Li><B>Pick up the pile</B> when it has many cards — a large pile can give you
              huge melding opportunities.</Li>
            <Li><B>Discard black 3s</B> to block opponents from picking up the pile.</Li>
            <Li><B>Watch the score thresholds</B> — as your score increases, the initial
              meld requirement gets harder (50 → 90 → 120).</Li>
            <Li><B>Coordinate with your partner</B> — North&apos;s melds help you and
              vice versa. You share team melds.</Li>
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

// ── Constants ────────────────────────────────────────────────────────

const AI_DELAY = 800

// ── Main component ───────────────────────────────────────────────────

function CanastaSinglePlayer({ onGameEnd, onStateChange: _onStateChange }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void } = {}) {
  const { load, save, clear } = useGameState<SavedState>('canasta')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('canasta'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('canasta')

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

  const [gameState, setGameState] = useState<CanastaState>(
    () => saved?.gameState ?? createCanastaGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedCards, setSelectedCards] = useState<number[]>([])
  const aiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Persist state
  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Detect game over
  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const won = gameState.teamScores[0] > gameState.teamScores[1]
      if (won) sfx.play('gin')
      setGameStatus(won ? 'won' : 'lost')
      onGameEnd?.(won ? 'win' : 'loss')
      clear()
    }
  }, [gameState, clear, onGameEnd])

  // AI auto-play
  useEffect(() => {
    if (gameState.phase === 'gameOver' || gameState.phase === 'roundOver') return
    if (gameState.currentPlayer === 0) return

    aiTimerRef.current = setTimeout(() => {
      setGameState(prev => {
        if (prev.currentPlayer === 0) return prev
        if (prev.phase === 'gameOver' || prev.phase === 'roundOver') return prev

        // Run AI turns for all non-human players in sequence
        let current = prev
        while (current.currentPlayer !== 0 &&
               current.phase !== 'gameOver' &&
               current.phase !== 'roundOver') {
          current = aiTurn(current)
        }
        return current
      })
    }, AI_DELAY)

    return () => {
      if (aiTimerRef.current) clearTimeout(aiTimerRef.current)
    }
  }, [gameState.currentPlayer, gameState.phase])

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (aiTimerRef.current) clearTimeout(aiTimerRef.current)
    }
  }, [])

  // ── Handlers ─────────────────────────────────────────────────────

  const handleDraw = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    setGameState(prev => drawFromStock(prev))
    setSelectedCards([])
  }, [])

  const handlePickupPile = useCallback(() => {
    setGameState(prev => pickupDiscardPile(prev, selectedCards))
    setSelectedCards([])
  }, [selectedCards])

  const handleMeld = useCallback(() => {
    if (selectedCards.length === 0) return
    sfx.play('meld')
    // Check if any existing team meld matches the selected cards' rank
    const player = gameState.currentPlayer
    const team = player % 2
    const hand = gameState.hands[player]
    const cards = selectedCards.map(i => hand[i]).filter(Boolean)
    const naturalCard = cards.find(c => !isWild(c))
    const rank = naturalCard?.rank

    if (rank !== undefined) {
      const existingIdx = gameState.teamMelds.findIndex(m => m.team === team && m.rank === rank)
      if (existingIdx >= 0) {
        setGameState(prev => meldCards(prev, selectedCards, existingIdx))
        setSelectedCards([])
        return
      }
    }

    setGameState(prev => meldCards(prev, selectedCards))
    setSelectedCards([])
  }, [selectedCards, gameState])

  const handleDiscard = useCallback(() => {
    if (selectedCards.length !== 1) return
    setGameState(prev => discard(prev, selectedCards[0]))
    setSelectedCards([])
  }, [selectedCards])

  const handleGoOut = useCallback(() => {
    sfx.play('knock')
    setGameState(prev => goOut(prev))
    setSelectedCards([])
  }, [])

  const handleNextRound = useCallback(() => {
    setGameState(prev => newRound(prev))
    setSelectedCards([])
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createCanastaGame())
    setGameStatus('playing')
    setSelectedCards([])
    clear()
  }, [clear])

  const toggleCardSelection = useCallback((index: number) => {
    setSelectedCards(prev =>
      prev.includes(index) ? prev.filter(i => i !== index) : [...prev, index]
    )
  }, [])

  // ── Derived state ────────────────────────────────────────────────

  const isHumanTurn = gameState.currentPlayer === 0
  const canDraw = isHumanTurn && gameState.phase === 'draw' && !gameState.hasDrawn
  const canMeld = isHumanTurn && gameState.phase === 'meld' && gameState.hasDrawn
  const canDiscard = isHumanTurn && gameState.hasDrawn && selectedCards.length === 1
  const canPickup = isHumanTurn && gameState.phase === 'draw' && !gameState.hasDrawn
  const canGoOut = isHumanTurn && gameState.phase === 'meld' && gameState.hasDrawn &&
    gameState.hands[0].length === 0 &&
    gameState.teamMelds.some(m => m.team === 0 && m.isCanasta)

  const team0Melds = gameState.teamMelds.filter(m => m.team === 0)
  const team1Melds = gameState.teamMelds.filter(m => m.team === 1)

  // ── Render ───────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex gap-3">
        <span className="text-blue-400">{TEAM_NAMES[0]}: {gameState.teamScores[0]}</span>
        <span className="text-red-400">{TEAM_NAMES[1]}: {gameState.teamScores[1]}</span>
      </div>
      <div className="flex gap-2 text-slate-400">
        <span>Stock: {gameState.stock.length}</span>
        <span>Pile: {gameState.discardPile.length}</span>
        {gameState.pileFrozen && <span className="text-cyan-400">Frozen</span>}
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowHelp(true)}
          className="p-1.5 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-white"
          title="How to Play"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Canasta" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-2">

        {/* North (Partner) */}
        <div className="text-center">
          <span className="text-xs text-blue-400">North (Partner) ({gameState.hands[2].length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[2].slice(0, 7).map((_, i) => (
              <div key={i} className={CARD_SLOT_V}><CardBack /></div>
            ))}
            {gameState.hands[2].length > 7 && (
              <span className="text-[0.6rem] text-slate-500 self-center">+{gameState.hands[2].length - 7}</span>
            )}
          </div>
          {/* North's red 3s */}
          {gameState.redThrees[2].length > 0 && (
            <div className="flex gap-0.5 justify-center mt-0.5">
              {gameState.redThrees[2].map((card, i) => (
                <div key={i} className={CARD_SLOT_V}>
                  <CardFace card={card} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* West + Center + East */}
        <div className="flex w-full items-center gap-2">
          {/* West (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">West ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
            {gameState.redThrees[3].length > 0 && (
              <div className="flex gap-0.5 justify-center mt-0.5">
                {gameState.redThrees[3].map((card, i) => (
                  <div key={i} className={CARD_SLOT_V}>
                    <CardFace card={card} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Center: Stock + Discard pile */}
          <div className="flex-1 flex items-center justify-center gap-3 h-36 sm:h-48">
            {/* Stock */}
            <div className="text-center">
              {gameState.stock.length > 0 ? (
                <div className={CARD_SIZE}>
                  <CardBack />
                </div>
              ) : (
                <div className={`${CARD_SIZE} border border-dashed border-slate-600 rounded-md flex items-center justify-center`}>
                  <span className="text-[0.6rem] text-slate-600">Empty</span>
                </div>
              )}
              <span className="text-[0.55rem] text-slate-500 mt-0.5">{gameState.stock.length}</span>
            </div>

            {/* Discard pile */}
            <div className="text-center">
              {gameState.discardPile.length > 0 ? (
                <div className={`${CARD_SIZE} ${
                  gameState.pileFrozen ? 'ring-2 ring-cyan-400' : ''
                }`}>
                  {(() => {
                    const topCard = gameState.discardPile[gameState.discardPile.length - 1]
                    return topCard.rank === 0 ? <JokerCard /> : <CardFace card={topCard} />
                  })()}
                </div>
              ) : (
                <div className={`${CARD_SIZE} border border-dashed border-slate-600 rounded-md flex items-center justify-center`}>
                  <span className="text-[0.6rem] text-slate-600">Empty</span>
                </div>
              )}
              <span className="text-[0.55rem] text-slate-500 mt-0.5">
                {gameState.discardPile.length}
                {gameState.pileFrozen ? ' (frozen)' : ''}
              </span>
            </div>
          </div>

          {/* East (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">East ({gameState.hands[1].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[1].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
            {gameState.redThrees[1].length > 0 && (
              <div className="flex gap-0.5 justify-center mt-0.5">
                {gameState.redThrees[1].map((card, i) => (
                  <div key={i} className={CARD_SLOT_V}>
                    <CardFace card={card} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Team melds */}
        {(team0Melds.length > 0 || team1Melds.length > 0) && (
          <div className="w-full space-y-1">
            {team0Melds.length > 0 && (
              <div>
                <span className="text-[0.6rem] text-blue-400">Your team&apos;s melds:</span>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {team0Melds.map((meld, i) => (
                    <MeldDisplay key={i} meld={meld} />
                  ))}
                </div>
              </div>
            )}
            {team1Melds.length > 0 && (
              <div>
                <span className="text-[0.6rem] text-red-400">Opponent melds:</span>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {team1Melds.map((meld, i) => (
                    <MeldDisplay key={i} meld={meld} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Red 3s for player 0 */}
        {gameState.redThrees[0].length > 0 && (
          <div className="flex gap-1 justify-center">
            <span className="text-[0.6rem] text-red-400 self-center mr-1">Red 3s:</span>
            {gameState.redThrees[0].map((card, i) => (
              <div key={i} className="w-8 h-12">
                <CardFace card={card} />
              </div>
            ))}
          </div>
        )}

        {/* Action buttons */}
        {isHumanTurn && gameState.phase !== 'roundOver' && gameState.phase !== 'gameOver' && (
          <div className="flex flex-wrap gap-2 justify-center">
            {canDraw && (
              <button
                onClick={handleDraw}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Draw 2
              </button>
            )}
            {canPickup && (
              <button
                onClick={handlePickupPile}
                disabled={selectedCards.length < 2}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  selectedCards.length >= 2
                    ? 'bg-amber-600 hover:bg-amber-500 text-white'
                    : 'bg-slate-700 text-slate-500 cursor-not-allowed'
                }`}
              >
                Pick Up Pile
              </button>
            )}
            {canMeld && selectedCards.length >= 1 && (
              <button
                onClick={handleMeld}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Meld Selected
              </button>
            )}
            {canDiscard && (
              <button
                onClick={handleDiscard}
                className="px-3 py-1.5 bg-orange-600 hover:bg-orange-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Discard
              </button>
            )}
            {canGoOut && (
              <button
                onClick={handleGoOut}
                className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Go Out
              </button>
            )}
          </div>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {gameState.hands[0].map((card, i) => (
            <GameCard
              key={`${card.rank}-${card.suit}-${i}`}
              card={card}
              selected={selectedCards.includes(i)}
              onClick={() => toggleCardSelection(i)}
              disabled={!isHumanTurn || gameState.phase === 'roundOver' || gameState.phase === 'gameOver'}
            />
          ))}
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

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost') && (
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
      {showHelp && <CanastaHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-meld-out against AI) ─────────────────────

function CanastaRaceWrapper({ roomId, difficulty: _difficulty }: { roomId: string; difficulty?: string }) {
  const { opponentStatus, raceResult, opponentLevelUp, broadcastState, reportFinish } = useRaceMode(roomId, 'first_to_win')
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
      />
      <CanastaSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} />
    </div>
  )
}

export default function Canasta() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'canasta',
        gameName: 'Canasta',
        modes: ['race'],
        maxPlayers: 2,
        hasDifficulty: true,
        raceDescription: 'First to meld out wins',
      }}
      renderSinglePlayer={() => <CanastaSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig) =>
        <CanastaRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} />
      }
    />
  )
}
