/**
 * Texas Hold'em VS Multiplayer — up to 4 humans at one table.
 *
 * Host runs the engine and broadcasts state via WebSocket.
 * Each human sees the game from their own seat perspective.
 * AI fills remaining seats; host runs AI turns automatically.
 * Friends can join mid-game to replace AI players between hands.
 * All players are labeled by display name.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SIZE_LARGE } from '../../PlayingCard'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { InGameInvite } from '../../multiplayer/InGameInvite'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
import {
  createTexasHoldemGame,
  startHand,
  fold,
  check,
  call,
  raise as raiseAction,
  allIn,
  getValidActions,
  getMinRaise,
  aiAction,
  nextHand,
  setBlinds,
  type TexasHoldemState,
} from './TexasHoldemEngine'

interface Props {
  roomId: string
  players: number[]         // user IDs in seat order (initial)
  playerNames: Record<number, string>
  onLeave?: () => void
}

// Number of seats at the table
const TABLE_SIZE = 4

export function TexasHoldemMultiplayer({ roomId, players: initialPlayers, playerNames: initialNames, onLeave }: Props) {
  const { user } = useAuth()
  const song = useMemo(() => getSongForGame('texas-holdem'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('texas-holdem')

  // Dynamic player list — grows as friends join mid-game
  const [livePlayers, setLivePlayers] = useState<number[]>(initialPlayers)
  const [liveNames, setLiveNames] = useState<Record<number, string>>(initialNames)

  // Determine seats: human players get seats 0..N-1, rest are AI
  const isHost = livePlayers[0] === user?.id
  const mySeat = livePlayers.indexOf(user?.id ?? -1)

  // Build seat → display name mapping (humans + AI)
  const seatNames = useMemo(() => {
    const names: string[] = []
    for (let i = 0; i < TABLE_SIZE; i++) {
      if (i < livePlayers.length) {
        names.push(liveNames[livePlayers[i]] || `Player ${livePlayers[i]}`)
      } else {
        names.push(`AI ${i + 1}`)
      }
    }
    return names
  }, [livePlayers, liveNames])

  // Which seats are human
  const humanSeats = useMemo(() => new Set(livePlayers.map((_, i) => i)), [livePlayers])

  // How many AI seats remain (for invite button)
  const openAiSeats = TABLE_SIZE - livePlayers.length

  // ── Game State ──
  const [gameState, setGameState] = useState<TexasHoldemState | null>(null)
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [raiseAmount, setRaiseAmount] = useState(40)
  const [actionText, setActionText] = useState<string | null>(null)
  const gameStartTime = useRef(Date.now())
  const gameStateRef = useRef<TexasHoldemState | null>(null)

  // Keep ref in sync
  useEffect(() => { gameStateRef.current = gameState }, [gameState])

  // ── Host: Initialize game ──
  useEffect(() => {
    if (!isHost) return
    const state = startHand(createTexasHoldemGame(TABLE_SIZE))
    setGameState(state)
    broadcastState(state)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Host: Blind escalation ──
  useEffect(() => {
    if (!isHost || gameStatus !== 'playing') return
    const timer = setInterval(() => {
      const elapsed = Date.now() - gameStartTime.current
      const level = Math.floor(elapsed / (10 * 60 * 1000))
      setGameState(prev => {
        if (!prev || prev.blindLevel === level) return prev
        const next = setBlinds(prev, level)
        broadcastState(next)
        return next
      })
    }, 5000)
    return () => clearInterval(timer)
  }, [isHost, gameStatus])

  // ── Host: Auto-run AI turns ──
  useEffect(() => {
    if (!isHost || !gameState) return
    const cp = gameState.currentPlayer
    if (humanSeats.has(cp)) return // human's turn
    if (gameState.phase === 'handOver' || gameState.phase === 'gameOver' || gameState.phase === 'showdown') return

    const timer = setTimeout(() => {
      setGameState(prev => {
        if (!prev) return prev
        const next = aiAction(prev)
        broadcastState(next, formatActionText(next.lastAction))
        return next
      })
    }, 1500)
    return () => clearTimeout(timer)
  }, [isHost, gameState?.currentPlayer, gameState?.phase]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Host: Detect game over ──
  useEffect(() => {
    if (!gameState || gameState.phase !== 'gameOver') return
    setGameStatus(gameState.chips[mySeat] > 0 ? 'won' : 'lost')
  }, [gameState?.phase, mySeat])

  // ── Broadcast state (host only) ──
  function broadcastState(state: TexasHoldemState, action?: string) {
    gameSocket.sendAction(roomId, {
      type: 'holdem_sync',
      state,
      actionText: action || null,
    })
  }

  // ── Format action text with display names ──
  function formatActionText(text: string): string {
    return text.replace(/Player (\d+)/g, (_, n) => seatNames[Number(n)])
  }

  // Ref for livePlayers to avoid stale closures in WS listener
  const livePlayersRef = useRef(livePlayers)
  livePlayersRef.current = livePlayers

  // ── Listen for mid-game player joins ──
  useEffect(() => {
    const unsub = gameSocket.on('game:mid_player_joined', (msg) => {
      if (msg.roomId !== roomId) return
      const newPlayerId = msg.playerId as number
      const newName = msg.playerName as string

      setLivePlayers(prev => {
        if (prev.includes(newPlayerId)) return prev
        return [...prev, newPlayerId]
      })
      setLiveNames(prev => ({ ...prev, [newPlayerId]: newName }))
    })
    return unsub
  }, [roomId])

  // ── Listen for game action WS messages ──
  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      const action = msg.action
      if (!action) return

      // State sync from host
      if (action.type === 'holdem_sync') {
        if (!isHost) {
          setGameState(action.state)
        }
        if (action.actionText) {
          setActionText(action.actionText)
          setTimeout(() => setActionText(null), 2000)
        }
        // SFX for community cards
        if (action.state.community?.length > 0) {
          sfx.play('reveal')
        }
        return
      }

      // Human player action (host processes these)
      if (action.type === 'holdem_do' && isHost) {
        const senderSeat = livePlayersRef.current.indexOf(msg.playerId)
        if (senderSeat < 0) return

        setGameState(prev => {
          if (!prev || prev.currentPlayer !== senderSeat) return prev

          let next: TexasHoldemState
          switch (action.action) {
            case 'fold': next = fold(prev); break
            case 'check': next = check(prev); break
            case 'call': next = call(prev); break
            case 'raise': next = raiseAction(prev, action.amount ?? getMinRaise(prev)); break
            case 'allIn': next = allIn(prev); break
            default: return prev
          }
          broadcastState(next, formatActionText(next.lastAction))
          return next
        })
        return
      }

      // Next hand request
      if (action.type === 'holdem_next' && isHost) {
        setGameState(prev => {
          if (!prev || prev.phase !== 'handOver') return prev
          const next = nextHand(prev)
          broadcastState(next)
          return next
        })
        return
      }
    })
    return unsub
  }, [roomId, isHost, sfx, seatNames]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Player actions (local or sent via WS) ──
  const sendAction = useCallback((actionName: string, amount?: number) => {
    music.init(); sfx.init(); music.start()

    if (isHost) {
      // Host applies directly
      setGameState(prev => {
        if (!prev) return prev
        let next: TexasHoldemState
        switch (actionName) {
          case 'fold': sfx.play('fold'); next = fold(prev); break
          case 'check': next = check(prev); break
          case 'call': sfx.play('bet'); next = call(prev); break
          case 'raise': sfx.play('bet'); next = raiseAction(prev, amount ?? getMinRaise(prev)); break
          case 'allIn': next = allIn(prev); break
          default: return prev
        }
        broadcastState(next, formatActionText(next.lastAction))
        return next
      })
    } else {
      // Guest sends action to host
      if (actionName === 'fold') sfx.play('fold')
      else if (actionName === 'call' || actionName === 'raise') sfx.play('bet')
      gameSocket.sendAction(roomId, {
        type: 'holdem_do',
        action: actionName,
        amount,
      })
    }
  }, [isHost, roomId, music, sfx]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleNextHand = useCallback(() => {
    sfx.play('deal')
    if (isHost) {
      setGameState(prev => {
        if (!prev) return prev
        const next = nextHand(prev)
        broadcastState(next)
        return next
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'holdem_next' })
    }
  }, [isHost, roomId, sfx]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Update raise slider ──
  useEffect(() => {
    if (!gameState) return
    const min = getMinRaise(gameState)
    setRaiseAmount(Math.min(min, gameState.chips[mySeat] + gameState.bets[mySeat]))
  }, [gameState?.phase, gameState?.currentBet, mySeat])

  // ── Render ──
  if (!gameState) {
    return (
      <GameLayout title="Texas Hold'em — VS" controls={<span />}>
        <p className="text-sm text-slate-400 text-center py-8">Waiting for host to deal...</p>
      </GameLayout>
    )
  }

  // Compute derived values
  const isMyTurn = gameState.currentPlayer === mySeat
    && gameState.phase !== 'handOver'
    && gameState.phase !== 'gameOver'
    && gameState.phase !== 'showdown'
  const validActions = isMyTurn ? getValidActions(gameState) : []
  const toCall = gameState.currentBet - gameState.bets[mySeat]

  // Winning card highlights
  const winningCardKeys = new Set<string>()
  if (gameState.phase === 'handOver' && gameState.showdownResults) {
    let bestRank = 0
    for (let i = 0; i < gameState.showdownResults.length; i++) {
      if (!gameState.foldedPlayers[i] && gameState.showdownResults[i].rank > bestRank) {
        bestRank = gameState.showdownResults[i].rank
      }
    }
    for (let i = 0; i < gameState.showdownResults.length; i++) {
      if (!gameState.foldedPlayers[i] && gameState.showdownResults[i].rank === bestRank) {
        for (const c of gameState.showdownResults[i].cards) {
          winningCardKeys.add(`${c.suit}-${c.rank}`)
        }
      }
    }
  }

  // Opponents: all seats except mine, rotated so seat order wraps
  const opponentSeats: number[] = []
  for (let offset = 1; offset < TABLE_SIZE; offset++) {
    opponentSeats.push((mySeat + offset) % TABLE_SIZE)
  }

  const myName = seatNames[mySeat]
  const currentTurnName = seatNames[gameState.currentPlayer]

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex items-center gap-3">
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-slate-400">Pot: <span className="text-yellow-400 font-bold">{gameState.pot}</span></span>
        <span className="text-slate-400">Blinds: {gameState.smallBlind}/{gameState.bigBlind}</span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Texas Hold'em — VS" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-xl space-y-2 sm:space-y-3">
        {/* Host can invite friends to fill AI seats */}
        {isHost && openAiSeats > 0 && (
          <InGameInvite roomId={roomId} openSeats={openAiSeats} />
        )}

        {/* Opponents */}
        <div className="flex gap-4 justify-center flex-wrap">
          {opponentSeats.map(si => {
            const hand = gameState.hands[si] || []
            const folded = gameState.foldedPlayers[si]
            const isAllIn = gameState.allInPlayers[si]
            const showCards = gameState.phase === 'handOver' && gameState.showdownResults && !folded
            const isDealer = gameState.dealerIdx === si
            const isSB = gameState.sbIdx === si
            const isBB = gameState.bbIdx === si
            const isHuman = humanSeats.has(si)
            const isTurn = gameState.currentPlayer === si

            return (
              <div key={si} className={`text-center ${folded ? 'opacity-40' : ''} ${isTurn && !folded ? 'ring-1 ring-blue-500/40 rounded-lg p-1' : 'p-1'}`}>
                <div className="flex items-center justify-center gap-1 mb-0.5">
                  <span className={`text-xs ${isHuman ? 'text-blue-400' : 'text-slate-400'}`}>
                    {seatNames[si]}
                  </span>
                  {isDealer && <span className="text-[0.6rem] bg-white text-slate-900 font-bold rounded-full w-4 h-4 flex items-center justify-center">D</span>}
                  {isSB && <span className="text-[0.6rem] bg-blue-500 text-white font-bold rounded-full px-1">SB</span>}
                  {isBB && <span className="text-[0.6rem] bg-amber-500 text-white font-bold rounded-full px-1">BB</span>}
                  {isAllIn && <span className="text-[0.6rem] text-red-400">(All-In)</span>}
                  {folded && <span className="text-[0.6rem] text-slate-500">(Fold)</span>}
                </div>
                <div className="text-xs text-yellow-400">{gameState.chips[si]}</div>
                <div className="flex gap-0.5 justify-center mt-1">
                  {hand.map((c, j) => {
                    const isWin = showCards && winningCardKeys.has(`${c.suit}-${c.rank}`)
                    return (
                      <div key={j} className={`w-10 h-14 sm:w-12 sm:h-[4rem] transition-transform ${isWin ? 'ring-2 ring-blue-400 rounded-md -translate-y-1' : ''}`}>
                        {showCards ? <CardFace card={c} mini /> : <CardBack />}
                      </div>
                    )
                  })}
                </div>
                {gameState.bets[si] > 0 && (
                  <span className="text-xs text-blue-400">Bet: {gameState.bets[si]}</span>
                )}
              </div>
            )
          })}
        </div>

        {/* Community cards */}
        <div className="flex gap-1.5 justify-center min-h-[5rem] sm:min-h-[7rem]">
          {gameState.community.map((card, i) => {
            const isWinning = winningCardKeys.has(`${card.suit}-${card.rank}`)
            return (
              <div key={i} className={`${CARD_SIZE_LARGE} transition-transform ${isWinning ? 'ring-2 ring-blue-400 rounded-lg -translate-y-2' : ''}`}>
                <CardFace card={card} large />
              </div>
            )
          })}
          {Array.from({ length: 5 - gameState.community.length }).map((_, i) => (
            <div key={`e${i}`} className={`${CARD_SIZE_LARGE} rounded-md border border-dashed border-slate-700/50`} />
          ))}
        </div>

        {/* Action text */}
        {actionText && (
          <p className="text-sm text-blue-400 font-medium text-center">{actionText}</p>
        )}
        {!isMyTurn && gameState.phase !== 'handOver' && gameState.phase !== 'gameOver' && gameState.phase !== 'showdown' && (
          <p className="text-xs text-slate-500 text-center animate-pulse">
            {currentTurnName} is thinking...
          </p>
        )}

        {/* Phase / status */}
        <p className="text-sm text-white font-medium text-center">
          {formatActionText(gameState.message)}
        </p>

        {/* My hand + controls */}
        <div className="flex items-center gap-3">
          <div className="flex flex-col items-center gap-1">
            {/* My cards */}
            <div className="flex gap-2 justify-center">
              {(gameState.hands[mySeat] || []).map((card, i) => {
                const isWinning = winningCardKeys.has(`${card.suit}-${card.rank}`)
                return (
                  <div key={i} className={`${CARD_SIZE} transition-transform ${isWinning ? 'ring-2 ring-blue-400 rounded-lg -translate-y-2' : ''}`}>
                    <CardFace card={card} />
                  </div>
                )
              })}
            </div>
            <div className="flex items-center justify-center gap-1.5 text-xs text-slate-400">
              <span className="text-blue-400">{myName}</span>
              {gameState.dealerIdx === mySeat && <span className="text-[0.6rem] bg-white text-slate-900 font-bold rounded-full w-4 h-4 flex items-center justify-center">D</span>}
              {gameState.sbIdx === mySeat && <span className="text-[0.6rem] bg-blue-500 text-white font-bold rounded-full px-1">SB</span>}
              {gameState.bbIdx === mySeat && <span className="text-[0.6rem] bg-amber-500 text-white font-bold rounded-full px-1">BB</span>}
              <span>— Chips: <span className="text-white font-bold">{gameState.chips[mySeat]}</span></span>
              {gameState.bets[mySeat] > 0 && <span>Bet: <span className="text-blue-400">{gameState.bets[mySeat]}</span></span>}
            </div>

            {/* Action buttons */}
            {isMyTurn && !gameState.foldedPlayers[mySeat] && (
              <div className="flex gap-1.5 sm:gap-2 flex-wrap justify-center">
                {validActions.includes('fold') && (
                  <button onClick={() => sendAction('fold')} className="px-2 sm:px-3 py-1 sm:py-1.5 bg-red-700 hover:bg-red-600 text-white rounded-lg text-xs sm:text-sm transition-colors">
                    Fold
                  </button>
                )}
                {validActions.includes('check') && (
                  <button onClick={() => sendAction('check')} className="px-2 sm:px-3 py-1 sm:py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-xs sm:text-sm transition-colors">
                    Check
                  </button>
                )}
                {validActions.includes('call') && (
                  <button onClick={() => sendAction('call')} className="px-2 sm:px-3 py-1 sm:py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs sm:text-sm transition-colors">
                    Call {toCall}
                  </button>
                )}
                {validActions.includes('raise') && (
                  <button onClick={() => sendAction('raise', raiseAmount)} className="px-2 sm:px-3 py-1 sm:py-1.5 bg-green-700 hover:bg-green-600 text-white rounded-lg text-xs sm:text-sm transition-colors">
                    Raise {raiseAmount}
                  </button>
                )}
                {validActions.includes('allIn') && (
                  <button onClick={() => sendAction('allIn')} className="px-2 sm:px-3 py-1 sm:py-1.5 bg-yellow-700 hover:bg-yellow-600 text-white rounded-lg text-xs sm:text-sm transition-colors">
                    All-In
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Vertical raise slider */}
          {isMyTurn && !gameState.foldedPlayers[mySeat] && validActions.includes('raise') && (
            <div className="flex flex-col items-center gap-0.5 self-stretch">
              <span className="text-[0.5rem] text-slate-500">{gameState.chips[mySeat] + gameState.bets[mySeat]}</span>
              <input
                type="range"
                min={getMinRaise(gameState)}
                max={gameState.chips[mySeat] + gameState.bets[mySeat]}
                step={gameState.bigBlind}
                value={raiseAmount}
                onChange={e => setRaiseAmount(Number(e.target.value))}
                className="flex-1"
                style={{ writingMode: 'vertical-lr', direction: 'rtl' }}
              />
              <span className="text-[0.5rem] text-slate-500">{getMinRaise(gameState)}</span>
            </div>
          )}
        </div>

        {/* Next hand / game over */}
        <div className="flex gap-2 justify-center">
          {gameState.phase === 'handOver' && (
            <button
              onClick={handleNextHand}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Next Hand
            </button>
          )}
        </div>

        {(gameStatus === 'won' || gameStatus === 'lost') && (
          <GameOverModal
            status={gameStatus}
            score={gameState.chips[mySeat]}
            message={formatActionText(gameState.message)}
            onPlayAgain={onLeave || (() => {})}
            playAgainText={onLeave ? 'Back to Lobby' : undefined}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
