/**
 * News Filter Bar Component
 *
 * Renders seen/unseen filter pills, full-articles-only toggle, and bulk mark buttons.
 * Used by both Articles and Videos tabs.
 */

import { BookOpen, CheckCheck } from 'lucide-react'
import { NewsItem, VideoItem, SeenFilter } from '../../../types/newsTypes'

interface NewsFilterBarProps {
  activeTab: 'articles' | 'videos'
  seenFilter: SeenFilter
  setSeenFilter: (filter: SeenFilter) => void
  seenVideoFilter: SeenFilter
  setSeenVideoFilter: (filter: SeenFilter) => void
  setCurrentPage: (page: number | ((prev: number) => number)) => void
  setVideoPage: (page: number | ((prev: number) => number)) => void
  fullArticlesOnly: boolean
  setFullArticlesOnly: (value: boolean) => void
  filteredNews: NewsItem[]
  filteredVideos: VideoItem[]
  bulkMarkSeen: (contentType: 'article' | 'video', ids: number[], markAsRead: boolean) => void
}

export function NewsFilterBar({
  activeTab,
  seenFilter,
  setSeenFilter,
  seenVideoFilter,
  setSeenVideoFilter,
  setCurrentPage,
  setVideoPage,
  fullArticlesOnly,
  setFullArticlesOnly,
  filteredNews,
  filteredVideos,
  bulkMarkSeen,
}: NewsFilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Filter pills: All / Unread|Unwatched / Read|Watched / Broken (articles only) */}
      <div className="flex space-x-0.5 bg-slate-800 rounded-lg p-0.5">
        {(activeTab === 'articles'
          ? ['all', 'unseen', 'seen', 'broken'] as SeenFilter[]
          : ['all', 'unseen', 'seen'] as SeenFilter[]
        ).map(f => {
          const active = (activeTab === 'articles' ? seenFilter : seenVideoFilter) === f
          const isVideo = activeTab === 'videos'
          const label = f === 'all' ? 'All'
            : f === 'unseen' ? (isVideo ? 'Unwatched' : 'Unread')
            : f === 'broken' ? 'Broken'
            : (isVideo ? 'Watched' : 'Read')
          return (
            <button
              key={f}
              onClick={() => {
                if (activeTab === 'articles') {
                  setSeenFilter(f)
                  setCurrentPage(1)
                } else {
                  setSeenVideoFilter(f)
                  setVideoPage(1)
                }
              }}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                active
                  ? f === 'broken' ? 'bg-amber-700/60 text-amber-200' : 'bg-slate-600 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-700'
              }`}
            >
              {label}
            </button>
          )
        })}
      </div>

      {/* Full articles only toggle (hide summary-only) */}
      {activeTab === 'articles' && (
        <button
          onClick={() => {
            setFullArticlesOnly(!fullArticlesOnly)
            setCurrentPage(1)
          }}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
            fullArticlesOnly
              ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
              : 'bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 border-slate-700'
          }`}
          title={fullArticlesOnly ? 'Showing full articles only -- click to show all' : 'Hide summary-only articles (sources that block full content)'}
        >
          <BookOpen className="w-3.5 h-3.5" />
          <span>Full articles</span>
        </button>
      )}

      {/* Bulk mark all read/unread */}
      {(() => {
        const items = activeTab === 'articles' ? filteredNews : filteredVideos
        const currentSeenFilter = activeTab === 'articles' ? seenFilter : seenVideoFilter
        const contentType = activeTab === 'articles' ? 'article' as const : 'video' as const
        const ids = items.map(i => i.id).filter((id): id is number => id != null)
        // Show "Mark all read/watched" when not filtering to only seen items, otherwise "Mark all unread/unwatched"
        const markAsRead = currentSeenFilter !== 'seen'
        const isVideo = activeTab === 'videos'
        const seenLabel = markAsRead
          ? (isVideo ? 'Mark all watched' : 'Mark all read')
          : (isVideo ? 'Mark all unwatched' : 'Mark all unread')
        const seenTitle = markAsRead
          ? (isVideo ? 'Mark all visible as watched' : 'Mark all visible as read')
          : (isVideo ? 'Mark all visible as unwatched' : 'Mark all visible as unread')
        return ids.length > 0 ? (
          <button
            onClick={() => bulkMarkSeen(contentType, ids, markAsRead)}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors border border-slate-700"
            title={seenTitle}
          >
            <CheckCheck className="w-3.5 h-3.5" />
            <span>{seenLabel}</span>
          </button>
        ) : null
      })()}
    </div>
  )
}
