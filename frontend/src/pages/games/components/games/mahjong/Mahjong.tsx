/**
 * Mahjong Solitaire — match pairs of free tiles to clear the board.
 *
 * Features: tile matching, shuffle, hint, undo, multiple layouts.
 */

import { useState, useCallback, useMemo } from 'react'
import { Shuffle, Lightbulb, Undo2, RotateCcw } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { useGameTimer } from '../../../hooks/useGameTimer'
import {
  createGame, canMatch, isTileFree, findAllMatches,
  removePair, shuffleTiles, isGameWon, isGameOver,
  type GameTile,
} from './mahjongEngine'
import { MahjongTile } from './MahjongTile'
import { TURTLE_LAYOUT, PYRAMID_LAYOUT } from './layouts'
import type { GameStatus } from '../../../types'

type LayoutName = 'turtle' | 'pyramid'
const LAYOUTS = { turtle: TURTLE_LAYOUT, pyramid: PYRAMID_LAYOUT }

export default function Mahjong() {
  const [layoutName, setLayoutName] = useState<LayoutName>('pyramid')
  const [game, setGame] = useState(() => createGame(LAYOUTS.pyramid))
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [hintPair, setHintPair] = useState<[number, number] | null>(null)
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [history, setHistory] = useState<GameTile[][]>([])
  const [shufflesLeft, setShuffle] = useState(3)
  const timer = useGameTimer()

  const remaining = game.tiles.filter(t => !t.removed).length
  const matches = useMemo(() => findAllMatches(game.tiles), [game.tiles])

  const handleTileClick = useCallback((id: number) => {
    if (gameStatus !== 'playing') return
    if (!timer.isRunning) timer.start()
    setHintPair(null)

    const tile = game.tiles.find(t => t.id === id)
    if (!tile || tile.removed || !isTileFree(tile, game.tiles)) return

    if (selectedId === null) {
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
      setHistory(prev => [...prev.slice(-30), game.tiles])
      const newTiles = removePair(game.tiles, selectedId, id)
      setGame({ ...game, tiles: newTiles })
      setSelectedId(null)

      if (isGameWon(newTiles)) {
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
  }, [layoutName, timer])

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
      </div>
    </div>
  )

  return (
    <GameLayout title="Mahjong Solitaire" timer={timer.formatted} controls={controls}>
      <div className="relative flex flex-col items-center">
        <div className="relative bg-emerald-900/40 rounded-lg p-4 min-h-[400px] min-w-[300px] sm:min-w-[500px] overflow-auto">
          {game.tiles.filter(t => !t.removed).map(tile => (
            <MahjongTile
              key={tile.id}
              tile={tile}
              isFree={isTileFree(tile, game.tiles)}
              isSelected={selectedId === tile.id}
              isHinted={hintPair !== null && (hintPair[0] === tile.id || hintPair[1] === tile.id)}
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
          />
        )}
      </div>
    </GameLayout>
  )
}
