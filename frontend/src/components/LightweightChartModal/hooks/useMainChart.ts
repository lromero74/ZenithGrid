import { useEffect, useRef } from 'react'
import { createChart, ColorType, IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import type { Position } from '../../../types'
import type { CandleData } from '../../../utils/indicators/types'
import { calculateHeikinAshi } from '../../../utils/indicators/calculations'
import { addPositionLines } from '../utils/positionLinesRenderer'
import { addMarkers } from '../utils/chartMarkers'

/**
 * Hook for managing the main chart initialization and rendering
 */
export function useMainChart(
  isOpen: boolean,
  chartData: CandleData[],
  chartType: 'candlestick' | 'bar' | 'line' | 'area' | 'baseline',
  useHeikinAshi: boolean,
  position: Position | null | undefined,
  symbol: string
): {
  chartContainerRef: React.RefObject<HTMLDivElement | null>
  chartRef: React.RefObject<IChartApi | null>
  mainSeriesRef: React.RefObject<ISeriesApi<'Candlestick' | 'Bar' | 'Line' | 'Area' | 'Baseline'> | null>
  positionLinesRef: React.RefObject<ISeriesApi<'Line'>[]>
  isCleanedUpRef: React.RefObject<boolean>
} {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const mainSeriesRef = useRef<ISeriesApi<'Candlestick' | 'Bar' | 'Line' | 'Area' | 'Baseline'> | null>(null)
  const positionLinesRef = useRef<ISeriesApi<'Line'>[]>([])
  const isCleanedUpRef = useRef<boolean>(false)

  // Initialize chart
  useEffect(() => {
    if (!isOpen || !chartContainerRef.current || chartData.length === 0) return
    if (chartRef.current) return // Already initialized

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 500,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: '#334155',
        scaleMargins: { top: 0.1, bottom: 0.2 },
        autoScale: true,
        minimumWidth: 100,
      },
    })

    chartRef.current = chart

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chart) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      isCleanedUpRef.current = true
      window.removeEventListener('resize', handleResize)
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
      }
    }
  }, [isOpen, chartData])

  // Render main chart series
  useEffect(() => {
    if (!chartRef.current || isCleanedUpRef.current) return
    if (chartData.length === 0) return

    // Remove existing main series
    if (mainSeriesRef.current) {
      try {
        chartRef.current.removeSeries(mainSeriesRef.current)
      } catch (e) {
        // Series might already be removed
      }
      mainSeriesRef.current = null
    }

    const isBTCPair = symbol.endsWith('-BTC')
    const priceFormat = isBTCPair
      ? { type: 'price' as const, precision: 8, minMove: 0.00000001 }
      : { type: 'price' as const, precision: 2, minMove: 0.01 }

    let data = chartData

    // Apply Heikin-Ashi if enabled
    if (useHeikinAshi) {
      data = calculateHeikinAshi(chartData)
    }

    // Create appropriate series based on chart type
    if (chartType === 'candlestick') {
      const series = chartRef.current.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        priceFormat,
        priceScaleId: 'right',
      })
      series.setData(data)
      mainSeriesRef.current = series as ISeriesApi<'Candlestick' | 'Bar' | 'Line' | 'Area' | 'Baseline'>
    } else if (chartType === 'bar') {
      const series = chartRef.current.addBarSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        priceFormat,
        priceScaleId: 'right',
      })
      series.setData(data)
      mainSeriesRef.current = series as ISeriesApi<'Candlestick' | 'Bar' | 'Line' | 'Area' | 'Baseline'>
    } else if (chartType === 'line') {
      const series = chartRef.current.addLineSeries({
        color: '#2196F3',
        lineWidth: 2,
        priceFormat,
        priceScaleId: 'right',
      })
      series.setData(data.map(d => ({ time: d.time as Time, value: d.close })))
      mainSeriesRef.current = series as ISeriesApi<'Candlestick' | 'Bar' | 'Line' | 'Area' | 'Baseline'>
    } else if (chartType === 'area') {
      const series = chartRef.current.addAreaSeries({
        topColor: 'rgba(33, 150, 243, 0.56)',
        bottomColor: 'rgba(33, 150, 243, 0.04)',
        lineColor: 'rgba(33, 150, 243, 1)',
        lineWidth: 2,
        priceFormat,
        priceScaleId: 'right',
      })
      series.setData(data.map(d => ({ time: d.time as Time, value: d.close })))
      mainSeriesRef.current = series as ISeriesApi<'Candlestick' | 'Bar' | 'Line' | 'Area' | 'Baseline'>
    } else if (chartType === 'baseline') {
      const baseValue = position?.average_buy_price || data[0]?.close || 0
      const series = chartRef.current.addBaselineSeries({
        baseValue: { type: 'price', price: baseValue },
        topLineColor: '#26a69a',
        topFillColor1: 'rgba(38, 166, 154, 0.28)',
        topFillColor2: 'rgba(38, 166, 154, 0.05)',
        bottomLineColor: '#ef5350',
        bottomFillColor1: 'rgba(239, 83, 80, 0.05)',
        bottomFillColor2: 'rgba(239, 83, 80, 0.28)',
        priceFormat,
        priceScaleId: 'right',
      })
      series.setData(data.map(d => ({ time: d.time as Time, value: d.close })))
      mainSeriesRef.current = series as ISeriesApi<'Candlestick' | 'Bar' | 'Line' | 'Area' | 'Baseline'>
    }

    // Ensure right price scale is visible and properly configured
    chartRef.current.priceScale('right').applyOptions({
      borderColor: '#334155',
      visible: true,
    })

    // Add position reference lines if we have position data
    if (position && mainSeriesRef.current && chartRef.current) {
      addPositionLines(chartRef.current, position, chartData, positionLinesRef)
    }

    // Add markers
    if (position && mainSeriesRef.current) {
      addMarkers(mainSeriesRef.current, position, chartData)
    }

    chartRef.current.timeScale().fitContent()
  }, [chartData, chartType, useHeikinAshi, position, symbol])

  return {
    chartContainerRef,
    chartRef,
    mainSeriesRef,
    positionLinesRef,
    isCleanedUpRef,
  }
}
