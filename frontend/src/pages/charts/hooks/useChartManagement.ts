import { useEffect, useRef, useState } from 'react'
import type { IChartApi, ISeriesApi, Time, Range } from 'lightweight-charts'
import { loadChartLib } from '../../../utils/chartLib'
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
  // Flips true once the (lazily imported) library has loaded and the chart
  // exists — downstream effects must depend on this, not on the refs.
  const [chartReady, setChartReady] = useState(false)

  // Sync all charts to a given time range (called when any chart is scrolled/zoomed)
  const syncAllChartsToRange = (sourceChartId: string, timeRange: Range<Time> | null) => {
    if (isSyncingRef.current || !timeRange) return

    isSyncingRef.current = true

    try {
      // Sync main chart if it's not the source
      if (sourceChartId !== 'main' && chartRef.current) {
        try {
          chartRef.current.timeScale().setVisibleRange(timeRange)
        } catch {
          // Chart may not have data yet
        }
      }

      // Sync all indicator charts except the source
      indicatorChartsRef.current.forEach((chart, id) => {
        if (id !== sourceChartId) {
          try {
            chart.timeScale().setVisibleRange(timeRange)
          } catch {
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

  // Initialize main chart (lightweight-charts is imported lazily)
  useEffect(() => {
    if (!chartContainerRef.current) return

    isCleanedUpRef.current = false
    let disposed = false
    let resizeObserver: ResizeObserver | null = null

    loadChartLib().then(({ createChart, ColorType }) => {
      if (disposed || !chartContainerRef.current) return

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
          rightOffset: 5,
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

      // Track the container's actual size with a ResizeObserver instead of only
      // the window 'resize' event. The chart is created lazily/asynchronously and
      // may be created while its container is hidden (the page applies a `hidden`
      // class during load/error → display:none → clientWidth 0). A window resize
      // never fires when the container later un-hides, so a width-0 chart would
      // stay invisible forever. The observer fires on the 0→N size change (and on
      // sidebar toggles, layout changes, etc.), keeping the chart correctly sized.
      resizeObserver = new ResizeObserver((entries) => {
        const width = Math.floor(entries[0]?.contentRect.width ?? 0)
        if (width > 0 && chartRef.current && !isCleanedUpRef.current) {
          chartRef.current.applyOptions({ width })
        }
      })
      resizeObserver.observe(chartContainerRef.current)

      setChartReady(true)
    })

    return () => {
      disposed = true
      isCleanedUpRef.current = true
      setChartReady(false)
      if (resizeObserver) {
        resizeObserver.disconnect()
        resizeObserver = null
      }
      // Unsubscribe main chart from time scale changes
      const mainCallback = syncCallbacksRef.current.get('main')
      if (mainCallback && chartRef.current) {
        try {
          chartRef.current.timeScale().unsubscribeVisibleTimeRangeChange(mainCallback)
        } catch {
          // Already unsubscribed
        }
      }
      syncCallbacksRef.current.delete('main')
      if (chartRef.current) {
        chartRef.current.remove()
      }
    }
  }, [])

  // Update chart type when changed (waits for the async chart creation)
  useEffect(() => {
    if (!chartReady || !chartRef.current || isCleanedUpRef.current) return

    if (mainSeriesRef.current) {
      try {
        chartRef.current.removeSeries(mainSeriesRef.current)
      } catch {
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
  }, [chartType, selectedPair, chartReady])

  return {
    chartReady,
    chartContainerRef,
    chartRef,
    mainSeriesRef,
    volumeSeriesRef,
    isCleanedUpRef,
    syncCallbacksRef,
    syncAllChartsToRange,
  }
}
