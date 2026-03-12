/**
 * Games Hub — landing page that displays all available games in a card grid.
 *
 * Features search by name, category filtering, and group-by with section headings
 * (category, difficulty, A-Z, recently played).
 */

import { useState, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, LayoutList, Swords, Flag, Shield, TrendingUp, Users, LogIn } from 'lucide-react'
import { GAMES, GAME_CATEGORIES, CARD_SUBCATEGORIES, GROUP_OPTIONS, GAME_ICONS } from '../constants'
import { useGameScores } from '../hooks/useGameScores'
import { useRecentlyPlayed } from '../hooks/useRecentlyPlayed'
import { useOnlineFriends, type OnlineFriendInfo } from '../hooks/useFriends'
import { gameSocket } from '../../../services/gameSocket'
import { groupGames } from '../groupGames'
import { GameCard } from './GameCard'
import type { GameCategory, GameGroupOption, GameInfo, MultiplayerMode } from '../types'

const GAME_MAP = Object.fromEntries(GAMES.map(g => [g.id, g]))

/** Friends' open lobbies — shown at the top of the Games hub. */
function FriendsLobbies({ navigate }: { navigate: ReturnType<typeof useNavigate> }) {
  const { data: onlineFriends = [] } = useOnlineFriends()
  const lobbies = useMemo(
    () => onlineFriends.filter((f): f is OnlineFriendInfo & { game_id: string; room_id: string } =>
      f.room_status === 'waiting' && !!f.game_id && !!f.room_id
    ),
    [onlineFriends],
  )

  if (lobbies.length === 0) return null

  const handleJoin = (friend: typeof lobbies[0]) => {
    gameSocket.captureJoinResult()
    gameSocket.send({ type: 'game:join_friend', friendUserId: friend.id })
    const game = GAME_MAP[friend.game_id]
    if (game) navigate(game.path, { state: { joiningFriend: true } })
  }

  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <Users className="w-4 h-4 text-green-400" />
        <h2 className="text-sm font-semibold text-green-300">Friends' Lobbies</h2>
        <div className="flex-1 border-t border-green-800/40" />
      </div>
      <div className="flex flex-wrap gap-3">
        {lobbies.map(lobby => {
          const game = GAME_MAP[lobby.game_id]
          const Icon = game ? GAME_ICONS[game.icon] : null
          return (
            <button
              key={lobby.room_id}
              onClick={() => handleJoin(lobby)}
              className="flex items-center gap-3 px-4 py-3 bg-slate-800 hover:bg-slate-700 border border-green-600/30 hover:border-green-500/50 rounded-xl transition-all group"
            >
              {Icon && <Icon className="w-6 h-6 text-green-400 group-hover:text-green-300 shrink-0" />}
              <div className="text-left">
                <div className="text-sm font-medium text-white">{game?.name ?? lobby.game_id}</div>
                <div className="text-xs text-slate-400">
                  {lobby.display_name ?? `Player ${lobby.id}`}
                  <span className="text-slate-500"> &middot; </span>
                  {lobby.player_count ?? 1}/{lobby.max_players ?? 2} players
                </div>
              </div>
              <LogIn className="w-4 h-4 text-green-400 group-hover:text-green-300 ml-2 shrink-0" />
            </button>
          )
        })}
      </div>
    </div>
  )
}

const LAST_GAME_KEY = 'zenith-games-last-path'
const CATEGORY_KEY = 'zenith-games-category'
const SUBCATEGORY_KEY = 'zenith-games-subcategory'
const GROUP_KEY = 'zenith-games-group'

/** Store the current game path so we can resume it later. */
export function setLastGamePath(path: string): void {
  try { sessionStorage.setItem(LAST_GAME_KEY, path) } catch { /* ignore */ }
}

/** Clear the stored game path (used when explicitly going back to hub). */
export function clearLastGamePath(): void {
  try { sessionStorage.removeItem(LAST_GAME_KEY) } catch { /* ignore */ }
}

export function GameHub() {
  const navigate = useNavigate()

  // Auto-navigate to last-played game if returning from another page
  useEffect(() => {
    try {
      const lastPath = sessionStorage.getItem(LAST_GAME_KEY)
      if (lastPath) {
        navigate(lastPath, { replace: true })
      }
    } catch { /* ignore */ }
  }, [navigate])
  const { getHighScore } = useGameScores()
  const { markPlayed, getRecentMap } = useRecentlyPlayed()
  const [activeCategory, setActiveCategoryState] = useState<'all' | GameCategory>(() => {
    try {
      const saved = sessionStorage.getItem(CATEGORY_KEY)
      if (saved) return saved as 'all' | GameCategory
    } catch { /* ignore */ }
    return 'all'
  })
  const [activeSubcategory, setActiveSubcategoryState] = useState<string>(() => {
    try {
      const saved = sessionStorage.getItem(SUBCATEGORY_KEY)
      if (saved) return saved
    } catch { /* ignore */ }
    return 'all'
  })
  const setActiveCategory = (cat: 'all' | GameCategory) => {
    setActiveCategoryState(cat)
    try { sessionStorage.setItem(CATEGORY_KEY, cat) } catch { /* ignore */ }
    if (cat !== 'cards') {
      setActiveSubcategoryState('all')
      try { sessionStorage.removeItem(SUBCATEGORY_KEY) } catch { /* ignore */ }
    }
  }
  const setActiveSubcategory = (sub: string) => {
    setActiveSubcategoryState(sub)
    try { sessionStorage.setItem(SUBCATEGORY_KEY, sub) } catch { /* ignore */ }
  }
  const [searchQuery, setSearchQuery] = useState('')
  const [groupOption, setGroupOption] = useState<GameGroupOption>(() => {
    try {
      const saved = sessionStorage.getItem(GROUP_KEY)
      if (saved) return saved as GameGroupOption
    } catch { /* ignore */ }
    return 'category'
  })
  const setGroupOptionPersisted = (opt: GameGroupOption) => {
    setGroupOption(opt)
    try { sessionStorage.setItem(GROUP_KEY, opt) } catch { /* ignore */ }
  }

  const [multiplayerFilter, setMultiplayerFilter] = useState<'all' | MultiplayerMode>('all')

  const displayedGroups = useMemo(() => {
    let games = GAMES as GameInfo[]

    // Filter by category
    if (activeCategory !== 'all') {
      games = games.filter(g => g.category === activeCategory)
    }

    // Filter by card subcategory
    if (activeCategory === 'cards' && activeSubcategory !== 'all') {
      games = games.filter(g => g.subcategory === activeSubcategory)
    }

    // Filter by multiplayer mode
    if (multiplayerFilter !== 'all') {
      games = games.filter(g => g.multiplayer?.includes(multiplayerFilter))
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      games = games.filter(g => g.name.toLowerCase().includes(q))
    }

    // Group
    return groupGames(games, groupOption, {
      recentlyPlayed: getRecentMap(),
      isCardsView: activeCategory === 'cards',
    })
  }, [activeCategory, activeSubcategory, multiplayerFilter, searchQuery, groupOption, getRecentMap])

  const totalGames = displayedGroups.reduce((sum, g) =>
    sum + g.games.length + (g.subgroups?.reduce((s, sg) => s + sg.games.length, 0) ?? 0), 0
  )

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-white">Games</h1>
        <p className="text-slate-400 text-sm hidden sm:block">
          Take a break between trades
        </p>
      </div>

      {/* Search bar */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          type="text"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="Search games..."
          className="w-full pl-9 pr-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
        />
      </div>

      {/* Category pills + Group By dropdown */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6 gap-2 sm:gap-3">
        <div className="flex flex-wrap gap-2">
          {GAME_CATEGORIES.map(cat => (
            <button
              key={cat.value}
              onClick={() => setActiveCategory(cat.value as 'all' | GameCategory)}
              className={`px-3 py-1 rounded-full text-sm whitespace-nowrap transition-colors ${
                activeCategory === cat.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-slate-300'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        <div className="flex items-center space-x-1.5 shrink-0">
          <LayoutList className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={groupOption}
            onChange={e => setGroupOptionPersisted(e.target.value as GameGroupOption)}
            className="bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-300 pl-1.5 pr-1 py-1 focus:outline-none focus:border-blue-500 transition-colors cursor-pointer"
          >
            {GROUP_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Multiplayer filter pills */}
      <div className="flex flex-wrap gap-2 mb-4 -mt-3">
        {([
          { value: 'all' as const, label: 'Any Mode', icon: null },
          { value: 'vs' as const, label: 'VS', icon: Swords },
          { value: 'first_to_win' as const, label: 'First to Win', icon: Flag },
          { value: 'survival' as const, label: 'Survival', icon: Shield },
          { value: 'best_score' as const, label: 'Best Score', icon: TrendingUp },
        ]).map(opt => (
          <button
            key={opt.value}
            onClick={() => setMultiplayerFilter(opt.value)}
            className={`flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs whitespace-nowrap transition-colors ${
              multiplayerFilter === opt.value
                ? 'bg-purple-600 text-white'
                : 'bg-slate-700/60 text-slate-400 hover:bg-slate-600 hover:text-slate-300'
            }`}
          >
            {opt.icon && <opt.icon className="w-3 h-3" />}
            {opt.label}
          </button>
        ))}
      </div>

      {/* Card subcategory pills */}
      {activeCategory === 'cards' && (
        <div className="flex flex-wrap gap-2 mb-4 -mt-3">
          {CARD_SUBCATEGORIES.map(sub => (
            <button
              key={sub.value}
              onClick={() => setActiveSubcategory(sub.value)}
              className={`px-2.5 py-0.5 rounded-full text-xs whitespace-nowrap transition-colors ${
                activeSubcategory === sub.value
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-700/60 text-slate-400 hover:bg-slate-600 hover:text-slate-300'
              }`}
            >
              {sub.label}
            </button>
          ))}
        </div>
      )}

      {/* Friends' open lobbies */}
      <FriendsLobbies navigate={navigate} />

      {/* Grouped game cards */}
      {displayedGroups.map(group => (
        <div key={group.label || '__default'}>
          {group.label && (
            <div className="flex items-center gap-3 mb-3 mt-6 first:mt-0">
              <h2 className="text-sm font-semibold text-slate-300">{group.label}</h2>
              <span className="text-xs text-slate-500">
                ({group.games.length + (group.subgroups?.reduce((s, sg) => s + sg.games.length, 0) ?? 0)})
              </span>
              <div className="flex-1 border-t border-slate-700/50" />
            </div>
          )}
          {group.games.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {group.games.map(game => (
                <GameCard
                  key={game.id}
                  game={game}
                  highScore={getHighScore(game.id)}
                  onPlay={() => markPlayed(game.id)}
                />
              ))}
            </div>
          )}
          {group.subgroups?.map(sub => (
            <div key={sub.label} className="ml-3">
              <div className="flex items-center gap-2 mb-2 mt-4">
                <h3 className="text-xs font-medium text-slate-400">{sub.label}</h3>
                <span className="text-xs text-slate-600">({sub.games.length})</span>
                <div className="flex-1 border-t border-slate-700/30" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {sub.games.map(game => (
                  <GameCard
                    key={game.id}
                    game={game}
                    highScore={getHighScore(game.id)}
                    onPlay={() => markPlayed(game.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}

      {totalGames === 0 && (
        <p className="text-slate-500 text-center py-8">
          {searchQuery.trim() ? 'No games match your search.' : 'No games in this category yet.'}
        </p>
      )}
    </div>
  )
}
