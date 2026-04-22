import type { ExpenseItem } from '../../types'

export const FREQUENCY_PILLS = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'biweekly', label: 'Every 2 Wks' },
  { value: 'semi_monthly', label: '2x/Month' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'semi_annual', label: '2x/Year' },
  { value: 'yearly', label: 'Annual' },
  { value: 'every_n_days', label: 'Custom' },
]

export const FREQ_LABELS: Record<string, string> = {
  daily: '/day', weekly: '/week', biweekly: '/2wk',
  semi_monthly: '/2x mo', every_n_days: '/N days',
  monthly: '/mo', quarterly: '/qtr', semi_annual: '/6mo', yearly: '/yr',
}

export const DAY_OF_WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export const MONTH_NAMES = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

export function ordinalDay(d: number): string {
  if (d === -1) return 'last'
  if (d >= 11 && d <= 13) return `${d}th`
  const s = { 1: 'st', 2: 'nd', 3: 'rd' }[d % 10] || 'th'
  return `${d}${s}`
}

export function formatDueBadge(item: ExpenseItem): string | null {
  if (item.due_day == null) return null
  const freq = item.frequency
  if (freq === 'weekly' || freq === 'biweekly') {
    return `Due ${DAY_OF_WEEK[item.due_day] ?? '?'}`
  }
  const dayPart = ordinalDay(item.due_day)
  if ((freq === 'quarterly' || freq === 'semi_annual' || freq === 'yearly') && item.due_month) {
    return `Due ${MONTH_NAMES[item.due_month - 1]} ${dayPart}`
  }
  return `Due ${dayPart}`
}
