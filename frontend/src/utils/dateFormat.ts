/**
 * Format a date/timestamp to include timezone information
 * Shows both date, time, and timezone (e.g., "11/16/2025, 3:45:30 PM EST")
 */
export function formatDateTime(date: Date | string | number): string {
  let d: Date

  if (typeof date === 'string') {
    // If string doesn't end with 'Z' or timezone offset, assume it's UTC and append 'Z'
    const dateStr = date.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(date) ? date : date + 'Z'
    d = new Date(dateStr)
  } else if (typeof date === 'number') {
    d = new Date(date)
  } else {
    d = date
  }

  return d.toLocaleString('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short' // Shows "EST", "PST", etc.
  })
}

/**
 * Format a date to show only date with timezone
 * (e.g., "11/16/2025 EST")
 */
export function formatDate(date: Date | string | number): string {
  const d = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date

  return d.toLocaleString('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZoneName: 'short'
  })
}

/**
 * Format a date to show only time with timezone
 * (e.g., "3:45:30 PM EST")
 */
export function formatTime(date: Date | string | number): string {
  const d = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date

  return d.toLocaleString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short'
  })
}

/**
 * Format a date for compact display (shorter timezone)
 * (e.g., "11/16/25 3:45 PM EST")
 */
export function formatDateTimeCompact(date: Date | string | number): string {
  let d: Date

  if (typeof date === 'string') {
    // If string doesn't end with 'Z' or timezone offset, assume it's UTC and append 'Z'
    const dateStr = date.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(date) ? date : date + 'Z'
    d = new Date(dateStr)
  } else if (typeof date === 'number') {
    d = new Date(date)
  } else {
    d = date
  }

  return d.toLocaleString('en-US', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short'
  })
}
