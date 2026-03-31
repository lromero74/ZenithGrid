import { useEffect, useRef, useState, useCallback } from 'react'
import { X, ChevronDown } from 'lucide-react'
import { SELL_FEE_RATE, calculateSOLevels } from './positions/positionUtils'

const getFeeAdjustedProfitMultiplier = (desiredNetProfitPercent: number): number => {
  const netMultiplier = 1 + (desiredNetProfitPercent / 100)
  return netMultiplier / (1 - SELL_FEE_RATE)
}

const getTakeProfitPercent = (position: any): number => {
  return position?.strategy_config_snapshot?.take_profit_percentage
    ?? position?.strategy_config_snapshot?.min_profit_percentage
    ?? position?.bot_config?.take_profit_percentage
    ?? position?.bot_config?.min_profit_percentage
    ?? 2.0
}

const TV_EXCHANGE_PREFIX: Record<string, string> = {
  coinbase: 'COINBASE',
  bybit: 'BYBIT',
  mt5_bridge: 'OANDA',
}

const TV_INTERVALS = [
  { label: '1m',  value: '1' },
  { label: '3m',  value: '3' },
  { label: '5m',  value: '5' },
  { label: '15m', value: '15' },
  { label: '30m', value: '30' },
  { label: '1h',  value: '60' },
  { label: '2h',  value: '120' },
  { label: '4h',  value: '240' },
  { label: '1D',  value: 'D' },
  { label: '1W',  value: 'W' },
  { label: '1M',  value: '1M' },
]

const TV_STYLES = [
  { label: 'Candles',        value: '1' },
  { label: 'Hollow Candles', value: '9' },
  { label: 'Heikin-Ashi',    value: '8' },
  { label: 'Bars',           value: '0' },
  { label: 'Line',           value: '2' },
  { label: 'Area',           value: '3' },
  { label: 'Baseline',       value: '10' },
  { label: 'HLC Area',       value: '12' },
  { label: 'Renko',          value: '4' },
  { label: 'Line Break',     value: '5' },
  { label: 'Kagi',           value: '6' },
  { label: 'P&F',            value: '7' },
]

const TV_STUDIES = [
  { id: 'BB@tv-basicstudies',           label: 'Bollinger Bands',  category: 'Trend' },
  { id: 'MASimple@tv-basicstudies',     label: 'MA (SMA)',         category: 'Trend' },
  { id: 'MAExp@tv-basicstudies',        label: 'EMA',              category: 'Trend' },
  { id: 'IchimokuCloud@tv-basicstudies',label: 'Ichimoku Cloud',   category: 'Trend' },
  { id: 'PSAR@tv-basicstudies',         label: 'Parabolic SAR',    category: 'Trend' },
  { id: 'ADX@tv-basicstudies',          label: 'ADX',              category: 'Trend' },
  { id: 'Aroon@tv-basicstudies',        label: 'Aroon',            category: 'Trend' },
  { id: 'RSI@tv-basicstudies',          label: 'RSI',              category: 'Momentum' },
  { id: 'MACD@tv-basicstudies',         label: 'MACD',             category: 'Momentum' },
  { id: 'Stochastic@tv-basicstudies',   label: 'Stochastic',       category: 'Momentum' },
  { id: 'CCI@tv-basicstudies',          label: 'CCI',              category: 'Momentum' },
  { id: 'WilliamR@tv-basicstudies',     label: 'Williams %R',      category: 'Momentum' },
  { id: 'Momentum@tv-basicstudies',     label: 'Momentum',         category: 'Momentum' },
  { id: 'MFI@tv-basicstudies',          label: 'MFI',              category: 'Momentum' },
  { id: 'Volume@tv-basicstudies',       label: 'Volume',           category: 'Volume' },
  { id: 'OBV@tv-basicstudies',          label: 'OBV',              category: 'Volume' },
  { id: 'VWAP@tv-basicstudies',         label: 'VWAP',             category: 'Volume' },
  { id: 'CMF@tv-basicstudies',          label: 'CMF',              category: 'Volume' },
]

const CATEGORIES = ['Trend', 'Momentum', 'Volume'] as const

function loadLS<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key)
    if (v === null) return fallback
    return JSON.parse(v) as T
  } catch { return fallback }
}

function saveLS(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch {}
}

interface TradingViewChartModalProps {
  isOpen: boolean
  onClose: () => void
  symbol: string
  position?: any
  exchange?: string
}

declare global {
  interface Window { TradingView: any }
}

export default function TradingViewChartModal({
  isOpen,
  onClose,
  symbol,
  position,
  exchange,
}: TradingViewChartModalProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const widgetRef = useRef<any>(null)
  const [isWidgetLoading, setIsWidgetLoading] = useState(false)

  // Persisted chart settings
  const [interval, setIntervalState]   = useState<string>(() => loadLS('tv-interval', '15'))
  const [style, setStyleState]         = useState<string>(() => loadLS('tv-style', '1'))
  const [studies, setStudiesState]     = useState<string[]>(() => loadLS('tv-studies', []))

  // Indicator panel state
  const [indicatorOpen, setIndicatorOpen] = useState(false)
  const [pendingStudies, setPendingStudies] = useState<string[]>(studies)
  const indicatorPanelRef = useRef<HTMLDivElement>(null)

  // Setters that also persist
  const setInterval = useCallback((v: string) => { setIntervalState(v); saveLS('tv-interval', v) }, [])
  const setStyle    = useCallback((v: string) => { setStyleState(v);    saveLS('tv-style', v)    }, [])
  const applyStudies = useCallback((s: string[]) => { setStudiesState(s); saveLS('tv-studies', s) }, [])

  // Escape + body scroll
  useEffect(() => {
    if (!isOpen) { document.body.style.overflow = 'unset'; return }
    document.body.style.overflow = 'hidden'
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    return () => { document.body.style.overflow = 'unset'; document.removeEventListener('keydown', handleKey) }
  }, [isOpen, onClose])

  // Close indicator panel on outside click
  useEffect(() => {
    if (!indicatorOpen) return
    const handle = (e: MouseEvent) => {
      if (indicatorPanelRef.current && !indicatorPanelRef.current.contains(e.target as Node)) {
        applyStudies(pendingStudies)
        setIndicatorOpen(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [indicatorOpen, pendingStudies, applyStudies])

  // Build/rebuild widget
  useEffect(() => {
    if (!isOpen || !containerRef.current) return

    setIsWidgetLoading(true)

    const doInit = () => {
      if (!containerRef.current) return

      const [base, quote] = symbol.split('-')
      const tvPrefix = TV_EXCHANGE_PREFIX[exchange || 'coinbase'] || 'COINBASE'
      const tvQuote  = (exchange === 'bybit' && quote === 'USD') ? 'USDT' : quote
      const tvSymbol = `${tvPrefix}:${base}${tvQuote}`

      const widget = new window.TradingView.widget({
        container_id:      containerRef.current.id,
        autosize:          true,
        symbol:            tvSymbol,
        interval,
        timezone:          'Etc/UTC',
        theme:             'dark',
        style,
        locale:            'en',
        toolbar_bg:        '#1e293b',
        enable_publishing: false,
        hide_top_toolbar:  true,   // We own the controls
        hide_side_toolbar: false,  // Keep drawing tools
        allow_symbol_change: true,
        save_image:        true,
        studies,
        studies_overrides: {
          'volume.volume.color.0': '#ef5350',
          'volume.volume.color.1': '#26a69a',
        },
      })

      widgetRef.current = widget
      try {
        widget.onChartReady(() => setIsWidgetLoading(false))
      } catch {
        setTimeout(() => setIsWidgetLoading(false), 3000)
      }
    }

    if (!window.TradingView) {
      const script = document.createElement('script')
      script.src = 'https://s3.tradingview.com/tv.js'
      script.async = true
      script.onload = doInit
      document.head.appendChild(script)
    } else {
      doInit()
    }

    return () => {
      if (widgetRef.current) {
        try { if (typeof widgetRef.current.remove === 'function') widgetRef.current.remove() } catch {}
        widgetRef.current = null
      }
    }
  }, [isOpen, symbol, position, interval, style, studies])

  const toggleStudy = (id: string) => {
    setPendingStudies(prev =>
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
    )
  }

  const currentStyleLabel = TV_STYLES.find(s => s.value === style)?.label ?? 'Candles'
  const activeStudiesCount = studies.length

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/80 z-[60] flex items-center justify-center p-2 sm:p-4" onClick={onClose}>
      <div className="bg-slate-900 rounded-lg w-full h-full max-w-[95vw] max-h-[95vh] flex flex-col pb-16 sm:pb-0" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-center justify-between p-2 sm:p-4 border-b border-slate-700 gap-2">
          <div className="flex items-center gap-2 sm:gap-4 flex-wrap min-w-0">
            <h2 className="text-lg sm:text-xl font-bold text-white">TV Chart</h2>
            <div className="text-sm text-slate-400 truncate">{symbol}</div>

            {position && (
              <div className="flex items-center gap-3 text-xs">
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 bg-orange-500" />
                  <span className="text-slate-400">Avg. Buy:</span>
                  <span className="text-orange-400 font-semibold">{position.average_buy_price?.toFixed(8)}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 bg-green-500" />
                  <span className="text-slate-400">Target (+{getTakeProfitPercent(position)}%):</span>
                  <span className="text-green-400 font-semibold">
                    {(position.average_buy_price * getFeeAdjustedProfitMultiplier(getTakeProfitPercent(position)))?.toFixed(8)}
                  </span>
                </div>
                {(() => {
                  const nextSO = calculateSOLevels(position)[0]
                  return nextSO ? (
                    <div className="flex items-center gap-1.5">
                      <div className="w-3 h-0.5 bg-blue-500" />
                      <span className="text-slate-400">Next SO{nextSO.soNumber}:</span>
                      <span className="text-blue-400 font-semibold">{nextSO.triggerPrice.toFixed(8)}</span>
                    </div>
                  ) : null
                })()}
              </div>
            )}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors p-2">
            <X size={24} />
          </button>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700 flex-wrap">

          {/* Intervals */}
          <div className="flex gap-1 flex-wrap">
            {TV_INTERVALS.map(tf => (
              <button
                key={tf.value}
                onClick={() => setInterval(tf.value)}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  interval === tf.value ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>

          <div className="w-px h-5 bg-slate-600 shrink-0" />

          {/* Chart type dropdown */}
          <div className="relative">
            <select
              value={style}
              onChange={e => setStyle(e.target.value)}
              className="appearance-none bg-slate-700 text-slate-200 text-xs px-3 py-1.5 pr-7 rounded border border-slate-600 cursor-pointer hover:bg-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
              title="Chart type"
            >
              {TV_STYLES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
            <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          </div>

          <div className="w-px h-5 bg-slate-600 shrink-0" />

          {/* Indicators panel */}
          <div className="relative" ref={indicatorPanelRef}>
            <button
              onClick={() => {
                if (!indicatorOpen) setPendingStudies(studies)
                else { applyStudies(pendingStudies) }
                setIndicatorOpen(o => !o)
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors border ${
                activeStudiesCount > 0
                  ? 'bg-blue-600/20 border-blue-500/40 text-blue-300 hover:bg-blue-600/30'
                  : 'bg-slate-700 border-slate-600 text-slate-300 hover:bg-slate-600'
              }`}
            >
              Indicators{activeStudiesCount > 0 ? ` (${activeStudiesCount})` : ''}
              <ChevronDown size={12} className={`transition-transform ${indicatorOpen ? 'rotate-180' : ''}`} />
            </button>

            {indicatorOpen && (
              <div className="absolute left-0 top-full mt-1 z-50 bg-slate-800 border border-slate-600 rounded-lg shadow-xl shadow-black/50 p-3 w-72 max-h-80 overflow-y-auto">
                {CATEGORIES.map(cat => (
                  <div key={cat} className="mb-3 last:mb-0">
                    <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">{cat}</div>
                    <div className="flex flex-wrap gap-1.5">
                      {TV_STUDIES.filter(s => s.category === cat).map(s => {
                        const active = pendingStudies.includes(s.id)
                        return (
                          <button
                            key={s.id}
                            onClick={() => toggleStudy(s.id)}
                            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                              active
                                ? 'bg-blue-600 text-white'
                                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                            }`}
                          >
                            {s.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
                <div className="mt-3 pt-2 border-t border-slate-700 flex justify-between items-center">
                  <button
                    onClick={() => setPendingStudies([])}
                    className="text-xs text-slate-400 hover:text-slate-200 transition-colors"
                  >
                    Clear all
                  </button>
                  <button
                    onClick={() => { applyStudies(pendingStudies); setIndicatorOpen(false) }}
                    className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded font-medium transition-colors"
                  >
                    Apply
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="ml-auto text-[10px] text-slate-500 hidden sm:block">
            {currentStyleLabel} · {TV_INTERVALS.find(t => t.value === interval)?.label}
            {activeStudiesCount > 0 && ` · ${activeStudiesCount} indicator${activeStudiesCount > 1 ? 's' : ''}`}
          </div>
        </div>

        {/* TradingView Chart Container */}
        <div className="flex-1 relative">
          <div id="tradingview_chart" ref={containerRef} className="absolute inset-0" />
          {isWidgetLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-10">
              <div className="flex flex-col items-center space-y-3">
                <svg className="animate-spin h-8 w-8 text-blue-400" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span className="text-sm text-slate-400">Loading chart...</span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-700 text-xs text-slate-500">
          Interval, chart type, and indicators are saved and restored across all pairs. Drawing tools are available in the chart's side toolbar.
        </div>
      </div>
    </div>
  )
}
