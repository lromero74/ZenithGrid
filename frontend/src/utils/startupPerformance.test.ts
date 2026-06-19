import { beforeEach, describe, expect, test, vi } from 'vitest'

import { markStartupMilestone, reportStartupPerformance } from './startupPerformance'

describe('startup performance marks', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  test('records each milestone once and measures it from bootstrap', () => {
    const mark = vi.spyOn(performance, 'mark').mockImplementation(() => ({} as PerformanceMark))
    const measure = vi.spyOn(performance, 'measure').mockImplementation(() => ({} as PerformanceMeasure))
    vi.spyOn(performance, 'getEntriesByName')
      .mockReturnValueOnce([])
      .mockReturnValueOnce([{} as PerformanceEntry])

    markStartupMilestone('auth-ready')
    markStartupMilestone('auth-ready')

    expect(mark).toHaveBeenCalledOnce()
    expect(mark).toHaveBeenCalledWith('zenith:auth-ready')
    expect(measure).toHaveBeenCalledWith(
      'zenith:bootstrap-to-auth-ready',
      'zenith:bootstrap',
      'zenith:auth-ready',
    )
  })

  test('reports only normalized anonymous startup measures', async () => {
    localStorage.setItem('auth_access_token', 'token')
    vi.spyOn(performance, 'getEntriesByType').mockReturnValue([
      { name: 'zenith:bootstrap-to-positions-data-ready', duration: 123.45 } as PerformanceEntry,
      { name: 'unrelated', duration: 8 } as PerformanceEntry,
    ])
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))

    reportStartupPerformance('/positions/193')

    expect(fetchMock).toHaveBeenCalledWith('/api/performance/client', expect.objectContaining({
      body: JSON.stringify({
        route: '/positions',
        timings: { 'zenith:bootstrap-to-positions-data-ready': 123.5 },
      }),
    }))
    localStorage.removeItem('auth_access_token')
  })
})
