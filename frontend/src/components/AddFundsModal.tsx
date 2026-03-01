/**
 * AddFundsModal - Add funds to an open position
 * Shows a slider and input field that stay synchronized
 * Respects exchange minimums as the floor
 */

import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, AlertTriangle, Info } from 'lucide-react'
import { accountApi, positionsApi } from '../services/api'
import type { Position } from '../types'

// Exchange minimums (from backend/app/order_validation.py)
const EXCHANGE_MINIMUMS = {
  BTC: 0.0001, // ~$10 at $100k/BTC
  USD: 1.0,    // $1 minimum
}

interface AddFundsModalProps {
  position: Position
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  readOnly?: boolean
}

export function AddFundsModal({ position, isOpen, onClose, onSuccess, readOnly = false }: AddFundsModalProps) {
  const [amount, setAmount] = useState(0)
  const [inputValue, setInputValue] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Determine quote currency from product_id (e.g., ETH-BTC -> BTC, SOL-USD -> USD)
  const quoteCurrency = useMemo(() => {
    if (!position.product_id) return 'BTC'
    const parts = position.product_id.split('-')
    return parts.length > 1 ? parts[1] : 'BTC'
  }, [position.product_id])

  const isUsdPair = quoteCurrency === 'USD'
  const exchangeMinimum = isUsdPair ? EXCHANGE_MINIMUMS.USD : EXCHANGE_MINIMUMS.BTC
  const decimals = isUsdPair ? 2 : 8

  // Fetch aggregate balances
  const { data: aggregateValue, isLoading } = useQuery({
    queryKey: ['aggregateValue'],
    queryFn: () => accountApi.getAggregateValue(),
    enabled: isOpen,
    staleTime: 10000, // 10 seconds
  })

  // Calculate available free balance for this quote currency
  const availableBalance = useMemo(() => {
    if (!aggregateValue) return 0
    return isUsdPair ? aggregateValue.aggregate_usd_value : aggregateValue.aggregate_btc_value
  }, [aggregateValue, isUsdPair])

  // Calculate percentage from amount
  const percentage = useMemo(() => {
    if (availableBalance <= 0) return 0
    return Math.min(100, (amount / availableBalance) * 100)
  }, [amount, availableBalance])

  // Position budget remaining
  const remainingBudget = position.max_quote_allowed - position.total_quote_spent

  // Maximum amount is the lesser of available balance and remaining budget
  const maxAmount = Math.min(availableBalance, remainingBudget)

  // Validation checks
  const isBelowMinimum = amount > 0 && amount < exchangeMinimum
  const exceedsBudget = amount > remainingBudget
  const exceedsAvailable = amount > availableBalance
  const isValidAmount = amount >= exchangeMinimum && !exceedsBudget && !exceedsAvailable

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen && availableBalance > 0) {
      // Start at 25% or minimum, whichever is greater
      const initialPercent = 25
      const initialAmount = Math.max(
        (availableBalance * initialPercent) / 100,
        exchangeMinimum
      )
      const clampedAmount = Math.min(initialAmount, maxAmount)
      setAmount(clampedAmount)
      setInputValue(clampedAmount.toFixed(decimals))
      setError(null)
    }
  }, [isOpen, availableBalance, exchangeMinimum, maxAmount, decimals])

  // Handle slider change - update both amount and input field
  const handleSliderChange = (newPercentage: number) => {
    const newAmount = (availableBalance * newPercentage) / 100
    // Clamp to exchange minimum if above 0
    const clampedAmount = newPercentage === 0 ? 0 : Math.max(newAmount, exchangeMinimum)
    const finalAmount = Math.min(clampedAmount, maxAmount)
    setAmount(finalAmount)
    setInputValue(finalAmount.toFixed(decimals))
  }

  // Handle input field change - update both amount and slider
  const handleInputChange = (value: string) => {
    setInputValue(value)
    const parsed = parseFloat(value)
    if (!isNaN(parsed) && parsed >= 0) {
      setAmount(parsed)
    } else if (value === '' || value === '0') {
      setAmount(0)
    }
  }

  // Handle input blur - enforce minimum if needed
  const handleInputBlur = () => {
    if (amount > 0 && amount < exchangeMinimum) {
      setAmount(exchangeMinimum)
      setInputValue(exchangeMinimum.toFixed(decimals))
    } else if (amount > maxAmount) {
      setAmount(maxAmount)
      setInputValue(maxAmount.toFixed(decimals))
    }
  }

  const handleSubmit = async () => {
    if (!isValidAmount) return

    setIsSubmitting(true)
    setError(null)

    try {
      await positionsApi.addFunds(position.id, amount)
      onSuccess()
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to add funds')
    } finally {
      setIsSubmitting(false)
    }
  }

  const formatAmount = (value: number) => {
    if (isUsdPair) {
      return `$${value.toFixed(2)}`
    }
    return `${value.toFixed(8)} BTC`
  }

  // Calculate minimum percentage that meets exchange minimum
  const minPercentage = useMemo(() => {
    if (availableBalance <= 0) return 0
    return (exchangeMinimum / availableBalance) * 100
  }, [availableBalance, exchangeMinimum])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-lg w-full max-w-md">
        {/* Header */}
        <div className="p-6 border-b border-slate-700">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xl font-bold text-white">Add Funds to Position</h3>
              <p className="text-sm text-slate-400 mt-1">{position.product_id}</p>
            </div>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white transition-colors"
            >
              <X size={24} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
            </div>
          ) : (
            <>
              {/* Available Balance Info */}
              <div className="bg-slate-700/50 rounded-lg p-4">
                <div className="flex items-center gap-2 text-slate-300 mb-2">
                  <Info size={16} />
                  <span className="text-sm">Available {quoteCurrency}</span>
                </div>
                <div className="text-2xl font-bold text-white">
                  {formatAmount(availableBalance)}
                </div>
                <div className="flex justify-between text-xs text-slate-400 mt-1">
                  <span>Min order: {formatAmount(exchangeMinimum)}</span>
                  <span>Position budget: {formatAmount(remainingBudget)}</span>
                </div>
              </div>

              {/* Amount Input */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Amount to Add
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step={isUsdPair ? '0.01' : '0.00000001'}
                    min={exchangeMinimum}
                    max={maxAmount}
                    value={inputValue}
                    onChange={(e) => handleInputChange(e.target.value)}
                    onBlur={handleInputBlur}
                    className="w-full bg-slate-700 border border-slate-600 rounded px-4 py-3 text-white text-lg font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 pr-16"
                    placeholder={exchangeMinimum.toFixed(decimals)}
                    disabled={isSubmitting}
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400">
                    {quoteCurrency}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  = {percentage.toFixed(1)}% of available balance
                </p>
              </div>

              {/* Percentage Slider */}
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <label className="text-sm font-medium text-slate-300">
                    Percentage of Available
                  </label>
                  <span className="text-lg font-bold text-blue-400">{percentage.toFixed(1)}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={0.5}
                  value={percentage}
                  onChange={(e) => handleSliderChange(parseFloat(e.target.value))}
                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer slider-thumb"
                  disabled={isSubmitting}
                />
                <div className="flex justify-between text-xs text-slate-500">
                  <span>0%</span>
                  <span>25%</span>
                  <span>50%</span>
                  <span>75%</span>
                  <span>100%</span>
                </div>

                {/* Quick select buttons */}
                <div className="flex gap-2">
                  {[10, 25, 50, 75, 100].map((pct) => (
                    <button
                      key={pct}
                      onClick={() => handleSliderChange(pct)}
                      className={`flex-1 py-1.5 text-sm rounded transition-colors ${
                        Math.abs(percentage - pct) < 1
                          ? 'bg-blue-600 text-white'
                          : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                      }`}
                      disabled={isSubmitting}
                    >
                      {pct}%
                    </button>
                  ))}
                </div>
              </div>

              {/* Warnings */}
              {isBelowMinimum && (
                <div className="flex items-center gap-2 bg-yellow-900/30 border border-yellow-600/50 rounded-lg px-4 py-3 text-yellow-400">
                  <AlertTriangle size={18} />
                  <span className="text-sm">
                    Amount is below exchange minimum ({formatAmount(exchangeMinimum)})
                  </span>
                </div>
              )}

              {exceedsBudget && !exceedsAvailable && (
                <div className="flex items-center gap-2 bg-red-900/30 border border-red-600/50 rounded-lg px-4 py-3 text-red-400">
                  <AlertTriangle size={18} />
                  <span className="text-sm">
                    Exceeds position budget (max: {formatAmount(remainingBudget)})
                  </span>
                </div>
              )}

              {exceedsAvailable && (
                <div className="flex items-center gap-2 bg-red-900/30 border border-red-600/50 rounded-lg px-4 py-3 text-red-400">
                  <AlertTriangle size={18} />
                  <span className="text-sm">
                    Exceeds available balance (max: {formatAmount(availableBalance)})
                  </span>
                </div>
              )}

              {minPercentage > 100 && (
                <div className="flex items-center gap-2 bg-red-900/30 border border-red-600/50 rounded-lg px-4 py-3 text-red-400">
                  <AlertTriangle size={18} />
                  <span className="text-sm">
                    Insufficient {quoteCurrency} balance for minimum order
                  </span>
                </div>
              )}

              {error && (
                <div className="flex items-center gap-2 bg-red-900/30 border border-red-600/50 rounded-lg px-4 py-3 text-red-400">
                  <AlertTriangle size={18} />
                  <span className="text-sm">{error}</span>
                </div>
              )}

              {/* Info text */}
              <p className="text-xs text-slate-400">
                This will execute a manual safety order at current market price.
              </p>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-700 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 bg-slate-700 hover:bg-slate-600 text-white px-4 py-3 rounded-lg font-medium transition-colors"
            disabled={isSubmitting}
          >
            Cancel
          </button>
          {!readOnly && (
            <button
              onClick={handleSubmit}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-4 py-3 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSubmitting || !isValidAmount || isLoading}
            >
              {isSubmitting ? 'Adding...' : `Add ${formatAmount(amount)}`}
            </button>
          )}
        </div>
      </div>

      {/* Custom slider thumb styles */}
      <style>{`
        .slider-thumb::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 20px;
          height: 20px;
          background: #3b82f6;
          border-radius: 50%;
          cursor: pointer;
          transition: background 0.15s ease;
        }
        .slider-thumb::-webkit-slider-thumb:hover {
          background: #2563eb;
        }
        .slider-thumb::-moz-range-thumb {
          width: 20px;
          height: 20px;
          background: #3b82f6;
          border-radius: 50%;
          cursor: pointer;
          border: none;
        }
      `}</style>
    </div>
  )
}
