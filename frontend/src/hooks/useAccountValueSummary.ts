import { useQuery, keepPreviousData } from '@tanstack/react-query'

import { accountValueSummaryApi } from '../services/api'

interface UseAccountValueSummaryArgs {
  selectedAccount: { id: number } | null
}

export function useAccountValueSummary({ selectedAccount }: UseAccountValueSummaryArgs) {
  const query = useQuery({
    queryKey: ['account-value-summary', selectedAccount?.id],
    queryFn: () => accountValueSummaryApi.get(selectedAccount!.id),
    enabled: !!selectedAccount,
    staleTime: 30000,
    refetchInterval: 60000,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  })

  return {
    summary: query.data,
    isLoading: query.isLoading,
  }
}
