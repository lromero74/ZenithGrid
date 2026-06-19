import { dehydrate, hydrate, type DehydratedState, type QueryClient, type QueryKey } from '@tanstack/react-query'

const CACHE_PREFIX = 'zenith-query-cache-v1'
const CACHE_TTL_MS = 2 * 60 * 1000

interface StoredQueryCache {
  userId: number
  savedAt: number
  state: DehydratedState
}

function cacheKey(userId: number): string {
  return `${CACHE_PREFIX}:${userId}`
}

function hasNumericAccountId(queryKey: QueryKey, index: number): boolean {
  return typeof queryKey[index] === 'number' && Number.isFinite(queryKey[index])
}

export function shouldPersistStartupQuery(queryKey: QueryKey): boolean {
  if (queryKey[0] === 'accounts') return queryKey.length === 1
  if (queryKey[0] === 'positions-page-summary') return hasNumericAccountId(queryKey, 1)
  if (queryKey[0] === 'bots') return hasNumericAccountId(queryKey, 1)
  if (queryKey[0] === 'account-portfolio') return hasNumericAccountId(queryKey, 1)
  if (queryKey[0] === 'available-products') return hasNumericAccountId(queryKey, 1)
  return queryKey[0] === 'positions'
    && queryKey[1] === 'open'
    && hasNumericAccountId(queryKey, 2)
}

export function getStoredAuthUserId(): number | null {
  try {
    const user = JSON.parse(localStorage.getItem('auth_user') || 'null')
    return typeof user?.id === 'number' ? user.id : null
  } catch {
    return null
  }
}

export function hydrateSessionQueries(
  queryClient: QueryClient,
  userId: number,
  now = Date.now(),
): boolean {
  try {
    const raw = sessionStorage.getItem(cacheKey(userId))
    if (!raw) return false
    const stored = JSON.parse(raw) as StoredQueryCache
    if (stored.userId !== userId || now - stored.savedAt > CACHE_TTL_MS) {
      sessionStorage.removeItem(cacheKey(userId))
      return false
    }

    // Render the cached snapshot immediately, but make every hydrated query stale
    // so production remains authoritative and React Query revalidates on mount.
    const staleState: DehydratedState = {
      ...stored.state,
      queries: stored.state.queries.map((query) => ({
        ...query,
        state: { ...query.state, dataUpdatedAt: 0 },
      })),
    }
    hydrate(queryClient, staleState)
    return true
  } catch {
    sessionStorage.removeItem(cacheKey(userId))
    return false
  }
}

export function persistSessionQueries(queryClient: QueryClient, userId: number): void {
  const state = dehydrate(queryClient, {
    shouldDehydrateQuery: (query) => query.state.status === 'success'
      && shouldPersistStartupQuery(query.queryKey),
  })
  const stored: StoredQueryCache = { userId, savedAt: Date.now(), state }
  sessionStorage.setItem(cacheKey(userId), JSON.stringify(stored))
}

export function installSessionQueryPersistence(queryClient: QueryClient, userId: number): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined
  const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.query.state.status !== 'success') return
    if (!shouldPersistStartupQuery(event.query.queryKey)) return
    clearTimeout(timer)
    timer = setTimeout(() => persistSessionQueries(queryClient, userId), 100)
  })
  return () => {
    clearTimeout(timer)
    unsubscribe()
  }
}

export function clearSessionQueryCache(userId: number): void {
  sessionStorage.removeItem(cacheKey(userId))
}
