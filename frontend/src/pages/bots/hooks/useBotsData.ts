import { useMemo } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { useAccountPortfolio } from '../../../hooks/useAccountPortfolio'
import { botsApi, templatesApi, accountApi, rebalanceApi, api } from '../../../services/api'
import type { Bot } from '../../../types'
import { convertProductsToTradingPairs, DEFAULT_TRADING_PAIRS, type TradingPair } from '../../../components/bots'
import { TimeRange } from '../../../components/trading/PnLChart'

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
      if (!selectedAccount) return data
      // Filter by account_id
      return data.filter((bot: Bot) => bot.account_id === selectedAccount.id)
    },
  })

  // Fetch available strategies
  const { data: strategies = [] } = useQuery({
    queryKey: ['strategies'],
    queryFn: botsApi.getStrategies,
  })

  // Portfolio data for percentage calculations — shared cache entry with the
  // other pages (one 60s poll app-wide instead of one per page)
  const { data: portfolio, isLoading: portfolioLoading } =
    useAccountPortfolio(selectedAccount?.id)

  // Fetch aggregate BTC/USD values for minimum percentage validation.
  // Scoped to the selected account so a multi-account user sees that account's
  // budget buckets (not the default first-CEX account's) — keyed by account so
  // it refetches on account switch.
  const { data: aggregateData } = useQuery({
    queryKey: ['aggregate-value', selectedAccount?.id],
    queryFn: () => accountApi.getAggregateValue(selectedAccount?.id),
    refetchInterval: 60000, // Update every 60 seconds
  })

  // Fetch rebalance status for reserve-aware budget calculations
  const { data: rebalanceStatus } = useQuery({
    queryKey: ['rebalance-status', selectedAccount?.id],
    queryFn: () => selectedAccount ? rebalanceApi.getStatus(selectedAccount.id) : null,
    enabled: !!selectedAccount,
    refetchInterval: 60000,
  })

  // Fetch available templates
  const { data: templates = [] } = useQuery({
    queryKey: ['templates'],
    queryFn: templatesApi.getAll,
  })

  // Fetch available trading pairs for the selected account's exchange
  const { data: productsData } = useQuery({
    queryKey: ['available-products', selectedAccount?.id],
    queryFn: async () => {
      const params = selectedAccount?.id ? { account_id: selectedAccount.id } : {}
      const response = await api.get('/products', { params })
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
    rebalanceStatus,
    templates,
    productsData,
    TRADING_PAIRS
  }
}
