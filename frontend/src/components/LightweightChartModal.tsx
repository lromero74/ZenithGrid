import { useEffect, useState } from 'react'
import { X, BarChart2, Search } from 'lucide-react'
import type { Position } from '../types'
import type { IndicatorConfig } from '../utils/indicators/types'
import { AVAILABLE_INDICATORS } from '../utils/indicators/definitions'
import { getFeeAdjustedProfitMultiplier } from './positions/positionUtils'
import { useChartData } from './LightweightChartModal/hooks/useChartData'
import { useMainChart } from './LightweightChartModal/hooks/useMainChart'
import { useIndicatorRendering } from './LightweightChartModal/hooks/useIndicatorRendering'
import { useOscillators } from './LightweightChartModal/hooks/useOscillators'

interface LightweightChartModalProps {
  isOpen: boolean
  onClose: () => void
  symbol: string
  position?: Position | null
}

const TIMEFRAMES = [
  { label: '1m', value: 'ONE_MINUTE' },
  { label: '5m', value: 'FIVE_MINUTE' },
  { label: '15m', value: 'FIFTEEN_MINUTE' },
  { label: '30m', value: 'THIRTY_MINUTE' },
  { label: '1h', value: 'ONE_HOUR' },
  { label: '2h', value: 'TWO_HOUR' },
  { label: '6h', value: 'SIX_HOUR' },
  { label: '1d', value: 'ONE_DAY' },
]

export default function LightweightChartModal({
  isOpen,
  onClose,
  symbol,
  position
}: LightweightChartModalProps) {
  const [timeframe, setTimeframe] = useState('FIFTEEN_MINUTE')
  const [chartType, setChartType] = useState<'candlestick' | 'bar' | 'line' | 'area' | 'baseline'>('candlestick')
  const [useHeikinAshi, setUseHeikinAshi] = useState(false)
  const [indicators, setIndicators] = useState<IndicatorConfig[]>([])
  const [showIndicatorModal, setShowIndicatorModal] = useState(false)
  const [indicatorSearch, setIndicatorSearch] = useState('')

  // Prevent body scroll when modal is open + Escape key to dismiss
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
      const handleKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose()
      }
      document.addEventListener('keydown', handleKey)
      return () => {
        document.body.style.overflow = 'unset'
        document.removeEventListener('keydown', handleKey)
      }
    } else {
      document.body.style.overflow = 'unset'
    }
  }, [isOpen, onClose])

  // Fetch candle data
  const { chartData } = useChartData(isOpen, symbol, timeframe)

  // Initialize and manage main chart
  const { chartContainerRef, chartRef, mainSeriesRef, isCleanedUpRef } = useMainChart(
    isOpen,
    chartData,
    chartType,
    useHeikinAshi,
    position,
    symbol
  )

  // Render overlay indicators (SMA, EMA, Bollinger Bands)
  useIndicatorRendering(chartRef, mainSeriesRef, indicators, chartData)

  // Manage oscillator charts (RSI, MACD, Stochastic)
  const {
    rsiContainerRef,
    macdContainerRef,
    stochasticContainerRef,
    hasRSI,
    hasMACD,
    hasStochastic,
  } = useOscillators(chartRef, indicators, chartData, isCleanedUpRef)

  // Filter indicators by search
  const filteredIndicators = AVAILABLE_INDICATORS.filter(ind =>
    ind.name.toLowerCase().includes(indicatorSearch.toLowerCase()) ||
    ind.description.toLowerCase().includes(indicatorSearch.toLowerCase())
  )

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/80 z-[60] flex items-center justify-center p-2 sm:p-4" onClick={onClose}>
      <div className="bg-slate-900 rounded-lg w-full h-full max-w-[95vw] max-h-[95vh] flex flex-col pb-16 sm:pb-0" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between p-2 sm:p-4 border-b border-slate-700 gap-2">
          <div className="flex items-center gap-2 sm:gap-4 flex-wrap min-w-0">
            <h2 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
              <BarChart2 size={20} />
              Chart
            </h2>
            <div className="text-sm text-slate-400 truncate">{symbol}</div>

            {position && (() => {
              const profitTargetPercent = position.strategy_config_snapshot?.min_profit_percentage
                || position.strategy_config_snapshot?.take_profit_percentage
                || position.bot_config?.min_profit_percentage
                || position.bot_config?.take_profit_percentage
                || 2.0
              // Apply fee adjustment to profit target
              const targetPrice = position.average_buy_price * getFeeAdjustedProfitMultiplier(profitTargetPercent)

              return (
                <div className="flex items-center gap-3 text-xs">
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-0.5 bg-orange-500"></div>
                    <span className="text-slate-400">Entry:</span>
                    <span className="text-orange-400 font-semibold">{position.average_buy_price?.toFixed(8)}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-0.5 bg-green-500"></div>
                    <span className="text-slate-400">Target (+{profitTargetPercent}%):</span>
                    <span className="text-green-400 font-semibold">{targetPrice?.toFixed(8)}</span>
                  </div>
                  {position.bot_config?.safety_order_step_percentage && (
                    <div className="flex items-center gap-1.5">
                      <div className="w-3 h-0.5 bg-blue-500"></div>
                      <span className="text-slate-400">Next SO:</span>
                      <span className="text-blue-400 font-semibold">
                        {(position.average_buy_price * (1 - position.bot_config.safety_order_step_percentage / 100))?.toFixed(8)}
                      </span>
                    </div>
                  )}
                </div>
              )
            })()}
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors p-2"
          >
            <X size={24} />
          </button>
        </div>

        {/* Chart Controls */}
        <div className="flex items-center gap-3 p-3 border-b border-slate-700 flex-wrap">
          {/* Timeframe Selector */}
          <div className="flex gap-1">
            {TIMEFRAMES.map(tf => (
              <button
                key={tf.value}
                onClick={() => setTimeframe(tf.value)}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  timeframe === tf.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>

          <div className="w-px h-6 bg-slate-600" />

          {/* Chart Type Selector */}
          <div className="flex gap-1">
            {['candlestick', 'bar', 'line', 'area', 'baseline'].map(type => (
              <button
                key={type}
                onClick={() => setChartType(type as 'candlestick' | 'bar' | 'line' | 'area' | 'baseline')}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors capitalize ${
                  chartType === type
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {type === 'candlestick' ? <BarChart2 size={14} /> : type}
              </button>
            ))}
          </div>

          <div className="w-px h-6 bg-slate-600" />

          {/* Heikin-Ashi Toggle */}
          <button
            onClick={() => setUseHeikinAshi(!useHeikinAshi)}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              useHeikinAshi
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            Heikin-Ashi
          </button>

          {/* Indicators Button */}
          <button
            onClick={() => setShowIndicatorModal(true)}
            className="px-2 py-1 rounded text-xs font-medium transition-colors bg-slate-700 text-slate-300 hover:bg-slate-600"
          >
            Indicators ({indicators.length})
          </button>
        </div>

        {/* Chart Containers */}
        <div className="flex-1 relative p-4 overflow-hidden flex flex-col gap-2">
          {/* Main Price Chart */}
          <div ref={chartContainerRef} className="w-full flex-1 min-h-[300px]" />

          {/* MACD Oscillator */}
          {hasMACD && (
            <div className="w-full h-[120px] border-t border-slate-700">
              <div ref={macdContainerRef} className="w-full h-full" />
            </div>
          )}

          {/* RSI Oscillator */}
          {hasRSI && (
            <div className="w-full h-[120px] border-t border-slate-700">
              <div ref={rsiContainerRef} className="w-full h-full" />
            </div>
          )}

          {/* Stochastic Oscillator */}
          {hasStochastic && (
            <div className="w-full h-[120px] border-t border-slate-700">
              <div ref={stochasticContainerRef} className="w-full h-full" />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-700 text-xs text-slate-500">
          <p>
            Full-featured chart with position markers and reference lines. Add indicators, change timeframes, and analyze your trades.
          </p>
        </div>
      </div>

      {/* Indicator Modal */}
      {showIndicatorModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[70]">
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

            <div className="space-y-2">
              {Object.entries(
                filteredIndicators.reduce((acc, ind) => {
                  if (!acc[ind.category]) acc[ind.category] = []
                  acc[ind.category].push(ind)
                  return acc
                }, {} as Record<string, typeof AVAILABLE_INDICATORS>)
              ).map(([category, categoryIndicators]) => (
                <div key={category}>
                  <div className="text-xs font-semibold text-slate-400 mb-2 mt-4 first:mt-0">
                    {category}
                  </div>
                  {categoryIndicators.map((ind) => {
                    const alreadyAdded = indicators.some(i => i.type === ind.id)
                    return (
                      <button
                        key={ind.id}
                        onClick={() => {
                          if (alreadyAdded) {
                            // Remove indicator
                            setIndicators(indicators.filter(i => i.type !== ind.id))
                          } else {
                            // Add indicator with default settings
                            const newIndicator: IndicatorConfig = {
                              id: `${ind.id}-${Date.now()}`,
                              type: ind.id,
                              settings: ind.defaultSettings
                            }
                            setIndicators([...indicators, newIndicator])
                          }
                          setShowIndicatorModal(false)
                        }}
                        className={`w-full text-left p-3 rounded transition-colors mb-2 ${
                          alreadyAdded
                            ? 'bg-blue-600 hover:bg-blue-700'
                            : 'bg-slate-700 hover:bg-slate-600'
                        }`}
                      >
                        <div className="font-semibold text-white flex items-center justify-between">
                          {ind.name}
                          {alreadyAdded && <span className="text-xs">Added</span>}
                        </div>
                        <div className="text-xs text-slate-400">{ind.description}</div>
                      </button>
                    )
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
