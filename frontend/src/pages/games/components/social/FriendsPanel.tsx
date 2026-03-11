/**
 * Friends Panel — sidebar/tab in the Games section for social features.
 *
 * Shows friends list, pending requests, user search, and blocked users.
 * Integrates with the friends API hooks.
 */

import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Users, UserPlus, Search, Shield, X, Check, Send,
  ChevronDown, ChevronUp, UserMinus, Ban, Unlock, Gamepad2,
} from 'lucide-react'
import {
  useFriends,
  useFriendRequests,
  useSentFriendRequests,
  useCancelSentRequest,
  useSendFriendRequest,
  useAcceptFriendRequest,
  useRejectFriendRequest,
  useRemoveFriend,
  useBlockUser,
  useUnblockUser,
  useBlockedUsers,
  useUserSearch,
  useOnlineFriends,
  type OnlineFriendInfo,
} from '../../hooks/useFriends'
import { GAMES } from '../../constants'
import { gameSocket } from '../../../../services/gameSocket'

type Tab = 'friends' | 'requests' | 'sent' | 'search' | 'blocked'

export function FriendsPanel(props: { defaultOpen?: boolean }) {
  const [activeTab, setActiveTab] = useState<Tab>('friends')
  const [isOpen, setIsOpen] = useState(props.defaultOpen ?? false)
  const { data: requests = [] } = useFriendRequests()
  const { data: onlineFriends = [] } = useOnlineFriends()
  const onlineIds = useMemo(() => onlineFriends.map(f => f.id), [onlineFriends])

  const tabs: { key: Tab; label: string; icon: typeof Users; badge?: number }[] = [
    { key: 'friends', label: 'Friends', icon: Users },
    { key: 'requests', label: 'Requests', icon: UserPlus, badge: requests.length },
    { key: 'sent', label: 'Sent', icon: Send },
    { key: 'search', label: 'Search', icon: Search },
    { key: 'blocked', label: 'Blocked', icon: Shield },
  ]

  return (
    <div className="bg-slate-800/60 rounded-lg border border-slate-700/50">
      {/* Toggle header */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-700/30 rounded-lg transition-colors"
      >
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-slate-200">Social</span>
          {onlineIds.length > 0 && (
            <span className="flex items-center gap-1 text-xs text-green-400">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
              {onlineIds.length}
            </span>
          )}
          {requests.length > 0 && (
            <span className="bg-blue-500 text-white text-xs px-1.5 py-0.5 rounded-full">
              {requests.length}
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
          {/* Tab buttons */}
          <div className="flex gap-1 mb-3">
            {tabs.map(t => (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={`flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors ${
                  activeTab === t.key
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
                }`}
              >
                <t.icon className="w-3 h-3" />
                {t.label}
                {t.badge ? (
                  <span className="bg-red-500 text-white text-[10px] px-1 rounded-full ml-0.5">
                    {t.badge}
                  </span>
                ) : null}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === 'friends' && <FriendsList />}
          {activeTab === 'requests' && <RequestsList />}
          {activeTab === 'sent' && <SentRequestsList />}
          {activeTab === 'search' && <UserSearchTab />}
          {activeTab === 'blocked' && <BlockedList />}
        </div>
      )}
    </div>
  )
}

// ----- Friends List -----

/** Lookup map: game ID → game name */
const GAME_NAME_MAP = Object.fromEntries(GAMES.map(g => [g.id, g.name]))

function FriendsList() {
  const { data: friends = [], isLoading } = useFriends()
  const { data: onlineFriends = [] } = useOnlineFriends()
  const removeFriend = useRemoveFriend()
  const blockUser = useBlockUser()
  const navigate = useNavigate()
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null)

  const onlineSet = new Set(onlineFriends.map(f => f.id))
  const onlineMap = useMemo(() => {
    const m = new Map<number, OnlineFriendInfo>()
    for (const f of onlineFriends) m.set(f.id, f)
    return m
  }, [onlineFriends])

  if (isLoading) return <p className="text-xs text-slate-500 py-2">Loading...</p>
  if (!friends.length) return <p className="text-xs text-slate-500 py-2">No friends yet. Search for players to add!</p>

  // Sort online friends first, then those in games
  const sorted = [...friends].sort((a, b) => {
    const aOnline = onlineSet.has(a.id) ? 0 : 1
    const bOnline = onlineSet.has(b.id) ? 0 : 1
    if (aOnline !== bOnline) return aOnline - bOnline
    // Among online friends, prioritize those in games
    const aInGame = onlineMap.get(a.id)?.game_id ? 0 : 1
    const bInGame = onlineMap.get(b.id)?.game_id ? 0 : 1
    return aInGame - bInGame
  })

  const handleJoinFriend = (friendId: number, gameId: string) => {
    gameSocket.send({ type: 'game:join_friend', friendUserId: friendId })
    // Navigate to the game page — the game:joined response will be caught by MultiplayerWrapper
    const game = GAMES.find(g => g.id === gameId)
    if (game) navigate(game.path)
  }

  return (
    <div className="space-y-1 max-h-48 overflow-y-auto">
      {sorted.map(f => {
        const info = onlineMap.get(f.id)
        const inGame = info?.game_id
        const gameName = inGame ? GAME_NAME_MAP[inGame] ?? inGame : null

        return (
          <div key={f.id} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-slate-700/30 group">
            <div className="flex items-center gap-2 min-w-0">
              <span className={`w-2 h-2 rounded-full shrink-0 ${
                onlineSet.has(f.id) ? 'bg-green-400' : 'bg-slate-600'
              }`} title={onlineSet.has(f.id) ? 'Online' : 'Offline'} />
              <div className="min-w-0">
                <span className="text-sm text-slate-200">{f.display_name}</span>
                {inGame && (
                  <p className="text-[10px] text-blue-400 truncate">
                    {info?.room_status === 'playing' ? 'Playing' : 'In lobby'}: {gameName}
                  </p>
                )}
              </div>
            </div>
            <div className="flex gap-1 items-center">
              {/* Join button — visible when friend is in a joinable game */}
              {inGame && (
                <button
                  onClick={() => handleJoinFriend(f.id, inGame)}
                  className="p-1 rounded bg-green-600/20 text-green-400 hover:bg-green-600/40"
                  title={`Join ${f.display_name}'s game`}
                >
                  <Gamepad2 className="w-3 h-3" />
                </button>
              )}
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                {confirmRemove === f.id ? (
                  <>
                    <button
                      onClick={() => { removeFriend.mutate(f.id); setConfirmRemove(null) }}
                      className="p-0.5 text-red-400 hover:text-red-300"
                      title="Confirm remove"
                    >
                      <Check className="w-3 h-3" />
                    </button>
                    <button
                      onClick={() => setConfirmRemove(null)}
                      className="p-0.5 text-slate-400 hover:text-slate-300"
                      title="Cancel"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => setConfirmRemove(f.id)}
                      className="p-0.5 text-slate-500 hover:text-red-400"
                      title="Remove friend"
                    >
                      <UserMinus className="w-3 h-3" />
                    </button>
                    <button
                      onClick={() => blockUser.mutate(f.id)}
                      className="p-0.5 text-slate-500 hover:text-red-400"
                      title="Block"
                    >
                      <Ban className="w-3 h-3" />
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ----- Friend Requests -----

function RequestsList() {
  const { data: requests = [], isLoading } = useFriendRequests()
  const accept = useAcceptFriendRequest()
  const reject = useRejectFriendRequest()

  if (isLoading) return <p className="text-xs text-slate-500 py-2">Loading...</p>
  if (!requests.length) return <p className="text-xs text-slate-500 py-2">No pending requests</p>

  return (
    <div className="space-y-1 max-h-48 overflow-y-auto">
      {requests.map(r => (
        <div key={r.id} className="flex items-center justify-between py-1.5 px-2 rounded bg-slate-700/20">
          <span className="text-sm text-slate-200">{r.from_display_name}</span>
          <div className="flex gap-1">
            <button
              onClick={() => accept.mutate(r.id)}
              className="p-1 rounded bg-green-600/20 text-green-400 hover:bg-green-600/40"
              title="Accept"
            >
              <Check className="w-3 h-3" />
            </button>
            <button
              onClick={() => reject.mutate(r.id)}
              className="p-1 rounded bg-red-600/20 text-red-400 hover:bg-red-600/40"
              title="Reject"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

// ----- Sent Requests -----

function SentRequestsList() {
  const { data: sentRequests = [], isLoading } = useSentFriendRequests()
  const cancelRequest = useCancelSentRequest()

  if (isLoading) return <p className="text-xs text-slate-500 py-2">Loading...</p>
  if (!sentRequests.length) return <p className="text-xs text-slate-500 py-2">No pending sent requests</p>

  return (
    <div className="space-y-1 max-h-48 overflow-y-auto">
      {sentRequests.map(r => (
        <div key={r.id} className="flex items-center justify-between py-1.5 px-2 rounded bg-slate-700/20">
          <div className="min-w-0">
            <span className="text-sm text-slate-200">{r.to_display_name}</span>
            <p className="text-[10px] text-slate-500">Pending</p>
          </div>
          <button
            onClick={() => cancelRequest.mutate(r.id)}
            className="p-1 rounded bg-red-600/20 text-red-400 hover:bg-red-600/40"
            title="Cancel request"
            disabled={cancelRequest.isPending}
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      ))}
    </div>
  )
}

// ----- User Search -----

function UserSearchTab() {
  const [query, setQuery] = useState('')
  const { data: results = [], isLoading } = useUserSearch(query)
  const sendRequest = useSendFriendRequest()
  const [sent, setSent] = useState<Set<string>>(new Set())

  const handleSend = async (displayName: string) => {
    try {
      await sendRequest.mutateAsync(displayName)
      setSent(prev => new Set(prev).add(displayName))
    } catch {
      // error handled by mutation
    }
  }

  return (
    <div>
      <div className="relative mb-2">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-500" />
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search by display name..."
          className="w-full pl-7 pr-2 py-1.5 bg-slate-900/50 border border-slate-600/50 rounded text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-blue-500/50"
        />
      </div>

      {isLoading && <p className="text-xs text-slate-500 py-1">Searching...</p>}

      <div className="space-y-1 max-h-48 overflow-y-auto">
        {results.map(u => (
          <div key={u.id} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-slate-700/30">
            <span className="text-sm text-slate-200">{u.display_name}</span>
            {sent.has(u.display_name) ? (
              <span className="text-[10px] text-green-400">Sent</span>
            ) : (
              <button
                onClick={() => handleSend(u.display_name)}
                className="p-1 rounded bg-blue-600/20 text-blue-400 hover:bg-blue-600/40"
                title="Send friend request"
                disabled={sendRequest.isPending}
              >
                <UserPlus className="w-3 h-3" />
              </button>
            )}
          </div>
        ))}
        {query && !isLoading && !results.length && (
          <p className="text-xs text-slate-500 py-1">No users found</p>
        )}
      </div>
    </div>
  )
}

// ----- Blocked Users -----

function BlockedList() {
  const { data: blocked = [], isLoading } = useBlockedUsers()
  const unblock = useUnblockUser()

  if (isLoading) return <p className="text-xs text-slate-500 py-2">Loading...</p>
  if (!blocked.length) return <p className="text-xs text-slate-500 py-2">No blocked users</p>

  return (
    <div className="space-y-1 max-h-48 overflow-y-auto">
      {blocked.map(b => (
        <div key={b.user_id} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-slate-700/30">
          <span className="text-sm text-slate-400">{b.display_name}</span>
          <button
            onClick={() => unblock.mutate(b.user_id)}
            className="p-1 rounded bg-slate-600/20 text-slate-400 hover:bg-slate-600/40 hover:text-slate-200"
            title="Unblock"
          >
            <Unlock className="w-3 h-3" />
          </button>
        </div>
      ))}
    </div>
  )
}
