/**
 * Notification Context for order fill alerts — context + hooks only.
 * The provider (WebSocket connection, audio playback, visual toasts) lives in
 * NotificationProvider.tsx.
 */

import { createContext, useContext } from 'react'
import { ToastData } from '../components/shared/Toast'

export interface NotificationContextType {
  addToast: (toast: Omit<ToastData, 'id' | 'timestamp'>) => void
  dismissToast: (id: string) => void
  isConnected: boolean
  audioEnabled: boolean
  setAudioEnabled: (enabled: boolean) => void
  // When true, paper-trading order notifications are hidden while the active
  // account is a real (non-paper) account. See setActiveAccountIsPaper.
  suppressPaperWhenReal: boolean
  setSuppressPaperWhenReal: (enabled: boolean) => void
  // Bridge from AccountContext (which is a descendant provider): the active
  // account's paper status. null = unknown/none selected.
  setActiveAccountIsPaper: (isPaper: boolean | null) => void
}

export const NotificationContext = createContext<NotificationContextType | null>(null)

export function useNotifications() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotifications must be used within NotificationProvider')
  }
  return context
}

// Non-throwing variant for components that may render outside the provider
// (e.g. a bridge whose placement must never crash the whole app to a blank
// screen). Returns null when no provider is present.
export function useNotificationsOptional() {
  return useContext(NotificationContext)
}
