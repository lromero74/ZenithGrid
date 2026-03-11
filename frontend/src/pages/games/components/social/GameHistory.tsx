/**
 * Game History panel — shows past game results with filtering and pagination.
 *
 * Displays game name, date, result (win/loss/draw), score, and opponent names.
 * Includes a game filter dropdown and pagination controls.
 */

import { useState } from 'react'
import {
  History, ChevronDown, ChevronUp, ChevronLeft, ChevronRight,
  Trophy, X as XIcon, Minus, Filter,
} from 'lucide-react'
import { GAMES } from '../../constants'
import { useGameHistory } from '../../hooks/useGameHistory'
import type { GameHistoryItem } from '../../hooks/useGameHistory'

const RESULT_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  win:  { bg: 'bg-green-600/20', text: 'text-green-400', label: 'Win' },
  loss: { bg: 'bg-red-600/20',   text: 'text-red-400',   label: 'Loss' },
  draw: { bg: 'bg-yellow-600/20', text: 'text-yellow-400', label: 'Draw' },
}

const RESULT_ICONS: Record<string, typeof Trophy> = {
  win: Trophy,
  loss: XIcon,
  draw: Minus,
}

function getGameName(gameId: string): string {
  return GAMES.find(g => g.id === gameId)?.name ?? gameId
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return ''
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s > 0 ? `${m}m ${s}s` : `${m}m`
}

function GameHistoryRow({ item }: { item: GameHistoryItem }) {
  const style = RESULT_STYLES[item.result] || RESULT_STYLES.draw
  const ResultIcon = RESULT_ICONS[item.result] || Minus

  return (
    <div className="flex items-center justify-between py-2 px-2 rounded hover:bg-slate-700/30">
      <div className="flex items-center gap-3 min-w-0 flex-1">
        {/* Result badge */}
        <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${style.bg} ${style.text}`}>
          <ResultIcon className="w-3 h-3" />
          {style.label}
        </span>

        {/* Game name + opponents */}
        <div className="min-w-0">
          <p className="text-sm text-slate-200 truncate">{getGameName(item.game_id)}</p>
          {item.opponent_names.length > 0 && (
            <p className="text-[11px] text-slate-500 truncate">
              vs {item.opponent_names.join(', ')}
            </p>
          )}
        </div>
      </div>

      {/* Score + date */}
      <div className="flex items-center gap-3 shrink-0">
        {item.score !== null && (
          <span className="text-xs text-slate-400">{item.score.toLocaleString()}</span>
        )}
        {item.duration_seconds !== null && (
          <span className="text-[10px] text-slate-500">{formatDuration(item.duration_seconds)}</span>
        )}
        <span className="text-[10px] text-slate-500 w-20 text-right">{formatDate(item.finished_at)}</span>
      </div>
    </div>
  )
}

export function GameHistory(props: { defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(props.defaultOpen ?? false)
  const [gameFilter, setGameFilter] = useState<string>('')
  const [page, setPage] = useState(1)
  const pageSize = 15

  const { data, isLoading } = useGameHistory(gameFilter || undefined, page, pageSize)

  const items = data?.items ?? []
  const totalPages = data?.total_pages ?? 1
  const total = data?.total ?? 0

  return (
    <div className="bg-slate-800/60 rounded-lg border border-slate-700/50">
      {/* Toggle header */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-700/30 rounded-lg transition-colors"
      >
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-purple-400" />
          <span className="text-sm font-medium text-slate-200">Game History</span>
          {total > 0 && (
            <span className="text-xs text-slate-500">({total})</span>
          )}
        </div>
        {isOpen ? (
          <ChevronUp className="w-4 h-4 text-slate-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-400" />
        )}
      </button>

      {isOpen && (
        <div className="px-3 pb-3">
          {/* Filter dropdown */}
          <div className="flex items-center gap-2 mb-2">
            <Filter className="w-3 h-3 text-slate-500" />
            <select
              value={gameFilter}
              onChange={e => { setGameFilter(e.target.value); setPage(1) }}
              className="flex-1 bg-slate-900/50 border border-slate-600/50 rounded text-xs text-slate-300 py-1 px-2 focus:outline-none focus:border-blue-500/50"
            >
              <option value="">All Games</option>
              {GAMES.map(g => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </div>

          {/* Results list */}
          {isLoading ? (
            <p className="text-xs text-slate-500 py-2">Loading...</p>
          ) : items.length === 0 ? (
            <p className="text-xs text-slate-500 py-2">No game history yet. Play some games!</p>
          ) : (
            <div className="space-y-0.5 max-h-64 overflow-y-auto">
              {items.map(item => (
                <GameHistoryRow key={item.id} item={item} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-700/50">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1 text-slate-400 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <span className="text-[10px] text-slate-500">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1 text-slate-400 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
