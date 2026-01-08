interface CloseConfirmModalProps {
  isOpen: boolean
  isProcessing: boolean
  onClose: () => void
  onConfirm: () => void
}

export const CloseConfirmModal = ({
  isOpen,
  isProcessing,
  onClose,
  onConfirm,
}: CloseConfirmModalProps) => {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-lg w-full max-w-md p-6">
        <h2 className="text-xl font-bold mb-4 text-red-400 flex items-center gap-2">
          <span>⚠️</span> Close Position at Market Price
        </h2>

        <p className="text-slate-300 mb-4">
          This will immediately sell the entire position at the current market price.
        </p>

        <p className="text-slate-400 text-sm mb-6">
          <strong>Warning:</strong> This action cannot be undone. The position will be closed and profits/losses will be realized.
        </p>

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            disabled={isProcessing}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg font-semibold transition-colors"
            disabled={isProcessing}
          >
            {isProcessing ? 'Closing...' : 'Close Position'}
          </button>
        </div>
      </div>
    </div>
  )
}
