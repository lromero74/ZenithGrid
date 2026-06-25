/**
 * Pure data-shaping helpers for AccountValueChart.
 *
 * Extracted so the series-building logic (split-vs-total value selection and the
 * appended live "now" point) is unit-testable and has one authoritative
 * definition, independent of the chart's React/lightweight-charts lifecycle.
 */

export interface AccountValueSnapshot {
  date: string
  timestamp: string
  total_value_btc: number
  total_value_usd: number
  usd_portion_usd?: number | null
  btc_portion_btc?: number | null
}

export type ChartMode = 'total' | 'split'

/** A single {time, value} point for a lightweight-charts line series. */
export interface SeriesPoint {
  time: string
  value: number
}

/**
 * Build the BTC and USD line-series data from account-value history.
 *
 * - `total` mode plots `total_value_btc` / `total_value_usd`, and (when live
 *   values are provided and the last snapshot isn't already "today") appends a
 *   live "now" point so the chart reaches the current value.
 * - `split` mode plots the BTC/USD *portions*, dropping snapshots that lack
 *   portion data, and never appends a live point (no live portion breakdown).
 *
 * `today` is injected (the caller passes the current YYYY-MM-DD) so the result
 * is deterministic and testable.
 */
export function buildAccountValueSeries(
  history: AccountValueSnapshot[],
  chartMode: ChartMode,
  liveBtcValue: number | null | undefined,
  liveUsdValue: number | null | undefined,
  today: string,
): { btcData: SeriesPoint[]; usdData: SeriesPoint[] } {
  const isSplit = chartMode === 'split'

  const chartData = isSplit
    ? history.filter(s => s.usd_portion_usd != null && s.btc_portion_btc != null)
    : history

  const btcData: SeriesPoint[] = chartData.map(s => ({
    time: s.date,
    value: isSplit ? (s.btc_portion_btc ?? 0) : s.total_value_btc,
  }))
  const usdData: SeriesPoint[] = chartData.map(s => ({
    time: s.date,
    value: isSplit ? (s.usd_portion_usd ?? 0) : s.total_value_usd,
  }))

  // Append a live "now" point (total mode only — split needs portion data we
  // don't have live), unless the latest snapshot is already today's.
  if (!isSplit && liveBtcValue != null && liveUsdValue != null) {
    const lastDate = chartData.length > 0 ? chartData[chartData.length - 1].date : null
    if (lastDate !== today) {
      btcData.push({ time: today, value: liveBtcValue })
      usdData.push({ time: today, value: liveUsdValue })
    }
  }

  return { btcData, usdData }
}
