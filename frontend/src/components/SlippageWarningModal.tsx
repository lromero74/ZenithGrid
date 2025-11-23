import { X } from 'lucide-react'

interface SlippageWarningModalProps {
  positionId: number
  productId: string
  slippageData: {
    best_bid: number
    mark_price: number
    expected_profit_at_mark: number
    actual_profit_at_bid: number
    slippage_amount: number
    slippage_percentage: number
  }
  quoteCurrency: string
  onClose: () => void
  onProceedWithMarket: () => void
  onSwitchToLimit: () => void
}

export function SlippageWarningModal({
  positionId,
  productId,
  slippageData,
  quoteCurrency,
  onClose,
  onProceedWithMarket,
  onSwitchToLimit
}: SlippageWarningModalProps) {
  const getPrecision = () => {
    if (quoteCurrency === 'USD') return 2
    if (quoteCurrency === 'BTC') return 8
    return 8
  }

  const formatPrice = (price: number) => {
    const precision = getPrecision()
    return price.toFixed(precision)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-lg w-full max-w-lg">
        {/* Header */}
        <div className="p-6 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-xl font-bold text-white">
            ⚠️ High Slippage Warning
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          {/* Warning Message */}
          <div className="bg-yellow-500/10 border border-yellow-500 rounded p-4">
            <p className="text-yellow-400 font-semibold mb-2">
              Market order may result in significant slippage
            </p>
            <p className="text-yellow-400/80 text-sm">
              Closing at market price would consume <strong>{slippageData.slippage_percentage.toFixed(1)}%</strong> of your expected profit due to unfavorable bid/ask spread.
            </p>
          </div>

          {/* Profit Comparison */}
          <div className="bg-slate-900 rounded-lg p-4 space-y-3">
            <div className="flex justify-between">
              <span className="text-slate-400 text-sm">Expected profit at mark price:</span>
              <span className="text-green-400 font-mono font-semibold">
                {formatPrice(slippageData.expected_profit_at_mark)} {quoteCurrency}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400 text-sm">Actual profit at market (bid):</span>
              <span className="text-yellow-400 font-mono font-semibold">
                {formatPrice(slippageData.actual_profit_at_bid)} {quoteCurrency}
              </span>
            </div>
            <div className="border-t border-slate-700 pt-3 flex justify-between">
              <span className="text-slate-400 text-sm">Slippage cost:</span>
              <span className="text-red-400 font-mono font-semibold">
                -{formatPrice(slippageData.slippage_amount)} {quoteCurrency}
              </span>
            </div>
          </div>

          {/* Price Details */}
          <div className="bg-slate-900 rounded-lg p-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-slate-400">Best Bid (market sell):</span>
              <span className="text-red-400 font-mono">{formatPrice(slippageData.best_bid)} {quoteCurrency}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-slate-400">Mark Price (mid):</span>
              <span className="text-blue-400 font-mono">{formatPrice(slippageData.mark_price)} {quoteCurrency}</span>
            </div>
          </div>

          {/* Recommendation */}
          <div className="bg-blue-500/10 border border-blue-500 rounded p-4">
            <p className="text-blue-400 text-sm">
              <strong>Recommendation:</strong> Use a limit order at or near the mark price ({formatPrice(slippageData.mark_price)} {quoteCurrency}) to minimize slippage and capture more profit.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-700 flex flex-col gap-3">
          <button
            onClick={onSwitchToLimit}
            className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold transition-colors"
          >
            Use Limit Order (Recommended)
          </button>
          <button
            onClick={onProceedWithMarket}
            className="w-full px-4 py-2 bg-yellow-600 hover:bg-yellow-700 rounded-lg font-semibold transition-colors"
          >
            Proceed with Market Order Anyway
          </button>
          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
