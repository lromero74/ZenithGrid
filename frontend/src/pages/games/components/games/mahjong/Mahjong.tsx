/**
 * Mahjong Solitaire — match pairs of free tiles to clear the board.
 *
 * Features: tile matching, shuffle, hint, undo, multiple layouts.
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { Shuffle, Lightbulb, Undo2, RotateCcw } from 'lucide-react'
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

export default function Mahjong() {
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
      } else if (isGameOver(newTiles)) {
        setGameStatus('lost')
        timer.stop()
      }
    } else {
      // Select the new tile instead
      setSelectedId(id)
    }
  }, [game, selectedId, gameStatus, timer])

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

        {gameStatus !== 'playing' && gameStatus !== 'idle' && (
          <GameOverModal
            status={gameStatus}
            message={gameStatus === 'won' ? `Cleared in ${timer.formatted}` : 'No more moves available'}
            onPlayAgain={() => handleNewGame()}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
