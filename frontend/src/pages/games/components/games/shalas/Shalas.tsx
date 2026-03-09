/**
 * Shalas — card game UI.
 *
 * Interactive card game with special card mechanics.
 * Responsive: mobile (2-col) and desktop (3-col) layouts.
 */

import { useState, useCallback, useMemo, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE_COMPACT } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { getRankDisplay } from '../../../utils/cardUtils'
import {
  createShalasGame,
  playFromHand,
  playFromPairRow,
  playFromStackRow,
  playFromSecondRow,
  drawOneCard,
  chooseWildValue,
  chooseSelectorTarget,
  cantPlay,
  getActiveSource,
  hasValidPlay,
  rankName,
} from './shalasEngine'
import type { ShalasState } from './shalasEngine'

// ── Persistence ──────────────────────────────────────────────────────

interface SavedState {
  gameState: ShalasState
}

// ── Wild value choices ───────────────────────────────────────────────

const WILD_CHOICES = [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]

// ── Component ────────────────────────────────────────────────────────

export default function Shalas() {
  const { load, save, clear } = useGameState<SavedState>('shalas')

  const [gameState, setGameState] = useState<ShalasState>(
    () => load()?.gameState ?? createShalasGame()
  )

  // Music & SFX
  const song = useMemo(() => getSongForGame('shalas'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('shalas')

  // Undo support — store previous state
  const [prevState, setPrevState] = useState<ShalasState | null>(null)

  // Persist on changes
  const updateState = useCallback((newState: ShalasState) => {
    setGameState(prev => {
      setPrevState(prev)
      return newState
    })
    if (newState.phase !== 'won' && newState.phase !== 'lost') {
      save({ gameState: newState })
    } else {
      clear()
    }
  }, [save, clear])

  const handleUndo = useCallback(() => {
    if (!prevState) return
    setGameState(prevState)
    save({ gameState: prevState })
    setPrevState(null)
    setSelectedHandIndices([])
  }, [prevState, save])

  const handleNewGame = useCallback(() => {
    setGameState(createShalasGame())
    setSelectedHandIndices([])
    setPrevState(null)
    clear()
  }, [clear])

  // ── Hand selection state ────────────────────────────────────────

  const [selectedHandIndices, setSelectedHandIndices] = useState<number[]>([])

  // ── Game actions ─────────────────────────────────────────────────

  const activeSource = getActiveSource(gameState)

  // Safety net: if no cards left to play anywhere, the player has won
  useEffect(() => {
    if (activeSource === 'none' && gameState.drawStack.length === 0 && gameState.phase === 'playing') {
      updateState({ ...gameState, phase: 'won', message: 'You win! All cards cleared!' })
    }
  }, [activeSource, gameState, updateState])

  // Clear selection when game state changes phase or hand changes length
  const clearSelection = useCallback(() => setSelectedHandIndices([]), [])

  const handleHandClick = useCallback((index: number) => {
    if (gameState.phase === 'choose_selector') {
      sfx.play('place')
      updateState(chooseSelectorTarget(gameState, { type: 'hand', index }))
      clearSelection()
      return
    }
    if (gameState.phase !== 'playing' || activeSource !== 'hand') return

    const clickedCard = gameState.hand[index]

    // Toggle selection
    if (selectedHandIndices.includes(index)) {
      // Deselect
      setSelectedHandIndices(prev => prev.filter(i => i !== index))
    } else {
      // Can only select cards of the same rank as already selected
      if (selectedHandIndices.length > 0) {
        const selectedRank = gameState.hand[selectedHandIndices[0]].rank
        if (clickedCard.rank !== selectedRank) {
          // Different rank — start a new selection
          setSelectedHandIndices([index])
          return
        }
      }
      setSelectedHandIndices(prev => [...prev, index])
    }
  }, [gameState, activeSource, selectedHandIndices, sfx, updateState, clearSelection])

  /** Double-click a hand card to play it immediately. */
  const handleHandDoubleClick = useCallback((index: number) => {
    if (gameState.phase !== 'playing' || activeSource !== 'hand') return
    const result = playFromHand(gameState, [index])
    if (result !== gameState) sfx.play('place')
    updateState(result)
    clearSelection()
  }, [gameState, activeSource, updateState, sfx, clearSelection])

  /** Play the currently selected hand cards to discard. */
  const handlePlaySelected = useCallback(() => {
    if (selectedHandIndices.length === 0) return
    if (gameState.phase !== 'playing' || activeSource !== 'hand') return

    const result = playFromHand(gameState, selectedHandIndices)
    if (result !== gameState) {
      sfx.play(selectedHandIndices.length >= 4 ? 'win' : 'place')
    }
    updateState(result)
    clearSelection()
  }, [gameState, activeSource, selectedHandIndices, updateState, sfx, clearSelection])

  const handlePairClick = useCallback((stackIndex: number, position: 'faceUp' | 'faceDown') => {
    if (gameState.phase === 'choose_selector') {
      sfx.play('place')
      updateState(chooseSelectorTarget(gameState, { type: 'pairRow', stackIndex, card: position }))
      return
    }
    if (gameState.phase !== 'playing' || activeSource !== 'pairRow') return
    const result = playFromPairRow(gameState, stackIndex, position)
    if (result !== gameState) sfx.play('place')
    updateState(result)
  }, [gameState, activeSource, updateState, sfx])

  const handleStackClick = useCallback((stackIndex: number) => {
    if (gameState.phase === 'choose_selector') {
      sfx.play('place')
      updateState(chooseSelectorTarget(gameState, { type: 'stackRow', stackIndex }))
      return
    }
    if (gameState.phase !== 'playing' || activeSource !== 'stackRow') return
    const result = playFromStackRow(gameState, stackIndex)
    if (result !== gameState) sfx.play('flip')
    updateState(result)
  }, [gameState, activeSource, updateState, sfx])

  const handleSecondRowClick = useCallback((index: number) => {
    if (gameState.phase === 'choose_selector') {
      sfx.play('place')
      updateState(chooseSelectorTarget(gameState, { type: 'secondRow', index }))
      return
    }
    if (gameState.phase !== 'playing' || activeSource !== 'secondRow') return
    const result = playFromSecondRow(gameState, index)
    if (result !== gameState) sfx.play('place')
    updateState(result)
  }, [gameState, activeSource, updateState, sfx])

  const handleWildChoice = useCallback((rank: number) => {
    sfx.play('place')
    updateState(chooseWildValue(gameState, rank))
  }, [gameState, updateState, sfx])

  const handleDrawCard = useCallback(() => {
    if (gameState.phase !== 'playing' || gameState.drawStack.length === 0) return
    sfx.play('flip')
    updateState(drawOneCard(gameState))
    clearSelection()
  }, [gameState, updateState, sfx, clearSelection])

  const handleCantPlay = useCallback(() => {
    sfx.play('flip')
    updateState(cantPlay(gameState))
  }, [gameState, updateState, sfx])

  // ── Derived state ────────────────────────────────────────────────

  const canPlayerPlay = gameState.phase === 'playing' && hasValidPlay(gameState)
  const { hand, secondRow, stackRow, pairRow, drawStack, discardPile } = gameState

  // ── Special card tooltip ────────────────────────────────────────

  const selectedSpecialInfo = useMemo(() => {
    if (selectedHandIndices.length === 0 || activeSource !== 'hand') return null
    const rank = hand[selectedHandIndices[0]]?.rank
    if (!rank) return null

    if (selectedHandIndices.length >= 4) {
      return { label: '4-of-a-Kind', desc: 'Resets discard to Ace. All 4 cards stay on pile.', color: 'text-purple-400' }
    }
    if (rank === 10) return { label: 'Destroyer', desc: 'Removes itself + entire discard pile from the game.', color: 'text-red-400' }
    if (rank === 2) return { label: 'Wildcard', desc: 'Choose any reset value (A or 3–K). The 2 stays on discard.', color: 'text-cyan-400' }
    if (rank === 7) return { label: 'Selector', desc: 'Pick any table card to move to discard.', color: 'text-emerald-400' }
    if (rank === 1) return { label: 'Ace', desc: 'Highest & lowest. Any card can follow except King.', color: 'text-amber-400' }
    return null
  }, [selectedHandIndices, hand, activeSource])

  // ── Shared sub-renderers ─────────────────────────────────────────

  const canDraw = gameState.phase === 'playing' && drawStack.length > 0

  const renderDrawStack = () => (
    <div className="flex flex-col items-center">
      <span className="text-[0.55rem] text-slate-500 uppercase tracking-wider mb-1">Draw</span>
      <div
        className={`relative ${canDraw ? 'cursor-pointer' : ''}`}
        style={{ width: '3.5rem', height: '5rem' }}
        onClick={canDraw ? handleDrawCard : undefined}
      >
        {drawStack.length > 0 ? (
          <>
            {drawStack.length > 2 && (
              <div className={`${CARD_SIZE_COMPACT} absolute`} style={{ top: '2px', left: '2px' }}><CardBack /></div>
            )}
            {drawStack.length > 1 && (
              <div className={`${CARD_SIZE_COMPACT} absolute`} style={{ top: '1px', left: '1px' }}><CardBack /></div>
            )}
            <div className={`${CARD_SIZE_COMPACT} absolute top-0 left-0 ${canDraw ? 'hover:ring-2 hover:ring-yellow-400 rounded-md' : ''}`}><CardBack /></div>
            <div className="absolute -bottom-3 left-0 right-0 text-center">
              <span className="text-[0.6rem] text-slate-500">{drawStack.length}</span>
            </div>
          </>
        ) : (
          <div className={`${CARD_SIZE_COMPACT} rounded-md border border-dashed border-slate-600/40 flex items-center justify-center`}>
            <span className="text-slate-600 text-[0.6rem]">Empty</span>
          </div>
        )}
      </div>
    </div>
  )

  const renderDiscardPile = () => (
    <div className="flex flex-col items-center">
      <span className="text-[0.55rem] text-slate-500 uppercase tracking-wider mb-1">
        Discard{discardPile.length > 0 ? ` (${discardPile.length})` : ''}
      </span>
      <div className="relative" style={{ width: '7rem', height: '7rem' }}>
        {discardPile.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className={`${CARD_SIZE_COMPACT} rounded-md border border-dashed border-slate-600/40 flex items-center justify-center`}>
              <span className="text-slate-600 text-[0.6rem]">Empty</span>
            </div>
          </div>
        ) : (
          discardPile.map((card, i) => {
            const count = discardPile.length
            const spread = Math.min(10, 120 / Math.max(count, 1))
            const angle = (i - (count - 1) / 2) * spread
            return (
              <div
                key={i}
                className={`${CARD_SIZE_COMPACT} absolute`}
                style={{
                  left: '50%', bottom: '0', marginLeft: '-1.5rem',
                  transform: `rotate(${angle}deg)`, transformOrigin: '50% 100%', zIndex: i,
                }}
              >
                <CardFace card={card} />
              </div>
            )
          })
        )}
      </div>
    </div>
  )

  const renderSpecialInfo = () =>
    selectedSpecialInfo ? (
      <div className="mt-3 px-2 py-1.5 rounded border border-slate-700 bg-slate-800/60 max-w-[7rem] text-center">
        <div className={`text-[0.6rem] font-bold ${selectedSpecialInfo.color}`}>{selectedSpecialInfo.label}</div>
        <div className="text-[0.5rem] text-slate-400 leading-tight mt-0.5">{selectedSpecialInfo.desc}</div>
      </div>
    ) : null

  const isClickable = (source: string) =>
    gameState.phase === 'choose_selector' || activeSource === source

  const renderTable = (gapPair: string, gapStack: string) => (
    <>
      {/* Row 4: pair stacks */}
      <div className={`w-full flex justify-center ${gapPair}`}>
        {pairRow.map((pair, i) => (
          <div key={i} className="relative" style={{ width: '4.5rem', height: '5.5rem' }}>
            {pair.faceDown ? (
              <div
                className={`${CARD_SIZE_COMPACT} absolute top-0 left-0 group ${isClickable('pairRow') && pair.faceUp === null ? 'cursor-pointer' : ''}`}
                onClick={() => pair.faceUp === null && handlePairClick(i, 'faceDown')}
              >
                <CardBack />
                {isClickable('pairRow') && pair.faceUp === null && (
                  <div className="absolute inset-0 rounded-md ring-0 group-hover:ring-2 group-hover:ring-yellow-400 pointer-events-none z-10" />
                )}
              </div>
            ) : (
              <div className={`${CARD_SIZE_COMPACT} absolute top-0 left-0 rounded-md border border-dashed border-slate-600/20`} />
            )}
            {pair.faceUp ? (
              <div
                className={`${CARD_SIZE_COMPACT} absolute group ${isClickable('pairRow') ? 'cursor-pointer' : ''}`}
                style={{ top: '10px', left: '14px' }}
                onClick={() => handlePairClick(i, 'faceUp')}
                onDoubleClick={() => handlePairClick(i, 'faceUp')}
              >
                <CardFace card={pair.faceUp} />
                {isClickable('pairRow') && (
                  <div className="absolute inset-0 rounded-md ring-0 group-hover:ring-2 group-hover:ring-yellow-400 pointer-events-none z-10" />
                )}
              </div>
            ) : pair.faceDown ? (
              <div className={`${CARD_SIZE_COMPACT} absolute rounded-md border border-dashed border-slate-600/20`} style={{ top: '10px', left: '14px' }} />
            ) : null}
          </div>
        ))}
      </div>

      {/* Row 3: face-down stacks */}
      <div className={`w-full flex justify-center ${gapStack}`}>
        {stackRow.map((stack, si) => (
          <div
            key={si}
            className={`relative group ${isClickable('stackRow') && stack.length > 0 ? 'cursor-pointer' : ''}`}
            style={{ width: '3.5rem', height: '5.25rem' }}
            onClick={() => stack.length > 0 && handleStackClick(si)}
          >
            {stack.length > 0 ? (
              <>
                {stack.map((_, ci) => {
                  const isTop = ci === stack.length - 1
                  return (
                    <div key={ci} className={`${CARD_SIZE_COMPACT} absolute`}
                      style={{ top: `${ci * 2}px`, left: `${ci * 1}px`, zIndex: ci }}>
                      <CardBack />
                      {isTop && isClickable('stackRow') && (
                        <div className="absolute inset-0 rounded-md ring-0 group-hover:ring-2 group-hover:ring-yellow-400 pointer-events-none z-10" />
                      )}
                    </div>
                  )
                })}
              </>
            ) : (
              <div className={`${CARD_SIZE_COMPACT} rounded-md border border-dashed border-slate-600/20`} />
            )}
            <div className="absolute -bottom-3 left-0 right-0 text-center">
              <span className="text-[0.6rem] text-slate-500">{stack.length}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Row 2: face-up cards */}
      <div className="w-full flex justify-center gap-2">
        {secondRow.map((card, i) => (
          <div
            key={i}
            className={`${CARD_SIZE_COMPACT} relative group ${isClickable('secondRow') ? 'cursor-pointer' : ''}`}
            onClick={() => handleSecondRowClick(i)}
            onDoubleClick={() => handleSecondRowClick(i)}
          >
            <CardFace card={card} />
            {isClickable('secondRow') && (
              <div className="absolute inset-0 rounded-md ring-0 group-hover:ring-2 group-hover:ring-yellow-400 pointer-events-none z-10" />
            )}
          </div>
        ))}
        {secondRow.length === 0 && (
          <span className="text-[0.6rem] text-slate-600">Row cleared</span>
        )}
      </div>

      {/* Row 1: Player's hand */}
      <div className="w-full flex flex-col items-center">
        <span className="text-[0.6rem] text-slate-400 uppercase tracking-widest mb-1">Your Hand</span>
        <div className="relative py-2 rounded-lg border border-emerald-700/40 bg-emerald-900/20 shadow-inner w-full"
          style={{ height: '6rem' }}
        >
          {hand.length > 0 ? hand.map((card, i) => {
            const isSelected = selectedHandIndices.includes(i)
            const isHandActive = activeSource === 'hand' || gameState.phase === 'choose_selector'
            // Fan cards across full container width; last card sits at right edge
            // Reserve ~3rem (48px) for the rightmost card to be fully visible
            const pct = hand.length === 1 ? 50 : (i / (hand.length - 1)) * 100
            const leftCalc = hand.length === 1
              ? 'calc(50% - 1.5rem)'
              : `calc(${pct}% - ${pct * 3 / 100}rem)`
            return (
              <div
                key={i}
                className={`${CARD_SIZE_COMPACT} absolute ${
                  isHandActive ? 'cursor-pointer rounded-md transition-all' : ''
                } ${isSelected ? 'ring-2 ring-yellow-400 -translate-y-2 rounded-md' : ''}`}
                style={{ left: leftCalc, top: '0.5rem', zIndex: isSelected ? 50 : i }}
                onClick={() => handleHandClick(i)}
                onDoubleClick={() => handleHandDoubleClick(i)}
              >
                <CardFace card={card} selected={isSelected} />
              </div>
            )
          }) : (
            <span className="absolute inset-0 flex items-center justify-center text-[0.6rem] text-slate-600">Hand empty — play from table</span>
          )}
        </div>
        {/* Play selected button */}
        {selectedHandIndices.length > 0 && activeSource === 'hand' && gameState.phase === 'playing' && (
          <div className="flex gap-2 mt-2">
            <button
              onClick={handlePlaySelected}
              className="px-4 py-1.5 text-xs rounded bg-emerald-700 text-emerald-100 hover:bg-emerald-600 transition-colors"
            >
              Play {selectedHandIndices.length > 1
                ? `${selectedHandIndices.length} × ${getRankDisplay(gameState.hand[selectedHandIndices[0]].rank)}`
                : getRankDisplay(gameState.hand[selectedHandIndices[0]].rank)}
            </button>
            <button
              onClick={clearSelection}
              className="px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </>
  )

  // ── Controls toolbar ───────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <button
          onClick={handleNewGame}
          className="px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
        >
          New Game
        </button>
        {prevState && (
          <button
            onClick={handleUndo}
            className="px-3 py-1.5 text-xs rounded bg-indigo-700 text-indigo-100 hover:bg-indigo-600 transition-colors"
          >
            Undo
          </button>
        )}
        {gameState.phase === 'playing' && !canPlayerPlay && (
          <button
            onClick={handleCantPlay}
            className="px-3 py-1.5 text-xs rounded bg-amber-700 text-amber-100 hover:bg-amber-600 transition-colors"
          >
            Can&apos;t Play
          </button>
        )}
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <GameLayout
      title="Shalas"
      controls={controls}
      subtitle={<span className="text-[0.5rem] text-slate-600">&copy; 2026 David Damir Greene</span>}
    >
      {/* Status message */}
      <div className="text-center mb-3">
        <span className="text-xs text-slate-300">{gameState.message}</span>
        {gameState.effectiveRank > 0 && gameState.phase !== 'choose_wild' && (
          <span className="text-xs text-amber-400 ml-2">
            (min: {rankName(gameState.effectiveRank)})
          </span>
        )}
      </div>

      {/* Wild value chooser */}
      {gameState.phase === 'choose_wild' && (
        <div className="flex flex-wrap justify-center gap-1.5 mb-3 px-2">
          {WILD_CHOICES.map(rank => (
            <button
              key={rank}
              onClick={() => handleWildChoice(rank)}
              className="px-2 py-1 text-xs rounded bg-cyan-700 text-cyan-100 hover:bg-cyan-600 transition-colors min-w-[2rem]"
            >
              {getRankDisplay(rank)}
            </button>
          ))}
        </div>
      )}

      {/* Selector prompt */}
      {gameState.phase === 'choose_selector' && (
        <div className="text-center mb-3">
          <span className="text-xs text-cyan-400">Click any card on the table to move it to discard</span>
        </div>
      )}

      {/* ── Mobile layout: two columns ──────────────────────────────── */}
      <div className="flex sm:hidden w-full gap-3">
        <div className="flex flex-col items-center gap-6 pt-2">
          {renderDrawStack()}
          {renderSpecialInfo()}
          {renderDiscardPile()}
        </div>
        <div className="flex-1 flex flex-col items-center space-y-4">
          {renderTable('gap-4', 'gap-3')}
        </div>
      </div>

      {/* ── Desktop: three-column layout ────────────────────────────── */}
      <div className="hidden sm:flex w-full max-w-2xl gap-4">
        <div className="flex flex-col items-center pt-2">
          {renderDrawStack()}
          {renderSpecialInfo()}
        </div>
        <div className="flex-1 flex flex-col items-center space-y-4">
          {renderTable('gap-6 sm:gap-8', 'gap-4 sm:gap-6')}
        </div>
        <div className="flex flex-col items-center pt-2">
          {renderDiscardPile()}
        </div>
      </div>

      {/* Win overlay */}
      {gameState.phase === 'won' && (
        <GameOverModal
          status="won"
          message="All cards cleared!"
          onPlayAgain={handleNewGame}
          music={music}
          sfx={sfx}
        />
      )}
    </GameLayout>
  )
}
