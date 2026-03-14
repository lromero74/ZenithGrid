/**
 * Video Poker (Jacks or Better) — hold/draw poker against the machine.
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
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'
import {
  createVideoPokerGame,
  deal,
  toggleHold,
  draw,
  newHand,
  setBet,
  isGameOver,
  getPayTable,
  MAX_BET,
  MIN_BET,
  type VideoPokerState,
} from './videoPokerEngine'

interface SavedState {
  gameState: VideoPokerState
  gameStatus: GameStatus
}

function VideoPokerHelp({ onClose }: { onClose: () => void }) {
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
        <h2 className="text-lg font-bold text-white mb-4">How to Play Video Poker</h2>
        <Sec title="Goal"><p>Make the best 5-card poker hand. This is <B>Jacks or Better</B> — you need at least a pair of Jacks to win.</p></Sec>
        <Sec title="How to Play"><ul className="space-y-1">
          <Li><B>Bet</B> credits and click <B>Deal</B> to receive 5 cards.</Li>
          <Li><B>Hold</B> the cards you want to keep by clicking them.</Li>
          <Li>Click <B>Draw</B> to replace un-held cards with new ones from the deck.</Li>
          <Li>Your final hand is evaluated and pays according to the pay table.</Li>
        </ul></Sec>
        <Sec title="Hand Rankings (Low to High)"><ul className="space-y-1">
          <Li><B>Jacks or Better</B> — Pair of J, Q, K, or A.</Li>
          <Li><B>Two Pair</B> — Two different pairs.</Li>
          <Li><B>Three of a Kind</B> — Three cards of the same rank.</Li>
          <Li><B>Straight</B> — Five consecutive cards.</Li>
          <Li><B>Flush</B> — Five cards of the same suit.</Li>
          <Li><B>Full House</B> — Three of a kind + a pair.</Li>
          <Li><B>Four of a Kind</B> — Four cards of the same rank.</Li>
          <Li><B>Straight Flush</B> — Straight + flush.</Li>
          <Li><B>Royal Flush</B> — 10, J, Q, K, A of the same suit.</Li>
        </ul></Sec>
        <Sec title="Strategy Tips"><ul className="space-y-1">
          <Li>Always hold a paying hand (pair of Jacks or better).</Li>
          <Li>Hold 4 to a flush or straight — the draw odds are good.</Li>
          <Li>Never hold a kicker with a high pair.</Li>
          <Li>Max bet for the best Royal Flush payout.</Li>
        </ul></Sec>
      </div>
    </div>
  )
}

function VideoPokerSinglePlayer({ onGameEnd, onScoreChange, onStateChange: _onStateChange, isMultiplayer }: {
  onGameEnd?: (result: 'win' | 'loss' | 'draw') => void
  onScoreChange?: (credits: number) => void
  onStateChange?: (state: object) => void
  isMultiplayer?: boolean
} = {}) {
  const { load, save, clear } = useGameState<SavedState>('video-poker')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('video-poker'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('video-poker')
  const [showHelp, setShowHelp] = useState(false)

  const [gameState, setGameState] = useState<VideoPokerState>(
    () => saved?.gameState ?? createVideoPokerGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  useEffect(() => {
    if (gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (isGameOver(gameState)) {
      setGameStatus('lost')
      onGameEnd?.('loss')
      clear()
    }
  }, [gameState, clear, onGameEnd])

  // Report score changes for race mode
  useEffect(() => {
    onScoreChange?.(gameState.credits)
  }, [gameState.credits, onScoreChange])

  // SFX on result
  useEffect(() => {
    if (gameState.phase === 'result' && gameState.lastResult) {
      if (gameState.lastResult.name === 'Royal Flush') sfx.play('jackpot')
      else if (gameState.lastResult.multiplier > 0) sfx.play('win')
    }
  }, [gameState.phase])

  const handleBetChange = useCallback((delta: number) => {
    setGameState(prev => setBet(prev, prev.bet + delta))
  }, [])

  const handleDeal = useCallback(() => { music.init(); sfx.init(); music.start(); sfx.play('deal'); setGameState(prev => deal(prev)) }, [])
  const handleToggle = useCallback((i: number) => { sfx.play('hold'); setGameState(prev => toggleHold(prev, i)) }, [])
  const handleDraw = useCallback(() => { sfx.play('draw'); setGameState(prev => draw(prev)) }, [])
  const handleNewHand = useCallback(() => setGameState(prev => newHand(prev)), [])

  const handleNewGame = useCallback(() => {
    setGameState(createVideoPokerGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const payTable = getPayTable()

  const controls = (
    <div className="flex items-center justify-between">
      <span className="text-xs text-slate-400">Jacks or Better</span>
      <span className="text-xs text-yellow-400 font-mono">Credits: {gameState.credits}</span>
      <div className="flex items-center gap-2">
        <button onClick={() => setShowHelp(true)} className="p-1 hover:bg-slate-700 rounded transition-colors" title="How to Play"><HelpCircle className="w-4 h-4 text-blue-400" /></button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Video Poker" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* Pay table */}
        <div className="w-full bg-slate-800/50 rounded-lg p-2 text-[0.6rem] sm:text-xs">
          <div className="grid grid-cols-6 gap-x-2 gap-y-0.5 text-center">
            <div className="text-slate-500 font-semibold text-left col-span-1">Hand</div>
            {[1, 2, 3, 4, 5].map(b => (
              <div key={b} className={`font-mono ${b === gameState.bet ? 'text-yellow-400 font-bold' : 'text-slate-500'}`}>
                {b}x
              </div>
            ))}
            {payTable.map(row => (
              <div key={row.name} className="contents">
                <div className={`text-left truncate ${gameState.lastResult?.name === row.name ? 'text-emerald-400 font-bold' : 'text-slate-400'}`}>
                  {row.name}
                </div>
                {[1, 2, 3, 4, 5].map(b => {
                  const mult = row.name === 'Royal Flush' && b === 5 ? 800 : row.multiplier
                  return (
                    <div key={b} className={`font-mono ${
                      gameState.lastResult?.name === row.name && b === gameState.bet
                        ? 'text-emerald-400 font-bold' : 'text-slate-500'
                    }`}>
                      {mult * b}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>

        {/* Cards */}
        <div className="flex gap-2 justify-center">
          {gameState.phase === 'betting' ? (
            // Show 5 card backs
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className={CARD_SIZE}>
                <CardBack />
              </div>
            ))
          ) : (
            gameState.hand.map((card, i) => (
              <div key={i} className="flex flex-col items-center gap-1">
                <div
                  className={`${CARD_SIZE} cursor-pointer ${gameState.phase === 'dealt' ? 'hover:opacity-80' : ''}`}
                  onClick={() => handleToggle(i)}
                >
                  <CardFace card={card} held={gameState.held[i]} />
                </div>
                {gameState.held[i] && (
                  <span className="text-[0.6rem] text-cyan-400 font-bold">HELD</span>
                )}
              </div>
            ))
          )}
        </div>

        {/* Message */}
        <p className={`text-sm font-medium ${gameState.lastResult ? 'text-emerald-400' : 'text-white'}`}>
          {gameState.message}
        </p>

        {/* Controls */}
        <div className="flex items-center gap-3">
          {gameState.phase === 'betting' && (
            <>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleBetChange(-1)}
                  disabled={gameState.bet <= MIN_BET}
                  className="px-2 py-1 text-xs bg-slate-700 text-slate-300 rounded hover:bg-slate-600 disabled:opacity-40"
                >
                  -
                </button>
                <span className="text-sm text-white font-mono w-8 text-center">Bet {gameState.bet}</span>
                <button
                  onClick={() => handleBetChange(1)}
                  disabled={gameState.bet >= MAX_BET || gameState.bet >= gameState.credits}
                  className="px-2 py-1 text-xs bg-slate-700 text-slate-300 rounded hover:bg-slate-600 disabled:opacity-40"
                >
                  +
                </button>
              </div>
              <button
                onClick={handleDeal}
                disabled={gameState.bet > gameState.credits}
                className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
              >
                Deal
              </button>
            </>
          )}
          {gameState.phase === 'dealt' && (
            <button
              onClick={handleDraw}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Draw
            </button>
          )}
          {gameState.phase === 'result' && !isGameOver(gameState) && (
            <button
              onClick={handleNewHand}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              New Hand
            </button>
          )}
        </div>

        {gameStatus === 'lost' && !isMultiplayer && (
          <GameOverModal
            status="lost"
            message="You're out of credits!"
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <VideoPokerHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (best_score — highest credits wins) ─────────────────

function VideoPokerRaceWrapper({ roomId, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, localScore, opponentLevelUp, broadcastState, reportFinish, reportScore, leaveRoom } =
    useRaceMode(roomId, 'best_score')
  const finishedRef = useRef(false)
  const latestCredits = useRef(100)

  const handleScoreChange = useCallback((credits: number) => {
    latestCredits.current = credits
    reportScore(credits)
  }, [reportScore])

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw') => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish(result === 'draw' ? 'loss' : result, latestCredits.current)
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
      <VideoPokerSinglePlayer onGameEnd={handleGameEnd} onScoreChange={handleScoreChange} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function VideoPoker() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'video-poker',
        gameName: 'Video Poker',
        modes: ['best_score'],
        maxPlayers: 2,
        hasDifficulty: false,
        modeDescriptions: { best_score: 'Highest credits wins' },
      }}
      renderSinglePlayer={() => <VideoPokerSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, _roomConfig, onLeave) =>
        <VideoPokerRaceWrapper roomId={roomId} onLeave={onLeave} />
      }
    />
  )
}
