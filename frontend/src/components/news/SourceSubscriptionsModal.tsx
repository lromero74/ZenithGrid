import { useState, useEffect } from 'react'
import { X, Newspaper, Video, Check, Loader2, ExternalLink } from 'lucide-react'
import { sourceColors, videoSourceColors } from './newsUtils'
import { useAuth } from '../../contexts/AuthContext'

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
}

interface SourceSubscriptionsModalProps {
  isOpen: boolean
  onClose: () => void
}

export function SourceSubscriptionsModal({ isOpen, onClose }: SourceSubscriptionsModalProps) {
  const { getAccessToken } = useAuth()
  const [sources, setSources] = useState<ContentSource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<'news' | 'video'>('news')

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
      const token = getAccessToken()
      const response = await fetch('/api/sources/', {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      })
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
      const token = getAccessToken()
      const endpoint = source.is_subscribed
        ? `/api/sources/${source.id}/unsubscribe`
        : `/api/sources/${source.id}/subscribe`

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
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

  if (!isOpen) return null

  const newsSources = sources.filter(s => s.type === 'news')
  const videoSources = sources.filter(s => s.type === 'video')
  const currentSources = activeTab === 'news' ? newsSources : videoSources

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
            <div className="space-y-2">
              {currentSources.map(source => {
                const colorClass = activeTab === 'news'
                  ? sourceColors[source.source_key] || 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                  : videoSourceColors[source.source_key] || 'bg-slate-500/20 text-slate-400 border-slate-500/30'

                return (
                  <div
                    key={source.id}
                    className="flex items-center justify-between p-3 bg-slate-700/50 rounded-lg hover:bg-slate-700 transition-colors"
                  >
                    <div className="flex items-center space-x-3 flex-1 min-w-0">
                      <div className={`px-2 py-1 rounded text-xs border ${colorClass}`}>
                        {source.name}
                      </div>
                      <div className="flex-1 min-w-0">
                        {source.description && (
                          <p className="text-sm text-slate-400 truncate">
                            {source.description}
                          </p>
                        )}
                      </div>
                      {source.website && (
                        <a
                          href={source.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1.5 hover:bg-slate-600 rounded transition-colors"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ExternalLink className="w-4 h-4 text-slate-400" />
                        </a>
                      )}
                    </div>

                    {/* Toggle Switch */}
                    <button
                      onClick={() => toggleSubscription(source)}
                      disabled={togglingId === source.id}
                      className={`relative w-12 h-6 rounded-full transition-colors ${
                        source.is_subscribed
                          ? 'bg-green-500'
                          : 'bg-slate-600'
                      } ${togglingId === source.id ? 'opacity-50' : ''}`}
                    >
                      <div
                        className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                          source.is_subscribed ? 'left-6' : 'left-0.5'
                        } flex items-center justify-center`}
                      >
                        {togglingId === source.id ? (
                          <Loader2 className="w-3 h-3 text-slate-400 animate-spin" />
                        ) : source.is_subscribed ? (
                          <Check className="w-3 h-3 text-green-500" />
                        ) : null}
                      </div>
                    </button>
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
