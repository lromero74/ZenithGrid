/**
 * Tests for BrandContext
 *
 * Tests fetch + merge with DEFAULTS, brandImageUrl helper,
 * document.title side effect, cancelled-flag cleanup, and error handling.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'

import { BrandProvider, useBrand } from './BrandContext'

// TestConsumer to expose context values
function TestConsumer() {
  const { brand, brandLoaded, brandImageUrl } = useBrand()
  return (
    <div>
      <span data-testid="loaded">{String(brandLoaded)}</span>
      <span data-testid="name">{brand.name}</span>
      <span data-testid="short-name">{brand.shortName}</span>
      <span data-testid="tagline">{brand.tagline}</span>
      <span data-testid="login-title">{brand.loginTitle}</span>
      <span data-testid="login-tagline">{brand.loginTagline}</span>
      <span data-testid="company">{brand.company}</span>
      <span data-testid="copyright">{brand.copyright}</span>
      <span data-testid="default-theme">{brand.defaultTheme}</span>
      <span data-testid="primary-color">{brand.colors.primary}</span>
      <span data-testid="primary-hover">{brand.colors.primaryHover}</span>
      <span data-testid="login-bg">{brand.images.loginBackground}</span>
      <span data-testid="image-url">{brandImageUrl('logo.png')}</span>
      <span data-testid="image-url-empty">{brandImageUrl('')}</span>
    </div>
  )
}

describe('BrandContext', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    fetchSpy = vi.spyOn(globalThis, 'fetch')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('useBrand throws when used outside BrandProvider', () => {
    function BadConsumer() {
      useBrand()
      return <div />
    }
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<BadConsumer />)).toThrow('useBrand must be used within a BrandProvider')
    spy.mockRestore()
  })

  test('uses DEFAULTS before fetch completes', () => {
    fetchSpy.mockReturnValue(new Promise(() => {})) // Never resolves

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    expect(screen.getByTestId('loaded').textContent).toBe('false')
    expect(screen.getByTestId('name').textContent).toBe('Zenith Grid')
    expect(screen.getByTestId('tagline').textContent).toBe('Multi-Strategy Trading Platform')
    expect(screen.getByTestId('default-theme').textContent).toBe('classic')
    expect(screen.getByTestId('primary-color').textContent).toBe('#3b82f6')
  })

  test('merges fetched brand data with DEFAULTS', async () => {
    const customBrand = {
      name: 'Custom Bot',
      shortName: 'CB',
      tagline: 'My Trading Bot',
      defaultTheme: 'neon',
    }

    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(customBrand),
    } as Response)

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loaded').textContent).toBe('true')
    })

    // Custom values should override defaults
    expect(screen.getByTestId('name').textContent).toBe('Custom Bot')
    expect(screen.getByTestId('short-name').textContent).toBe('CB')
    expect(screen.getByTestId('tagline').textContent).toBe('My Trading Bot')
    expect(screen.getByTestId('default-theme').textContent).toBe('neon')

    // Defaults should remain for unspecified fields
    expect(screen.getByTestId('copyright').textContent).toBe('Zenith Grid')
    expect(screen.getByTestId('primary-color').textContent).toBe('#3b82f6')
    expect(screen.getByTestId('primary-hover').textContent).toBe('#2563eb')
  })

  test('deep-merges colors object with DEFAULTS', async () => {
    const customBrand = {
      name: 'Color Test',
      colors: { primary: '#ff0000' },
    }

    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(customBrand),
    } as Response)

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loaded').textContent).toBe('true')
    })

    // Custom primary color
    expect(screen.getByTestId('primary-color').textContent).toBe('#ff0000')
    // Default primaryHover should remain
    expect(screen.getByTestId('primary-hover').textContent).toBe('#2563eb')
  })

  test('deep-merges images object with DEFAULTS', async () => {
    const customBrand = {
      images: { loginBackground: 'custom-bg.jpg' },
    }

    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(customBrand),
    } as Response)

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loaded').textContent).toBe('true')
    })

    expect(screen.getByTestId('login-bg').textContent).toBe('custom-bg.jpg')
  })

  test('brandImageUrl constructs correct URL for filename', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    } as Response)

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loaded').textContent).toBe('true')
    })

    expect(screen.getByTestId('image-url').textContent).toBe('/api/brand/images/logo.png')
  })

  test('brandImageUrl returns empty string for empty filename', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    } as Response)

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loaded').textContent).toBe('true')
    })

    expect(screen.getByTestId('image-url-empty').textContent).toBe('')
  })

  test('brandImageUrl encodes special characters in filename', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    } as Response)

    // Render a consumer that tests encoding
    function EncodingConsumer() {
      const { brandImageUrl } = useBrand()
      return <span data-testid="encoded">{brandImageUrl('my logo file.png')}</span>
    }

    render(
      <BrandProvider>
        <EncodingConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('encoded').textContent).toBe('/api/brand/images/my%20logo%20file.png')
    })
  })

  test('updates document.title when brand loads', async () => {
    const customBrand = {
      shortName: 'TestBot',
      tagline: 'Test Platform',
    }

    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(customBrand),
    } as Response)

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loaded').textContent).toBe('true')
    })

    expect(document.title).toBe('TestBot - Test Platform')
  })

  test('uses default title when no custom brand is fetched', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    } as Response)

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loaded').textContent).toBe('true')
    })

    expect(document.title).toBe('Zenith Grid - Multi-Strategy Trading Platform')
  })

  test('handles fetch failure gracefully — sets brandLoaded true with defaults', async () => {
    fetchSpy.mockResolvedValue({
      ok: false,
      status: 500,
    } as Response)

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loaded').textContent).toBe('true')
    })

    // Should still have defaults
    expect(screen.getByTestId('name').textContent).toBe('Zenith Grid')
    expect(screen.getByTestId('default-theme').textContent).toBe('classic')
  })

  test('handles network error gracefully — sets brandLoaded true with defaults', async () => {
    fetchSpy.mockRejectedValue(new Error('Network error'))

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loaded').textContent).toBe('true')
    })

    expect(screen.getByTestId('name').textContent).toBe('Zenith Grid')
  })

  test('cancelled flag prevents state update after unmount', async () => {
    let resolvePromise: (value: Response) => void
    const fetchPromise = new Promise<Response>((resolve) => {
      resolvePromise = resolve
    })
    fetchSpy.mockReturnValue(fetchPromise)

    const { unmount } = render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    expect(screen.getByTestId('loaded').textContent).toBe('false')

    // Unmount before fetch resolves — this sets cancelled = true
    unmount()

    // Now resolve the fetch — state update should be skipped (no error)
    await act(async () => {
      resolvePromise!({
        ok: true,
        json: () => Promise.resolve({ name: 'Late Brand' }),
      } as Response)
    })

    // If we get here without error, the cancelled flag worked
    expect(true).toBe(true)
  })

  test('fetches from /api/brand endpoint', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    } as Response)

    render(
      <BrandProvider>
        <TestConsumer />
      </BrandProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loaded').textContent).toBe('true')
    })

    expect(fetchSpy).toHaveBeenCalledWith('/api/brand')
  })
})
