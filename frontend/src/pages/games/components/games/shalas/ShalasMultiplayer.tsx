/**
 * Shalas Multiplayer — 2-player VS mode.
 *
 * Host-authoritative: host runs the engine, broadcasts state.
 * Both players see the same board but only their own hand.
 * Player 2 gets an extra hand dealt from the draw stack.
 */

import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { HelpCircle, X, ArrowLeft } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE_COMPACT } from '../../PlayingCard'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { getRankDisplay } from '../../../utils/cardUtils'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
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
  applyAsPlayer,
} from './shalasEngine'
import type { ShalasState } from './shalasEngine'

// ── Wild value choices ───────────────────────────────────────────────

const WILD_CHOICES = [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]

// ── Help modal (reused from Shalas.tsx) ─────────────────────────────

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
        <h2 className="text-lg font-bold text-white mb-3">Shalas — Multiplayer</h2>
        <div className="text-xs text-slate-400 space-y-2">
          <p>Both players share the same board and take turns playing cards.</p>
          <p>Each player has their own hand — you cannot see your opponent&apos;s cards.</p>
          <p>When your hand drops below 3 cards, it auto-refills to 5 from the shared draw stack.</p>
          <p>The <span className="text-emerald-400 font-medium">7 (Selector)</span> penalty in multiplayer: your opponent takes 10 cards from the discard pile (unless they block with a 3).</p>
          <p>If you can&apos;t play, your turn is skipped.</p>
          <p>First player to clear all their cards wins!</p>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-700 text-center">
          <button onClick={onClose} className="px-6 py-2 text-sm rounded-lg bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors">
            Got it!
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Props ────────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

// ── Component ────────────────────────────────────────────────────────

export function ShalasMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()

  // Music & SFX
  const song = useMemo(() => getSongForGame('shalas'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('shalas')

  // Help modal
  const [showHelp, setShowHelp] = useState(false)

  // Player assignment: host = players[0] = player 0, guest = player 1
  const isHost = players[0] === user?.id
  const myPlayerIndex = isHost ? 0 : 1
  const opponentPlayerIndex = isHost ? 1 : 0
  const myName = playerNames[user?.id ?? 0] ?? 'You'
  const opponentName = playerNames[players[opponentPlayerIndex]] ?? 'Opponent'

  // Game state (host-authoritative — host holds canonical state)
  const [gameState, setGameState] = useState<ShalasState | null>(null)
  const gameStateRef = useRef<ShalasState | null>(null)

  // Keep ref in sync
  useEffect(() => { gameStateRef.current = gameState }, [gameState])

  // Hand selection state
  const [selectedHandIndices, setSelectedHandIndices] = useState<number[]>([])
  const [selectedBlindCard, setSelectedBlindCard] = useState<{
    source: 'stackRow' | 'pairRow'; stackIndex: number; position?: 'faceDown'
  } | null>(null)

  // ── Derived state ──────────────────────────────────────────────────

  const myHand = gameState
    ? (myPlayerIndex === 0 ? gameState.hand : gameState.opponentHand)
    : []
  const opponentHandCount = gameState
    ? (myPlayerIndex === 0 ? gameState.opponentHand.length : gameState.hand.length)
    : 0
  const isMyTurn = gameState?.currentPlayer === myPlayerIndex
  const activeSource = gameState ? getActiveSource(
    myPlayerIndex === 0 ? gameState : { ...gameState, hand: gameState.opponentHand, opponentHand: gameState.hand }
  ) : 'none'

  // ── Host: create game on mount ─────────────────────────────────────

  useEffect(() => {
    if (!isHost) return
    const state = createShalasGame(2)
    setGameState(state)
    // Broadcast initial state to guest
    gameSocket.sendAction(roomId, { type: 'shalas_sync', state })
  }, [isHost, roomId])

  // ── Broadcast state (host only) ───────────────────────────────────

  const broadcastState = useCallback((state: ShalasState) => {
    gameSocket.sendAction(roomId, { type: 'shalas_sync', state })
  }, [roomId])

  // ── Apply action (host processes, then broadcasts) ─────────────────

  const applyAction = useCallback((
    actionFn: (s: ShalasState) => ShalasState,
    playerIndex: number,
  ) => {
    const current = gameStateRef.current
    if (!current) return
    const result = applyAsPlayer(current, playerIndex, actionFn)
    setGameState(result)
    broadcastState(result)
  }, [broadcastState])

  // ── Send action to host (guest) or apply directly (host) ──────────

  const doAction = useCallback((action: Record<string, unknown>) => {
    if (isHost) {
      // Host applies directly
      handleIncomingAction(action, myPlayerIndex)
    } else {
      // Guest sends to host
      gameSocket.sendAction(roomId, action)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isHost, roomId, myPlayerIndex])

  // ── Handle incoming actions ────────────────────────────────────────

  const handleIncomingAction = useCallback((action: Record<string, unknown>, fromPlayer: number) => {
    const current = gameStateRef.current
    if (!current) return

    switch (action.type) {
      case 'shalas_play_hand': {
        const indices = action.indices as number[]
        applyAction(s => playFromHand(s, indices), fromPlayer)
        break
      }
      case 'shalas_play_pair': {
        const stackIndex = action.stackIndex as number
        const position = action.position as 'faceUp' | 'faceDown'
        applyAction(s => playFromPairRow(s, stackIndex, position), fromPlayer)
        break
      }
      case 'shalas_play_stack': {
        const stackIndex = action.stackIndex as number
        applyAction(s => playFromStackRow(s, stackIndex), fromPlayer)
        break
      }
      case 'shalas_play_second': {
        const index = action.index as number
        applyAction(s => playFromSecondRow(s, index), fromPlayer)
        break
      }
      case 'shalas_draw': {
        applyAction(s => drawOneCard(s), fromPlayer)
        break
      }
      case 'shalas_wild': {
        const rank = action.rank as number
        applyAction(s => chooseWildValue(s, rank), fromPlayer)
        break
      }
      case 'shalas_selector': {
        const source = action.source as { type: string; index?: number; stackIndex?: number; card?: string }
        applyAction(s => chooseSelectorTarget(s, source as any), fromPlayer)
        break
      }
      case 'shalas_cant_play': {
        applyAction(s => cantPlay(s), fromPlayer)
        break
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applyAction])

  // ── WebSocket listener ─────────────────────────────────────────────

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: any) => {
      if (msg.roomId !== roomId) return

      const action = msg.action
      if (!action) return

      // State sync from host → guest
      if (action.type === 'shalas_sync' && !isHost) {
        setGameState(action.state)
        return
      }

      // Guest action → host processes it
      if (isHost && action.type?.startsWith('shalas_') && action.type !== 'shalas_sync') {
        // Determine which player sent this
        const fromPlayer = msg.playerId === players[0] ? 0 : 1
        handleIncomingAction(action, fromPlayer)
      }
    })
    return unsub
  }, [roomId, isHost, players, handleIncomingAction])

  // ── Game over detection ────────────────────────────────────────────

  const gameOver = gameState?.phase === 'won'
  // checkWin runs BEFORE turn switch, so currentPlayer = the player who just cleared their cards
  const iWon = gameOver && gameState?.currentPlayer === myPlayerIndex

  // ── Selection & action handlers ────────────────────────────────────

  const clearSelection = useCallback(() => {
    setSelectedHandIndices([])
    setSelectedBlindCard(null)
  }, [])

  const handleHandClick = useCallback((index: number) => {
    if (!gameState || !isMyTurn) return

    if (gameState.phase === 'choose_selector') {
      sfx.play('place')
      doAction({ type: 'shalas_selector', source: { type: 'hand', index } })
      clearSelection()
      return
    }
    if (gameState.phase !== 'playing' || activeSource !== 'hand') return

    const clickedCard = myHand[index]

    if (selectedHandIndices.includes(index)) {
      setSelectedHandIndices(prev => prev.filter(i => i !== index))
    } else {
      if (selectedHandIndices.length > 0) {
        const firstRank = myHand[selectedHandIndices[0]].rank
        const allSameRank = selectedHandIndices.every(i => myHand[i].rank === firstRank)

        if (allSameRank && clickedCard.rank === firstRank) {
          setSelectedHandIndices(prev => [...prev, index])
        } else {
          const newIndices = [...selectedHandIndices, index]
          if (isConsecutiveRun(myHand, newIndices)) {
            setSelectedHandIndices(newIndices)
          } else {
            setSelectedHandIndices([index])
          }
        }
      } else {
        setSelectedHandIndices([index])
      }
    }
  }, [gameState, isMyTurn, activeSource, myHand, selectedHandIndices, sfx, doAction, clearSelection])

  const handleHandDoubleClick = useCallback((index: number) => {
    if (!gameState || !isMyTurn) return
    if (gameState.phase !== 'playing' || activeSource !== 'hand') return
    sfx.play('place')
    doAction({ type: 'shalas_play_hand', indices: [index] })
    clearSelection()
  }, [gameState, isMyTurn, activeSource, sfx, doAction, clearSelection])

  const handlePlaySelected = useCallback(() => {
    if (selectedHandIndices.length === 0 || !isMyTurn) return
    sfx.play(selectedHandIndices.length >= 4 ? 'win' : 'place')
    doAction({ type: 'shalas_play_hand', indices: selectedHandIndices })
    clearSelection()
  }, [selectedHandIndices, isMyTurn, sfx, doAction, clearSelection])

  const handlePairClick = useCallback((stackIndex: number, position: 'faceUp' | 'faceDown') => {
    if (!gameState || !isMyTurn) return

    if (gameState.phase === 'choose_selector') {
      sfx.play('place')
      doAction({ type: 'shalas_selector', source: { type: 'pairRow', stackIndex, card: position } })
      return
    }
    if (gameState.phase !== 'playing' || activeSource !== 'pairRow') return
    if (position === 'faceDown') {
      setSelectedBlindCard(prev =>
        prev?.source === 'pairRow' && prev.stackIndex === stackIndex
          ? null : { source: 'pairRow', stackIndex, position: 'faceDown' }
      )
      return
    }
    sfx.play('place')
    doAction({ type: 'shalas_play_pair', stackIndex, position })
  }, [gameState, isMyTurn, activeSource, sfx, doAction])

  const handleStackClick = useCallback((stackIndex: number) => {
    if (!gameState || !isMyTurn) return

    if (gameState.phase === 'choose_selector') {
      sfx.play('place')
      doAction({ type: 'shalas_selector', source: { type: 'stackRow', stackIndex } })
      return
    }
    if (gameState.phase !== 'playing' || activeSource !== 'stackRow') return
    setSelectedBlindCard(prev =>
      prev?.source === 'stackRow' && prev.stackIndex === stackIndex
        ? null : { source: 'stackRow', stackIndex }
    )
  }, [gameState, isMyTurn, activeSource, sfx, doAction])

  const handleSecondRowClick = useCallback((index: number) => {
    if (!gameState || !isMyTurn) return

    if (gameState.phase === 'choose_selector') {
      sfx.play('place')
      doAction({ type: 'shalas_selector', source: { type: 'secondRow', index } })
      return
    }
    if (gameState.phase !== 'playing' || activeSource !== 'secondRow') return
    sfx.play('place')
    doAction({ type: 'shalas_play_second', index })
  }, [gameState, isMyTurn, activeSource, sfx, doAction])

  const handlePlayBlindCard = useCallback(() => {
    if (!selectedBlindCard || !isMyTurn) return
    sfx.play('flip')
    if (selectedBlindCard.source === 'stackRow') {
      doAction({ type: 'shalas_play_stack', stackIndex: selectedBlindCard.stackIndex })
    } else {
      doAction({ type: 'shalas_play_pair', stackIndex: selectedBlindCard.stackIndex, position: 'faceDown' })
    }
    setSelectedBlindCard(null)
  }, [selectedBlindCard, isMyTurn, sfx, doAction])

  const handleWildChoice = useCallback((rank: number) => {
    if (!isMyTurn) return
    sfx.play('place')
    doAction({ type: 'shalas_wild', rank })
  }, [isMyTurn, sfx, doAction])

  const handleDrawCard = useCallback(() => {
    if (!gameState || !isMyTurn) return
    if (gameState.phase !== 'playing' || gameState.drawStack.length === 0) return
    sfx.play('flip')
    doAction({ type: 'shalas_draw' })
    clearSelection()
  }, [gameState, isMyTurn, sfx, doAction, clearSelection])

  const handleCantPlay = useCallback(() => {
    if (!isMyTurn) return
    sfx.play('flip')
    doAction({ type: 'shalas_cant_play' })
  }, [isMyTurn, sfx, doAction])

  // Clear selection on turn change
  useEffect(() => { clearSelection() }, [gameState?.currentPlayer, clearSelection])

  // ── Derived rendering state ────────────────────────────────────────

  if (!gameState) {
    return (
      <div className="flex items-center justify-center py-12">
        <span className="text-slate-400 text-sm">Waiting for game to start...</span>
      </div>
    )
  }

  const { secondRow, stackRow, pairRow, drawStack, discardPile } = gameState

  const canPlayerPlay = isMyTurn && gameState.phase === 'playing' && hasValidPlay(
    myPlayerIndex === 0 ? gameState : { ...gameState, hand: gameState.opponentHand, opponentHand: gameState.hand }
  )

  const canDraw = isMyTurn && gameState.phase === 'playing' && drawStack.length > 0

  const selectedSpecialInfo = (() => {
    if (selectedHandIndices.length === 0 || activeSource !== 'hand') return null
    const rank = myHand[selectedHandIndices[0]]?.rank
    if (!rank) return null
    if (selectedHandIndices.length >= 4) {
      return { label: '4-of-a-Kind', desc: 'Resets discard. All 4 stay on pile.', color: 'text-purple-400' }
    }
    if (rank === 10) return { label: 'Destroyer', desc: 'Removes discard pile from game.', color: 'text-red-400' }
    if (rank === 2) return { label: 'Wildcard', desc: 'Choose any value.', color: 'text-cyan-400' }
    if (rank === 7) return { label: 'Selector', desc: 'Pick a table card. Opponent takes 10.', color: 'text-emerald-400' }
    if (rank === 1) return { label: 'Ace', desc: 'Highest & lowest.', color: 'text-amber-400' }
    return null
  })()

  const isClickable = (source: string) =>
    isMyTurn && (gameState.phase === 'choose_selector' || activeSource === source)

  // ── Sub-renderers ──────────────────────────────────────────────────

  const renderOpponentHand = () => (
    <div className="w-full flex flex-col items-center mb-2">
      <span className="text-[0.6rem] text-slate-500 uppercase tracking-widest mb-1">
        {opponentName}&apos;s Hand ({opponentHandCount} cards)
      </span>
      <div className="flex gap-0.5 justify-center">
        {Array.from({ length: Math.min(opponentHandCount, 12) }).map((_, i) => (
          <div key={i} className="w-5 h-7">
            <CardBack />
          </div>
        ))}
        {opponentHandCount > 12 && (
          <span className="text-[0.5rem] text-slate-500 self-center ml-1">+{opponentHandCount - 12}</span>
        )}
      </div>
    </div>
  )

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

      {/* My hand */}
      <div className="w-full flex flex-col items-center">
        <span className="text-[0.6rem] text-slate-400 uppercase tracking-widest mb-1">
          {myName}&apos;s Hand
        </span>
        <div className="relative py-2 rounded-lg border border-emerald-700/40 bg-emerald-900/20 shadow-inner w-full"
          style={{ height: '6rem' }}
        >
          {myHand.length > 0 ? myHand.map((card, i) => {
            const isSelected = selectedHandIndices.includes(i)
            const isHandActive = isMyTurn && (activeSource === 'hand' || gameState.phase === 'choose_selector')
            const pct = myHand.length === 1 ? 50 : (i / (myHand.length - 1)) * 100
            const leftCalc = myHand.length === 1
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
            <span className="absolute inset-0 flex items-center justify-center text-[0.6rem] text-slate-600">
              Hand empty — play from table
            </span>
          )}
        </div>

        {/* Play selected */}
        {selectedHandIndices.length > 0 && activeSource === 'hand' && isMyTurn && gameState.phase === 'playing' && (
          <div className="flex gap-2 mt-2">
            <button
              onClick={handlePlaySelected}
              className="px-4 py-1.5 text-xs rounded bg-emerald-700 text-emerald-100 hover:bg-emerald-600 transition-colors"
            >
              Play {(() => {
                const allSame = selectedHandIndices.every(i => myHand[i].rank === myHand[selectedHandIndices[0]].rank)
                if (allSame) {
                  return selectedHandIndices.length > 1
                    ? `${selectedHandIndices.length} × ${getRankDisplay(myHand[selectedHandIndices[0]].rank)}`
                    : getRankDisplay(myHand[selectedHandIndices[0]].rank)
                }
                const ranks = selectedHandIndices.map(i => myHand[i].rank).sort((a, b) => a - b)
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

        {/* Blind card confirmation */}
        {selectedBlindCard && isMyTurn && gameState.phase === 'playing' && (
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

  // ── Turn indicator ─────────────────────────────────────────────────

  const turnIndicator = (
    <div className={`text-center py-1.5 px-4 rounded-lg text-xs font-medium ${
      isMyTurn
        ? 'bg-emerald-900/40 border border-emerald-700/50 text-emerald-300'
        : 'bg-amber-900/40 border border-amber-700/50 text-amber-300'
    }`}>
      {gameState.phase === 'choose_wild'
        ? (isMyTurn ? 'Choose the reset value' : `${opponentName} is choosing a value...`)
        : gameState.phase === 'choose_selector'
        ? (isMyTurn ? 'Pick a table card to discard' : `${opponentName} is picking a card...`)
        : gameState.phase === 'block_chance'
        ? (isMyTurn ? 'Opponent can block with a 3...' : 'You can play a 3 to block!')
        : isMyTurn ? 'Your turn' : `${opponentName}'s turn`
      }
    </div>
  )

  // ── Controls ───────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        {onLeave && (
          <button
            onClick={onLeave}
            className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
          >
            <ArrowLeft className="w-3 h-3" /> Leave
          </button>
        )}
        {isMyTurn && gameState.phase === 'playing' && !canPlayerPlay && (
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
        {/* Turn indicator */}
        {!gameOver && turnIndicator}

        {/* Opponent hand (face-down count) */}
        <div className="mt-2">
          {renderOpponentHand()}
        </div>

        {/* Wild value chooser */}
        {isMyTurn && gameState.phase === 'choose_wild' && (
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
                >
                  {getRankDisplay(rank)}{special ? '*' : ''}
                </button>
              )
            })}
          </div>
        )}

        {/* Selector prompt */}
        {isMyTurn && gameState.phase === 'choose_selector' && (
          <div className="text-center mb-3">
            <span className="text-xs text-cyan-400">Click any card on the table to move it to discard</span>
          </div>
        )}

        {/* Special info tooltip */}
        {selectedSpecialInfo && (
          <div className="mb-2 px-2 py-1.5 rounded border border-slate-700 bg-slate-800/60 max-w-[12rem] text-center">
            <div className={`text-[0.6rem] font-bold ${selectedSpecialInfo.color}`}>{selectedSpecialInfo.label}</div>
            <div className="text-[0.5rem] text-slate-400 leading-tight mt-0.5">{selectedSpecialInfo.desc}</div>
          </div>
        )}

        {/* Mobile layout */}
        <div className="flex sm:hidden w-full gap-3">
          <div className="flex flex-col items-center gap-6 pt-2">
            {renderDrawStack()}
            {renderDiscardPile()}
          </div>
          <div className="flex-1 flex flex-col items-center space-y-4">
            {renderTable('gap-4', 'gap-3')}
          </div>
        </div>

        {/* Desktop layout */}
        <div className="hidden sm:flex w-full max-w-2xl gap-4">
          <div className="flex flex-col items-center pt-2 gap-4">
            {renderDrawStack()}
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

        {/* Game over */}
        {gameOver && (
          <GameOverModal
            status={iWon ? 'won' : 'lost'}
            message={iWon ? 'You cleared all your cards!' : `${opponentName} cleared all their cards!`}
            onPlayAgain={onLeave ?? (() => {})}
            playAgainText="Return to Lobby"
            music={music}
            sfx={sfx}
          />
        )}

        {showHelp && <ShalasHelp onClose={() => setShowHelp(false)} />}
      </div>
    </GameLayout>
  )
}
