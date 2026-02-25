/**
 * Synchronized Text-to-Speech hook with word-level highlighting
 * Fetches audio and word timings, tracks playback for karaoke-style highlighting
 * Uses a persistent Audio element to preserve autoplay permissions across articles
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { authFetch } from '../../../services/api'

export interface WordTiming {
  text: string
  startTime: number
  endTime: number
}

interface TTSSyncResponse {
  audio?: string  // Base64-encoded MP3 (fallback when no article_id)
  audio_url?: string  // Streaming URL (when article_id provided)
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
  volume: number

  // Direct audio access (bypasses React state for smooth animations)
  getPlaybackState: () => { currentTime: number; duration: number }

  // Actions
  loadAndPlay: (text: string, overrideVoice?: string, articleId?: number) => Promise<void>
  play: () => void
  pause: () => void
  resume: () => void
  stop: () => void
  replay: () => void
  seekToWord: (index: number) => void
  seekToTime: (time: number) => void
  skipWords: (count: number) => void
  setVoice: (voice: string) => void
  setRate: (rate: number) => void
  setVolume: (volume: number) => void
  setVolumeImmediate: (volume: number) => void  // GainNode + audio only, no React state (for smooth slider drag)
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
  const [volume, setVolumeState] = useState(() => {
    try {
      const saved = localStorage.getItem('tts-volume')
      if (saved !== null) return parseFloat(saved)
    } catch { /* ignore */ }
    return 1.0
  })

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const animationFrameRef = useRef<number | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Web Audio API refs — GainNode controls volume on iOS WebKit where audio.volume is ignored
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const audioContextRef = useRef<any>(null)
  const gainNodeRef = useRef<GainNode | null>(null)
  const volumeRef = useRef(volume)  // Track volume for non-React access

  // Silent WAV (844 bytes, 0.1s at 8kHz 8-bit mono) — used to clear audio source without
  // "Invalid URI" errors. Firefox requires actual audio samples (not just a header) to decode
  // successfully. This properly clears the media session (AirPods, lock screen, etc.)
  const SILENT_WAV = 'data:audio/wav;base64,UklGRkQDAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YSADAACAg' +
    'ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA' +
    'gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI' +
    'CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA' +
    'gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI' +
    'CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA' +
    'gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI' +
    'CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA' +
    'gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI' +
    'CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA' +
    'gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI' +
    'CAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA=='
  const wordsRef = useRef<WordTiming[]>([])  // Ref to avoid stale closure
  const isAnimatingRef = useRef(false)  // Track if animation loop should run
  const lastFoundIndexRef = useRef(0)  // Track last word index for O(1) search
  const animationEpochRef = useRef(0)  // Epoch counter to kill stale animation loops
  const lastWordIndexRef = useRef(-1)  // Avoid redundant setCurrentWordIndex calls
  const cacheRef = useRef<CachedAudio | null>(null)  // Cache audio for re-play
  const currentAudioUrlRef = useRef<string | null>(null)  // Track current audio URL for cleanup
  const requestIdRef = useRef(0)  // Counter to track current request, ignore errors from stale requests

  // Keep wordsRef in sync with words state
  useEffect(() => {
    wordsRef.current = words
  }, [words])

  // Find the word index for a given time (O(1) typical case, O(n) worst case)
  const findWordIndex = useCallback((time: number): number => {
    const wordList = wordsRef.current
    if (wordList.length === 0) return -1

    const startIdx = Math.max(0, lastFoundIndexRef.current)

    // Check current and forward positions first (most common case)
    for (let i = startIdx; i < wordList.length; i++) {
      if (time >= wordList[i].startTime && time < wordList[i].endTime) {
        return i
      }
      if (time < wordList[i].startTime) {
        return Math.max(0, i - 1)
      }
    }

    // If past all words, use last word
    if (time >= wordList[wordList.length - 1].startTime) {
      return wordList.length - 1
    }

    // Seek backward case - search from beginning
    for (let i = 0; i < startIdx; i++) {
      if (time >= wordList[i].startTime && time < wordList[i].endTime) {
        return i
      }
    }

    return -1
  }, [])

  // Animation loop - uses epoch counter to prevent duplicate loops
  const startAnimationLoop = useCallback(() => {
    // Cancel any pending frame from a previous loop
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }

    isAnimatingRef.current = true
    const epoch = ++animationEpochRef.current  // New epoch kills any stale loops

    const animate = () => {
      // Stale loop check - a newer startAnimationLoop call supersedes this one
      if (epoch !== animationEpochRef.current) return
      if (!isAnimatingRef.current || !audioRef.current) return

      try {
        const time = audioRef.current.currentTime

        const foundIndex = findWordIndex(time)

        if (foundIndex >= 0) {
          lastFoundIndexRef.current = foundIndex
        }

        // Only update React state when the word actually changes
        if (foundIndex !== lastWordIndexRef.current) {
          lastWordIndexRef.current = foundIndex
          setCurrentWordIndex(foundIndex)
        }
      } catch (err) {
        console.error('TTS animation loop error:', err)
        // Don't let exceptions kill the loop - just skip this frame
      }

      // Continue if still animating and audio is playing
      if (epoch === animationEpochRef.current && isAnimatingRef.current &&
          audioRef.current && !audioRef.current.paused) {
        animationFrameRef.current = requestAnimationFrame(animate)
      }
    }

    animationFrameRef.current = requestAnimationFrame(animate)
  }, [findWordIndex])

  const stopAnimationLoop = useCallback(() => {
    isAnimatingRef.current = false
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }
  }, [])

  // Lazily initialize Web Audio API GainNode for iOS volume control.
  // MUST be called from a user gesture handler (click/tap) — iOS suspends
  // AudioContexts created outside user gestures.
  // createMediaElementSource permanently routes audio through the context,
  // so this is a one-time operation on the persistent Audio element.
  const ensureGainNode = useCallback(() => {
    if (!audioRef.current) return
    if (!gainNodeRef.current) {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext
        if (!AudioCtx) return
        const ctx = new AudioCtx()
        const source = ctx.createMediaElementSource(audioRef.current)
        const gain = ctx.createGain()
        source.connect(gain)
        gain.connect(ctx.destination)
        gain.gain.value = volumeRef.current
        audioContextRef.current = ctx
        gainNodeRef.current = gain
      } catch (e) {
        console.warn('AudioContext init failed:', e)
        return
      }
    }
    // Always resume if suspended — a user gesture call can unlock a
    // context that was created outside a gesture (or auto-suspended by iOS)
    if (audioContextRef.current?.state === 'suspended') {
      audioContextRef.current.resume()
    }
  }, [])

  // Initialize persistent audio element once
  useEffect(() => {
    const audio = new Audio()
    audio.volume = volume
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
      // Only set error if we have a valid blob URL audio source
      // Ignore errors from clearing src which can trigger spurious errors
      if (audio.src && audio.src.startsWith('blob:')) {
        setError('Audio playback failed')
        setIsPlaying(false)
        setIsLoading(false)
        stopAnimationLoop()
      }
    }

    audio.onloadedmetadata = () => {
      setDuration(audio.duration)
    }

    // Safety net: timeupdate fires ~4Hz from the browser reliably,
    // even when the tab is backgrounded and rAF is throttled/stopped.
    // Always push currentTime here so the progress bar never gets stuck.
    audio.ontimeupdate = () => {
      setCurrentTime(audio.currentTime)
      if (!audio.paused && !isAnimatingRef.current) {
        startAnimationLoop()
      }
    }

    // Cleanup on unmount
    return () => {
      stopAnimationLoop()
      audio.pause()
      audio.src = SILENT_WAV
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
      // Close AudioContext if it was created
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {})
        audioContextRef.current = null
        gainNodeRef.current = null
      }
    }
  }, [startAnimationLoop, stopAnimationLoop])

  // Update playback rate when it changes
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.playbackRate = playbackRate
    }
  }, [playbackRate])

  // Update volume when it changes
  useEffect(() => {
    volumeRef.current = volume
    if (gainNodeRef.current) {
      gainNodeRef.current.gain.value = volume
    }
    if (audioRef.current) {
      audioRef.current.volume = volume
    }
  }, [volume])

  const loadAndPlay = useCallback(async (text: string, overrideVoice?: string, articleId?: number) => {
    const audio = audioRef.current
    if (!audio) return

    // Initialize GainNode on first call (user gesture context required for iOS)
    ensureGainNode()

    // Increment request ID - any errors from previous requests will be ignored
    const thisRequestId = ++requestIdRef.current

    // Stop any existing playback and CLEAR the audio source
    // This prevents stale audio from being playable via media controls
    stopAnimationLoop()
    audio.pause()
    audio.src = SILENT_WAV  // Clear previous audio without "Invalid URI" errors

    // Abort any in-flight requests
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
    lastFoundIndexRef.current = 0
    lastWordIndexRef.current = -1
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

    const MAX_RETRIES = 2
    const BACKOFF_BASE_MS = 1000  // 1s, 2s, 4s backoff

    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      // Check if a newer request has started - if so, exit silently
      if (thisRequestId !== requestIdRef.current) {
        return  // Don't update any state - newer request owns it now
      }

      try {
        abortControllerRef.current = new AbortController()

        // Add timeout - abort if TTS takes longer than 90 seconds
        // (edge_tts on t2.micro can take 25-50s for long uncached articles)
        const timeoutId = setTimeout(() => {
          abortControllerRef.current?.abort()
        }, 90000)

        const response = await authFetch('/api/news/tts-sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, voice: voiceToUse, rate: rateStr, ...(articleId ? { article_id: articleId } : {}) }),
          signal: abortControllerRef.current.signal,
        })

        clearTimeout(timeoutId)

        // Check again after async operation
        if (thisRequestId !== requestIdRef.current) return

        if (!response.ok) {
          throw new Error(`TTS request failed: ${response.status}`)
        }

        const data: TTSSyncResponse = await response.json()

        // Check again after async operation
        if (thisRequestId !== requestIdRef.current) return

        // M1+M5: Create audio blob — prefer streaming URL, fall back to direct decode
        let audioBlob: Blob
        if (data.audio_url) {
          // Streaming fetch — no base64 in memory
          const audioResp = await authFetch(data.audio_url, {
            signal: abortControllerRef.current.signal,
          })
          if (!audioResp.ok) throw new Error(`Audio fetch failed: ${audioResp.status}`)
          audioBlob = await audioResp.blob()
        } else if (data.audio) {
          // Fallback: decode base64 directly (no intermediate fetch(data:...))
          const binaryStr = atob(data.audio)
          const bytes = new Uint8Array(binaryStr.length)
          for (let i = 0; i < binaryStr.length; i++) {
            bytes[i] = binaryStr.charCodeAt(i)
          }
          audioBlob = new Blob([bytes], { type: 'audio/mpeg' })
        } else {
          throw new Error('No audio data in response')
        }
        const audioUrl = URL.createObjectURL(audioBlob)

        // Check again after async operation
        if (thisRequestId !== requestIdRef.current) {
          URL.revokeObjectURL(audioUrl)  // Clean up since we won't use it
          return
        }

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

        // Check again after async operation
        if (thisRequestId !== requestIdRef.current) return

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
            if (thisRequestId === requestIdRef.current) {
              setIsLoading(false)
              setIsReady(true)
            }
            return  // Not an error, just needs user interaction
          } else {
            throw playErr
          }
        }
      } catch (err) {
        // If a newer request started, exit silently without setting error
        if (thisRequestId !== requestIdRef.current) {
          return
        }

        const isAbort = (err as Error).name === 'AbortError'

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
  }, [currentVoice, playbackRate, stopAnimationLoop, ensureGainNode])

  const play = useCallback(() => {
    if (audioRef.current && isReady) {
      ensureGainNode()  // User gesture context — safe to init AudioContext
      audioRef.current.play()
        .then(() => setIsReady(false))
        .catch(err => {
          console.error('Play failed:', err)
          setError('Failed to play audio')
        })
    }
  }, [isReady, ensureGainNode])

  const pause = useCallback(() => {
    if (audioRef.current && !audioRef.current.paused) {
      audioRef.current.pause()
    }
  }, [])

  const resume = useCallback(() => {
    if (audioRef.current && audioRef.current.paused && isPaused) {
      ensureGainNode()
      audioRef.current.play()
    }
  }, [isPaused, ensureGainNode])

  const stop = useCallback(() => {
    // Init/resume GainNode here — stop() is called synchronously from user
    // gesture handlers (startPlaylist, playArticle) BEFORE any async gaps
    ensureGainNode()
    stopAnimationLoop()
    // Increment request ID to invalidate any in-flight requests
    requestIdRef.current++
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      // CRITICAL: Clear the audio source to fully release the old audio
      // This prevents AirPods/media controls from playing stale audio
      audioRef.current.src = SILENT_WAV
    }
    setIsPlaying(false)
    setIsPaused(false)
    setIsLoading(false)
    setIsReady(false)
    setCurrentWordIndex(-1)
    lastFoundIndexRef.current = 0
    lastWordIndexRef.current = -1
    setCurrentTime(0)
    setDuration(0)
    setWords([])  // Clear words to prevent stale state
    wordsRef.current = []
    setError(null)
  }, [stopAnimationLoop, ensureGainNode])

  const replay = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.currentTime = 0
      setCurrentTime(0)
      setCurrentWordIndex(0)
      lastFoundIndexRef.current = 0
      lastWordIndexRef.current = 0
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
    lastFoundIndexRef.current = clampedIndex
    lastWordIndexRef.current = clampedIndex

    // If paused, start playing from the new position
    if (audioRef.current.paused) {
      audioRef.current.play().catch(err => {
        console.error('Seek play failed:', err)
        setError('Failed to play audio')
      })
    }
  }, [])

  // Seek to a specific time (seconds) - finds the nearest word and seeks there
  const seekToTime = useCallback((targetTime: number) => {
    if (!audioRef.current) return
    const wordList = wordsRef.current
    if (wordList.length === 0) {
      // No words, just seek the audio directly
      audioRef.current.currentTime = targetTime
      setCurrentTime(targetTime)
      return
    }
    // Find the word that contains or is nearest to targetTime
    let bestIdx = 0
    for (let i = 0; i < wordList.length; i++) {
      if (targetTime >= wordList[i].startTime) {
        bestIdx = i
      } else {
        break
      }
    }
    seekToWord(bestIdx)
  }, [seekToWord])

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

  const setVolume = useCallback((vol: number) => {
    const clamped = Math.max(0, Math.min(1, vol))
    volumeRef.current = clamped
    setVolumeState(clamped)
    // User gesture (slider/mute click) can resume a suspended AudioContext
    ensureGainNode()
    // GainNode for iOS WebKit (audio.volume is ignored)
    if (gainNodeRef.current) {
      gainNodeRef.current.gain.value = clamped
    }
    if (audioRef.current) {
      audioRef.current.volume = clamped
    }
    try {
      localStorage.setItem('tts-volume', String(clamped))
    } catch { /* ignore */ }
  }, [ensureGainNode])

  // Lightweight volume update — only touches audio refs, no React state or localStorage.
  // Used during slider drag for zero-latency volume changes without re-renders.
  const setVolumeImmediate = useCallback((vol: number) => {
    const clamped = Math.max(0, Math.min(1, vol))
    volumeRef.current = clamped
    if (gainNodeRef.current) {
      gainNodeRef.current.gain.value = clamped
    }
    if (audioRef.current) {
      audioRef.current.volume = clamped
    }
  }, [])

  // Direct audio element access — reads currentTime/duration without React state delay
  const getPlaybackState = useCallback(() => {
    const audio = audioRef.current
    return {
      currentTime: audio ? audio.currentTime : 0,
      duration: (audio && !isNaN(audio.duration)) ? audio.duration : 0,
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
    volume,
    getPlaybackState,
    loadAndPlay,
    play,
    pause,
    resume,
    stop,
    replay,
    seekToWord,
    seekToTime,
    skipWords,
    setVoice,
    setRate,
    setVolume,
    setVolumeImmediate,
  }
}
