/**
 * Speed — real-time 2-player card game. Race to empty your hand first!
 * Contributed by Shantina Jackson-Romero.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SIZE_MINI } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { getRankDisplay, getSuitSymbol } from '../../../utils/cardUtils'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import {
  createSpeedGame,
  playCard,
  aiPlayCard,
  flipCenterCards,
  flipStartingCards,
  getAiMove,
  getPlayerMoves,
  generateAiPlayDelay,
  type SpeedState,
  type AiDifficulty,
} from './speedEngine'

interface SavedState {
  gameState: SpeedState
  gameStatus: GameStatus
}

// ── Difficulty selection screen ─────────────────────────────────────

function DifficultySelect({ onStart }: { onStart: (difficulty: AiDifficulty) => void }) {
  const [difficulty, setDifficulty] = useState<AiDifficulty>('normal')

  return (
    <div className="flex flex-col items-center gap-6 py-4">
      <div className="text-center">
        <h3 className="text-sm font-medium text-slate-300 mb-3 uppercase tracking-wider">AI Difficulty</h3>
        <div className="flex gap-2">
          {(['easy', 'normal', 'adept'] as const).map(d => (
            <button
              key={d}
              onClick={() => setDifficulty(d)}
              className={`px-4 py-2.5 rounded-lg text-sm font-medium transition-all capitalize ${
                difficulty === d
                  ? d === 'easy' ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/40'
                    : d === 'normal' ? 'bg-amber-600 text-white shadow-lg shadow-amber-900/40'
                    : 'bg-red-600 text-white shadow-lg shadow-red-900/40'
                  : 'bg-slate-700/60 text-slate-400 hover:bg-slate-700'
              }`}
            >
              {d}
            </button>
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-2 max-w-xs">
          {difficulty === 'easy' ? 'AI reacts like an average human — room to breathe.'
            : difficulty === 'normal' ? 'AI is competent — occasionally catches you off guard.'
            : 'AI has fast reflexes — top 10% reaction speed.'}
        </p>
      </div>

      <button
        onClick={() => onStart(difficulty)}
        className="mt-2 px-10 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl
          text-lg font-bold transition-all active:scale-95 shadow-lg shadow-emerald-900/50"
      >
        Deal Cards
      </button>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────

// ── Help modal ──────────────────────────────────────────────────────
function SpeedHelp({ onClose }: { onClose: () => void }) {
  const Sec = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div className="mb-4"><h3 className="text-sm font-semibold text-slate-200 mb-1">{title}</h3><div className="text-xs leading-relaxed text-slate-400">{children}</div></div>
  )
  const Li = ({ children }: { children: React.ReactNode }) => (
    <li className="flex gap-1.5 text-xs"><span className="text-slate-600 mt-0.5">&bull;</span><span>{children}</span></li>
  )
  const B = ({ children }: { children: React.ReactNode }) => <span className="text-white font-medium">{children}</span>

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6" onClick={e => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white"><X className="w-5 h-5" /></button>
        <h2 className="text-lg font-bold text-white mb-4">How to Play Speed</h2>

        <Sec title="Goal">
          <p>Be the first to get rid of all your cards (hand + draw pile). It's a real-time race — no turns!</p>
        </Sec>

        <Sec title="Setup">
          <ul className="space-y-1">
            <Li>Each player gets a <B>5-card hand</B> and a <B>15-card draw pile</B>.</Li>
            <Li>Two <B>center piles</B> start with one card each.</Li>
            <Li>Two <B>replacement piles</B> (5 cards each) are used to unstick the game.</Li>
          </ul>
        </Sec>

        <Sec title="How to Play">
          <ul className="space-y-1">
            <Li>Click a card in your hand to play it on either center pile.</Li>
            <Li>A card can be played if its rank is <B>±1</B> from the center pile's top card (Ace wraps to King).</Li>
            <Li>After playing, your hand auto-refills from your draw pile (back to 5 cards).</Li>
            <Li>The AI plays simultaneously — speed matters!</Li>
          </ul>
        </Sec>

        <Sec title="Stalls">
          <ul className="space-y-1">
            <Li>If neither player can play, cards are flipped from <B>replacement piles</B> onto the center.</Li>
            <Li>If replacement piles are empty and nobody can play, the game ends — fewest cards remaining wins.</Li>
          </ul>
        </Sec>

        <Sec title="Difficulty">
          <ul className="space-y-1">
            <Li><B>Easy</B> — AI plays slowly.</Li>
            <Li><B>Normal</B> — AI plays at moderate speed.</Li>
            <Li><B>Adept</B> — AI plays fast and aggressively.</Li>
          </ul>
        </Sec>

        <Sec title="Strategy Tips">
          <ul className="space-y-1">
            <Li>Play fast — this is a race, not a strategy game.</Li>
            <Li>Watch both center piles — sometimes only one has a valid play.</Li>
            <Li>Prioritize getting through your draw pile early.</Li>
          </ul>
        </Sec>
      </div>
    </div>
  )
}

function SpeedSinglePlayer({ onGameEnd, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<SavedState>('speed')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('speed'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('speed')

  const [showHelp, setShowHelp] = useState(false)
  const [showDifficultySelect, setShowDifficultySelect] = useState<boolean>(() => {
    const s = saved?.gameState
    return !(s && s.replacementPiles && s.difficulty)
  })
  const [gameState, setGameState] = useState<SpeedState>(() => {
    const s = saved?.gameState
    if (s && s.replacementPiles && s.difficulty) return s
    return createSpeedGame()
  })
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedCard, setSelectedCard] = useState<number | null>(null)
  const [flipping, setFlipping] = useState(false)
  const [flipRevealed, setFlipRevealed] = useState(false)

  // Persist state
  useEffect(() => {
    if (showDifficultySelect) return
    if (gameStatus !== 'won' && gameStatus !== 'lost' && gameStatus !== 'draw') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save, showDifficultySelect])

  // Detect game over
  useEffect(() => {
    if (showDifficultySelect) return
    if (gameState.phase === 'gameOver') {
      const pLeft = gameState.playerHand.length + gameState.playerDrawPile.length
      const aLeft = gameState.aiHand.length + gameState.aiDrawPile.length
      if (pLeft < aLeft) {
        setGameStatus('won')
        onGameEnd?.('win')
      } else if (aLeft < pLeft) {
        setGameStatus('lost')
        onGameEnd?.('loss')
      } else {
        setGameStatus('draw')
        onGameEnd?.('draw')
      }
      clear()
    }
  }, [gameState, clear, showDifficultySelect, onGameEnd])

  // AI play loop — human-modeled reaction timing
  const aiTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (showDifficultySelect) return
    if (gameState.phase !== 'playing' || gameStatus !== 'playing') return

    const delay = generateAiPlayDelay(gameState.difficulty)
    aiTimerRef.current = setTimeout(() => {
      setGameState(prev => {
        if (prev.phase !== 'playing') return prev
        const move = getAiMove(prev)
        if (!move) return prev
        sfx.play('play')
        return aiPlayCard(prev, move.handIndex, move.pileIndex)
      })
    }, delay)

    return () => {
      if (aiTimerRef.current) clearTimeout(aiTimerRef.current)
    }
  }, [gameState, gameStatus, sfx, showDifficultySelect])

  // Get valid player moves
  const playerMoves = useMemo(() => getPlayerMoves(gameState), [gameState])
  const playableCardIndices = useMemo(() => {
    const set = new Set<number>()
    for (const m of playerMoves) set.add(m.handIndex)
    return set
  }, [playerMoves])
  const playablePileIndices = useMemo(() => {
    if (selectedCard === null) return new Set<number>()
    const set = new Set<number>()
    for (const m of playerMoves) {
      if (m.handIndex === selectedCard) set.add(m.pileIndex)
    }
    return set
  }, [playerMoves, selectedCard])

  const handleCardClick = useCallback((handIndex: number) => {
    music.init()
    sfx.init()
    music.start()

    if (!playableCardIndices.has(handIndex)) return

    // Find which piles this card can play on
    const validPiles = playerMoves.filter(m => m.handIndex === handIndex).map(m => m.pileIndex)

    if (validPiles.length === 1) {
      // Auto-play on the only valid pile
      sfx.play('play')
      setGameState(prev => playCard(prev, handIndex, validPiles[0]))
      setSelectedCard(null)
    } else if (validPiles.length > 1) {
      // Select card, let player choose pile
      setSelectedCard(handIndex)
    }
  }, [playableCardIndices, playerMoves, music, sfx])

  const handlePileClick = useCallback((pileIndex: number) => {
    if (selectedCard === null) return
    if (!playablePileIndices.has(pileIndex)) return

    sfx.play('play')
    setGameState(prev => playCard(prev, selectedCard, pileIndex))
    setSelectedCard(null)
  }, [selectedCard, playablePileIndices, sfx])

  const handleStartingFlip = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('flip')
    setFlipping(true)
    setFlipRevealed(false)
    // At the halfway point (card is edge-on), swap to face-up
    setTimeout(() => setFlipRevealed(true), 300)
    // After full animation, update game state
    setTimeout(() => {
      setGameState(prev => flipStartingCards(prev))
      setFlipping(false)
      setFlipRevealed(false)
    }, 600)
  }, [music, sfx])

  const handleFlip = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('flip')
    setGameState(prev => flipCenterCards(prev))
  }, [music, sfx])

  const handleNewGame = useCallback(() => {
    setShowDifficultySelect(true)
    setGameStatus('playing')
    setSelectedCard(null)
    clear()
  }, [clear])

  const handleStart = useCallback((difficulty: AiDifficulty) => {
    music.init()
    sfx.init()
    music.start()
    setGameState(createSpeedGame(difficulty))
    setGameStatus('playing')
    setSelectedCard(null)
    setShowDifficultySelect(false)
  }, [music, sfx])

  // ── Difficulty selection screen ───────────────────────────────────
  if (showDifficultySelect) {
    return (
      <GameLayout title="Speed" controls={<MusicToggle music={music} sfx={sfx} />}>
        <DifficultySelect onStart={handleStart} />
      </GameLayout>
    )
  }

  // ── Game screen ───────────────────────────────────────────────────
  const playerCardsLeft = gameState.playerHand.length + gameState.playerDrawPile.length
  const aiCardsLeft = gameState.aiHand.length + gameState.aiDrawPile.length
  const difficultyLabel = gameState.difficulty === 'easy' ? 'Easy' : gameState.difficulty === 'normal' ? 'Normal' : 'Adept'

  const controls = (
    <div className="flex items-center justify-between text-xs w-full">
      <div className="flex items-center gap-2">
        <button
          onClick={handleNewGame}
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          New Game
        </button>
        <span className="text-slate-500">{difficultyLabel}</span>
        <span className="text-slate-400">You: {playerCardsLeft} | AI: {aiCardsLeft}</span>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play">
          <HelpCircle className="w-4 h-4 text-blue-400" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Speed" controls={controls}>
      {/* Card flip animation keyframes */}
      <style>{`
        @keyframes cardFlip {
          0% { transform: rotateY(0deg); }
          50% { transform: rotateY(90deg); }
          100% { transform: rotateY(0deg); }
        }
      `}</style>
      <div className="flex flex-col items-center w-full max-w-md space-y-3">
        {/* AI area */}
        <div className="flex items-center justify-center gap-4 w-full">
          {/* AI draw pile */}
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">
              Draw ({gameState.aiDrawPile.length})
            </span>
            <div className={CARD_SIZE}>
              {gameState.aiDrawPile.length > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700 rounded-lg" />
              )}
            </div>
          </div>
          {/* AI hand (face down) */}
          <div className="flex gap-1">
            {gameState.aiHand.map((_, i) => (
              <div key={i} className={CARD_SIZE_MINI}>
                <CardBack />
              </div>
            ))}
          </div>
        </div>

        {/* Center area: replacement piles flanking center piles */}
        <div className="flex items-center justify-center gap-3 py-2">
          {/* Left replacement pile */}
          <div className="text-center">
            <div className={CARD_SIZE_MINI}>
              {gameState.replacementPiles[0].length > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700/50 rounded-md" />
              )}
            </div>
            <span className="text-[0.5rem] text-slate-600 block mt-0.5">
              {gameState.replacementPiles[0].length}
            </span>
          </div>

          {/* Center piles */}
          {[0, 1].map(pi => {
            const pile = gameState.centerPiles[pi]
            const topCard = pile.length > 0 ? pile[pile.length - 1] : null
            const isTarget = playablePileIndices.has(pi)
            const isReady = gameState.phase === 'ready'
            return (
              <div
                key={pi}
                className="perspective-500"
                style={{ perspective: '500px' }}
              >
                <button
                  onClick={() => isReady ? undefined : handlePileClick(pi)}
                  disabled={isReady || !isTarget}
                  className={`${CARD_SIZE} transition-all ${
                    isTarget ? 'cursor-pointer' : ''
                  } ${flipping ? 'animate-card-flip' : ''}`}
                  style={flipping ? {
                    animation: 'cardFlip 600ms ease-in-out',
                    transformStyle: 'preserve-3d',
                  } : undefined}
                >
                  {isReady && !flipRevealed ? (
                    <CardBack />
                  ) : topCard ? (
                    <CardFace card={{ ...topCard, faceUp: true }} validTarget={isTarget} />
                  ) : (
                    <div className="w-full h-full border border-dashed border-slate-600 rounded-lg" />
                  )}
                </button>
              </div>
            )
          })}

          {/* Right replacement pile */}
          <div className="text-center">
            <div className={CARD_SIZE_MINI}>
              {gameState.replacementPiles[1].length > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700/50 rounded-md" />
              )}
            </div>
            <span className="text-[0.5rem] text-slate-600 block mt-0.5">
              {gameState.replacementPiles[1].length}
            </span>
          </div>
        </div>

        {/* Message + flip buttons */}
        <div className="text-center min-h-[2.5rem]">
          <p className="text-sm text-white font-medium">{gameState.message}</p>
          {gameState.phase === 'ready' && !flipping && (
            <button
              onClick={handleStartingFlip}
              className="mt-2 px-8 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg
                text-base font-bold transition-colors active:scale-95 animate-pulse shadow-lg shadow-emerald-900/50"
            >
              Flip!
            </button>
          )}
          {gameState.phase === 'stalled' && gameStatus === 'playing' && (
            <button
              onClick={handleFlip}
              className="mt-1 px-5 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded-lg
                text-sm font-medium transition-colors active:scale-95 animate-pulse"
            >
              Flip!
            </button>
          )}
        </div>

        {/* Player hand */}
        <div className="flex items-center justify-center gap-4 w-full">
          <div className="flex gap-1.5">
            {gameState.playerHand.map((card, i) => {
              const isReady = gameState.phase === 'ready'
              const canPlay = !isReady && playableCardIndices.has(i)
              const isSelected = selectedCard === i
              return (
                <button
                  key={`${card.suit}-${card.rank}-${i}`}
                  onClick={() => !isReady && handleCardClick(i)}
                  disabled={isReady || (!canPlay && !isSelected)}
                  className={`${CARD_SIZE} transition-all ${
                    isReady ? '' : canPlay ? 'hover:-translate-y-1 cursor-pointer' : 'cursor-default'
                  } ${isSelected ? '-translate-y-2' : ''}`}
                >
                  {isReady ? <CardBack /> : <CardFace card={card} selected={isSelected} />}
                </button>
              )
            })}
          </div>
          {/* Player draw pile */}
          <div className="text-center">
            <div className={CARD_SIZE}>
              {gameState.playerDrawPile.length > 0 ? <CardBack /> : (
                <div className="w-full h-full border border-dashed border-slate-700 rounded-lg" />
              )}
            </div>
            <span className="text-[0.6rem] text-slate-500 block mt-0.5">
              Draw ({gameState.playerDrawPile.length})
            </span>
          </div>
        </div>

        {/* Center pile labels */}
        {gameState.phase === 'playing' && playerMoves.length > 0 && selectedCard === null && (
          <p className="text-xs text-slate-500">Tap a card, then tap a center pile to play it</p>
        )}
        {selectedCard !== null && (
          <p className="text-xs text-green-400">
            Playing {getRankDisplay(gameState.playerHand[selectedCard]?.rank ?? 0)}
            {getSuitSymbol(gameState.playerHand[selectedCard]?.suit ?? 'hearts')}
            — tap a green pile
          </p>
        )}

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            score={26 - playerCardsLeft}
            message={gameState.message}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <SpeedHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-win against opponent) ──────────────────

function SpeedRaceWrapper({ roomId, onLeave }: { roomId: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, opponentLevelUp, reportFinish } = useRaceMode(roomId, 'first_to_win')
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
      />
      <SpeedSinglePlayer onGameEnd={handleGameEnd} isMultiplayer />
    </div>
  )
}

export default function Speed() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'speed',
        gameName: 'Speed',
        modes: ['first_to_win'],
        maxPlayers: 2,
        hasDifficulty: false,
        modeDescriptions: { first_to_win: 'First to beat the AI wins' },
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <SpeedSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, _roomConfig, onLeave) =>
        <SpeedRaceWrapper roomId={roomId} onLeave={onLeave} />
      }
    />
  )
}
