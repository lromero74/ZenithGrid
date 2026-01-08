import { useState, useMemo } from 'react'
import type { Position } from '../../../types'

interface UsePositionFiltersProps {
  positionsWithPnL: (Position & { _cachedPnL?: any })[]
}

export const usePositionFilters = ({ positionsWithPnL }: UsePositionFiltersProps) => {
  // Filtering and sorting state (like 3Commas)
  const [filterBot, setFilterBot] = useState<number | 'all'>('all')
  const [filterMarket, setFilterMarket] = useState<'all' | 'USD' | 'BTC'>('all')
  const [filterPair, setFilterPair] = useState<string>('all')
  const [sortBy, setSortBy] = useState<'created' | 'pnl' | 'invested' | 'pair' | 'bot'>('created')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  // Apply filters and sorting (like 3Commas)
  // Use memoized positionsWithPnL instead of recalculating
  const openPositions = useMemo(() => {
    return positionsWithPnL.filter(p => {
      if (p.status !== 'open') return false

      // Filter by bot
      if (filterBot !== 'all' && p.bot_id !== filterBot) return false

      // Filter by market (USD-based or BTC-based)
      if (filterMarket !== 'all') {
        const quoteCurrency = (p.product_id || 'ETH-BTC').split('-')[1]
        if (filterMarket === 'USD' && quoteCurrency !== 'USD') return false
        if (filterMarket === 'BTC' && quoteCurrency !== 'BTC') return false
      }

      // Filter by specific pair
      if (filterPair !== 'all' && p.product_id !== filterPair) return false

      return true
    }).sort((a, b) => {
      let aVal: any, bVal: any

      switch (sortBy) {
        case 'created':
          // For closed positions, sort by closed_at (most recent closure first)
          // For open positions, sort by opened_at
          aVal = a.status === 'closed' && a.closed_at
            ? new Date(a.closed_at).getTime()
            : new Date(a.opened_at).getTime()
          bVal = b.status === 'closed' && b.closed_at
            ? new Date(b.closed_at).getTime()
            : new Date(b.opened_at).getTime()
          break
        case 'pnl':
          // Use cached P&L instead of recalculating
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
        default:
          aVal = 0
          bVal = 0
      }

      if (sortOrder === 'asc') {
        return aVal > bVal ? 1 : -1
      } else {
        return aVal < bVal ? 1 : -1
      }
    })
  }, [positionsWithPnL, filterBot, filterMarket, filterPair, sortBy, sortOrder])

  // Get unique pairs for filter dropdown
  const uniquePairs = useMemo(() => {
    const allPositions = positionsWithPnL.filter(p => p.status === 'open')
    return Array.from(new Set(allPositions.map(p => p.product_id || 'ETH-BTC')))
  }, [positionsWithPnL])

  const clearFilters = () => {
    setFilterBot('all')
    setFilterMarket('all')
    setFilterPair('all')
  }

  return {
    // Filter state
    filterBot,
    setFilterBot,
    filterMarket,
    setFilterMarket,
    filterPair,
    setFilterPair,

    // Sort state
    sortBy,
    setSortBy,
    sortOrder,
    setSortOrder,

    // Filtered data
    openPositions,
    uniquePairs,

    // Actions
    clearFilters,
  }
}
