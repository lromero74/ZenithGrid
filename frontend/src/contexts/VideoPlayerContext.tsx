/**
 * Video Player Context for persistent video playback
 * Manages video playlist state across the app for background listening
 */

import { createContext, useContext, useState, useCallback, useRef, useEffect, ReactNode } from 'react'

export interface VideoItem {
  title: string
  url: string
  video_id: string
  source: string
  source_name: string
  channel_name: string
  published: string | null
  thumbnail: string | null
  description: string | null
}

interface VideoPlayerContextType {
  // Playlist state
  playlist: VideoItem[]
  currentIndex: number
  isPlaying: boolean
  showMiniPlayer: boolean
  isExpanded: boolean

  // Actions
  startPlaylist: (videos: VideoItem[], startIndex?: number, startExpanded?: boolean) => void
  stopPlaylist: () => void
  playVideo: (index: number) => void
  nextVideo: () => void
  previousVideo: () => void
  toggleMiniPlayer: () => void
  closeMiniPlayer: () => void
  setExpanded: (expanded: boolean) => void

  // Current video helper
  currentVideo: VideoItem | null
}

const VideoPlayerContext = createContext<VideoPlayerContextType | null>(null)

export function useVideoPlayer() {
  const context = useContext(VideoPlayerContext)
  if (!context) {
    throw new Error('useVideoPlayer must be used within VideoPlayerProvider')
  }
  return context
}

interface VideoPlayerProviderProps {
  children: ReactNode
}

// Storage key for persisting playlist position
const PLAYLIST_STORAGE_KEY = 'crypto-news-video-playlist-position'

export function VideoPlayerProvider({ children }: VideoPlayerProviderProps) {
  const [playlist, setPlaylist] = useState<VideoItem[]>([])
  const [currentIndex, setCurrentIndex] = useState<number>(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [showMiniPlayer, setShowMiniPlayer] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)

  // Ref to hold playlist for use in event handlers
  const playlistRef = useRef<VideoItem[]>([])

  // Ref to debounce nextVideo calls (YouTube sends duplicate end events)
  const lastNextVideoTime = useRef<number>(0)

  // Keep ref in sync
  useEffect(() => {
    playlistRef.current = playlist
  }, [playlist])

  // Load saved playlist position on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(PLAYLIST_STORAGE_KEY)
      if (saved) {
        const position = parseInt(saved, 10)
        if (!isNaN(position) && position >= 0) {
          setCurrentIndex(position)
        }
      }
    } catch {
      // Ignore localStorage errors
    }
  }, [])

  // Save playlist position when it changes
  useEffect(() => {
    if (isPlaying) {
      try {
        localStorage.setItem(PLAYLIST_STORAGE_KEY, currentIndex.toString())
      } catch {
        // Ignore localStorage errors
      }
    }
  }, [currentIndex, isPlaying])

  // Start a new playlist
  const startPlaylist = useCallback((videos: VideoItem[], startIndex: number = 0, startExpanded: boolean = false) => {
    if (videos.length === 0) return
    const clampedIndex = Math.min(Math.max(0, startIndex), videos.length - 1)
    setPlaylist(videos)
    setCurrentIndex(clampedIndex)
    setIsPlaying(true)
    setShowMiniPlayer(true)
    setIsExpanded(startExpanded)
  }, [])

  // Stop playlist and close mini-player
  const stopPlaylist = useCallback(() => {
    setIsPlaying(false)
    setShowMiniPlayer(false)
  }, [])

  // Play specific video in playlist
  const playVideo = useCallback((index: number) => {
    if (index >= 0 && index < playlistRef.current.length) {
      setCurrentIndex(index)
      setIsPlaying(true)
    }
  }, [])

  // Go to next video (with debouncing to prevent YouTube's duplicate end events)
  const nextVideo = useCallback(() => {
    const now = Date.now()
    // Debounce: ignore if called within 500ms of last call
    if (now - lastNextVideoTime.current < 500) {
      return
    }
    lastNextVideoTime.current = now

    if (currentIndex < playlistRef.current.length - 1) {
      setCurrentIndex(prev => prev + 1)
    } else {
      // End of playlist
      setIsPlaying(false)
      setShowMiniPlayer(false)
    }
  }, [currentIndex])

  // Go to previous video
  const previousVideo = useCallback(() => {
    if (currentIndex > 0) {
      setCurrentIndex(prev => prev - 1)
    }
  }, [currentIndex])

  // Toggle mini-player visibility (minimize/restore)
  const toggleMiniPlayer = useCallback(() => {
    setShowMiniPlayer(prev => !prev)
  }, [])

  // Close mini-player (stops playback)
  const closeMiniPlayer = useCallback(() => {
    stopPlaylist()
  }, [stopPlaylist])

  // Get current video
  const currentVideo = playlist.length > 0 && currentIndex < playlist.length
    ? playlist[currentIndex]
    : null

  // Handle YouTube iframe API messages for video end detection
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== 'https://www.youtube.com') return
      if (!isPlaying) return

      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data

        // YouTube Player API event: state 0 = ended
        if (data.event === 'onStateChange' && data.info === 0) {
          nextVideo()
        } else if (data.event === 'infoDelivery' && data.info?.playerState === 0) {
          nextVideo()
        }
      } catch {
        // Not a JSON message, ignore
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [isPlaying, nextVideo])

  const value: VideoPlayerContextType = {
    playlist,
    currentIndex,
    isPlaying,
    showMiniPlayer,
    isExpanded,
    startPlaylist,
    stopPlaylist,
    playVideo,
    nextVideo,
    previousVideo,
    toggleMiniPlayer,
    closeMiniPlayer,
    setExpanded: setIsExpanded,
    currentVideo,
  }

  return (
    <VideoPlayerContext.Provider value={value}>
      {children}
    </VideoPlayerContext.Provider>
  )
}
