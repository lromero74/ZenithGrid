/**
 * Rummy 500 — 2-player card game vs AI.
 *
 * Draw, form melds (sets/runs), lay off on any meld, discard.
 * First to 500 cumulative points wins.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
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
  createRummy500Game,
  drawFromStock,
  drawFromDiscard,
  toggleSelectCard,
  meldCards,
  layOff,
  discard,
  canLayOff,
  newRound,
  type Rummy500State,
} from './Rummy500Engine'

interface SavedState {
  gameState: Rummy500State
  gameStatus: GameStatus
}

// ── Help modal ──────────────────────────────────────────────────────
function Rummy500Help({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Rummy 500</h2>

        <Sec title="Goal">
          <p>Be the first player to reach <B>500 cumulative points</B> across multiple rounds. Score points by forming melds and laying off cards.</p>
        </Sec>

        <Sec title="Card Values">
          <ul className="space-y-1">
            <Li><B>Ace</B> — 1 point (or 15 in a high run with King).</Li>
            <Li><B>2–10</B> — Face value.</Li>
            <Li><B>J, Q, K</B> — 10 points each.</Li>
          </ul>
        </Sec>

        <Sec title="Turn Structure">
          <ul className="space-y-1">
            <Li><B>Draw</B> — Take the top card from the stock pile, or take from the discard pile.</Li>
            <Li><B>Meld</B> — Optionally play melds from your hand (sets or runs of 3+ cards).</Li>
            <Li><B>Lay Off</B> — Optionally add cards from your hand to any existing meld on the table.</Li>
            <Li><B>Discard</B> — End your turn by placing one card on the discard pile.</Li>
          </ul>
        </Sec>

        <Sec title="Melds">
          <ul className="space-y-1">
            <Li><B>Set</B> — 3 or 4 cards of the same rank, each a different suit.</Li>
            <Li><B>Run</B> — 3+ consecutive cards of the same suit (Ace can be low A-2-3 or high Q-K-A).</Li>
          </ul>
        </Sec>

        <Sec title="Scoring">
          <ul className="space-y-1">
            <Li>Points come from cards in your melds and lay-offs.</Li>
            <Li>Cards left in your hand at round end are <B>subtracted</B> from your score.</Li>
            <Li>A round ends when someone empties their hand or the stock runs out.</Li>
          </ul>
        </Sec>

        <Sec title="Strategy Tips">
          <ul className="space-y-1">
            <Li>Meld early to lock in points — cards in hand are a liability.</Li>
            <Li>Watch what the AI discards to guess what they're collecting.</Li>
            <Li>Laying off on the AI's melds scores you points too!</Li>
            <Li>Keep low-value cards in hand to minimize penalties at round end.</Li>
          </ul>
        </Sec>
      </div>
    </div>
  )
}

export default function Rummy500() {
  const { load, save, clear } = useGameState<SavedState>('rummy-500')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('rummy-500'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('rummy-500')

  const [gameState, setGameState] = useState<Rummy500State>(
    () => saved?.gameState ?? createRummy500Game()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [layOffMode, setLayOffMode] = useState<number | null>(null) // card index being laid off
  const [showHelp, setShowHelp] = useState(false)

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      if (gameState.scores[0] >= 500) sfx.play('gin')
      setGameStatus(gameState.scores[0] >= 500 ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  const handleDrawStock = useCallback(() => { music.init(); sfx.init(); music.start(); sfx.play('draw'); setGameState(prev => drawFromStock(prev)) }, [])
  const handleDrawDiscard = useCallback(() => { music.init(); sfx.init(); music.start(); sfx.play('draw'); setGameState(prev => drawFromDiscard(prev)) }, [])
  const handleMeld = useCallback(() => { sfx.play('meld'); setGameState(prev => meldCards(prev)) }, [])
  const handleNewRound = useCallback(() => setGameState(prev => newRound(prev)), [])

  const handleCardClick = useCallback((index: number) => {
    if (gameState.phase === 'meld' && gameState.hasDrawn) {
      if (layOffMode !== null) {
        // Cancel lay off mode if clicking another card
        setLayOffMode(null)
      }
      setGameState(prev => toggleSelectCard(prev, index))
    }
  }, [gameState.phase, gameState.hasDrawn, layOffMode])

  const handleDiscard = useCallback((index: number) => {
    setLayOffMode(null)
    sfx.play('draw')
    setGameState(prev => discard(prev, index))
  }, [])

  const handleLayOffStart = useCallback((cardIndex: number) => {
    setLayOffMode(cardIndex)
  }, [])

  const handleMeldClick = useCallback((meldIndex: number) => {
    if (layOffMode === null) return
    setGameState(prev => {
      const next = layOff(prev, layOffMode, meldIndex)
      return next
    })
    setLayOffMode(null)
  }, [layOffMode])

  const handleNewGame = useCallback(() => {
    setGameState(createRummy500Game())
    setGameStatus('playing')
    setLayOffMode(null)
    clear()
  }, [clear])

  const isDrawPhase = gameState.phase === 'draw' && gameState.currentPlayer === 0
  const isMeldPhase = gameState.phase === 'meld' && gameState.hasDrawn && gameState.currentPlayer === 0
  const hasSelection = gameState.selectedCards.length > 0
  const topDiscard = gameState.discardPile.length > 0
    ? gameState.discardPile[gameState.discardPile.length - 1]
    : null

  // Check which melds can accept the lay-off card
  const layOffTargets = layOffMode !== null
    ? gameState.melds.map((meld, i) =>
        canLayOff(gameState.hands[0][layOffMode], meld) ? i : -1
      ).filter(i => i >= 0)
    : []

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3 text-xs">
        <span className="text-white">You: {gameState.scores[0]}</span>
        <span className="text-slate-400">AI: {gameState.scores[1]}</span>
      </div>
      <span className="text-xs text-slate-400">
        Stock: {gameState.stock.length}
      </span>
      <div className="flex items-center gap-2">
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play">
          <HelpCircle className="w-4 h-4 text-blue-400" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Rummy 500" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* AI hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400 mb-1 block">AI ({gameState.hands[1].length} cards)</span>
          <div className="flex gap-1 justify-center flex-wrap">
            {gameState.hands[1].map((_, i) => (
              <div key={i} className={CARD_SIZE}>
                <CardBack />
              </div>
            ))}
          </div>
        </div>

        {/* Stock + Discard pile */}
        <div className="flex gap-4 items-center justify-center">
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">Stock</span>
            <div
              className={`${CARD_SIZE} ${
                isDrawPhase ? 'cursor-pointer ring-2 ring-blue-400/50 rounded-md' : ''
              }`}
              onClick={isDrawPhase ? handleDrawStock : undefined}
            >
              {gameState.stock.length > 0 ? <CardBack /> : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                  Empty
                </div>
              )}
            </div>
          </div>
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">Discard</span>
            <div
              className={`${CARD_SIZE} ${
                isDrawPhase && topDiscard ? 'cursor-pointer ring-2 ring-blue-400/50 rounded-md' : ''
              }`}
              onClick={isDrawPhase ? handleDrawDiscard : undefined}
            >
              {topDiscard ? <CardFace card={topDiscard} /> : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50" />
              )}
            </div>
          </div>
        </div>

        {/* Melds area */}
        {gameState.melds.length > 0 && (
          <div className="w-full">
            <span className="text-xs text-slate-400 mb-1 block text-center">Melds</span>
            <div className="flex flex-wrap gap-3 justify-center">
              {gameState.melds.map((meld, mi) => (
                <div
                  key={mi}
                  className={`flex gap-0.5 p-1 rounded-lg border transition-colors ${
                    layOffTargets.includes(mi)
                      ? 'border-emerald-400/60 bg-emerald-900/20 cursor-pointer ring-1 ring-emerald-400/40'
                      : 'border-slate-700 bg-slate-800/50'
                  }`}
                  onClick={() => layOffTargets.includes(mi) && handleMeldClick(mi)}
                >
                  {meld.cards.map((card, ci) => (
                    <div key={ci} className={CARD_SIZE}>
                      <CardFace card={{ ...card, faceUp: true }} />
                    </div>
                  ))}
                  <span className="text-[0.5rem] text-slate-500 self-end ml-0.5">
                    {meld.type}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Action buttons */}
        {isMeldPhase && (
          <div className="flex gap-2 flex-wrap justify-center">
            {hasSelection && (
              <button
                onClick={handleMeld}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Meld Selected ({gameState.selectedCards.length} cards)
              </button>
            )}
            {layOffMode !== null && (
              <button
                onClick={() => setLayOffMode(null)}
                className="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Cancel Lay Off
              </button>
            )}
          </div>
        )}

        {/* Player hand */}
        <div className="text-center w-full">
          <span className="text-xs text-slate-400 mb-1 block">
            Your Hand
            {isMeldPhase && (
              <span className="text-slate-500 ml-2">
                (click to select for meld, right-click to lay off)
              </span>
            )}
          </span>
          <div className="flex gap-1 justify-center flex-wrap">
            {gameState.hands[0].map((card, i) => {
              const isSelected = gameState.selectedCards.includes(i)
              const isLayOffSource = layOffMode === i

              return (
                <div
                  key={i}
                  className={`${CARD_SIZE} transition-transform ${
                    isMeldPhase ? 'cursor-pointer hover:-translate-y-1' : ''
                  } ${isSelected ? '-translate-y-2' : ''}
                  ${isLayOffSource ? '-translate-y-2' : ''}
                  `}
                  onClick={() => {
                    if (isMeldPhase) {
                      handleCardClick(i)
                    }
                  }}
                  onContextMenu={(e) => {
                    e.preventDefault()
                    if (isMeldPhase && gameState.melds.length > 0) {
                      handleLayOffStart(i)
                    }
                  }}
                >
                  <CardFace
                    card={card}
                    selected={isSelected || isLayOffSource}
                  />
                </div>
              )
            })}
          </div>

          {/* Discard buttons: show below each card when in meld phase */}
          {isMeldPhase && gameState.hands[0].length > 0 && (
            <div className="flex gap-1 justify-center flex-wrap mt-2">
              {gameState.hands[0].map((_, i) => (
                <button
                  key={i}
                  onClick={() => handleDiscard(i)}
                  className="w-14 sm:w-16 text-[0.5rem] py-0.5 bg-red-800/60 hover:bg-red-700 text-red-200 rounded transition-colors"
                >
                  Discard
                </button>
              ))}
            </div>
          )}

          {/* Lay off instructions */}
          {isMeldPhase && gameState.melds.length > 0 && layOffMode === null && (
            <p className="text-[0.6rem] text-slate-500 mt-1">
              Right-click a card, then click a meld to lay it off
            </p>
          )}
          {layOffMode !== null && (
            <p className="text-[0.6rem] text-emerald-400 mt-1">
              Click a highlighted meld to lay off the selected card
            </p>
          )}
        </div>

        {/* Round over */}
        {gameState.phase === 'roundOver' && (
          <div className="text-center space-y-2">
            <p className="text-sm text-emerald-400">{gameState.message}</p>
            <div className="text-xs text-slate-400">
              Scores: You {gameState.scores[0]} | AI {gameState.scores[1]}
            </div>
            <button
              onClick={handleNewRound}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Next Round
            </button>
          </div>
        )}

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
      {showHelp && <Rummy500Help onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}
