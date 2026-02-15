import { useEffect, useState } from 'react'
import { BarChart2, X, Settings, Search, Activity } from 'lucide-react'
import {
  calculateHeikinAshi,
  TIME_INTERVALS,
} from '../utils/indicators'
import { IndicatorSettingsModal } from '../components/charts'
import { useChartsData } from './charts/hooks/useChartsData'
import { useChartManagement } from './charts/hooks/useChartManagement'
import { useIndicators } from './charts/hooks/useIndicators'
import { transformPriceData, transformVolumeData, filterIndicators, groupIndicatorsByCategory } from './charts/helpers'

function Charts() {
  const [selectedPair, setSelectedPair] = useState(() => {
    const saved = localStorage.getItem('chart-selected-pair')
    return saved || 'BTC-USD'
  })
  const [selectedInterval, setSelectedInterval] = useState(() => {
    return localStorage.getItem('chart-selected-interval') || 'FIFTEEN_MINUTE'
  })
  const [chartType, setChartType] = useState<'candlestick' | 'bar' | 'line' | 'area' | 'baseline'>(() => {
    const saved = localStorage.getItem('chart-type')
    return (saved as any) || 'candlestick'
  })
  const [useHeikinAshi, setUseHeikinAshi] = useState(() => {
    return localStorage.getItem('chart-heikin-ashi') === 'true'
  })

  // Save chart settings to localStorage
  useEffect(() => {
    localStorage.setItem('chart-selected-pair', selectedPair)
  }, [selectedPair])

  useEffect(() => {
    localStorage.setItem('chart-selected-interval', selectedInterval)
  }, [selectedInterval])

  useEffect(() => {
    localStorage.setItem('chart-type', chartType)
  }, [chartType])

  useEffect(() => {
    localStorage.setItem('chart-heikin-ashi', useHeikinAshi.toString())
  }, [useHeikinAshi])

  // Initialize chart management hook (creates main chart and manages series)
  const {
    chartContainerRef,
    chartRef,
    mainSeriesRef,
    volumeSeriesRef,
    isCleanedUpRef,
    syncCallbacksRef,
    syncAllChartsToRange,
  } = useChartManagement(chartType, selectedPair, { current: new Map() })

  // Initialize indicators hook (manages all indicator state and rendering)
  const {
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
  } = useIndicators({
    chartRef,
    selectedPair,
    syncCallbacksRef,
    syncAllChartsToRange,
  })

  // Fetch chart data and manage data updates
  const {
    TRADING_PAIRS,
    loading,
    error,
    candleDataRef,
    lastUpdateRef,
  } = useChartsData(selectedPair, selectedInterval, chartType, useHeikinAshi, indicators)

  // Update chart data when candles are fetched
  // Note: 'loading' is included as a dependency to trigger re-run when data fetch completes
  useEffect(() => {
    if (!mainSeriesRef.current || !volumeSeriesRef.current || isCleanedUpRef.current) return
    if (!candleDataRef.current.length) return

    const candles = candleDataRef.current
    const latestCandleKey = candles.length > 0
      ? `${candles[candles.length - 1].time}_${candles[candles.length - 1].close}_${useHeikinAshi}`
      : ''

    if (latestCandleKey !== lastUpdateRef.current) {
      // Apply Heikin-Ashi transformation if enabled
      const displayCandles = useHeikinAshi ? calculateHeikinAshi(candles) : candles

      const priceData = transformPriceData(displayCandles, chartType)
      const volumeData = transformVolumeData(displayCandles)

      if (mainSeriesRef.current && volumeSeriesRef.current && !isCleanedUpRef.current) {
        try {
          mainSeriesRef.current.setData(priceData as any)
          volumeSeriesRef.current.setData(volumeData)

          // Render indicators with the new candle data
          if (indicators.length > 0) {
            renderIndicators(candles)
          }

          if (lastUpdateRef.current === '' && chartRef.current && !isCleanedUpRef.current) {
            chartRef.current.timeScale().fitContent()
          }

          lastUpdateRef.current = latestCandleKey
        } catch (e) {
          // Chart may have been cleaned up
          return
        }
      }
    }
  }, [candleDataRef, mainSeriesRef, volumeSeriesRef, isCleanedUpRef, chartRef, chartType, useHeikinAshi, indicators, renderIndicators, lastUpdateRef, loading])

  // Reset last update when pair or interval changes
  useEffect(() => {
    lastUpdateRef.current = ''
  }, [selectedPair, selectedInterval, lastUpdateRef])

  const filteredIndicators = filterIndicators(indicatorSearch)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Charts</h1>
      </div>

      {/* Toolbar */}
      <div className="bg-slate-800 rounded-lg p-3 flex items-center gap-3 flex-wrap">
        {/* Pair Selector */}
        <select
          value={selectedPair}
          onChange={(e) => setSelectedPair(e.target.value)}
          className="bg-slate-700 text-white px-3 py-2 rounded text-sm font-medium border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <optgroup label="USD Pairs">
            {TRADING_PAIRS.filter((p: { value: string; label: string; group: string; inPortfolio?: boolean }) => p.group === 'USD Pairs').map((pair: { value: string; label: string; group: string; inPortfolio?: boolean }) => (
              <option key={pair.value} value={pair.value}>
                {pair.inPortfolio ? '• ' : ''}{pair.label}
              </option>
            ))}
          </optgroup>
          <optgroup label="BTC Pairs">
            {TRADING_PAIRS.filter((p: { value: string; label: string; group: string; inPortfolio?: boolean }) => p.group === 'BTC Pairs').map((pair: { value: string; label: string; group: string; inPortfolio?: boolean }) => (
              <option key={pair.value} value={pair.value}>
                {pair.inPortfolio ? '• ' : ''}{pair.label}
              </option>
            ))}
          </optgroup>
        </select>

        <div className="w-px h-6 bg-slate-600" />

        {/* Chart Type Buttons */}
        <div className="flex gap-1">
          <button
            onClick={() => setChartType('candlestick')}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              chartType === 'candlestick'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
            title="Candlestick"
          >
            <BarChart2 size={16} />
          </button>
          <button
            onClick={() => setChartType('bar')}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              chartType === 'bar'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
            title="Bar"
          >
            Bar
          </button>
          <button
            onClick={() => setChartType('line')}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              chartType === 'line'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
            title="Line"
          >
            Line
          </button>
          <button
            onClick={() => setChartType('area')}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              chartType === 'area'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
            title="Area"
          >
            Area
          </button>
          <button
            onClick={() => setChartType('baseline')}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              chartType === 'baseline'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
            title="Baseline"
          >
            Baseline
          </button>
        </div>

        <div className="w-px h-6 bg-slate-600" />

        {/* Heikin-Ashi Toggle */}
        <button
          onClick={() => setUseHeikinAshi(!useHeikinAshi)}
          className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
            useHeikinAshi
              ? 'bg-purple-600 text-white'
              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
          }`}
          title="Heikin-Ashi Candles"
        >
          HA
        </button>

        <div className="w-px h-6 bg-slate-600" />

        {/* Indicators Button */}
        <button
          onClick={() => setShowIndicatorModal(true)}
          className="bg-slate-700 text-slate-300 hover:bg-slate-600 px-3 py-1.5 rounded text-sm font-medium transition-colors flex items-center gap-2"
        >
          <Activity size={16} />
          Indicators
        </button>

        <div className="flex-1" />

        {/* Time Interval Buttons */}
        <div className="flex gap-1">
          {TIME_INTERVALS.map((interval) => (
            <button
              key={interval.value}
              onClick={() => setSelectedInterval(interval.value)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                selectedInterval === interval.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {interval.label}
            </button>
          ))}
        </div>
      </div>

      {/* Active Indicators Legend */}
      {indicators.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-3 flex items-center gap-3 flex-wrap">
          {indicators.map((indicator) => (
            <div
              key={indicator.id}
              className="flex items-center gap-2 bg-slate-700 px-3 py-1.5 rounded text-sm"
            >
              <span className="text-white font-medium">{indicator.name}</span>
              <button
                onClick={() => setEditingIndicator(indicator)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <Settings size={14} />
              </button>
              <button
                onClick={() => removeIndicator(indicator.id)}
                className="text-slate-400 hover:text-red-400 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Chart Container */}
      <div className="bg-slate-800 rounded-lg p-4">
        {loading && (
          <div className="text-center py-8">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-500 border-r-transparent"></div>
            <p className="mt-2 text-slate-400">Loading chart data...</p>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500 rounded p-4 text-red-400">
            {error}
          </div>
        )}

        <div ref={chartContainerRef} className={loading || error ? 'hidden' : ''} />
      </div>

      {/* Oscillator Indicator Panels */}
      {indicators.filter(i => ['rsi', 'macd', 'stochastic'].includes(i.type)).map((indicator) => (
        <div key={indicator.id} className="bg-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-300">{indicator.name}</h3>
          </div>
          <div
            id={`indicator-chart-${indicator.id}`}
            style={{ height: '200px' }}
          />
        </div>
      ))}

      {/* Indicator Modal */}
      {showIndicatorModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-white">Add Indicator</h2>
              <button
                onClick={() => setShowIndicatorModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X size={24} />
              </button>
            </div>

            {/* Search */}
            <div className="mb-4 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" size={20} />
              <input
                type="text"
                placeholder="Search indicators..."
                value={indicatorSearch}
                onChange={(e) => setIndicatorSearch(e.target.value)}
                className="w-full bg-slate-700 text-white pl-10 pr-4 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Indicator List */}
            <div className="space-y-2">
              {Object.entries(groupIndicatorsByCategory(filteredIndicators)).map(([category, categoryIndicators]) => (
                <div key={category}>
                  <div className="text-xs font-semibold text-slate-400 mb-2 mt-4 first:mt-0">
                    {category}
                  </div>
                  {categoryIndicators.map((indicator) => (
                    <button
                      key={indicator.id}
                      onClick={() => addIndicator(indicator.id)}
                      className="w-full text-left bg-slate-700 hover:bg-slate-600 text-white px-4 py-3 rounded transition-colors"
                    >
                      {indicator.name}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Indicator Settings Modal */}
      {editingIndicator && (
        <IndicatorSettingsModal
          indicator={editingIndicator}
          onClose={() => setEditingIndicator(null)}
          onUpdateSettings={updateIndicatorSettings}
        />
      )}
    </div>
  )
}

export default Charts
