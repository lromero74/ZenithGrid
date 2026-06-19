import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import {
  clearSessionQueryCache,
  hydrateSessionQueries,
  persistSessionQueries,
  shouldPersistStartupQuery,
} from './sessionQueryPersistence'

describe('session query persistence', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  test('only allows user-keyed or numeric account-keyed startup queries', () => {
    expect(shouldPersistStartupQuery(['accounts'])).toBe(true)
    expect(shouldPersistStartupQuery(['positions', 'open', 7])).toBe(true)
    expect(shouldPersistStartupQuery(['positions-page-summary', 7])).toBe(true)
    expect(shouldPersistStartupQuery(['bots', null])).toBe(false)
    expect(shouldPersistStartupQuery(['positions', 'open', undefined])).toBe(false)
    expect(shouldPersistStartupQuery(['realized-pnl', 7])).toBe(false)
  })

  test('hydrates only the matching user and marks cached data stale', () => {
    const source = new QueryClient()
    source.setQueryData(['positions', 'open', 7], [{ id: 1 }])
    source.setQueryData(['invitations', 'pending'], [{ token: 'secret' }])
    persistSessionQueries(source, 42)

    const target = new QueryClient()
    expect(hydrateSessionQueries(target, 42)).toBe(true)
    expect(target.getQueryData(['positions', 'open', 7])).toEqual([{ id: 1 }])
    expect(target.getQueryData(['invitations', 'pending'])).toBeUndefined()
    expect(target.getQueryState(['positions', 'open', 7])?.dataUpdatedAt).toBe(0)

    expect(hydrateSessionQueries(new QueryClient(), 99)).toBe(false)
  })

  test('rejects expired snapshots and supports explicit logout cleanup', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_000)
    const source = new QueryClient()
    source.setQueryData(['accounts'], [{ id: 7 }])
    persistSessionQueries(source, 42)

    expect(hydrateSessionQueries(new QueryClient(), 42, 121_001)).toBe(false)

    persistSessionQueries(source, 42)
    clearSessionQueryCache(42)
    expect(hydrateSessionQueries(new QueryClient(), 42, 1_001)).toBe(false)
  })
})
