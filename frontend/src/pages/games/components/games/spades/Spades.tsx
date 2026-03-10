/**
 * Spades — 4-player partnership trick-taking card game.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE_COMPACT, CARD_SLOT_V, CARD_SLOT_H } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import {
  createSpadesGame,
  placeBid,
  playCard,
  nextRound,
  getValidPlays,
  PLAYER_NAMES,
  TEAM_NAMES,
  type SpadesState,
} from './spadesEngine'

interface SavedState {
  gameState: SpadesState
  gameStatus: GameStatus
}

// ── Help modal ──────────────────────────────────────────────────────
function SpadesHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Spades</h2>

        <Sec title="Overview">
          <p>4-player partnership trick-taking game. You (South) and North vs East and West. <B>Spades are always trump.</B></p>
        </Sec>

        <Sec title="Bidding">
          <ul className="space-y-1">
            <Li>Each player bids how many tricks they expect to win (0–13).</Li>
            <Li>Your team's bids are combined — you must win at least that many tricks total.</Li>
            <Li>A bid of <B>0 (Nil)</B> means you'll try to win zero tricks — risky but rewarding.</Li>
            <Li><B>Blind Nil</B> — Bid Nil without looking at your cards for even bigger reward.</Li>
          </ul>
        </Sec>

        <Sec title="Playing">
          <ul className="space-y-1">
            <Li>You must <B>follow suit</B> — play the same suit as the lead card if you can.</Li>
            <Li>If you can't follow suit, you may play any card (including a spade to trump).</Li>
            <Li>Spades cannot be led until they've been <B>broken</B> (played on another trick).</Li>
            <Li>Highest card of the led suit wins, unless a spade trumps it.</Li>
          </ul>
        </Sec>

        <Sec title="Scoring">
          <ul className="space-y-1">
            <Li><B>Making bid</B> — 10 points per trick bid, plus 1 per overtrick (bag).</Li>
            <Li><B>Bags penalty</B> — Every 10 accumulated bags costs −100 points.</Li>
            <Li><B>Nil success</B> — +100 points. Nil failure — −100 points.</Li>
            <Li><B>Blind Nil success</B> — +200 points. Failure — −200 points.</Li>
            <Li>First team to <B>500</B> wins. If tied, play continues.</Li>
          </ul>
        </Sec>

        <Sec title="Strategy Tips">
          <ul className="space-y-1">
            <Li>Bid conservatively — bags add up fast and the penalty is steep.</Li>
            <Li>Lead with off-suit winners early to force out trumps.</Li>
            <Li>Protect your partner's Nil bid by taking tricks that might force them to win.</Li>
            <Li>Count spades played — knowing how many remain is key in late tricks.</Li>
          </ul>
        </Sec>
      </div>
    </div>
  )
}

function SpadesSinglePlayer({ onGameEnd, onStateChange: _onStateChange }: { onGameEnd?: (result: 'win' | 'loss' | 'draw') => void; onStateChange?: (state: object) => void } = {}) {
  const { load, save, clear } = useGameState<SavedState>('spades')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('spades'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('spades')

  const [showHelp, setShowHelp] = useState(false)
  const [gameState, setGameState] = useState<SpadesState>(
    () => saved?.gameState ?? createSpadesGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedBid, setSelectedBid] = useState(3)
  const [blindNil, setBlindNil] = useState(false)

  // SFX on trick completion
  const prevTrickLen = useRef(0)
  useEffect(() => {
    if (prevTrickLen.current > 0 && gameState.currentTrick.length === 0) sfx.play('trick_won')
    prevTrickLen.current = gameState.currentTrick.length
  }, [gameState.currentTrick.length])

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const result = gameState.teamScores[0] > gameState.teamScores[1] ? 'won' : 'lost'
      setGameStatus(result)
      onGameEnd?.(result === 'won' ? 'win' : 'loss')
      clear()
    }
  }, [gameState, clear, onGameEnd])

  const handleBid = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    setGameState(prev => placeBid(prev, selectedBid, blindNil))
    setBlindNil(false)
  }, [selectedBid, blindNil])

  const handlePlay = useCallback((i: number) => {
    sfx.play('play')
    setGameState(prev => playCard(prev, i))
  }, [])

  const handleNextRound = useCallback(() => {
    sfx.play('hand_won')
    setGameState(prev => nextRound(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createSpadesGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const validPlays = getValidPlays(gameState)
  const isBidding = gameState.phase === 'bidding'
  const isPlaying = gameState.phase === 'playing' && gameState.currentPlayer === 0
  const bids = gameState.bids

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex gap-3">
        <span className="text-blue-400">{TEAM_NAMES[0]}: {gameState.teamScores[0]}</span>
        <span className="text-red-400">{TEAM_NAMES[1]}: {gameState.teamScores[1]}</span>
      </div>
      {bids[0] !== null && (
        <div className="flex gap-2 text-slate-400">
          {PLAYER_NAMES.map((name, i) => (
            <span key={i}>
              {name}: {bids[i] ?? '?'}/{gameState.tricksTaken[i]}
            </span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2">
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play">
          <HelpCircle className="w-4 h-4 text-blue-400" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Spades" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* North (Partner) */}
        <div className="text-center">
          <span className="text-xs text-blue-400">North (Partner) ({gameState.hands[2].length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[2].slice(0, 7).map((_, i) => (
              <div key={i} className={CARD_SLOT_V}><CardBack /></div>
            ))}
            {gameState.hands[2].length > 7 && <span className="text-[0.6rem] text-slate-500 self-center">+{gameState.hands[2].length - 7}</span>}
          </div>
        </div>

        {/* West + Trick area + East */}
        <div className="flex w-full items-center gap-2">
          {/* West (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">West ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>

          {/* Trick area */}
          <div className="flex-1 relative h-36 sm:h-48">
            {gameState.currentTrick.map((play) => {
              const positions = [
                'bottom-0 left-1/2 -translate-x-1/2',
                'right-0 top-1/2 -translate-y-1/2',
                'top-0 left-1/2 -translate-x-1/2',
                'left-0 top-1/2 -translate-y-1/2',
              ]
              return (
                <div key={`${play.player}-${play.card.rank}-${play.card.suit}`}
                  className={`absolute ${positions[play.player]} ${CARD_SIZE_COMPACT}`}
                >
                  <CardFace card={play.card} />
                </div>
              )
            })}
            {gameState.spadesBroken && (
              <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[0.6rem] text-slate-500">
                Spades broken
              </span>
            )}
          </div>

          {/* East (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">East ({gameState.hands[1].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[1].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Bidding */}
        {isBidding && (
          <div className="flex flex-col items-center gap-2">
            <div className="flex gap-1 flex-wrap justify-center">
              {Array.from({ length: 14 }, (_, i) => (
                <button
                  key={i}
                  onClick={() => setSelectedBid(i)}
                  className={`w-8 h-8 text-xs rounded transition-colors ${
                    selectedBid === i ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {i === 0 ? 'Nil' : i}
                </button>
              ))}
            </div>
            {selectedBid === 0 && (
              <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={blindNil}
                  onChange={e => setBlindNil(e.target.checked)}
                  className="rounded"
                />
                Blind Nil (+/-200 instead of +/-100)
              </label>
            )}
            <button
              onClick={handleBid}
              className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Bid {selectedBid === 0 ? (blindNil ? 'Blind Nil' : 'Nil') : selectedBid}
            </button>
          </div>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {gameState.hands[0].map((card, i) => {
            const isValid = validPlays.includes(i)
            return (
              <div
                key={`${card.rank}-${card.suit}`}
                className={`${CARD_SIZE_COMPACT} transition-transform ${
                  isPlaying && isValid ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
                }`}
                onClick={() => isPlaying && isValid && handlePlay(i)}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {/* Round over */}
        {gameState.phase === 'roundOver' && (
          <button
            onClick={handleNextRound}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Next Round
          </button>
        )}

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
      {showHelp && <SpadesHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (first-to-win against AI) ─────────────────────────

function SpadesRaceWrapper({ roomId, difficulty: _difficulty }: { roomId: string; difficulty?: string }) {
  const { opponentStatus, raceResult, opponentLevelUp, broadcastState, reportFinish } = useRaceMode(roomId, 'first_to_win')
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
      />
      <SpadesSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} />
    </div>
  )
}

export default function Spades() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'spades',
        gameName: 'Spades',
        modes: ['race'],
        maxPlayers: 2,
        hasDifficulty: true,
        raceDescription: 'First to make their bid wins',
      }}
      renderSinglePlayer={() => <SpadesSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig) =>
        <SpadesRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} />
      }
    />
  )
}
