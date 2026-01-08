import { useEffect, useRef, useMemo } from 'react'
import { IChartApi, Time, LineStyle } from 'lightweight-charts'
import {
  calculateRSI,
  calculateMACD,
  calculateStochastic,
} from '../../../utils/indicators/calculations'
import type { CandleData, IndicatorConfig } from '../../../utils/indicators/types'
import { createOscillatorChart } from '../utils/oscillatorChartFactory'

/**
 * Unified hook for managing RSI, MACD, and Stochastic oscillator charts
 * - Handles chart lifecycle (creation, cleanup)
 * - Time scale synchronization with main chart
 * - Indicator data rendering
 */
export function useOscillators(
  mainChartRef: React.RefObject<IChartApi | null>,
  indicators: IndicatorConfig[],
  chartData: CandleData[],
  isCleanedUpRef: React.MutableRefObject<boolean>
) {
  // Container refs for oscillator charts
  const rsiContainerRef = useRef<HTMLDivElement>(null)
  const macdContainerRef = useRef<HTMLDivElement>(null)
  const stochasticContainerRef = useRef<HTMLDivElement>(null)

  // Chart instance refs
  const rsiChartRef = useRef<IChartApi | null>(null)
  const macdChartRef = useRef<IChartApi | null>(null)
  const stochasticChartRef = useRef<IChartApi | null>(null)

  // Check which indicators are enabled
  const hasRSI = useMemo(() => indicators.some(ind => ind.type === 'rsi'), [indicators])
  const hasMACD = useMemo(() => indicators.some(ind => ind.type === 'macd'), [indicators])
  const hasStochastic = useMemo(() => indicators.some(ind => ind.type === 'stochastic'), [indicators])

  // RSI Oscillator Chart
  useEffect(() => {
    const rsiIndicator = indicators.find(ind => ind.type === 'rsi')
    if (!rsiIndicator || !rsiContainerRef.current || chartData.length === 0) {
      // Clean up if RSI was removed
      if (rsiChartRef.current) {
        rsiChartRef.current.remove()
        rsiChartRef.current = null
      }
      return
    }

    // Create RSI chart if it doesn't exist
    if (!rsiChartRef.current) {
      const { chartInstance, syncTimeScale } = createOscillatorChart(
        rsiContainerRef,
        mainChartRef,
        isCleanedUpRef
      )
      if (chartInstance) {
        rsiChartRef.current = chartInstance
        syncTimeScale()
      }
    }

    if (!rsiChartRef.current) return

    // Add RSI series
    const period = rsiIndicator.settings.period || 14
    const closes = chartData.map(c => c.close)
    const rsiValues = calculateRSI(closes, period)
    const rsiData = chartData
      .map((c, i) => ({ time: c.time as Time, value: rsiValues[i] ?? 0 }))
      .filter((_d, i) => rsiValues[i] !== null)

    const rsiSeries = rsiChartRef.current.addLineSeries({
      color: rsiIndicator.settings.color || '#2196F3',
      lineWidth: 2,
      title: `RSI(${period})`,
    })
    rsiSeries.setData(rsiData)

    // Add overbought/oversold lines
    const overbought = rsiIndicator.settings.overbought || 70
    const oversold = rsiIndicator.settings.oversold || 30

    const overboughtSeries = rsiChartRef.current.addLineSeries({
      color: 'rgba(239, 83, 80, 0.5)',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
      priceLineVisible: false,
    })
    overboughtSeries.setData(chartData.map(c => ({ time: c.time as Time, value: overbought })))

    const oversoldSeries = rsiChartRef.current.addLineSeries({
      color: 'rgba(38, 166, 154, 0.5)',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
      priceLineVisible: false,
    })
    oversoldSeries.setData(chartData.map(c => ({ time: c.time as Time, value: oversold })))

    rsiChartRef.current.timeScale().fitContent()

    // Cleanup
    return () => {
      if (rsiChartRef.current) {
        rsiChartRef.current.removeSeries(rsiSeries)
        rsiChartRef.current.removeSeries(overboughtSeries)
        rsiChartRef.current.removeSeries(oversoldSeries)
      }
    }
  }, [indicators, chartData, mainChartRef, isCleanedUpRef])

  // MACD Oscillator Chart
  useEffect(() => {
    const macdIndicator = indicators.find(ind => ind.type === 'macd')
    if (!macdIndicator || !macdContainerRef.current || chartData.length === 0) {
      // Clean up if MACD was removed
      if (macdChartRef.current) {
        macdChartRef.current.remove()
        macdChartRef.current = null
      }
      return
    }

    // Create MACD chart if it doesn't exist
    if (!macdChartRef.current) {
      const { chartInstance, syncTimeScale } = createOscillatorChart(
        macdContainerRef,
        mainChartRef,
        isCleanedUpRef
      )
      if (chartInstance) {
        macdChartRef.current = chartInstance
        syncTimeScale()
      }
    }

    if (!macdChartRef.current) return

    // Add MACD series
    const fastPeriod = macdIndicator.settings.fastPeriod || 12
    const slowPeriod = macdIndicator.settings.slowPeriod || 26
    const signalPeriod = macdIndicator.settings.signalPeriod || 9
    const closes = chartData.map(c => c.close)
    const macdResult = calculateMACD(closes, fastPeriod, slowPeriod, signalPeriod)

    const macdData = chartData
      .map((c, i) => ({ time: c.time as Time, value: macdResult.macd[i] ?? 0 }))
      .filter((_d, i) => macdResult.macd[i] !== null)
    const signalData = chartData
      .map((c, i) => ({ time: c.time as Time, value: macdResult.signal[i] ?? 0 }))
      .filter((_d, i) => macdResult.signal[i] !== null)
    const histogramData = chartData
      .map((c, i) => ({ time: c.time as Time, value: macdResult.histogram[i] ?? 0 }))
      .filter((_d, i) => macdResult.histogram[i] !== null)

    const macdSeries = macdChartRef.current.addLineSeries({
      color: macdIndicator.settings.macdColor || '#2196F3',
      lineWidth: 2,
      title: 'MACD',
    })
    macdSeries.setData(macdData)

    const signalSeries = macdChartRef.current.addLineSeries({
      color: macdIndicator.settings.signalColor || '#FF5722',
      lineWidth: 2,
      title: 'Signal',
    })
    signalSeries.setData(signalData)

    const histogramSeries = macdChartRef.current.addLineSeries({
      color: macdIndicator.settings.histogramColor || '#4CAF50',
      lineWidth: 2,
      title: 'Histogram',
    })
    histogramSeries.setData(histogramData)

    macdChartRef.current.timeScale().fitContent()

    // Cleanup
    return () => {
      if (macdChartRef.current) {
        macdChartRef.current.removeSeries(macdSeries)
        macdChartRef.current.removeSeries(signalSeries)
        macdChartRef.current.removeSeries(histogramSeries)
      }
    }
  }, [indicators, chartData, mainChartRef, isCleanedUpRef])

  // Stochastic Oscillator Chart
  useEffect(() => {
    const stochasticIndicator = indicators.find(ind => ind.type === 'stochastic')
    if (!stochasticIndicator || !stochasticContainerRef.current || chartData.length === 0) {
      // Clean up if Stochastic was removed
      if (stochasticChartRef.current) {
        stochasticChartRef.current.remove()
        stochasticChartRef.current = null
      }
      return
    }

    // Create Stochastic chart if it doesn't exist
    if (!stochasticChartRef.current) {
      const { chartInstance, syncTimeScale } = createOscillatorChart(
        stochasticContainerRef,
        mainChartRef,
        isCleanedUpRef
      )
      if (chartInstance) {
        stochasticChartRef.current = chartInstance
        syncTimeScale()
      }
    }

    if (!stochasticChartRef.current) return

    // Add Stochastic series
    const kPeriod = stochasticIndicator.settings.kPeriod || 14
    const dPeriod = stochasticIndicator.settings.dPeriod || 3
    const highs = chartData.map(c => c.high)
    const lows = chartData.map(c => c.low)
    const closes = chartData.map(c => c.close)
    const stochasticResult = calculateStochastic(highs, lows, closes, kPeriod, dPeriod)

    const kData = chartData
      .map((c, i) => ({ time: c.time as Time, value: stochasticResult.k[i] ?? 0 }))
      .filter((_d, i) => stochasticResult.k[i] !== null)
    const dData = chartData
      .map((c, i) => ({ time: c.time as Time, value: stochasticResult.d[i] ?? 0 }))
      .filter((_d, i) => stochasticResult.d[i] !== null)

    const kSeries = stochasticChartRef.current.addLineSeries({
      color: stochasticIndicator.settings.kColor || '#2196F3',
      lineWidth: 2,
      title: '%K',
    })
    kSeries.setData(kData)

    const dSeries = stochasticChartRef.current.addLineSeries({
      color: stochasticIndicator.settings.dColor || '#FF5722',
      lineWidth: 2,
      title: '%D',
    })
    dSeries.setData(dData)

    // Add 80/20 reference lines
    const overboughtSeries = stochasticChartRef.current.addLineSeries({
      color: 'rgba(239, 83, 80, 0.5)',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
      priceLineVisible: false,
    })
    overboughtSeries.setData(chartData.map(c => ({ time: c.time as Time, value: 80 })))

    const oversoldSeries = stochasticChartRef.current.addLineSeries({
      color: 'rgba(38, 166, 154, 0.5)',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
      priceLineVisible: false,
    })
    oversoldSeries.setData(chartData.map(c => ({ time: c.time as Time, value: 20 })))

    stochasticChartRef.current.timeScale().fitContent()

    // Cleanup
    return () => {
      if (stochasticChartRef.current) {
        stochasticChartRef.current.removeSeries(kSeries)
        stochasticChartRef.current.removeSeries(dSeries)
        stochasticChartRef.current.removeSeries(overboughtSeries)
        stochasticChartRef.current.removeSeries(oversoldSeries)
      }
    }
  }, [indicators, chartData, mainChartRef, isCleanedUpRef])

  return {
    rsiContainerRef,
    macdContainerRef,
    stochasticContainerRef,
    hasRSI,
    hasMACD,
    hasStochastic,
  }
}
