/**
 * Notification Context for order fill alerts
 * Manages WebSocket connection, audio playback, and visual toasts
 */

import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, ReactNode } from 'react'
import { ToastContainer, ToastData, ToastType } from '../components/shared/Toast'
import { useAudio, OrderFillType } from '../hooks/useAudio'
import { tryRefreshToken } from '../services/api'

interface OrderFillEvent {
  type: 'order_fill'
  fill_type: 'base_order' | 'dca_order' | 'sell_order' | 'partial_fill'
  product_id: string
  bot_name?: string
  base_amount: number
  quote_amount: number
  price: number
  profit?: number
  profit_percentage?: number
  position_id: number
  is_paper_trading?: boolean
  exit_source?: string
  exit_trigger_reason?: string
  exit_process_role?: string
  exit_hostname?: string
  exit_order_id?: string
  unexpected_exit?: boolean
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
  // When true, paper-trading order notifications are hidden while the active
  // account is a real (non-paper) account. See setActiveAccountIsPaper.
  suppressPaperWhenReal: boolean
  setSuppressPaperWhenReal: (enabled: boolean) => void
  // Bridge from AccountContext (which is a descendant provider): the active
  // account's paper status. null = unknown/none selected.
  setActiveAccountIsPaper: (isPaper: boolean | null) => void
}

const NotificationContext = createContext<NotificationContextType | null>(null)

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

interface NotificationProviderProps {
  children: ReactNode
}

const VERSION_CHECK_INTERVAL = 5 * 60 * 1000 // 5 minutes

export function NotificationProvider({ children }: NotificationProviderProps) {
  const [toasts, setToasts] = useState<ToastData[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [audioEnabled, setAudioEnabledState] = useState(() => {
    const saved = localStorage.getItem('audio-notifications-enabled')
    return saved !== 'false' // Default to true
  })
  const [suppressPaperWhenReal, setSuppressPaperWhenRealState] = useState(() => {
    // Default OFF — paper notifications show unless the user opts to mute them.
    return localStorage.getItem('suppress-paper-notifications-when-real') === 'true'
  })
  // Read inside handleOrderFill (which the socket captures once), so use refs to
  // dodge stale closures rather than relying on callback identity.
  const audioEnabledRef = useRef(audioEnabled)
  const suppressPaperWhenRealRef = useRef(suppressPaperWhenReal)
  const activeAccountIsPaperRef = useRef<boolean | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const loadedVersionRef = useRef<string | null>(null)
  const loadedStartupTimeRef = useRef<string | null>(null)
  const updateToastShownForRef = useRef<string | null>(null)
  const versionCheckIntervalRef = useRef<number | null>(null)
  const versionVerifyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
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
    setToasts((prev) => {
      const toast = prev.find((t) => t.id === id)
      // If dismissing an update toast, allow it to re-appear on next version check
      if (toast?.type === 'update') {
        updateToastShownForRef.current = null
      }
      return prev.filter((t) => t.id !== id)
    })
  }, [])

  // Toggle audio
  const setAudioEnabled = useCallback((enabled: boolean) => {
    setAudioEnabledState(enabled)
    audioEnabledRef.current = enabled
    setAudioHookEnabled(enabled)
    localStorage.setItem('audio-notifications-enabled', enabled ? 'true' : 'false')
  }, [setAudioHookEnabled])

  // Toggle "hide paper notifications while on a real account"
  const setSuppressPaperWhenReal = useCallback((enabled: boolean) => {
    setSuppressPaperWhenRealState(enabled)
    suppressPaperWhenRealRef.current = enabled
    localStorage.setItem('suppress-paper-notifications-when-real', enabled ? 'true' : 'false')
  }, [])

  // Bridge setter — pushed by a component inside AccountProvider.
  const setActiveAccountIsPaper = useCallback((isPaper: boolean | null) => {
    activeAccountIsPaperRef.current = isPaper
  }, [])

  // Check for new version and show update toast.
  // After detecting a new version, waits and re-verifies the server is stable
  // before prompting — avoids showing the toast while the backend is still starting.
  const checkForNewVersion = useCallback(() => {
    fetch('/api/')
      .then(res => res.json())
      .then(data => {
        const serverVersion = data.version
        const startupTime = data.startup_time
        if (!serverVersion) return

        // Capture the initially loaded version + startup time on first check
        if (!loadedVersionRef.current) {
          loadedVersionRef.current = serverVersion
          loadedStartupTimeRef.current = startupTime || null
          return
        }

        // Require BOTH version change AND startup_time change (actual restart).
        // This prevents the toast from firing when a tag is pushed but the
        // backend hasn't restarted yet — the live git tag would change but
        // startup_time stays the same until the process restarts.
        const versionChanged = serverVersion !== loadedVersionRef.current
        const serverRestarted = startupTime && startupTime !== loadedStartupTimeRef.current
        if (
          versionChanged &&
          serverRestarted &&
          updateToastShownForRef.current !== serverVersion
        ) {
          // Verify the server is fully stable: check 3 times over 15 seconds.
          // All checks must return the same new version before we notify.
          const verifyVersion = (checksRemaining: number) => {
            fetch('/api/')
              .then(res => res.json())
              .then(data => {
                if (data.version !== serverVersion) return  // Version changed mid-check, abort
                if (updateToastShownForRef.current === serverVersion) return  // Already shown
                if (checksRemaining > 1) {
                  versionVerifyTimerRef.current = setTimeout(() => verifyVersion(checksRemaining - 1), 5000)
                } else {
                  // All checks passed — server is stable
                  updateToastShownForRef.current = serverVersion
                  loadedStartupTimeRef.current = data.startup_time || null
                  addToast({
                    type: 'update',
                    title: 'New Version Available',
                    message: `Version ${serverVersion} is ready. Reload to get the latest updates.`,
                    persistent: true,
                    actionLabel: 'Reload',
                    onAction: () => window.location.reload(),
                  })
                }
              })
              .catch(() => {})  // Server not responding — don't notify yet
          }
          versionVerifyTimerRef.current = setTimeout(() => verifyVersion(3), 5000)  // Start after 5s, then 3 checks × 5s = 20s total
        }
      })
      .catch(() => {
        // Silently ignore — server may be restarting
      })
  }, [addToast])

  // Handle incoming order fill events
  const handleOrderFill = useCallback((event: OrderFillEvent) => {
    // Suppress paper-trading notifications while the active account is a real
    // (non-paper) account, if the user enabled that. Refs avoid stale closures.
    if (
      suppressPaperWhenRealRef.current &&
      activeAccountIsPaperRef.current === false &&
      event.is_paper_trading
    ) {
      return
    }

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
      botName: event.bot_name,
      productId: event.product_id,
      amount,
      price,
      profit,
      isPaperTrading: event.is_paper_trading,
    })

    if (event.unexpected_exit) {
      addToast({
        type: 'info',
        title: 'Unexpected automatic exit',
        message: (
          `${event.product_id} was closed by ${event.exit_process_role ?? 'an unknown process'} ` +
          `on ${event.exit_hostname ?? 'an unknown host'}. ` +
          `Reason: ${event.exit_trigger_reason ?? 'not recorded'}.`
        ),
        persistent: true,
      })
    }

    // Play audio if enabled
    if (audioEnabledRef.current) {
      playOrderSound(event.fill_type as OrderFillType)
    }

    // Signal portfolio to refresh after any completed trade
    window.dispatchEvent(new CustomEvent('portfolio:trade-completed'))
  }, [addToast, playOrderSound])

  // Connect to WebSocket
  const connect = useCallback(async () => {
    // Determine WebSocket URL based on current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host

    // Check if the access token is expired before connecting.
    // If it is, try a silent refresh first so we don't open a socket that
    // the backend will immediately reject (avoids console error spam).
    let token = localStorage.getItem('auth_access_token')
    const expiry = parseInt(localStorage.getItem('auth_token_expiry') || '0')
    if (!token || Date.now() >= expiry) {
      token = await tryRefreshToken()
      if (!token) {
        // No valid token — user is logged out or refresh failed; don't connect
        return
      }
    }

    const wsUrl = `${protocol}//${host}/ws?token=${encodeURIComponent(token)}`

    console.debug('Connecting to notification WebSocket')

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.debug('WebSocket connected')
        setIsConnected(true)
        // Clear any pending reconnect
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = null
        }
        // Check for new version on every connect/reconnect
        checkForNewVersion()
      }

      ws.onmessage = (event) => {
        try {
          const data: WebSocketMessage = JSON.parse(event.data)
          console.debug('📨 WebSocket message received, type:', data.type)

          if (data.type === 'order_fill') {
            handleOrderFill(data as unknown as OrderFillEvent)
          } else if (data.type === 'friend:online') {
            addToast({
              type: 'social',
              title: 'Friend Online',
              message: `${data.display_name ?? 'Someone'} is now online`,
            })
          } else if (data.type === 'friend:request_accepted') {
            addToast({
              type: 'social',
              title: 'Friend Request Accepted',
              message: `${data.display_name ?? 'Someone'} accepted your friend request!`,
            })
          } else if (data.type === 'account:invitation') {
            // Real-time notification when an invitation is sent to a logged-in user
            const inviterName = (data.invited_by as string) ?? 'Someone'
            const accountName = (data.account_name as string) ?? 'an account'
            const inviteToken = data.token as string | undefined
            addToast({
              type: 'info',
              title: 'Account Invitation',
              message: `${inviterName} invited you to ${data.role === 'manager' ? 'manage' : 'observe'} "${accountName}"`,
              actionLabel: inviteToken ? 'Review' : undefined,
              onAction: () => {
                if (inviteToken) {
                  window.location.href = `/accept-invite?token=${inviteToken}`
                }
              },
            })
            // Trigger a refresh of pending invitations in AccountContext
            window.dispatchEvent(new CustomEvent('account:invitation_received'))
          } else if (data.type === 'admin:user_presence') {
            window.dispatchEvent(new CustomEvent('admin:user_presence', {
              detail: { user_id: data.user_id, is_online: data.is_online },
            }))
          } else if (data.type === 'speculative_calibration_alert') {
            const payload = (data.payload as {
              total_closed?: number
              overall_win_rate_pct?: number
              divergence_pp?: number
              dismiss_url?: string
            }) || {}
            const totalClosed = payload.total_closed ?? 0
            const divergencePp = Number(payload.divergence_pp ?? 0)
            const dismissUrl = payload.dismiss_url
            addToast({
              type: 'info',
              title: 'Speculative preset: recalibrate weights',
              message: (
                `After ${totalClosed} closed positions, signal components diverge by ` +
                `${divergencePp.toFixed(1)}pp. Check your email for the full report.`
              ),
              persistent: true,
              actionLabel: 'Review in email',
              onAction: () => {
                if (typeof dismissUrl === 'string' && dismissUrl.length > 0) {
                  window.location.href = dismissUrl
                }
              },
            })
          }
        } catch (error) {
          console.warn('Failed to parse WebSocket message:', error)
        }
      }

      ws.onerror = (error) => {
        console.warn('WebSocket error:', error)
      }

      ws.onclose = () => {
        console.debug('WebSocket disconnected')
        setIsConnected(false)
        wsRef.current = null

        // Attempt to reconnect after 5 seconds
        reconnectTimeoutRef.current = window.setTimeout(() => {
          console.debug('Attempting WebSocket reconnection...')
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
  }, [handleOrderFill, checkForNewVersion])

  // Connect on mount (delayed to avoid React StrictMode "closed before established")
  useEffect(() => {
    // setTimeout(0) ensures Strict Mode's immediate cleanup cancels this before it fires,
    // so only the second (real) mount actually creates the WebSocket connection.
    const connectTimer = setTimeout(connect, 0)

    // Periodic version check as fallback (covers non-restart version bumps)
    versionCheckIntervalRef.current = window.setInterval(checkForNewVersion, VERSION_CHECK_INTERVAL)

    return () => {
      clearTimeout(connectTimer)
      const ws = wsRef.current
      if (ws) {
        ws.onopen = null
        ws.onmessage = null
        ws.onerror = null
        ws.onclose = null
        ws.close()
        wsRef.current = null
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      if (versionCheckIntervalRef.current) {
        clearInterval(versionCheckIntervalRef.current)
        versionCheckIntervalRef.current = null
      }
      if (versionVerifyTimerRef.current) {
        clearTimeout(versionVerifyTimerRef.current)
        versionVerifyTimerRef.current = null
      }
    }
  }, [connect, checkForNewVersion])

  const value: NotificationContextType = useMemo(() => ({
    addToast,
    dismissToast,
    isConnected,
    audioEnabled,
    setAudioEnabled,
    suppressPaperWhenReal,
    setSuppressPaperWhenReal,
    setActiveAccountIsPaper,
  }), [addToast, dismissToast, isConnected, audioEnabled, setAudioEnabled,
       suppressPaperWhenReal, setSuppressPaperWhenReal, setActiveAccountIsPaper])

  return (
    <NotificationContext.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </NotificationContext.Provider>
  )
}
