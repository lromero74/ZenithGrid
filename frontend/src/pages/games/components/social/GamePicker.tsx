/**
 * GamePicker — searchable multiplayer game list popup for chat-to-game integration.
 *
 * Shown above the chat input bar. User picks a game → host creates a room
 * and invites all channel members.
 */

import { useState, useRef, useEffect } from 'react'
import { Search } from 'lucide-react'
import { GAMES, GAME_ICONS } from '../../constants'
import type { GameInfo, MultiplayerMode } from '../../types'

const MODE_LABELS: Record<MultiplayerMode, { label: string; color: string }> = {
  vs: { label: 'VS', color: 'text-purple-400 bg-purple-900/30' },
  first_to_win: { label: 'FTW', color: 'text-cyan-400 bg-cyan-900/30' },
  survival: { label: 'Surv', color: 'text-amber-400 bg-amber-900/30' },
  best_score: { label: 'Race', color: 'text-emerald-400 bg-emerald-900/30' },
}

const MULTIPLAYER_GAMES = GAMES.filter(g => g.multiplayer && g.multiplayer.length > 0)

interface GamePickerProps {
  memberCount: number
  onSelect: (game: GameInfo) => void
  onClose: () => void
}

export function GamePicker({ memberCount, onSelect, onClose }: GamePickerProps) {
  const [query, setQuery] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => { searchRef.current?.focus() }, [])

  const filtered = query
    ? MULTIPLAYER_GAMES.filter(g => g.name.toLowerCase().includes(query.toLowerCase()))
    : MULTIPLAYER_GAMES

  return (
    <div className="absolute bottom-full left-0 mb-1 bg-slate-800 border border-slate-600/50 rounded-lg shadow-xl z-20 w-72">
      {/* Search */}
      <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-slate-700/50">
        <Search className="w-3 h-3 text-slate-500 shrink-0" />
        <input
          ref={searchRef}
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search games..."
          className="flex-1 bg-transparent text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none"
        />
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs">
          esc
        </button>
      </div>

      {/* Game list */}
      <div className="max-h-60 overflow-y-auto py-1">
        {filtered.length === 0 && (
          <p className="text-center text-xs text-slate-500 py-4">No multiplayer games found</p>
        )}
        {filtered.map(game => {
          const Icon = GAME_ICONS[game.icon]
          return (
            <button
              key={game.id}
              onClick={() => onSelect(game)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-slate-700/50 transition-colors"
            >
              <div className="w-6 h-6 rounded bg-slate-700 flex items-center justify-center shrink-0">
                {Icon && <Icon className="w-3.5 h-3.5 text-slate-300" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-slate-200 font-medium truncate">{game.name}</p>
              </div>
              <div className="flex gap-0.5 shrink-0">
                {game.multiplayer?.map(mode => {
                  const ml = MODE_LABELS[mode]
                  return (
                    <span key={mode} className={`text-[9px] px-1 py-0.5 rounded ${ml.color}`}>
                      {ml.label}
                    </span>
                  )
                })}
              </div>
            </button>
          )
        })}
      </div>

      {/* Footer */}
      <div className="px-2 py-1 border-t border-slate-700/50">
        <span className="text-[8px] text-slate-600">
          {memberCount} player{memberCount !== 1 ? 's' : ''} will be invited
        </span>
      </div>
    </div>
  )
}
