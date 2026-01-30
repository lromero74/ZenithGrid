/**
 * Synchronized Text-to-Speech hook with word-level highlighting
 * Fetches audio and word timings, tracks playback for karaoke-style highlighting
 */

import { useState, useRef, useCallback, useEffect } from 'react'

export interface WordTiming {
  text: string
  startTime: number
  endTime: number
}

interface TTSSyncResponse {
  audio: string  // Base64-encoded MP3
  words: WordTiming[]
  voice: string
  rate: string
}

interface UseTTSSyncOptions {
  defaultVoice?: string
  defaultRate?: number
}

interface UseTTSSyncReturn {
  // State
  isLoading: boolean
  isPlaying: boolean
  isPaused: boolean
  isReady: boolean
  error: string | null
  words: WordTiming[]
  currentWordIndex: number
  currentTime: number
  duration: number
  currentVoice: string
  playbackRate: number

  // Actions
  loadAndPlay: (text: string) => Promise<void>
  play: () => void
  pause: () => void
  resume: () => void
  stop: () => void
  setVoice: (voice: string) => void
  setRate: (rate: number) => void
}

export function useTTSSync(options: UseTTSSyncOptions = {}): UseTTSSyncReturn {
  const { defaultVoice = 'aria', defaultRate = 1.0 } = options

  const [isLoading, setIsLoading] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [isReady, setIsReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [words, setWords] = useState<WordTiming[]>([])
  const [currentWordIndex, setCurrentWordIndex] = useState(-1)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [currentVoice, setCurrentVoice] = useState(defaultVoice)
  const [playbackRate, setPlaybackRate] = useState(defaultRate)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const animationFrameRef = useRef<number | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Update current word based on playback time
  const updateCurrentWord = useCallback(() => {
    if (!audioRef.current || !words.length) return

    const time = audioRef.current.currentTime
    setCurrentTime(time)

    // Find the word that contains the current time
    let foundIndex = -1
    for (let i = 0; i < words.length; i++) {
      if (time >= words[i].startTime && time < words[i].endTime) {
        foundIndex = i
        break
      }
      // Also check if we're between words (use the previous word)
      if (i > 0 && time >= words[i - 1].endTime && time < words[i].startTime) {
        foundIndex = i - 1
        break
      }
    }

    // If past all words, use last word
    if (foundIndex === -1 && words.length > 0 && time >= words[words.length - 1].startTime) {
      foundIndex = words.length - 1
    }

    setCurrentWordIndex(foundIndex)

    // Continue animation if playing
    if (isPlaying && !audioRef.current.paused) {
      animationFrameRef.current = requestAnimationFrame(updateCurrentWord)
    }
  }, [words, isPlaying])

  // Cleanup
  useEffect(() => {
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ''
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  const loadAndPlay = useCallback(async (text: string) => {
    // Stop any existing playback
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
    }
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
    setWords([])
    setCurrentWordIndex(-1)
    setCurrentTime(0)

    try {
      abortControllerRef.current = new AbortController()

      // Convert playback rate to percentage
      const ratePercent = Math.round((playbackRate - 1) * 100)
      const rateStr = ratePercent >= 0 ? `+${ratePercent}%` : `${ratePercent}%`

      const params = new URLSearchParams({
        text,
        voice: currentVoice,
        rate: rateStr,
      })

      const response = await fetch(`/api/news/tts-sync?${params.toString()}`, {
        method: 'POST',
        signal: abortControllerRef.current.signal,
      })

      if (!response.ok) {
        throw new Error(`TTS request failed: ${response.status}`)
      }

      const data: TTSSyncResponse = await response.json()

      // Store word timings
      setWords(data.words)

      // Create audio from base64
      const audioBlob = await fetch(`data:audio/mpeg;base64,${data.audio}`).then(r => r.blob())
      const audioUrl = URL.createObjectURL(audioBlob)

      const audio = new Audio(audioUrl)
      audio.playbackRate = playbackRate
      audioRef.current = audio

      audio.onloadedmetadata = () => {
        setDuration(audio.duration)
      }

      audio.onplay = () => {
        setIsPlaying(true)
        setIsPaused(false)
        setIsReady(false)
        setIsLoading(false)
        // Start tracking playback
        animationFrameRef.current = requestAnimationFrame(updateCurrentWord)
      }

      audio.onpause = () => {
        if (!audio.ended) {
          setIsPaused(true)
          setIsPlaying(false)
        }
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current)
        }
      }

      audio.onended = () => {
        setIsPlaying(false)
        setIsPaused(false)
        setCurrentWordIndex(-1)
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current)
        }
        URL.revokeObjectURL(audioUrl)
      }

      audio.onerror = () => {
        setError('Audio playback failed')
        setIsPlaying(false)
        setIsLoading(false)
        URL.revokeObjectURL(audioUrl)
      }

      // Try to play
      try {
        await audio.play()
      } catch (playErr) {
        if ((playErr as Error).name === 'NotAllowedError') {
          setIsLoading(false)
          setIsReady(true)
        } else {
          throw playErr
        }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        return
      }
      console.error('TTS sync error:', err)
      setError((err as Error).message || 'Failed to generate speech')
      setIsLoading(false)
    }
  }, [currentVoice, playbackRate, updateCurrentWord])

  const play = useCallback(() => {
    if (audioRef.current && isReady) {
      audioRef.current.play()
        .then(() => setIsReady(false))
        .catch(err => {
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
    if (audioRef.current && audioRef.current.paused && isPaused) {
      audioRef.current.play().then(() => {
        animationFrameRef.current = requestAnimationFrame(updateCurrentWord)
      })
    }
  }, [isPaused, updateCurrentWord])

  const stop = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
    }
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
    setCurrentWordIndex(-1)
    setCurrentTime(0)
    setError(null)
  }, [])

  const setVoice = useCallback((voice: string) => {
    setCurrentVoice(voice)
  }, [])

  const setRate = useCallback((rate: number) => {
    setPlaybackRate(rate)
    if (audioRef.current) {
      audioRef.current.playbackRate = rate
    }
  }, [])

  return {
    isLoading,
    isPlaying,
    isPaused,
    isReady,
    error,
    words,
    currentWordIndex,
    currentTime,
    duration,
    currentVoice,
    playbackRate,
    loadAndPlay,
    play,
    pause,
    resume,
    stop,
    setVoice,
    setRate,
  }
}
