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
  /** Room ID of an active game — used for auto-rejoin on reconnect. */
  private _activeRoomId: string | null = null
  /** Buffered game:joined response — survives navigation between pages. */
  private _pendingJoinResult: any = null

  get connected(): boolean {
    return this._connected
  }

  get activeRoomId(): string | null {
    return this._activeRoomId
  }

  /** Track that we're in an active game (for auto-rejoin on reconnect). */
  setActiveRoom(roomId: string | null): void {
    this._activeRoomId = roomId
  }

  connect(token: string): void {
    // Prevent duplicate connections — guard covers both OPEN and CONNECTING states
    if (this.ws && (this._connected || this.ws.readyState === WebSocket.CONNECTING)) return
    this._token = token

    // Close any stale socket before opening a new one
    if (this.ws) {
      this.ws.onclose = null // prevent reconnect/event from stale socket
      this.ws.close()
      this.ws = null
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws?token=${token}`

    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      if (this.ws !== ws) return // stale socket — ignore
      this._connected = true
      this._emit('connection', { connected: true })
      // Auto-rejoin if we were in a game when we disconnected
      if (this._activeRoomId) {
        this.send({ type: 'game:rejoin', roomId: this._activeRoomId })
      }
    }

    ws.onclose = () => {
      if (this.ws !== ws) return // stale socket — ignore
      this._connected = false
      this._emit('connection', { connected: false })
      this._scheduleReconnect()
    }

    ws.onerror = () => {
      // onclose will fire after this
    }

    ws.onmessage = (event) => {
      if (this.ws !== ws) return // stale socket — ignore
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
    this._activeRoomId = null
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

  midJoinRoom(roomId: string): void {
    this.send({ type: 'game:mid_join', roomId })
  }

  leaveRoom(roomId: string): void {
    this._activeRoomId = null
    this.send({ type: 'game:leave', roomId })
  }

  rejoinRoom(roomId: string): void {
    this.send({ type: 'game:rejoin', roomId })
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

  updateConfig(roomId: string, config: object): void {
    this.send({ type: 'game:update_config', roomId, config })
  }

  /**
   * Buffer the next game:joined response so it survives page navigation.
   * Call before sending game:join_friend and navigating away.
   */
  captureJoinResult(): void {
    this._pendingJoinResult = null
    const unsub = this.on('game:joined', (msg) => {
      this._pendingJoinResult = msg
      unsub()
    })
    // Auto-cleanup if no response within 10s
    setTimeout(() => { unsub(); }, 10000)
  }

  /** Consume the buffered game:joined result (returns null if none). */
  consumeJoinResult(): any {
    const result = this._pendingJoinResult
    this._pendingJoinResult = null
    return result
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
