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

interface CachedAudio {
  cacheKey: string
  audioUrl: string
  words: WordTiming[]
  duration: number
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
  loadAndPlay: (text: string, overrideVoice?: string) => Promise<void>
  play: () => void
  pause: () => void
  resume: () => void
  stop: () => void
  replay: () => void
  seekToWord: (index: number) => void
  skipWords: (count: number) => void
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
  const wordsRef = useRef<WordTiming[]>([])  // Ref to avoid stale closure
  const isAnimatingRef = useRef(false)  // Track if animation loop should run
  const cacheRef = useRef<CachedAudio | null>(null)  // Cache audio for re-play

  // Keep wordsRef in sync with words state
  useEffect(() => {
    wordsRef.current = words
  }, [words])

  // Animation loop - uses refs to avoid stale closures
  const startAnimationLoop = useCallback(() => {
    isAnimatingRef.current = true

    const animate = () => {
      if (!isAnimatingRef.current || !audioRef.current) return

      const time = audioRef.current.currentTime
      setCurrentTime(time)

      // Find the word that contains the current time
      const wordList = wordsRef.current
      let foundIndex = -1

      for (let i = 0; i < wordList.length; i++) {
        if (time >= wordList[i].startTime && time < wordList[i].endTime) {
          foundIndex = i
          break
        }
        // Also check if we're between words (use the previous word)
        if (i > 0 && time >= wordList[i - 1].endTime && time < wordList[i].startTime) {
          foundIndex = i - 1
          break
        }
      }

      // If past all words, use last word
      if (foundIndex === -1 && wordList.length > 0 && time >= wordList[wordList.length - 1].startTime) {
        foundIndex = wordList.length - 1
      }

      setCurrentWordIndex(foundIndex)

      // Continue if still animating and audio is playing
      if (isAnimatingRef.current && audioRef.current && !audioRef.current.paused) {
        animationFrameRef.current = requestAnimationFrame(animate)
      }
    }

    animationFrameRef.current = requestAnimationFrame(animate)
  }, [])

  const stopAnimationLoop = useCallback(() => {
    isAnimatingRef.current = false
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopAnimationLoop()
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ''
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      // Revoke cached audio URL on unmount
      if (cacheRef.current) {
        URL.revokeObjectURL(cacheRef.current.audioUrl)
        cacheRef.current = null
      }
    }
  }, [stopAnimationLoop])

  // Helper to create and setup audio element
  const setupAudio = useCallback((audioUrl: string, cachedWords: WordTiming[], cachedDuration?: number) => {
    const audio = new Audio(audioUrl)
    audio.playbackRate = playbackRate
    audioRef.current = audio

    // Set words immediately
    setWords(cachedWords)
    wordsRef.current = cachedWords

    if (cachedDuration) {
      setDuration(cachedDuration)
    }

    audio.onloadedmetadata = () => {
      setDuration(audio.duration)
    }

    audio.onplay = () => {
      setIsPlaying(true)
      setIsPaused(false)
      setIsReady(false)
      setIsLoading(false)
      startAnimationLoop()
    }

    audio.onpause = () => {
      if (!audio.ended) {
        setIsPaused(true)
        setIsPlaying(false)
      }
      stopAnimationLoop()
    }

    audio.onended = () => {
      setIsPlaying(false)
      setIsPaused(false)
      setCurrentWordIndex(-1)
      stopAnimationLoop()
      // Don't revoke URL - keep in cache for re-play
    }

    audio.onerror = () => {
      setError('Audio playback failed')
      setIsPlaying(false)
      setIsLoading(false)
      stopAnimationLoop()
    }

    return audio
  }, [playbackRate, startAnimationLoop, stopAnimationLoop])

  const loadAndPlay = useCallback(async (text: string, overrideVoice?: string) => {
    // Stop any existing playback
    stopAnimationLoop()
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.src = ''
      audioRef.current = null
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    // Use override voice if provided, otherwise use current state
    const voiceToUse = overrideVoice || currentVoice

    // Update the voice state if override was provided
    if (overrideVoice && overrideVoice !== currentVoice) {
      setCurrentVoice(overrideVoice)
    }

    setError(null)
    setIsPlaying(false)
    setIsPaused(false)
    setIsReady(false)
    setCurrentWordIndex(-1)
    setCurrentTime(0)

    // Generate cache key from text + voice + rate
    const ratePercent = Math.round((playbackRate - 1) * 100)
    const rateStr = ratePercent >= 0 ? `+${ratePercent}%` : `${ratePercent}%`
    const cacheKey = `${text}|${voiceToUse}|${rateStr}`

    // Check cache
    if (cacheRef.current && cacheRef.current.cacheKey === cacheKey) {
      // Use cached audio
      const audio = setupAudio(cacheRef.current.audioUrl, cacheRef.current.words, cacheRef.current.duration)

      try {
        await audio.play()
      } catch (playErr) {
        if ((playErr as Error).name === 'NotAllowedError') {
          setIsReady(true)
        } else {
          console.error('Cached play failed:', playErr)
          setError('Failed to play audio')
        }
      }
      return
    }

    // Need to fetch new audio
    setIsLoading(true)
    setWords([])

    try {
      abortControllerRef.current = new AbortController()

      const params = new URLSearchParams({
        text,
        voice: voiceToUse,
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

      // Create audio from base64
      const audioBlob = await fetch(`data:audio/mpeg;base64,${data.audio}`).then(r => r.blob())
      const audioUrl = URL.createObjectURL(audioBlob)

      // Revoke old cache URL if exists
      if (cacheRef.current) {
        URL.revokeObjectURL(cacheRef.current.audioUrl)
      }

      const audio = setupAudio(audioUrl, data.words)

      // Wait for duration to be set
      await new Promise<void>((resolve) => {
        if (audio.duration) {
          resolve()
        } else {
          const originalOnLoadedMetadata = audio.onloadedmetadata
          audio.onloadedmetadata = (e) => {
            if (originalOnLoadedMetadata) {
              (originalOnLoadedMetadata as EventListener)(e)
            }
            resolve()
          }
        }
      })

      // Store in cache
      cacheRef.current = {
        cacheKey,
        audioUrl,
        words: data.words,
        duration: audio.duration,
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
  }, [currentVoice, playbackRate, setupAudio, stopAnimationLoop])

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
      audioRef.current.play()
    }
  }, [isPaused])

  const stop = useCallback(() => {
    stopAnimationLoop()
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
  }, [stopAnimationLoop])

  const replay = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.currentTime = 0
      setCurrentTime(0)
      setCurrentWordIndex(0)
      if (audioRef.current.paused) {
        audioRef.current.play().catch(err => {
          console.error('Replay failed:', err)
          setError('Failed to replay audio')
        })
      }
    }
  }, [])

  const seekToWord = useCallback((index: number) => {
    if (!audioRef.current || wordsRef.current.length === 0) return

    const wordList = wordsRef.current
    const clampedIndex = Math.max(0, Math.min(index, wordList.length - 1))
    const targetTime = wordList[clampedIndex].startTime

    audioRef.current.currentTime = targetTime
    setCurrentTime(targetTime)
    setCurrentWordIndex(clampedIndex)

    // If paused, start playing from the new position
    if (audioRef.current.paused) {
      audioRef.current.play().catch(err => {
        console.error('Seek play failed:', err)
        setError('Failed to play audio')
      })
    }
  }, [])

  const skipWords = useCallback((count: number) => {
    if (!audioRef.current || wordsRef.current.length === 0) return

    // Find current word index based on current time
    const time = audioRef.current.currentTime
    const wordList = wordsRef.current
    let currentIdx = 0

    for (let i = 0; i < wordList.length; i++) {
      if (time >= wordList[i].startTime) {
        currentIdx = i
      } else {
        break
      }
    }

    // Calculate target index
    const targetIndex = Math.max(0, Math.min(currentIdx + count, wordList.length - 1))
    seekToWord(targetIndex)
  }, [seekToWord])

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
    replay,
    seekToWord,
    skipWords,
    setVoice,
    setRate,
  }
}
