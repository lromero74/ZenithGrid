import { X } from 'lucide-react'
import type { Bot } from '../../../types'
import type { GroupByMode } from '../hooks/usePositionFilters'

interface FilterPanelProps {
  filterBot: number | 'all'
  setFilterBot: (value: number | 'all') => void
  filterMarket: string
  setFilterMarket: (value: string) => void
  filterPair: string
  setFilterPair: (value: string) => void
  filterCategory: string
  setFilterCategory: (value: string) => void
  groupBy: GroupByMode
  setGroupBy: (value: GroupByMode) => void
  bots: Bot[] | undefined
  uniqueMarkets: { value: string; count: number }[]
  uniqueBots: { id: number; name: string; count: number }[]
  uniquePairs: { value: string; count: number }[]
  uniqueCategories: { value: string; label: string; count: number }[]
  onClearFilters: () => void
}

export const FilterPanel = ({
  filterBot, setFilterBot,
  filterMarket, setFilterMarket,
  filterPair, setFilterPair,
  filterCategory, setFilterCategory,
  groupBy, setGroupBy,
  uniqueMarkets,
  uniqueBots,
  uniquePairs,
  uniqueCategories,
  onClearFilters,
}: FilterPanelProps) => {
  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 mb-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-300">Filters & Grouping</h3>
        <button
          onClick={onClearFilters}
          className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded transition-colors flex items-center gap-2"
        >
          <X className="w-4 h-4" />
          Clear
        </button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {/* Market Filter */}
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">Market</label>
          <select
            value={filterMarket}
            onChange={(e) => setFilterMarket(e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Markets</option>
            {uniqueMarkets.map(m => (
              <option 
                key={m.value} 
                value={m.value}
                disabled={m.count === 0}
                className={m.count === 0 ? 'text-slate-500' : ''}
              >
                {m.value} Markets {m.count > 0 ? `(${m.count})` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Bot Filter */}
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">Bot</label>
          <select
            value={filterBot}
            onChange={(e) => setFilterBot(e.target.value === 'all' ? 'all' : parseInt(e.target.value))}
            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Bots</option>
            {uniqueBots.map(bot => (
              <option 
                key={bot.id} 
                value={bot.id}
                disabled={bot.count === 0}
                className={bot.count === 0 ? 'text-slate-500' : ''}
              >
                {bot.name} {bot.count > 0 ? `(${bot.count})` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Pair Filter */}
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">Pair</label>
          <select
            value={filterPair}
            onChange={(e) => setFilterPair(e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Pairs</option>
            {uniquePairs.map(pair => (
              <option 
                key={pair.value} 
                value={pair.value}
                disabled={pair.count === 0}
                className={pair.count === 0 ? 'text-slate-500' : ''}
              >
                {pair.value} {pair.count > 0 ? `(${pair.count})` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Category Filter */}
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">Coin Category</label>
          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Categories</option>
            {uniqueCategories.map(cat => (
              <option 
                key={cat.value} 
                value={cat.value}
                disabled={cat.count === 0}
                className={cat.count === 0 ? 'text-slate-500' : ''}
              >
                {cat.label} {cat.count > 0 ? `(${cat.count})` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Group By */}
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">Group By</label>
          <select
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value as GroupByMode)}
            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="none">No Grouping</option>
            <option value="category">Category</option>
            <option value="market">Market</option>
            <option value="bot">Bot</option>
            <option value="pair">Pair</option>
          </select>
        </div>
      </div>
    </div>
  )
}
