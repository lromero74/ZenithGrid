/**
 * NewChatDialog — create a new DM or group chat.
 *
 * Shows DM/Group mode toggle, friend selection, and group name input.
 */

import { useState } from 'react'
import { useFriends, } from '../../hooks/useFriends'
import { useCreateChannel } from '../../hooks/useChat'

export function NewChatDialog({ onClose, onCreated }: {
  onClose: () => void
  onCreated: (channelId: number) => void
}) {
  const [mode, setMode] = useState<'dm' | 'group'>('dm')
  const [groupName, setGroupName] = useState('')
  const [selectedFriends, setSelectedFriends] = useState<number[]>([])
  const { data: friends = [] } = useFriends()
  const createChannel = useCreateChannel()

  const toggleFriend = (id: number) => {
    setSelectedFriends(prev =>
      prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
    )
  }

  const handleCreate = async () => {
    try {
      let result
      if (mode === 'dm') {
        if (selectedFriends.length !== 1) return
        result = await createChannel.mutateAsync({
          type: 'dm',
          friend_id: selectedFriends[0],
        })
      } else {
        if (!groupName.trim()) return
        result = await createChannel.mutateAsync({
          type: 'group',
          name: groupName.trim(),
          member_ids: selectedFriends,
        })
      }
      onCreated(result.id)
    } catch {
      // error handled by mutation
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-slate-200">New Chat</h4>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs">Cancel</button>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => { setMode('dm'); setSelectedFriends([]) }}
          className={`px-3 py-1 rounded text-xs ${mode === 'dm' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400'}`}
        >
          Direct Message
        </button>
        <button
          onClick={() => { setMode('group'); setSelectedFriends([]) }}
          className={`px-3 py-1 rounded text-xs ${mode === 'group' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400'}`}
        >
          Group Chat
        </button>
      </div>

      {mode === 'group' && (
        <input
          type="text"
          value={groupName}
          onChange={e => setGroupName(e.target.value)}
          placeholder="Group name..."
          maxLength={100}
          className="w-full bg-slate-900/50 border border-slate-600/50 rounded text-xs text-slate-200 py-1.5 px-2 placeholder:text-slate-500 focus:outline-none focus:border-blue-500/50"
        />
      )}

      <div>
        <p className="text-[10px] text-slate-500 mb-1">
          {mode === 'dm' ? 'Select a friend:' : 'Select friends:'}
        </p>
        <div className="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
          {friends.map((f: { id: number; display_name: string }) => (
            <button
              key={f.id}
              onClick={() => {
                if (mode === 'dm') setSelectedFriends([f.id])
                else toggleFriend(f.id)
              }}
              className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                selectedFriends.includes(f.id)
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700/60 text-slate-400 hover:bg-slate-600'
              }`}
            >
              {f.display_name}
            </button>
          ))}
          {friends.length === 0 && (
            <p className="text-[10px] text-slate-500">No friends yet. Add friends first!</p>
          )}
        </div>
      </div>

      <button
        onClick={handleCreate}
        disabled={
          createChannel.isPending ||
          (mode === 'dm' && selectedFriends.length !== 1) ||
          (mode === 'group' && !groupName.trim())
        }
        className="w-full py-1.5 rounded text-xs font-medium bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {createChannel.isPending ? 'Creating...' : mode === 'dm' ? 'Open Chat' : 'Create Group'}
      </button>
    </div>
  )
}
