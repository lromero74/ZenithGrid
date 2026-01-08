import { useEffect, useRef, useState, MutableRefObject } from 'react'
import { createChart, ColorType, IChartApi, ISeriesApi, Time, LineData, Range } from 'lightweight-charts'
import {
  calculateSMA,
  calculateEMA,
  calculateRSI,
  calculateMACD,
  calculateBollingerBands,
  calculateStochastic,
  AVAILABLE_INDICATORS,
  type CandleData
} from '../../../utils/indicators'
import type { IndicatorConfig } from '../../../components/charts'
import { getPriceFormat } from '../helpers'

interface UseIndicatorsProps {
  chartRef: MutableRefObject<IChartApi | null>
  selectedPair: string
  syncAllChartsToRange: (sourceChartId: string, timeRange: Range<Time> | null, indicatorChartsRef: Map<string, IChartApi>) => void
  syncCallbacksRef: MutableRefObject<Map<string, (timeRange: Range<Time> | null) => void>>
}

export function useIndicators({
  chartRef,
  selectedPair,
  syncAllChartsToRange,
  syncCallbacksRef,
}: UseIndicatorsProps) {
  const [indicators, setIndicators] = useState<IndicatorConfig[]>(() => {
    // Load saved indicators from localStorage
    try {
      const saved = localStorage.getItem('chart-indicators')
      if (saved) {
        return JSON.parse(saved)
      }
    } catch (e) {
      console.error('Failed to load saved indicators:', e)
    }
    return []
  })
  const [showIndicatorModal, setShowIndicatorModal] = useState(false)
  const [indicatorSearch, setIndicatorSearch] = useState('')
  const [editingIndicator, setEditingIndicator] = useState<IndicatorConfig | null>(null)

  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<any>[]>>(new Map())
  const indicatorChartsRef = useRef<Map<string, IChartApi>>(new Map())

  // Save indicators to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('chart-indicators', JSON.stringify(indicators))
    } catch (e) {
      console.error('Failed to save indicators:', e)
    }
  }, [indicators])

  // Add indicator
  const addIndicator = (indicatorType: string) => {
    const template = AVAILABLE_INDICATORS.find(i => i.id === indicatorType)
    if (!template) return

    const newIndicator: IndicatorConfig = {
      id: `${indicatorType}-${Date.now()}`,
      name: template.name,
      type: indicatorType,
      enabled: true,
      settings: { ...template.defaultSettings },
      series: []
    }

    setIndicators(prev => [...prev, newIndicator])
    setShowIndicatorModal(false)
  }

  // Remove indicator
  const removeIndicator = (indicatorId: string) => {
    // Remove series from charts
    const series = indicatorSeriesRef.current.get(indicatorId)
    if (series) {
      series.forEach(s => {
        try {
          // Try to remove from main chart first
          if (chartRef.current) {
            chartRef.current.removeSeries(s)
          }
        } catch (e) {
          // Series may have already been removed or belongs to indicator chart
        }
      })
      indicatorSeriesRef.current.delete(indicatorId)
    }

    // Remove indicator chart if it exists
    const indicatorChart = indicatorChartsRef.current.get(indicatorId)
    if (indicatorChart) {
      try {
        indicatorChart.remove()
      } catch (e) {
        // Chart may have already been removed
      }
      indicatorChartsRef.current.delete(indicatorId)
    }

    setIndicators(prev => prev.filter(i => i.id !== indicatorId))
  }

  // Update indicator settings
  const updateIndicatorSettings = (indicatorId: string, newSettings: Record<string, any>) => {
    setIndicators(prev =>
      prev.map(ind =>
        ind.id === indicatorId ? { ...ind, settings: { ...ind.settings, ...newSettings } } : ind
      )
    )
    setEditingIndicator(null)
  }

  // Render indicators
  const renderIndicators = (candles: CandleData[]) => {
    if (!chartRef.current || !candles.length) {
      console.log('renderIndicators: missing requirements', {
        hasChart: !!chartRef.current,
        candlesLength: candles.length
      })
      return
    }

    console.log('renderIndicators: rendering', indicators.length, 'indicators')

    const priceFormat = getPriceFormat(selectedPair)

    const closes = candles.map(c => c.close)
    const highs = candles.map(c => c.high)
    const lows = candles.map(c => c.low)

    indicators.forEach(indicator => {
      if (!indicator.enabled) return

      console.log('Rendering indicator:', indicator.type, indicator.id)

      // Remove old series for this indicator
      const oldSeries = indicatorSeriesRef.current.get(indicator.id)
      if (oldSeries && oldSeries.length > 0) {
        oldSeries.forEach(series => {
          if (!series) return

          try {
            if (indicator.type === 'rsi' || indicator.type === 'macd' || indicator.type === 'stochastic') {
              // Remove from indicator's specific chart
              const indicatorChart = indicatorChartsRef.current.get(indicator.id)
              if (indicatorChart) {
                indicatorChart.removeSeries(series)
              }
            } else {
              // Remove from main chart
              if (chartRef.current) {
                chartRef.current.removeSeries(series)
              }
            }
          } catch (e) {
            // Series may have already been removed, ignore
          }
        })
        // Clear the old series from the ref
        indicatorSeriesRef.current.delete(indicator.id)
      }

      const newSeries: ISeriesApi<any>[] = []

      if (indicator.type === 'sma') {
        const smaValues = calculateSMA(closes, indicator.settings.period)
        const smaData: LineData<Time>[] = []
        candles.forEach((c, i) => {
          if (smaValues[i] !== null) {
            smaData.push({ time: c.time as Time, value: smaValues[i]! })
          }
        })
        const series = chartRef.current!.addLineSeries({
          color: indicator.settings.color,
          lineWidth: 2,
          title: `SMA(${indicator.settings.period})`,
          priceFormat: priceFormat,
        })
        series.setData(smaData)
        newSeries.push(series)
      }

      if (indicator.type === 'ema') {
        const emaValues = calculateEMA(closes, indicator.settings.period)
        const emaData: LineData<Time>[] = []
        candles.forEach((c, i) => {
          if (emaValues[i] !== null) {
            emaData.push({ time: c.time as Time, value: emaValues[i]! })
          }
        })
        const series = chartRef.current!.addLineSeries({
          color: indicator.settings.color,
          lineWidth: 2,
          title: `EMA(${indicator.settings.period})`,
          priceFormat: priceFormat,
        })
        series.setData(emaData)
        newSeries.push(series)
      }

      if (indicator.type === 'bollinger') {
        const { upper, middle, lower } = calculateBollingerBands(
          closes,
          indicator.settings.period,
          indicator.settings.stdDev
        )

        const upperLineData: LineData<Time>[] = []
        const middleLineData: LineData<Time>[] = []
        const lowerLineData: LineData<Time>[] = []

        candles.forEach((c, i) => {
          if (upper[i] !== null && lower[i] !== null && middle[i] !== null) {
            upperLineData.push({ time: c.time as Time, value: upper[i]! })
            middleLineData.push({ time: c.time as Time, value: middle[i]! })
            lowerLineData.push({ time: c.time as Time, value: lower[i]! })
          }
        })

        const upperLineSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.upperColor,
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: priceFormat,
        })
        const middleLineSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.middleColor,
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: priceFormat,
        })
        const lowerLineSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.lowerColor,
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: priceFormat,
        })

        upperLineSeries.setData(upperLineData)
        middleLineSeries.setData(middleLineData)
        lowerLineSeries.setData(lowerLineData)

        newSeries.push(upperLineSeries, middleLineSeries, lowerLineSeries)
      }

      if (indicator.type === 'rsi') {
        const indicatorChart = indicatorChartsRef.current.get(indicator.id)
        if (!indicatorChart) {
          console.log(`Chart not found for RSI indicator ${indicator.id}`)
          return
        }

        console.log('RSI: Chart found, calculating values...')

        const rsiValues = calculateRSI(closes, indicator.settings.period)
        const rsiData: LineData<Time>[] = []
        candles.forEach((c, i) => {
          if (rsiValues[i] !== null) {
            rsiData.push({ time: c.time as Time, value: rsiValues[i]! })
          }
        })

        console.log('RSI data points:', rsiData.length, 'Sample values:', rsiData.slice(0, 3).map(d => d.value))

        // Add overbought zone shading (70-100)
        const overboughtFillData: any[] = candles.map(c => ({
          time: c.time as Time,
          value: 100,
        }))
        const overboughtFillSeries = indicatorChart.addBaselineSeries({
          baseValue: { type: 'price', price: indicator.settings.overbought },
          topLineColor: 'transparent',
          topFillColor1: '#ef444410',
          topFillColor2: '#ef444408',
          bottomLineColor: 'transparent',
          bottomFillColor1: 'transparent',
          bottomFillColor2: 'transparent',
          lastValueVisible: false,
          priceLineVisible: false,
        })
        overboughtFillSeries.setData(overboughtFillData)

        // Add oversold zone shading (0-30)
        const oversoldFillData: any[] = candles.map(c => ({
          time: c.time as Time,
          value: 0,
        }))
        const oversoldFillSeries = indicatorChart.addBaselineSeries({
          baseValue: { type: 'price', price: indicator.settings.oversold },
          topLineColor: 'transparent',
          topFillColor1: 'transparent',
          topFillColor2: 'transparent',
          bottomLineColor: 'transparent',
          bottomFillColor1: '#10b98108',
          bottomFillColor2: '#10b98110',
          lastValueVisible: false,
          priceLineVisible: false,
        })
        oversoldFillSeries.setData(oversoldFillData)

        const rsiSeries = indicatorChart.addLineSeries({
          color: indicator.settings.color,
          lineWidth: 2,
          title: `RSI(${indicator.settings.period})`,
        })
        rsiSeries.setData(rsiData)

        // Add overbought/oversold reference lines
        const overboughtData: LineData<Time>[] = candles.map(c => ({
          time: c.time as Time,
          value: indicator.settings.overbought
        }))
        const oversoldData: LineData<Time>[] = candles.map(c => ({
          time: c.time as Time,
          value: indicator.settings.oversold
        }))

        const obSeries = indicatorChart.addLineSeries({
          color: '#ef444440',
          lineWidth: 1,
          lineStyle: 2,
          lastValueVisible: false,
          priceLineVisible: false,
        })
        const osSeries = indicatorChart.addLineSeries({
          color: '#10b98140',
          lineWidth: 1,
          lineStyle: 2,
          lastValueVisible: false,
          priceLineVisible: false,
        })

        obSeries.setData(overboughtData)
        osSeries.setData(oversoldData)

        console.log('RSI: All series created and data set')
        newSeries.push(overboughtFillSeries, oversoldFillSeries, rsiSeries, obSeries, osSeries)
      }

      if (indicator.type === 'macd') {
        const indicatorChart = indicatorChartsRef.current.get(indicator.id)
        if (!indicatorChart) {
          console.log(`Chart not found for MACD indicator ${indicator.id}`)
          return
        }

        console.log('MACD: Chart found, calculating values...')

        const { macd, signal, histogram } = calculateMACD(
          closes,
          indicator.settings.fastPeriod,
          indicator.settings.slowPeriod,
          indicator.settings.signalPeriod
        )

        const macdData: LineData<Time>[] = []
        const signalData: LineData<Time>[] = []
        const histogramData: any[] = []

        candles.forEach((c, i) => {
          if (macd[i] !== null) {
            macdData.push({ time: c.time as Time, value: macd[i]! })
          }
          if (signal[i] !== null) {
            signalData.push({ time: c.time as Time, value: signal[i]! })
          }
          if (histogram[i] !== null) {
            histogramData.push({
              time: c.time as Time,
              value: histogram[i]!,
              color: histogram[i]! >= 0 ? '#10b981' : '#ef4444'
            })
          }
        })

        const macdSeries = indicatorChart.addLineSeries({
          color: indicator.settings.macdColor,
          lineWidth: 2,
          title: 'MACD',
        })
        const signalSeries = indicatorChart.addLineSeries({
          color: indicator.settings.signalColor,
          lineWidth: 2,
          title: 'Signal',
        })
        const histSeries = indicatorChart.addHistogramSeries({
          title: 'Histogram',
        })

        macdSeries.setData(macdData)
        signalSeries.setData(signalData)
        histSeries.setData(histogramData)

        console.log('MACD: All series created and data set. MACD points:', macdData.length, 'Signal points:', signalData.length, 'Histogram points:', histogramData.length)
        newSeries.push(macdSeries, signalSeries, histSeries)
      }

      if (indicator.type === 'stochastic') {
        const indicatorChart = indicatorChartsRef.current.get(indicator.id)
        if (!indicatorChart) {
          console.log(`Chart not found for Stochastic indicator ${indicator.id}`)
          return
        }

        const { k, d } = calculateStochastic(
          highs,
          lows,
          closes,
          indicator.settings.kPeriod,
          indicator.settings.dPeriod
        )

        const kData: LineData<Time>[] = []
        const dData: LineData<Time>[] = []

        candles.forEach((c, i) => {
          if (k[i] !== null) {
            kData.push({ time: c.time as Time, value: k[i]! })
          }
          if (d[i] !== null) {
            dData.push({ time: c.time as Time, value: d[i]! })
          }
        })

        const kSeries = indicatorChart.addLineSeries({
          color: indicator.settings.kColor,
          lineWidth: 2,
          title: `%K(${indicator.settings.kPeriod})`,
        })
        const dSeries = indicatorChart.addLineSeries({
          color: indicator.settings.dColor,
          lineWidth: 2,
          title: `%D(${indicator.settings.dPeriod})`,
        })

        kSeries.setData(kData)
        dSeries.setData(dData)

        newSeries.push(kSeries, dSeries)
      }

      // Save series to ref
      if (newSeries.length > 0) {
        indicatorSeriesRef.current.set(indicator.id, newSeries)
        console.log(`Saved ${newSeries.length} series for ${indicator.type} ${indicator.id}`)
      } else {
        console.warn(`No series created for ${indicator.type} ${indicator.id}`)
      }
    })

    console.log('renderIndicators: Complete. Total indicators rendered:', indicators.length)
  }

  // Create and manage charts for oscillator indicators
  useEffect(() => {
    const oscillators = indicators.filter(i => ['rsi', 'macd', 'stochastic'].includes(i.type))

    oscillators.forEach(indicator => {
      // Check if chart already exists
      if (indicatorChartsRef.current.has(indicator.id)) return

      // Get container element
      const container = document.getElementById(`indicator-chart-${indicator.id}`)
      if (!container) {
        console.log(`Container not found for indicator ${indicator.id}`)
        return
      }

      console.log(`Creating chart for ${indicator.type} indicator ${indicator.id}`)

      // Create chart
      const chart = createChart(container, {
        layout: {
          background: { type: ColorType.Solid, color: '#1e293b' },
          textColor: '#94a3b8',
        },
        grid: {
          vertLines: { color: '#334155' },
          horzLines: { color: '#334155' },
        },
        width: container.clientWidth,
        height: 200,
        timeScale: {
          timeVisible: true,
          secondsVisible: false,
          visible: false,
        },
      })

      // Subscribe this indicator chart to sync all charts when it's scrolled/zoomed
      const indicatorSyncCallback = (timeRange: Range<Time> | null) => {
        syncAllChartsToRange(indicator.id, timeRange, indicatorChartsRef.current)
      }
      chart.timeScale().subscribeVisibleTimeRangeChange(indicatorSyncCallback)
      syncCallbacksRef.current.set(indicator.id, indicatorSyncCallback)

      // Handle resize for this indicator chart
      const handleIndicatorResize = () => {
        const currentContainer = document.getElementById(`indicator-chart-${indicator.id}`)
        if (currentContainer) {
          chart.applyOptions({ width: currentContainer.clientWidth })
        }
      }
      window.addEventListener('resize', handleIndicatorResize)
      // Store the resize handler in a data attribute so we can remove it later
      ;(chart as any).__resizeHandler = handleIndicatorResize

      indicatorChartsRef.current.set(indicator.id, chart)
    })

    // Remove charts for indicators that no longer exist
    const existingOscillatorIds = new Set(oscillators.map(i => i.id))
    indicatorChartsRef.current.forEach((chart, id) => {
      if (!existingOscillatorIds.has(id)) {
        console.log(`Removing chart for indicator ${id}`)
        // Unsubscribe from time scale changes
        const callback = syncCallbacksRef.current.get(id)
        if (callback) {
          try {
            chart.timeScale().unsubscribeVisibleTimeRangeChange(callback)
          } catch (e) {
            // Already unsubscribed
          }
          syncCallbacksRef.current.delete(id)
        }
        // Remove resize handler
        const resizeHandler = (chart as any).__resizeHandler
        if (resizeHandler) {
          window.removeEventListener('resize', resizeHandler)
        }
        try {
          chart.remove()
        } catch (e) {
          // Chart may have already been removed
        }
        indicatorChartsRef.current.delete(id)
      }
    })
  }, [indicators, syncAllChartsToRange, syncCallbacksRef])

  // Cleanup indicator charts when component unmounts
  useEffect(() => {
    return () => {
      indicatorChartsRef.current.forEach((chart, id) => {
        // Unsubscribe from time scale changes
        const callback = syncCallbacksRef.current.get(id)
        if (callback) {
          try {
            chart.timeScale().unsubscribeVisibleTimeRangeChange(callback)
          } catch (e) {
            // Already unsubscribed
          }
          syncCallbacksRef.current.delete(id)
        }
        // Remove resize handler
        const resizeHandler = (chart as any).__resizeHandler
        if (resizeHandler) {
          window.removeEventListener('resize', resizeHandler)
        }
        try {
          chart.remove()
        } catch (e) {
          // Chart may have already been removed
        }
      })
      indicatorChartsRef.current.clear()
    }
  }, [syncCallbacksRef])

  return {
    indicators,
    showIndicatorModal,
    setShowIndicatorModal,
    indicatorSearch,
    setIndicatorSearch,
    editingIndicator,
    setEditingIndicator,
    addIndicator,
    removeIndicator,
    updateIndicatorSettings,
    renderIndicators,
  }
}
