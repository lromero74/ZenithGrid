/**
 * Lazy loader for the lightweight-charts library (~60KB+ parsed).
 *
 * Charts are not needed for initial page render anywhere in the app, so the
 * library is loaded on demand the first time a chart actually mounts. All
 * consumers share a single in-flight import.
 */

export type ChartLib = typeof import('lightweight-charts')

let libPromise: Promise<ChartLib> | null = null

export function loadChartLib(): Promise<ChartLib> {
  if (!libPromise) {
    libPromise = import('lightweight-charts')
  }
  return libPromise
}
