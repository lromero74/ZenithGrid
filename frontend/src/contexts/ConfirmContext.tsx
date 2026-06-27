/**
 * ConfirmContext — context + hook for the styled confirm dialog.
 * The provider lives in ConfirmProvider.tsx.
 * Usage: const confirm = useConfirm(); const ok = await confirm({ title, message })
 */

import { createContext, useContext } from 'react'

export interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'danger' | 'warning' | 'default'
}

export type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>

export const ConfirmContext = createContext<ConfirmFn | null>(null)

export function useConfirm(): ConfirmFn {
  const fn = useContext(ConfirmContext)
  if (!fn) throw new Error('useConfirm must be used within ConfirmProvider')
  return fn
}
