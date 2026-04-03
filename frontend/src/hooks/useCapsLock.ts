import { useState, useEffect } from 'react'

/** Returns true when Caps Lock is currently active, detected via keyboard events. */
export function useCapsLock(): boolean {
  const [capsLock, setCapsLock] = useState(false)

  useEffect(() => {
    const update = (e: KeyboardEvent) => {
      setCapsLock(e.getModifierState('CapsLock'))
    }
    window.addEventListener('keydown', update)
    window.addEventListener('keyup', update)
    return () => {
      window.removeEventListener('keydown', update)
      window.removeEventListener('keyup', update)
    }
  }, [])

  return capsLock
}
