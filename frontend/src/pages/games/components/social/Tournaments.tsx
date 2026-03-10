/**
 * Tournaments panel — create, browse, join, and manage tournaments.
 *
 * Shows tournament list with status badges, a create form, detail view
 * with standings, and action buttons for join/leave/start/archive/delete.
 */

import { useState } from 'react'
import {
  Trophy, ChevronDown, ChevronUp, Plus, Play, LogOut, Archive,
  Trash2, Users, ArrowLeft, Crown,
} from 'lucide-react'
import { useAuth } from '../../../../contexts/AuthContext'
import { GAMES } from '../../constants'
import {
  useTournaments,
  useTournamentDetail,
  useTournamentStandings,
  useCreateTournament,
  useJoinTournament,
  useLeaveTournament,
  useStartTournament,
  useArchiveTournament,
  useVoteDeleteTournament,
} from '../../hooks/useTournaments'
import type { Tournament, TournamentStatus } from '../../hooks/useTournaments'

const STATUS_STYLES: Record<TournamentStatus, { bg: string; text: string }> = {
  pending:  { bg: 'bg-yellow-600/20', text: 'text-yellow-400' },
  active:   { bg: 'bg-green-600/20',  text: 'text-green-400' },
  finished: { bg: 'bg-blue-600/20',   text: 'text-blue-400' },
  archived: { bg: 'bg-slate-600/20',  text: 'text-slate-400' },
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// ----- Tournament List Item -----

function TournamentRow({ t, onSelect }: { t: Tournament; onSelect: (id: number) => void }) {
  const style = STATUS_STYLES[t.status] || STATUS_STYLES.pending
  return (
    <button
      onClick={() => onSelect(t.id)}
      className="w-full flex items-center justify-between py-2 px-2 rounded hover:bg-slate-700/30 text-left transition-colors"
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm text-slate-200 truncate">{t.name}</p>
        <p className="text-[10px] text-slate-500">
          {t.game_ids.length} game{t.game_ids.length !== 1 ? 's' : ''} &middot;{' '}
          by {t.creator_name} &middot; {formatDate(t.created_at)}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-2">
        <span className="flex items-center gap-1 text-[10px] text-slate-400">
          <Users className="w-3 h-3" />
          {t.player_count}
        </span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${style.bg} ${style.text}`}>
          {t.status}
        </span>
      </div>
    </button>
  )
}

// ----- Create Tournament Form -----

function CreateForm({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [selectedGames, setSelectedGames] = useState<string[]>([])
  const createTournament = useCreateTournament()

  const toggleGame = (id: string) => {
    setSelectedGames(prev =>
      prev.includes(id) ? prev.filter(g => g !== id) : [...prev, id]
    )
  }

  const handleSubmit = async () => {
    if (!name.trim() || selectedGames.length === 0) return
    try {
      await createTournament.mutateAsync({
        name: name.trim(),
        game_ids: selectedGames,
      })
      onClose()
    } catch {
      // error handled by mutation
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium text-slate-300">Create Tournament</h4>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs">Cancel</button>
      </div>

      {/* Name */}
      <input
        type="text"
        value={name}
        onChange={e => setName(e.target.value)}
        placeholder="Tournament name..."
        className="w-full bg-slate-900/50 border border-slate-600/50 rounded text-xs text-slate-200 py-1.5 px-2 placeholder:text-slate-500 focus:outline-none focus:border-blue-500/50"
      />

      {/* Game selection */}
      <div>
        <p className="text-[10px] text-slate-500 mb-1">Select games:</p>
        <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
          {GAMES.map(g => (
            <button
              key={g.id}
              onClick={() => toggleGame(g.id)}
              className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                selectedGames.includes(g.id)
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700/60 text-slate-400 hover:bg-slate-600'
              }`}
            >
              {g.name}
            </button>
          ))}
        </div>
      </div>

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!name.trim() || selectedGames.length === 0 || createTournament.isPending}
        className="w-full py-1.5 rounded text-xs font-medium bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {createTournament.isPending ? 'Creating...' : 'Create Tournament'}
      </button>
    </div>
  )
}

// ----- Tournament Detail View -----

function TournamentDetailView({ id, onBack }: { id: number; onBack: () => void }) {
  const { user } = useAuth()
  const { data: detail, isLoading } = useTournamentDetail(id)
  const { data: standings = [] } = useTournamentStandings(id)
  const joinTournament = useJoinTournament()
  const leaveTournament = useLeaveTournament()
  const startTournament = useStartTournament()
  const archiveTournament = useArchiveTournament()
  const voteDelete = useVoteDeleteTournament()

  if (isLoading || !detail) {
    return <p className="text-xs text-slate-500 py-2">Loading...</p>
  }

  const style = STATUS_STYLES[detail.status] || STATUS_STYLES.pending
  const gameNames = detail.game_ids
    .map(gid => GAMES.find(g => g.id === gid)?.name ?? gid)
    .join(', ')

  const isCreator = user?.id === detail.creator_id
  const isParticipant = detail.players.some(p => p.user_id === user?.id)

  return (
    <div className="space-y-2">
      {/* Back + title */}
      <div className="flex items-center gap-2">
        <button onClick={onBack} className="p-0.5 text-slate-400 hover:text-slate-200">
          <ArrowLeft className="w-3.5 h-3.5" />
        </button>
        <h4 className="text-sm font-medium text-slate-200 truncate flex-1">{detail.name}</h4>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${style.bg} ${style.text}`}>
          {detail.status}
        </span>
      </div>

      {/* Info */}
      <div className="text-[10px] text-slate-500 space-y-0.5">
        <p>Games: {gameNames}</p>
        <p>Created by {detail.creator_name} on {formatDate(detail.created_at)}</p>
      </div>

      {/* Players */}
      <div>
        <p className="text-[10px] text-slate-500 mb-1">
          Players ({detail.players.length}):
        </p>
        <div className="space-y-0.5 max-h-20 overflow-y-auto">
          {detail.players.map(p => (
            <div key={p.user_id} className="flex items-center gap-1 py-0.5 px-1">
              {p.user_id === detail.creator_id && <Crown className="w-3 h-3 text-yellow-500" />}
              <span className="text-xs text-slate-300">
                {p.display_name}
                {p.user_id === user?.id && <span className="text-slate-500 ml-1">(you)</span>}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Standings */}
      {standings.length > 0 && (
        <div>
          <p className="text-[10px] text-slate-500 mb-1">Standings:</p>
          <div className="space-y-0.5 max-h-32 overflow-y-auto">
            {standings.map(s => (
              <div key={s.user_id} className="flex items-center justify-between py-1 px-1.5 rounded bg-slate-700/20">
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-bold w-4 text-right ${
                    s.rank === 1 ? 'text-yellow-400' : s.rank === 2 ? 'text-slate-300' : s.rank === 3 ? 'text-amber-600' : 'text-slate-500'
                  }`}>
                    #{s.rank}
                  </span>
                  <span className="text-xs text-slate-200">{s.display_name}</span>
                </div>
                <div className="flex items-center gap-2 text-[10px]">
                  <span className="text-slate-400 w-10 text-right">{s.total_score} pts</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action buttons — role-gated */}
      <div className="flex flex-wrap gap-1.5 pt-1 border-t border-slate-700/50">
        {detail.status === 'pending' && (
          <>
            {!isParticipant && (
              <button
                onClick={() => joinTournament.mutate(id)}
                disabled={joinTournament.isPending}
                className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-green-600/20 text-green-400 hover:bg-green-600/40 disabled:opacity-40"
              >
                <Plus className="w-3 h-3" /> Join
              </button>
            )}
            {isParticipant && !isCreator && (
              <button
                onClick={() => leaveTournament.mutate(id)}
                disabled={leaveTournament.isPending}
                className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-red-600/20 text-red-400 hover:bg-red-600/40 disabled:opacity-40"
              >
                <LogOut className="w-3 h-3" /> Leave
              </button>
            )}
            {isCreator && (
              <button
                onClick={() => startTournament.mutate(id)}
                disabled={startTournament.isPending}
                className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-blue-600/20 text-blue-400 hover:bg-blue-600/40 disabled:opacity-40"
              >
                <Play className="w-3 h-3" /> Start
              </button>
            )}
          </>
        )}
        {isCreator && (detail.status === 'finished' || detail.status === 'active') && (
          <button
            onClick={() => archiveTournament.mutate(id)}
            disabled={archiveTournament.isPending}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-slate-600/20 text-slate-400 hover:bg-slate-600/40 disabled:opacity-40"
          >
            <Archive className="w-3 h-3" /> Archive
          </button>
        )}
        {isParticipant && (
          <button
            onClick={() => voteDelete.mutate(id)}
            disabled={voteDelete.isPending}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-red-600/20 text-red-400 hover:bg-red-600/40 disabled:opacity-40"
          >
            <Trash2 className="w-3 h-3" /> Vote Delete
          </button>
        )}
      </div>
    </div>
  )
}

// ----- Main Tournaments Panel -----

export function Tournaments() {
  const [isOpen, setIsOpen] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const { data: rawTournaments, isLoading } = useTournaments()
  const tournaments = Array.isArray(rawTournaments) ? rawTournaments : []

  const activeTournaments = tournaments.filter(t => t.status === 'active' || t.status === 'pending')

  return (
    <div className="bg-slate-800/60 rounded-lg border border-slate-700/50">
      {/* Toggle header */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-700/30 rounded-lg transition-colors"
      >
        <div className="flex items-center gap-2">
          <Trophy className="w-4 h-4 text-yellow-400" />
          <span className="text-sm font-medium text-slate-200">Tournaments</span>
          {activeTournaments.length > 0 && (
            <span className="bg-yellow-500 text-white text-xs px-1.5 py-0.5 rounded-full">
              {activeTournaments.length}
            </span>
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
          {selectedId !== null ? (
            <TournamentDetailView
              id={selectedId}
              onBack={() => setSelectedId(null)}
            />
          ) : showCreate ? (
            <CreateForm onClose={() => setShowCreate(false)} />
          ) : (
            <>
              {/* Create button */}
              <button
                onClick={() => setShowCreate(true)}
                className="w-full flex items-center justify-center gap-1 py-1.5 mb-2 rounded text-xs bg-blue-600/20 text-blue-400 hover:bg-blue-600/40 transition-colors"
              >
                <Plus className="w-3 h-3" /> New Tournament
              </button>

              {/* Tournament list */}
              {isLoading ? (
                <p className="text-xs text-slate-500 py-2">Loading...</p>
              ) : tournaments.length === 0 ? (
                <p className="text-xs text-slate-500 py-2">No tournaments yet. Create one!</p>
              ) : (
                <div className="space-y-0.5 max-h-48 overflow-y-auto">
                  {tournaments.map(t => (
                    <TournamentRow key={t.id} t={t} onSelect={setSelectedId} />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
