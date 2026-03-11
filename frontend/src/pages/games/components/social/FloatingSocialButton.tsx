/**
 * Floating Social Button — accessible from any game page.
 *
 * Opens a slide-out panel with the FriendsPanel (always expanded).
 * Renders as a fixed button in the bottom-left corner.
 * Hidden for users without social:chat permission.
 */

import { useState } from 'react'
import { Users, X } from 'lucide-react'
import { FriendsPanel } from './FriendsPanel'
import { useHasPermission } from '../../../../hooks/usePermission'

export function FloatingSocialButton() {
  const [open, setOpen] = useState(false)
  const canChat = useHasPermission('social:chat')

  // Don't render for observers / users without social permission
  if (!canChat) return null

  return (
    <>
      {/* Toggle button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-4 left-4 z-40 flex items-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-full shadow-lg transition-colors"
          title="Friends & Social"
        >
          <Users className="w-4 h-4" />
          <span className="text-xs font-medium hidden sm:inline">Social</span>
        </button>
      )}

      {/* Slide-out panel */}
      {open && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/30"
            onClick={() => setOpen(false)}
          />
          <div className="fixed bottom-0 left-0 z-50 w-full sm:w-80 max-h-[70vh] bg-slate-900 border-t sm:border-r sm:border-t-0 border-slate-700 rounded-t-xl sm:rounded-tr-xl sm:rounded-tl-none shadow-2xl overflow-y-auto">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-blue-400" />
                <span className="text-sm font-medium text-white">Social</span>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-3">
              <FriendsPanel defaultOpen />
            </div>
          </div>
        </>
      )}
    </>
  )
}
