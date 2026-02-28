/**
 * Tests for useSeenStatus hook
 *
 * Verifies mark-seen API mutations, optimistic cache updates,
 * bulk operations, and revert-on-failure behavior.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useSeenStatus } from './useSeenStatus'

vi.mock('../../../services/api', () => ({
  authFetch: vi.fn(),
}))

import { authFetch } from '../../../services/api'

const mockedAuthFetch = vi.mocked(authFetch)

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  })
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

const mockNewsData = {
  news: [
    { id: 1, title: 'Article 1', url: 'https://example.com/1', source: 's1', source_name: 'Source', published: null, summary: null, thumbnail: null, category: 'Finance', is_seen: false },
    { id: 2, title: 'Article 2', url: 'https://example.com/2', source: 's1', source_name: 'Source', published: null, summary: null, thumbnail: null, category: 'Tech', is_seen: false },
    { id: 3, title: 'Article 3', url: 'https://example.com/3', source: 's2', source_name: 'Source 2', published: null, summary: null, thumbnail: null, category: 'Finance', is_seen: true },
  ],
  sources: [],
  cached_at: '',
  cache_expires_at: '',
  total_items: 3,
  page: 1,
  page_size: 0,
  total_pages: 1,
}

const mockVideoData = {
  videos: [
    { id: 10, title: 'Video 1', url: 'https://yt.com/1', video_id: 'v1', source: 'yt', source_name: 'YT', channel_name: 'Ch', published: null, thumbnail: null, description: null, category: 'Crypto', is_seen: false },
    { id: 11, title: 'Video 2', url: 'https://yt.com/2', video_id: 'v2', source: 'yt', source_name: 'YT', channel_name: 'Ch', published: null, thumbnail: null, description: null, category: 'Crypto', is_seen: true },
  ],
  sources: [],
  cached_at: '',
  cache_expires_at: '',
  total_items: 2,
}

beforeEach(() => {
  localStorage.clear()
  mockedAuthFetch.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useSeenStatus markSeen', () => {
  test('optimistically marks an article as seen in cache', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-news'], mockNewsData)
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.markSeen('article', 1, true)
    })

    const cached = qc.getQueryData<typeof mockNewsData>(['crypto-news'])
    expect(cached!.news[0].is_seen).toBe(true)
  })

  test('calls authFetch with correct payload for article', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-news'], mockNewsData)
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.markSeen('article', 1, true)
    })

    expect(mockedAuthFetch).toHaveBeenCalledWith('/api/news/seen', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_type: 'article', content_id: 1, seen: true }),
    })
  })

  test('optimistically marks a video as seen in cache', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-videos'], mockVideoData)
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.markSeen('video', 10, true)
    })

    const cached = qc.getQueryData<typeof mockVideoData>(['crypto-videos'])
    expect(cached!.videos[0].is_seen).toBe(true)
  })

  test('defaults seen to true when not specified', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-news'], mockNewsData)
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.markSeen('article', 1)
    })

    expect(mockedAuthFetch).toHaveBeenCalledWith('/api/news/seen', expect.objectContaining({
      body: JSON.stringify({ content_type: 'article', content_id: 1, seen: true }),
    }))
  })

  test('marks article as unseen when seen=false', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-news'], mockNewsData)
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.markSeen('article', 3, false)
    })

    const cached = qc.getQueryData<typeof mockNewsData>(['crypto-news'])
    expect(cached!.news[2].is_seen).toBe(false)
  })

  test('reverts optimistic update on API failure', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-news'], mockNewsData)
    mockedAuthFetch.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.markSeen('article', 1, true)
    })

    // Should revert to original false
    const cached = qc.getQueryData<typeof mockNewsData>(['crypto-news'])
    expect(cached!.news[0].is_seen).toBe(false)
  })

  test('does not affect other articles when marking one as seen', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-news'], mockNewsData)
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.markSeen('article', 1, true)
    })

    const cached = qc.getQueryData<typeof mockNewsData>(['crypto-news'])
    expect(cached!.news[1].is_seen).toBe(false) // Article 2 unchanged
    expect(cached!.news[2].is_seen).toBe(true)  // Article 3 unchanged
  })
})

describe('useSeenStatus bulkMarkSeen', () => {
  test('optimistically marks multiple articles as seen', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-news'], mockNewsData)
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.bulkMarkSeen('article', [1, 2], true)
    })

    const cached = qc.getQueryData<typeof mockNewsData>(['crypto-news'])
    expect(cached!.news[0].is_seen).toBe(true)
    expect(cached!.news[1].is_seen).toBe(true)
  })

  test('calls authFetch with bulk endpoint and correct payload', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-news'], mockNewsData)
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.bulkMarkSeen('article', [1, 2], true)
    })

    expect(mockedAuthFetch).toHaveBeenCalledWith('/api/news/seen/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_type: 'article', content_ids: [1, 2], seen: true }),
    })
  })

  test('skips API call when contentIds is empty', async () => {
    const qc = createQueryClient()
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.bulkMarkSeen('article', [], true)
    })

    expect(mockedAuthFetch).not.toHaveBeenCalled()
  })

  test('reverts bulk optimistic update on API failure', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-news'], mockNewsData)
    mockedAuthFetch.mockRejectedValue(new Error('Server error'))

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.bulkMarkSeen('article', [1, 2], true)
    })

    const cached = qc.getQueryData<typeof mockNewsData>(['crypto-news'])
    expect(cached!.news[0].is_seen).toBe(false) // reverted
    expect(cached!.news[1].is_seen).toBe(false) // reverted
  })

  test('bulk marks videos as seen correctly', async () => {
    const qc = createQueryClient()
    qc.setQueryData(['crypto-videos'], mockVideoData)
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    await act(async () => {
      await result.current.bulkMarkSeen('video', [10], true)
    })

    const cached = qc.getQueryData<typeof mockVideoData>(['crypto-videos'])
    expect(cached!.videos[0].is_seen).toBe(true)
  })

  test('handles missing cache data gracefully (does not throw)', async () => {
    const qc = createQueryClient()
    // Intentionally do NOT set any cache data
    mockedAuthFetch.mockResolvedValue({ ok: true } as Response)

    const { result } = renderHook(() => useSeenStatus(), { wrapper: createWrapper(qc) })

    // Should not throw even though cache is empty
    await act(async () => {
      await result.current.markSeen('article', 999, true)
    })

    expect(mockedAuthFetch).toHaveBeenCalled()
  })
})
