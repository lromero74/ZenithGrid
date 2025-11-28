/**
 * Blacklist Manager Component
 *
 * Dual-list UI for managing coin blacklist.
 * - Left list: Available coins (from bot product_ids)
 * - Right list: Blacklisted coins with reasons
 */

import { useState, useEffect, useMemo } from 'react'
import {
  Ban,
  ChevronRight,
  ChevronLeft,
  RefreshCw,
  AlertCircle,
  Edit2,
  Check,
  X,
  Search,
} from 'lucide-react'
import { blacklistApi, BlacklistEntry, botsApi } from '../services/api'

export function BlacklistManager() {
  const [blacklistedCoins, setBlacklistedCoins] = useState<BlacklistEntry[]>([])
  const [allTrackedSymbols, setAllTrackedSymbols] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Selected items in each list
  const [selectedAvailable, setSelectedAvailable] = useState<Set<string>>(new Set())
  const [selectedBlacklisted, setSelectedBlacklisted] = useState<Set<string>>(new Set())

  // Search/filter
  const [availableFilter, setAvailableFilter] = useState('')
  const [blacklistedFilter, setBlacklistedFilter] = useState('')

  // Add reason modal
  const [addReasonModal, setAddReasonModal] = useState<{ symbols: string[] } | null>(null)
  const [newReason, setNewReason] = useState('')

  // Edit reason
  const [editingSymbol, setEditingSymbol] = useState<string | null>(null)
  const [editReason, setEditReason] = useState('')

  // Fetch data
  const fetchData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const [blacklist, bots] = await Promise.all([
        blacklistApi.getAll(),
        botsApi.getAll(),
      ])

      setBlacklistedCoins(blacklist)

      // Extract unique symbols from all bots' product_ids
      const symbols = new Set<string>()
      for (const bot of bots) {
        const productIds = bot.product_ids || []
        if (bot.product_id) productIds.push(bot.product_id)

        for (const productId of productIds) {
          const base = productId.split('-')[0]
          symbols.add(base)
        }
      }
      setAllTrackedSymbols(Array.from(symbols).sort())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  // Compute available coins (tracked but not blacklisted)
  const blacklistedSymbols = useMemo(
    () => new Set(blacklistedCoins.map((c) => c.symbol)),
    [blacklistedCoins]
  )

  const availableCoins = useMemo(
    () => allTrackedSymbols.filter((s) => !blacklistedSymbols.has(s)),
    [allTrackedSymbols, blacklistedSymbols]
  )

  // Filtered lists
  const filteredAvailable = useMemo(
    () =>
      availableCoins.filter((s) =>
        s.toLowerCase().includes(availableFilter.toLowerCase())
      ),
    [availableCoins, availableFilter]
  )

  const filteredBlacklisted = useMemo(
    () =>
      blacklistedCoins.filter(
        (c) =>
          c.symbol.toLowerCase().includes(blacklistedFilter.toLowerCase()) ||
          (c.reason || '').toLowerCase().includes(blacklistedFilter.toLowerCase())
      ),
    [blacklistedCoins, blacklistedFilter]
  )

  // Toggle selection
  const toggleAvailable = (symbol: string) => {
    const newSet = new Set(selectedAvailable)
    if (newSet.has(symbol)) {
      newSet.delete(symbol)
    } else {
      newSet.add(symbol)
    }
    setSelectedAvailable(newSet)
  }

  const toggleBlacklisted = (symbol: string) => {
    const newSet = new Set(selectedBlacklisted)
    if (newSet.has(symbol)) {
      newSet.delete(symbol)
    } else {
      newSet.add(symbol)
    }
    setSelectedBlacklisted(newSet)
  }

  // Move to blacklist (show reason modal)
  const handleMoveToBlacklist = () => {
    if (selectedAvailable.size === 0) return
    setAddReasonModal({ symbols: Array.from(selectedAvailable) })
    setNewReason('')
  }

  // Confirm add to blacklist
  const confirmAddToBlacklist = async () => {
    if (!addReasonModal) return

    try {
      await blacklistApi.addBulk(addReasonModal.symbols, newReason || undefined)
      setSelectedAvailable(new Set())
      setAddReasonModal(null)
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add to blacklist')
    }
  }

  // Remove from blacklist
  const handleRemoveFromBlacklist = async () => {
    if (selectedBlacklisted.size === 0) return

    try {
      await Promise.all(
        Array.from(selectedBlacklisted).map((symbol) => blacklistApi.remove(symbol))
      )
      setSelectedBlacklisted(new Set())
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove from blacklist')
    }
  }

  // Edit reason
  const startEditReason = (coin: BlacklistEntry) => {
    setEditingSymbol(coin.symbol)
    setEditReason(coin.reason || '')
  }

  const saveEditReason = async () => {
    if (!editingSymbol) return

    try {
      await blacklistApi.updateReason(editingSymbol, editReason || null)
      setEditingSymbol(null)
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update reason')
    }
  }

  if (isLoading) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <div className="flex items-center justify-center">
          <RefreshCw className="w-5 h-5 text-slate-400 animate-spin" />
          <span className="ml-2 text-slate-400">Loading blacklist...</span>
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
            <Ban className="w-5 h-5 text-red-400" />
            Coin Blacklist
          </h3>
          <p className="text-sm text-slate-400 mt-1">
            Bots will not open new positions in blacklisted coins
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

      {/* Error Message */}
      {error && (
        <div className="flex items-start space-x-2 p-3 bg-red-900/20 border border-red-700 rounded-lg">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {/* Dual List */}
      <div className="grid grid-cols-[1fr_auto_1fr] gap-4">
        {/* Available Coins (Left) */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <div className="px-4 py-3 bg-slate-900 border-b border-slate-700">
            <h4 className="font-medium text-white text-sm">Available Coins</h4>
            <p className="text-xs text-slate-400">{availableCoins.length} tracked</p>
          </div>

          {/* Search */}
          <div className="p-2 border-b border-slate-700">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Filter..."
                value={availableFilter}
                onChange={(e) => setAvailableFilter(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-sm bg-slate-700 border border-slate-600 rounded focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {/* List */}
          <div className="max-h-64 overflow-y-auto">
            {filteredAvailable.length === 0 ? (
              <div className="p-4 text-center text-slate-400 text-sm">
                {availableFilter ? 'No matches' : 'No available coins'}
              </div>
            ) : (
              filteredAvailable.map((symbol) => (
                <label
                  key={symbol}
                  className="flex items-center gap-2 px-4 py-2 hover:bg-slate-700/50 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedAvailable.has(symbol)}
                    onChange={() => toggleAvailable(symbol)}
                    className="w-4 h-4 rounded border-slate-500 bg-slate-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
                  />
                  <span className="text-sm font-mono text-white">{symbol}</span>
                </label>
              ))
            )}
          </div>

          {/* Selection count */}
          {selectedAvailable.size > 0 && (
            <div className="px-4 py-2 bg-slate-900 border-t border-slate-700 text-xs text-slate-400">
              {selectedAvailable.size} selected
            </div>
          )}
        </div>

        {/* Transfer Buttons */}
        <div className="flex flex-col justify-center gap-2">
          <button
            onClick={handleMoveToBlacklist}
            disabled={selectedAvailable.size === 0}
            className="p-2 bg-red-600 hover:bg-red-700 disabled:bg-slate-700 disabled:text-slate-500 rounded-lg transition-colors"
            title="Add to blacklist"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
          <button
            onClick={handleRemoveFromBlacklist}
            disabled={selectedBlacklisted.size === 0}
            className="p-2 bg-green-600 hover:bg-green-700 disabled:bg-slate-700 disabled:text-slate-500 rounded-lg transition-colors"
            title="Remove from blacklist"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
        </div>

        {/* Blacklisted Coins (Right) */}
        <div className="bg-slate-800 rounded-lg border border-red-900/50 overflow-hidden">
          <div className="px-4 py-3 bg-red-900/20 border-b border-red-900/50">
            <h4 className="font-medium text-red-400 text-sm flex items-center gap-2">
              <Ban className="w-4 h-4" />
              Blacklisted
            </h4>
            <p className="text-xs text-slate-400">{blacklistedCoins.length} blocked</p>
          </div>

          {/* Search */}
          <div className="p-2 border-b border-slate-700">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Filter..."
                value={blacklistedFilter}
                onChange={(e) => setBlacklistedFilter(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-sm bg-slate-700 border border-slate-600 rounded focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {/* List */}
          <div className="max-h-64 overflow-y-auto">
            {filteredBlacklisted.length === 0 ? (
              <div className="p-4 text-center text-slate-400 text-sm">
                {blacklistedFilter ? 'No matches' : 'No blacklisted coins'}
              </div>
            ) : (
              filteredBlacklisted.map((coin) => (
                <div
                  key={coin.symbol}
                  className="flex items-start gap-2 px-4 py-2 hover:bg-slate-700/50"
                >
                  <input
                    type="checkbox"
                    checked={selectedBlacklisted.has(coin.symbol)}
                    onChange={() => toggleBlacklisted(coin.symbol)}
                    className="w-4 h-4 mt-0.5 rounded border-slate-500 bg-slate-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono text-red-400 font-medium">
                        {coin.symbol}
                      </span>
                      {editingSymbol === coin.symbol ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={saveEditReason}
                            className="p-0.5 text-green-400 hover:text-green-300"
                          >
                            <Check className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => setEditingSymbol(null)}
                            className="p-0.5 text-slate-400 hover:text-slate-300"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => startEditReason(coin)}
                          className="p-0.5 text-slate-400 hover:text-slate-300"
                          title="Edit reason"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                    {editingSymbol === coin.symbol ? (
                      <input
                        type="text"
                        value={editReason}
                        onChange={(e) => setEditReason(e.target.value)}
                        placeholder="Enter reason..."
                        className="w-full mt-1 px-2 py-1 text-xs bg-slate-700 border border-slate-600 rounded focus:outline-none focus:border-blue-500"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveEditReason()
                          if (e.key === 'Escape') setEditingSymbol(null)
                        }}
                      />
                    ) : (
                      coin.reason && (
                        <p className="text-xs text-slate-400 truncate" title={coin.reason}>
                          {coin.reason}
                        </p>
                      )
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Selection count */}
          {selectedBlacklisted.size > 0 && (
            <div className="px-4 py-2 bg-slate-900 border-t border-slate-700 text-xs text-slate-400">
              {selectedBlacklisted.size} selected
            </div>
          )}
        </div>
      </div>

      {/* Add Reason Modal */}
      {addReasonModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-full max-w-md border border-slate-700">
            <h4 className="text-lg font-bold text-white mb-4">
              Add to Blacklist
            </h4>
            <p className="text-sm text-slate-400 mb-4">
              Adding {addReasonModal.symbols.length} coin(s):{' '}
              <span className="text-red-400 font-mono">
                {addReasonModal.symbols.join(', ')}
              </span>
            </p>
            <div className="mb-4">
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Reason (optional)
              </label>
              <textarea
                value={newReason}
                onChange={(e) => setNewReason(e.target.value)}
                placeholder="Why is this coin being blacklisted?"
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-sm focus:outline-none focus:border-blue-500 resize-none"
                rows={3}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setAddReasonModal(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmAddToBlacklist}
                className="px-4 py-2 text-sm bg-red-600 hover:bg-red-700 rounded-lg font-medium transition-colors"
              >
                Add to Blacklist
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default BlacklistManager
