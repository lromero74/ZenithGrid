/**
 * Mini Video Player Component
 * Persistent player that morphs between mini-bar and full modal
 * Single iframe that transforms - no video restart when expanding/collapsing
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { Play, Pause, SkipBack, SkipForward, X, Maximize2, Minimize2, ListVideo, ExternalLink } from 'lucide-react'
import { useVideoPlayer } from '../contexts/VideoPlayerContext'
import { videoSourceColors, formatRelativeTime } from './news'

export function MiniPlayer() {
  const {
    playlist,
    currentIndex,
    isPlaying,
    showMiniPlayer,
    isExpanded,
    setExpanded,
    currentVideo,
    nextVideo,
    previousVideo,
    closeMiniPlayer,
    playVideo,
  } = useVideoPlayer()
  const [showPlaylistDropdown, setShowPlaylistDropdown] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)

  // Toggle play/pause via YouTube iframe API
  const togglePlayPause = useCallback(() => {
    if (iframeRef.current?.contentWindow) {
      const command = isPaused ? 'playVideo' : 'pauseVideo'
      iframeRef.current.contentWindow.postMessage(
        JSON.stringify({ event: 'command', func: command, args: '' }),
        '*'
      )
      setIsPaused(!isPaused)
    }
  }, [isPaused])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowPlaylistDropdown(false)
      }
    }
    if (showPlaylistDropdown) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showPlaylistDropdown])

  // ESC key to collapse (not close)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isExpanded) {
        setExpanded(false)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isExpanded, setExpanded])

  // Reset pause state when video changes
  useEffect(() => {
    setIsPaused(false)
  }, [currentVideo?.video_id])

  // Don't render if not playing or mini-player is hidden
  if (!isPlaying || !showMiniPlayer || !currentVideo) {
    return null
  }

  return (
    <>
      {/* Dark overlay when expanded */}
      {isExpanded && (
        <div
          className="fixed inset-0 bg-black/80 z-40 transition-opacity"
          onClick={() => setExpanded(false)}
        />
      )}

      {/* Player container - morphs between mini-bar and modal */}
      <div
        className={`fixed z-50 transition-all duration-300 ease-in-out ${
          isExpanded
            ? 'inset-4 sm:inset-8 md:inset-12 lg:inset-x-[10%] lg:inset-y-8'
            : 'bottom-0 left-0 right-0 h-20'
        }`}
      >
        <div className={`h-full bg-slate-800 shadow-2xl flex transition-all duration-300 ${
          isExpanded
            ? 'flex-col rounded-lg border border-slate-700'
            : 'flex-row border-t border-slate-700'
        }`}>

          {/* Video iframe container - overflow-visible in mini mode to allow hover expansion */}
          <div className={`bg-black flex-shrink-0 transition-all duration-300 ${
            isExpanded
              ? 'flex-1 rounded-t-lg overflow-hidden'
              : 'w-28 h-16 my-auto ml-4 rounded relative group overflow-visible'
          }`}>
            {/* Video wrapper - scales up 6x on hover in mini mode, positioned absolutely to break out of container */}
            <div className={`bg-black rounded ${
              !isExpanded
                ? 'absolute bottom-0 left-0 w-28 h-16 transition-all duration-200 ease-out group-hover:w-[672px] group-hover:h-96 group-hover:z-[100] group-hover:shadow-2xl'
                : 'w-full h-full'
            }`}>
              <iframe
                ref={iframeRef}
                key={`player-${currentVideo.video_id}`}
                src={`https://www.youtube.com/embed/${currentVideo.video_id}?autoplay=1&rel=0&enablejsapi=1&origin=${window.location.origin}`}
                title={currentVideo.title}
                className="w-full h-full rounded"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          </div>

          {/* Controls bar */}
          <div className={`flex items-center gap-4 transition-all duration-300 ${
            isExpanded
              ? 'p-4 border-t border-slate-700'
              : 'flex-1 px-4'
          }`}>
            {/* Video thumbnail (only in expanded) */}
            {isExpanded && (
              <div className="relative flex-shrink-0 w-20 h-12 bg-black rounded overflow-hidden">
                {currentVideo.thumbnail && (
                  <img
                    src={currentVideo.thumbnail}
                    alt=""
                    className="w-full h-full object-cover"
                  />
                )}
              </div>
            )}

            {/* Video info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`px-1.5 py-0.5 rounded text-xs font-medium border flex-shrink-0 ${
                    videoSourceColors[currentVideo.source] || 'bg-slate-600 text-slate-300'
                  }`}
                >
                  {currentVideo.channel_name}
                </span>
                <span className="text-xs text-slate-500">
                  {currentIndex + 1} / {playlist.length}
                </span>
              </div>
              <h4 className="text-sm font-medium text-white truncate">
                {currentVideo.title}
              </h4>
              {currentVideo.published && (
                <p className="text-xs text-slate-500">
                  {formatRelativeTime(currentVideo.published)}
                </p>
              )}
            </div>

            {/* Controls */}
            <div className="flex items-center gap-2">
              {/* Previous */}
              <button
                onClick={previousVideo}
                disabled={currentIndex === 0}
                className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors"
                title="Previous"
              >
                <SkipBack className="w-5 h-5" />
              </button>

              {/* Play/Pause */}
              <button
                onClick={togglePlayPause}
                className="w-12 h-12 flex items-center justify-center rounded-full bg-red-600 hover:bg-red-500 text-white transition-colors"
                title={isPaused ? "Play" : "Pause"}
              >
                {isPaused ? (
                  <Play className="w-6 h-6 ml-0.5" fill="white" />
                ) : (
                  <Pause className="w-6 h-6" />
                )}
              </button>

              {/* Next */}
              <button
                onClick={nextVideo}
                disabled={currentIndex >= playlist.length - 1}
                className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors"
                title="Next"
              >
                <SkipForward className="w-5 h-5" />
              </button>
            </div>

            {/* Secondary controls */}
            <div className="flex items-center gap-2">
              {/* Playlist dropdown */}
              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => setShowPlaylistDropdown(!showPlaylistDropdown)}
                  className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors"
                  title="Playlist"
                >
                  <ListVideo className="w-5 h-5" />
                </button>

                {showPlaylistDropdown && (
                  <div className="absolute bottom-full right-0 mb-2 w-80 max-h-96 overflow-y-auto bg-slate-800 border border-slate-600 rounded-lg shadow-xl">
                    <div className="p-2 border-b border-slate-700 sticky top-0 bg-slate-800">
                      <p className="text-xs text-slate-400">Playlist ({playlist.length} videos)</p>
                    </div>
                    {playlist.map((video, idx) => (
                      <button
                        key={`playlist-${video.source}-${video.video_id}`}
                        onClick={() => {
                          playVideo(idx)
                          setShowPlaylistDropdown(false)
                        }}
                        className={`w-full flex items-start gap-3 p-3 hover:bg-slate-700 transition-colors text-left ${
                          idx === currentIndex ? 'bg-red-500/10 border-l-2 border-red-500' : ''
                        }`}
                      >
                        <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                          idx === currentIndex ? 'bg-red-500 text-white' : 'bg-slate-600 text-slate-300'
                        }`}>
                          {idx + 1}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-white truncate">{video.title}</p>
                          <p className="text-xs text-slate-500">{video.channel_name}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Open on YouTube (only in expanded) */}
              {isExpanded && (
                <a
                  href={currentVideo.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors"
                  title="Open on YouTube"
                >
                  <ExternalLink className="w-5 h-5" />
                </a>
              )}

              {/* Expand/Minimize toggle */}
              <button
                onClick={() => setExpanded(!isExpanded)}
                className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors"
                title={isExpanded ? "Minimize" : "Expand"}
              >
                {isExpanded ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
              </button>

              {/* Close */}
              <button
                onClick={closeMiniPlayer}
                className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-700 hover:bg-red-600 text-white transition-colors"
                title="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Spacer to prevent content from being hidden behind mini-player */}
      <div className="h-20" />
    </>
  )
}
