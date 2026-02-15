import { useState, useEffect, useMemo } from 'react'
import { X, Newspaper, Video, Check, Loader2, ExternalLink, ChevronDown, ChevronRight } from 'lucide-react'
import { sourceColors, videoSourceColors } from './newsUtils'
import { authFetch } from '../../services/api'
import { CATEGORY_COLORS, NewsCategory } from '../../pages/news/types'

interface ContentSource {
  id: number
  source_key: string
  name: string
  type: 'news' | 'video'
  url: string
  website: string | null
  description: string | null
  channel_id: string | null
  is_system: boolean
  is_enabled: boolean
  is_subscribed: boolean
  category: string
}

interface SourceSubscriptionsModalProps {
  isOpen: boolean
  onClose: () => void
}

export function SourceSubscriptionsModal({ isOpen, onClose }: SourceSubscriptionsModalProps) {
  const [sources, setSources] = useState<ContentSource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<'news' | 'video'>('news')
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set())

  // Fetch sources on mount
  useEffect(() => {
    if (isOpen) {
      fetchSources()
    }
  }, [isOpen])

  const fetchSources = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await authFetch('/api/sources/')
      if (!response.ok) throw new Error('Failed to fetch sources')
      const data = await response.json()
      setSources(data.sources)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sources')
    } finally {
      setLoading(false)
    }
  }

  const toggleSubscription = async (source: ContentSource) => {
    setTogglingId(source.id)
    try {
      const endpoint = source.is_subscribed
        ? `/api/sources/${source.id}/unsubscribe`
        : `/api/sources/${source.id}/subscribe`

      const response = await authFetch(endpoint, {
        method: 'POST',
      })
      if (!response.ok) throw new Error('Failed to update subscription')

      // Update local state
      setSources(prev => prev.map(s =>
        s.id === source.id
          ? { ...s, is_subscribed: !s.is_subscribed }
          : s
      ))
    } catch (err) {
      console.error('Failed to toggle subscription:', err)
    } finally {
      setTogglingId(null)
    }
  }

  const toggleCategoryCollapse = (category: string) => {
    setCollapsedCategories(prev => {
      const next = new Set(prev)
      if (next.has(category)) {
        next.delete(category)
      } else {
        next.add(category)
      }
      return next
    })
  }

  const toggleAllInCategory = async (category: string, subscribe: boolean) => {
    const categorySources = currentSources.filter(s => s.category === category)
    const toToggle = categorySources.filter(s => s.is_subscribed !== subscribe)
    if (toToggle.length === 0) return

    for (const source of toToggle) {
      try {
        const endpoint = subscribe
          ? `/api/sources/${source.id}/subscribe`
          : `/api/sources/${source.id}/unsubscribe`
        const response = await authFetch(endpoint, {
          method: 'POST',
        })
        if (response.ok) {
          setSources(prev => prev.map(s =>
            s.id === source.id ? { ...s, is_subscribed: subscribe } : s
          ))
        }
      } catch {
        // Continue with remaining sources
      }
    }
  }

  if (!isOpen) return null

  const newsSources = sources.filter(s => s.type === 'news')
  const videoSources = sources.filter(s => s.type === 'video')
  const currentSources = activeTab === 'news' ? newsSources : videoSources

  // Group sources by category
  const groupedSources = useMemo(() => {
    const groups: Record<string, ContentSource[]> = {}
    for (const source of currentSources) {
      const cat = source.category || 'CryptoCurrency'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(source)
    }
    // Sort categories: CryptoCurrency first, then alphabetically
    const sortedCategories = Object.keys(groups).sort((a, b) => {
      if (a === 'CryptoCurrency') return -1
      if (b === 'CryptoCurrency') return 1
      return a.localeCompare(b)
    })
    return sortedCategories.map(cat => ({ category: cat, sources: groups[cat] }))
  }, [currentSources])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-slate-800 rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden border border-slate-700 mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div>
            <h2 className="text-xl font-bold text-white">News Sources</h2>
            <p className="text-sm text-slate-400">Choose which sources appear in your feed</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex space-x-1 bg-slate-900 p-1 mx-4 mt-4 rounded-lg w-fit">
          <button
            onClick={() => setActiveTab('news')}
            className={`flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'news'
                ? 'bg-blue-500/20 text-blue-400'
                : 'text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            <Newspaper className="w-4 h-4" />
            <span>News ({newsSources.length})</span>
          </button>
          <button
            onClick={() => setActiveTab('video')}
            className={`flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'video'
                ? 'bg-red-500/20 text-red-400'
                : 'text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            <Video className="w-4 h-4" />
            <span>Videos ({videoSources.length})</span>
          </button>
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto max-h-[calc(80vh-180px)]">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <p className="text-red-400 mb-4">{error}</p>
              <button
                onClick={fetchSources}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-white transition-colors"
              >
                Retry
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {groupedSources.map(({ category, sources: categorySources }) => {
                const isCollapsed = collapsedCategories.has(category)
                const subscribedCount = categorySources.filter(s => s.is_subscribed).length
                const allSubscribed = subscribedCount === categorySources.length
                const noneSubscribed = subscribedCount === 0
                const categoryColor = CATEGORY_COLORS[category as NewsCategory] || 'bg-slate-500/20 text-slate-400 border-slate-500/30'

                return (
                  <div key={category} className="rounded-lg border border-slate-700 overflow-hidden">
                    {/* Category header */}
                    <div className="flex items-center justify-between px-3 py-2.5 bg-slate-700/50">
                      <button
                        onClick={() => toggleCategoryCollapse(category)}
                        className="flex items-center space-x-2 flex-1 text-left"
                      >
                        {isCollapsed
                          ? <ChevronRight className="w-4 h-4 text-slate-400" />
                          : <ChevronDown className="w-4 h-4 text-slate-400" />
                        }
                        <span className={`px-2 py-0.5 rounded text-xs font-medium border ${categoryColor}`}>
                          {category}
                        </span>
                        <span className="text-xs text-slate-500">
                          {subscribedCount}/{categorySources.length} subscribed
                        </span>
                      </button>
                      <div className="flex items-center space-x-1">
                        <button
                          onClick={() => toggleAllInCategory(category, true)}
                          disabled={allSubscribed}
                          className="px-2 py-1 text-xs text-green-400 hover:bg-green-500/10 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          All
                        </button>
                        <span className="text-slate-600">|</span>
                        <button
                          onClick={() => toggleAllInCategory(category, false)}
                          disabled={noneSubscribed}
                          className="px-2 py-1 text-xs text-red-400 hover:bg-red-500/10 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          None
                        </button>
                      </div>
                    </div>

                    {/* Category sources */}
                    {!isCollapsed && (
                      <div className="divide-y divide-slate-700/50">
                        {categorySources.map(source => {
                          const colorClass = activeTab === 'news'
                            ? sourceColors[source.source_key] || 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                            : videoSourceColors[source.source_key] || 'bg-slate-500/20 text-slate-400 border-slate-500/30'

                          return (
                            <div
                              key={source.id}
                              className="flex items-center justify-between px-3 py-2.5 hover:bg-slate-700/30 transition-colors"
                            >
                              <div className="flex items-center space-x-3 flex-1 min-w-0">
                                <div className={`px-2 py-0.5 rounded text-xs border whitespace-nowrap ${colorClass}`}>
                                  {source.name}
                                </div>
                                <div className="flex-1 min-w-0">
                                  {source.description && (
                                    <p className="text-xs text-slate-400 truncate">
                                      {source.description}
                                    </p>
                                  )}
                                </div>
                                {source.website && (
                                  <a
                                    href={source.website}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="p-1 hover:bg-slate-600 rounded transition-colors flex-shrink-0"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
                                  </a>
                                )}
                              </div>

                              {/* Toggle Switch */}
                              <button
                                onClick={() => toggleSubscription(source)}
                                disabled={togglingId === source.id}
                                className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ml-2 ${
                                  source.is_subscribed
                                    ? 'bg-green-500'
                                    : 'bg-slate-600'
                                } ${togglingId === source.id ? 'opacity-50' : ''}`}
                              >
                                <div
                                  className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                                    source.is_subscribed ? 'left-5' : 'left-0.5'
                                  } flex items-center justify-center`}
                                >
                                  {togglingId === source.id ? (
                                    <Loader2 className="w-2.5 h-2.5 text-slate-400 animate-spin" />
                                  ) : source.is_subscribed ? (
                                    <Check className="w-2.5 h-2.5 text-green-500" />
                                  ) : null}
                                </div>
                              </button>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 bg-slate-800/50">
          <p className="text-xs text-slate-500 text-center">
            Subscribed sources will appear in your news feed. Unsubscribed sources will be hidden.
          </p>
        </div>
      </div>
    </div>
  )
}
