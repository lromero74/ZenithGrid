import { useEffect, useState, useRef } from 'react'
import { Time } from 'lightweight-charts'
import { api } from '../../../services/api'
import type { CandleData } from '../../../utils/indicators/types'

/**
 * Hook for fetching and managing candle data from the API
 */
export function useChartData(
  isOpen: boolean,
  symbol: string,
  timeframe: string
): {
  chartData: CandleData[]
  candleDataRef: React.MutableRefObject<CandleData[]>
} {
  const [chartData, setChartData] = useState<CandleData[]>([])
  const candleDataRef = useRef<CandleData[]>([])

  useEffect(() => {
    if (!isOpen || !symbol) return

    const fetchCandles = async () => {
      try {
        const response = await api.get('/candles', {
          params: {
            product_id: symbol,
            granularity: timeframe,
            limit: 300,
          },
        })

        const candles = response.data.candles || []
        const formattedCandles = candles
          .map((c: { time?: number | string; start?: string; open: string; high: string; low: string; close: string; volume?: string }) => {
            // Convert to Unix timestamp (seconds)
            let timestamp: number
            if (typeof c.time === 'number') {
              timestamp = c.time
            } else if (c.start) {
              timestamp = Math.floor(new Date(c.start).getTime() / 1000)
            } else if (c.time) {
              timestamp = Math.floor(new Date(c.time).getTime() / 1000)
            } else {
              timestamp = 0  // Fallback, will be filtered out
            }

            return {
              time: timestamp as Time,
              open: parseFloat(c.open),
              high: parseFloat(c.high),
              low: parseFloat(c.low),
              close: parseFloat(c.close),
              volume: parseFloat(c.volume || '0'),
            }
          })
          .filter((c: CandleData) =>
            (c.time as number) > 0 &&
            !isNaN(c.open) &&
            !isNaN(c.high) &&
            !isNaN(c.low) &&
            !isNaN(c.close)
          )
          .sort((a: CandleData, b: CandleData) => (a.time as number) - (b.time as number))

        candleDataRef.current = formattedCandles
        setChartData(formattedCandles)
      } catch (error) {
        console.error('Error fetching candles:', error)
      }
    }

    fetchCandles()
  }, [isOpen, symbol, timeframe])

  return {
    chartData,
    candleDataRef,
  }
}
