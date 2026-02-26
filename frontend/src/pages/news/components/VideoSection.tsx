/**
 * Video Section Component
 *
 * Renders the full Videos tab: category/source filters, Play All controls,
 * video grid, pagination, and empty state.
 */

import { useRef, useState, useEffect } from 'react'
import { ExternalLink, Filter, Video, Play, ListVideo, ChevronDown, Crosshair, Check, Eye, EyeOff } from 'lucide-react'
import { useVideoPlayer, VideoItem as ContextVideoItem } from '../../../contexts/VideoPlayerContext'
import {
  formatRelativeTime,
  sortSourcesByCategory,
} from '../../../components/news'
import { VideoItem, VideoResponse, NEWS_CATEGORIES, CATEGORY_COLORS } from '../../../types/newsTypes'
import { cleanupHoverHighlights, highlightVideo, unhighlightVideo, countItemsBySource } from '../helpers'

interface VideoSectionProps {
  videoData: VideoResponse | undefined
  filteredVideos: VideoItem[]
  paginatedVideos: VideoItem[]
  selectedVideoCategories: Set<string>
  toggleVideoCategory: (category: string) => void
  toggleAllVideoCategories: () => void
  allVideoCategoriesSelected: boolean
  selectedVideoSources: Set<string>
  toggleVideoSource: (source: string) => void
  toggleAllVideoSources: () => void
  allVideoSourcesSelected: boolean
  videoPage: number
  setVideoPage: (page: number | ((prev: number) => number)) => void
  videoTotalPages: number
  pageSize: number
  markSeen: (contentType: 'article' | 'video', id: number, seen: boolean) => void
  findVideo: (videoId: string, addPulse?: boolean) => void
}

export function VideoSection({
  videoData,
  filteredVideos,
  paginatedVideos,
  selectedVideoCategories,
  toggleVideoCategory,
  toggleAllVideoCategories,
  allVideoCategoriesSelected,
  selectedVideoSources,
  toggleVideoSource,
  toggleAllVideoSources,
  allVideoSourcesSelected,
  videoPage,
  setVideoPage,
  videoTotalPages,
  pageSize,
  markSeen,
  findVideo,
}: VideoSectionProps) {
  const { startPlaylist, isPlaying: isPlaylistPlaying, currentIndex: playlistIndex, playlist, currentVideo } = useVideoPlayer()

  // Playlist dropdown state
  const [showPlaylistDropdown, setShowPlaylistDropdown] = useState(false)
  const [hoveredPlaylistIndex, setHoveredPlaylistIndex] = useState<number | null>(null)
  const [dropdownPosition, setDropdownPosition] = useState<{ top: number; right: number } | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const dropdownButtonRef = useRef<HTMLButtonElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!showPlaylistDropdown) return
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowPlaylistDropdown(false)
        cleanupHoverHighlights()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showPlaylistDropdown])

  const availableVideoSources = videoData?.sources || []

  // Scroll to currently playing video with pulse effect
  const scrollToPlayingVideo = () => {
    if (!currentVideo) return
    findVideo(currentVideo.video_id, true)
  }

  return (
    <>
      {/* Video category filter (multi-select) */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-slate-400">Category:</span>
        <button
          onClick={toggleAllVideoCategories}
          className={`px-3 py-1.5 rounded-lg text-sm transition-colors border ${
            allVideoCategoriesSelected
              ? 'bg-white/20 text-white border-white/30'
              : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700 border-transparent'
          }`}
        >
          All
        </button>
        {NEWS_CATEGORIES.map((category) => (
          <button
            key={category}
            onClick={() => toggleVideoCategory(category)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors border ${
              selectedVideoCategories.has(category)
                ? CATEGORY_COLORS[category]
                : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700 border-transparent'
            }`}
          >
            {category}
          </button>
        ))}
      </div>

      {/* Video source filter (multi-select) */}
      <div className="flex flex-wrap items-center gap-2">
        <Filter className="w-4 h-4 text-slate-400" />
        <button
          onClick={() => toggleAllVideoSources()}
          className={`px-3 py-1.5 rounded-lg text-sm transition-colors border ${
            allVideoSourcesSelected
              ? 'bg-red-500/20 text-red-400 border-red-500/30'
              : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700 border-transparent'
          }`}
        >
          All
        </button>
        {sortSourcesByCategory(
          availableVideoSources.filter(source => {
            const categoryVideos = (videoData?.videos || []).filter(v => selectedVideoCategories.has(v.category))
            return categoryVideos.some(v => v.source === source.id)
          }),
        ).map((source) => {
          const categoryVideos = (videoData?.videos || []).filter(v => selectedVideoCategories.has(v.category))
          const count = countItemsBySource(categoryVideos, source.id)
          return (
            <button
              key={source.id}
              onClick={() => toggleVideoSource(source.id)}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors border ${
                (allVideoSourcesSelected || selectedVideoSources.has(source.id))
                  ? CATEGORY_COLORS[source.category || ''] || 'bg-slate-600 text-white border-slate-500'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700 border-transparent'
              }`}
            >
              {source.name} ({count})
            </button>
          )
        })}
      </div>

      {/* Auto-play controls */}
      <div className="flex flex-wrap items-center gap-3 bg-slate-800/50 rounded-lg p-3 border border-slate-700">
        <ListVideo className="w-5 h-5 text-red-400" />

        {/* Play All button - opens mini-player */}
        <button
          onClick={() => startPlaylist(filteredVideos as ContextVideoItem[], 0)}
          disabled={filteredVideos.length === 0}
          className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-500 disabled:bg-slate-600 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors"
        >
          <Play className="w-4 h-4" fill="white" />
          <span>Play All</span>
        </button>

        {/* Now playing indicator and scroll button */}
        {isPlaylistPlaying && (
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2 text-sm text-slate-300">
              <span className="text-green-400 font-medium">Now playing:</span>
              <span>{playlistIndex + 1} / {playlist.length}</span>
            </div>
            <button
              onClick={scrollToPlayingVideo}
              className="flex items-center space-x-1.5 px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 border border-red-500/30 rounded-lg text-red-400 text-sm transition-colors"
              title="Scroll to currently playing video"
            >
              <Crosshair className="w-4 h-4" />
              <span className="hidden sm:inline">Find Playing</span>
            </button>
          </div>
        )}

        {/* Position selector dropdown - start from specific video */}
        <div className="relative ml-auto" ref={dropdownRef}>
          <button
            ref={dropdownButtonRef}
            onClick={() => {
              if (showPlaylistDropdown) {
                cleanupHoverHighlights()
                setShowPlaylistDropdown(false)
              } else {
                // Calculate position based on button location
                if (dropdownButtonRef.current) {
                  const rect = dropdownButtonRef.current.getBoundingClientRect()
                  setDropdownPosition({
                    top: rect.bottom + 8, // 8px gap below button
                    right: window.innerWidth - rect.right, // Align right edges
                  })
                }
                setShowPlaylistDropdown(true)
              }
            }}
            className="flex items-center space-x-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-300 transition-colors"
          >
            <span>Start from video...</span>
            <ChevronDown className={`w-4 h-4 transition-transform ${showPlaylistDropdown ? 'rotate-180' : ''}`} />
          </button>

          {showPlaylistDropdown && dropdownPosition && (
            <div
              className="fixed w-80 max-h-[60vh] overflow-y-auto bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-50"
              style={{ top: dropdownPosition.top, right: dropdownPosition.right }}
            >
              <div className="p-2 border-b border-slate-700 sticky top-0 bg-slate-800 z-10">
                <p className="text-xs text-slate-400">Hover to preview - Click to play</p>
              </div>
              {filteredVideos.map((video, idx) => (
                <button
                  key={`${video.source}-${video.video_id}`}
                  onClick={() => {
                    startPlaylist(filteredVideos as ContextVideoItem[], idx, true) // Start expanded
                    setShowPlaylistDropdown(false)
                    cleanupHoverHighlights()
                  }}
                  onMouseEnter={() => {
                    setHoveredPlaylistIndex(idx)
                    // Navigate to correct page, scroll to, and highlight the video in the grid
                    highlightVideo(video.video_id)
                    findVideo(video.video_id, false)
                  }}
                  onMouseLeave={() => {
                    setHoveredPlaylistIndex(null)
                    // Remove blue halo effect
                    unhighlightVideo(video.video_id)
                  }}
                  className={`w-full flex items-start space-x-3 p-3 hover:bg-slate-700 transition-colors text-left ${
                    hoveredPlaylistIndex === idx ? 'bg-blue-500/10' : ''
                  }`}
                >
                  <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                    hoveredPlaylistIndex === idx ? 'bg-blue-500 text-white' : 'bg-slate-600 text-slate-300'
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
      </div>

      {/* Videos grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {paginatedVideos.map((video, idx) => {
          // Use unique key combining source and video_id to avoid collisions
          const uniqueKey = `${video.source}-${video.video_id}`

          // Check if this video is currently playing in the mini player
          const isCurrentlyPlaying = isPlaylistPlaying && currentVideo?.video_id === video.video_id

          // Handler to play this specific video in expanded modal
          // Use absolute index into filteredVideos so the full playlist plays correctly
          const absoluteIdx = (videoPage - 1) * pageSize + idx
          const handlePlayVideo = () => {
            startPlaylist(filteredVideos as ContextVideoItem[], absoluteIdx, true) // true = start expanded
          }

          return (
            <div
              key={uniqueKey}
              data-video-id={video.video_id}
              className={`group bg-slate-800 rounded-lg overflow-hidden transition-all hover:shadow-lg ${
                isCurrentlyPlaying
                  ? 'border-2 border-red-500 ring-4 ring-red-500/30 shadow-lg shadow-red-500/20'
                  : 'border border-slate-700 hover:border-slate-600 hover:shadow-slate-900/50'
              }`}
            >
              {/* Video thumbnail with play button */}
              <div className="aspect-video w-full overflow-hidden bg-slate-900 relative">
                {video.thumbnail && (
                  <img
                    src={video.thumbnail}
                    alt=""
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none'
                    }}
                  />
                )}
                {/* Now Playing badge */}
                {isCurrentlyPlaying && (
                  <div className="absolute top-2 left-2 flex items-center space-x-1.5 px-2 py-1 bg-red-600 rounded-full z-10 animate-pulse">
                    <div className="w-2 h-2 bg-white rounded-full" />
                    <span className="text-xs font-medium text-white">Playing</span>
                  </div>
                )}
                {/* Seen badge */}
                {video.is_seen && !isCurrentlyPlaying && (
                  <div className="absolute top-2 left-2 z-10 w-6 h-6 bg-slate-700/80 rounded-full flex items-center justify-center">
                    <Check className="w-3.5 h-3.5 text-slate-400" />
                  </div>
                )}
                {/* Play button overlay - click to open in expanded modal */}
                <button
                  onClick={handlePlayVideo}
                  className="absolute inset-0 flex items-center justify-center bg-black/30 group-hover:bg-black/40 transition-colors cursor-pointer"
                >
                  <div className="w-14 h-14 bg-red-600 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform">
                    <Play className="w-7 h-7 text-white ml-1" fill="white" />
                  </div>
                </button>
                {/* Open in new tab button */}
                <a
                  href={video.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="absolute top-2 right-2 w-8 h-8 bg-black/70 hover:bg-black/90 rounded-full flex items-center justify-center transition-colors z-10"
                  title="Open on YouTube"
                >
                  <ExternalLink className="w-4 h-4 text-white" />
                </a>
              </div>

              <div className="p-4 space-y-3">
                {/* Channel badge and time */}
                <div className="flex items-center justify-between">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium border ${
                      CATEGORY_COLORS[video.category] || 'bg-slate-600 text-slate-300 border-slate-500'
                    }`}
                  >
                    {video.channel_name}
                  </span>
                  {video.published && (
                    <span className="text-xs text-slate-500">
                      {formatRelativeTime(video.published)}
                    </span>
                  )}
                </div>

                {/* Title */}
                <h3 className={`font-medium line-clamp-2 ${video.is_seen ? 'text-slate-400' : 'text-white'}`}>
                  {video.title}
                </h3>

                {/* Description */}
                {video.description && (
                  <p className="text-sm text-slate-400 line-clamp-2">{video.description}</p>
                )}

                {/* Footer: link + seen toggle */}
                <div className="flex items-center justify-between">
                  <a
                    href={video.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center space-x-1 text-xs text-slate-500 hover:text-red-400 transition-colors"
                  >
                    <ExternalLink className="w-3 h-3" />
                    <span>Open on YouTube</span>
                  </a>
                  {video.id != null && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        markSeen('video', video.id!, !video.is_seen)
                      }}
                      className="w-7 h-7 rounded-full flex items-center justify-center bg-slate-700/80 hover:bg-slate-600 transition-colors"
                      title={video.is_seen ? 'Mark as unwatched' : 'Mark as watched'}
                    >
                      {video.is_seen
                        ? <EyeOff className="w-3.5 h-3.5 text-slate-400" />
                        : <Eye className="w-3.5 h-3.5 text-slate-400" />
                      }
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Video pagination controls */}
      {videoTotalPages > 1 && (
        <div className="flex items-center justify-center space-x-4 py-6">
          <button
            onClick={() => setVideoPage(p => Math.max(1, p - 1))}
            disabled={videoPage === 1}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            Previous
          </button>
          <div className="flex items-center space-x-2">
            {Array.from({ length: videoTotalPages }, (_, i) => i + 1)
              .filter(pageNum => {
                if (pageNum === 1 || pageNum === videoTotalPages) return true
                if (Math.abs(pageNum - videoPage) <= 1) return true
                return false
              })
              .map((pageNum, idx, arr) => (
                <span key={pageNum} className="flex items-center">
                  {idx > 0 && arr[idx - 1] !== pageNum - 1 && (
                    <span className="px-2 text-slate-500">...</span>
                  )}
                  <button
                    onClick={() => setVideoPage(pageNum)}
                    className={`w-10 h-10 rounded-lg transition-colors ${
                      videoPage === pageNum
                        ? 'bg-red-600 text-white'
                        : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
                    }`}
                  >
                    {pageNum}
                  </button>
                </span>
              ))}
          </div>
          <button
            onClick={() => setVideoPage(p => Math.min(videoTotalPages, p + 1))}
            disabled={videoPage === videoTotalPages}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            Next
          </button>
        </div>
      )}

      {/* Video page info */}
      {filteredVideos.length > 0 && (
        <div className="text-center text-sm text-slate-500">
          Showing {((videoPage - 1) * pageSize) + 1}-{Math.min(videoPage * pageSize, filteredVideos.length)} of {filteredVideos.length} videos
        </div>
      )}

      {/* Empty state for videos */}
      {filteredVideos.length === 0 && (
        <div className="text-center py-12">
          <Video className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-400">No videos found</p>
          {!allVideoSourcesSelected && (
            <button
              onClick={() => toggleAllVideoSources()}
              className="mt-2 text-red-400 hover:text-red-300"
            >
              Show all channels
            </button>
          )}
        </div>
      )}
    </>
  )
}
