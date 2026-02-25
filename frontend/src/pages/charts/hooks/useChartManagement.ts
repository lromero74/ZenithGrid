import { useEffect, useRef } from 'react'
import { createChart, ColorType, IChartApi, ISeriesApi, Time, Range } from 'lightweight-charts'
import { getPriceFormat } from '../helpers'

export function useChartManagement(
  chartType: 'candlestick' | 'bar' | 'line' | 'area' | 'baseline',
  selectedPair: string,
  indicatorChartsRef: React.MutableRefObject<Map<string, IChartApi>>
) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const mainSeriesRef = useRef<ISeriesApi<any> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const isSyncingRef = useRef<boolean>(false)
  const syncCallbacksRef = useRef<Map<string, (timeRange: Range<Time> | null) => void>>(new Map())
  const isCleanedUpRef = useRef<boolean>(false)

  // Sync all charts to a given time range (called when any chart is scrolled/zoomed)
  const syncAllChartsToRange = (sourceChartId: string, timeRange: Range<Time> | null) => {
    if (isSyncingRef.current || !timeRange) return

    isSyncingRef.current = true

    try {
      // Sync main chart if it's not the source
      if (sourceChartId !== 'main' && chartRef.current) {
        try {
          chartRef.current.timeScale().setVisibleRange(timeRange)
        } catch (e) {
          // Chart may not have data yet
        }
      }

      // Sync all indicator charts except the source
      indicatorChartsRef.current.forEach((chart, id) => {
        if (id !== sourceChartId) {
          try {
            chart.timeScale().setVisibleRange(timeRange)
          } catch (e) {
            // Chart may not have data yet
          }
        }
      })
    } finally {
      // Use setTimeout to allow the current sync operation to complete
      setTimeout(() => {
        isSyncingRef.current = false
      }, 0)
    }
  }

  // Initialize main chart
  useEffect(() => {
    if (!chartContainerRef.current) return

    isCleanedUpRef.current = false

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1e293b' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#334155' },
        horzLines: { color: '#334155' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 500,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      rightPriceScale: {
        visible: true,
        borderVisible: true,
        borderColor: '#334155',
        autoScale: true,
        scaleMargins: {
          top: 0.1,
          bottom: 0.2,
        },
      },
      leftPriceScale: {
        visible: false,
      },
      crosshair: {
        mode: 1,
      },
    })

    chartRef.current = chart

    // Subscribe main chart to sync all charts when it's scrolled/zoomed
    const mainSyncCallback = (timeRange: Range<Time> | null) => {
      syncAllChartsToRange('main', timeRange)
    }
    chart.timeScale().subscribeVisibleTimeRangeChange(mainSyncCallback)
    syncCallbacksRef.current.set('main', mainSyncCallback)

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'volume',
    })

    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.85,
        bottom: 0,
      },
    })

    // Ensure the right price scale is visible
    chart.priceScale('right').applyOptions({
      scaleMargins: {
        top: 0.1,
        bottom: 0.2,
      },
    })

    volumeSeriesRef.current = volumeSeries

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
        })
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      isCleanedUpRef.current = true
      window.removeEventListener('resize', handleResize)
      // Unsubscribe main chart from time scale changes
      const mainCallback = syncCallbacksRef.current.get('main')
      if (mainCallback && chartRef.current) {
        try {
          chartRef.current.timeScale().unsubscribeVisibleTimeRangeChange(mainCallback)
        } catch (e) {
          // Already unsubscribed
        }
      }
      syncCallbacksRef.current.delete('main')
      if (chartRef.current) {
        chartRef.current.remove()
      }
    }
  }, [])

  // Update chart type when changed
  useEffect(() => {
    if (!chartRef.current || isCleanedUpRef.current) return

    if (mainSeriesRef.current) {
      try {
        chartRef.current.removeSeries(mainSeriesRef.current)
      } catch (e) {
        // Series may have already been removed
      }
      mainSeriesRef.current = null
    }

    const priceFormat = getPriceFormat(selectedPair)

    if (chartType === 'candlestick') {
      mainSeriesRef.current = chartRef.current.addCandlestickSeries({
        upColor: '#10b981',
        downColor: '#ef4444',
        borderUpColor: '#10b981',
        borderDownColor: '#ef4444',
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
        priceScaleId: 'right',
        priceFormat: priceFormat,
      })
    } else if (chartType === 'bar') {
      mainSeriesRef.current = chartRef.current.addBarSeries({
        upColor: '#10b981',
        downColor: '#ef4444',
        openVisible: true,
        thinBars: false,
        priceScaleId: 'right',
        priceFormat: priceFormat,
      })
    } else if (chartType === 'line') {
      mainSeriesRef.current = chartRef.current.addLineSeries({
        color: '#2196F3',
        lineWidth: 2,
        priceScaleId: 'right',
        priceFormat: priceFormat,
      })
    } else if (chartType === 'area') {
      mainSeriesRef.current = chartRef.current.addAreaSeries({
        topColor: '#2196F380',
        bottomColor: '#2196F310',
        lineColor: '#2196F3',
        lineWidth: 2,
        priceScaleId: 'right',
        priceFormat: priceFormat,
      })
    } else if (chartType === 'baseline') {
      mainSeriesRef.current = chartRef.current.addBaselineSeries({
        topLineColor: '#10b981',
        topFillColor1: '#10b98140',
        topFillColor2: '#10b98120',
        bottomLineColor: '#ef4444',
        bottomFillColor1: '#ef444440',
        bottomFillColor2: '#ef444420',
        lineWidth: 2,
        priceScaleId: 'right',
        priceFormat: priceFormat,
      })
    }
  }, [chartType, selectedPair])

  return {
    chartContainerRef,
    chartRef,
    mainSeriesRef,
    volumeSeriesRef,
    isCleanedUpRef,
    syncCallbacksRef,
    syncAllChartsToRange,
  }
}
