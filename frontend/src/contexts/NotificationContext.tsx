/**
 * Notification Context for order fill alerts
 * Manages WebSocket connection, audio playback, and visual toasts
 */

import { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from 'react'
import { ToastContainer, ToastData, ToastType } from '../components/Toast'
import { useAudio, OrderFillType } from '../hooks/useAudio'

interface OrderFillEvent {
  type: 'order_fill'
  fill_type: 'base_order' | 'dca_order' | 'sell_order' | 'partial_fill'
  product_id: string
  base_amount: number
  quote_amount: number
  price: number
  profit?: number
  profit_percentage?: number
  position_id: number
  timestamp: string
}

interface WebSocketMessage {
  type: string
  [key: string]: unknown
}

interface NotificationContextType {
  addToast: (toast: Omit<ToastData, 'id' | 'timestamp'>) => void
  dismissToast: (id: string) => void
  isConnected: boolean
  audioEnabled: boolean
  setAudioEnabled: (enabled: boolean) => void
}

const NotificationContext = createContext<NotificationContextType | null>(null)

export function useNotifications() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotifications must be used within NotificationProvider')
  }
  return context
}

interface NotificationProviderProps {
  children: ReactNode
}

export function NotificationProvider({ children }: NotificationProviderProps) {
  const [toasts, setToasts] = useState<ToastData[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [audioEnabled, setAudioEnabledState] = useState(() => {
    const saved = localStorage.getItem('audio-notifications-enabled')
    return saved !== 'false' // Default to true
  })
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const { playOrderSound, setAudioEnabled: setAudioHookEnabled } = useAudio()

  // Add a new toast
  const addToast = useCallback((toast: Omit<ToastData, 'id' | 'timestamp'>) => {
    const newToast: ToastData = {
      ...toast,
      id: `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Date.now(),
    }
    setToasts((prev) => [...prev.slice(-4), newToast]) // Keep max 5 toasts
  }, [])

  // Dismiss a toast
  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // Toggle audio
  const setAudioEnabled = useCallback((enabled: boolean) => {
    setAudioEnabledState(enabled)
    setAudioHookEnabled(enabled)
    localStorage.setItem('audio-notifications-enabled', enabled ? 'true' : 'false')
  }, [setAudioHookEnabled])

  // Handle incoming order fill events
  const handleOrderFill = useCallback((event: OrderFillEvent) => {
    // Map fill type to toast type
    const toastType: ToastType = event.fill_type

    // Create appropriate title and message
    let title = ''
    let message = ''

    switch (event.fill_type) {
      case 'base_order':
        title = 'New Position Opened'
        message = `Bought ${event.product_id.split('-')[0]}`
        break
      case 'dca_order':
        title = 'DCA Order Filled'
        message = `Added to ${event.product_id.split('-')[0]} position`
        break
      case 'sell_order':
        title = 'Position Closed'
        message = event.profit !== undefined && event.profit > 0
          ? `Profit realized on ${event.product_id.split('-')[0]}!`
          : `Sold ${event.product_id.split('-')[0]}`
        break
      case 'partial_fill':
        title = 'Partial Fill'
        message = `${event.product_id.split('-')[0]} order partially filled`
        break
    }

    // Format amounts
    const baseSymbol = event.product_id.split('-')[0]
    const quoteSymbol = event.product_id.split('-')[1]
    const amount = `${event.base_amount.toFixed(8)} ${baseSymbol}`
    const price = `${event.price.toFixed(8)} ${quoteSymbol}`
    const profit = event.profit != null
      ? `${event.profit >= 0 ? '+' : ''}${event.profit.toFixed(8)} ${quoteSymbol} (${event.profit_percentage?.toFixed(2) ?? 0}%)`
      : undefined

    // Add visual toast
    addToast({
      type: toastType,
      title,
      message,
      productId: event.product_id,
      amount,
      price,
      profit,
    })

    // Play audio if enabled
    if (audioEnabled) {
      playOrderSound(event.fill_type as OrderFillType)
    }
  }, [addToast, audioEnabled, playOrderSound])

  // Connect to WebSocket
  const connect = useCallback(() => {
    // Determine WebSocket URL based on current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const token = localStorage.getItem('auth_access_token')
    const wsUrl = token ? `${protocol}//${host}/ws?token=${encodeURIComponent(token)}` : `${protocol}//${host}/ws`

    console.log('🔌 Connecting to notification WebSocket')

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('✅ Notification WebSocket connected')
        setIsConnected(true)
        // Clear any pending reconnect
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = null
        }
      }

      ws.onmessage = (event) => {
        try {
          const data: WebSocketMessage = JSON.parse(event.data)
          console.debug('📨 WebSocket message received, type:', data.type)

          if (data.type === 'order_fill') {
            handleOrderFill(data as unknown as OrderFillEvent)
          }
        } catch (error) {
          console.warn('Failed to parse WebSocket message:', error)
        }
      }

      ws.onerror = (error) => {
        console.warn('WebSocket error:', error)
      }

      ws.onclose = () => {
        console.log('🔌 WebSocket disconnected')
        setIsConnected(false)
        wsRef.current = null

        // Attempt to reconnect after 5 seconds
        reconnectTimeoutRef.current = window.setTimeout(() => {
          console.log('🔄 Attempting WebSocket reconnection...')
          connect()
        }, 5000)
      }
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
      // Attempt to reconnect after 5 seconds
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect()
      }, 5000)
    }
  }, [handleOrderFill])

  // Connect on mount
  useEffect(() => {
    connect()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [connect])

  const value: NotificationContextType = {
    addToast,
    dismissToast,
    isConnected,
    audioEnabled,
    setAudioEnabled,
  }

  return (
    <NotificationContext.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </NotificationContext.Provider>
  )
}
