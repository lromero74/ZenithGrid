/**
 * Bridge — 4-player partnership trick-taking card game.
 *
 * Teams: You (South) + Partner (North) vs East + West.
 * Bidding phase with level + strain, declarer/dummy system,
 * 13 tricks per hand. First team to 500 wins.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SLOT_V, CARD_SLOT_H } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { getSuitSymbol } from '../../../utils/cardUtils'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { BridgeMultiplayer } from './BridgeMultiplayer'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import {
  createBridgeGame,
  makeBid,
  passBid,
  playCard,
  nextHand,
  getValidPlays,
  strainSymbol,
  formatBid,
  PLAYER_NAMES,
  TEAM_NAMES,
  STRAIN_ORDER,
  type BridgeState,
  type Strain,
} from './BridgeEngine'

interface SavedState {
  gameState: BridgeState
  gameStatus: GameStatus
}

const STRAIN_LABELS: { strain: Strain; label: string; color: string }[] = [
  { strain: 'clubs', label: '\u2663', color: 'bg-slate-700 hover:bg-slate-600' },
  { strain: 'diamonds', label: '\u2666', color: 'bg-red-800 hover:bg-red-700' },
  { strain: 'hearts', label: '\u2665', color: 'bg-red-700 hover:bg-red-600' },
  { strain: 'spades', label: '\u2660', color: 'bg-slate-700 hover:bg-slate-600' },
  { strain: 'nt', label: 'NT', color: 'bg-amber-700 hover:bg-amber-600' },
]

// ── Help modal ───────────────────────────────────────────────────────

function BridgeHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Bridge</h2>

        {/* Goal */}
        <Sec title="Goal">
          Win tricks with your partner to fulfill your <B>contract</B> (the number
          of tricks you bid). The first team to reach <B>500 points</B> wins the game.
        </Sec>

        {/* Partnerships */}
        <Sec title="Partnerships">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>You sit <B>South</B>. Your AI partner sits <B>North</B> (directly
              across from you).</Li>
            <Li>Your opponents are <B>East</B> and <B>West</B>, both controlled by AI.</Li>
            <Li>Each hand deals all <B>52 cards</B> evenly &mdash; <B>13 cards</B> per player.</Li>
          </ul>
        </Sec>

        {/* Bidding */}
        <Sec title="Bidding Phase">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Bidding starts with the player to the left of the <B>dealer</B> and
              proceeds clockwise.</Li>
            <Li>A bid consists of a <B>level</B> (1&ndash;7) and a <B>strain</B> (suit
              or No Trump). For example, &quot;2{'\u2665'}&quot; means you commit to
              winning <B>8 tricks</B> (6 + level) with hearts as trump.</Li>
            <Li>Strains rank from lowest to highest:
              {' '}<B>{'\u2663'}</B> (Clubs) &lt; <B>{'\u2666'}</B> (Diamonds)
              {' '}&lt; <B>{'\u2665'}</B> (Hearts) &lt; <B>{'\u2660'}</B> (Spades)
              {' '}&lt; <B>NT</B> (No Trump).</Li>
            <Li>Each new bid must be <B>higher</B> than the previous &mdash; either a
              higher level, or the same level with a higher-ranking strain.</Li>
            <Li>You may <B>Pass</B> instead of bidding. If all four players pass
              without a bid, the hand is redealt with a new dealer.</Li>
            <Li>Bidding ends when <B>three consecutive passes</B> follow a bid. The
              last bid becomes the <B>contract</B>.</Li>
          </ul>
        </Sec>

        {/* Declarer & Dummy */}
        <Sec title="Declarer &amp; Dummy">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>The <B>declarer</B> is the first player on the winning team who bid
              the contract&apos;s strain.</Li>
            <Li>The declarer&apos;s partner becomes the <B>dummy</B>. Dummy&apos;s
              cards are placed face-up on the table, and the declarer plays both
              hands.</Li>
            <Li>If you are the declarer, you will play your own cards AND select
              cards from dummy&apos;s hand when it is dummy&apos;s turn.</Li>
          </ul>
        </Sec>

        {/* Card Play */}
        <Sec title="Card Play">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>The player to the <B>left of the declarer</B> leads the first trick.</Li>
            <Li>Play proceeds <B>clockwise</B>. Each player plays one card per trick.</Li>
            <Li>You <B>must follow suit</B> if you can. If you have no cards in the
              led suit, you may play any card (including a trump).</Li>
            <Li>The trick is won by the highest <B>trump</B> played, or if no trump
              was played, by the highest card <B>in the led suit</B>.</Li>
            <Li>The winner of each trick leads the next one.</Li>
            <Li><B>Ace is the highest</B> card in each suit.</Li>
          </ul>
        </Sec>

        {/* Tricks Required */}
        <Sec title="Making Your Contract">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Your team needs to win at least <B>6 + bid level</B> tricks.
              For example, a 3{'\u2660'} contract requires <B>9 tricks</B>.</Li>
            <Li>Extra tricks beyond the contract are called <B>overtricks</B>.</Li>
            <Li>If you fall short, each missing trick is an <B>undertrick</B>.</Li>
          </ul>
        </Sec>

        {/* Scoring */}
        <Sec title="Scoring">
          <div className="space-y-2">
            <div>
              <div className="text-xs text-slate-300 font-medium mb-1">Trick Points (contracted tricks only):</div>
              <ul className="space-y-1 text-slate-300">
                <Li><B>{'\u2663'} Clubs / {'\u2666'} Diamonds</B> &mdash; 20 points per trick.</Li>
                <Li><B>{'\u2665'} Hearts / {'\u2660'} Spades</B> &mdash; 30 points per trick.</Li>
                <Li><B>No Trump</B> &mdash; 40 for the first trick, 30 for each additional.</Li>
              </ul>
            </div>
            <div>
              <div className="text-xs text-slate-300 font-medium mb-1">Bonuses:</div>
              <ul className="space-y-1 text-slate-300">
                <Li><B>Game bonus</B> &mdash; +300 if trick points reach 100 or more.</Li>
                <Li><B>Partial bonus</B> &mdash; +50 if trick points are below 100.</Li>
                <Li><B>Small slam</B> &mdash; +500 for bidding and making a level 6 contract (12 tricks).</Li>
                <Li><B>Grand slam</B> &mdash; +1,000 for bidding and making a level 7 contract (all 13 tricks).</Li>
              </ul>
            </div>
            <div>
              <div className="text-xs text-slate-300 font-medium mb-1">Overtricks &amp; Undertricks:</div>
              <ul className="space-y-1 text-slate-300">
                <Li><B>Overtricks</B> &mdash; same per-trick value as the contract strain.</Li>
                <Li><B>Undertricks</B> &mdash; the declaring team loses <B>50 points per trick short</B>.</Li>
              </ul>
            </div>
          </div>
        </Sec>

        {/* AI */}
        <Sec title="AI Partner &amp; Opponents">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>Your partner (North) and both opponents are played by <B>AI</B>.</Li>
            <Li>AI bids based on <B>high-card points</B> (HCP): Ace=4, King=3,
              Queen=2, Jack=1. It needs <B>13+ HCP</B> to open.</Li>
            <Li>AI will try to <B>support its partner&apos;s strain</B> at the
              next level when possible.</Li>
            <Li>During play, AI follows standard strategy: lead non-trumps, play
              low when partner is winning, try to beat the current best card, and
              avoid trumping partner&apos;s winning trick.</Li>
          </ul>
        </Sec>

        {/* Controls */}
        <Sec title="Controls">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>During <B>bidding</B>: select a level (1&ndash;7) and a strain, then
              click <B>Bid</B>. Or click <B>Pass</B> to pass.</Li>
            <Li>During <B>play</B>: click a valid card in your hand. Valid cards are
              highlighted; invalid ones are dimmed.</Li>
            <Li>When you are the declarer, click on <B>dummy&apos;s cards</B> to play
              them during dummy&apos;s turn.</Li>
            <Li>After each hand, click <B>Next Hand</B> to continue.</Li>
          </ul>
        </Sec>

        {/* Strategy Tips */}
        <Sec title="Strategy Tips">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Count your points before bidding.</B> With 13+ HCP, you have
              enough to open. Below that, pass and let your partner bid.</Li>
            <Li><B>Bid your longest suit.</B> A 5+ card suit often makes a good
              trump. With balanced hands (no long suit), consider No Trump.</Li>
            <Li><B>Support your partner.</B> If partner bids a suit and you have
              3+ cards in it, raise to show support.</Li>
            <Li><B>Lead with strong suits.</B> Open with your best non-trump suit
              to establish winning tricks early.</Li>
            <Li><B>Follow suit wisely.</B> If you cannot beat the current winning
              card, play your lowest to save your high cards.</Li>
            <Li><B>Count trumps.</B> Track how many trump cards have been played to
              know when it is safe to lead trump.</Li>
            <Li><B>Don&apos;t overbid.</B> Undertricks cost points. A modest contract
              you can make is better than an ambitious one you cannot.</Li>
            <Li><B>Watch the dummy.</B> When dummy&apos;s cards are visible, plan your
              play around what you can see.</Li>
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

function BridgeSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<SavedState>('bridge')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('bridge'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('bridge')

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

  const [gameState, setGameState] = useState<BridgeState>(
    () => saved?.gameState ?? createBridgeGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedLevel, setSelectedLevel] = useState(1)
  const [selectedStrain, setSelectedStrain] = useState<Strain>('clubs')

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
      const won = gameState.teamScores[0] > gameState.teamScores[1]
      setGameStatus(won ? 'won' : 'lost')
      onGameEnd?.(won ? 'win' : 'loss')
      clear()
    }
  }, [gameState, clear, onGameEnd])

  const handleBid = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    setGameState(prev => makeBid(prev, selectedLevel, selectedStrain))
  }, [selectedLevel, selectedStrain])

  const handlePass = useCallback(() => {
    setGameState(prev => passBid(prev))
  }, [])

  const handlePlay = useCallback((playerIdx: number, cardIndex: number) => {
    sfx.play('play')
    setGameState(prev => playCard(prev, playerIdx, cardIndex))
  }, [])

  const handleNextHand = useCallback(() => {
    sfx.play('hand_won')
    setGameState(prev => nextHand(prev))
    setSelectedLevel(1)
    setSelectedStrain('clubs')
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createBridgeGame())
    setGameStatus('playing')
    setSelectedLevel(1)
    setSelectedStrain('clubs')
    clear()
  }, [clear])

  const isBidding = gameState.phase === 'bidding' && gameState.currentPlayer === 0
  const isPlaying = gameState.phase === 'playing'
  const isHumanTurn = isPlaying && gameState.currentPlayer === 0
  const isDummyTurn = isPlaying && gameState.currentPlayer === gameState.dummy && gameState.declarer === 0

  const humanValidPlays = isHumanTurn ? getValidPlays(gameState, 0) : []
  const dummyValidPlays = isDummyTurn && gameState.dummy !== null ? getValidPlays(gameState, gameState.dummy) : []

  // Get the highest existing bid to validate new bids
  const highestBid = gameState.bids.reduce<{ level: number; strain: Strain } | null>((best, bid) => {
    if (bid.level === 0) return best
    if (!best) return { level: bid.level, strain: bid.strain as Strain }
    const bestIdx = STRAIN_ORDER.indexOf(best.strain)
    const bidIdx = STRAIN_ORDER.indexOf(bid.strain as Strain)
    if (bid.level > best.level || (bid.level === best.level && bidIdx > bestIdx)) {
      return { level: bid.level, strain: bid.strain as Strain }
    }
    return best
  }, null)

  // Check if current selection is a valid bid
  const isValidBidSelection = !highestBid || (
    selectedLevel > highestBid.level ||
    (selectedLevel === highestBid.level && STRAIN_ORDER.indexOf(selectedStrain) > STRAIN_ORDER.indexOf(highestBid.strain))
  )

  // Contract display
  const contractStr = gameState.contract
    ? `${gameState.contract.level}${strainSymbol(gameState.contract.strain!)} by ${PLAYER_NAMES[gameState.declarer!]}`
    : null

  // Tricks won by team
  const teamTricks = [
    (gameState.tricksWon[0] || 0) + (gameState.tricksWon[2] || 0),
    (gameState.tricksWon[1] || 0) + (gameState.tricksWon[3] || 0),
  ]

  const controls = (
    <div className="flex items-center justify-between text-xs flex-wrap gap-1">
      <div className="flex gap-3">
        <span className="text-blue-400">{TEAM_NAMES[0]}: {gameState.teamScores[0]}</span>
        <span className="text-red-400">{TEAM_NAMES[1]}: {gameState.teamScores[1]}</span>
      </div>
      <div className="flex gap-2 text-slate-400">
        {contractStr && (
          <span className="text-yellow-400">
            Contract: {contractStr}
          </span>
        )}
        {isPlaying && (
          <span>Tricks: {teamTricks[0]}-{teamTricks[1]}</span>
        )}
        <span>Dealer: {PLAYER_NAMES[gameState.dealer]}</span>
      </div>
      <div className="flex items-center gap-1">
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

  // Render a player's hand (face down for opponents, face up for dummy)
  const renderOpponentHand = (playerIdx: number, position: 'top' | 'left' | 'right') => {
    const hand = gameState.hands[playerIdx]
    const isDummy = playerIdx === gameState.dummy && gameState.dummyRevealed
    const label = playerIdx === gameState.dummy ? `${PLAYER_NAMES[playerIdx]} (Dummy)` : PLAYER_NAMES[playerIdx]
    const teamColor = playerIdx % 2 === 0 ? 'text-blue-400' : 'text-red-400'
    const isDummyPlayable = isDummyTurn && playerIdx === gameState.dummy

    if (position === 'top') {
      return (
        <div className="text-center">
          <span className={`text-xs ${teamColor}`}>{label} ({hand.length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5 flex-wrap">
            {isDummy ? (
              hand.map((card, i) => {
                const isValid = isDummyPlayable && dummyValidPlays.includes(i)
                return (
                  <div
                    key={`${card.rank}-${card.suit}-${i}`}
                    className={`${CARD_SIZE} transition-transform ${
                      isValid ? 'cursor-pointer hover:-translate-y-1' : isDummyPlayable ? 'opacity-40' : ''
                    }`}
                    onClick={() => isDummyPlayable && isValid && handlePlay(playerIdx, i)}
                  >
                    <CardFace card={card} />
                  </div>
                )
              })
            ) : (
              hand.slice(0, 7).map((_, i) => (
                <div key={i} className={CARD_SLOT_V}><CardBack /></div>
              ))
            )}
            {!isDummy && hand.length > 7 && (
              <span className="text-[0.6rem] text-slate-500 self-center">+{hand.length - 7}</span>
            )}
          </div>
        </div>
      )
    }

    // Left or right opponent
    return (
      <div className="text-center w-16 flex-shrink-0">
        <span className={`text-[0.6rem] ${teamColor}`}>{label} ({hand.length})</span>
        <div className="flex flex-col items-center gap-0.5 mt-0.5">
          {isDummy ? (
            hand.map((card, i) => {
              const isValid = isDummyPlayable && dummyValidPlays.includes(i)
              return (
                <div
                  key={`${card.rank}-${card.suit}-${i}`}
                  className={`w-12 h-[4.25rem] transition-transform ${
                    isValid ? 'cursor-pointer hover:scale-105' : isDummyPlayable ? 'opacity-40' : ''
                  }`}
                  onClick={() => isDummyPlayable && isValid && handlePlay(playerIdx, i)}
                >
                  <CardFace card={card} />
                </div>
              )
            })
          ) : (
            hand.slice(0, 5).map((_, i) => (
              <div key={i} className={CARD_SLOT_H}><CardBack /></div>
            ))
          )}
        </div>
      </div>
    )
  }

  return (
    <GameLayout title="Bridge" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* North (Partner) */}
        {renderOpponentHand(2, 'top')}

        {/* West + Trick area + East */}
        <div className="flex w-full items-center gap-2">
          {/* West */}
          {renderOpponentHand(3, 'left')}

          {/* Trick area */}
          <div className="flex-1 relative h-36 sm:h-48">
            {/* Current trick cards */}
            {gameState.currentTrick.map((play) => {
              const positions = [
                'bottom-0 left-1/2 -translate-x-1/2',    // South (You)
                'right-0 top-1/2 -translate-y-1/2',       // East
                'top-0 left-1/2 -translate-x-1/2',        // North / Partner
                'left-0 top-1/2 -translate-y-1/2',        // West
              ]
              return (
                <div key={`${play.player}-${play.card.rank}-${play.card.suit}`}
                  className={`absolute ${positions[play.player]} ${CARD_SIZE}`}
                >
                  <CardFace card={play.card} />
                </div>
              )
            })}

            {/* Trump / NT indicator in center when no trick cards */}
            {gameState.currentTrick.length === 0 && gameState.trumpSuit && (
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
                {gameState.trumpSuit === 'nt' ? (
                  <span className="text-lg font-bold text-amber-400">NT</span>
                ) : (
                  <span className="text-2xl">
                    {getSuitSymbol(gameState.trumpSuit as 'clubs' | 'diamonds' | 'hearts' | 'spades')}
                  </span>
                )}
                <p className="text-[0.6rem] text-slate-500 mt-0.5">
                  {gameState.trumpSuit === 'nt' ? 'No Trump' : 'Trump'}
                </p>
              </div>
            )}

            {/* Bid history during bidding */}
            {gameState.phase === 'bidding' && gameState.bids.length > 0 && (
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
                <div className="text-[0.6rem] text-slate-400 space-y-0.5">
                  {gameState.bids.slice(-4).map((bid, i) => (
                    <div key={i}>
                      <span className="text-slate-500">{PLAYER_NAMES[bid.player]}: </span>
                      <span className={bid.level > 0 ? 'text-yellow-400' : 'text-slate-500'}>
                        {formatBid(bid)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* East */}
          {renderOpponentHand(1, 'right')}
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Bidding UI */}
        {isBidding && (
          <div className="flex flex-col items-center gap-2">
            {/* Level selector */}
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5, 6, 7].map(level => (
                <button
                  key={level}
                  onClick={() => setSelectedLevel(level)}
                  className={`w-8 h-8 text-xs rounded transition-colors ${
                    selectedLevel === level
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>

            {/* Strain selector */}
            <div className="flex gap-1">
              {STRAIN_LABELS.map(({ strain, label, color }) => (
                <button
                  key={strain}
                  onClick={() => setSelectedStrain(strain)}
                  className={`px-3 h-8 text-sm rounded transition-colors text-white ${
                    selectedStrain === strain
                      ? 'ring-2 ring-yellow-400 ' + color
                      : color
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Bid / Pass buttons */}
            <div className="flex gap-2">
              <button
                onClick={handleBid}
                disabled={!isValidBidSelection}
                className={`px-5 py-2 text-white rounded-lg text-sm font-medium transition-colors ${
                  isValidBidSelection
                    ? 'bg-emerald-600 hover:bg-emerald-500'
                    : 'bg-slate-600 text-slate-400 cursor-not-allowed'
                }`}
              >
                Bid {selectedLevel}{strainSymbol(selectedStrain)}
              </button>
              <button
                onClick={handlePass}
                className="px-5 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium transition-colors"
              >
                Pass
              </button>
            </div>

            {/* Current highest bid indicator */}
            {highestBid && (
              <span className="text-[0.65rem] text-slate-500">
                Current high bid: {highestBid.level}{strainSymbol(highestBid.strain)}
              </span>
            )}
          </div>
        )}

        {/* Player hand (South) */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {gameState.hands[0].map((card, i) => {
            const isValid = humanValidPlays.includes(i)
            const canPlay = isHumanTurn && isValid
            return (
              <div
                key={`${card.rank}-${card.suit}-${i}`}
                className={`${CARD_SIZE} transition-transform ${
                  canPlay ? 'cursor-pointer hover:-translate-y-1' : (isHumanTurn || isDummyTurn) ? 'opacity-40' : ''
                }`}
                onClick={() => canPlay && handlePlay(0, i)}
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

        {/* Help modal */}
        {showHelp && <BridgeHelp onClose={() => setShowHelp(false)} />}
      </div>
    </GameLayout>
  )
}

// ── Race wrapper (first-to-win against AI) ─────────────────────────

function BridgeRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
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
      <BridgeSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function Bridge() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'bridge',
        gameName: 'Bridge',
        modes: ['vs', 'first_to_win'],
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: {
          vs: '2 humans + 2 AI partnerships',
          first_to_win: 'First to make contract wins',
        },
      }}
      renderSinglePlayer={() => <BridgeSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <BridgeMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
        ) : (
          <BridgeRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
        )
      }
    />
  )
}
