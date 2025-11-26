import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import axios from 'axios'
import { API_BASE_URL } from '../config/api'

interface LimitCloseModalProps {
  positionId: number
  productId: string
  totalAmount: number
  quoteCurrency: string
  isEditing?: boolean  // Whether we're editing an existing order
  currentLimitPrice?: number  // Current limit price if editing
  onClose: () => void
  onSuccess: () => void
}

interface TickerData {
  best_bid: number
  best_ask: number
  mark_price: number
  last_price: number
}

interface ProductPrecision {
  quote_increment: string
  quote_decimals: number
  base_increment: string
}

export function LimitCloseModal({
  positionId,
  productId,
  totalAmount,
  quoteCurrency,
  isEditing = false,
  currentLimitPrice,
  onClose,
  onSuccess
}: LimitCloseModalProps) {
  const [ticker, setTicker] = useState<TickerData | null>(null)
  const [productPrecision, setProductPrecision] = useState<ProductPrecision | null>(null)
  const [limitPrice, setLimitPrice] = useState<number>(currentLimitPrice || 0)
  const [sliderValue, setSliderValue] = useState<number>(50) // 0-100 range
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch product precision data
  useEffect(() => {
    const fetchPrecision = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/api/market-data/product-precision/${productId}`)
        setProductPrecision(response.data)
      } catch (err: any) {
        console.error('Failed to fetch product precision:', err)
        // Use defaults if fetch fails
        setProductPrecision({
          quote_increment: quoteCurrency === 'USD' ? '0.01' : '0.00000001',
          quote_decimals: quoteCurrency === 'USD' ? 2 : 8,
          base_increment: '0.00000001'
        })
      }
    }
    fetchPrecision()
  }, [productId, quoteCurrency])

  // Fetch ticker data
  useEffect(() => {
    const fetchTicker = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/api/positions/${positionId}/ticker`)
        const data = response.data
        setTicker(data)
        // Default to mark price if not editing, otherwise keep current limit price
        if (!isEditing) {
          setLimitPrice(data.mark_price)
        }
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to fetch ticker data')
      }
    }

    fetchTicker()
    // Refresh ticker every 5 seconds
    const interval = setInterval(fetchTicker, 5000)
    return () => clearInterval(interval)
  }, [positionId])

  // Helper function to round price to correct increment
  const roundToIncrement = (price: number): number => {
    if (!productPrecision) return price

    const increment = parseFloat(productPrecision.quote_increment)
    // Round to nearest increment (not floor, to avoid always rounding down)
    const rounded = Math.round(price / increment) * increment

    // Return with proper decimal precision
    const decimals = productPrecision.quote_decimals
    return parseFloat(rounded.toFixed(decimals))
  }

  // Update limit price when slider changes
  useEffect(() => {
    if (!ticker || !productPrecision) return

    const { best_bid, best_ask } = ticker
    const range = best_ask - best_bid
    const rawPrice = best_bid + (range * sliderValue / 100)

    // Round to correct increment for this product
    const roundedPrice = roundToIncrement(rawPrice)
    setLimitPrice(roundedPrice)
  }, [sliderValue, ticker, productPrecision])

  const handleSubmit = async () => {
    setIsSubmitting(true)
    setError(null)

    try {
      if (isEditing) {
        // Update existing limit order
        await axios.post(`${API_BASE_URL}/api/positions/${positionId}/update-limit-close`, {
          new_limit_price: limitPrice
        })
      } else {
        // Create new limit order
        await axios.post(`${API_BASE_URL}/api/positions/${positionId}/limit-close`, {
          limit_price: limitPrice
        })
      }
      onSuccess()
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || `Failed to ${isEditing ? 'update' : 'place'} limit order`)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handlePriceInput = (value: string) => {
    const price = parseFloat(value)
    if (isNaN(price) || !ticker) return

    // Round to correct increment before setting
    const roundedPrice = roundToIncrement(price)
    setLimitPrice(roundedPrice)

    // Update slider to match manual input
    const { best_bid, best_ask } = ticker
    const range = best_ask - best_bid
    if (range > 0) {
      const percentage = ((roundedPrice - best_bid) / range) * 100
      setSliderValue(Math.max(0, Math.min(100, percentage)))
    }
  }

  // Get precision for the quote currency
  const getPrecision = () => {
    if (quoteCurrency === 'USD') return 2
    if (quoteCurrency === 'BTC') return 8
    return 8
  }

  // Get step size for slider based on quote currency
  const getStepSize = () => {
    if (quoteCurrency === 'USD') return 0.01
    if (quoteCurrency === 'BTC') return 0.00000001
    return 0.00000001
  }

  const formatPrice = (price: number) => {
    const precision = getPrecision()
    return price.toFixed(precision)
  }

  const estimatedProceeds = limitPrice * totalAmount

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-lg w-full max-w-lg">
        {/* Header */}
        <div className="p-6 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-xl font-bold text-white">
            {isEditing ? 'Update Limit Close Price' : 'Close Position at Limit Price'}
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
          {error && (
            <div className="bg-red-500/10 border border-red-500 rounded p-4 text-red-400 text-sm">
              {error}
            </div>
          )}

          {/* Ticker Info */}
          {ticker && (
            <div className="bg-slate-900 rounded-lg p-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Best Bid:</span>
                <span className="text-green-400 font-mono">{formatPrice(ticker.best_bid)} {quoteCurrency}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Mark Price:</span>
                <span className="text-blue-400 font-mono">{formatPrice(ticker.mark_price)} {quoteCurrency}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Best Ask:</span>
                <span className="text-red-400 font-mono">{formatPrice(ticker.best_ask)} {quoteCurrency}</span>
              </div>
            </div>
          )}

          {/* Slider */}
          {ticker && (
            <div className="space-y-3">
              <label className="block text-sm font-medium text-slate-300">
                Select Limit Price
              </label>
              <div className="relative">
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="0.1"
                  value={sliderValue}
                  onChange={(e) => setSliderValue(parseFloat(e.target.value))}
                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                  style={{
                    background: `linear-gradient(to right, #22c55e ${sliderValue}%, #475569 ${sliderValue}%)`
                  }}
                />
                <div className="flex justify-between text-xs text-slate-400 mt-1">
                  <span>Bid</span>
                  <span>Mark</span>
                  <span>Ask</span>
                </div>
              </div>
            </div>
          )}

          {/* Manual Price Input */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-slate-300">
              Limit Price ({quoteCurrency})
            </label>
            <input
              type="number"
              value={limitPrice}
              onChange={(e) => handlePriceInput(e.target.value)}
              step={getStepSize()}
              className="w-full px-4 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Order Details */}
          <div className="bg-slate-900 rounded-lg p-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-slate-400">Order Type:</span>
              <span className="text-white">Limit (Good-Til-Cancelled)</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-slate-400">Amount to Sell:</span>
              <span className="text-white font-mono">{totalAmount.toFixed(8)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-slate-400">Estimated Proceeds:</span>
              <span className="text-green-400 font-mono">{formatPrice(estimatedProceeds)} {quoteCurrency}</span>
            </div>
          </div>

          {/* Warning */}
          <div className="bg-yellow-500/10 border border-yellow-500 rounded p-4 text-yellow-400 text-sm">
            <strong>Note:</strong> Your limit order may fill partially or not at all if the market price doesn't reach your limit price. You can edit or cancel the order from the positions page.
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-700 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold transition-colors"
            disabled={isSubmitting || !ticker}
          >
            {isSubmitting ? (isEditing ? 'Updating...' : 'Placing Order...') : (isEditing ? 'Update Limit Price' : 'Place Limit Order')}
          </button>
        </div>
      </div>
    </div>
  )
}
