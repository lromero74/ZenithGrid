import { describe, test, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useMediaQuery } from './useMediaQuery'

type Listener = () => void

function mockMatchMedia(initialMatches: boolean) {
  let matches = initialMatches
  const listeners = new Set<Listener>()
  const mql = {
    get matches() { return matches },
    media: '',
    addEventListener: (_: string, cb: Listener) => listeners.add(cb),
    removeEventListener: (_: string, cb: Listener) => listeners.delete(cb),
    // test helper to flip the query result
    _set: (v: boolean) => { matches = v; listeners.forEach(cb => cb()) },
  }
  window.matchMedia = vi.fn().mockReturnValue(mql) as unknown as typeof window.matchMedia
  return mql
}

afterEach(() => {
  vi.restoreAllMocks()
  // @ts-expect-error reset for next test
  delete window.matchMedia
})

describe('useMediaQuery', () => {
  test('happy path: returns the initial match state', () => {
    mockMatchMedia(true)
    const { result } = renderHook(() => useMediaQuery('(min-width: 1024px)'))
    expect(result.current).toBe(true)
  })

  test('edge: updates when the query starts matching', () => {
    const mql = mockMatchMedia(false)
    const { result } = renderHook(() => useMediaQuery('(min-width: 1536px)'))
    expect(result.current).toBe(false)

    act(() => { mql._set(true) })
    expect(result.current).toBe(true)
  })

  test('failure: returns false when matchMedia is unavailable', () => {
    // @ts-expect-error simulate an environment without matchMedia
    delete window.matchMedia
    const { result } = renderHook(() => useMediaQuery('(min-width: 1024px)'))
    expect(result.current).toBe(false)
  })
})
