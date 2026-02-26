/**
 * Article Section Component
 *
 * Renders the full Articles tab: Read All controls, category/source filters,
 * article grid, pagination, and empty state.
 */

import { useRef, useState, useEffect } from 'react'
import { Newspaper, ExternalLink, Filter, Volume2, AlertCircle, ChevronDown, Crosshair, Eye, EyeOff, Check } from 'lucide-react'
import { useArticleReader, ArticleItem } from '../../../contexts/ArticleReaderContext'
import {
  formatRelativeTime,
  sortSourcesByCategory,
} from '../../../components/news'
import { NewsItem, NewsResponse, NEWS_CATEGORIES, CATEGORY_COLORS, SeenFilter } from '../../../types/newsTypes'
import { cleanupArticleHoverHighlights, highlightArticle, unhighlightArticle, countItemsBySource } from '../helpers'

interface ArticleSectionProps {
  newsData: NewsResponse | undefined
  filteredNews: NewsItem[]
  paginatedNews: NewsItem[]
  selectedCategories: Set<string>
  toggleCategory: (category: string) => void
  toggleAllCategories: () => void
  allCategoriesSelected: boolean
  selectedSources: Set<string>
  toggleSource: (source: string) => void
  toggleAllSources: () => void
  allSourcesSelected: boolean
  seenFilter: SeenFilter
  currentPage: number
  setCurrentPage: (page: number | ((prev: number) => number)) => void
  totalPages: number
  totalFilteredItems: number
  pageSize: number
  markSeen: (contentType: 'article' | 'video', id: number, seen: boolean) => void
  findArticle: (articleUrl: string, addPulse?: boolean) => void
}

export function ArticleSection({
  newsData,
  filteredNews,
  paginatedNews,
  selectedCategories,
  toggleCategory,
  toggleAllCategories,
  allCategoriesSelected,
  selectedSources,
  toggleSource,
  toggleAllSources,
  allSourcesSelected,
  seenFilter,
  currentPage,
  setCurrentPage,
  totalPages,
  totalFilteredItems,
  pageSize,
  markSeen,
  findArticle,
}: ArticleSectionProps) {
  const {
    openArticle,
    startPlaylist: startArticlePlaylist,
    isPlaying: isArticleReaderPlaying,
    currentIndex: articleReaderIndex,
    playlist: articlePlaylist,
    currentArticle,
  } = useArticleReader()

  // Article playlist dropdown state
  const [showArticleDropdown, setShowArticleDropdown] = useState(false)
  const [hoveredArticleIndex, setHoveredArticleIndex] = useState<number | null>(null)
  const [articleDropdownPosition, setArticleDropdownPosition] = useState<{ top: number; right: number } | null>(null)
  const articleDropdownRef = useRef<HTMLDivElement>(null)
  const articleDropdownButtonRef = useRef<HTMLButtonElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!showArticleDropdown) return
    const handleClickOutside = (e: MouseEvent) => {
      if (articleDropdownRef.current && !articleDropdownRef.current.contains(e.target as Node)) {
        setShowArticleDropdown(false)
        setHoveredArticleIndex(null)
        cleanupArticleHoverHighlights()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showArticleDropdown])

  const availableSources = newsData?.sources || []

  /** Convert a NewsItem to ArticleItem for the reader context */
  const toArticleItem = (item: NewsItem): ArticleItem => ({
    id: item.id,
    title: item.title,
    url: item.url,
    source: item.source,
    source_name: item.source_name,
    published: item.published,
    thumbnail: item.thumbnail,
    summary: item.summary,
    category: item.category,
    has_issue: item.has_issue,
  })

  const allArticleItems = filteredNews.map(toArticleItem)

  return (
    <>
      {/* Read All controls */}
      <div className="flex flex-wrap items-center gap-3 bg-slate-800/50 rounded-lg p-3 border border-slate-700">
        <Volume2 className="w-5 h-5 text-green-400" />

        {/* Read All button */}
        <button
          onClick={() => {
            const isBrokenFilter = seenFilter === 'broken'
            startArticlePlaylist(allArticleItems, 0, false, true, false, isBrokenFilter)
          }}
          disabled={filteredNews.length === 0}
          className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-500 disabled:bg-slate-600 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors"
        >
          <Volume2 className="w-4 h-4" />
          <span>{seenFilter === 'broken' ? 'Retry All' : 'Read All'}</span>
        </button>

        {/* Now reading indicator and scroll button */}
        {isArticleReaderPlaying && (
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2 text-sm text-slate-300">
              <span className="text-green-400 font-medium">Now reading:</span>
              <span>{articleReaderIndex + 1} / {articlePlaylist.length}</span>
            </div>
            {currentArticle && (
              <>
                <span className="text-xs text-slate-400 truncate max-w-[200px]">
                  {currentArticle.title}
                </span>
                <button
                  onClick={() => findArticle(currentArticle.url, true)}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 border border-green-500/30 rounded-lg text-green-400 text-sm transition-colors"
                  title="Scroll to currently reading article"
                >
                  <Crosshair className="w-4 h-4" />
                  <span className="hidden sm:inline">Find Reading</span>
                </button>
              </>
            )}
          </div>
        )}

        {/* Start from specific article dropdown */}
        <div className="relative ml-auto" ref={articleDropdownRef}>
          <button
            ref={articleDropdownButtonRef}
            onClick={() => {
              if (showArticleDropdown) {
                setShowArticleDropdown(false)
                setHoveredArticleIndex(null)
                cleanupArticleHoverHighlights()
              } else {
                if (articleDropdownButtonRef.current) {
                  const rect = articleDropdownButtonRef.current.getBoundingClientRect()
                  setArticleDropdownPosition({
                    top: rect.bottom + 8,
                    right: window.innerWidth - rect.right,
                  })
                }
                setShowArticleDropdown(true)
              }
            }}
            className="flex items-center space-x-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-300 transition-colors"
          >
            <span>Start from article...</span>
            <ChevronDown className={`w-4 h-4 transition-transform ${showArticleDropdown ? 'rotate-180' : ''}`} />
          </button>

          {showArticleDropdown && articleDropdownPosition && (
            <div
              className="fixed w-80 max-h-[60vh] overflow-y-auto bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-50"
              style={{ top: articleDropdownPosition.top, right: articleDropdownPosition.right }}
            >
              <div className="p-2 border-b border-slate-700 sticky top-0 bg-slate-800 z-10">
                <p className="text-xs text-slate-400">Click to start reading from article</p>
              </div>
              {filteredNews.map((article, idx) => {
                const isCurrentlyReading = isArticleReaderPlaying && currentArticle?.url === article.url
                return (
                  <button
                    key={`${article.source}-${idx}`}
                    onClick={() => {
                      startArticlePlaylist(allArticleItems, idx, true)
                      setShowArticleDropdown(false)
                      setHoveredArticleIndex(null)
                      cleanupArticleHoverHighlights()
                    }}
                    onMouseEnter={() => {
                      setHoveredArticleIndex(idx)
                      highlightArticle(article.url)
                      findArticle(article.url, false)
                    }}
                    onMouseLeave={() => {
                      setHoveredArticleIndex(null)
                      unhighlightArticle(article.url)
                    }}
                    className={`w-full flex items-start space-x-3 p-3 hover:bg-slate-700 transition-colors text-left ${
                      isCurrentlyReading ? 'bg-green-500/20' : hoveredArticleIndex === idx ? 'bg-green-500/10' : ''
                    }`}
                  >
                    {isCurrentlyReading ? (
                      <span className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center bg-green-500 text-white">
                        <Volume2 className="w-3 h-3 animate-pulse" />
                      </span>
                    ) : (
                      <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                        hoveredArticleIndex === idx ? 'bg-green-500 text-white' : 'bg-slate-600 text-slate-300'
                      }`}>
                        {idx + 1}
                      </span>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm truncate ${isCurrentlyReading ? 'text-green-400 font-medium' : 'text-white'}`}>{article.title}</p>
                      <p className="text-xs text-slate-500">{article.source_name}</p>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Category filter (multi-select) */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-slate-400">Category:</span>
        <button
          onClick={toggleAllCategories}
          className={`px-3 py-1.5 rounded-lg text-sm transition-colors border ${
            allCategoriesSelected
              ? 'bg-white/20 text-white border-white/30'
              : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700 border-transparent'
          }`}
        >
          All
        </button>
        {NEWS_CATEGORIES.map((category) => (
          <button
            key={category}
            onClick={() => toggleCategory(category)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors border ${
              selectedCategories.has(category)
                ? CATEGORY_COLORS[category]
                : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700 border-transparent'
            }`}
          >
            {category}
          </button>
        ))}
      </div>

      {/* Source filter (multi-select) */}
      <div className="flex flex-wrap items-center gap-2">
        <Filter className="w-4 h-4 text-slate-400" />
        <button
          onClick={() => toggleAllSources()}
          className={`px-3 py-1.5 rounded-lg text-sm transition-colors border ${
            allSourcesSelected
              ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
              : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700 border-transparent'
          }`}
        >
          All
        </button>
        {sortSourcesByCategory(
          availableSources.filter(source => {
            // Only show sources that have articles in the selected categories
            const categoryNews = (newsData?.news || []).filter(n => selectedCategories.has(n.category))
            return categoryNews.some(n => n.source === source.id)
          }),
        ).map((source) => {
          const categoryNews = (newsData?.news || []).filter(n => selectedCategories.has(n.category))
          const count = countItemsBySource(categoryNews, source.id)
          return (
            <button
              key={source.id}
              onClick={() => toggleSource(source.id)}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors border ${
                (allSourcesSelected || selectedSources.has(source.id))
                  ? CATEGORY_COLORS[source.category || ''] || 'bg-slate-600 text-white border-slate-500'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700 border-transparent'
              }`}
            >
              {source.name.replace('Reddit ', 'r/')} ({count})
            </button>
          )
        })}
      </div>

      {/* News grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {paginatedNews.map((item, index) => {
          const isCurrentlyReading = isArticleReaderPlaying && currentArticle?.url === item.url
          return (
          <div
            key={`${item.source}-${index}`}
            data-article-url={item.url}
            className={`group bg-slate-800 border rounded-lg overflow-hidden transition-all hover:shadow-lg hover:shadow-slate-900/50 relative ${
              isCurrentlyReading
                ? 'border-green-500 ring-2 ring-green-500/30'
                : 'border-slate-700 hover:border-slate-600'
            }`}
          >
            {/* Now Reading badge */}
            {isCurrentlyReading && (
              <div className="absolute top-2 left-2 z-20 flex items-center space-x-1 px-2 py-1 bg-green-600 rounded-full text-xs font-medium text-white shadow-lg">
                <Volume2 className="w-3 h-3 animate-pulse" />
                <span>Now Reading</span>
              </div>
            )}
            {/* Issue badge (takes priority over seen badge) */}
            {item.has_issue && !isCurrentlyReading && (
              <div className="absolute top-2 left-2 z-20 w-6 h-6 bg-amber-600/80 rounded-full flex items-center justify-center" title="Playback issue">
                <AlertCircle className="w-3.5 h-3.5 text-amber-200" />
              </div>
            )}
            {/* Seen badge (only if no issue badge) */}
            {item.is_seen && !item.has_issue && !isCurrentlyReading && (
              <div className="absolute top-2 left-2 z-20 w-6 h-6 bg-slate-700/80 rounded-full flex items-center justify-center">
                <Check className="w-3.5 h-3.5 text-slate-400" />
              </div>
            )}
            {/* Thumbnail with preview/external link buttons */}
            <div className="aspect-video w-full overflow-hidden bg-slate-900 relative">
              {item.thumbnail && (
                <img
                  src={item.thumbnail}
                  alt=""
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none'
                  }}
                />
              )}
              {/* Click overlay to open in article reader */}
              <button
                onClick={() => {
                  openArticle(toArticleItem(item), allArticleItems)
                }}
                className="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/30 transition-colors cursor-pointer"
              />
              {/* Open in new tab button */}
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="absolute top-2 right-2 w-8 h-8 bg-black/70 hover:bg-black/90 rounded-full flex items-center justify-center transition-colors z-10"
                title="Open on website"
              >
                <ExternalLink className="w-4 h-4 text-white" />
              </a>
            </div>

            <button
              onClick={() => {
                openArticle(toArticleItem(item), allArticleItems)
              }}
              className="p-4 space-y-3 text-left w-full cursor-pointer hover:bg-slate-700/30 transition-colors"
            >
              {/* Source badge and time */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium border ${
                      CATEGORY_COLORS[item.category] || 'bg-slate-600 text-slate-300 border-slate-500'
                    }`}
                  >
                    {item.source_name}
                  </span>
                  {!item.content_scrape_allowed && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-900/50 text-amber-400 border border-amber-700/50">
                      Summary only
                    </span>
                  )}
                </div>
                {item.published && (
                  <span className="text-xs text-slate-500">
                    {formatRelativeTime(item.published)}
                  </span>
                )}
              </div>

              {/* Title */}
              <h3 className={`font-medium group-hover:text-blue-400 transition-colors line-clamp-3 ${item.is_seen ? 'text-slate-400' : 'text-white'}`}>
                {item.title}
              </h3>

              {/* Summary */}
              {item.summary && (
                <p className="text-sm text-slate-400 line-clamp-2">{item.summary}</p>
              )}

              {/* Footer: preview indicator + seen toggle */}
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-1 text-xs text-slate-500 group-hover:text-blue-400 transition-colors">
                  <Newspaper className="w-3 h-3" />
                  <span>Click to preview</span>
                </div>
              </div>
            </button>
            {/* Seen toggle button */}
            {item.id != null && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  markSeen('article', item.id!, !item.is_seen)
                }}
                className="absolute bottom-3 right-3 w-7 h-7 rounded-full flex items-center justify-center bg-slate-700/80 hover:bg-slate-600 transition-colors z-10"
                title={item.is_seen ? 'Mark as unread' : 'Mark as read'}
              >
                {item.is_seen
                  ? <EyeOff className="w-3.5 h-3.5 text-slate-400" />
                  : <Eye className="w-3.5 h-3.5 text-slate-400" />
                }
              </button>
            )}
          </div>
        )})}
      </div>

      {/* Pagination controls (client-side - instant page changes) */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center space-x-4 py-6">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            Previous
          </button>
          <div className="flex items-center space-x-2">
            {/* Show page numbers with ellipsis for large page counts */}
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter(pageNum => {
                // Always show first, last, current, and neighbors
                if (pageNum === 1 || pageNum === totalPages) return true
                if (Math.abs(pageNum - currentPage) <= 1) return true
                return false
              })
              .map((pageNum, idx, arr) => (
                <span key={pageNum} className="flex items-center">
                  {/* Add ellipsis if there's a gap */}
                  {idx > 0 && arr[idx - 1] !== pageNum - 1 && (
                    <span className="px-2 text-slate-500">...</span>
                  )}
                  <button
                    onClick={() => setCurrentPage(pageNum)}
                    className={`w-10 h-10 rounded-lg transition-colors ${
                      currentPage === pageNum
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
                    }`}
                  >
                    {pageNum}
                  </button>
                </span>
              ))}
          </div>
          <button
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            Next
          </button>
        </div>
      )}

      {/* Page info */}
      {totalFilteredItems > 0 && (
        <div className="text-center text-sm text-slate-500">
          Showing {((currentPage - 1) * pageSize) + 1}-{Math.min(currentPage * pageSize, totalFilteredItems)} of {totalFilteredItems} articles
          {newsData?.retention_days && (
            <span className="ml-2 text-slate-600">
              (last {newsData.retention_days} days, min 5 per source)
            </span>
          )}
        </div>
      )}

      {/* Empty state */}
      {filteredNews.length === 0 && (
        <div className="text-center py-12">
          <Newspaper className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-400">No news articles found</p>
          {!allSourcesSelected && (
            <button
              onClick={() => toggleAllSources()}
              className="mt-2 text-blue-400 hover:text-blue-300"
            >
              Show all sources
            </button>
          )}
        </div>
      )}
    </>
  )
}
