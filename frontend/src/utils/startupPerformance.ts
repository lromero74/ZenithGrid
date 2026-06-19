const START_MARK = 'zenith:bootstrap'
let reportTimer: ReturnType<typeof setTimeout> | undefined
const reportedMeasures = new Set<string>()

function normalizeRoute(pathname: string): string {
  const route = [
    '/positions', '/bots', '/charts', '/portfolio', '/history', '/settings',
    '/news', '/reports', '/games', '/social', '/chat', '/admin',
  ].find((path) => pathname === path || pathname.startsWith(`${path}/`))
  return route || '/'
}

export function reportStartupPerformance(pathname = window.location.pathname): void {
  const token = localStorage.getItem('auth_access_token')
  if (!token || typeof performance.getEntriesByType !== 'function') return

  const timings: Record<string, number> = {}
  performance.getEntriesByType('measure').forEach((entry) => {
    if (!entry.name.startsWith('zenith:bootstrap-to-') || reportedMeasures.has(entry.name)) return
    timings[entry.name] = Math.round(entry.duration * 10) / 10
    reportedMeasures.add(entry.name)
  })
  if (Object.keys(timings).length === 0) return

  void fetch('/api/performance/client', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ route: normalizeRoute(pathname), timings }),
    keepalive: true,
  }).catch(() => undefined)
}

export function markStartupMilestone(name: string): void {
  if (typeof performance === 'undefined' || typeof performance.mark !== 'function') return
  const markName = `zenith:${name}`
  if (performance.getEntriesByName(markName, 'mark').length > 0) return

  performance.mark(markName)
  if (typeof performance.measure !== 'function') return
  try {
    performance.measure(`zenith:bootstrap-to-${name}`, START_MARK, markName)
  } catch {
    // Tests, embedded browsers, or late module loading may not have the start mark.
  }

  if (import.meta.env.PROD) {
    clearTimeout(reportTimer)
    reportTimer = setTimeout(() => reportStartupPerformance(), 1000)
  }
}
