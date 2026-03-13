/**
 * Mahjong Solitaire — match pairs of free tiles to clear the board.
 *
 * Features: tile matching, shuffle, hint, undo, multiple layouts.
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { Shuffle, Lightbulb, Undo2, RotateCcw, HelpCircle, X } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameTimer } from '../../../hooks/useGameTimer'
import { useGameState } from '../../../hooks/useGameState'
import {
  createGame, canMatch, isTileFree, findAllMatches,
  removePair, shuffleTiles, isGameWon, isGameOver,
  type GameTile,
} from './mahjongEngine'
import { MahjongTile, type TileTheme } from './MahjongTile'
import { TURTLE_LAYOUT, PYRAMID_LAYOUT } from './layouts'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { MultiplayerWrapper } from '../../multiplayer/MultiplayerWrapper'
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

type LayoutName = 'turtle' | 'pyramid'
const LAYOUTS = { turtle: TURTLE_LAYOUT, pyramid: PYRAMID_LAYOUT }

interface MahjongSaved {
  layoutName: LayoutName
  tileTheme: TileTheme
  tiles: GameTile[]
  gameStatus: GameStatus
  shufflesLeft: number
  elapsed: number
}

// ── Help Modal ──────────────────────────────────────────────────────

function MahjongHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-5 sm:p-6"
        onClick={e => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-4">How to Play Mahjong Solitaire</h2>

        <Sec title="Goal">
          Remove all tiles from the board by matching them in <B>pairs</B>.
          Clear every tile to win. If no more matches are available and tiles
          remain, the game is over.
        </Sec>

        <Sec title="How It Works">
          <ol className="mt-1.5 space-y-1 text-slate-300 list-decimal list-inside">
            <li>Tiles are stacked in layers on the board.</li>
            <li>Click a <B>free tile</B> to select it (highlighted with a blue border).</li>
            <li>Click a second free tile with the <B>same face</B> to remove the pair.</li>
            <li>If the second tile does not match, it becomes the new selection.</li>
            <li>Continue until all tiles are cleared or no moves remain.</li>
          </ol>
        </Sec>

        <Sec title="Free Tiles">
          A tile is <B>free</B> (selectable) only when both conditions are met:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li>No tile is sitting <B>on top</B> of it (on a higher layer).</Li>
            <Li>At least one <B>side</B> (left or right) is open &mdash; not blocked
              by an adjacent tile on the same layer.</Li>
          </ul>
          Blocked tiles appear slightly dimmed and cannot be selected.
        </Sec>

        <Sec title="Tile Suits">
          The board contains tiles from several suits:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Bamboo</B> (1&ndash;9) &mdash; each number matches its identical copy.</Li>
            <Li><B>Circle</B> (1&ndash;9) &mdash; same matching rule as Bamboo.</Li>
            <Li><B>Character</B> (1&ndash;9) &mdash; same matching rule.</Li>
            <Li><B>Winds</B> (N, S, E, W) &mdash; each direction matches its identical copy.</Li>
            <Li><B>Dragons</B> (Red, Green, White) &mdash; each matches its identical copy.</Li>
            <Li><B>Flowers</B> (Plum, Orchid, Chrysanthemum, Bamboo) &mdash; any flower matches <B>any other flower</B>.</Li>
            <Li><B>Seasons</B> (Spring, Summer, Autumn, Winter) &mdash; any season matches <B>any other season</B>.</Li>
          </ul>
        </Sec>

        <Sec title="Layouts">
          Two board layouts are available, selectable from the toolbar:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Pyramid</B> &mdash; a layered pyramid shape.</Li>
            <Li><B>Turtle</B> &mdash; the classic Mahjong Solitaire arrangement with 144 tiles
              across 5 layers, including wing tiles on the sides.</Li>
          </ul>
          Selecting a layout starts a new game.
        </Sec>

        <Sec title="Tile Themes">
          Toggle between two visual styles with the theme button in the toolbar:
          <ul className="mt-1.5 space-y-1 text-slate-300">
            <Li><B>Kanji</B> &mdash; tiles display traditional Mahjong characters and symbols.</Li>
            <Li><B>Classic</B> &mdash; tiles display emoji-style icons.</Li>
          </ul>
        </Sec>

        <Sec title="Tools">
          <ul className="space-y-1 text-slate-300">
            <Li><B>Hint</B> (lightbulb) &mdash; highlights a valid matching pair on the board.</Li>
            <Li><B>Shuffle</B> &mdash; rearranges the remaining tiles into new positions.
              You get <B>3 shuffles</B> per game. Use them when you are stuck.</Li>
            <Li><B>Undo</B> &mdash; reverses the last match, restoring the removed pair.
              Supports up to 30 levels of undo.</Li>
            <Li><B>New Game</B> (rotate icon) &mdash; starts a fresh game with the current layout.</Li>
          </ul>
        </Sec>

        <Sec title="Strategy Tips">
          <ul className="space-y-1 text-slate-300">
            <Li>Focus on removing tiles from the <B>highest layers</B> first to uncover
              more options below.</Li>
            <Li>Try to keep the board <B>balanced</B> &mdash; avoid clearing one side
              completely while the other remains stacked.</Li>
            <Li>Look for <B>identical pairs</B> that are both free before committing
              &mdash; sometimes there are multiple ways to pair the same tile.</Li>
            <Li>Save your <B>shuffles</B> for when you truly have no moves.</Li>
            <Li>Use <B>hints</B> sparingly &mdash; they are unlimited but finding matches
              yourself is more satisfying!</Li>
            <Li>Remember that <B>Flowers</B> and <B>Seasons</B> match any tile in
              their group, making them easier to pair.</Li>
          </ul>
        </Sec>
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

function MahjongSinglePlayer({ onGameEnd, onStateChange: _onStateChange, isMultiplayer }: { onGameEnd?: (result: 'win' | 'loss' | 'draw', score?: number) => void; onStateChange?: (state: object) => void; isMultiplayer?: boolean } = {}) {
  const { load, save, clear } = useGameState<MahjongSaved>('mahjong')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('mahjong'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('mahjong')

  const initLayout = saved?.layoutName ?? 'pyramid'
  const [layoutName, setLayoutName] = useState<LayoutName>(initLayout)
  const [tileTheme, setTileTheme] = useState<TileTheme>(saved?.tileTheme ?? 'kanji')
  const [game, setGame] = useState(() =>
    saved?.tiles ? { tiles: saved.tiles } : createGame(LAYOUTS[initLayout])
  )
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [hintPair, setHintPair] = useState<[number, number] | null>(null)
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [history, setHistory] = useState<GameTile[][]>([])
  const [shufflesLeft, setShuffle] = useState(saved?.shufflesLeft ?? 3)
  const [showHelp, setShowHelp] = useState(false)
  const timer = useGameTimer(saved?.elapsed)

  // Persist state
  useEffect(() => {
    save({ layoutName, tileTheme, tiles: game.tiles, gameStatus, shufflesLeft, elapsed: timer.seconds })
  }, [layoutName, tileTheme, game.tiles, gameStatus, shufflesLeft, timer.seconds, save])

  const remaining = game.tiles.filter(t => !t.removed).length
  const matches = useMemo(() => findAllMatches(game.tiles), [game.tiles])

  const handleTileClick = useCallback((id: number) => {
    if (gameStatus !== 'playing') return
    music.init()
    sfx.init()
    music.start()
    if (!timer.isRunning) timer.start()
    setHintPair(null)

    const tile = game.tiles.find(t => t.id === id)
    if (!tile || tile.removed || !isTileFree(tile, game.tiles)) return

    if (selectedId === null) {
      sfx.play('select')
      setSelectedId(id)
      return
    }

    if (selectedId === id) {
      setSelectedId(null)
      return
    }

    const selectedTile = game.tiles.find(t => t.id === selectedId)
    if (!selectedTile) { setSelectedId(null); return }

    if (canMatch(selectedTile, tile) && isTileFree(selectedTile, game.tiles)) {
      sfx.play('match')
      setHistory(prev => [...prev.slice(-30), game.tiles])
      const newTiles = removePair(game.tiles, selectedId, id)
      setGame({ ...game, tiles: newTiles })
      setSelectedId(null)

      if (isGameWon(newTiles)) {
        sfx.play('win')
        setGameStatus('won')
        timer.stop()
        onGameEnd?.('win', timer.seconds)
      } else if (isGameOver(newTiles)) {
        setGameStatus('lost')
        timer.stop()
        onGameEnd?.('loss', timer.seconds)
      }
    } else {
      // Select the new tile instead
      setSelectedId(id)
    }
  }, [game, selectedId, gameStatus, timer, onGameEnd])

  const handleShuffle = useCallback(() => {
    if (shufflesLeft <= 0) return
    const shuffled = shuffleTiles(game.tiles)
    setGame({ ...game, tiles: shuffled })
    setShuffle(s => s - 1)
    setSelectedId(null)
    setHintPair(null)
  }, [game, shufflesLeft])

  const handleHint = useCallback(() => {
    if (matches.length > 0) {
      setHintPair(matches[0])
      setSelectedId(null)
    }
  }, [matches])

  const handleUndo = useCallback(() => {
    if (history.length === 0) return
    setGame({ ...game, tiles: history[history.length - 1] })
    setHistory(h => h.slice(0, -1))
    setSelectedId(null)
    setHintPair(null)
    if (gameStatus !== 'playing') setGameStatus('playing')
  }, [history, game, gameStatus])

  const handleNewGame = useCallback((layout?: LayoutName) => {
    const l = layout ?? layoutName
    setLayoutName(l)
    setGame(createGame(LAYOUTS[l]))
    setSelectedId(null)
    setHintPair(null)
    setGameStatus('playing')
    setHistory([])
    setShuffle(3)
    timer.reset()
    music.start()
    clear()
  }, [layoutName, timer, music, clear])

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex space-x-1.5">
        {(['pyramid', 'turtle'] as LayoutName[]).map(l => (
          <button
            key={l}
            onClick={() => handleNewGame(l)}
            className={`px-2 py-1 rounded text-xs font-medium capitalize transition-colors ${
              layoutName === l ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
          >
            {l}
          </button>
        ))}
        <button
          onClick={() => setTileTheme(t => t === 'classic' ? 'kanji' : 'classic')}
          className="px-2 py-1 rounded text-xs font-medium bg-slate-700 text-slate-400 hover:bg-slate-600 transition-colors"
          title={`Switch to ${tileTheme === 'classic' ? 'Kanji' : 'Classic'} tiles`}
        >
          {tileTheme === 'classic' ? '漢' : '🀄'}
        </button>
      </div>
      <div className="flex items-center space-x-2">
        <span className="text-xs text-slate-400">{remaining} tiles</span>
        <button onClick={handleHint} className="p-1 hover:bg-slate-700 rounded transition-colors" title="Hint">
          <Lightbulb className="w-4 h-4 text-yellow-400" />
        </button>
        <button onClick={handleShuffle} disabled={shufflesLeft <= 0} className="p-1 hover:bg-slate-700 rounded disabled:opacity-40 transition-colors" title={`Shuffle (${shufflesLeft})`}>
          <Shuffle className="w-4 h-4 text-slate-400" />
        </button>
        <button onClick={handleUndo} disabled={history.length === 0} className="p-1 hover:bg-slate-700 rounded disabled:opacity-40 transition-colors" title="Undo">
          <Undo2 className="w-4 h-4 text-slate-400" />
        </button>
        <button onClick={() => handleNewGame()} className="p-1 hover:bg-slate-700 rounded transition-colors" title="New Game">
          <RotateCcw className="w-4 h-4 text-slate-400" />
        </button>
        <button
          onClick={() => setShowHelp(true)}
          className="p-1.5 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-white"
          title="How to Play"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Mahjong Solitaire" timer={timer.formatted} controls={controls}>
      <div className="relative flex flex-col items-center">
        <div className="relative bg-emerald-900/40 rounded-lg p-4 min-h-[400px] min-w-[300px] sm:min-w-[700px] overflow-auto">
          {game.tiles.filter(t => !t.removed).map(tile => (
            <MahjongTile
              key={tile.id}
              tile={tile}
              isFree={isTileFree(tile, game.tiles)}
              isSelected={selectedId === tile.id}
              isHinted={hintPair !== null && (hintPair[0] === tile.id || hintPair[1] === tile.id)}
              theme={tileTheme}
              onClick={handleTileClick}
            />
          ))}
        </div>

        <p className="text-xs text-slate-500 mt-3 hidden sm:block">
          Click two matching free tiles to remove them.
        </p>

        {gameStatus !== 'playing' && gameStatus !== 'idle' && !isMultiplayer && (
          <GameOverModal
            status={gameStatus}
            message={gameStatus === 'won' ? `Cleared in ${timer.formatted}` : 'No more moves available'}
            onPlayAgain={() => handleNewGame()}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
      {showHelp && <MahjongHelp onClose={() => setShowHelp(false)} />}
    </GameLayout>
  )
}

// ── Race wrapper (fastest to clear all tiles) ───────────────────────

function MahjongRaceWrapper({ roomId, difficulty: _difficulty, onLeave }: { roomId: string; difficulty?: string; onLeave?: () => void }) {
  const { opponentStatus, raceResult, opponentLevelUp, broadcastState, reportFinish, leaveRoom } = useRaceMode(roomId, 'best_score')
  const finishedRef = useRef(false)

  const handleGameEnd = useCallback((result: 'win' | 'loss' | 'draw', score?: number) => {
    if (finishedRef.current) return
    finishedRef.current = true
    reportFinish(result === 'draw' ? 'loss' : result, score)
  }, [reportFinish])

  return (
    <div className="relative">
      <RaceOverlay
        raceResult={raceResult}
        opponentScore={opponentStatus.score}
        opponentFinished={opponentStatus.finished}
        opponentLevelUp={opponentLevelUp}
        onDismiss={onLeave}
        onBackToLobby={onLeave}
        onLeaveGame={leaveRoom}
      />
      <MahjongSinglePlayer onGameEnd={handleGameEnd} onStateChange={broadcastState} isMultiplayer />
    </div>
  )
}

export default function Mahjong() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'mahjong',
        gameName: 'Mahjong Solitaire',
        modes: ['best_score'],
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: { best_score: 'Fastest to clear all tiles wins' },
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <MahjongSinglePlayer />}
      renderMultiplayer={(roomId, _players, _playerNames, _mode, roomConfig, onLeave) =>
        <MahjongRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
      }
    />
  )
}
