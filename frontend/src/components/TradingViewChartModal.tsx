import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { SELL_FEE_RATE } from './positions/positionUtils'

// Helper to calculate fee-adjusted profit target multiplier
const getFeeAdjustedProfitMultiplier = (desiredNetProfitPercent: number): number => {
  const netMultiplier = 1 + (desiredNetProfitPercent / 100)
  return netMultiplier / (1 - SELL_FEE_RATE)
}

// Get take profit percentage from position config
const getTakeProfitPercent = (position: any): number => {
  return position?.strategy_config_snapshot?.take_profit_percentage
    ?? position?.strategy_config_snapshot?.min_profit_percentage
    ?? position?.bot_config?.take_profit_percentage
    ?? position?.bot_config?.min_profit_percentage
    ?? 2.0 // Default 2% if not configured
}

// TradingView exchange prefix mapping
const TV_EXCHANGE_PREFIX: Record<string, string> = {
  coinbase: 'COINBASE',
  bybit: 'BYBIT',
  mt5_bridge: 'OANDA',  // Reasonable default for MT5/forex
}

interface TradingViewChartModalProps {
  isOpen: boolean
  onClose: () => void
  symbol: string  // e.g., "LTC-BTC"
  position?: any
  exchange?: string  // e.g., "coinbase", "bybit"
}

declare global {
  interface Window {
    TradingView: any
  }
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

  useEffect(() => {
    // Prevent body scroll when modal is open
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = 'unset'
    }

    return () => {
      document.body.style.overflow = 'unset'
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen || !containerRef.current) return

    // Load TradingView widget script if not already loaded
    if (!window.TradingView) {
      const script = document.createElement('script')
      script.src = 'https://s3.tradingview.com/tv.js'
      script.async = true
      script.onload = () => initWidget()
      document.head.appendChild(script)
    } else {
      initWidget()
    }

    function initWidget() {
      if (!containerRef.current) return

      // Convert our symbol format (LTC-BTC) to TradingView format (EXCHANGE:LTCBTC)
      const [base, quote] = symbol.split('-')
      const tvPrefix = TV_EXCHANGE_PREFIX[exchange || 'coinbase'] || 'COINBASE'
      // ByBit uses USDT pairs on TradingView (our system maps USDT→USD internally)
      const tvQuote = (exchange === 'bybit' && quote === 'USD') ? 'USDT' : quote
      const tvSymbol = `${tvPrefix}:${base}${tvQuote}`

      // Get saved chart settings from localStorage
      const savedSettings = localStorage.getItem(`chart_settings_${symbol}`)
      const settings = savedSettings ? JSON.parse(savedSettings) : {
        interval: 'D',  // Default to daily chart
        studies: ['BB@tv-basicstudies', 'RSI@tv-basicstudies', 'MACD@tv-basicstudies'],
        theme: 'dark'
      }

      const widget = new window.TradingView.widget({
        container_id: containerRef.current.id,
        autosize: true,
        symbol: tvSymbol,
        interval: settings.interval || 'D',
        timezone: 'Etc/UTC',
        theme: 'dark',
        style: '1',
        locale: 'en',
        toolbar_bg: '#1e293b',
        enable_publishing: false,
        hide_side_toolbar: false,
        allow_symbol_change: true,
        save_image: true,
        studies: settings.studies || [
          'BB@tv-basicstudies',
          'RSI@tv-basicstudies',
          'MACD@tv-basicstudies'
        ],
        show_popup_button: true,
        popup_width: '1000',
        popup_height: '650',
        studies_overrides: {
          'volume.volume.color.0': '#ef5350',
          'volume.volume.color.1': '#26a69a'
        }
      })

      widgetRef.current = widget
    }

    return () => {
      if (widgetRef.current) {
        try {
          if (typeof widgetRef.current.remove === 'function') {
            widgetRef.current.remove()
          }
        } catch (error) {
          // Silently ignore cleanup errors
          // TradingView widget cleanup skipped
        }
        widgetRef.current = null
      }
    }
  }, [isOpen, symbol, position])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 rounded-lg w-full h-full max-w-[95vw] max-h-[95vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center gap-4">
            <h2 className="text-xl font-bold text-white">TV Chart</h2>
            <div className="text-sm text-slate-400">{symbol}</div>

            {position && (
              <div className="flex items-center gap-3 text-xs">
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 bg-orange-500"></div>
                  <span className="text-slate-400">Avg. Buy Price:</span>
                  <span className="text-orange-400 font-semibold">{position.average_buy_price?.toFixed(8)}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 bg-green-500"></div>
                  <span className="text-slate-400">Target (+{getTakeProfitPercent(position)}%):</span>
                  <span className="text-green-400 font-semibold">{(position.average_buy_price * getFeeAdjustedProfitMultiplier(getTakeProfitPercent(position)))?.toFixed(8)}</span>
                </div>
                {position.bot_config?.safety_order_step_percentage && (
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-0.5 bg-blue-500"></div>
                    <span className="text-slate-400">Next SO (-{position.bot_config.safety_order_step_percentage}%):</span>
                    <span className="text-blue-400 font-semibold">
                      {(position.average_buy_price * (1 - position.bot_config.safety_order_step_percentage / 100))?.toFixed(8)}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors p-2"
          >
            <X size={24} />
          </button>
        </div>

        {/* TradingView Chart Container */}
        <div className="flex-1 relative">
          <div
            id="tradingview_chart"
            ref={containerRef}
            className="absolute inset-0"
          />
        </div>

        {/* Footer with tips */}
        <div className="p-3 border-t border-slate-700 text-xs text-slate-500">
          <p>
            💡 Your chart settings (timeframe, indicators, drawings) are automatically saved for this pair
          </p>
        </div>
      </div>
    </div>
  )
}
