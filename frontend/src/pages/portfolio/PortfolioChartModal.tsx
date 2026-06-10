/**
 * Candlestick/volume chart modal for a single portfolio asset.
 *
 * Extracted from Portfolio.tsx and loaded via React.lazy so the
 * lightweight-charts library is only fetched when a chart is opened —
 * the holdings table renders without it.
 */

import { useState, useEffect, useRef } from 'react'
import { BarChart3, X } from 'lucide-react'
import { createChart, ColorType } from 'lightweight-charts'
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import { api } from '../../services/api'
import type { CandleData } from '../../utils/indicators/types'

interface PortfolioChartModalProps {
  asset: string
  onClose: () => void
}

const TIMEFRAMES: Record<string, string> = {
  FIVE_MINUTE: '5m',
  FIFTEEN_MINUTE: '15m',
  THIRTY_MINUTE: '30m',
  ONE_HOUR: '1h',
  ONE_DAY: '1d',
}

function PortfolioChartModal({ asset, onClose }: PortfolioChartModalProps) {
  const [chartPairType, setChartPairType] = useState<'USD' | 'BTC'>('USD')
  const [chartTimeframe, setChartTimeframe] = useState('FIFTEEN_MINUTE')
  const [chartLoading, setChartLoading] = useState(false)
  const [chartError, setChartError] = useState<string | null>(null)

  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const mainSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return

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
      height: 400,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
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
    })

    chartRef.current = chart

    // Determine price format based on pair type
    const isBTCPair = chartPairType === 'BTC'
    const priceFormat = isBTCPair
      ? { type: 'price' as const, precision: 8, minMove: 0.00000001 }
      : { type: 'price' as const, precision: 2, minMove: 0.01 }

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceScaleId: 'right',
      priceFormat: priceFormat,
    })

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

    mainSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    // Resize chart when container resizes
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width })
      }
    })
    resizeObserver.observe(chartContainerRef.current)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      chartRef.current = null
      mainSeriesRef.current = null
      volumeSeriesRef.current = null
    }
  }, [asset, chartPairType])

  // Fetch chart data
  useEffect(() => {
    if (!mainSeriesRef.current || !volumeSeriesRef.current) return

    const fetchChartData = async () => {
      setChartLoading(true)
      setChartError(null)

      try {
        const productId = `${asset}-${chartPairType}`
        const response = await api.get<{ candles: CandleData[] }>(
          '/candles',
          {
            params: {
              product_id: productId,
              granularity: chartTimeframe,
              limit: 200,
            },
          }
        )

        const { candles } = response.data

        if (!candles || candles.length === 0) {
          setChartError(`No data available for ${productId}`)
          return
        }

        const priceData = candles.map((c) => ({
          time: c.time as Time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }))

        const volumeData = candles.map((c) => ({
          time: c.time as Time,
          value: c.volume,
          color: c.close >= c.open ? '#10b98180' : '#ef444480',
        }))

        if (mainSeriesRef.current && volumeSeriesRef.current) {
          mainSeriesRef.current.setData(priceData)
          volumeSeriesRef.current.setData(volumeData)
          if (chartRef.current) {
            chartRef.current.timeScale().fitContent()
          }
        }
      } catch (err: unknown) {
        console.error('Error fetching chart data:', err)
        const e = err as { response?: { data?: { detail?: string } } }
        setChartError(e.response?.data?.detail || 'Failed to load chart data')
      } finally {
        setChartLoading(false)
      }
    }

    fetchChartData()
  }, [asset, chartPairType, chartTimeframe])

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-slate-800 rounded-lg w-full max-w-full sm:max-w-4xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-slate-800 border-b border-slate-700 p-4 flex items-center justify-between z-10">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <BarChart3 size={24} className="text-blue-400" />
              {asset} Chart
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close chart"
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Pair Type Selector */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex gap-1">
              <button
                onClick={() => setChartPairType('USD')}
                className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                  chartPairType === 'USD'
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {asset}/USD
              </button>
              <button
                onClick={() => setChartPairType('BTC')}
                className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                  chartPairType === 'BTC'
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {asset}/BTC
              </button>
            </div>

            <div className="w-px h-6 bg-slate-600" />

            {/* Timeframe Selector */}
            <div className="flex gap-1">
              {Object.entries(TIMEFRAMES).map(([tf, label]) => (
                <button
                  key={tf}
                  onClick={() => setChartTimeframe(tf)}
                  className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                    chartTimeframe === tf
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Chart */}
          <div className="bg-slate-900 rounded-lg p-4">
            {chartLoading && (
              <div className="text-center py-8">
                <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-500 border-r-transparent"></div>
                <p className="mt-2 text-slate-400">Loading chart data...</p>
              </div>
            )}

            {chartError && (
              <div className="bg-red-500/10 border border-red-500 rounded p-4 text-red-400">
                {chartError}
              </div>
            )}

            <div
              ref={chartContainerRef}
              className={chartLoading || chartError ? 'hidden' : ''}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export default PortfolioChartModal
