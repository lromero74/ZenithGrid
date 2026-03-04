import { useState, useRef, useEffect, useMemo } from 'react'
import { ChevronDown, Search } from 'lucide-react'

export interface TradingPair {
  value: string
  label: string
  group: string
  inPortfolio?: boolean
}

interface PairSelectorProps {
  pairs: TradingPair[]
  selectedPair: string
  onSelectPair: (pair: string) => void
}

export function PairSelector({ pairs, selectedPair, onSelectPair }: PairSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [activeMarket, setActiveMarket] = useState('All')
  const containerRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Focus search when dropdown opens
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      searchInputRef.current.focus()
    }
  }, [isOpen])

  // Get unique market tabs from pairs (F13)
  const markets = useMemo(() => ['All', ...Array.from(new Set(pairs.map(p => p.group))).sort()], [pairs])

  // Filter pairs by market tab and search (F13)
  const filteredPairs = useMemo(() => {
    const searchLower = search.toLowerCase()
    return pairs.filter(p => {
      const matchesMarket = activeMarket === 'All' || p.group === activeMarket
      const matchesSearch = !search || p.label.toLowerCase().includes(searchLower)
        || p.value.toLowerCase().includes(searchLower)
      return matchesMarket && matchesSearch
    })
  }, [pairs, activeMarket, search])

  // Group filtered pairs: portfolio first, then alphabetical (F13)
  const sortedPairs = useMemo(() => [...filteredPairs].sort((a, b) => {
    if (a.inPortfolio && !b.inPortfolio) return -1
    if (!a.inPortfolio && b.inPortfolio) return 1
    return a.label.localeCompare(b.label)
  }), [filteredPairs])

  const selectedLabel = useMemo(
    () => pairs.find(p => p.value === selectedPair)?.label || selectedPair,
    [pairs, selectedPair]
  )

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger button */}
      <button
        onClick={() => { setIsOpen(!isOpen); setSearch('') }}
        className="flex items-center gap-2 bg-slate-700 text-white px-3 py-2 rounded text-sm font-medium border border-slate-600 hover:bg-slate-600 transition-colors min-w-[140px]"
      >
        <span className="truncate">{selectedLabel}</span>
        <ChevronDown size={14} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-50 overflow-hidden">
          {/* Search input */}
          <div className="p-2 border-b border-slate-700">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" size={14} />
              <input
                ref={searchInputRef}
                type="text"
                placeholder="Search pairs..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-slate-700 text-white text-sm pl-8 pr-3 py-1.5 rounded border border-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Market tabs */}
          <div className="flex gap-1 p-2 border-b border-slate-700 flex-wrap">
            {markets.map(market => (
              <button
                key={market}
                onClick={() => setActiveMarket(market)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  activeMarket === market
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {market}
              </button>
            ))}
          </div>

          {/* Pair list */}
          <div className="max-h-64 overflow-y-auto">
            {sortedPairs.length === 0 ? (
              <div className="px-3 py-4 text-sm text-slate-400 text-center">No pairs found</div>
            ) : (
              sortedPairs.map(pair => (
                <button
                  key={pair.value}
                  onClick={() => { onSelectPair(pair.value); setIsOpen(false) }}
                  className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 transition-colors ${
                    pair.value === selectedPair
                      ? 'bg-blue-600/20 text-blue-300'
                      : 'text-slate-200 hover:bg-slate-700'
                  }`}
                >
                  {pair.inPortfolio && (
                    <span className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />
                  )}
                  <span className="flex-1">{pair.label}</span>
                  <span className="text-xs text-slate-500">{pair.group}</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
