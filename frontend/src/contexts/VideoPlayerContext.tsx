/**
 * Video Player Context for persistent video playback.
 * Context + hook only; the provider lives in VideoPlayerProvider.tsx.
 */

import { createContext, useContext } from 'react'

export interface VideoItem {
  id?: number  // DB video ID (for seen tracking)
  title: string
  url: string
  video_id: string
  source: string
  source_name: string
  channel_name: string
  published: string | null
  thumbnail: string | null
  description: string | null
  category?: string
  is_seen?: boolean
}

export interface VideoPlayerContextType {
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

export const VideoPlayerContext = createContext<VideoPlayerContextType | null>(null)

export function useVideoPlayer() {
  const context = useContext(VideoPlayerContext)
  if (!context) {
    throw new Error('useVideoPlayer must be used within VideoPlayerProvider')
  }
  return context
}
