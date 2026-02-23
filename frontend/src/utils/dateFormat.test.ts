import {
  formatDateTime,
  formatDate,
  formatTime,
  formatDuration,
  formatDateTimeCompact,
} from './dateFormat'

// ── formatDateTime ───────────────────────────────────────────────────

describe('formatDateTime', () => {
  test('Date object produces formatted string', () => {
    const d = new Date('2025-11-16T15:45:30Z')
    const result = formatDateTime(d)
    // Should contain date and time components
    expect(result).toMatch(/11\/16\/2025/)
    expect(result).toMatch(/\d{2}:\d{2}:\d{2}/)
  })

  test('ISO string with Z suffix', () => {
    const result = formatDateTime('2025-06-01T12:00:00Z')
    expect(result).toMatch(/06\/01\/2025/)
  })

  test('string without Z suffix gets Z appended (treated as UTC)', () => {
    const result = formatDateTime('2025-06-01T12:00:00')
    // Should parse the same as with Z
    expect(result).toMatch(/06\/01\/2025/)
  })

  test('string with timezone offset', () => {
    const result = formatDateTime('2025-06-01T12:00:00+05:00')
    expect(result).toMatch(/2025/)
  })

  test('Unix timestamp (number)', () => {
    const ts = new Date('2025-03-15T10:30:00Z').getTime()
    const result = formatDateTime(ts)
    expect(result).toMatch(/03\/15\/2025/)
  })

  test('includes timezone abbreviation', () => {
    const result = formatDateTime(new Date())
    // Should end with a timezone like EST, CST, UTC, etc.
    expect(result).toMatch(/[A-Z]{2,5}$/)
  })
})

// ── formatDate ───────────────────────────────────────────────────────

describe('formatDate', () => {
  test('Date object', () => {
    const result = formatDate(new Date('2025-12-25T00:00:00Z'))
    expect(result).toMatch(/12\/25\/2025/)
  })

  test('ISO string', () => {
    const result = formatDate('2025-01-01T00:00:00Z')
    expect(result).toMatch(/01\/01\/2025/)
  })

  test('number timestamp', () => {
    const ts = new Date('2025-07-04T00:00:00Z').getTime()
    const result = formatDate(ts)
    expect(result).toMatch(/2025/)
  })

  test('includes timezone abbreviation', () => {
    const result = formatDate(new Date())
    expect(result).toMatch(/[A-Z]{2,5}$/)
  })
})

// ── formatTime ───────────────────────────────────────────────────────

describe('formatTime', () => {
  test('Date object includes hours, minutes, seconds', () => {
    const result = formatTime(new Date('2025-01-01T14:30:45Z'))
    expect(result).toMatch(/\d{2}:\d{2}:\d{2}/)
  })

  test('string input', () => {
    const result = formatTime('2025-01-01T00:00:00Z')
    expect(result).toMatch(/\d{2}:\d{2}:\d{2}/)
  })

  test('includes timezone abbreviation', () => {
    const result = formatTime(new Date())
    expect(result).toMatch(/[A-Z]{2,5}$/)
  })
})

// ── formatDuration ───────────────────────────────────────────────────

describe('formatDuration', () => {
  test('days and hours format', () => {
    const start = new Date('2025-01-01T00:00:00Z')
    const end = new Date('2025-01-03T05:30:00Z') // 2 days, 5 hours, 30 min
    const result = formatDuration(start, end)
    expect(result).toBe('2d 5h')
  })

  test('hours and minutes format (less than 1 day)', () => {
    const start = new Date('2025-01-01T00:00:00Z')
    const end = new Date('2025-01-01T03:45:00Z')
    const result = formatDuration(start, end)
    expect(result).toBe('3h 45m')
  })

  test('minutes only (less than 1 hour)', () => {
    const start = new Date('2025-01-01T00:00:00Z')
    const end = new Date('2025-01-01T00:25:00Z')
    const result = formatDuration(start, end)
    expect(result).toBe('25m')
  })

  test('zero duration', () => {
    const d = new Date('2025-01-01T00:00:00Z')
    const result = formatDuration(d, d)
    expect(result).toBe('0m')
  })

  test('string inputs without Z suffix', () => {
    const result = formatDuration('2025-01-01T00:00:00', '2025-01-02T12:00:00')
    expect(result).toBe('1d 12h')
  })

  test('string inputs with timezone offset', () => {
    const result = formatDuration('2025-01-01T00:00:00+00:00', '2025-01-01T02:00:00+00:00')
    expect(result).toBe('2h 0m')
  })

  test('number (timestamp) inputs', () => {
    const start = new Date('2025-01-01T00:00:00Z').getTime()
    const end = new Date('2025-01-01T05:15:00Z').getTime()
    const result = formatDuration(start, end)
    expect(result).toBe('5h 15m')
  })

  test('without end date uses current time', () => {
    // Using a start date slightly in the past ensures non-zero duration
    const start = new Date(Date.now() - 120_000) // 2 minutes ago
    const result = formatDuration(start)
    expect(result).toBe('2m')
  })
})

// ── formatDateTimeCompact ────────────────────────────────────────────

describe('formatDateTimeCompact', () => {
  test('uses 2-digit year', () => {
    const result = formatDateTimeCompact(new Date('2025-11-16T15:45:30Z'))
    expect(result).toMatch(/11\/16\/25/)
  })

  test('Date object', () => {
    const result = formatDateTimeCompact(new Date('2025-06-01T12:00:00Z'))
    expect(result).toMatch(/06\/01\/25/)
  })

  test('ISO string without Z suffix', () => {
    const result = formatDateTimeCompact('2025-06-01T12:00:00')
    expect(result).toMatch(/06\/01\/25/)
  })

  test('number timestamp', () => {
    const ts = new Date('2025-03-15T10:30:00Z').getTime()
    const result = formatDateTimeCompact(ts)
    expect(result).toMatch(/03\/15\/25/)
  })

  test('includes timezone', () => {
    const result = formatDateTimeCompact(new Date())
    expect(result).toMatch(/[A-Z]{2,5}$/)
  })
})
