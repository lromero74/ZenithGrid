import {
  getFearGreedColor,
  formatDebt,
  calculateDebtMilestone,
  formatDebtCountdown,
  formatExtendedCountdown,
  calculateHalvingCountdown,
  NEXT_HALVING_BLOCK,
  BLOCKS_PER_HALVING,
} from './marketSentiment'

// ── getFearGreedColor ────────────────────────────────────────────────

describe('getFearGreedColor', () => {
  test('extreme fear (0-25) returns red', () => {
    expect(getFearGreedColor(0).text).toBe('text-red-400')
    expect(getFearGreedColor(25).text).toBe('text-red-400')
  })

  test('fear (26-45) returns orange', () => {
    expect(getFearGreedColor(26).text).toBe('text-orange-400')
    expect(getFearGreedColor(45).text).toBe('text-orange-400')
  })

  test('neutral (46-55) returns yellow', () => {
    expect(getFearGreedColor(46).text).toBe('text-yellow-400')
    expect(getFearGreedColor(55).text).toBe('text-yellow-400')
  })

  test('greed (56-75) returns lime', () => {
    expect(getFearGreedColor(56).text).toBe('text-lime-400')
    expect(getFearGreedColor(75).text).toBe('text-lime-400')
  })

  test('extreme greed (76-100) returns green', () => {
    expect(getFearGreedColor(76).text).toBe('text-green-400')
    expect(getFearGreedColor(100).text).toBe('text-green-400')
  })

  test('returns all 4 color properties', () => {
    const result = getFearGreedColor(50)
    expect(result).toHaveProperty('bg')
    expect(result).toHaveProperty('text')
    expect(result).toHaveProperty('border')
    expect(result).toHaveProperty('gradient')
  })
})

// ── formatDebt ───────────────────────────────────────────────────────

describe('formatDebt', () => {
  test('formats large numbers with commas', () => {
    expect(formatDebt(36_000_000_000_000)).toBe('36,000,000,000,000')
  })

  test('formats small numbers', () => {
    expect(formatDebt(1234)).toBe('1,234')
  })

  test('formats zero', () => {
    expect(formatDebt(0)).toBe('0')
  })
})

// ── calculateDebtMilestone ───────────────────────────────────────────

describe('calculateDebtMilestone', () => {
  test('increasing debt finds next trillion milestone', () => {
    const result = calculateDebtMilestone(36_500_000_000_000, 100_000, 1)
    // Next milestone should be 37 trillion
    expect(result.milestone).toBe(37_000_000_000_000)
    expect(result.isIncreasing).toBe(true)
    expect(result.secondsUntil).toBeGreaterThan(0)
    expect(result.estimatedDate.getTime()).toBeGreaterThan(Date.now())
  })

  test('decreasing debt finds next milestone below', () => {
    const result = calculateDebtMilestone(36_500_000_000_000, -100_000, 1)
    // Next milestone should be 36 trillion (going down)
    expect(result.milestone).toBe(36_000_000_000_000)
    expect(result.isIncreasing).toBe(false)
    expect(result.secondsUntil).toBeGreaterThan(0)
  })

  test('exactly on a milestone jumps to next', () => {
    const result = calculateDebtMilestone(36_000_000_000_000, 100_000, 1)
    expect(result.milestone).toBe(37_000_000_000_000)
  })

  test('exactly on a milestone with decreasing debt', () => {
    const result = calculateDebtMilestone(36_000_000_000_000, -100_000, 1)
    expect(result.milestone).toBe(35_000_000_000_000)
  })

  test('custom milestone size', () => {
    const result = calculateDebtMilestone(36_500_000_000_000, 100_000, 5)
    // Next 5-trillion milestone above 36.5T is 40T
    expect(result.milestone).toBe(40_000_000_000_000)
  })
})

// ── formatDebtCountdown ──────────────────────────────────────────────

describe('formatDebtCountdown', () => {
  test('years format (> 365 days)', () => {
    const twoYears = 2 * 365 * 24 * 60 * 60
    const result = formatDebtCountdown(twoYears)
    expect(result).toBe('2y 0mo')
  })

  test('months format (31-365 days)', () => {
    const threeMonths = 90 * 24 * 60 * 60
    const result = formatDebtCountdown(threeMonths)
    expect(result).toBe('3mo 0d')
  })

  test('days format (1-30 days)', () => {
    const fiveDays = 5 * 24 * 60 * 60 + 3 * 60 * 60 // 5d 3h
    const result = formatDebtCountdown(fiveDays)
    expect(result).toBe('5d 3h')
  })

  test('hours format (< 1 day)', () => {
    const threeHours = 3 * 60 * 60 + 15 * 60 // 3h 15m
    const result = formatDebtCountdown(threeHours)
    expect(result).toBe('3h 15m')
  })

  test('zero seconds', () => {
    expect(formatDebtCountdown(0)).toBe('0h 0m')
  })
})

// ── formatExtendedCountdown ──────────────────────────────────────────

describe('formatExtendedCountdown', () => {
  test('zero or negative returns halving imminent', () => {
    expect(formatExtendedCountdown(0)).toBe('Halving imminent!')
    expect(formatExtendedCountdown(-1000)).toBe('Halving imminent!')
  })

  test('years, months, days, hours format', () => {
    // ~1.5 years in milliseconds
    const ms = (365.25 + 60) * 24 * 60 * 60 * 1000
    const result = formatExtendedCountdown(ms)
    expect(result).toMatch(/1y/)
    expect(result).toMatch(/mo/)
  })

  test('hours only (less than 1 day)', () => {
    const ms = 5 * 60 * 60 * 1000 // 5 hours
    const result = formatExtendedCountdown(ms)
    // Should not contain y, mo, or d parts
    expect(result).not.toMatch(/y /)
    expect(result).not.toMatch(/mo/)
    expect(result).toMatch(/h/)
    expect(result).toMatch(/m/)
    expect(result).toMatch(/s/)
  })

  test('includes seconds', () => {
    const ms = 90 * 24 * 60 * 60 * 1000 // 90 days
    const result = formatExtendedCountdown(ms)
    expect(result).toMatch(/\d+s/)
  })
})

// ── calculateHalvingCountdown ────────────────────────────────────────

describe('calculateHalvingCountdown', () => {
  test('returns correct blocks remaining', () => {
    const height = 900_000
    const result = calculateHalvingCountdown(height)
    expect(result.blocksRemaining).toBe(NEXT_HALVING_BLOCK - height)
  })

  test('estimated date is in the future for block below target', () => {
    const result = calculateHalvingCountdown(900_000)
    expect(result.estimatedDate.getTime()).toBeGreaterThan(Date.now())
  })

  test('days, hours, minutes are non-negative for block below target', () => {
    const result = calculateHalvingCountdown(900_000)
    expect(result.daysRemaining).toBeGreaterThanOrEqual(0)
    expect(result.hoursRemaining).toBeGreaterThanOrEqual(0)
    expect(result.minutesRemaining).toBeGreaterThanOrEqual(0)
  })

  test('percent complete is between 0 and 100', () => {
    const epochStart = NEXT_HALVING_BLOCK - BLOCKS_PER_HALVING
    // Mid-epoch
    const midHeight = epochStart + BLOCKS_PER_HALVING / 2
    const result = calculateHalvingCountdown(midHeight)
    expect(result.percentComplete).toBeCloseTo(50, 0)
  })

  test('percent complete clamped at boundaries', () => {
    // At epoch start → 0%
    const epochStart = NEXT_HALVING_BLOCK - BLOCKS_PER_HALVING
    const result = calculateHalvingCountdown(epochStart)
    expect(result.percentComplete).toBeCloseTo(0)

    // Beyond target → clamped to 100%
    const result2 = calculateHalvingCountdown(NEXT_HALVING_BLOCK + 100)
    expect(result2.percentComplete).toBe(100)
  })

  test('zero blocks remaining when at target', () => {
    const result = calculateHalvingCountdown(NEXT_HALVING_BLOCK)
    expect(result.blocksRemaining).toBe(0)
  })
})
