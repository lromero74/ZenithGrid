import { X } from 'lucide-react'

interface NotesModalProps {
  isOpen: boolean
  isProcessing: boolean
  notesText: string
  onNotesChange: (text: string) => void
  onClose: () => void
  onSave: () => void
}

export const NotesModal = ({
  isOpen,
  isProcessing,
  notesText,
  onNotesChange,
  onClose,
  onSave,
}: NotesModalProps) => {
  if (!isOpen) return null

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Save on Cmd+Enter or Ctrl+Enter
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      onSave()
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-lg w-full max-w-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold text-white">Edit Note</h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        <div className="mb-4">
          <textarea
            value={notesText}
            onChange={(e) => onNotesChange(e.target.value)}
            onKeyDown={handleKeyDown}
            className="w-full bg-slate-700 border border-slate-600 rounded px-2 sm:px-4 py-2 sm:py-3 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[120px] resize-y"
            placeholder="Add a note for this position..."
            autoFocus
            disabled={isProcessing}
          />
          <p className="text-xs text-slate-400 mt-2">Cmd + Enter to save</p>
        </div>

        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors"
            disabled={isProcessing}
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
            disabled={isProcessing}
          >
            <span>✓</span> Save
          </button>
        </div>
      </div>
    </div>
  )
}
