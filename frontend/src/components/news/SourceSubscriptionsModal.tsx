import { useState, useEffect, useMemo } from 'react'
import { X, Newspaper, Video, Check, Loader2, ExternalLink, ChevronDown, ChevronRight, Plus, Trash2, Clock, Search, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import { sourceColors, videoSourceColors } from './newsUtils'
import { authFetch } from '../../services/api'
import { CATEGORY_COLORS, NewsCategory, NEWS_CATEGORIES } from '../../pages/news/types'

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
  user_category: string | null
  retention_days: number | null
}

interface SourceListResponse {
  sources: ContentSource[]
  total: number
  custom_source_count: number
  max_custom_sources: number
}

interface SourceSubscriptionsModalProps {
  isOpen: boolean
  onClose: () => void
}

interface RobotsPolicyResponse {
  domain: string
  robots_found: boolean
  robots_fetch_error: string | null
  rss_allowed: boolean
  scraping_allowed: boolean
  crawl_delay_seconds: number
  summary: string
  can_add: boolean
}

const RETENTION_OPTIONS = [
  { value: null, label: 'Default (14 days)' },
  { value: 3, label: '3 days' },
  { value: 7, label: '7 days' },
  { value: 14, label: '14 days' },
  { value: 30, label: '30 days' },
]

export function SourceSubscriptionsModal({ isOpen, onClose }: SourceSubscriptionsModalProps) {
  const [sources, setSources] = useState<ContentSource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<'news' | 'video'>('news')
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set())
  const [customSourceCount, setCustomSourceCount] = useState(0)
  const [maxCustomSources, setMaxCustomSources] = useState(10)
  const [showAddForm, setShowAddForm] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  const [addLoading, setAddLoading] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [retentionEditId, setRetentionEditId] = useState<number | null>(null)

  // Robots.txt check state
  const [robotsPolicy, setRobotsPolicy] = useState<RobotsPolicyResponse | null>(null)
  const [robotsLoading, setRobotsLoading] = useState(false)
  const [robotsChecked, setRobotsChecked] = useState(false)

  // Add form state
  const [newSource, setNewSource] = useState({
    source_key: '',
    name: '',
    type: 'news' as 'news' | 'video',
    url: '',
    website: '',
    description: '',
    channel_id: '',
    category: 'CryptoCurrency',
  })

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
      const data: SourceListResponse = await response.json()
      setSources(data.sources)
      setCustomSourceCount(data.custom_source_count)
      setMaxCustomSources(data.max_custom_sources)
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

      const response = await authFetch(endpoint, { method: 'POST' })
      if (!response.ok) throw new Error('Failed to update subscription')

      setSources(prev => prev.map(s =>
        s.id === source.id ? { ...s, is_subscribed: !s.is_subscribed } : s
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
        const response = await authFetch(endpoint, { method: 'POST' })
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

  const handleAddSource = async () => {
    setAddError(null)
    setAddLoading(true)
    try {
      const body: Record<string, string | null> = {
        source_key: newSource.source_key || newSource.name.toLowerCase().replace(/[^a-z0-9]+/g, '_'),
        name: newSource.name,
        type: newSource.type,
        url: newSource.url,
        category: newSource.category,
        website: newSource.website || null,
        description: newSource.description || null,
        channel_id: newSource.channel_id || null,
      }
      const response = await authFetch('/api/sources/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to add source')
      }

      // Refresh sources list
      await fetchSources()
      setShowAddForm(false)
      setRobotsPolicy(null)
      setRobotsChecked(false)
      setNewSource({
        source_key: '', name: '', type: 'news', url: '',
        website: '', description: '', channel_id: '', category: 'CryptoCurrency',
      })
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add source')
    } finally {
      setAddLoading(false)
    }
  }

  const handleDeleteSource = async (source: ContentSource) => {
    setDeletingId(source.id)
    try {
      const response = await authFetch(`/api/sources/${source.id}`, { method: 'DELETE' })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to delete source')
      }
      await fetchSources()
    } catch (err) {
      console.error('Failed to delete source:', err)
    } finally {
      setDeletingId(null)
    }
  }

  const handleRetentionChange = async (sourceId: number, days: number | null) => {
    try {
      const response = await authFetch(`/api/sources/${sourceId}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ retention_days: days }),
      })
      if (response.ok) {
        setSources(prev => prev.map(s =>
          s.id === sourceId ? { ...s, retention_days: days } : s
        ))
      }
    } catch (err) {
      console.error('Failed to update retention:', err)
    }
    setRetentionEditId(null)
  }

  const checkRobots = async () => {
    setRobotsLoading(true)
    setRobotsPolicy(null)
    setAddError(null)
    try {
      const response = await authFetch('/api/sources/check-robots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: newSource.url }),
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to check robots.txt')
      }
      const policy: RobotsPolicyResponse = await response.json()
      setRobotsPolicy(policy)
      setRobotsChecked(true)
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to check robots.txt')
    } finally {
      setRobotsLoading(false)
    }
  }

  // Reset robots policy when URL or type changes
  const handleUrlChange = (url: string) => {
    setNewSource(prev => ({ ...prev, url }))
    setRobotsPolicy(null)
    setRobotsChecked(false)
  }

  const handleTypeChange = (type: 'news' | 'video') => {
    setNewSource(prev => ({ ...prev, type }))
    setRobotsPolicy(null)
    setRobotsChecked(false)
  }

  const newsSources = sources.filter(s => s.type === 'news')
  const videoSources = sources.filter(s => s.type === 'video')
  const currentSources = activeTab === 'news' ? newsSources : videoSources

  const groupedSources = useMemo(() => {
    const groups: Record<string, ContentSource[]> = {}
    for (const source of currentSources) {
      const cat = source.category || 'CryptoCurrency'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(source)
    }
    const sortedCategories = Object.keys(groups).sort((a, b) => {
      if (a === 'CryptoCurrency') return -1
      if (b === 'CryptoCurrency') return 1
      return a.localeCompare(b)
    })
    return sortedCategories.map(cat => ({ category: cat, sources: groups[cat] }))
  }, [currentSources])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      <div className="relative bg-slate-800 rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden border border-slate-700 mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div>
            <h2 className="text-xl font-bold text-white">News Sources</h2>
            <p className="text-sm text-slate-400">
              Choose which sources appear in your feed
              {customSourceCount > 0 && (
                <span className="ml-2 text-xs text-amber-400">
                  Custom: {customSourceCount}/{maxCustomSources}
                </span>
              )}
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              className="flex items-center space-x-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm text-white transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Source</span>
            </button>
            <button onClick={onClose} className="p-2 hover:bg-slate-700 rounded-lg transition-colors">
              <X className="w-5 h-5 text-slate-400" />
            </button>
          </div>
        </div>

        {/* Add Custom Source Form */}
        {showAddForm && (
          <div className="p-4 border-b border-slate-700 bg-slate-700/30">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-white">Add Custom Source</h3>
                <span className="text-xs text-slate-400">{customSourceCount}/{maxCustomSources} used</span>
              </div>
              {addError && (
                <div className="px-3 py-2 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-400">
                  {addError}
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="Source name"
                  value={newSource.name}
                  onChange={e => setNewSource(prev => ({ ...prev, name: e.target.value }))}
                  className="bg-slate-700 text-white text-sm rounded-lg px-3 py-2 border border-slate-600 focus:border-blue-500 focus:outline-none"
                />
                <input
                  type="url"
                  placeholder="Feed URL (RSS / YouTube)"
                  value={newSource.url}
                  onChange={e => handleUrlChange(e.target.value)}
                  className="bg-slate-700 text-white text-sm rounded-lg px-3 py-2 border border-slate-600 focus:border-blue-500 focus:outline-none"
                />
                <select
                  value={newSource.type}
                  onChange={e => handleTypeChange(e.target.value as 'news' | 'video')}
                  className="bg-slate-700 text-white text-sm rounded-lg px-3 py-2 border border-slate-600 focus:border-blue-500 focus:outline-none"
                >
                  <option value="news">News (RSS)</option>
                  <option value="video">Video (YouTube)</option>
                </select>
                <select
                  value={newSource.category}
                  onChange={e => setNewSource(prev => ({ ...prev, category: e.target.value }))}
                  className="bg-slate-700 text-white text-sm rounded-lg px-3 py-2 border border-slate-600 focus:border-blue-500 focus:outline-none"
                >
                  {NEWS_CATEGORIES.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </div>
              {newSource.type === 'video' && (
                <input
                  type="text"
                  placeholder="YouTube Channel ID"
                  value={newSource.channel_id}
                  onChange={e => setNewSource(prev => ({ ...prev, channel_id: e.target.value }))}
                  className="w-full bg-slate-700 text-white text-sm rounded-lg px-3 py-2 border border-slate-600 focus:border-blue-500 focus:outline-none"
                />
              )}

              {/* Check Source button — news only */}
              {newSource.type === 'news' && newSource.url && (
                <div className="flex items-center space-x-2">
                  <button
                    onClick={checkRobots}
                    disabled={robotsLoading || !newSource.url}
                    className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-600 hover:bg-slate-500 disabled:bg-slate-700 disabled:cursor-not-allowed rounded-lg text-sm text-white transition-colors"
                  >
                    {robotsLoading
                      ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : <Search className="w-3.5 h-3.5" />
                    }
                    <span>{robotsChecked ? 'Re-check' : 'Check Source'}</span>
                  </button>
                  {!robotsChecked && (
                    <span className="text-xs text-slate-400">Check robots.txt before adding</span>
                  )}
                </div>
              )}

              {/* Robots.txt policy panel */}
              {robotsPolicy && newSource.type === 'news' && (
                <div className={`rounded-lg border p-3 text-sm ${
                  robotsPolicy.rss_allowed && robotsPolicy.scraping_allowed
                    ? 'border-green-500/40 bg-green-500/5'
                    : robotsPolicy.rss_allowed
                      ? 'border-amber-500/40 bg-amber-500/5'
                      : 'border-red-500/40 bg-red-500/5'
                }`}>
                  <div className="flex items-center space-x-2 mb-2">
                    {robotsPolicy.rss_allowed && robotsPolicy.scraping_allowed ? (
                      <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
                    ) : robotsPolicy.rss_allowed ? (
                      <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                    )}
                    <span className={`font-medium ${
                      robotsPolicy.rss_allowed && robotsPolicy.scraping_allowed
                        ? 'text-green-400'
                        : robotsPolicy.rss_allowed
                          ? 'text-amber-400'
                          : 'text-red-400'
                    }`}>
                      {robotsPolicy.domain}
                    </span>
                  </div>
                  <div className="space-y-1 text-xs ml-6">
                    <div className="flex items-center space-x-2">
                      {robotsPolicy.rss_allowed
                        ? <CheckCircle className="w-3 h-3 text-green-400" />
                        : <XCircle className="w-3 h-3 text-red-400" />
                      }
                      <span className={robotsPolicy.rss_allowed ? 'text-green-300' : 'text-red-300'}>
                        RSS Feed Access
                      </span>
                    </div>
                    <div className="flex items-center space-x-2">
                      {robotsPolicy.scraping_allowed
                        ? <CheckCircle className="w-3 h-3 text-green-400" />
                        : <XCircle className="w-3 h-3 text-amber-400" />
                      }
                      <span className={robotsPolicy.scraping_allowed ? 'text-green-300' : 'text-amber-300'}>
                        Article Scraping {!robotsPolicy.scraping_allowed && '(RSS-only mode)'}
                      </span>
                    </div>
                    {robotsPolicy.crawl_delay_seconds > 0 && (
                      <div className="flex items-center space-x-2">
                        <Clock className="w-3 h-3 text-slate-400" />
                        <span className="text-slate-300">
                          {robotsPolicy.crawl_delay_seconds}s crawl delay
                        </span>
                      </div>
                    )}
                    {robotsPolicy.robots_fetch_error && (
                      <div className="flex items-center space-x-2 mt-1">
                        <AlertTriangle className="w-3 h-3 text-amber-400" />
                        <span className="text-amber-300">{robotsPolicy.robots_fetch_error}</span>
                      </div>
                    )}
                    {!robotsPolicy.can_add && (
                      <p className="text-red-300 mt-1">
                        This source blocks bot access and cannot be added.
                      </p>
                    )}
                  </div>
                </div>
              )}

              <div className="flex justify-end space-x-2">
                <button
                  onClick={() => {
                    setShowAddForm(false)
                    setAddError(null)
                    setRobotsPolicy(null)
                    setRobotsChecked(false)
                  }}
                  className="px-3 py-1.5 text-sm text-slate-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddSource}
                  disabled={
                    !newSource.name || !newSource.url || addLoading
                    || customSourceCount >= maxCustomSources
                    || (newSource.type === 'news' && robotsChecked && robotsPolicy !== null && !robotsPolicy.can_add)
                  }
                  className="flex items-center space-x-1 px-4 py-1.5 bg-green-600 hover:bg-green-500 disabled:bg-slate-600 disabled:cursor-not-allowed rounded-lg text-sm text-white transition-colors"
                >
                  {addLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                  <span>Add</span>
                </button>
              </div>
            </div>
          </div>
        )}

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
        <div className="p-4 overflow-y-auto max-h-[calc(80vh-220px)]">
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
                                {!source.is_system && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-400 border border-amber-500/30">
                                    Custom
                                  </span>
                                )}
                                <div className="flex-1 min-w-0">
                                  {source.description && (
                                    <p className="text-xs text-slate-400 truncate">{source.description}</p>
                                  )}
                                </div>
                                {source.website && (
                                  <a
                                    href={source.website}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="p-1 hover:bg-slate-600 rounded transition-colors flex-shrink-0"
                                    onClick={e => e.stopPropagation()}
                                  >
                                    <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
                                  </a>
                                )}
                              </div>

                              <div className="flex items-center space-x-2 flex-shrink-0 ml-2">
                                {/* Retention dropdown */}
                                {retentionEditId === source.id ? (
                                  <select
                                    value={source.retention_days ?? ''}
                                    onChange={e => handleRetentionChange(
                                      source.id,
                                      e.target.value ? parseInt(e.target.value) : null,
                                    )}
                                    onBlur={() => setRetentionEditId(null)}
                                    autoFocus
                                    className="bg-slate-700 text-xs text-white rounded px-1.5 py-1 border border-slate-600 focus:border-blue-500 focus:outline-none"
                                  >
                                    {RETENTION_OPTIONS.map(opt => (
                                      <option key={opt.label} value={opt.value ?? ''}>{opt.label}</option>
                                    ))}
                                  </select>
                                ) : (
                                  <button
                                    onClick={() => setRetentionEditId(source.id)}
                                    className="p-1 hover:bg-slate-600 rounded transition-colors"
                                    title={`Retention: ${source.retention_days ? `${source.retention_days} days` : 'Default'}`}
                                  >
                                    <Clock className={`w-3.5 h-3.5 ${source.retention_days ? 'text-amber-400' : 'text-slate-500'}`} />
                                  </button>
                                )}

                                {/* Delete button for custom sources */}
                                {!source.is_system && (
                                  <button
                                    onClick={() => handleDeleteSource(source)}
                                    disabled={deletingId === source.id}
                                    className="p-1 hover:bg-red-500/20 rounded transition-colors"
                                    title="Remove custom source"
                                  >
                                    {deletingId === source.id
                                      ? <Loader2 className="w-3.5 h-3.5 text-red-400 animate-spin" />
                                      : <Trash2 className="w-3.5 h-3.5 text-red-400" />
                                    }
                                  </button>
                                )}

                                {/* Toggle Switch */}
                                <button
                                  onClick={() => toggleSubscription(source)}
                                  disabled={togglingId === source.id}
                                  className={`relative w-10 h-5 rounded-full transition-colors ${
                                    source.is_subscribed ? 'bg-green-500' : 'bg-slate-600'
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
