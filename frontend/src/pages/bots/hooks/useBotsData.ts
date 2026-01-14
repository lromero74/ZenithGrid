import { useMemo } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { botsApi, templatesApi, accountApi } from '../../../services/api'
import type { Bot } from '../../../types'
import { convertProductsToTradingPairs, DEFAULT_TRADING_PAIRS, type TradingPair } from '../../../components/bots'
import { TimeRange } from '../../../components/PnLChart'
import axios from 'axios'

interface UseBotsDataProps {
  selectedAccount: { id: number } | null
  projectionTimeframe: TimeRange
}

export function useBotsData({ selectedAccount, projectionTimeframe }: UseBotsDataProps) {
  // Fetch all bots (filtered by selected account)
  const { data: bots = [], isLoading: botsLoading, isFetching: botsFetching } = useQuery({
    queryKey: ['bots', selectedAccount?.id, projectionTimeframe],
    queryFn: () => botsApi.getAll(projectionTimeframe),
    refetchInterval: 30000, // Refetch every 30 seconds (reduced from 5 seconds)
    placeholderData: keepPreviousData, // Keep showing previous data while fetching new timeframe
    select: (data) => {
      console.log('[DEBUG] useBotsData - Raw bots from API:', data)
      console.log('[DEBUG] useBotsData - Selected account:', selectedAccount)

      if (!selectedAccount) {
        console.log('[DEBUG] useBotsData - No account selected, returning all bots')
        return data
      }

      // Filter by account_id
      const filtered = data.filter((bot: Bot) => {
        const matches = bot.account_id === selectedAccount.id
        console.log(`[DEBUG] Bot "${bot.name}" (id: ${bot.id}, account_id: ${bot.account_id}) ${matches ? 'MATCHES' : 'FILTERED OUT'}`)
        return matches
      })

      console.log('[DEBUG] useBotsData - Filtered bots:', filtered)
      return filtered
    },
  })

  // Fetch available strategies
  const { data: strategies = [] } = useQuery({
    queryKey: ['strategies'],
    queryFn: botsApi.getStrategies,
  })

  // Fetch portfolio data for percentage calculations (account-specific)
  const { data: portfolio, isLoading: portfolioLoading } = useQuery({
    queryKey: ['account-portfolio-bots', selectedAccount?.id],
    queryFn: async () => {
      if (selectedAccount) {
        const response = await fetch(`/api/accounts/${selectedAccount.id}/portfolio`)
        if (!response.ok) throw new Error('Failed to fetch portfolio')
        return response.json()
      }
      const response = await fetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 60000, // Update every 60 seconds
    placeholderData: keepPreviousData, // Keep portfolio value visible while refetching
  })

  // Fetch aggregate BTC/USD values for minimum percentage validation
  const { data: aggregateData } = useQuery({
    queryKey: ['aggregate-value'],
    queryFn: accountApi.getAggregateValue,
    refetchInterval: 60000, // Update every 60 seconds
  })

  // Fetch available templates
  const { data: templates = [] } = useQuery({
    queryKey: ['templates'],
    queryFn: templatesApi.getAll,
  })

  // Fetch available trading pairs from Coinbase
  const { data: productsData } = useQuery({
    queryKey: ['available-products'],
    queryFn: async () => {
      const response = await axios.get('/api/products')
      return response.data
    },
    staleTime: 3600000, // Cache for 1 hour (product list rarely changes)
  })

  // Generate trading pairs from all available products
  const TRADING_PAIRS = useMemo<TradingPair[]>(() => {
    if (!productsData?.products) {
      return DEFAULT_TRADING_PAIRS
    }
    return convertProductsToTradingPairs(productsData.products)
  }, [productsData])

  return {
    bots,
    botsLoading,
    botsFetching,
    strategies,
    portfolio,
    portfolioLoading,
    aggregateData,
    templates,
    productsData,
    TRADING_PAIRS
  }
}
