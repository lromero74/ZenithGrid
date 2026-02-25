/**
 * Audio playback hook for order fill notifications
 * Uses Web Audio API to generate distinct sounds for different order types
 */

import { useCallback, useRef, useEffect } from 'react'

export type OrderFillType = 'base_order' | 'dca_order' | 'sell_order' | 'partial_fill'

interface AudioConfig {
  frequency: number
  duration: number
  type: OscillatorType
  gain: number
  rampDown?: boolean
}

// Different sounds for different order types
const AUDIO_CONFIGS: Record<OrderFillType, AudioConfig[]> = {
  // Base order: Descending tone (money spent)
  base_order: [
    { frequency: 880, duration: 0.1, type: 'sine', gain: 0.35 },
    { frequency: 783.99, duration: 0.1, type: 'sine', gain: 0.3 },
    { frequency: 659.25, duration: 0.1, type: 'sine', gain: 0.25 },
    { frequency: 523.25, duration: 0.2, type: 'sine', gain: 0.2, rampDown: true },
  ],
  // DCA order: Double beep (averaging down)
  dca_order: [
    { frequency: 440, duration: 0.08, type: 'sine', gain: 0.25 },
    { frequency: 440, duration: 0.08, type: 'sine', gain: 0.25 },
  ],
  // Sell order: Ascending chime (money made!)
  sell_order: [
    { frequency: 523.25, duration: 0.1, type: 'sine', gain: 0.3 },
    { frequency: 659.25, duration: 0.1, type: 'sine', gain: 0.3 },
    { frequency: 783.99, duration: 0.15, type: 'sine', gain: 0.3, rampDown: true },
  ],
  // Partial fill: Single soft beep
  partial_fill: [
    { frequency: 600, duration: 0.1, type: 'sine', gain: 0.15, rampDown: true },
  ],
}

export function useAudio() {
  const audioContextRef = useRef<AudioContext | null>(null)
  const isEnabledRef = useRef<boolean>(true)

  // Initialize AudioContext lazily (browsers require user interaction first)
  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
    }
    return audioContextRef.current
  }, [])

  // Play a single tone
  const playTone = useCallback(async (config: AudioConfig, startTime: number) => {
    const ctx = getAudioContext()

    // Resume context if suspended (browser autoplay policy)
    if (ctx.state === 'suspended') {
      await ctx.resume()
    }

    const oscillator = ctx.createOscillator()
    const gainNode = ctx.createGain()

    oscillator.type = config.type
    oscillator.frequency.value = config.frequency

    gainNode.gain.setValueAtTime(config.gain, startTime)
    if (config.rampDown) {
      gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + config.duration)
    }

    oscillator.connect(gainNode)
    gainNode.connect(ctx.destination)

    oscillator.start(startTime)
    oscillator.stop(startTime + config.duration)

    return config.duration
  }, [getAudioContext])

  // Play sound for a specific order type
  const playOrderSound = useCallback(async (orderType: OrderFillType) => {
    if (!isEnabledRef.current) return

    const configs = AUDIO_CONFIGS[orderType]
    if (!configs) return

    try {
      const ctx = getAudioContext()
      let currentTime = ctx.currentTime

      for (const config of configs) {
        await playTone(config, currentTime)
        currentTime += config.duration + 0.02 // Small gap between tones
      }
    } catch (error) {
      console.warn('Audio playback failed:', error)
    }
  }, [getAudioContext, playTone])

  // Enable/disable audio
  const setAudioEnabled = useCallback((enabled: boolean) => {
    isEnabledRef.current = enabled
    // Store preference
    localStorage.setItem('audio-notifications-enabled', enabled ? 'true' : 'false')
  }, [])

  // Load preference on mount
  useEffect(() => {
    const saved = localStorage.getItem('audio-notifications-enabled')
    if (saved !== null) {
      isEnabledRef.current = saved === 'true'
    }
  }, [])

  // Get current enabled state
  const isAudioEnabled = useCallback(() => {
    return isEnabledRef.current
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (audioContextRef.current) {
        audioContextRef.current.close()
      }
    }
  }, [])

  return {
    playOrderSound,
    setAudioEnabled,
    isAudioEnabled,
  }
}
