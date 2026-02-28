/**
 * Hook for a game timer that counts elapsed seconds.
 *
 * Provides start/stop/reset controls and formatted time display.
 */

import { useState, useCallback, useRef, useEffect } from 'react'

export function useGameTimer() {
  const [seconds, setSeconds] = useState(0)
  const [isRunning, setIsRunning] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const clearTimer = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  const start = useCallback(() => {
    if (intervalRef.current !== null) return // already running
    setIsRunning(true)
    intervalRef.current = setInterval(() => {
      setSeconds(s => s + 1)
    }, 1000)
  }, [])

  const stop = useCallback(() => {
    clearTimer()
    setIsRunning(false)
  }, [clearTimer])

  const reset = useCallback(() => {
    clearTimer()
    setIsRunning(false)
    setSeconds(0)
  }, [clearTimer])

  // Cleanup on unmount
  useEffect(() => {
    return () => clearTimer()
  }, [clearTimer])

  const minutes = Math.floor(seconds / 60)
  const secs = seconds % 60
  const formatted = `${minutes}:${secs.toString().padStart(2, '0')}`

  return { seconds, isRunning, formatted, start, stop, reset }
}
