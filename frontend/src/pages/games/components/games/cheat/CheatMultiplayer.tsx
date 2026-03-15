/**
 * Cheat (BS) VS — 2-4 human players over WebSocket.
 *
 * Host-authoritative: host runs the engine, broadcasts state.
 * Each player sees only their own hand face-up.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi, ArrowLeft } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SIZE_MINI } from '../../PlayingCard'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
import { getRankDisplay, type Card } from '../../../utils/cardUtils'
import {
  createCheatGame,
  playCards,
  callBS,
  passChallenge,
  resolveChallenge,
  type CheatState,
} from './cheatEngine'

// ── Types ────────────────────────────────────────────────────────────

interface GuestView {
  myHand: Card[]
  handCounts: number[]
  pile: number
  phase: CheatState['phase']
  currentPlayer: number
  requiredRank: number
  lastPlay: {
    player: number
    claimedRank: number
    claimedCount: number
  } | null
  revealCards: Card[] | null
  challengeResult: 'honest' | 'bluff' | null
  challengedBy: number | null
  passedPlayers: number[]
  winner: number | null
  playerCount: number
  myIndex: number
}

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

// ── Component ────────────────────────────────────────────────────────

export function CheatMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()

  const song = useMemo(() => getSongForGame('cheat'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('cheat')

  const isHost = players[0] === user?.id
  const myPlayerIndex = players.indexOf(user?.id ?? -1)
  const playerCount = players.length

  const [gameState, setGameState] = useState<CheatState | null>(null)
  const gameStateRef = useRef<CheatState | null>(null)
  useEffect(() => { gameStateRef.current = gameState }, [gameState])

  const [guestView, setGuestView] = useState<GuestView | null>(null)
  const [selectedCards, setSelectedCards] = useState<number[]>([])


  // ── Build guest view ──────────────────────────────────────────

  const buildGuestView = useCallback((state: CheatState, forIndex: number): GuestView => {
    return {
      myHand: state.hands[forIndex],
      handCounts: state.hands.map(h => h.length),
      pile: state.pile.length,
      phase: state.phase,
      currentPlayer: state.currentPlayer,
      requiredRank: state.requiredRank,
      lastPlay: state.lastPlay ? {
        player: state.lastPlay.player,
        claimedRank: state.lastPlay.claimedRank,
        claimedCount: state.lastPlay.claimedCount,
      } : null,
      revealCards: state.phase === 'reveal' && state.lastPlay ? state.lastPlay.cards : null,
      challengeResult: state.challengeResult,
      challengedBy: state.challengedBy,
      passedPlayers: state.passedPlayers,
      winner: state.winner,
      playerCount: state.playerCount,
      myIndex: forIndex,
    }
  }, [])

  // ── Host: create game ────────────────────────────────────────

  useEffect(() => {
    if (!isHost) return
    const state = createCheatGame(playerCount)
    setGameState(state)
    // Broadcast to each guest
    for (let i = 1; i < playerCount; i++) {
      gameSocket.sendAction(roomId, {
        type: 'cheat_sync',
        targetPlayer: players[i],
        view: buildGuestView(state, i),
      })
    }
  }, [isHost, roomId, playerCount, players, buildGuestView])

  const broadcastAndSet = useCallback((state: CheatState) => {
    setGameState(state)
    for (let i = 1; i < playerCount; i++) {
      gameSocket.sendAction(roomId, {
        type: 'cheat_sync',
        targetPlayer: players[i],
        view: buildGuestView(state, i),
      })
    }
  }, [roomId, playerCount, players, buildGuestView])

  // ── Resolve reveal after delay (host only) ───────────────────

  useEffect(() => {
    if (!isHost || !gameState || gameState.phase !== 'reveal') return
    const timer = setTimeout(() => {
      setGameState(prev => {
        if (!prev || prev.phase !== 'reveal') return prev
        const resolved = resolveChallenge(prev)
        // Broadcast resolved state
        for (let i = 1; i < playerCount; i++) {
          gameSocket.sendAction(roomId, {
            type: 'cheat_sync',
            targetPlayer: players[i],
            view: buildGuestView(resolved, i),
          })
        }
        return resolved
      })
    }, 2500)
    return () => clearTimeout(timer)
  }, [isHost, gameState?.phase, roomId, playerCount, players, buildGuestView])

  // ── Process actions (host) ───────────────────────────────────

  const processAction = useCallback((action: Record<string, unknown>, fromIndex: number) => {
    const current = gameStateRef.current
    if (!current) return

    switch (action.type) {
      case 'cheat_play': {
        if (current.phase !== 'play' || current.currentPlayer !== fromIndex) return
        const indices = action.indices as number[]
        if (!Array.isArray(indices) || indices.length === 0 || indices.length > 4) return
        const result = playCards(current, indices, current.requiredRank)
        if (result !== current) broadcastAndSet(result)
        break
      }
      case 'cheat_bs': {
        if (current.phase !== 'challenge') return
        if (!current.lastPlay || current.lastPlay.player === fromIndex) return
        const result = callBS(current, fromIndex)
        if (result !== current) broadcastAndSet(result)
        break
      }
      case 'cheat_pass': {
        if (current.phase !== 'challenge') return
        const result = passChallenge(current, fromIndex)
        if (result !== current) broadcastAndSet(result)
        break
      }
    }
  }, [broadcastAndSet])

  // ── Send action ──────────────────────────────────────────────

  const sendAction = useCallback((action: Record<string, unknown>) => {
    music.init()
    sfx.init()
    music.start()

    if (isHost) {
      processAction(action, myPlayerIndex)
    } else {
      gameSocket.sendAction(roomId, action)
    }
  }, [isHost, roomId, myPlayerIndex, processAction, music, sfx])

  // ── WebSocket listener ───────────────────────────────────────

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: any) => {
      if (msg.roomId !== roomId) return
      const action = msg.action
      if (!action) return

      if (action.type === 'cheat_sync' && !isHost) {
        if (action.targetPlayer === user?.id) {
          setGuestView(action.view)
        }
        return
      }

      if (isHost && action.type?.startsWith('cheat_') && action.type !== 'cheat_sync') {
        const fromIndex = players.indexOf(msg.playerId)
        if (fromIndex >= 0) processAction(action, fromIndex)
      }
    })
    return unsub
  }, [roomId, isHost, players, processAction, user?.id])

  // ── Derive view ──────────────────────────────────────────────

  const view: GuestView | null = isHost && gameState
    ? buildGuestView(gameState, 0)
    : guestView

  if (!view) {
    return (
      <div className="flex items-center justify-center py-12">
        <span className="text-slate-400 text-sm">Waiting for game to start...</span>
      </div>
    )
  }

  // Reveal cards effect for guest view
  const showReveal = view.phase === 'reveal' && view.revealCards

  const isMyTurn = view.phase === 'play' && view.currentPlayer === view.myIndex
  const canChallenge = view.phase === 'challenge' &&
    view.lastPlay !== null &&
    view.lastPlay.player !== view.myIndex &&
    !view.passedPlayers.includes(view.myIndex)

  const getName = (idx: number) => {
    if (idx === view.myIndex) return 'You'
    const playerId = players[idx]
    return playerNames[playerId] ?? `Player ${idx + 1}`
  }

  const gameOver = view.phase === 'gameOver'
  const iWon = gameOver && view.winner === view.myIndex

  // ── Status message ───────────────────────────────────────────

  let statusMsg = ''
  if (gameOver) {
    statusMsg = view.winner === view.myIndex ? 'You win!' : `${getName(view.winner!)} wins!`
  } else if (view.phase === 'reveal' && view.lastPlay && view.challengedBy !== null) {
    const challenger = getName(view.challengedBy)
    const player = getName(view.lastPlay.player)
    statusMsg = view.challengeResult === 'bluff'
      ? `${challenger} called BS! ${player} was bluffing!`
      : `${challenger} called BS! ${player} was honest!`
  } else if (view.phase === 'challenge' && view.lastPlay) {
    statusMsg = `${getName(view.lastPlay.player)} played ${view.lastPlay.claimedCount} ${getRankDisplay(view.lastPlay.claimedRank)}(s)`
  } else if (view.phase === 'play') {
    statusMsg = isMyTurn
      ? `Your turn — play cards as ${getRankDisplay(view.requiredRank)}s`
      : `${getName(view.currentPlayer)}'s turn`
  }

  // ── Handlers ─────────────────────────────────────────────────

  const toggleCard = (index: number) => {
    setSelectedCards(prev => {
      if (prev.includes(index)) return prev.filter(i => i !== index)
      if (prev.length >= 4) return prev
      return [...prev, index]
    })
  }

  const handlePlay = () => {
    if (selectedCards.length === 0) return
    sfx.play('play')
    sendAction({ type: 'cheat_play', indices: selectedCards })
    setSelectedCards([])
  }

  const handleCallBS = () => {
    sfx.play('play')
    sendAction({ type: 'cheat_bs' })
  }

  const handlePass = () => {
    sendAction({ type: 'cheat_pass' })
  }

  // ── Controls ─────────────────────────────────────────────────

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
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
      </div>
      <div className="flex items-center gap-3 text-xs">
        <span className="text-white">Required: {getRankDisplay(view.requiredRank)}</span>
        <span className="text-slate-400">Pile: {view.pile}</span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  // ── Render ───────────────────────────────────────────────────

  return (
    <GameLayout title="Cheat — VS" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-2xl space-y-3">
        {/* Other players */}
        <div className="flex gap-6 justify-center flex-wrap">
          {Array.from({ length: view.playerCount }).map((_, p) => {
            if (p === view.myIndex) return null
            return (
              <div key={p} className={`text-center ${view.currentPlayer === p && view.phase === 'play' ? 'ring-2 ring-blue-500 rounded-lg p-1.5' : 'p-1.5'}`}>
                <span className={`text-xs ${view.currentPlayer === p ? 'text-blue-400 font-medium' : 'text-slate-400'}`}>
                  {getName(p)} ({view.handCounts[p]})
                </span>
                <div className="flex gap-0.5 justify-center mt-1">
                  {Array.from({ length: Math.min(view.handCounts[p], 6) }).map((_, j) => (
                    <div key={j} className={CARD_SIZE_MINI}>
                      <CardBack />
                    </div>
                  ))}
                  {view.handCounts[p] > 6 && (
                    <span className="text-xs text-slate-500 self-center ml-0.5">+{view.handCounts[p] - 6}</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Pile */}
        <div className="flex gap-3 items-center justify-center">
          <div className={`${CARD_SIZE} relative`}>
            {view.pile > 0 ? (
              <div className="relative">
                <CardBack />
                <span className="absolute -bottom-1 -right-1 bg-slate-800 text-white text-xs px-1.5 py-0.5 rounded-full border border-slate-600">
                  {view.pile}
                </span>
              </div>
            ) : (
              <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                Empty
              </div>
            )}
          </div>
        </div>

        {/* Reveal cards */}
        {showReveal && view.revealCards && (
          <div className="flex gap-1 justify-center bg-slate-800/80 rounded-lg p-2 border border-yellow-500/50">
            <span className="text-xs text-yellow-400 mr-2 self-center">Revealed:</span>
            {view.revealCards.map((c, i) => (
              <div key={i} className={CARD_SIZE}>
                <CardFace card={c} />
              </div>
            ))}
          </div>
        )}

        {/* Status */}
        <p className="text-sm text-white font-medium text-center min-h-[1.5rem]">{statusMsg}</p>

        {/* Action buttons */}
        <div className="flex gap-2 justify-center min-h-[2.5rem]">
          {isMyTurn && selectedCards.length > 0 && (
            <button
              onClick={handlePlay}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Play {selectedCards.length} as {getRankDisplay(view.requiredRank)}{selectedCards.length > 1 ? 's' : ''}
            </button>
          )}
          {canChallenge && (
            <>
              <button
                onClick={handleCallBS}
                className="px-4 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                BS!
              </button>
              <button
                onClick={handlePass}
                className="px-4 py-1.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Pass
              </button>
            </>
          )}
        </div>

        {/* Player hand */}
        <div className="flex flex-wrap gap-1.5 justify-center max-w-lg">
          {view.myHand.map((card, i) => {
            const isSelected = selectedCards.includes(i)
            const isClickable = isMyTurn
            return (
              <div
                key={i}
                className={`${CARD_SIZE} transition-transform cursor-pointer ${
                  isSelected ? '-translate-y-2 ring-2 ring-emerald-400 rounded' : ''
                } ${isClickable ? 'hover:-translate-y-1' : 'opacity-70'}`}
                onClick={() => isClickable && toggleCard(i)}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {/* Game over */}
        {gameOver && (
          <GameOverModal
            status={iWon ? 'won' : 'lost'}
            score={0}
            message={statusMsg}
            onPlayAgain={onLeave ?? (() => {})}
            playAgainText="Return to Lobby"
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
