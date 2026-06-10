/**
 * Shared portfolio query.
 *
 * One cache entry per account for everything that needs holdings/values
 * (Bots, Charts, …) so concurrent pages share a single 60s poll instead of
 * each running their own. The Portfolio page passes `live: true` to bypass
 * the backend cache (force_fresh) — that flavor gets an isolated cache key
 * so its always-stale settings don't drag extra exchange fetches onto the
 * cheap cached flavor.
 */

import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { authFetch } from '../services/api'

async function fetchPortfolio(accountId: number | null | undefined, forceFresh: boolean) {
  const qs = forceFresh ? '?force_fresh=true' : ''
  const url = accountId
    ? `/api/accounts/${accountId}/portfolio${qs}`
    : `/api/account/portfolio${qs}`
  const response = await authFetch(url)
  if (!response.ok) throw new Error('Failed to fetch portfolio')
  return response.json()
}

export function useAccountPortfolio<T = unknown>(
  accountId: number | null | undefined,
  { live = false }: { live?: boolean } = {},
) {
  return useQuery<T>({
    queryKey: live
      ? ['account-portfolio', accountId ?? null, 'live']
      : ['account-portfolio', accountId ?? null],
    queryFn: () => fetchPortfolio(accountId, live) as Promise<T>,
    refetchInterval: 60000,
    refetchIntervalInBackground: false,
    ...(live
      ? {
          // Live exchange view: refetch whenever the page is (re)entered
          staleTime: 0,
          refetchOnMount: true,
          refetchOnWindowFocus: true,
        }
      : {
          staleTime: 30000,
          refetchOnMount: false,
          refetchOnWindowFocus: false,
          placeholderData: keepPreviousData as never,
        }),
  })
}
