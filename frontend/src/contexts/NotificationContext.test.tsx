/**
 * Tests for NotificationContext
 *
 * Tests WebSocket connection management, order fill handling per fill type,
 * toast creation/dismissal, version check stabilization, and audio enable/disable.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'

// Mock useAudio hook
const mockPlayOrderSound = vi.fn()
const mockSetAudioEnabled = vi.fn()
vi.mock('../hooks/useAudio', () => ({
  useAudio: () => ({
    playOrderSound: mockPlayOrderSound,
    setAudioEnabled: mockSetAudioEnabled,
    isAudioEnabled: () => true,
  }),
}))

// Mock Toast component to simplify rendering
vi.mock('../components/Toast', () => ({
  ToastContainer: ({ toasts, onDismiss }: { toasts: Array<{ id: string; type: string; title: string; message: string }>; onDismiss: (id: string) => void }) => (
    <div data-testid="toast-container">
      {toasts.map((t) => (
        <div key={t.id} data-testid={`toast-${t.type}`}>
          <span data-testid={`toast-title-${t.id}`}>{t.title}</span>
          <span data-testid={`toast-msg-${t.id}`}>{t.message}</span>
          <button data-testid={`toast-dismiss-${t.id}`} onClick={() => onDismiss(t.id)}>Dismiss</button>
        </div>
      ))}
    </div>
  ),
}))

import { NotificationProvider, useNotifications } from './NotificationContext'

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  readyState = 0
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  // Helper to simulate events
  simulateOpen() {
    this.readyState = 1
    if (this.onopen) this.onopen(new Event('open'))
  }

  simulateMessage(data: unknown) {
    if (this.onmessage) this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  simulateClose() {
    this.readyState = 3
    if (this.onclose) this.onclose(new CloseEvent('close'))
  }

  simulateError() {
    if (this.onerror) this.onerror(new Event('error'))
  }
}

// TestConsumer exposes context values to assertions
function TestConsumer() {
  const ctx = useNotifications()
  return (
    <div>
      <span data-testid="connected">{String(ctx.isConnected)}</span>
      <span data-testid="audio-enabled">{String(ctx.audioEnabled)}</span>
      <button data-testid="add-toast" onClick={() => ctx.addToast({ type: 'info', title: 'Test', message: 'Hello' })}>
        Add Toast
      </button>
      <button data-testid="enable-audio" onClick={() => ctx.setAudioEnabled(true)}>Enable Audio</button>
      <button data-testid="disable-audio" onClick={() => ctx.setAudioEnabled(false)}>Disable Audio</button>
    </div>
  )
}

describe('NotificationContext', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    mockPlayOrderSound.mockClear()
    mockSetAudioEnabled.mockClear()
    vi.useFakeTimers()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)

    // Default fetch mock for version check (return a version)
    fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ version: 'v1.0.0' }),
    } as Response)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  test('useNotifications throws outside of provider', () => {
    function BadConsumer() {
      useNotifications()
      return <div />
    }
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<BadConsumer />)).toThrow('useNotifications must be used within NotificationProvider')
    spy.mockRestore()
  })

  test('connects to WebSocket on mount', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    // The connection is deferred via setTimeout(0) to handle StrictMode
    act(() => { vi.advanceTimersByTime(0) })

    expect(MockWebSocket.instances.length).toBe(1)
    const ws = MockWebSocket.instances[0]
    expect(ws.url).toContain('/ws')
  })

  test('includes auth token in WebSocket URL when present', async () => {
    localStorage.setItem('auth_access_token', 'my-secret-token')

    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })

    const ws = MockWebSocket.instances[0]
    expect(ws.url).toContain('token=my-secret-token')
  })

  test('sets isConnected to true on WebSocket open', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })

    expect(screen.getByTestId('connected').textContent).toBe('false')

    const ws = MockWebSocket.instances[0]
    await act(async () => { ws.simulateOpen() })

    expect(screen.getByTestId('connected').textContent).toBe('true')
  })

  test('sets isConnected to false on WebSocket close', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]

    await act(async () => { ws.simulateOpen() })
    expect(screen.getByTestId('connected').textContent).toBe('true')

    await act(async () => { ws.simulateClose() })
    expect(screen.getByTestId('connected').textContent).toBe('false')
  })

  test('attempts reconnection after WebSocket close', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]

    await act(async () => { ws.simulateClose() })

    // Should reconnect after 5 seconds
    expect(MockWebSocket.instances.length).toBe(1) // not yet
    act(() => { vi.advanceTimersByTime(5000) })
    expect(MockWebSocket.instances.length).toBe(2) // reconnected
  })

  test('handleOrderFill for base_order creates correct toast', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]
    await act(async () => { ws.simulateOpen() })

    await act(async () => {
      ws.simulateMessage({
        type: 'order_fill',
        fill_type: 'base_order',
        product_id: 'BTC-USD',
        base_amount: 0.001,
        quote_amount: 50.0,
        price: 50000.0,
        position_id: 1,
        timestamp: '2026-01-01T00:00:00Z',
      })
    })

    expect(screen.getByTestId('toast-container')).toBeDefined()
    const toasts = screen.getAllByTestId('toast-base_order')
    expect(toasts.length).toBe(1)
  })

  test('handleOrderFill for dca_order creates DCA toast', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]
    await act(async () => { ws.simulateOpen() })

    await act(async () => {
      ws.simulateMessage({
        type: 'order_fill',
        fill_type: 'dca_order',
        product_id: 'ETH-USD',
        base_amount: 0.5,
        quote_amount: 1000.0,
        price: 2000.0,
        position_id: 2,
        timestamp: '2026-01-01T00:00:00Z',
      })
    })

    const toasts = screen.getAllByTestId('toast-dca_order')
    expect(toasts.length).toBe(1)
  })

  test('handleOrderFill for sell_order with profit creates profit toast', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]
    await act(async () => { ws.simulateOpen() })

    await act(async () => {
      ws.simulateMessage({
        type: 'order_fill',
        fill_type: 'sell_order',
        product_id: 'BTC-USD',
        base_amount: 0.001,
        quote_amount: 55.0,
        price: 55000.0,
        profit: 5.0,
        profit_percentage: 10.0,
        position_id: 1,
        timestamp: '2026-01-01T00:00:00Z',
      })
    })

    const toasts = screen.getAllByTestId('toast-sell_order')
    expect(toasts.length).toBe(1)
  })

  test('handleOrderFill for partial_fill creates partial fill toast', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]
    await act(async () => { ws.simulateOpen() })

    await act(async () => {
      ws.simulateMessage({
        type: 'order_fill',
        fill_type: 'partial_fill',
        product_id: 'SOL-USD',
        base_amount: 2.0,
        quote_amount: 300.0,
        price: 150.0,
        position_id: 3,
        timestamp: '2026-01-01T00:00:00Z',
      })
    })

    const toasts = screen.getAllByTestId('toast-partial_fill')
    expect(toasts.length).toBe(1)
  })

  test('plays audio on order fill when audio is enabled', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]
    await act(async () => { ws.simulateOpen() })

    await act(async () => {
      ws.simulateMessage({
        type: 'order_fill',
        fill_type: 'base_order',
        product_id: 'BTC-USD',
        base_amount: 0.001,
        quote_amount: 50.0,
        price: 50000.0,
        position_id: 1,
        timestamp: '2026-01-01T00:00:00Z',
      })
    })

    expect(mockPlayOrderSound).toHaveBeenCalledWith('base_order')
  })

  test('does not play audio when audio is disabled', async () => {
    localStorage.setItem('audio-notifications-enabled', 'false')

    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]
    await act(async () => { ws.simulateOpen() })

    await act(async () => {
      ws.simulateMessage({
        type: 'order_fill',
        fill_type: 'base_order',
        product_id: 'BTC-USD',
        base_amount: 0.001,
        quote_amount: 50.0,
        price: 50000.0,
        position_id: 1,
        timestamp: '2026-01-01T00:00:00Z',
      })
    })

    expect(mockPlayOrderSound).not.toHaveBeenCalled()
  })

  test('setAudioEnabled persists to localStorage and updates state', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    // Audio enabled by default
    expect(screen.getByTestId('audio-enabled').textContent).toBe('true')

    // Disable audio
    await act(async () => {
      screen.getByTestId('disable-audio').click()
    })

    expect(screen.getByTestId('audio-enabled').textContent).toBe('false')
    expect(localStorage.getItem('audio-notifications-enabled')).toBe('false')

    // Re-enable audio
    await act(async () => {
      screen.getByTestId('enable-audio').click()
    })

    expect(screen.getByTestId('audio-enabled').textContent).toBe('true')
    expect(localStorage.getItem('audio-notifications-enabled')).toBe('true')
  })

  test('audio defaults to enabled when localStorage has no value', () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    expect(screen.getByTestId('audio-enabled').textContent).toBe('true')
  })

  test('audio reads disabled state from localStorage', () => {
    localStorage.setItem('audio-notifications-enabled', 'false')

    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    expect(screen.getByTestId('audio-enabled').textContent).toBe('false')
  })

  test('addToast creates a visible toast', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    await act(async () => {
      screen.getByTestId('add-toast').click()
    })

    expect(screen.getByTestId('toast-container').children.length).toBe(1)
  })

  test('toasts are capped at 5 maximum', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    // Add 7 toasts
    for (let i = 0; i < 7; i++) {
      await act(async () => {
        screen.getByTestId('add-toast').click()
      })
    }

    // Should only have 5 (max)
    expect(screen.getByTestId('toast-container').children.length).toBeLessThanOrEqual(5)
  })

  test('ignores non-order_fill WebSocket messages', async () => {
    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]
    await act(async () => { ws.simulateOpen() })

    await act(async () => {
      ws.simulateMessage({ type: 'heartbeat', data: {} })
    })

    // No toasts should be created
    expect(screen.getByTestId('toast-container').children.length).toBe(0)
  })

  test('handles malformed WebSocket messages gracefully', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]
    await act(async () => { ws.simulateOpen() })

    // Send invalid JSON — simulating raw (non-JSON) data
    await act(async () => {
      if (ws.onmessage) {
        ws.onmessage(new MessageEvent('message', { data: 'not valid json' }))
      }
    })

    expect(warnSpy).toHaveBeenCalled()
    expect(screen.getByTestId('toast-container').children.length).toBe(0)
    warnSpy.mockRestore()
  })

  test('version check captures initial version on first fetch', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ version: 'v1.0.0' }),
    } as Response)

    render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]

    // onopen triggers checkForNewVersion
    await act(async () => { ws.simulateOpen() })

    // First call captures version — no toast should appear
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })

    expect(screen.getByTestId('toast-container').children.length).toBe(0)
  })

  test('cleans up WebSocket and timers on unmount', async () => {
    const { unmount } = render(
      <NotificationProvider>
        <TestConsumer />
      </NotificationProvider>
    )

    act(() => { vi.advanceTimersByTime(0) })
    const ws = MockWebSocket.instances[0]
    await act(async () => { ws.simulateOpen() })

    unmount()

    expect(ws.close).toHaveBeenCalled()
  })
})
