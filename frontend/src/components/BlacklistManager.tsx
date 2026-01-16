/**
 * Blacklist Manager Component
 *
 * Manages coin categorization with 4 categories:
 * - APPROVED: Solid projects, allowed to trade
 * - BORDERLINE: Decent but with concerns
 * - QUESTIONABLE: Higher risk projects
 * - BLACKLISTED: Do not trade
 *
 * Category toggles control which categories can open new positions.
 */

import { useState, useEffect, useMemo } from 'react'
import {
  RefreshCw,
  AlertCircle,
  Edit2,
  Check,
  X,
  Search,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  ChevronDown,
  Coins,
} from 'lucide-react'
import { blacklistApi, BlacklistEntry, marketDataApi, CategorySettings, AIProviderSettings } from '../services/api'
import CoinIcon from './CoinIcon'

// Category display config
const CATEGORY_CONFIG: Record<string, { color: string; bgColor: string; borderColor: string; label: string; description: string }> = {
  APPROVED: { color: 'text-green-400', bgColor: 'bg-green-600/20', borderColor: 'border-green-600/50', label: 'Approved', description: 'Solid project, safe to trade' },
  BORDERLINE: { color: 'text-yellow-400', bgColor: 'bg-yellow-600/20', borderColor: 'border-yellow-600/50', label: 'Borderline', description: 'Decent but has concerns' },
  QUESTIONABLE: { color: 'text-orange-400', bgColor: 'bg-orange-600/20', borderColor: 'border-orange-600/50', label: 'Questionable', description: 'Higher risk project' },
  BLACKLISTED: { color: 'text-red-400', bgColor: 'bg-red-600/20', borderColor: 'border-red-600/50', label: 'Blacklisted', description: 'Do not trade' },
}

const CATEGORIES = ['APPROVED', 'BORDERLINE', 'QUESTIONABLE', 'BLACKLISTED']

// Coin with market info
interface CoinInfo {
  symbol: string
  markets: string[]
  product_ids: string[]
}

export function BlacklistManager() {
  const [blacklistedCoins, setBlacklistedCoins] = useState<BlacklistEntry[]>([])
  const [allCoins, setAllCoins] = useState<CoinInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [savingSymbol, setSavingSymbol] = useState<string | null>(null)

  // Category settings (used for fetching, but permissions now handled at bot level)
  const [categorySettings, setCategorySettings] = useState<CategorySettings | null>(null)

  // AI Review
  const [runningAIReview, setRunningAIReview] = useState(false)
  const [aiProviderSettings, setAIProviderSettings] = useState<AIProviderSettings | null>(null)
  const [savingAIProvider, setSavingAIProvider] = useState(false)

  // Filter
  const [searchFilter, setSearchFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)

  // Edit reason
  const [editingSymbol, setEditingSymbol] = useState<string | null>(null)
  const [editReason, setEditReason] = useState('')

  // Category dropdown
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)

  // Fetch data
  const fetchData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const [blacklist, coinsData, categories, aiProvider] = await Promise.all([
        blacklistApi.getAll(),
        marketDataApi.getCoins(),
        blacklistApi.getCategories(),
        blacklistApi.getAIProvider(),
      ])

      setBlacklistedCoins(blacklist)
      setCategorySettings(categories)
      setAllCoins(coinsData.coins)
      setAIProviderSettings(aiProvider)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = () => setOpenDropdown(null)
    if (openDropdown) {
      document.addEventListener('click', handleClickOutside)
      return () => document.removeEventListener('click', handleClickOutside)
    }
  }, [openDropdown])

  // Helper to get category from reason
  const getCategoryFromReason = (reason: string | null): string => {
    if (!reason) return 'BLACKLISTED'
    if (reason.startsWith('[APPROVED]')) return 'APPROVED'
    if (reason.startsWith('[BORDERLINE]')) return 'BORDERLINE'
    if (reason.startsWith('[QUESTIONABLE]')) return 'QUESTIONABLE'
    return 'BLACKLISTED'
  }

  // Helper to get reason text without category prefix
  const getReasonText = (reason: string | null): string => {
    if (!reason) return ''
    return reason.replace(/^\[(APPROVED|BORDERLINE|QUESTIONABLE|BLACKLISTED)\]\s*/, '')
  }

  // Build coin list with categories
  const coinList = useMemo(() => {
    const blacklistMap = new Map(blacklistedCoins.map(c => [c.symbol, c]))

    return allCoins.map(coin => {
      const entry = blacklistMap.get(coin.symbol)
      const category = entry ? getCategoryFromReason(entry.reason) : 'APPROVED'
      const reasonText = entry ? getReasonText(entry.reason) : ''

      return {
        symbol: coin.symbol,
        markets: coin.markets,
        category,
        reasonText,
        id: entry?.id,
        created_at: entry?.created_at,
      }
    })
  }, [allCoins, blacklistedCoins])

  // Filtered coin list
  const filteredCoins = useMemo(() => {
    return coinList.filter(coin => {
      // Category filter
      if (categoryFilter && coin.category !== categoryFilter) return false

      // Search filter
      if (searchFilter) {
        const search = searchFilter.toLowerCase()
        return coin.symbol.toLowerCase().includes(search) ||
               coin.reasonText.toLowerCase().includes(search)
      }

      return true
    })
  }, [coinList, categoryFilter, searchFilter])

  // Count coins by category
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {
      APPROVED: 0,
      BORDERLINE: 0,
      QUESTIONABLE: 0,
      BLACKLISTED: 0,
    }
    for (const coin of coinList) {
      counts[coin.category] = (counts[coin.category] || 0) + 1
    }
    return counts
  }, [coinList])

  // Change coin category
  const changeCoinCategory = async (symbol: string, newCategory: string, currentReasonText: string) => {
    setSavingSymbol(symbol)
    setError(null)
    setOpenDropdown(null)

    try {
      // Build new reason with category prefix
      const newReason = newCategory === 'BLACKLISTED' && !currentReasonText
        ? null
        : `[${newCategory}] ${currentReasonText}`.trim()

      // Check if coin exists in blacklist
      const existingEntry = blacklistedCoins.find(c => c.symbol === symbol)

      if (existingEntry) {
        // Update existing entry
        await blacklistApi.updateReason(symbol, newReason)
      } else {
        // Add new entry
        await blacklistApi.add(symbol, newReason || undefined)
      }

      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update category')
    } finally {
      setSavingSymbol(null)
    }
  }

  // Edit reason
  const startEditReason = (symbol: string, currentReason: string) => {
    setEditingSymbol(symbol)
    setEditReason(currentReason)
  }

  const saveEditReason = async (symbol: string, category: string) => {
    setSavingSymbol(symbol)
    setError(null)

    try {
      const newReason = `[${category}] ${editReason}`.trim()

      const existingEntry = blacklistedCoins.find(c => c.symbol === symbol)
      if (existingEntry) {
        await blacklistApi.updateReason(symbol, newReason)
      } else {
        await blacklistApi.add(symbol, newReason)
      }

      setEditingSymbol(null)
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update reason')
    } finally {
      setSavingSymbol(null)
    }
  }

  // Update AI provider
  const updateAIProvider = async (provider: string) => {
    if (savingAIProvider) return

    setSavingAIProvider(true)
    setError(null)

    try {
      const updated = await blacklistApi.updateAIProvider(provider)
      setAIProviderSettings(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update AI provider')
    } finally {
      setSavingAIProvider(false)
    }
  }

  // Trigger AI review
  const triggerAIReview = async () => {
    if (runningAIReview) return

    setRunningAIReview(true)
    setError(null)

    try {
      await blacklistApi.triggerAIReview()
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run AI review')
    } finally {
      setRunningAIReview(false)
    }
  }

  if (isLoading) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <div className="flex items-center justify-center">
          <RefreshCw className="w-5 h-5 text-slate-400 animate-spin" />
          <span className="ml-2 text-slate-400">Loading coin categories...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <Coins className="w-5 h-5 text-blue-400" />
            Coin Categories
          </h3>
          <p className="text-sm text-slate-400 mt-1">
            Categorize coins and control which categories can trade
          </p>
        </div>
        <button
          onClick={fetchData}
          className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4 text-slate-400" />
        </button>
      </div>

      {/* AI Coin Review */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="font-medium text-white text-sm">Coin Categorization</h4>
            <p className="text-xs text-slate-400">AI-reviewed coin safety categories. Category filters are set per-bot when creating/editing bots.</p>
          </div>
          <div className="flex items-center gap-2">
            {/* AI Provider Selector */}
            {aiProviderSettings && (
              <select
                value={aiProviderSettings.provider}
                onChange={(e) => updateAIProvider(e.target.value)}
                disabled={savingAIProvider || runningAIReview}
                className="px-2 py-1.5 text-sm bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-purple-500 disabled:opacity-50"
                title="Select AI provider for coin review"
              >
                {aiProviderSettings.available_providers.map((provider) => (
                  <option key={provider} value={provider}>
                    {provider.charAt(0).toUpperCase() + provider.slice(1)}
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={triggerAIReview}
              disabled={runningAIReview}
              className="flex items-center gap-2 px-3 py-1.5 text-sm bg-purple-600 hover:bg-purple-700 disabled:bg-slate-700 disabled:text-slate-500 rounded-lg transition-colors"
              title="Run AI to re-categorize all coins"
            >
              <Sparkles className={`w-4 h-4 ${runningAIReview ? 'animate-pulse' : ''}`} />
              {runningAIReview ? 'Reviewing...' : 'AI Review'}
            </button>
          </div>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="flex items-start space-x-2 p-3 bg-red-900/20 border border-red-700 rounded-lg">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {/* Coin List */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
        {/* Filters */}
        <div className="p-3 border-b border-slate-700 space-y-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search coins..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm bg-slate-700 border border-slate-600 rounded-lg focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Category Filter Tabs */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setCategoryFilter(null)}
              className={`px-3 py-1 text-xs rounded-full transition-colors ${
                categoryFilter === null
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              All ({coinList.length})
            </button>
            {CATEGORIES.map((cat) => {
              const config = CATEGORY_CONFIG[cat]
              const count = categoryCounts[cat] || 0
              return (
                <button
                  key={cat}
                  onClick={() => setCategoryFilter(categoryFilter === cat ? null : cat)}
                  className={`px-3 py-1 text-xs rounded-full transition-colors ${
                    categoryFilter === cat
                      ? `${config.bgColor} ${config.color} border ${config.borderColor}`
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {config.label} ({count})
                </button>
              )
            })}
          </div>
        </div>

        {/* Table Header */}
        <div className="grid grid-cols-[140px_80px_130px_1fr] gap-4 px-4 py-2 bg-slate-900 border-b border-slate-700 text-xs font-medium text-slate-400 uppercase">
          <span>Symbol</span>
          <span>Markets</span>
          <span>Category</span>
          <span>Reason</span>
        </div>

        {/* Coin Rows */}
        <div className="max-h-96 overflow-y-auto">
          {filteredCoins.length === 0 ? (
            <div className="p-8 text-center text-slate-400">
              {searchFilter || categoryFilter ? 'No coins match your filters' : 'No tracked coins'}
            </div>
          ) : (
            filteredCoins.map((coin) => {
              const config = CATEGORY_CONFIG[coin.category]
              const isSaving = savingSymbol === coin.symbol
              const isEditing = editingSymbol === coin.symbol

              return (
                <div
                  key={coin.symbol}
                  className={`grid grid-cols-[140px_80px_130px_1fr] gap-4 px-4 py-3 border-b border-slate-700/50 hover:bg-slate-700/30 items-center ${
                    isSaving ? 'opacity-50' : ''
                  }`}
                >
                  {/* Symbol with Icon */}
                  <div className="flex items-center gap-2">
                    <CoinIcon symbol={coin.symbol} size="sm" />
                    <span className={`font-mono font-medium ${config.color}`}>
                      {coin.symbol}
                    </span>
                  </div>

                  {/* Markets */}
                  <div className="flex flex-wrap gap-1">
                    {coin.markets.map((market) => (
                      <span
                        key={market}
                        className={`text-[10px] px-1.5 py-0.5 rounded ${
                          market === 'BTC' ? 'bg-orange-600/20 text-orange-400' :
                          market === 'USD' ? 'bg-green-600/20 text-green-400' :
                          'bg-blue-600/20 text-blue-400'
                        }`}
                      >
                        {market}
                      </span>
                    ))}
                  </div>

                  {/* Category Dropdown */}
                  <div className="relative">
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setOpenDropdown(openDropdown === coin.symbol ? null : coin.symbol)
                      }}
                      disabled={isSaving}
                      className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-xs font-medium ${config.bgColor} ${config.color} border ${config.borderColor} hover:opacity-80 transition-opacity`}
                    >
                      <span>{config.label}</span>
                      <ChevronDown className={`w-3 h-3 transition-transform ${openDropdown === coin.symbol ? 'rotate-180' : ''}`} />
                    </button>

                    {/* Dropdown Menu */}
                    {openDropdown === coin.symbol && (
                      <div className="absolute z-20 top-full left-0 mt-1 w-48 bg-slate-800 border border-slate-600 rounded-lg shadow-xl overflow-hidden">
                        {CATEGORIES.map((cat) => {
                          const catConfig = CATEGORY_CONFIG[cat]
                          const isSelected = cat === coin.category
                          return (
                            <button
                              key={cat}
                              onClick={(e) => {
                                e.stopPropagation()
                                if (!isSelected) {
                                  changeCoinCategory(coin.symbol, cat, coin.reasonText)
                                }
                              }}
                              className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-slate-700 transition-colors ${
                                isSelected ? catConfig.bgColor : ''
                              }`}
                            >
                              <div className={`w-2 h-2 rounded-full ${catConfig.bgColor} ${catConfig.borderColor} border`} />
                              <span className={isSelected ? catConfig.color : 'text-slate-300'}>
                                {catConfig.label}
                              </span>
                              {isSelected && <Check className={`w-3 h-3 ml-auto ${catConfig.color}`} />}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>

                  {/* Reason */}
                  <div className="flex items-center gap-2 min-w-0">
                    {isEditing ? (
                      <div className="flex-1 flex items-center gap-2">
                        <input
                          type="text"
                          value={editReason}
                          onChange={(e) => setEditReason(e.target.value)}
                          placeholder="Enter reason..."
                          className="flex-1 px-2 py-1 text-sm bg-slate-700 border border-slate-600 rounded focus:outline-none focus:border-blue-500"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') saveEditReason(coin.symbol, coin.category)
                            if (e.key === 'Escape') setEditingSymbol(null)
                          }}
                        />
                        <button
                          onClick={() => saveEditReason(coin.symbol, coin.category)}
                          className="p-1 text-green-400 hover:text-green-300"
                        >
                          <Check className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setEditingSymbol(null)}
                          className="p-1 text-slate-400 hover:text-slate-300"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ) : (
                      <>
                        <span className="text-sm text-slate-400 truncate flex-1" title={coin.reasonText}>
                          {coin.reasonText || <span className="text-slate-600 italic">No reason</span>}
                        </span>
                        <button
                          onClick={() => startEditReason(coin.symbol, coin.reasonText)}
                          className="p-1 text-slate-500 hover:text-slate-300 flex-shrink-0"
                          title="Edit reason"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 bg-slate-900 border-t border-slate-700 text-xs text-slate-500">
          Showing {filteredCoins.length} of {coinList.length} coins
        </div>
      </div>
    </div>
  )
}

export default BlacklistManager
