import { useState, useMemo, useEffect, useCallback } from 'react'
import type { PositionWithPnL } from '../helpers'

export type GroupByMode = 'none' | 'category' | 'market' | 'bot' | 'pair'

/** Active-deals layout: compact table, single-column cards, or tiled card grid. */
export type DealsViewMode = 'table' | 'list' | 'grid'
const DEALS_VIEW_MODES: DealsViewMode[] = ['table', 'list', 'grid']

interface UsePositionFiltersProps {
  positionsWithPnL: PositionWithPnL[]
  bots?: { id: number; name: string }[]
}

const COIN_CATEGORY_LABELS: Record<string, string> = {
  APPROVED: 'Approved',
  BORDERLINE: 'Borderline',
  QUESTIONABLE: 'Questionable',
  MEME: 'Meme',
  BLACKLISTED: 'Blacklisted',
}

export function getCategoryLabel(category: string | null | undefined): string {
  if (!category) return 'Uncategorized'
  return COIN_CATEGORY_LABELS[category] ?? category
}

export const usePositionFilters = ({ positionsWithPnL, bots }: UsePositionFiltersProps) => {
  // Filtering and sorting state - persisted to localStorage
  const [filterBot, setFilterBot] = useState<number | 'all'>(() => {
    try { const v = localStorage.getItem('zenith-positions-filter-bot'); return v && v !== 'all' ? Number(v) : 'all' } catch { return 'all' }
  })
  const [filterMarket, setFilterMarket] = useState<string>(() => {
    try { return localStorage.getItem('zenith-positions-filter-market') || 'all' } catch { return 'all' }
  })
  const [filterPair, setFilterPair] = useState<string>(() => {
    try { return localStorage.getItem('zenith-positions-filter-pair') || 'all' } catch { return 'all' }
  })
  const [filterCategory, setFilterCategory] = useState<string>(() => {
    try { return localStorage.getItem('zenith-positions-filter-category') || 'all' } catch { return 'all' }
  })
  const [groupBy, setGroupBy] = useState<GroupByMode>(() => {
    try { return (localStorage.getItem('zenith-positions-group-by') as GroupByMode) || 'none' } catch { return 'none' }
  })
  const [sortBy, setSortBy] = useState<'created' | 'pnl' | 'invested' | 'pair' | 'bot'>(() => {
    try { return (localStorage.getItem('zenith-positions-sort-by') as 'created' | 'pnl' | 'invested' | 'pair' | 'bot') || 'created' } catch { return 'created' }
  })
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(() => {
    try { return (localStorage.getItem('zenith-positions-sort-order') as 'asc' | 'desc') || 'desc' } catch { return 'desc' }
  })

  // Active-deals view mode (table / card list / tiled grid)
  const [viewMode, setViewMode] = useState<DealsViewMode>(() => {
    try {
      const v = localStorage.getItem('zenith-positions-view-mode') as DealsViewMode
      return DEALS_VIEW_MODES.includes(v) ? v : 'table'
    } catch { return 'table' }
  })

  // Pagination
  const [pageSize, setPageSize] = useState<10 | 100>(() => {
    try { const v = localStorage.getItem('zenith-positions-page-size'); return v === '100' ? 100 : 10 } catch { return 10 }
  })
  const [currentPage, setCurrentPage] = useState(1)

  // Persist filter/sort/pagination state
  useEffect(() => { try { localStorage.setItem('zenith-positions-filter-bot', String(filterBot)) } catch { /* ignored */ } }, [filterBot])
  useEffect(() => { try { localStorage.setItem('zenith-positions-filter-market', filterMarket) } catch { /* ignored */ } }, [filterMarket])
  useEffect(() => { try { localStorage.setItem('zenith-positions-filter-pair', filterPair) } catch { /* ignored */ } }, [filterPair])
  useEffect(() => { try { localStorage.setItem('zenith-positions-filter-category', filterCategory) } catch { /* ignored */ } }, [filterCategory])
  useEffect(() => { try { localStorage.setItem('zenith-positions-group-by', groupBy) } catch { /* ignored */ } }, [groupBy])
  useEffect(() => { try { localStorage.setItem('zenith-positions-sort-by', sortBy) } catch { /* ignored */ } }, [sortBy])
  useEffect(() => { try { localStorage.setItem('zenith-positions-sort-order', sortOrder) } catch { /* ignored */ } }, [sortOrder])
  useEffect(() => { try { localStorage.setItem('zenith-positions-page-size', String(pageSize)) } catch { /* ignored */ } }, [pageSize])
  useEffect(() => { try { localStorage.setItem('zenith-positions-view-mode', viewMode) } catch { /* ignored */ } }, [viewMode])

  // Reset to page 1 when filters or page size change
  useEffect(() => { setCurrentPage(1) }, [filterBot, filterMarket, filterPair, filterCategory, groupBy, sortBy, sortOrder, pageSize])

  // Get group key for a position
  const getGroupKey = useCallback((p: PositionWithPnL): string => {
    switch (groupBy) {
      case 'category': return p.coin_category || 'Uncategorized'
      case 'market': return (p.product_id || 'ETH-BTC').split('-')[1] || 'Other'
      case 'bot': {
        const bot = bots?.find(b => b.id === p.bot_id)
        return bot ? bot.name : (p.bot_id ? `Bot #${p.bot_id}` : 'No Bot')
      }
      case 'pair': return p.product_id || 'Unknown'
      default: return ''
    }
  }, [groupBy, bots])

  // All filtered + sorted open positions (before pagination)
  const filteredPositions = useMemo(() => {
    return positionsWithPnL.filter(p => {
      if (p.status !== 'open') return false

      if (filterBot !== 'all' && p.bot_id !== filterBot) return false

      if (filterMarket !== 'all') {
        const quoteCurrency = (p.product_id || 'ETH-BTC').split('-')[1]
        if (quoteCurrency !== filterMarket) return false
      }

      if (filterPair !== 'all' && p.product_id !== filterPair) return false

      if (filterCategory !== 'all') {
        const cat = p.coin_category || 'Uncategorized'
        if (cat !== filterCategory) return false
      }

      return true
    }).sort((a, b) => {
      // When groupBy is active: sort by group key first, then by secondary sort within group
      if (groupBy !== 'none') {
        const gA = getGroupKey(a)
        const gB = getGroupKey(b)
        if (gA < gB) return -1
        if (gA > gB) return 1
      }

      let aVal: number | string, bVal: number | string
      switch (sortBy) {
        case 'created':
          aVal = a.status === 'closed' && a.closed_at
            ? new Date(a.closed_at).getTime()
            : new Date(a.opened_at).getTime()
          bVal = b.status === 'closed' && b.closed_at
            ? new Date(b.closed_at).getTime()
            : new Date(b.opened_at).getTime()
          break
        case 'pnl':
          aVal = a._cachedPnL?.percent || 0
          bVal = b._cachedPnL?.percent || 0
          break
        case 'invested':
          aVal = a.total_quote_spent
          bVal = b.total_quote_spent
          break
        case 'pair':
          aVal = a.product_id || 'ETH-BTC'
          bVal = b.product_id || 'ETH-BTC'
          break
        case 'bot':
          aVal = a.bot_id || 0
          bVal = b.bot_id || 0
          break
        default:
          aVal = 0
          bVal = 0
      }

      if (sortOrder === 'asc') return aVal > bVal ? 1 : -1
      return aVal < bVal ? 1 : -1
    })
  }, [positionsWithPnL, filterBot, filterMarket, filterPair, filterCategory, groupBy, sortBy, sortOrder, getGroupKey])

  // Paginated slice
  const totalCount = filteredPositions.length
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize))
  const safePage = Math.min(currentPage, totalPages)
  const pageStart = (safePage - 1) * pageSize
  const openPositions = filteredPositions.slice(pageStart, pageStart + pageSize)

  // Helper for market matching
  const matchesMarket = (productId: string | undefined, market: string) => {
    if (market === 'all') return true
    const quoteCurrency = (productId || 'ETH-BTC').split('-')[1]
    return quoteCurrency === market
  }

  // Dynamic filter options — derived from actual open positions, not a hardcoded list
  const uniqueMarkets = useMemo(() => {
    // Single-pass O(n): collect all markets and accumulate filtered counts in one loop.
    // counts apply bot/pair/category filters but NOT the market filter (that's the "own" dimension).
    const allMarkets = new Set<string>()
    const counts = new Map<string, number>()
    for (const p of positionsWithPnL) {
      if (p.status !== 'open') continue
      const quote = (p.product_id || 'ETH-BTC').split('-')[1]
      if (!quote) continue
      allMarkets.add(quote)
      if (filterBot !== 'all' && p.bot_id !== filterBot) continue
      if (filterPair !== 'all' && p.product_id !== filterPair) continue
      if (filterCategory !== 'all' && (p.coin_category || 'Uncategorized') !== filterCategory) continue
      counts.set(quote, (counts.get(quote) ?? 0) + 1)
    }
    return Array.from(allMarkets).sort().map(m => ({ value: m, count: counts.get(m) ?? 0 }))
  }, [positionsWithPnL, filterBot, filterPair, filterCategory])

  const uniqueBots = useMemo(() => {
    // Single-pass O(n): collect all bot IDs and accumulate filtered counts in one loop.
    // counts apply market/pair/category filters but NOT the bot filter (own dimension).
    const allBotIds = new Set<number>()
    const counts = new Map<number, number>()
    for (const p of positionsWithPnL) {
      if (p.status !== 'open' || !p.bot_id) continue
      allBotIds.add(p.bot_id)
      if (!matchesMarket(p.product_id, filterMarket)) continue
      if (filterPair !== 'all' && p.product_id !== filterPair) continue
      if (filterCategory !== 'all' && (p.coin_category || 'Uncategorized') !== filterCategory) continue
      counts.set(p.bot_id, (counts.get(p.bot_id) ?? 0) + 1)
    }
    return Array.from(allBotIds)
      .map(id => {
        const bot = bots?.find(b => b.id === id)
        return { id, name: bot?.name || `Bot #${id}`, count: counts.get(id) ?? 0 }
      })
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [positionsWithPnL, filterMarket, filterPair, filterCategory, bots])

  const uniquePairs = useMemo(() => {
    // Single-pass O(n): collect all pairs and accumulate filtered counts in one loop.
    // counts apply bot/market/category filters but NOT the pair filter (own dimension).
    const allPairs = new Set<string>()
    const counts = new Map<string, number>()
    for (const p of positionsWithPnL) {
      if (p.status !== 'open') continue
      const pair = p.product_id || 'ETH-BTC'
      allPairs.add(pair)
      if (filterBot !== 'all' && p.bot_id !== filterBot) continue
      if (!matchesMarket(p.product_id, filterMarket)) continue
      if (filterCategory !== 'all' && (p.coin_category || 'Uncategorized') !== filterCategory) continue
      counts.set(pair, (counts.get(pair) ?? 0) + 1)
    }
    return Array.from(allPairs)
      .map(pair => ({ value: pair, count: counts.get(pair) ?? 0 }))
      .sort((a, b) => {
        const [baseA, quoteA] = a.value.split('-')
        const [baseB, quoteB] = b.value.split('-')
        // Sort by quote (market) first, then base (coin)
        if (quoteA !== quoteB) return quoteA.localeCompare(quoteB)
        return baseA.localeCompare(baseB)
      })
  }, [positionsWithPnL, filterBot, filterMarket, filterCategory])

  const uniqueCategories = useMemo(() => {
    // Single-pass O(n): collect all categories and accumulate filtered counts in one loop.
    // counts apply bot/market/pair filters but NOT the category filter (own dimension).
    const allCats = new Set<string>()
    const counts = new Map<string, number>()
    for (const p of positionsWithPnL) {
      if (p.status !== 'open') continue
      const cat = p.coin_category || 'Uncategorized'
      allCats.add(cat)
      if (filterBot !== 'all' && p.bot_id !== filterBot) continue
      if (!matchesMarket(p.product_id, filterMarket)) continue
      if (filterPair !== 'all' && p.product_id !== filterPair) continue
      counts.set(cat, (counts.get(cat) ?? 0) + 1)
    }
    return Array.from(allCats)
      .map(cat => ({ value: cat, label: getCategoryLabel(cat), count: counts.get(cat) ?? 0 }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [positionsWithPnL, filterBot, filterMarket, filterPair])

  const clearFilters = () => {
    setFilterBot('all')
    setFilterMarket('all')
    setFilterPair('all')
    setFilterCategory('all')
  }

  return {
    // Filter state
    filterBot, setFilterBot,
    filterMarket, setFilterMarket,
    filterPair, setFilterPair,
    filterCategory, setFilterCategory,

    // Group/sort state
    groupBy, setGroupBy,
    sortBy, setSortBy,
    sortOrder, setSortOrder,

    // View mode
    viewMode, setViewMode,

    // Pagination state
    pageSize, setPageSize,
    currentPage,
    setCurrentPage,
    totalCount,
    totalPages,

    // Filtered data
    openPositions,
    filteredPositions,
    uniqueMarkets,
    uniqueBots,
    uniquePairs,
    uniqueCategories,

    // Helpers
    getGroupKey,

    // Actions
    clearFilters,
  }
}
