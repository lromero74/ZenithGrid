/**
 * Bridge — 4-player partnership trick-taking card game.
 *
 * Teams: You (South) + Partner (North) vs East + West.
 * Bidding phase with level + strain, declarer/dummy system,
 * 13 tricks per hand. First team to 500 wins.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
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

export default function Bridge() {
  const { load, save, clear } = useGameState<SavedState>('bridge')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('bridge'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('bridge')

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
      setGameStatus(gameState.teamScores[0] > gameState.teamScores[1] ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

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
      <MusicToggle music={music} sfx={sfx} />
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
    </GameLayout>
  )
}
