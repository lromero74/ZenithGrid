import { ISeriesApi } from 'lightweight-charts'
import type { Position } from '../../../types'
import type { CandleData } from '../../../utils/indicators/types'

/**
 * Adds entry and current price markers to the chart
 */
export function addMarkers(
  mainSeries: ISeriesApi<'Candlestick' | 'Bar' | 'Line' | 'Area' | 'Baseline'>,
  position: Position | null | undefined,
  chartData: CandleData[]
): void {
  if (!position || chartData.length === 0) return

  const markers: any[] = []

  // Entry marker
  if (position.opened_at) {
    const openedTime = Math.floor(new Date(position.opened_at).getTime() / 1000)
    const nearestCandle = chartData.reduce((prev, curr) =>
      Math.abs((curr.time as number) - openedTime) < Math.abs((prev.time as number) - openedTime) ? curr : prev
    )

    if (nearestCandle) {
      markers.push({
        time: nearestCandle.time,
        position: 'belowBar' as const,
        color: '#10b981',
        shape: 'arrowUp' as const,
        text: 'Entry',
      })
    }
  }

  // Current price marker
  const lastCandle = chartData[chartData.length - 1]
  if (lastCandle) {
    markers.push({
      time: lastCandle.time,
      position: 'inBar' as const,
      color: '#3b82f6',
      shape: 'circle' as const,
      text: 'Now',
    })
  }

  mainSeries.setMarkers(markers)
}
