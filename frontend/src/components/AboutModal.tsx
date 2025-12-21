import { useEffect, useState, useCallback } from 'react'
import { X, RefreshCw, Check, ArrowUp, ChevronDown } from 'lucide-react'

interface VersionInfo {
  version: string
  date: string
  commits: string[]
  is_installed: boolean
}

interface ChangelogData {
  current_version: string
  latest_version: string
  update_available: boolean
  versions: VersionInfo[]
  total_versions: number
  has_more: boolean
}

interface AboutModalProps {
  isOpen: boolean
  onClose: () => void
}

const PAGE_SIZE = 20

export function AboutModal({ isOpen, onClose }: AboutModalProps) {
  const [changelog, setChangelog] = useState<ChangelogData | null>(null)
  const [versions, setVersions] = useState<VersionInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [totalVersions, setTotalVersions] = useState(0)

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setVersions([])
      setOffset(0)
      setHasMore(false)
      fetchChangelog(0, true)
    }
  }, [isOpen])

  const fetchChangelog = useCallback(async (currentOffset: number, isInitial: boolean = false) => {
    if (isInitial) {
      setLoading(true)
    } else {
      setLoadingMore(true)
    }
    setError(null)

    try {
      const response = await fetch(`/api/changelog?limit=${PAGE_SIZE}&offset=${currentOffset}`)
      if (!response.ok) throw new Error('Failed to fetch changelog')
      const data: ChangelogData = await response.json()

      if (isInitial) {
        setChangelog(data)
        setVersions(data.versions)
      } else {
        setVersions(prev => [...prev, ...data.versions])
      }

      setHasMore(data.has_more)
      setTotalVersions(data.total_versions)
      setOffset(currentOffset + data.versions.length)
    } catch (err) {
      setError('Failed to load changelog')
      console.error(err)
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [])

  const loadMore = () => {
    if (!loadingMore && hasMore) {
      fetchChangelog(offset, false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-lg w-full max-w-2xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-slate-700 flex items-center justify-between shrink-0">
          <div>
            <h2 className="text-xl font-bold text-white">About Zenith Grid</h2>
            <p className="text-sm text-slate-400 mt-1">Multi-Strategy Trading Platform</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="w-6 h-6 text-blue-400 animate-spin" />
              <span className="ml-2 text-slate-400">Loading changelog...</span>
            </div>
          ) : error ? (
            <div className="text-center py-8">
              <p className="text-red-400">{error}</p>
              <button
                onClick={() => fetchChangelog(0, true)}
                className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-white text-sm"
              >
                Retry
              </button>
            </div>
          ) : changelog ? (
            <>
              {/* Version Info */}
              <div className="mb-6 p-4 bg-slate-900 rounded-lg">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-slate-400">Installed Version</p>
                    <p className="text-lg font-bold text-white">{changelog.current_version}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-slate-400">Latest Version</p>
                    <p className={`text-lg font-bold ${changelog.update_available ? 'text-yellow-400' : 'text-green-400'}`}>
                      {changelog.latest_version}
                    </p>
                  </div>
                </div>
                {changelog.update_available && (
                  <div className="mt-3 p-3 bg-yellow-900/30 border border-yellow-600/50 rounded text-sm">
                    <div className="flex items-center text-yellow-400">
                      <ArrowUp className="w-4 h-4 mr-2" />
                      <span>Update available! Run <code className="bg-slate-800 px-1 rounded">python3 update.py</code> to upgrade.</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Changelog */}
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white">Version History</h3>
                <span className="text-sm text-slate-500">
                  Showing {versions.length} of {totalVersions} versions
                </span>
              </div>

              <div className="space-y-4">
                {versions.map((version) => (
                  <div
                    key={version.version}
                    className={`p-4 rounded-lg border ${
                      version.is_installed
                        ? 'bg-blue-900/20 border-blue-600/50'
                        : 'bg-slate-900 border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-white">{version.version}</span>
                        {version.is_installed && (
                          <span className="flex items-center text-xs text-green-400 bg-green-900/30 px-2 py-0.5 rounded">
                            <Check className="w-3 h-3 mr-1" />
                            Installed
                          </span>
                        )}
                      </div>
                      {version.date && (
                        <span className="text-sm text-slate-500">{version.date}</span>
                      )}
                    </div>
                    {version.commits.length > 0 ? (
                      <ul className="space-y-1">
                        {version.commits.map((commit, idx) => (
                          <li key={idx} className="text-sm text-slate-300 flex items-start">
                            <span className="text-yellow-500 mr-2">•</span>
                            <span>{commit}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-slate-500 italic">No commits in this release</p>
                    )}
                  </div>
                ))}
              </div>

              {/* Load More Button */}
              {hasMore && (
                <div className="mt-6 text-center">
                  <button
                    onClick={loadMore}
                    disabled={loadingMore}
                    className="inline-flex items-center px-6 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 rounded-lg text-white text-sm transition-colors"
                  >
                    {loadingMore ? (
                      <>
                        <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                        Loading...
                      </>
                    ) : (
                      <>
                        <ChevronDown className="w-4 h-4 mr-2" />
                        Load More ({totalVersions - versions.length} remaining)
                      </>
                    )}
                  </button>
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 shrink-0">
          <p className="text-xs text-slate-500 text-center">
            &copy; {new Date().getFullYear()} Romero Tech Solutions. All rights reserved.
          </p>
        </div>
      </div>
    </div>
  )
}
