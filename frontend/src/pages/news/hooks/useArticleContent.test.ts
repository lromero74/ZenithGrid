/**
 * Tests for useArticleContent hook
 *
 * Verifies article content fetching, loading/error states,
 * reader mode toggling, caching behavior, and clearContent.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useArticleContent } from './useArticleContent'

vi.mock('../../../services/api', () => ({
  authFetch: vi.fn(),
}))

import { authFetch } from '../../../services/api'

const mockedAuthFetch = vi.mocked(authFetch)

beforeEach(() => {
  localStorage.clear()
  mockedAuthFetch.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

const mockArticle = {
  id: 1,
  title: 'Test Article',
  url: 'https://example.com/article-1',
  source: 'src1',
  source_name: 'Source 1',
  published: '2026-01-01',
  summary: 'A summary',
  thumbnail: null,
  category: 'Finance',
}

const mockContentResponse = {
  url: 'https://example.com/article-1',
  title: 'Test Article Full',
  content: '<p>Full article content here</p>',
  author: 'John Doe',
  date: '2026-01-01',
  success: true,
  error: null,
}

describe('useArticleContent initial state', () => {
  test('starts with null content and reader mode disabled', () => {
    const { result } = renderHook(() =>
      useArticleContent({ previewArticle: null })
    )

    expect(result.current.articleContent).toBeNull()
    expect(result.current.articleContentLoading).toBe(false)
    expect(result.current.readerModeEnabled).toBe(false)
  })

  test('does not fetch when previewArticle is null', () => {
    renderHook(() => useArticleContent({ previewArticle: null }))

    expect(mockedAuthFetch).not.toHaveBeenCalled()
  })
})

describe('useArticleContent fetching', () => {
  test('fetches content when reader mode is enabled with a preview article', async () => {
    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => mockContentResponse,
    } as Response)

    const { result } = renderHook(() =>
      useArticleContent({ previewArticle: mockArticle })
    )

    act(() => {
      result.current.setReaderModeEnabled(true)
    })

    await waitFor(() => {
      expect(result.current.articleContentLoading).toBe(false)
    })

    expect(result.current.articleContent).toEqual(mockContentResponse)
    expect(mockedAuthFetch).toHaveBeenCalledWith(
      `/api/news/article-content?url=${encodeURIComponent(mockArticle.url)}`
    )
  })

  test('does not fetch when reader mode is disabled', () => {
    renderHook(() =>
      useArticleContent({ previewArticle: mockArticle })
    )

    expect(mockedAuthFetch).not.toHaveBeenCalled()
  })

  test('sets loading state while fetching', async () => {
    let resolvePromise: (value: Response) => void
    const fetchPromise = new Promise<Response>((resolve) => {
      resolvePromise = resolve
    })
    mockedAuthFetch.mockReturnValue(fetchPromise)

    const { result } = renderHook(() =>
      useArticleContent({ previewArticle: mockArticle })
    )

    act(() => {
      result.current.setReaderModeEnabled(true)
    })

    await waitFor(() => {
      expect(result.current.articleContentLoading).toBe(true)
    })

    // Resolve the fetch
    await act(async () => {
      resolvePromise!({
        ok: true,
        json: async () => mockContentResponse,
      } as Response)
    })

    await waitFor(() => {
      expect(result.current.articleContentLoading).toBe(false)
    })
  })

  test('URL-encodes the article URL in the fetch', async () => {
    const specialArticle = {
      ...mockArticle,
      url: 'https://example.com/article?id=1&foo=bar',
    }

    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ ...mockContentResponse, url: specialArticle.url }),
    } as Response)

    const { result } = renderHook(() =>
      useArticleContent({ previewArticle: specialArticle })
    )

    act(() => {
      result.current.setReaderModeEnabled(true)
    })

    await waitFor(() => {
      expect(result.current.articleContentLoading).toBe(false)
    })

    expect(mockedAuthFetch).toHaveBeenCalledWith(
      `/api/news/article-content?url=${encodeURIComponent(specialArticle.url)}`
    )
  })
})

describe('useArticleContent error handling', () => {
  test('sets error content when fetch returns non-ok response', async () => {
    mockedAuthFetch.mockResolvedValue({
      ok: false,
      status: 500,
    } as Response)

    const { result } = renderHook(() =>
      useArticleContent({ previewArticle: mockArticle })
    )

    act(() => {
      result.current.setReaderModeEnabled(true)
    })

    await waitFor(() => {
      expect(result.current.articleContentLoading).toBe(false)
    })

    expect(result.current.articleContent).toEqual({
      url: mockArticle.url,
      title: null,
      content: null,
      author: null,
      date: null,
      success: false,
      error: 'Failed to connect to article extraction service',
    })
  })

  test('sets error content when fetch throws', async () => {
    mockedAuthFetch.mockRejectedValue(new Error('Network failure'))

    const { result } = renderHook(() =>
      useArticleContent({ previewArticle: mockArticle })
    )

    act(() => {
      result.current.setReaderModeEnabled(true)
    })

    await waitFor(() => {
      expect(result.current.articleContentLoading).toBe(false)
    })

    expect(result.current.articleContent?.success).toBe(false)
    expect(result.current.articleContent?.error).toBe(
      'Failed to connect to article extraction service'
    )
  })

  test('clears previous content before fetching new article', async () => {
    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => mockContentResponse,
    } as Response)

    const { result, rerender } = renderHook(
      ({ article }) => useArticleContent({ previewArticle: article }),
      { initialProps: { article: mockArticle as typeof mockArticle | null } }
    )

    // Enable reader mode and fetch first article
    act(() => { result.current.setReaderModeEnabled(true) })

    await waitFor(() => {
      expect(result.current.articleContent).toEqual(mockContentResponse)
    })

    // Switch to a new article
    const newArticle = { ...mockArticle, id: 2, url: 'https://example.com/article-2' }
    rerender({ article: newArticle })

    await waitFor(() => {
      expect(result.current.articleContentLoading).toBe(false)
    })
  })
})

describe('useArticleContent clearContent', () => {
  test('clears content and disables reader mode', async () => {
    mockedAuthFetch.mockResolvedValue({
      ok: true,
      json: async () => mockContentResponse,
    } as Response)

    const { result } = renderHook(() =>
      useArticleContent({ previewArticle: mockArticle })
    )

    act(() => { result.current.setReaderModeEnabled(true) })

    await waitFor(() => {
      expect(result.current.articleContent).toBeTruthy()
    })

    act(() => { result.current.clearContent() })

    expect(result.current.articleContent).toBeNull()
    expect(result.current.readerModeEnabled).toBe(false)
  })
})

describe('useArticleContent reader mode toggle', () => {
  test('setReaderModeEnabled enables reader mode', () => {
    const { result } = renderHook(() =>
      useArticleContent({ previewArticle: mockArticle })
    )

    act(() => { result.current.setReaderModeEnabled(true) })
    expect(result.current.readerModeEnabled).toBe(true)

    act(() => { result.current.setReaderModeEnabled(false) })
    expect(result.current.readerModeEnabled).toBe(false)
  })
})
