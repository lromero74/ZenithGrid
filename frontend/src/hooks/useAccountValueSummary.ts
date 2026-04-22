import { useEffect } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'

import { accountValueSummaryApi } from '../services/api'

const STALE_SUMMARY_RECHECK_MS = 5000
const FRESH_SUMMARY_RECHECK_MS = 60000

interface UseAccountValueSummaryArgs {
  selectedAccount: { id: number } | null
}

export function useAccountValueSummary({ selectedAccount }: UseAccountValueSummaryArgs) {
  const query = useQuery({
    queryKey: ['account-value-summary', selectedAccount?.id],
    queryFn: () => accountValueSummaryApi.get(selectedAccount!.id),
    enabled: !!selectedAccount,
    staleTime: 30000,
    refetchInterval: FRESH_SUMMARY_RECHECK_MS,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  })
  const summary = query.data

  useEffect(() => {
    if (!selectedAccount || !summary) return
    if (!summary.is_stale && !summary.is_refreshing) return

    const timer = window.setTimeout(() => {
      void query.refetch()
    }, STALE_SUMMARY_RECHECK_MS)

    return () => window.clearTimeout(timer)
  }, [query.refetch, selectedAccount, summary])

  return {
    summary,
    isLoading: query.isLoading,
  }
}
