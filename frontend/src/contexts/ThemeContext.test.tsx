/**
 * Tests for ThemeContext
 *
 * Tests localStorage initialization, brand default override,
 * toggleTheme cycling, and DOM class mutation.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'

// Mock BrandContext — ThemeProvider depends on useBrand()
const mockBrand = {
  name: 'Zenith Grid',
  shortName: 'Zenith Grid',
  tagline: 'Multi-Strategy Trading Platform',
  loginTitle: 'Zenith Grid',
  loginTagline: 'Multi-Strategy Trading Platform',
  company: '',
  companyLine: '',
  copyright: 'Zenith Grid',
  defaultTheme: 'classic' as 'neon' | 'classic',
  colors: { primary: '#3b82f6', primaryHover: '#2563eb' },
  images: { loginBackground: '' },
}

let mockBrandLoaded = true

vi.mock('./BrandContext', () => ({
  useBrand: () => ({
    brand: mockBrand,
    brandLoaded: mockBrandLoaded,
    brandImageUrl: (f: string) => f ? `/api/brand/images/${f}` : '',
  }),
}))

import { ThemeProvider, useTheme } from './ThemeContext'

const STORAGE_KEY = 'btcbot-theme'

// TestConsumer to expose context values
function TestConsumer() {
  const { theme, toggleTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button data-testid="toggle" onClick={toggleTheme}>Toggle</button>
    </div>
  )
}

describe('ThemeContext', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    // Reset DOM classes
    document.documentElement.classList.remove('theme-neon', 'theme-classic')
    // Reset brand mock to defaults
    mockBrand.defaultTheme = 'classic'
    mockBrandLoaded = true
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('useTheme throws when used outside ThemeProvider', () => {
    function BadConsumer() {
      useTheme()
      return <div />
    }
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<BadConsumer />)).toThrow('useTheme must be used within a ThemeProvider')
    spy.mockRestore()
  })

  test('defaults to classic theme when no localStorage value', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('theme').textContent).toBe('classic')
  })

  test('reads neon theme from localStorage', () => {
    localStorage.setItem(STORAGE_KEY, 'neon')

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('theme').textContent).toBe('neon')
  })

  test('reads classic theme from localStorage', () => {
    localStorage.setItem(STORAGE_KEY, 'classic')

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('theme').textContent).toBe('classic')
  })

  test('ignores invalid localStorage value and defaults to classic', () => {
    localStorage.setItem(STORAGE_KEY, 'invalid-theme')

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('theme').textContent).toBe('classic')
  })

  test('toggleTheme switches from classic to neon', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('theme').textContent).toBe('classic')

    act(() => {
      screen.getByTestId('toggle').click()
    })

    expect(screen.getByTestId('theme').textContent).toBe('neon')
  })

  test('toggleTheme switches from neon to classic', () => {
    localStorage.setItem(STORAGE_KEY, 'neon')

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('theme').textContent).toBe('neon')

    act(() => {
      screen.getByTestId('toggle').click()
    })

    expect(screen.getByTestId('theme').textContent).toBe('classic')
  })

  test('toggleTheme cycles correctly through multiple toggles', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('theme').textContent).toBe('classic')

    act(() => { screen.getByTestId('toggle').click() })
    expect(screen.getByTestId('theme').textContent).toBe('neon')

    act(() => { screen.getByTestId('toggle').click() })
    expect(screen.getByTestId('theme').textContent).toBe('classic')

    act(() => { screen.getByTestId('toggle').click() })
    expect(screen.getByTestId('theme').textContent).toBe('neon')
  })

  test('adds theme class to document.documentElement', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    expect(document.documentElement.classList.contains('theme-classic')).toBe(true)
    expect(document.documentElement.classList.contains('theme-neon')).toBe(false)
  })

  test('updates DOM class when theme toggles', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    expect(document.documentElement.classList.contains('theme-classic')).toBe(true)

    act(() => { screen.getByTestId('toggle').click() })

    expect(document.documentElement.classList.contains('theme-neon')).toBe(true)
    expect(document.documentElement.classList.contains('theme-classic')).toBe(false)
  })

  test('persists theme to localStorage on toggle', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    act(() => { screen.getByTestId('toggle').click() })

    expect(localStorage.getItem(STORAGE_KEY)).toBe('neon')

    act(() => { screen.getByTestId('toggle').click() })

    expect(localStorage.getItem(STORAGE_KEY)).toBe('classic')
  })

  test('applies brand default theme when no user preference exists', () => {
    mockBrand.defaultTheme = 'neon'
    mockBrandLoaded = true

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    // Brand default 'neon' should apply since no localStorage preference
    expect(screen.getByTestId('theme').textContent).toBe('neon')
  })

  test('user preference in localStorage overrides brand default', () => {
    localStorage.setItem(STORAGE_KEY, 'classic')
    mockBrand.defaultTheme = 'neon'
    mockBrandLoaded = true

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    // User preference should win over brand default
    expect(screen.getByTestId('theme').textContent).toBe('classic')
  })

  test('does not apply brand default when brand is not loaded yet', () => {
    mockBrand.defaultTheme = 'neon'
    mockBrandLoaded = false

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    // Should remain at safe default (classic) until brand loads
    expect(screen.getByTestId('theme').textContent).toBe('classic')
  })

  test('removes old theme class before adding new one', () => {
    // Start with classic
    document.documentElement.classList.add('theme-classic')

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>
    )

    act(() => { screen.getByTestId('toggle').click() })

    // Should NOT have both
    const classes = document.documentElement.classList
    expect(classes.contains('theme-neon')).toBe(true)
    expect(classes.contains('theme-classic')).toBe(false)
  })
})
