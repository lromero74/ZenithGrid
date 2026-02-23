/**
 * ConfirmContext — styled confirm dialog that replaces native window.confirm().
 * Usage: const confirm = useConfirm(); const ok = await confirm({ title, message })
 */

import { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { AlertTriangle, X } from 'lucide-react'

export interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'danger' | 'warning' | 'default'
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>

const ConfirmContext = createContext<ConfirmFn | null>(null)

export function useConfirm(): ConfirmFn {
  const fn = useContext(ConfirmContext)
  if (!fn) throw new Error('useConfirm must be used within ConfirmProvider')
  return fn
}

interface ConfirmState {
  options: ConfirmOptions
  resolve: (value: boolean) => void
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConfirmState | null>(null)

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({ options, resolve })
    })
  }, [])

  const handleConfirm = () => {
    state?.resolve(true)
    setState(null)
  }

  const handleCancel = () => {
    state?.resolve(false)
    setState(null)
  }

  const variant = state?.options.variant || 'default'
  const confirmLabel = state?.options.confirmLabel || 'Confirm'
  const cancelLabel = state?.options.cancelLabel || 'Cancel'

  const confirmBtnClass = variant === 'danger'
    ? 'bg-red-600 hover:bg-red-700'
    : variant === 'warning'
    ? 'bg-amber-600 hover:bg-amber-700'
    : 'bg-blue-600 hover:bg-blue-700'

  const titleColor = variant === 'danger'
    ? 'text-red-400'
    : variant === 'warning'
    ? 'text-amber-400'
    : 'text-white'

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[60] p-4">
          <div className="w-full max-w-md bg-slate-800 rounded-lg shadow-2xl border border-slate-700">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div className="flex items-center space-x-2">
                {variant !== 'default' && (
                  <AlertTriangle className={`w-5 h-5 ${variant === 'danger' ? 'text-red-400' : 'text-amber-400'}`} />
                )}
                <h3 className={`text-lg font-semibold ${titleColor}`}>{state.options.title}</h3>
              </div>
              <button
                onClick={handleCancel}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="p-4">
              <p className="text-slate-300 text-sm whitespace-pre-line">{state.options.message}</p>
            </div>

            {/* Footer */}
            <div className="flex justify-end space-x-3 p-4 border-t border-slate-700">
              <button
                onClick={handleCancel}
                className="px-4 py-2 text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
              >
                {cancelLabel}
              </button>
              <button
                onClick={handleConfirm}
                className={`px-4 py-2 ${confirmBtnClass} text-white font-medium rounded-lg transition-colors`}
              >
                {confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}
