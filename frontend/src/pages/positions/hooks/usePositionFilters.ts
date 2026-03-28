import { useState, useMemo, useEffect } from 'react'
import type { Position } from '../../../types'

export type GroupByMode = 'none' | 'category' | 'market' | 'bot' | 'pair'

interface UsePositionFiltersProps {
  positionsWithPnL: (Position & { _cachedPnL?: any })[]
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
  const [filterMarket, setFilterMarket] = useState<'all' | 'USD' | 'BTC'>(() => {
    try { return (localStorage.getItem('zenith-positions-filter-market') as 'all' | 'USD' | 'BTC') || 'all' } catch { return 'all' }
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

  // Reset to page 1 when filters or page size change
  useEffect(() => { setCurrentPage(1) }, [filterBot, filterMarket, filterPair, filterCategory, groupBy, sortBy, sortOrder, pageSize])

  // Get group key for a position
  const getGroupKey = (p: Position & { _cachedPnL?: any }): string => {
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
  }

  // All filtered + sorted open positions (before pagination)
  const filteredPositions = useMemo(() => {
    return positionsWithPnL.filter(p => {
      if (p.status !== 'open') return false

      if (filterBot !== 'all' && p.bot_id !== filterBot) return false

      if (filterMarket !== 'all') {
        const quoteCurrency = (p.product_id || 'ETH-BTC').split('-')[1]
        if (filterMarket === 'USD' && quoteCurrency !== 'USD') return false
        if (filterMarket === 'BTC' && quoteCurrency !== 'BTC') return false
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

      let aVal: any, bVal: any
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
  }, [positionsWithPnL, filterBot, filterMarket, filterPair, filterCategory, groupBy, sortBy, sortOrder, bots])

  // Paginated slice
  const totalCount = filteredPositions.length
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize))
  const safePage = Math.min(currentPage, totalPages)
  const pageStart = (safePage - 1) * pageSize
  const openPositions = filteredPositions.slice(pageStart, pageStart + pageSize)

  // Helper for market matching
  const matchesMarket = (productId: string | undefined, market: 'all' | 'USD' | 'BTC') => {
    if (market === 'all') return true
    const quoteCurrency = (productId || 'ETH-BTC').split('-')[1]
    return quoteCurrency === market
  }

  // Dynamic filter options with counts relative to OTHER active filters
  const uniqueMarkets = useMemo(() => {
    const markets: ('USD' | 'BTC')[] = ['USD', 'BTC']
    return markets.map(m => {
      const count = positionsWithPnL.filter(p => {
        if (p.status !== 'open') return false
        if (filterBot !== 'all' && p.bot_id !== filterBot) return false
        if (filterPair !== 'all' && p.product_id !== filterPair) return false
        if (filterCategory !== 'all' && (p.coin_category || 'Uncategorized') !== filterCategory) return false
        return matchesMarket(p.product_id, m)
      }).length
      return { value: m, count }
    })
  }, [positionsWithPnL, filterBot, filterPair, filterCategory])

  const uniqueBots = useMemo(() => {
    const botIds = Array.from(new Set(positionsWithPnL.filter(p => p.status === 'open' && p.bot_id).map(p => p.bot_id as number)))
    return botIds.map(id => {
      const bot = bots?.find(b => b.id === id)
      const count = positionsWithPnL.filter(p => {
        if (p.status !== 'open') return false
        if (p.bot_id !== id) return false
        if (!matchesMarket(p.product_id, filterMarket)) return false
        if (filterPair !== 'all' && p.product_id !== filterPair) return false
        if (filterCategory !== 'all' && (p.coin_category || 'Uncategorized') !== filterCategory) return false
        return true
      }).length
      return { id, name: bot?.name || `Bot #${id}`, count }
    }).sort((a, b) => a.name.localeCompare(b.name))
  }, [positionsWithPnL, filterMarket, filterPair, filterCategory, bots])

  const uniquePairs = useMemo(() => {
    const pairs = Array.from(new Set(positionsWithPnL.filter(p => p.status === 'open').map(p => p.product_id || 'ETH-BTC')))
    return pairs.map(pair => {
      const count = positionsWithPnL.filter(p => {
        if (p.status !== 'open') return false
        if ((p.product_id || 'ETH-BTC') !== pair) return false
        if (filterBot !== 'all' && p.bot_id !== filterBot) return false
        if (!matchesMarket(p.product_id, filterMarket)) return false
        if (filterCategory !== 'all' && (p.coin_category || 'Uncategorized') !== filterCategory) return false
        return true
      }).length
      return { value: pair, count }
    }).sort((a, b) => {
      const [baseA, quoteA] = a.value.split('-')
      const [baseB, quoteB] = b.value.split('-')
      // Sort by quote (market) first, then base (coin)
      if (quoteA !== quoteB) return quoteA.localeCompare(quoteB)
      return baseA.localeCompare(baseB)
    })
  }, [positionsWithPnL, filterBot, filterMarket, filterCategory])

  const uniqueCategories = useMemo(() => {
    const cats = Array.from(new Set(positionsWithPnL.filter(p => p.status === 'open').map(p => p.coin_category || 'Uncategorized')))
    return cats.map(cat => {
      const count = positionsWithPnL.filter(p => {
        if (p.status !== 'open') return false
        if ((p.coin_category || 'Uncategorized') !== cat) return false
        if (filterBot !== 'all' && p.bot_id !== filterBot) return false
        if (!matchesMarket(p.product_id, filterMarket)) return false
        if (filterPair !== 'all' && p.product_id !== filterPair) return false
        return true
      }).length
      return { value: cat, label: getCategoryLabel(cat), count }
    }).sort((a, b) => a.label.localeCompare(b.label))
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
