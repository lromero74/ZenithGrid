/**
 * Mini Video Player Component
 * Persistent bottom bar for video playback while navigating the app
 */

import { useState, useRef, useEffect } from 'react'
import { Play, Pause, SkipBack, SkipForward, X, Maximize2, ChevronDown, ChevronUp, ListVideo, ExternalLink } from 'lucide-react'
import { useVideoPlayer } from '../contexts/VideoPlayerContext'
import { videoSourceColors, formatRelativeTime } from './news'

export function MiniPlayer() {
  const {
    playlist,
    currentIndex,
    isPlaying,
    showMiniPlayer,
    currentVideo,
    nextVideo,
    previousVideo,
    closeMiniPlayer,
    expandToModal,
    playVideo,
    showModal,
    setShowModal,
  } = useVideoPlayer()

  const [isExpanded, setIsExpanded] = useState(false)
  const [showPlaylistDropdown, setShowPlaylistDropdown] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

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

  // ESC key to close modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && showModal) {
        setShowModal(false)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [showModal, setShowModal])

  // Collapse mini-player when modal opens (so only one video plays)
  useEffect(() => {
    if (showModal) {
      setIsExpanded(false)
    }
  }, [showModal])

  // Don't render if not playing or mini-player is hidden
  if (!isPlaying || !showMiniPlayer || !currentVideo) {
    return null
  }

  return (
    <>
      {/* Mini Player Bar - fixed at bottom */}
      <div className={`fixed bottom-0 left-0 right-0 bg-slate-800 border-t border-slate-700 z-40 transition-all duration-300 ${isExpanded ? 'h-80' : 'h-20'}`}>
        <div className="container mx-auto px-4 h-full flex flex-col">
          {/* Main bar content */}
          <div className="flex items-center h-20 gap-4">
            {/* Video thumbnail */}
            <div className="relative flex-shrink-0 w-28 h-16 bg-black rounded overflow-hidden">
              {currentVideo.thumbnail && (
                <img
                  src={currentVideo.thumbnail}
                  alt=""
                  className="w-full h-full object-cover"
                />
              )}
              {!isExpanded && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/30">
                  <div className="w-8 h-8 bg-red-600 rounded-full flex items-center justify-center">
                    <Play className="w-4 h-4 text-white ml-0.5" fill="white" />
                  </div>
                </div>
              )}
            </div>

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

              {/* Play/Pause - toggles expanded view */}
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-12 h-12 flex items-center justify-center rounded-full bg-red-600 hover:bg-red-500 text-white transition-colors"
                title={isExpanded ? "Collapse" : "Expand"}
              >
                {isExpanded ? (
                  <Pause className="w-6 h-6" />
                ) : (
                  <Play className="w-6 h-6 ml-0.5" fill="white" />
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

              {/* Expand to modal */}
              <button
                onClick={expandToModal}
                className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors"
                title="Expand to full view"
              >
                <Maximize2 className="w-5 h-5" />
              </button>

              {/* Toggle expand bar */}
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors"
                title={isExpanded ? "Collapse" : "Expand player"}
              >
                {isExpanded ? <ChevronDown className="w-5 h-5" /> : <ChevronUp className="w-5 h-5" />}
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

          {/* Expanded content - larger video player */}
          {isExpanded && (
            <div className="flex-1 pb-4">
              <div className="h-full bg-black rounded-lg overflow-hidden">
                <iframe
                  key={`expanded-${currentVideo.video_id}`}
                  src={`https://www.youtube.com/embed/${currentVideo.video_id}?autoplay=1&rel=0&enablejsapi=1&origin=${window.location.origin}`}
                  title={currentVideo.title}
                  className="w-full h-full"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Full Modal View */}
      {showModal && currentVideo && (
        <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg w-full max-w-5xl max-h-[95vh] overflow-hidden shadow-2xl">
            {/* Modal header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 px-3 py-1.5 bg-red-600 rounded-lg">
                  <ListVideo className="w-4 h-4 text-white" />
                  <span className="text-white font-medium text-sm">
                    {currentIndex + 1} / {playlist.length}
                  </span>
                </div>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium border ${
                    videoSourceColors[currentVideo.source] || 'bg-slate-600 text-slate-300'
                  }`}
                >
                  {currentVideo.channel_name}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {/* Skip controls */}
                <button
                  onClick={previousVideo}
                  disabled={currentIndex === 0}
                  className="flex items-center gap-2 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-700/50 disabled:cursor-not-allowed rounded-lg text-white text-sm transition-colors"
                >
                  <SkipBack className="w-4 h-4" />
                </button>
                <button
                  onClick={nextVideo}
                  disabled={currentIndex >= playlist.length - 1}
                  className="flex items-center gap-2 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-700/50 disabled:cursor-not-allowed rounded-lg text-white text-sm transition-colors"
                >
                  <SkipForward className="w-4 h-4" />
                  <span className="hidden sm:inline">Skip</span>
                </button>
                {/* Minimize to mini-player */}
                <button
                  onClick={() => setShowModal(false)}
                  className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-white text-sm transition-colors"
                >
                  Minimize
                </button>
                {/* Close */}
                <button
                  onClick={closeMiniPlayer}
                  className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center transition-colors"
                >
                  <X className="w-5 h-5 text-slate-400" />
                </button>
              </div>
            </div>

            {/* Video player */}
            <div className="aspect-video w-full bg-black">
              <iframe
                key={`modal-${currentVideo.video_id}`}
                src={`https://www.youtube.com/embed/${currentVideo.video_id}?autoplay=1&rel=0&enablejsapi=1&origin=${window.location.origin}`}
                title={currentVideo.title}
                className="w-full h-full"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>

            {/* Video info */}
            <div className="p-4 space-y-3 border-t border-slate-700">
              <h3 className="font-medium text-white text-lg line-clamp-2">
                {currentVideo.title}
              </h3>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 text-sm text-slate-400">
                  {currentVideo.published && (
                    <span>{formatRelativeTime(currentVideo.published)}</span>
                  )}
                </div>
                <a
                  href={currentVideo.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-sm text-slate-400 hover:text-red-400 transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                  <span>Open on YouTube</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Spacer to prevent content from being hidden behind mini-player */}
      <div className={`${isExpanded ? 'h-80' : 'h-20'}`} />
    </>
  )
}
