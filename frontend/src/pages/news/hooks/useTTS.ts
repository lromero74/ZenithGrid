/**
 * Text-to-Speech hook for reading article content aloud
 * Uses Microsoft Edge's neural TTS via backend API
 */

import { useState, useRef, useCallback, useEffect } from 'react'

export interface TTSVoice {
  id: string
  name: string
  gender: string
  style: string
  desc: string
}

interface UseTTSOptions {
  defaultVoice?: string
  defaultRate?: number
}

interface UseTTSReturn {
  // State
  isPlaying: boolean
  isPaused: boolean
  isLoading: boolean
  isReady: boolean  // Audio loaded but needs user click to play (autoplay blocked)
  error: string | null
  currentVoice: string
  playbackRate: number
  voices: TTSVoice[]

  // Actions
  speak: (text: string) => Promise<void>
  play: () => void  // Start playback when isReady (after autoplay blocked)
  pause: () => void
  resume: () => void
  stop: () => void
  setVoice: (voiceId: string) => void
  setRate: (rate: number) => void
}

const DEFAULT_VOICES: TTSVoice[] = [
  { id: 'aria', name: 'Aria', gender: 'Female', style: 'News', desc: 'Clear' },
  { id: 'guy', name: 'Guy', gender: 'Male', style: 'News', desc: 'Authoritative' },
  { id: 'jenny', name: 'Jenny', gender: 'Female', style: 'General', desc: 'Friendly' },
  { id: 'brian', name: 'Brian', gender: 'Male', style: 'Casual', desc: 'Approachable' },
  { id: 'emma', name: 'Emma', gender: 'Female', style: 'Casual', desc: 'Cheerful' },
  { id: 'andrew', name: 'Andrew', gender: 'Male', style: 'Casual', desc: 'Warm' },
]

export function useTTS(options: UseTTSOptions = {}): UseTTSReturn {
  const { defaultVoice = 'aria', defaultRate = 1.0 } = options

  const [isPlaying, setIsPlaying] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [isReady, setIsReady] = useState(false)  // Audio ready but autoplay was blocked
  const [error, setError] = useState<string | null>(null)
  const [currentVoice, setCurrentVoice] = useState(defaultVoice)
  const [playbackRate, setPlaybackRate] = useState(defaultRate)
  const [voices] = useState<TTSVoice[]>(DEFAULT_VOICES)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ''
        audioRef.current = null
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  const speak = useCallback(async (text: string) => {
    // Stop any existing playback
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.src = ''
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    setIsLoading(true)
    setError(null)
    setIsPlaying(false)
    setIsPaused(false)
    setIsReady(false)

    try {
      // Convert playback rate to percentage (1.0 = +0%, 1.2 = +20%, 0.8 = -20%)
      const ratePercent = Math.round((playbackRate - 1) * 100)
      const rateStr = ratePercent >= 0 ? `+${ratePercent}%` : `${ratePercent}%`

      // Create abort controller for this request
      abortControllerRef.current = new AbortController()

      // Build URL with query params
      const params = new URLSearchParams({
        text: text,
        voice: currentVoice,
        rate: rateStr,
      })

      const response = await fetch(`/api/news/tts?${params.toString()}`, {
        method: 'POST',
        signal: abortControllerRef.current.signal,
      })

      if (!response.ok) {
        throw new Error(`TTS request failed: ${response.status}`)
      }

      // Get audio blob from streaming response
      const blob = await response.blob()
      const audioUrl = URL.createObjectURL(blob)

      // Create and play audio
      const audio = new Audio(audioUrl)
      audio.playbackRate = playbackRate
      audioRef.current = audio

      // Set up event handlers
      audio.onplay = () => {
        setIsPlaying(true)
        setIsPaused(false)
        setIsLoading(false)
      }

      audio.onpause = () => {
        if (!audio.ended) {
          setIsPaused(true)
          setIsPlaying(false)
        }
      }

      audio.onended = () => {
        setIsPlaying(false)
        setIsPaused(false)
        URL.revokeObjectURL(audioUrl)
      }

      audio.onerror = () => {
        setError('Audio playback failed')
        setIsPlaying(false)
        setIsLoading(false)
        URL.revokeObjectURL(audioUrl)
      }

      // Try to play - may be blocked by autoplay policy
      try {
        await audio.play()
      } catch (playErr) {
        // Check if it's an autoplay policy block
        if ((playErr as Error).name === 'NotAllowedError') {
          // Audio is loaded but needs user interaction to play
          setIsLoading(false)
          setIsReady(true)
          console.log('Autoplay blocked - user needs to click play')
        } else {
          throw playErr
        }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        // Request was cancelled, not an error
        return
      }
      console.error('TTS error:', err)
      setError((err as Error).message || 'Failed to generate speech')
      setIsLoading(false)
    }
  }, [currentVoice, playbackRate])

  // Play when audio is ready (after autoplay was blocked)
  const play = useCallback(() => {
    if (audioRef.current && isReady) {
      audioRef.current.play()
        .then(() => {
          setIsReady(false)
        })
        .catch((err) => {
          console.error('Play failed:', err)
          setError('Failed to play audio')
        })
    }
  }, [isReady])

  const pause = useCallback(() => {
    if (audioRef.current && !audioRef.current.paused) {
      audioRef.current.pause()
    }
  }, [])

  const resume = useCallback(() => {
    if (audioRef.current && audioRef.current.paused) {
      audioRef.current.play()
    }
  }, [])

  const stop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioRef.current.src = ''
      audioRef.current = null
    }
    setIsPlaying(false)
    setIsPaused(false)
    setIsLoading(false)
    setIsReady(false)
    setError(null)
  }, [])

  const setVoice = useCallback((voiceId: string) => {
    setCurrentVoice(voiceId)
  }, [])

  const setRate = useCallback((rate: number) => {
    setPlaybackRate(rate)
    // Also update current audio if playing
    if (audioRef.current) {
      audioRef.current.playbackRate = rate
    }
  }, [])

  return {
    isPlaying,
    isPaused,
    isLoading,
    isReady,
    error,
    currentVoice,
    playbackRate,
    voices,
    speak,
    play,
    pause,
    resume,
    stop,
    setVoice,
    setRate,
  }
}
