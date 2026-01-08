import { X } from 'lucide-react'
import type { Bot } from '../../../types'

interface FilterPanelProps {
  filterBot: number | 'all'
  setFilterBot: (value: number | 'all') => void
  filterMarket: 'all' | 'USD' | 'BTC'
  setFilterMarket: (value: 'all' | 'USD' | 'BTC') => void
  filterPair: string
  setFilterPair: (value: string) => void
  bots: Bot[] | undefined
  uniquePairs: string[]
  onClearFilters: () => void
}

export const FilterPanel = ({
  filterBot,
  setFilterBot,
  filterMarket,
  setFilterMarket,
  filterPair,
  setFilterPair,
  bots,
  uniquePairs,
  onClearFilters,
}: FilterPanelProps) => {
  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 mb-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-300">Filters</h3>
        <button
          onClick={onClearFilters}
          className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded transition-colors flex items-center gap-2"
        >
          <X className="w-4 h-4" />
          Clear
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Account Filter (Market in our case) */}
        <div>
          <label className="block text-sm font-medium text-slate-400 mb-2">Account</label>
          <select
            value={filterMarket}
            onChange={(e) => setFilterMarket(e.target.value as 'all' | 'USD' | 'BTC')}
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="all">All</option>
            <option value="USD">USD Markets</option>
            <option value="BTC">BTC Markets</option>
          </select>
        </div>

        {/* Bot Filter */}
        <div>
          <label className="block text-sm font-medium text-slate-400 mb-2">Bot</label>
          <select
            value={filterBot}
            onChange={(e) => setFilterBot(e.target.value === 'all' ? 'all' : parseInt(e.target.value))}
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="all">All</option>
            {bots?.map(bot => (
              <option key={bot.id} value={bot.id}>{bot.name}</option>
            ))}
          </select>
        </div>

        {/* Pair Filter */}
        <div>
          <label className="block text-sm font-medium text-slate-400 mb-2">Pair</label>
          <select
            value={filterPair}
            onChange={(e) => setFilterPair(e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="all">All</option>
            {uniquePairs.map(pair => (
              <option key={pair} value={pair}>{pair}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}
