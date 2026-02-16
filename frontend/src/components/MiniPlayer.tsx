/**
 * Mini Video Player Component
 * Persistent player that morphs between mini-bar and full modal
 * Single iframe that transforms - no video restart when expanding/collapsing
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { Play, Pause, SkipBack, SkipForward, X, Maximize2, Minimize2, ListVideo, ExternalLink, Volume2, VolumeX } from 'lucide-react'
import { useVideoPlayer } from '../contexts/VideoPlayerContext'
import { videoSourceColors } from './news'

// Format seconds to MM:SS or HH:MM:SS
function formatTime(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

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
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [volume, setVolume] = useState(100)
  const [isMuted, setIsMuted] = useState(false)
  const [showVolumeSlider, setShowVolumeSlider] = useState(false)
  const [hoveredPlaylistIndex, setHoveredPlaylistIndex] = useState<number | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const volumeRef = useRef<HTMLDivElement>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const progressBarRef = useRef<HTMLDivElement>(null)

  // Detect iOS to determine if we need to start muted (iOS autoplay policy requires mute)
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
                (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)

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

  // Seek to position (seconds)
  const seekTo = useCallback((seconds: number) => {
    if (iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        JSON.stringify({ event: 'command', func: 'seekTo', args: [seconds, true] }),
        '*'
      )
      setCurrentTime(seconds)
    }
  }, [])

  // Handle progress bar click for seeking
  const handleProgressClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!progressBarRef.current || duration === 0) return
    const rect = progressBarRef.current.getBoundingClientRect()
    const clickX = e.clientX - rect.left
    const percentage = clickX / rect.width
    const newTime = percentage * duration
    seekTo(newTime)
  }, [duration, seekTo])

  // Set volume (0-100)
  const setPlayerVolume = useCallback((vol: number) => {
    if (iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        JSON.stringify({ event: 'command', func: 'setVolume', args: [vol] }),
        '*'
      )
      setVolume(vol)
      if (vol > 0) setIsMuted(false)
    }
  }, [])

  // Toggle mute
  const toggleMute = useCallback(() => {
    if (iframeRef.current?.contentWindow) {
      const command = isMuted ? 'unMute' : 'mute'
      iframeRef.current.contentWindow.postMessage(
        JSON.stringify({ event: 'command', func: command, args: '' }),
        '*'
      )
      setIsMuted(!isMuted)
    }
  }, [isMuted])

  // Handle volume slider change
  const handleVolumeChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newVolume = parseInt(e.target.value, 10)
    setPlayerVolume(newVolume)
  }, [setPlayerVolume])

  // Clean up hover highlights when dropdown closes
  const cleanupHoverHighlights = useCallback(() => {
    setHoveredPlaylistIndex(null)
    document.querySelectorAll('[data-video-id]').forEach(el => {
      el.classList.remove('ring-4', 'ring-blue-500/50', 'border-blue-500')
    })
  }, [])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowPlaylistDropdown(false)
        cleanupHoverHighlights()
      }
      if (volumeRef.current && !volumeRef.current.contains(e.target as Node)) {
        setShowVolumeSlider(false)
      }
    }
    if (showPlaylistDropdown || showVolumeSlider) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showPlaylistDropdown, showVolumeSlider, cleanupHoverHighlights])

  // Poll for current time and duration from YouTube iframe
  useEffect(() => {
    if (!isPlaying) return

    // Function to poll YouTube for time info
    const pollYouTube = () => {
      if (iframeRef.current?.contentWindow) {
        // Request current time
        iframeRef.current.contentWindow.postMessage(
          JSON.stringify({ event: 'command', func: 'getCurrentTime', args: '' }),
          '*'
        )
        // Request duration
        iframeRef.current.contentWindow.postMessage(
          JSON.stringify({ event: 'command', func: 'getDuration', args: '' }),
          '*'
        )
      }
    }

    // Wait a bit for iframe to load before starting to poll
    const startDelay = setTimeout(() => {
      pollYouTube() // Poll immediately after delay
    }, 1500)

    // Then poll every second
    const pollInterval = setInterval(pollYouTube, 1000)

    return () => {
      clearTimeout(startDelay)
      clearInterval(pollInterval)
    }
  }, [isPlaying, currentVideo?.video_id])

  // Handle YouTube API responses for time/duration
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== 'https://www.youtube.com') return

      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data

        // Handle infoDelivery messages which contain currentTime and duration
        if (data.event === 'infoDelivery' && data.info) {
          if (typeof data.info.currentTime === 'number') {
            setCurrentTime(data.info.currentTime)
          }
          if (typeof data.info.duration === 'number' && data.info.duration > 0) {
            setDuration(data.info.duration)
          }
          if (typeof data.info.volume === 'number') {
            setVolume(data.info.volume)
          }
          if (typeof data.info.muted === 'boolean') {
            setIsMuted(data.info.muted)
          }
        }
      } catch {
        // Not JSON, ignore
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [])

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

  // Reset state when video changes
  useEffect(() => {
    setIsPaused(false)
    setCurrentTime(0)
    setDuration(0)
  }, [currentVideo?.video_id])

  // Listen for YouTube video end events to auto-advance playlist
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== 'https://www.youtube.com') return

      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data

        // YouTube Player API: playerState 0 = ended
        // Extract playerState from either message format (only once to prevent double-advance)
        const playerState = data.info?.playerState ?? (data.event === 'onStateChange' ? data.info : null)
        if (playerState === 0) {
          nextVideo()
        }
      } catch {
        // Not JSON, ignore
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [nextVideo])

  // Subscribe to YouTube iframe events when iframe loads
  useEffect(() => {
    if (!currentVideo) return

    // Function to subscribe to YouTube events
    const subscribeToYouTube = () => {
      if (iframeRef.current?.contentWindow) {
        // Request YouTube to send us state change events and info
        iframeRef.current.contentWindow.postMessage(
          JSON.stringify({
            event: 'listening',
            id: 1,
            channel: 'widget'
          }),
          '*'
        )
      }
    }

    // Subscribe after initial delay, then retry a few times to ensure it catches
    const timer1 = setTimeout(subscribeToYouTube, 1000)
    const timer2 = setTimeout(subscribeToYouTube, 2000)
    const timer3 = setTimeout(subscribeToYouTube, 3000)

    return () => {
      clearTimeout(timer1)
      clearTimeout(timer2)
      clearTimeout(timer3)
    }
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
            : 'bottom-0 left-0 right-0 sm:h-20'
        }`}
      >
        <div className={`h-full bg-slate-800 shadow-2xl flex transition-all duration-300 overflow-hidden ${
          isExpanded
            ? 'flex-col rounded-lg border border-slate-700'
            : 'flex-row border-t border-slate-700'
        }`}>

          {/* Video iframe container - overflow-visible in mini mode to allow hover expansion */}
          <div className={`bg-black flex-shrink-0 transition-all duration-300 ${
            isExpanded
              ? 'flex-1 rounded-t-lg overflow-hidden'
              : 'w-20 h-12 sm:w-28 sm:h-16 my-auto ml-2 sm:ml-4 rounded relative group overflow-visible'
          }`}>
            {/* Video wrapper - scales up 6x on hover in mini mode, positioned absolutely to break out of container */}
            <div className={`bg-black rounded ${
              !isExpanded
                ? 'absolute bottom-0 left-0 w-20 h-12 sm:w-28 sm:h-16 transition-all duration-200 ease-out group-hover:w-[672px] group-hover:h-96 group-hover:z-[100] group-hover:shadow-2xl'
                : 'w-full h-full'
            }`}>
              <iframe
                ref={iframeRef}
                key={`player-${currentVideo.video_id}`}
                src={`https://www.youtube.com/embed/${currentVideo.video_id}?autoplay=1${isIOS ? '&mute=1' : ''}&rel=0&enablejsapi=1&origin=${window.location.origin}`}
                title={currentVideo.title}
                className="w-full h-full rounded"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          </div>

          {/* Controls bar */}
          <div className={`flex transition-all duration-300 ${
            isExpanded
              ? 'flex-col sm:flex-row items-center gap-2 sm:gap-4 p-2 sm:p-4 border-t border-slate-700'
              : 'flex-col flex-1 min-w-0 px-2 sm:px-4 py-2 justify-center gap-0.5 sm:gap-1'
          }`}>
            {/* Video thumbnail (only in expanded, hidden on mobile) */}
            {isExpanded && (
              <div className="relative flex-shrink-0 w-20 h-12 bg-black rounded overflow-hidden hidden sm:block">
                {currentVideo.thumbnail && (
                  <img
                    src={currentVideo.thumbnail}
                    alt=""
                    className="w-full h-full object-cover"
                  />
                )}
              </div>
            )}

            {/* Top row in mini mode: Video info */}
            <div className={`min-w-0 ${isExpanded ? 'w-full sm:w-auto sm:flex-shrink-0 sm:max-w-[12rem]' : 'flex items-center gap-2'}`}>
              <span
                className={`px-1.5 py-0.5 rounded text-xs font-medium border flex-shrink-0 ${
                  videoSourceColors[currentVideo.source] || 'bg-slate-600 text-slate-300'
                }`}
              >
                {currentVideo.channel_name}
              </span>
              <h4 className={`text-sm font-medium text-white truncate ${isExpanded ? 'mt-1' : 'flex-1'}`}>
                {currentVideo.title}
              </h4>
              <span className="text-xs text-slate-500 flex-shrink-0">
                {currentIndex + 1}/{playlist.length}
              </span>
            </div>

            {/* Bottom row in mini mode: Progress bar, time, and controls */}
            <div className={`flex gap-1 sm:gap-2 w-full sm:w-auto ${isExpanded ? 'flex-col sm:flex-row items-center flex-1' : 'flex-col sm:flex-row items-center'}`}>
              {/* Progress bar and time */}
              <div className={`flex items-center gap-2 min-w-0 w-full ${isExpanded ? 'sm:w-auto sm:flex-1' : 'sm:flex-1'}`}>
                {/* Current time */}
                <span className="text-xs text-slate-400 w-10 text-right flex-shrink-0 font-mono">
                  {formatTime(currentTime)}
                </span>

                {/* Progress bar */}
                <div
                  ref={progressBarRef}
                  className="flex-1 h-2 bg-slate-700 rounded-full cursor-pointer group relative"
                  onClick={handleProgressClick}
                >
                  {/* Progress fill */}
                  <div
                    className="h-full bg-red-500 rounded-full transition-all duration-100 relative"
                    style={{ width: duration > 0 ? `${(currentTime / duration) * 100}%` : '0%' }}
                  >
                    {/* Scrubber handle */}
                    <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 w-3 h-3 bg-white rounded-full shadow-md opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>

                  {/* Hover time tooltip - appears on hover */}
                  <div className="absolute -top-8 left-1/2 -translate-x-1/2 px-2 py-1 bg-slate-900 text-xs text-white rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                    {formatTime(currentTime)} / {formatTime(duration)}
                  </div>
                </div>

                {/* Remaining time */}
                <span className="text-xs text-slate-400 w-12 flex-shrink-0 font-mono">
                  -{formatTime(Math.max(0, duration - currentTime))}
                </span>
              </div>

              {/* Volume control */}
              <div className="relative flex-shrink-0" ref={volumeRef}>
                <button
                  onClick={toggleMute}
                  onMouseEnter={() => setShowVolumeSlider(true)}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title={isMuted ? "Unmute" : "Mute"}
                >
                  {isMuted || volume === 0 ? (
                    <VolumeX className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                  ) : (
                    <Volume2 className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                  )}
                </button>

              {/* Volume slider popup */}
              {showVolumeSlider && (
                <div
                  className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 p-3 bg-slate-800 border border-slate-600 rounded-lg shadow-xl"
                  onMouseLeave={() => setShowVolumeSlider(false)}
                >
                  <div className="flex flex-col items-center gap-2">
                    <span className="text-xs text-slate-400">{Math.round(volume)}%</span>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={isMuted ? 0 : volume}
                      onChange={handleVolumeChange}
                      className="h-24 w-2 appearance-none bg-slate-600 rounded-full cursor-pointer"
                      style={{ writingMode: 'vertical-lr', direction: 'rtl' }}
                    />
                  </div>
                </div>
              )}
              </div>

              {/* Controls */}
              <div className={`flex items-center gap-1 flex-shrink-0 ${isExpanded ? 'flex-wrap justify-center sm:justify-start' : 'justify-center sm:justify-start'}`}>
                {/* Previous */}
                <button
                  onClick={previousVideo}
                  disabled={currentIndex === 0}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Previous"
                >
                  <SkipBack className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>

                {/* Play/Pause */}
                <button
                  onClick={togglePlayPause}
                  className={`flex items-center justify-center rounded-full bg-red-600 hover:bg-red-500 text-white transition-colors ${isExpanded ? 'w-12 h-12' : 'w-9 h-9'}`}
                  title={isPaused ? "Play" : "Pause"}
                >
                  {isPaused ? (
                    <Play className={`${isExpanded ? 'w-6 h-6' : 'w-4 h-4'} ml-0.5`} fill="white" />
                  ) : (
                    <Pause className={isExpanded ? 'w-6 h-6' : 'w-4 h-4'} />
                  )}
                </button>

                {/* Next */}
                <button
                  onClick={nextVideo}
                  disabled={currentIndex >= playlist.length - 1}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Next"
                >
                  <SkipForward className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>
              </div>

              {/* Secondary controls */}
              <div className="flex items-center gap-1 flex-shrink-0">
              {/* Playlist dropdown */}
              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => {
                    if (showPlaylistDropdown) {
                      cleanupHoverHighlights()
                    }
                    setShowPlaylistDropdown(!showPlaylistDropdown)
                  }}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Playlist"
                >
                  <ListVideo className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>

                {showPlaylistDropdown && (
                  <div className="fixed bottom-24 right-4 w-80 max-h-96 overflow-y-auto bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-[60]">
                    <div className="p-2 border-b border-slate-700 sticky top-0 bg-slate-800 z-10">
                      <p className="text-xs text-slate-400">Playlist ({playlist.length} videos) - Hover to scroll</p>
                    </div>
                    {playlist.map((video, idx) => (
                      <button
                        key={`playlist-${video.source}-${video.video_id}`}
                        onClick={() => {
                          playVideo(idx)
                          setShowPlaylistDropdown(false)
                          setHoveredPlaylistIndex(null)
                          // Remove any lingering hover highlight
                          document.querySelectorAll('[data-video-id]').forEach(el => {
                            el.classList.remove('ring-4', 'ring-blue-500/50', 'border-blue-500')
                          })
                        }}
                        onMouseEnter={() => {
                          setHoveredPlaylistIndex(idx)
                          // Scroll to and highlight the video in the list
                          const videoElement = document.querySelector(`[data-video-id="${video.video_id}"]`)
                          if (videoElement) {
                            videoElement.scrollIntoView({ behavior: 'smooth', block: 'center' })
                            // Add blue halo effect
                            videoElement.classList.add('ring-4', 'ring-blue-500/50', 'border-blue-500')
                          }
                        }}
                        onMouseLeave={() => {
                          setHoveredPlaylistIndex(null)
                          // Remove blue halo effect
                          const videoElement = document.querySelector(`[data-video-id="${video.video_id}"]`)
                          if (videoElement) {
                            videoElement.classList.remove('ring-4', 'ring-blue-500/50', 'border-blue-500')
                          }
                        }}
                        className={`w-full flex items-start gap-3 p-3 hover:bg-slate-700 transition-colors text-left ${
                          idx === currentIndex ? 'bg-red-500/10 border-l-2 border-red-500' : ''
                        } ${hoveredPlaylistIndex === idx ? 'bg-blue-500/10' : ''}`}
                      >
                        <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                          idx === currentIndex ? 'bg-red-500 text-white' : hoveredPlaylistIndex === idx ? 'bg-blue-500 text-white' : 'bg-slate-600 text-slate-300'
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
                className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                title={isExpanded ? "Minimize" : "Expand"}
              >
                {isExpanded ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-4 h-4" />}
              </button>

              {/* Close */}
              <button
                onClick={closeMiniPlayer}
                className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-red-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                title="Close"
              >
                <X className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
              </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Spacer to prevent content from being hidden behind mini-player */}
      <div className="h-24 sm:h-20" />
    </>
  )
}
