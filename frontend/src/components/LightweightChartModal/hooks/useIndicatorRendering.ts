import { useEffect, useRef } from 'react'
import { IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import {
  calculateSMA,
  calculateEMA,
  calculateBollingerBands,
} from '../../../utils/indicators/calculations'
import type { CandleData, IndicatorConfig } from '../../../utils/indicators/types'

/**
 * Hook for rendering overlay indicators (SMA, EMA, Bollinger Bands) on the main chart
 * Oscillators (RSI, MACD, Stochastic) are handled separately by useOscillators
 */
export function useIndicatorRendering(
  chartRef: React.RefObject<IChartApi | null>,
  mainSeriesRef: React.RefObject<ISeriesApi<'Candlestick' | 'Bar' | 'Line' | 'Area' | 'Baseline'> | null>,
  indicators: IndicatorConfig[],
  chartData: CandleData[]
): void {
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<'Line'>[]>>(new Map())

  useEffect(() => {
    if (!chartRef.current || chartData.length === 0 || !mainSeriesRef.current) return
    if (indicators.length === 0) return  // Only run if we have indicators to render

    // Clear existing indicator series
    indicatorSeriesRef.current.forEach((seriesList) => {
      seriesList.forEach((series) => {
        try {
          chartRef.current?.removeSeries(series)
        } catch {
          // Series may already be removed
        }
      })
    })
    indicatorSeriesRef.current.clear()

    // Render each indicator
    indicators.forEach((indicator) => {
      const closes = chartData.map(c => c.close)

      if (indicator.type === 'sma') {
        const period = indicator.settings.period || 20
        const smaValues = calculateSMA(closes, period)
        const smaData = chartData
          .map((c, i) => ({ time: c.time as Time, value: smaValues[i] ?? 0 }))
          .filter((_d, i) => smaValues[i] !== null)

        const smaSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.color || '#FF9800',
          lineWidth: 2,
          title: `SMA(${period})`,
          priceScaleId: 'right',
        })
        smaSeries.setData(smaData)
        indicatorSeriesRef.current.set(indicator.id, [smaSeries])

      } else if (indicator.type === 'ema') {
        const period = indicator.settings.period || 12
        const emaValues = calculateEMA(closes, period)
        const emaData = chartData
          .map((c, i) => ({ time: c.time as Time, value: emaValues[i] ?? 0 }))
          .filter((_d, i) => emaValues[i] !== null)

        const emaSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.color || '#9C27B0',
          lineWidth: 2,
          title: `EMA(${period})`,
          priceScaleId: 'right',
        })
        emaSeries.setData(emaData)
        indicatorSeriesRef.current.set(indicator.id, [emaSeries])

      } else if (indicator.type === 'bollinger') {
        const period = indicator.settings.period || 20
        const stdDev = indicator.settings.stdDev || 2
        const bands = calculateBollingerBands(closes, period, stdDev)

        const upperData = chartData
          .map((c, i) => ({ time: c.time as Time, value: bands.upper[i] ?? 0 }))
          .filter((_d, i) => bands.upper[i] !== null)
        const middleData = chartData
          .map((c, i) => ({ time: c.time as Time, value: bands.middle[i] ?? 0 }))
          .filter((_d, i) => bands.middle[i] !== null)
        const lowerData = chartData
          .map((c, i) => ({ time: c.time as Time, value: bands.lower[i] ?? 0 }))
          .filter((_d, i) => bands.lower[i] !== null)

        const upperSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.upperColor || '#2196F3',
          lineWidth: 1,
          title: `BB Upper(${period})`,
          priceScaleId: 'right',
        })
        upperSeries.setData(upperData)

        const middleSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.middleColor || '#FF9800',
          lineWidth: 1,
          title: `BB Middle(${period})`,
          priceScaleId: 'right',
        })
        middleSeries.setData(middleData)

        const lowerSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.lowerColor || '#2196F3',
          lineWidth: 1,
          title: `BB Lower(${period})`,
          priceScaleId: 'right',
        })
        lowerSeries.setData(lowerData)

        indicatorSeriesRef.current.set(indicator.id, [upperSeries, middleSeries, lowerSeries])

      }
      // Oscillators (RSI, MACD, Stochastic) are rendered in separate charts below
    })

    // Ensure right price scale remains visible after adding indicators
    if (chartRef.current) {
      chartRef.current.priceScale('right').applyOptions({
        borderColor: '#334155',
        visible: true,
      })
    }
    // chartRef and mainSeriesRef are stable refs, safe to exclude from deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indicators, chartData])
}
