/**
 * Hook for keyboard event handling in games.
 *
 * Attaches a keydown listener to the document and calls the handler.
 * Automatically cleans up on unmount or handler change.
 */

import { useEffect, useCallback, useRef } from 'react'

export function useKeyboard(handler: (event: KeyboardEvent) => void, enabled = true) {
  const handlerRef = useRef(handler)
  handlerRef.current = handler

  const stableHandler = useCallback((e: KeyboardEvent) => {
    handlerRef.current(e)
  }, [])

  useEffect(() => {
    if (!enabled) return
    document.addEventListener('keydown', stableHandler)
    return () => document.removeEventListener('keydown', stableHandler)
  }, [enabled, stableHandler])
}
