export function parseDevice(ua: string | null): string {
  if (!ua) return 'Unknown device'
  const browser = ua.match(/(Chrome|Firefox|Safari|Edge|Opera)/)?.[1] ?? 'Browser'
  const os = ua.match(/(Windows|Mac OS|iPhone|iPad|Android|Linux)/)?.[1] ?? ''
  return `${browser}${os ? ' on ' + os : ''}`
}

export function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Unknown'
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}
