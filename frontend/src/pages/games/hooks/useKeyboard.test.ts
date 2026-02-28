/**
 * Tests for useKeyboard hook
 *
 * Verifies keyboard event listener registration, cleanup on unmount,
 * key event dispatching, handler ref updates, and disabled state.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useKeyboard } from './useKeyboard'

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

function fireKeydown(key: string, opts?: Partial<KeyboardEventInit>) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, ...opts })
  document.dispatchEvent(event)
  return event
}

describe('useKeyboard event handling', () => {
  test('calls handler when a key is pressed', () => {
    const handler = vi.fn()
    renderHook(() => useKeyboard(handler))

    fireKeydown('ArrowUp')

    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler.mock.calls[0][0].key).toBe('ArrowUp')
  })

  test('calls handler for multiple different keys', () => {
    const handler = vi.fn()
    renderHook(() => useKeyboard(handler))

    fireKeydown('ArrowUp')
    fireKeydown('ArrowDown')
    fireKeydown('Enter')

    expect(handler).toHaveBeenCalledTimes(3)
    expect(handler.mock.calls[0][0].key).toBe('ArrowUp')
    expect(handler.mock.calls[1][0].key).toBe('ArrowDown')
    expect(handler.mock.calls[2][0].key).toBe('Enter')
  })

  test('receives full KeyboardEvent with modifiers', () => {
    const handler = vi.fn()
    renderHook(() => useKeyboard(handler))

    fireKeydown('a', { ctrlKey: true, shiftKey: true })

    expect(handler).toHaveBeenCalledTimes(1)
    const event = handler.mock.calls[0][0] as KeyboardEvent
    expect(event.key).toBe('a')
    expect(event.ctrlKey).toBe(true)
    expect(event.shiftKey).toBe(true)
  })
})

describe('useKeyboard disabled state', () => {
  test('does not call handler when enabled is false', () => {
    const handler = vi.fn()
    renderHook(() => useKeyboard(handler, false))

    fireKeydown('ArrowUp')

    expect(handler).not.toHaveBeenCalled()
  })

  test('responds to key events when re-enabled', () => {
    const handler = vi.fn()
    const { rerender } = renderHook(
      ({ enabled }) => useKeyboard(handler, enabled),
      { initialProps: { enabled: false } }
    )

    fireKeydown('ArrowUp')
    expect(handler).not.toHaveBeenCalled()

    // Re-enable
    rerender({ enabled: true })

    fireKeydown('ArrowDown')
    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler.mock.calls[0][0].key).toBe('ArrowDown')
  })

  test('stops responding when disabled after being enabled', () => {
    const handler = vi.fn()
    const { rerender } = renderHook(
      ({ enabled }) => useKeyboard(handler, enabled),
      { initialProps: { enabled: true } }
    )

    fireKeydown('a')
    expect(handler).toHaveBeenCalledTimes(1)

    // Disable
    rerender({ enabled: false })

    fireKeydown('b')
    expect(handler).toHaveBeenCalledTimes(1) // Still 1, not 2
  })
})

describe('useKeyboard cleanup on unmount', () => {
  test('removes event listener on unmount', () => {
    const handler = vi.fn()
    const { unmount } = renderHook(() => useKeyboard(handler))

    fireKeydown('ArrowUp')
    expect(handler).toHaveBeenCalledTimes(1)

    unmount()

    fireKeydown('ArrowDown')
    expect(handler).toHaveBeenCalledTimes(1) // No additional calls after unmount
  })

  test('removes event listener when transitioning to disabled', () => {
    const removeSpy = vi.spyOn(document, 'removeEventListener')
    const handler = vi.fn()

    const { rerender } = renderHook(
      ({ enabled }) => useKeyboard(handler, enabled),
      { initialProps: { enabled: true } }
    )

    rerender({ enabled: false })

    expect(removeSpy).toHaveBeenCalledWith('keydown', expect.any(Function))
  })
})

describe('useKeyboard handler ref updates', () => {
  test('uses latest handler without re-attaching listener', () => {
    const handler1 = vi.fn()
    const handler2 = vi.fn()

    const { rerender } = renderHook(
      ({ handler }) => useKeyboard(handler),
      { initialProps: { handler: handler1 } }
    )

    fireKeydown('a')
    expect(handler1).toHaveBeenCalledTimes(1)

    // Update handler (via ref, should not re-attach listener)
    rerender({ handler: handler2 })

    fireKeydown('b')
    expect(handler1).toHaveBeenCalledTimes(1) // Not called again
    expect(handler2).toHaveBeenCalledTimes(1) // New handler received the event
  })
})

describe('useKeyboard defaults', () => {
  test('enabled defaults to true when not specified', () => {
    const handler = vi.fn()
    renderHook(() => useKeyboard(handler))

    fireKeydown('Space')

    expect(handler).toHaveBeenCalledTimes(1)
  })

  test('only listens for keydown events (not keyup)', () => {
    const handler = vi.fn()
    renderHook(() => useKeyboard(handler))

    // Fire keyup instead of keydown
    const keyupEvent = new KeyboardEvent('keyup', { key: 'Enter', bubbles: true })
    document.dispatchEvent(keyupEvent)

    expect(handler).not.toHaveBeenCalled()
  })
})
