/**
 * WebSocket client for multiplayer game communication.
 *
 * Wraps the existing /ws endpoint with game-specific message routing.
 * Singleton instance with event-based message handling.
 */

type MessageHandler = (data: any) => void

class GameSocketClient {
  private ws: WebSocket | null = null
  private listeners: Map<string, Set<MessageHandler>> = new Map()
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _token: string | null = null
  private _connected = false

  get connected(): boolean {
    return this._connected
  }

  connect(token: string): void {
    if (this.ws && this._connected) return
    this._token = token

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws?token=${token}`

    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      this._connected = true
      this._emit('connection', { connected: true })
    }

    this.ws.onclose = () => {
      this._connected = false
      this._emit('connection', { connected: false })
      this._scheduleReconnect()
    }

    this.ws.onerror = () => {
      // onclose will fire after this
    }

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        const type = msg.type || 'unknown'
        this._emit(type, msg)
      } catch {
        // ignore malformed messages
      }
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this._token = null
    if (this.ws) {
      this.ws.onclose = null // prevent reconnect
      this.ws.close()
      this.ws = null
    }
    this._connected = false
  }

  send(message: object): void {
    if (this.ws && this._connected) {
      this.ws.send(JSON.stringify(message))
    }
  }

  /** Subscribe to a message type. Returns an unsubscribe function. */
  on(type: string, handler: MessageHandler): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set())
    }
    this.listeners.get(type)!.add(handler)
    return () => {
      this.listeners.get(type)?.delete(handler)
    }
  }

  // ----- Game Room Convenience Methods -----

  createRoom(gameId: string, mode: string, config?: object): void {
    this.send({ type: 'game:create', gameId, mode, config })
  }

  joinRoom(roomId: string): void {
    this.send({ type: 'game:join', roomId })
  }

  leaveRoom(roomId: string): void {
    this.send({ type: 'game:leave', roomId })
  }

  sendReady(roomId: string): void {
    this.send({ type: 'game:ready', roomId })
  }

  startGame(roomId: string): void {
    this.send({ type: 'game:start', roomId })
  }

  sendAction(roomId: string, action: object): void {
    this.send({ type: 'game:action', roomId, action })
  }

  sendState(roomId: string, state: object): void {
    this.send({ type: 'game:state', roomId, state })
  }

  // ----- Internal -----

  private _emit(type: string, data: any): void {
    this.listeners.get(type)?.forEach(handler => {
      try { handler(data) } catch { /* handler error */ }
    })
  }

  private _scheduleReconnect(): void {
    if (this.reconnectTimer || !this._token) return
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      if (this._token) {
        this.connect(this._token)
      }
    }, 3000)
  }
}

export const gameSocket = new GameSocketClient()
