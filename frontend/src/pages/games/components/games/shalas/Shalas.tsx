/**
 * Shalas — card game UI.
 *
 * Interactive card game with special card mechanics.
 * Responsive: mobile (2-col) and desktop (3-col) layouts.
 */

import { useState, useCallback, useMemo, useEffect } from 'react'
import { HelpCircle, X } from 'lucide-react'
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
  isConsecutiveRun,
  rankName,
} from './shalasEngine'
import type { ShalasState } from './shalasEngine'

// ── Persistence ──────────────────────────────────────────────────────

interface SavedState {
  gameState: ShalasState
}

// ── Wild value choices ───────────────────────────────────────────────

const WILD_CHOICES = [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]

// ── Help modal ───────────────────────────────────────────────────────

function ShalasHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-1">How to Play Shalas</h2>
        <p className="text-[0.65rem] text-slate-500 mb-4">&copy; 2026 David Damir Greene</p>

        {/* Goal */}
        <Section title="Goal">
          Clear every card from your hand and the table. The discard pile and
          burned pile don&apos;t count — only cards you still control matter.
        </Section>

        {/* Setup */}
        <Section title="Setup">
          A standard 52-card deck is shuffled and dealt into four areas:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Row 4</B> (top) — 3 stacks of 2 cards each: one face-down, one face-up on top.</Li>
            <Li><B>Row 3</B> — 4 stacks of 3 face-down cards.</Li>
            <Li><B>Row 2</B> — 4 face-up cards.</Li>
            <Li><B>Your Hand</B> (bottom) — 5 face-up cards. The rest go to the <B>draw stack</B>.</Li>
          </ul>
        </Section>

        {/* Basic play */}
        <Section title="Playing Cards">
          <ul className="space-y-1 text-slate-300">
            <Li>Play a card from your hand onto the discard pile. It must be
              <B> equal or higher rank</B> than the current top card.</Li>
            <Li>Click a card to select it, then click <B>Play</B>. Or double-click to play instantly.</Li>
            <Li>You may select <B>multiple cards of the same rank</B> and play them together in one move.</Li>
            <Li>When your hand drops below 3 cards, it <B>auto-refills to 5</B> from the draw stack.</Li>
            <Li>You can also click the draw stack at any time to draw an extra card.</Li>
          </ul>
        </Section>

        {/* Card order */}
        <Section title="Card Ranking">
          <p className="text-slate-300">
            Low to high: <B>A, 3, 4, 5, 6, 7, 8, 9, 10, J, Q, K</B>
          </p>
          <p className="text-slate-400 text-[0.7rem] mt-1">
            The <B>Ace</B> is special — it&apos;s always playable (acts as
            the highest card), but after it&apos;s played, the effective rank
            resets to 1. Any card except King can follow an Ace.
          </p>
          <p className="text-slate-400 text-[0.7rem] mt-1">
            <B>2</B> is not in the normal rank order — it&apos;s a Wildcard (see below).
          </p>
        </Section>

        {/* Special cards */}
        <Section title="Special Cards">
          <div className="space-y-3">
            <SpecialCard color="text-red-400" name="10 — Destroyer">
              Removes itself <B>and the entire discard pile</B> from the
              game permanently (burned). The discard resets to empty — any
              card can be played next. Only triggers when the discard pile
              has at least one card in it.
            </SpecialCard>
            <SpecialCard color="text-cyan-400" name="2 — Wildcard">
              Always playable regardless of the current rank. After playing
              a 2, you <B>choose the new effective rank</B> (Ace, or 3
              through King). The 2 stays on the discard pile. If you
              choose <B>7</B>, the Selector ability triggers — pick a
              table card. If you choose <B>10</B>, the Destroyer ability
              triggers — the discard pile is cleared.
            </SpecialCard>
            <SpecialCard color="text-emerald-400" name="7 — Selector">
              Always playable. After playing a 7, <B>pick any card from the
              table</B> (any row, including your hand) to move to the
              discard pile. That card becomes the new top. If you select a
              10, the Destroyer effect triggers automatically.
            </SpecialCard>
            <SpecialCard color="text-amber-400" name="Ace — Dual Rank">
              Always playable (highest card). After played, effective rank
              becomes 1. <B>Kings cannot be played on top of an Ace</B> —
              only lower cards or special cards (2, 7, 10) can follow.
            </SpecialCard>
            <SpecialCard color="text-purple-400" name="4-of-a-Kind — Wild Set">
              If you play cards that complete a set of 4 matching the same
              rank, it becomes a Wild Set. This can happen by playing 4 from
              your hand at once, <B>or</B> by playing cards that match the
              top of the discard pile to reach 4. For example, if a 6 is on
              top of the discard and you play three 6s, that&apos;s a
              4-of-a-kind. Works just like the <B>2 Wildcard</B> — you
              choose the new rank (A, or 3–K), and choosing 7 or 10
              triggers their special abilities too.
            </SpecialCard>
          </div>
        </Section>

        {/* Table progression */}
        <Section title="Table Progression">
          You must empty your hand (and draw stack) before touching the table.
          Then play from the table <B>top to bottom</B>:
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li><B>Row 4</B> first — face-up cards, then face-down cards revealed as you play.</li>
            <li><B>Row 3</B> next — all face-down (blind plays). Click a stack to flip and play the top card.</li>
            <li><B>Row 2</B> last — the 4 face-up cards.</li>
          </ol>
        </Section>

        {/* Blind plays */}
        <Section title="Blind Plays (Face-Down Cards)">
          When playing face-down cards from Row 3 or Row 4, the card is revealed
          as you play it. If it <B>can&apos;t beat the current top</B>, the play fails:
          the revealed card plus <B>the entire discard pile</B> go into your hand.
          The discard resets to empty.
        </Section>

        {/* Can't play */}
        <Section title="Can&apos;t Play?">
          If no card in your active area can beat the discard, a <B>&quot;Can&apos;t
          Play&quot;</B> button appears. Clicking it shuffles the discard pile,
          and you take 10 cards from it into your hand. Remaining cards stay
          on the discard pile. This is a penalty — avoid it if you can!
        </Section>

        {/* Invalid plays */}
        <Section title="Invalid Play Penalty">
          If you play a card that <B>doesn&apos;t meet the rank requirement</B>,
          you pick up the played card plus the entire discard pile into your hand.
          The discard resets to empty.
        </Section>

        {/* Strategy tips */}
        <Section title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li>Save <B>10s</B> (Destroyers) for when the discard pile is large — burn more cards at once.</Li>
            <Li>Use <B>2s</B> (Wildcards) to reset a high discard rank back down to something manageable.</Li>
            <Li>The <B>7</B> (Selector) lets you move a problematic card off the table to the discard. Use it strategically to clear face-up cards from Row 4.</Li>
            <Li>Playing an <B>Ace</B> blocks Kings — useful for controlling what can follow.</Li>
            <Li>Try to <B>clear face-up pairs</B> from Row 4 early to access the face-down cards underneath.</Li>
            <Li>Keep your hand small when possible — a huge hand means more cards to clear later.</Li>
            <Li>Draw extra cards when the draw stack is running low to keep options open.</Li>
          </ul>
        </Section>

        {/* Controls */}
        <Section title="Controls">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Click</B> a hand card to select it. Click more of the same rank to multi-select.</Li>
            <Li><B>Double-click</B> a hand card to play it instantly.</Li>
            <Li><B>Play</B> button appears when cards are selected.</Li>
            <Li><B>Undo</B> reverts the last action (one level).</Li>
            <Li><B>Draw stack</B> — click to draw an extra card into your hand.</Li>
            <Li>Yellow highlight shows which cards are currently clickable.</Li>
          </ul>
        </Section>

        <div className="mt-4 pt-3 border-t border-slate-700 text-center">
          <button onClick={onClose} className="px-6 py-2 text-sm rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors">
            Got it!
          </button>
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="text-sm font-semibold text-slate-200 mb-1">{title}</h3>
      <div className="text-xs leading-relaxed text-slate-400">{children}</div>
    </div>
  )
}

function SpecialCard({ color, name, children }: { color: string; name: string; children: React.ReactNode }) {
  return (
    <div className="pl-3 border-l-2 border-slate-700">
      <div className={`text-xs font-bold ${color} mb-0.5`}>{name}</div>
      <div className="text-xs text-slate-400 leading-relaxed">{children}</div>
    </div>
  )
}

function Li({ children }: { children: React.ReactNode }) {
  return <li className="flex gap-1.5 text-xs"><span className="text-slate-600 mt-0.5">•</span><span>{children}</span></li>
}

function B({ children }: { children: React.ReactNode }) {
  return <span className="text-white font-medium">{children}</span>
}

// ── Multiplayer imports ──────────────────────────────────────────────

import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { ShalasMultiplayer } from './ShalasMultiplayer'

// ── Component ────────────────────────────────────────────────────────

function ShalasSinglePlayer() {
  const { load, save, clear } = useGameState<SavedState>('shalas')

  const [gameState, setGameState] = useState<ShalasState>(
    () => load()?.gameState ?? createShalasGame()
  )

  // Music & SFX
  const song = useMemo(() => getSongForGame('shalas'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('shalas')

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

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
  const [selectedBlindCard, setSelectedBlindCard] = useState<{ source: 'stackRow' | 'pairRow'; stackIndex: number; position?: 'faceDown' } | null>(null)

  // ── Game actions ─────────────────────────────────────────────────

  const activeSource = getActiveSource(gameState)

  // Safety net: if no cards left to play anywhere, the player has won
  useEffect(() => {
    if (activeSource === 'none' && gameState.drawStack.length === 0 && gameState.phase === 'playing') {
      updateState({ ...gameState, phase: 'won', message: 'You win! All cards cleared!' })
    }
  }, [activeSource, gameState, updateState])

  // Clear selection when game state changes phase or hand changes length
  const clearSelection = useCallback(() => { setSelectedHandIndices([]); setSelectedBlindCard(null) }, [])

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
      if (selectedHandIndices.length > 0) {
        const firstRank = gameState.hand[selectedHandIndices[0]].rank
        const allSameRank = selectedHandIndices.every(i => gameState.hand[i].rank === firstRank)

        if (allSameRank && clickedCard.rank === firstRank) {
          // Adding another card of the same rank — extend same-rank group
          setSelectedHandIndices(prev => [...prev, index])
        } else {
          // Check if adding this card forms a valid consecutive run
          const newIndices = [...selectedHandIndices, index]
          if (isConsecutiveRun(gameState.hand, newIndices)) {
            setSelectedHandIndices(newIndices)
          } else {
            // Can't form a group or run — start a new selection
            setSelectedHandIndices([index])
          }
        }
      } else {
        setSelectedHandIndices([index])
      }
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
    // Face-down: select for confirmation instead of immediate play
    if (position === 'faceDown') {
      setSelectedBlindCard(prev =>
        prev?.source === 'pairRow' && prev.stackIndex === stackIndex ? null : { source: 'pairRow', stackIndex, position: 'faceDown' }
      )
      return
    }
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
    // Select for confirmation instead of immediate play
    setSelectedBlindCard(prev =>
      prev?.source === 'stackRow' && prev.stackIndex === stackIndex ? null : { source: 'stackRow', stackIndex }
    )
  }, [gameState, activeSource])

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

  const handlePlayBlindCard = useCallback(() => {
    if (!selectedBlindCard) return
    if (selectedBlindCard.source === 'stackRow') {
      const result = playFromStackRow(gameState, selectedBlindCard.stackIndex)
      if (result !== gameState) sfx.play('flip')
      updateState(result)
    } else if (selectedBlindCard.source === 'pairRow') {
      const result = playFromPairRow(gameState, selectedBlindCard.stackIndex, 'faceDown')
      if (result !== gameState) sfx.play('flip')
      updateState(result)
    }
    setSelectedBlindCard(null)
  }, [selectedBlindCard, gameState, updateState, sfx])

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
    if (rank === 2) return { label: 'Wildcard', desc: 'Choose any value (A or 3–K). Choosing 7 triggers Selector, 10 triggers Destroyer.', color: 'text-cyan-400' }
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
        {pairRow.map((pair, i) => {
          const isPairBlindSelected = selectedBlindCard?.source === 'pairRow' && selectedBlindCard.stackIndex === i
          return (
          <div key={i} className="relative" style={{ width: '4.5rem', height: '5.5rem' }}>
            {pair.faceDown ? (
              <div
                className={`${CARD_SIZE_COMPACT} absolute top-0 left-0 group ${isClickable('pairRow') && pair.faceUp === null ? 'cursor-pointer' : ''} ${
                  isPairBlindSelected && pair.faceUp === null ? 'ring-2 ring-yellow-400 rounded-md -translate-y-1' : ''
                }`}
                onClick={() => pair.faceUp === null && handlePairClick(i, 'faceDown')}
              >
                <CardBack />
                {isClickable('pairRow') && pair.faceUp === null && !isPairBlindSelected && (
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
          )
        })}
      </div>

      {/* Row 3: face-down stacks */}
      <div className={`w-full flex justify-center ${gapStack}`}>
        {stackRow.map((stack, si) => {
          const isBlindSelected = selectedBlindCard?.source === 'stackRow' && selectedBlindCard.stackIndex === si
          return (
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
                    <div key={ci} className={`${CARD_SIZE_COMPACT} absolute ${isTop && isBlindSelected ? 'ring-2 ring-yellow-400 rounded-md -translate-y-1' : ''}`}
                      style={{ top: `${ci * 2}px`, left: `${ci * 1}px`, zIndex: ci }}>
                      <CardBack />
                      {isTop && isClickable('stackRow') && !isBlindSelected && (
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
          )
        })}
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
                className={`${CARD_SIZE_COMPACT} absolute group ${
                  isHandActive ? 'cursor-pointer rounded-md transition-all' : ''
                } ${isSelected ? 'ring-2 ring-yellow-400 -translate-y-2 rounded-md' : ''}`}
                style={{ left: leftCalc, top: '0.5rem', zIndex: isSelected ? 50 : i }}
                onClick={() => handleHandClick(i)}
                onDoubleClick={() => handleHandDoubleClick(i)}
              >
                <CardFace card={card} />
                {isHandActive && !isSelected && (
                  <div className="absolute inset-0 rounded-md ring-0 group-hover:ring-2 group-hover:ring-yellow-400 pointer-events-none z-10" />
                )}
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
              Play {(() => {
                const allSame = selectedHandIndices.every(i => gameState.hand[i].rank === gameState.hand[selectedHandIndices[0]].rank)
                if (allSame) {
                  return selectedHandIndices.length > 1
                    ? `${selectedHandIndices.length} × ${getRankDisplay(gameState.hand[selectedHandIndices[0]].rank)}`
                    : getRankDisplay(gameState.hand[selectedHandIndices[0]].rank)
                }
                // Consecutive run — show range
                const ranks = selectedHandIndices.map(i => gameState.hand[i].rank).sort((a, b) => a - b)
                return `Run ${getRankDisplay(ranks[0])}–${getRankDisplay(ranks[ranks.length - 1])}`
              })()}
            </button>
            <button
              onClick={clearSelection}
              className="px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
            >
              Cancel
            </button>
          </div>
        )}
        {/* Play blind card confirmation */}
        {selectedBlindCard && gameState.phase === 'playing' && (
          <div className="flex gap-2 mt-2">
            <button
              onClick={handlePlayBlindCard}
              className="px-4 py-1.5 text-xs rounded bg-amber-700 text-amber-100 hover:bg-amber-600 transition-colors"
            >
              Flip &amp; Play
            </button>
            <button
              onClick={() => setSelectedBlindCard(null)}
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

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <GameLayout
      title="Shalas"
      controls={controls}
      subtitle={<span className="text-[0.5rem] text-slate-600">&copy; 2026 David Damir Greene</span>}
    >
      <div className="flex flex-col items-center w-full">
      {/* Wild value chooser */}
      {gameState.phase === 'choose_wild' && (
        <div className="flex flex-wrap justify-center gap-1.5 mb-3 px-2">
          {WILD_CHOICES.map(rank => {
            const isSelector = rank === 7
            const isDestroyer = rank === 10
            const special = isSelector || isDestroyer
            return (
              <button
                key={rank}
                onClick={() => handleWildChoice(rank)}
                className={`px-2 py-1 text-xs rounded transition-colors min-w-[2rem] ${
                  isSelector ? 'bg-emerald-700 text-emerald-100 hover:bg-emerald-600 ring-1 ring-emerald-400/50'
                    : isDestroyer ? 'bg-red-700 text-red-100 hover:bg-red-600 ring-1 ring-red-400/50'
                    : 'bg-cyan-700 text-cyan-100 hover:bg-cyan-600'
                }`}
                title={isSelector ? 'Also triggers Selector!' : isDestroyer ? 'Also triggers Destroyer!' : undefined}
              >
                {getRankDisplay(rank)}{special ? '*' : ''}
              </button>
            )
          })}
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
        <div className="flex flex-col items-center pt-2 gap-4">
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

      {/* Status message */}
      <div className="text-center mt-3 px-2">
        <span className="text-xs text-slate-300 break-words">{gameState.message}</span>
        {gameState.effectiveRank > 0 && gameState.phase !== 'choose_wild' && (
          <span className="text-[0.65rem] sm:text-xs text-amber-400 ml-1">
            (min: {rankName(gameState.effectiveRank)})
          </span>
        )}
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

      {/* Help modal */}
      {showHelp && <ShalasHelp onClose={() => setShowHelp(false)} />}
      </div>
    </GameLayout>
  )
}

// ── Default export with multiplayer wrapper ──────────────────────────

export default function Shalas() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'shalas',
        gameName: 'Shalas',
        modes: ['vs'],
        maxPlayers: 2,
      }}
      renderSinglePlayer={() => <ShalasSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames) => (
        <ShalasMultiplayer
          roomId={roomId}
          players={players}
          playerNames={playerNames}
        />
      )}
    />
  )
}
