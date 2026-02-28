/**
 * Tests for useNewsData hook
 *
 * Verifies news and video feed fetching via React Query,
 * loading/error states, refetch behavior, and force refresh.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useNewsData } from './useNewsData'

vi.mock('../../../services/api', () => ({
  authFetch: vi.fn(),
}))

import { authFetch } from '../../../services/api'

const mockedAuthFetch = vi.mocked(authFetch)

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

const mockNewsResponse = {
  news: [
    { id: 1, title: 'BTC up', url: 'https://example.com/1', source: 'src1', source_name: 'Source 1', published: '2026-01-01', summary: 'Summary', thumbnail: null, category: 'CryptoCurrency' },
    { id: 2, title: 'ETH down', url: 'https://example.com/2', source: 'src2', source_name: 'Source 2', published: '2026-01-02', summary: 'Summary 2', thumbnail: null, category: 'Finance' },
  ],
  sources: [{ id: 'src1', name: 'Source 1', website: 'https://example.com' }],
  cached_at: '2026-01-01T00:00:00Z',
  cache_expires_at: '2026-01-01T01:00:00Z',
  total_items: 2,
  page: 1,
  page_size: 0,
  total_pages: 1,
}

const mockVideoResponse = {
  videos: [
    { id: 10, title: 'Crypto video', url: 'https://yt.com/1', video_id: 'v1', source: 'yt1', source_name: 'YT Channel', channel_name: 'Channel', published: '2026-01-01', thumbnail: null, description: 'Desc', category: 'CryptoCurrency' },
  ],
  sources: [{ id: 'yt1', name: 'YT Channel', website: 'https://youtube.com', description: 'A channel' }],
  cached_at: '2026-01-01T00:00:00Z',
  cache_expires_at: '2026-01-01T01:00:00Z',
  total_items: 1,
}

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useNewsData initial state', () => {
  test('starts with loading state and undefined data', () => {
    mockedAuthFetch.mockImplementation(() => new Promise(() => {})) // Never resolves
    const { result } = renderHook(() => useNewsData(), { wrapper: createWrapper() })

    expect(result.current.newsLoading).toBe(true)
    expect(result.current.videosLoading).toBe(true)
    expect(result.current.newsData).toBeUndefined()
    expect(result.current.videoData).toBeUndefined()
    expect(result.current.newsError).toBeNull()
    expect(result.current.videosError).toBeNull()
  })
})

describe('useNewsData successful fetch', () => {
  test('fetches news data successfully', async () => {
    mockedAuthFetch.mockImplementation(async (url: string) => {
      if (url.includes('/api/news/videos')) {
        return { ok: true, json: async () => mockVideoResponse } as Response
      }
      return { ok: true, json: async () => mockNewsResponse } as Response
    })

    const { result } = renderHook(() => useNewsData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.newsLoading).toBe(false)
    })

    expect(result.current.newsData).toEqual(mockNewsResponse)
    expect(result.current.newsError).toBeNull()
  })

  test('fetches video data successfully', async () => {
    mockedAuthFetch.mockImplementation(async (url: string) => {
      if (url.includes('/api/news/videos')) {
        return { ok: true, json: async () => mockVideoResponse } as Response
      }
      return { ok: true, json: async () => mockNewsResponse } as Response
    })

    const { result } = renderHook(() => useNewsData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.videosLoading).toBe(false)
    })

    expect(result.current.videoData).toEqual(mockVideoResponse)
    expect(result.current.videosError).toBeNull()
  })

  test('calls authFetch with correct URLs', async () => {
    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => mockNewsResponse,
    } as Response)

    renderHook(() => useNewsData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(mockedAuthFetch).toHaveBeenCalledWith('/api/news/?page_size=0')
      expect(mockedAuthFetch).toHaveBeenCalledWith('/api/news/videos')
    })
  })
})

describe('useNewsData error handling', () => {
  test('sets newsError when news fetch returns non-ok', async () => {
    mockedAuthFetch.mockImplementation(async (url: string) => {
      if (url.includes('/api/news/videos')) {
        return { ok: true, json: async () => mockVideoResponse } as Response
      }
      return { ok: false, status: 500 } as Response
    })

    const { result } = renderHook(() => useNewsData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.newsError).toBeTruthy()
    })

    expect(result.current.newsError!.message).toBe('Failed to fetch news')
  })

  test('sets videosError when video fetch returns non-ok', async () => {
    mockedAuthFetch.mockImplementation(async (url: string) => {
      if (url.includes('/api/news/videos')) {
        return { ok: false, status: 500 } as Response
      }
      return { ok: true, json: async () => mockNewsResponse } as Response
    })

    const { result } = renderHook(() => useNewsData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.videosError).toBeTruthy()
    })

    expect(result.current.videosError!.message).toBe('Failed to fetch videos')
  })

  test('sets error when authFetch throws', async () => {
    mockedAuthFetch.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useNewsData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.newsError).toBeTruthy()
    })

    expect(result.current.newsError!.message).toBe('Network error')
  })
})

describe('useNewsData handleForceRefresh', () => {
  test('calls force_refresh for articles tab', async () => {
    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => mockNewsResponse,
    } as Response)

    const { result } = renderHook(() => useNewsData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.newsLoading).toBe(false)
    })

    mockedAuthFetch.mockClear()
    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => mockNewsResponse,
    } as Response)

    await result.current.handleForceRefresh('articles')

    expect(mockedAuthFetch).toHaveBeenCalledWith('/api/news/?force_refresh=true')
  })

  test('calls force_refresh for videos tab', async () => {
    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => mockVideoResponse,
    } as Response)

    const { result } = renderHook(() => useNewsData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.videosLoading).toBe(false)
    })

    mockedAuthFetch.mockClear()
    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => mockVideoResponse,
    } as Response)

    await result.current.handleForceRefresh('videos')

    expect(mockedAuthFetch).toHaveBeenCalledWith('/api/news/videos?force_refresh=true')
  })
})

describe('useNewsData refetch functions', () => {
  test('provides refetchNews and refetchVideos functions', async () => {
    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => mockNewsResponse,
    } as Response)

    const { result } = renderHook(() => useNewsData(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.newsLoading).toBe(false)
    })

    expect(typeof result.current.refetchNews).toBe('function')
    expect(typeof result.current.refetchVideos).toBe('function')
  })
})

describe('useNewsData isUserEngaged option', () => {
  test('returns all expected properties when user is engaged', async () => {
    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => mockNewsResponse,
    } as Response)

    const { result } = renderHook(
      () => useNewsData({ isUserEngaged: true }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.newsLoading).toBe(false)
    })

    // Verify all return properties exist
    expect(result.current).toHaveProperty('newsData')
    expect(result.current).toHaveProperty('videoData')
    expect(result.current).toHaveProperty('newsLoading')
    expect(result.current).toHaveProperty('videosLoading')
    expect(result.current).toHaveProperty('newsError')
    expect(result.current).toHaveProperty('videosError')
    expect(result.current).toHaveProperty('newsFetching')
    expect(result.current).toHaveProperty('videosFetching')
    expect(result.current).toHaveProperty('refetchNews')
    expect(result.current).toHaveProperty('refetchVideos')
    expect(result.current).toHaveProperty('handleForceRefresh')
  })
})
