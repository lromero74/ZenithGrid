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
 * Format a duration from a start date to now (or to an end date)
 * Shows "Xd Yh Zm" format (e.g., "17d 4h 32m" or "2h 15m")
 */
export function formatDuration(startDate: Date | string | number, endDate?: Date | string | number): string {
  let start: Date
  let end: Date

  if (typeof startDate === 'string') {
    const dateStr = startDate.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(startDate) ? startDate : startDate + 'Z'
    start = new Date(dateStr)
  } else if (typeof startDate === 'number') {
    start = new Date(startDate)
  } else {
    start = startDate
  }

  if (endDate) {
    if (typeof endDate === 'string') {
      const dateStr = endDate.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(endDate) ? endDate : endDate + 'Z'
      end = new Date(dateStr)
    } else if (typeof endDate === 'number') {
      end = new Date(endDate)
    } else {
      end = endDate
    }
  } else {
    end = new Date()
  }

  const diffMs = end.getTime() - start.getTime()
  const diffMinutes = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays > 0) {
    const remainingHours = diffHours % 24
    return `${diffDays}d ${remainingHours}h`
  } else if (diffHours > 0) {
    const remainingMinutes = diffMinutes % 60
    return `${diffHours}h ${remainingMinutes}m`
  } else {
    return `${diffMinutes}m`
  }
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
