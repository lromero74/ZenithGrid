const START_MARK = 'zenith:bootstrap'

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
}
