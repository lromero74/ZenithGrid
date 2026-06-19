import { beforeEach, describe, expect, test, vi } from 'vitest'

import { markStartupMilestone } from './startupPerformance'

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
})
