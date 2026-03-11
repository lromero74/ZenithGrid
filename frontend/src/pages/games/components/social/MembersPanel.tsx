/**
 * MembersPanel — channel member list with role management.
 *
 * Shows online presence dots, admin promote/demote, remove member,
 * leave group, delete group (owner only), and add-member UI.
 */

import { useState } from 'react'
import { X, UserPlus, LogOut, Trash2 } from 'lucide-react'
import { useAuth } from '../../../../contexts/AuthContext'
import { useFriends, useOnlineFriends } from '../../hooks/useFriends'
import {
  useChannelMembers, useAddMember, useRemoveMember,
  useDeleteChannel, useUpdateMemberRole,
} from '../../hooks/useChat'
import type { ChatChannel } from '../../hooks/useChat'

export function MembersPanel({ channelId, channel, onClose, onDeleted }: {
  channelId: number
  channel: ChatChannel
  onClose: () => void
  onDeleted: () => void
}) {
  const { user } = useAuth()
  const { data: members = [] } = useChannelMembers(channelId)
  const { data: friends = [] } = useFriends()
  const { data: onlineFriends = [] } = useOnlineFriends()
  const addMember = useAddMember()
  const removeMember = useRemoveMember()
  const deleteChannel = useDeleteChannel()
  const updateRole = useUpdateMemberRole()
  const [showAdd, setShowAdd] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const isOwner = channel.my_role === 'owner'
  const canManage = isOwner || channel.my_role === 'admin'
  const memberIds = new Set(members.map(m => m.user_id))
  const onlineIds = new Set(onlineFriends.map((f: { id: number }) => f.id))

  const availableFriends = friends.filter((f: { id: number }) => !memberIds.has(f.id))

  const handleDelete = async () => {
    try {
      await deleteChannel.mutateAsync(channelId)
      onDeleted()
    } catch {
      // error handled by mutation
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium text-slate-300">Members ({members.length})</h4>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs">Close</button>
      </div>

      <div className="space-y-0.5 max-h-40 overflow-y-auto">
        {members.map(m => (
          <div key={m.user_id} className="flex items-center justify-between py-0.5 px-1">
            <div className="flex items-center gap-1">
              {/* Online presence dot */}
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                onlineIds.has(m.user_id) || m.user_id === user?.id
                  ? 'bg-green-500' : 'bg-slate-600'
              }`} />
              <span className="text-xs text-slate-300">{m.display_name}</span>
              {m.role !== 'member' && (
                <span className="text-[9px] text-slate-500">({m.role})</span>
              )}
              {m.user_id === user?.id && (
                <span className="text-[9px] text-slate-600">(you)</span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {isOwner && m.user_id !== user?.id && (
                <button
                  onClick={() => updateRole.mutate({
                    channelId,
                    userId: m.user_id,
                    role: m.role === 'admin' ? 'member' : 'admin',
                  })}
                  className={`text-[9px] px-1.5 py-0.5 rounded transition-colors ${
                    m.role === 'admin'
                      ? 'bg-yellow-600/20 text-yellow-400 hover:bg-yellow-600/40'
                      : 'bg-slate-700/40 text-slate-500 hover:bg-slate-600/40 hover:text-slate-300'
                  }`}
                  title={m.role === 'admin' ? 'Demote to member' : 'Promote to admin'}
                >
                  {m.role === 'admin' ? 'Admin' : 'Make Admin'}
                </button>
              )}
              {canManage && m.user_id !== user?.id && (
                <button
                  onClick={() => removeMember.mutate({ channelId, userId: m.user_id })}
                  className="text-slate-500 hover:text-red-400 p-0.5"
                  title="Remove"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {channel.type !== 'dm' && !isOwner && (
        <button
          onClick={() => removeMember.mutate({ channelId, userId: user!.id })}
          className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-red-600/20 text-red-400 hover:bg-red-600/40"
        >
          <LogOut className="w-3 h-3" /> Leave
        </button>
      )}

      {isOwner && channel.type !== 'dm' && (
        !confirmDelete ? (
          <button
            onClick={() => setConfirmDelete(true)}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-red-600/20 text-red-400 hover:bg-red-600/40"
          >
            <Trash2 className="w-3 h-3" /> Delete Group
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-red-400">Delete this group?</span>
            <button
              onClick={handleDelete}
              disabled={deleteChannel.isPending}
              className="px-2 py-0.5 rounded text-[10px] bg-red-600 text-white hover:bg-red-500 disabled:opacity-40"
            >
              {deleteChannel.isPending ? '...' : 'Yes'}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="px-2 py-0.5 rounded text-[10px] bg-slate-700 text-slate-300 hover:bg-slate-600"
            >
              No
            </button>
          </div>
        )
      )}

      {canManage && channel.type !== 'dm' && (
        <>
          {!showAdd ? (
            <button
              onClick={() => setShowAdd(true)}
              className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-green-600/20 text-green-400 hover:bg-green-600/40"
            >
              <UserPlus className="w-3 h-3" /> Add Member
            </button>
          ) : (
            <div className="space-y-1">
              <p className="text-[10px] text-slate-500">Add a friend:</p>
              <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto">
                {availableFriends.map((f: { id: number; display_name: string }) => (
                  <button
                    key={f.id}
                    onClick={() => addMember.mutate({ channelId, userId: f.id })}
                    className="px-2 py-0.5 rounded text-[10px] bg-slate-700/60 text-slate-400 hover:bg-slate-600"
                  >
                    {f.display_name}
                  </button>
                ))}
                {availableFriends.length === 0 && (
                  <p className="text-[10px] text-slate-600">All friends are already members</p>
                )}
              </div>
              <button onClick={() => setShowAdd(false)} className="text-[10px] text-slate-500 hover:text-slate-300">
                Cancel
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
