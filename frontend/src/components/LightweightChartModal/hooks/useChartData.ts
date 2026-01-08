import { useEffect, useState, useRef } from 'react'
import { Time } from 'lightweight-charts'
import axios from 'axios'
import type { CandleData } from '../../../utils/indicators/types'
import { API_BASE_URL } from '../../../config/api'

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
        const response = await axios.get(`${API_BASE_URL}/api/candles`, {
          params: {
            product_id: symbol,
            granularity: timeframe,
            limit: 300,
          },
        })

        const candles = response.data.candles || []
        const formattedCandles = candles
          .map((c: { time?: number | string; start?: string; open: string; high: string; low: string; close: string; volume?: string }) => ({
            // API returns 'time' as Unix timestamp, not 'start' as ISO string
            time: (typeof c.time === 'number' ? c.time : Math.floor(new Date(c.start || c.time).getTime() / 1000)) as Time,
            open: parseFloat(c.open),
            high: parseFloat(c.high),
            low: parseFloat(c.low),
            close: parseFloat(c.close),
            volume: parseFloat(c.volume || 0),
          }))
          .filter((c: CandleData) =>
            !isNaN(c.time as number) &&
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
