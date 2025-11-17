import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

interface TradingViewChartModalProps {
  isOpen: boolean
  onClose: () => void
  symbol: string  // e.g., "LTC-BTC"
  position?: any
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
  position
}: TradingViewChartModalProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const widgetRef = useRef<any>(null)

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

      // Convert our symbol format (LTC-BTC) to TradingView format (COINBASE:LTCBTC)
      const [base, quote] = symbol.split('-')
      const tvSymbol = `COINBASE:${base}${quote}`

      // Get saved chart settings from localStorage
      const savedSettings = localStorage.getItem(`chart_settings_${symbol}`)
      const settings = savedSettings ? JSON.parse(savedSettings) : {
        interval: 'D',  // Default to daily chart
        studies: ['BB@tv-basicstudies', 'RSI@tv-basicstudies', 'MACD@tv-basicstudies'],
        theme: 'dark'
      }

      widgetRef.current = new window.TradingView.widget({
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
        // Add position reference lines if we have a position
        ...(position && {
          studies_overrides: {
            'volume.volume.color.0': '#ef5350',
            'volume.volume.color.1': '#26a69a'
          }
        })
      })
    }

    return () => {
      if (widgetRef.current) {
        try {
          if (typeof widgetRef.current.remove === 'function') {
            widgetRef.current.remove()
          }
        } catch (error) {
          // Silently ignore cleanup errors
          console.log('TradingView widget cleanup skipped')
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
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-white">TV Chart</h2>
            <div className="text-sm text-slate-400">
              {symbol}
              {position && (
                <span className="ml-2 text-xs">
                  • Position: {position.total_base_acquired?.toFixed(6)} @ {position.average_buy_price?.toFixed(8)}
                </span>
              )}
            </div>
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
