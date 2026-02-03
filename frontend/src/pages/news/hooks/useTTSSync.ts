/**
 * Synchronized Text-to-Speech hook with word-level highlighting
 * Fetches audio and word timings, tracks playback for karaoke-style highlighting
 * Uses a persistent Audio element to preserve autoplay permissions across articles
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
  const currentAudioUrlRef = useRef<string | null>(null)  // Track current audio URL for cleanup

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

  // Initialize persistent audio element once
  useEffect(() => {
    const audio = new Audio()
    audioRef.current = audio

    audio.onplay = () => {
      setIsPlaying(true)
      setIsPaused(false)
      setIsReady(false)
      setIsLoading(false)
      setError(null)  // Clear any previous error when playback starts
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
    }

    audio.onerror = () => {
      setError('Audio playback failed')
      setIsPlaying(false)
      setIsLoading(false)
      stopAnimationLoop()
    }

    audio.onloadedmetadata = () => {
      setDuration(audio.duration)
    }

    // Cleanup on unmount
    return () => {
      stopAnimationLoop()
      audio.pause()
      audio.src = ''
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      // Revoke cached audio URL on unmount
      if (cacheRef.current) {
        URL.revokeObjectURL(cacheRef.current.audioUrl)
        cacheRef.current = null
      }
      if (currentAudioUrlRef.current) {
        URL.revokeObjectURL(currentAudioUrlRef.current)
        currentAudioUrlRef.current = null
      }
    }
  }, [startAnimationLoop, stopAnimationLoop])

  // Update playback rate when it changes
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.playbackRate = playbackRate
    }
  }, [playbackRate])

  // Track if current request was cancelled by user (vs timeout)
  const userCancelledRef = useRef(false)

  const loadAndPlay = useCallback(async (text: string, overrideVoice?: string) => {
    const audio = audioRef.current
    if (!audio) return

    // Stop any existing playback and CLEAR the audio source
    // This prevents stale audio from being playable via media controls
    stopAnimationLoop()
    audio.pause()
    audio.src = ''  // Clear old audio immediately

    // Use override voice if provided, otherwise use current state
    const voiceToUse = overrideVoice || currentVoice

    // Update the voice state if override was provided
    if (overrideVoice && overrideVoice !== currentVoice) {
      setCurrentVoice(overrideVoice)
    }

    // Mark any in-flight request as user-cancelled before aborting
    userCancelledRef.current = true
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    // Reset for new request
    userCancelledRef.current = false

    setError(null)
    setIsPlaying(false)
    setIsPaused(false)
    setIsReady(false)
    setCurrentWordIndex(-1)
    setCurrentTime(0)
    setDuration(0)
    setWords([])  // Clear words immediately to prevent stale state
    wordsRef.current = []

    // Generate cache key from text + voice + rate
    const ratePercent = Math.round((playbackRate - 1) * 100)
    const rateStr = ratePercent >= 0 ? `+${ratePercent}%` : `${ratePercent}%`
    const cacheKey = `${text}|${voiceToUse}|${rateStr}`

    // Check cache
    if (cacheRef.current && cacheRef.current.cacheKey === cacheKey) {
      // Use cached audio
      setWords(cacheRef.current.words)
      wordsRef.current = cacheRef.current.words
      setDuration(cacheRef.current.duration)

      audio.src = cacheRef.current.audioUrl
      audio.currentTime = 0

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

    // Need to fetch new audio - with retry logic
    setIsLoading(true)

    const MAX_RETRIES = 3
    const BACKOFF_BASE_MS = 1000  // 1s, 2s, 4s backoff

    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      // Check if user cancelled while we were retrying
      if (userCancelledRef.current) {
        setIsLoading(false)
        return
      }

      try {
        abortControllerRef.current = new AbortController()
        let timedOut = false

        // Add timeout - abort if TTS takes longer than 45 seconds
        const timeoutId = setTimeout(() => {
          timedOut = true
          abortControllerRef.current?.abort()
        }, 45000)

        const params = new URLSearchParams({
          text,
          voice: voiceToUse,
          rate: rateStr,
        })

        const response = await fetch(`/api/news/tts-sync?${params.toString()}`, {
          method: 'POST',
          signal: abortControllerRef.current.signal,
        })

        clearTimeout(timeoutId)

        if (!response.ok) {
          throw new Error(`TTS request failed: ${response.status}`)
        }

        const data: TTSSyncResponse = await response.json()

        // Create audio from base64
        const audioBlob = await fetch(`data:audio/mpeg;base64,${data.audio}`).then(r => r.blob())
        const audioUrl = URL.createObjectURL(audioBlob)

        // Revoke old URLs
        if (cacheRef.current && cacheRef.current.audioUrl !== audioUrl) {
          URL.revokeObjectURL(cacheRef.current.audioUrl)
        }
        if (currentAudioUrlRef.current && currentAudioUrlRef.current !== audioUrl) {
          URL.revokeObjectURL(currentAudioUrlRef.current)
        }
        currentAudioUrlRef.current = audioUrl

        // Set words immediately
        setWords(data.words)
        wordsRef.current = data.words

        // Set audio source
        audio.src = audioUrl
        audio.currentTime = 0

        // Wait for duration to be set (with timeout)
        await new Promise<void>((resolve, reject) => {
          const metadataTimeout = setTimeout(() => {
            reject(new Error('Audio metadata load timeout'))
          }, 10000)

          if (audio.duration && !isNaN(audio.duration)) {
            clearTimeout(metadataTimeout)
            setDuration(audio.duration)
            resolve()
          } else {
            const handleMetadata = () => {
              clearTimeout(metadataTimeout)
              setDuration(audio.duration)
              audio.removeEventListener('loadedmetadata', handleMetadata)
              resolve()
            }
            audio.addEventListener('loadedmetadata', handleMetadata)
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
          // Success! Exit the retry loop
          return
        } catch (playErr) {
          if ((playErr as Error).name === 'NotAllowedError') {
            setIsLoading(false)
            setIsReady(true)
            return  // Not an error, just needs user interaction
          } else {
            throw playErr
          }
        }
      } catch (err) {
        const isAbort = (err as Error).name === 'AbortError'

        // If user cancelled (switched articles), exit silently
        if (isAbort && userCancelledRef.current) {
          setIsLoading(false)
          return
        }

        // If this was the last attempt, show error
        if (attempt === MAX_RETRIES - 1) {
          console.error('TTS sync error after retries:', err)
          setError(isAbort ? 'TTS request timed out' : ((err as Error).message || 'Failed to generate speech'))
          setIsLoading(false)
          return
        }

        // Otherwise, wait with exponential backoff before retrying
        const backoffMs = BACKOFF_BASE_MS * Math.pow(2, attempt) + Math.random() * 500
        console.log(`TTS attempt ${attempt + 1} failed, retrying in ${Math.round(backoffMs)}ms...`)
        await new Promise(resolve => setTimeout(resolve, backoffMs))
      }
    }
  }, [currentVoice, playbackRate, stopAnimationLoop])

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
    // Mark as user-cancelled so retry loop exits silently
    userCancelledRef.current = true
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      // CRITICAL: Clear the audio source to fully release the old audio
      // This prevents AirPods/media controls from playing stale audio
      audioRef.current.src = ''
    }
    setIsPlaying(false)
    setIsPaused(false)
    setIsLoading(false)
    setIsReady(false)
    setCurrentWordIndex(-1)
    setCurrentTime(0)
    setDuration(0)
    setWords([])  // Clear words to prevent stale state
    wordsRef.current = []
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
