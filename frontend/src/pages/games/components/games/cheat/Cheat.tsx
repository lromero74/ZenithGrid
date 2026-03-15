/**
 * Cheat (aka BS) — bluff your way to victory or call out the liars.
 * 1 human + 3 AI opponents in single-player mode.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SIZE_MINI } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import { getRankDisplay } from '../../../utils/cardUtils'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import { CheatMultiplayer } from './CheatMultiplayer'
import {
  createCheatGame,
  playCards,
  callBS,
  passChallenge,
  resolveChallenge,
  aiPlayTurn,
  aiDecideChallenge,
  type CheatState,
} from './cheatEngine'

interface SavedState {
  gameState: CheatState
  gameStatus: GameStatus
}

// ── Help modal ───────────────────────────────────────────────────────

function CheatHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Cheat (BS)</h2>

        <Sec title="Goal">
          Be the first player to get rid of <B>all your cards</B>. Bluff when you
          need to, but watch out — other players can call your bluff!
        </Sec>

        <Sec title="Setup">
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>A standard <B>52-card deck</B> is dealt evenly among 4 players.</Li>
            <Li>Each player gets <B>13 cards</B>.</Li>
            <Li>The required rank starts at <B>Ace</B> and cycles: A, 2, 3, ... K, A, 2, ...</Li>
          </ul>
        </Sec>

        <Sec title="How to Play">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li>On your turn, select <B>1-4 cards</B> from your hand.</li>
            <li>Click <B>"Play"</B> to place them face-down, claiming they are the required rank.</li>
            <li>You may <B>bluff</B> — the cards don&apos;t have to match the claimed rank!</li>
            <li>After cards are played, other players can call <B>"BS!"</B> or <B>pass</B>.</li>
          </ol>
        </Sec>

        <Sec title="Challenges">
          <ul className="space-y-1 text-slate-300">
            <Li>If someone calls <B>BS!</B> and you were bluffing, <B>you</B> pick up the entire pile.</Li>
            <Li>If you were honest, the <B>challenger</B> picks up the pile.</Li>
            <Li>If nobody challenges, play moves to the next player.</Li>
          </ul>
        </Sec>

        <Sec title="Winning">
          <ul className="space-y-1 text-slate-300">
            <Li>The first player to <B>empty their hand</B> wins.</Li>
            <Li>But if someone calls BS on your last play and you were bluffing, you pick up the pile!</Li>
          </ul>
        </Sec>

        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Play honestly when possible.</B> If you have cards of the required rank, use them.</Li>
            <Li><B>Bluff with confidence.</B> Playing just 1 card is less suspicious than 3-4.</Li>
            <Li><B>Watch the pile size.</B> Calling BS when the pile is large is risky but rewarding.</Li>
            <Li><B>Track what&apos;s been played.</B> If you hold 3 Aces and someone claims Aces, they&apos;re lying!</Li>
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

function CheatSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<SavedState>('cheat')
  const saved = useRef(load()).current

  const song = useMemo(() => getSongForGame('cheat'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('cheat')

  const [showHelp, setShowHelp] = useState(false)
  const [selectedCards, setSelectedCards] = useState<number[]>([])
  const [message, setMessage] = useState('')
  const [revealCards, setRevealCards] = useState<import('../../../utils/cardUtils').Card[] | null>(null)

  const [gameState, setGameState] = useState<CheatState>(
    () => saved?.gameState ?? createCheatGame(4)
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  // Save state
  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Update message based on game phase
  useEffect(() => {
    const { phase, currentPlayer, requiredRank, lastPlay, challengeResult, challengedBy, winner } = gameState

    if (phase === 'gameOver') {
      if (winner === 0) {
        setMessage('You win! You got rid of all your cards!')
      } else {
        setMessage(`Player ${winner! + 1} wins!`)
      }
      return
    }

    if (phase === 'reveal' && lastPlay && challengedBy !== null) {
      const challengerName = challengedBy === 0 ? 'You' : `AI ${challengedBy}`
      const playerName = lastPlay.player === 0 ? 'You' : `AI ${lastPlay.player}`
      if (challengeResult === 'bluff') {
        setMessage(`${challengerName} called BS! ${playerName} was bluffing! ${playerName === 'You' ? 'You pick' : `${playerName} picks`} up the pile.`)
      } else {
        setMessage(`${challengerName} called BS! ${playerName} was honest! ${challengerName === 'You' ? 'You pick' : `${challengerName} picks`} up the pile.`)
      }
      return
    }

    if (phase === 'challenge' && lastPlay) {
      const playerName = lastPlay.player === 0 ? 'You' : `AI ${lastPlay.player}`
      setMessage(`${playerName} played ${lastPlay.claimedCount} ${getRankDisplay(lastPlay.claimedRank)}(s). Call BS or pass?`)
      return
    }

    if (phase === 'play') {
      if (currentPlayer === 0) {
        setMessage(`Your turn — play cards as ${getRankDisplay(requiredRank)}s`)
      } else {
        setMessage(`AI ${currentPlayer}'s turn...`)
      }
    }
  }, [gameState])

  // Game over detection
  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const won = gameState.winner === 0
      sfx.play(won ? 'match' : 'play')
      setGameStatus(won ? 'won' : 'lost')
      onGameEnd?.(won ? 'win' : 'loss')
      clear()
    }
  }, [gameState.phase, gameState.winner, clear, onGameEnd, sfx])

  // AI play turn
  useEffect(() => {
    if (gameState.phase === 'play' && gameState.currentPlayer !== 0) {
      const timer = setTimeout(() => {
        setGameState(prev => aiPlayTurn(prev))
      }, 800)
      return () => clearTimeout(timer)
    }
  }, [gameState.phase, gameState.currentPlayer])

  // AI challenge decisions (sequential)
  useEffect(() => {
    if (gameState.phase !== 'challenge' || !gameState.lastPlay) return

    // Find next AI player who hasn't passed yet
    const playedBy = gameState.lastPlay.player
    for (let i = 1; i < gameState.playerCount; i++) {
      const p = (playedBy + i) % gameState.playerCount
      if (p === 0) continue // human decides manually
      if (p === playedBy) continue
      if (gameState.passedPlayers.includes(p)) continue

      // This AI player needs to decide
      const timer = setTimeout(() => {
        setGameState(prev => aiDecideChallenge(prev, p))
      }, 600 + Math.random() * 400)
      return () => clearTimeout(timer)
    }

    // If we get here and human hasn't passed yet, wait for human
    // If human already passed (or is the player), all have passed — handled by passChallenge
  }, [gameState.phase, gameState.passedPlayers, gameState.lastPlay, gameState.playerCount])

  // Reveal phase — show cards briefly then resolve
  useEffect(() => {
    if (gameState.phase === 'reveal' && gameState.lastPlay) {
      setRevealCards(gameState.lastPlay.cards)
      sfx.play('draw')
      const timer = setTimeout(() => {
        setRevealCards(null)
        setGameState(prev => resolveChallenge(prev))
      }, 2000)
      return () => clearTimeout(timer)
    }
  }, [gameState.phase, sfx])

  const toggleCard = useCallback((index: number) => {
    setSelectedCards(prev => {
      if (prev.includes(index)) return prev.filter(i => i !== index)
      if (prev.length >= 4) return prev
      return [...prev, index]
    })
  }, [])

  const handlePlay = useCallback(() => {
    if (selectedCards.length === 0) return
    music.init()
    sfx.init()
    music.start()
    sfx.play('play')
    setGameState(prev => playCards(prev, selectedCards, prev.requiredRank))
    setSelectedCards([])
  }, [selectedCards, music, sfx])

  const handleCallBS = useCallback(() => {
    sfx.play('play')
    setGameState(prev => callBS(prev, 0))
  }, [sfx])

  const handlePass = useCallback(() => {
    setGameState(prev => passChallenge(prev, 0))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createCheatGame(4))
    setGameStatus('playing')
    setSelectedCards([])
    setRevealCards(null)
    clear()
  }, [clear])

  const isMyTurn = gameState.phase === 'play' && gameState.currentPlayer === 0
  const canChallenge = gameState.phase === 'challenge' &&
    gameState.lastPlay !== null &&
    gameState.lastPlay.player !== 0 &&
    !gameState.passedPlayers.includes(0)

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3 text-xs text-slate-400">
        <span className="text-white">Required: {getRankDisplay(gameState.requiredRank)}</span>
        <span>Pile: {gameState.pile.length}</span>
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

  return (
    <GameLayout title="Cheat (aka BS)" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-2xl space-y-3">
        {/* AI opponents */}
        <div className="flex gap-6 justify-center flex-wrap">
          {[1, 2, 3].map(p => (
            <div key={p} className={`text-center ${gameState.currentPlayer === p && gameState.phase === 'play' ? 'ring-2 ring-blue-500 rounded-lg p-1.5' : 'p-1.5'}`}>
              <span className={`text-xs ${gameState.currentPlayer === p ? 'text-blue-400 font-medium' : 'text-slate-400'}`}>
                AI {p} ({gameState.hands[p].length})
              </span>
              <div className="flex gap-0.5 justify-center mt-1">
                {Array.from({ length: Math.min(gameState.hands[p].length, 6) }).map((_, j) => (
                  <div key={j} className={CARD_SIZE_MINI}>
                    <CardBack />
                  </div>
                ))}
                {gameState.hands[p].length > 6 && (
                  <span className="text-xs text-slate-500 self-center ml-0.5">+{gameState.hands[p].length - 6}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Pile */}
        <div className="flex gap-3 items-center justify-center">
          <div className={`${CARD_SIZE} relative`}>
            {gameState.pile.length > 0 ? (
              <div className="relative">
                <CardBack />
                <span className="absolute -bottom-1 -right-1 bg-slate-800 text-white text-xs px-1.5 py-0.5 rounded-full border border-slate-600">
                  {gameState.pile.length}
                </span>
              </div>
            ) : (
              <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                Empty
              </div>
            )}
          </div>
        </div>

        {/* Reveal cards during challenge */}
        {revealCards && (
          <div className="flex gap-1 justify-center bg-slate-800/80 rounded-lg p-2 border border-yellow-500/50">
            <span className="text-xs text-yellow-400 mr-2 self-center">Revealed:</span>
            {revealCards.map((c, i) => (
              <div key={i} className={CARD_SIZE}>
                <CardFace card={c} />
              </div>
            ))}
          </div>
        )}

        {/* Message */}
        <p className="text-sm text-white font-medium text-center min-h-[1.5rem]">{message}</p>

        {/* Action buttons */}
        <div className="flex gap-2 justify-center min-h-[2.5rem]">
          {isMyTurn && selectedCards.length > 0 && (
            <button
              onClick={handlePlay}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Play {selectedCards.length} as {getRankDisplay(gameState.requiredRank)}{selectedCards.length > 1 ? 's' : ''}
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
          {gameState.hands[0].map((card, i) => {
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

        {gameState.hands[0].length === 0 && gameState.phase !== 'gameOver' && (
          <p className="text-xs text-slate-500">No cards in hand</p>
        )}

        {(gameStatus === 'won' || gameStatus === 'lost') && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            score={0}
            message={message}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <CheatHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper ─────────────────────────────────────────────────────

function CheatRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
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
      <CheatSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function Cheat() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'cheat',
        gameName: 'Cheat (aka BS)',
        modes: ['vs', 'first_to_win'],
        maxPlayers: 4,
        hasDifficulty: false,
        modeDescriptions: { vs: 'Bluff and challenge in real-time', first_to_win: 'First to empty your hand wins' },
      }}
      renderSinglePlayer={() => <CheatSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <CheatMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
        ) : (
          <CheatRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
        )
      }
    />
  )
}
