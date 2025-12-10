import { useState, useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import axios from 'axios'
import { API_BASE_URL } from '../config/api'
import { DepthChart } from './DepthChart'

interface LimitCloseModalProps {
  positionId: number
  productId: string
  totalAmount: number
  quoteCurrency: string
  totalQuoteSpent: number  // Cost basis for P/L calculation
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
  totalQuoteSpent,
  isEditing = false,
  currentLimitPrice,
  onClose,
  onSuccess
}: LimitCloseModalProps) {
  const [ticker, setTicker] = useState<TickerData | null>(null)
  const [productPrecision, setProductPrecision] = useState<ProductPrecision | null>(null)
  const [limitPrice, setLimitPrice] = useState<number>(currentLimitPrice || 0)
  const [sliderStep, setSliderStep] = useState<number>(0) // Step index (0 to numSteps)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [btcUsdPrice, setBtcUsdPrice] = useState<number>(0)
  const [showLossConfirmation, setShowLossConfirmation] = useState(false)
  const hasInitializedSlider = useRef(false)

  // Fetch product precision data
  useEffect(() => {
    const fetchPrecision = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/api/product-precision/${productId}`)
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

  // Fetch BTC/USD price for USD conversion (only for BTC pairs)
  useEffect(() => {
    if (quoteCurrency !== 'BTC') return

    const fetchBtcPrice = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/api/market/btc-usd-price`)
        setBtcUsdPrice(response.data.price || 0)
      } catch (err: any) {
        console.error('Failed to fetch BTC/USD price:', err)
      }
    }
    fetchBtcPrice()
  }, [quoteCurrency])

  // Fetch ticker data
  useEffect(() => {
    const fetchTicker = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/api/positions/${positionId}/ticker`)
        const data = response.data
        setTicker(data)
        // Price initialization is handled by separate useEffect with hasInitializedSlider
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

  // Calculate slider parameters based on precision
  const getSliderParams = () => {
    if (!ticker || !productPrecision) return { numSteps: 100, increment: 0 }

    const increment = parseFloat(productPrecision.quote_increment)
    const range = ticker.best_ask - ticker.best_bid
    const numSteps = Math.round(range / increment)

    return { numSteps: Math.max(1, numSteps), increment }
  }

  // Initialize price to mark price ONCE when ticker/precision first loads
  useEffect(() => {
    if (!ticker || !productPrecision) return
    if (hasInitializedSlider.current) return  // Only initialize once

    // Start at mark price (middle of bid/ask)
    const initialPrice = roundToIncrement(ticker.mark_price)
    setLimitPrice(initialPrice)
    hasInitializedSlider.current = true
  }, [ticker, productPrecision])

  // Update slider step to match current price (for visual display)
  // This runs on ticker updates to keep slider position accurate
  useEffect(() => {
    if (!ticker || !productPrecision || limitPrice === 0) return

    const { best_bid } = ticker
    const increment = parseFloat(productPrecision.quote_increment)
    const { numSteps } = getSliderParams()

    // Calculate step from current price
    const step = Math.round((limitPrice - best_bid) / increment)
    // Clamp to valid range
    setSliderStep(Math.max(0, Math.min(numSteps, step)))
  }, [ticker, productPrecision, limitPrice])

  // Handle slider change - update price from new step
  const handleSliderChange = (newStep: number) => {
    if (!ticker || !productPrecision) return

    setShowLossConfirmation(false)

    const { best_bid } = ticker
    const increment = parseFloat(productPrecision.quote_increment)
    const decimals = productPrecision.quote_decimals

    const rawPrice = best_bid + (newStep * increment)
    const roundedPrice = parseFloat(rawPrice.toFixed(decimals))
    setLimitPrice(roundedPrice)
  }

  // Calculate profit/loss at current limit price
  const calculateProfitLoss = () => {
    const expectedProceeds = limitPrice * totalAmount
    const profitLossBtc = expectedProceeds - totalQuoteSpent
    const profitLossUsd = quoteCurrency === 'BTC' ? profitLossBtc * btcUsdPrice : profitLossBtc
    const profitLossPercent = totalQuoteSpent > 0 ? (profitLossBtc / totalQuoteSpent) * 100 : 0
    const isLoss = profitLossBtc < 0
    return { profitLossBtc, profitLossUsd, profitLossPercent, isLoss }
  }

  const handleSubmitClick = () => {
    const { isLoss } = calculateProfitLoss()
    if (isLoss && !showLossConfirmation) {
      // Show loss confirmation first
      setShowLossConfirmation(true)
      return
    }
    // Proceed with actual submission
    handleSubmit()
  }

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
      setShowLossConfirmation(false)
    }
  }

  const handlePriceInput = (value: string) => {
    const price = parseFloat(value)
    if (isNaN(price) || !ticker || !productPrecision) return

    // Reset loss confirmation when price changes
    setShowLossConfirmation(false)

    // Round to correct increment before setting
    const roundedPrice = roundToIncrement(price)
    setLimitPrice(roundedPrice)

    // Update slider step to match manual input
    const { best_bid } = ticker
    const increment = parseFloat(productPrecision.quote_increment)
    const { numSteps } = getSliderParams()

    if (increment > 0) {
      const step = Math.round((roundedPrice - best_bid) / increment)
      setSliderStep(Math.max(0, Math.min(numSteps, step)))
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

  // Calculate breakeven price for depth chart
  const breakevenPrice = totalAmount > 0 ? totalQuoteSpent / totalAmount : 0

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-lg w-full max-w-2xl flex">
        {/* Main Content */}
        <div className="flex-1">
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
          {ticker && productPrecision && (() => {
            const { isLoss } = calculateProfitLoss()
            const sliderColor = isLoss ? '#ef4444' : '#22c55e'  // Red when at loss, green when profit
            const { numSteps } = getSliderParams()

            // Calculate slider position as percentage for visual display
            const sliderPercent = numSteps > 0 ? (sliderStep / numSteps) * 100 : 50

            // Calculate breakeven position on slider
            const breakevenPrice = totalAmount > 0 ? totalQuoteSpent / totalAmount : 0
            const { best_bid, best_ask } = ticker
            const range = best_ask - best_bid
            const breakevenPercent = range > 0 ? ((breakevenPrice - best_bid) / range) * 100 : -1
            const showBreakevenTick = breakevenPercent >= 0 && breakevenPercent <= 100

            // Calculate tick marks - show max ~40 ticks for readability
            const maxTicks = 40
            const tickInterval = numSteps <= maxTicks ? 1 : Math.ceil(numSteps / maxTicks)
            const ticks: number[] = []
            for (let i = 0; i <= numSteps; i += tickInterval) {
              ticks.push(i)
            }
            // Always include the last tick
            if (ticks[ticks.length - 1] !== numSteps) {
              ticks.push(numSteps)
            }

            return (
              <div className="space-y-3">
                <label className="block text-sm font-medium text-slate-300">
                  Select Limit Price {isLoss && <span className="text-red-400 text-xs ml-2">(below breakeven)</span>}
                  <span className="text-slate-500 text-xs ml-2">({numSteps} price levels)</span>
                </label>
                <div className="relative">
                  {/* Tick marks container - positioned behind slider */}
                  <div className="absolute inset-0 flex items-center pointer-events-none" style={{ height: '8px' }}>
                    <div className="relative w-full h-full">
                      {ticks.map((tick) => {
                        const tickPercent = numSteps > 0 ? (tick / numSteps) * 100 : 0
                        const isInFilledRegion = tickPercent <= sliderPercent
                        return (
                          <div
                            key={tick}
                            className="absolute top-0 h-full"
                            style={{
                              left: `${tickPercent}%`,
                              width: '1px',
                              backgroundColor: isInFilledRegion
                                ? (isLoss ? 'rgba(185, 28, 28, 0.6)' : 'rgba(21, 128, 61, 0.6)')  // Darker shade of slider color
                                : 'rgba(100, 116, 139, 0.5)',  // slate-500 with opacity
                              transform: 'translateX(-50%)'
                            }}
                          />
                        )
                      })}
                    </div>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max={numSteps}
                    step="1"
                    value={sliderStep}
                    onChange={(e) => handleSliderChange(parseInt(e.target.value))}
                    className="w-full h-2 bg-transparent rounded-lg appearance-none cursor-pointer relative z-10"
                    style={{
                      background: `linear-gradient(to right, ${sliderColor} ${sliderPercent}%, #475569 ${sliderPercent}%)`
                    }}
                  />
                  {/* Breakeven tick mark */}
                  {showBreakevenTick && (
                    <div
                      className="absolute top-0 w-0.5 h-4 bg-yellow-400 -translate-x-1/2 pointer-events-none z-20"
                      style={{ left: `${breakevenPercent}%`, marginTop: '-3px' }}
                      title={`Breakeven: ${formatPrice(breakevenPrice)}`}
                    >
                      <div className="absolute -top-4 left-1/2 -translate-x-1/2 text-[10px] text-yellow-400 whitespace-nowrap">
                        BE
                      </div>
                    </div>
                  )}
                  <div className="flex justify-between text-xs text-slate-400 mt-1">
                    <span>Bid</span>
                    <span>Mark</span>
                    <span>Ask</span>
                  </div>
                </div>
              </div>
            )
          })()}

          {/* Manual Price Input */}
          {(() => {
            const { isLoss } = calculateProfitLoss()
            return (
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-300">
                  Limit Price ({quoteCurrency})
                </label>
                <input
                  type="number"
                  value={limitPrice}
                  onChange={(e) => handlePriceInput(e.target.value)}
                  step={getStepSize()}
                  className={`w-full px-4 py-2 bg-slate-900 border rounded-lg text-white font-mono focus:outline-none focus:ring-2 ${
                    isLoss
                      ? 'border-red-500 focus:ring-red-500'
                      : 'border-slate-700 focus:ring-blue-500'
                  }`}
                />
              </div>
            )
          })()}

          {/* Order Details */}
          {(() => {
            const { profitLossBtc, profitLossUsd, profitLossPercent, isLoss } = calculateProfitLoss()
            return (
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
                  <span className={`font-mono ${isLoss ? 'text-red-400' : 'text-green-400'}`}>
                    {formatPrice(estimatedProceeds)} {quoteCurrency}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Est. P/L:</span>
                  <span className={`font-mono ${isLoss ? 'text-red-400' : 'text-green-400'}`}>
                    {isLoss ? '' : '+'}{quoteCurrency === 'BTC' ? profitLossBtc.toFixed(8) : profitLossBtc.toFixed(2)} {quoteCurrency}
                    {quoteCurrency === 'BTC' && btcUsdPrice > 0 && (
                      <span className="ml-2 text-slate-400">
                        (${isLoss ? '-' : '+'}${Math.abs(profitLossUsd).toFixed(2)})
                      </span>
                    )}
                    <span className="ml-2">({profitLossPercent >= 0 ? '+' : ''}{profitLossPercent.toFixed(2)}%)</span>
                  </span>
                </div>
              </div>
            )
          })()}

          {/* Loss Warning (shown when selling at a loss and confirmed) */}
          {showLossConfirmation && (() => {
            const { profitLossBtc, profitLossUsd, profitLossPercent } = calculateProfitLoss()
            return (
              <div className="bg-red-500/20 border-2 border-red-500 rounded p-4 text-red-300 text-sm space-y-2">
                <div className="flex items-center gap-2 font-bold text-red-400">
                  <span className="text-xl">⚠️</span>
                  <span>This order will result in a LOSS</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-slate-400">Loss ({quoteCurrency}):</span>
                    <span className="ml-2 font-mono text-red-400">
                      {quoteCurrency === 'BTC' ? profitLossBtc.toFixed(8) : profitLossBtc.toFixed(2)} {quoteCurrency}
                    </span>
                  </div>
                  {quoteCurrency === 'BTC' && btcUsdPrice > 0 && (
                    <div>
                      <span className="text-slate-400">Loss (USD):</span>
                      <span className="ml-2 font-mono text-red-400">${Math.abs(profitLossUsd).toFixed(2)}</span>
                    </div>
                  )}
                  <div>
                    <span className="text-slate-400">Loss %:</span>
                    <span className="ml-2 font-mono text-red-400">{profitLossPercent.toFixed(2)}%</span>
                  </div>
                </div>
                <p className="mt-2 text-yellow-400 font-semibold">Are you sure you want to sell at a loss?</p>
              </div>
            )
          })()}

          {/* Standard Warning (shown when not confirming loss) */}
          {!showLossConfirmation && (
            <div className="bg-yellow-500/10 border border-yellow-500 rounded p-4 text-yellow-400 text-sm">
              <strong>Note:</strong> Your limit order may fill partially or not at all if the market price doesn't reach your limit price. You can edit or cancel the order from the positions page.
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-700 flex gap-3">
          <button
            onClick={() => {
              if (showLossConfirmation) {
                setShowLossConfirmation(false)
              } else {
                onClose()
              }
            }}
            className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            disabled={isSubmitting}
          >
            {showLossConfirmation ? 'Go Back' : 'Cancel'}
          </button>
          <button
            onClick={handleSubmitClick}
            className={`flex-1 px-4 py-2 rounded-lg font-semibold transition-colors ${
              showLossConfirmation
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
            disabled={isSubmitting || !ticker}
          >
            {isSubmitting
              ? (isEditing ? 'Updating...' : 'Placing Order...')
              : showLossConfirmation
                ? 'Yes, Sell at Loss'
                : (isEditing ? 'Update Limit Price' : 'Place Limit Order')
            }
          </button>
        </div>
        </div>

        {/* Depth Chart - Right Side */}
        <div className="w-32 border-l border-slate-700 p-2">
          <DepthChart
            productId={productId}
            limitPrice={limitPrice}
            breakevenPrice={breakevenPrice}
            quoteCurrency={quoteCurrency}
          />
        </div>
      </div>
    </div>
  )
}
