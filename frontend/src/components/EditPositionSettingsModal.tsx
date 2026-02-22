import { useState } from 'react'
import { X, Settings, TrendingUp, Shield, Target } from 'lucide-react'
import { positionsApi, UpdatePositionSettingsRequest } from '../services/api'
import type { Position } from '../types'

interface EditPositionSettingsModalProps {
  position: Position
  onClose: () => void
  onSuccess: () => void
}

export function EditPositionSettingsModal({
  position,
  onClose,
  onSuccess
}: EditPositionSettingsModalProps) {
  const config = position.strategy_config_snapshot || {}

  // Form state initialized from current config snapshot
  // Use string state for number inputs to allow natural editing (clearing, typing)
  const [takeProfitPercentage, setTakeProfitPercentage] = useState<string>(
    String(config.take_profit_percentage ?? 1.5)
  )
  const [maxSafetyOrders, setMaxSafetyOrders] = useState<string>(
    String(config.max_safety_orders ?? 5)
  )
  const [trailingTakeProfit, setTrailingTakeProfit] = useState<boolean>(
    config.trailing_take_profit ?? false
  )
  const [trailingTpDeviation, setTrailingTpDeviation] = useState<string>(
    String(config.trailing_tp_deviation ?? 0.5)
  )
  const [stopLossEnabled, setStopLossEnabled] = useState<boolean>(
    config.stop_loss_enabled ?? false
  )
  const [stopLossPercentage, setStopLossPercentage] = useState<string>(
    String(config.stop_loss_percentage ?? -10)
  )

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Parse string state to numbers for comparison and submission
  const parsedTakeProfit = parseFloat(takeProfitPercentage) || 0
  const parsedMaxSafety = parseInt(maxSafetyOrders) || 0
  const parsedTrailingDev = parseFloat(trailingTpDeviation) || 0
  const parsedStopLoss = parseFloat(stopLossPercentage) || 0

  // Track which fields have been modified
  const hasChanges = () => {
    const originalConfig = position.strategy_config_snapshot || {}
    return (
      parsedTakeProfit !== (originalConfig.take_profit_percentage ?? 1.5) ||
      parsedMaxSafety !== (originalConfig.max_safety_orders ?? 5) ||
      trailingTakeProfit !== (originalConfig.trailing_take_profit ?? false) ||
      parsedTrailingDev !== (originalConfig.trailing_tp_deviation ?? 0.5) ||
      stopLossEnabled !== (originalConfig.stop_loss_enabled ?? false) ||
      parsedStopLoss !== (originalConfig.stop_loss_percentage ?? -10)
    )
  }

  const handleSubmit = async () => {
    setIsSubmitting(true)
    setError(null)
    setSuccessMessage(null)

    try {
      // Build request with only changed fields
      const request: UpdatePositionSettingsRequest = {}
      const originalConfig = position.strategy_config_snapshot || {}

      if (parsedTakeProfit !== (originalConfig.take_profit_percentage ?? 1.5)) {
        request.take_profit_percentage = parsedTakeProfit
      }
      if (parsedMaxSafety !== (originalConfig.max_safety_orders ?? 5)) {
        request.max_safety_orders = parsedMaxSafety
      }
      if (trailingTakeProfit !== (originalConfig.trailing_take_profit ?? false)) {
        request.trailing_take_profit = trailingTakeProfit
      }
      if (parsedTrailingDev !== (originalConfig.trailing_tp_deviation ?? 0.5)) {
        request.trailing_tp_deviation = parsedTrailingDev
      }
      if (stopLossEnabled !== (originalConfig.stop_loss_enabled ?? false)) {
        request.stop_loss_enabled = stopLossEnabled
      }
      if (parsedStopLoss !== (originalConfig.stop_loss_percentage ?? -10)) {
        request.stop_loss_percentage = parsedStopLoss
      }

      const result = await positionsApi.updateSettings(position.id, request)
      setSuccessMessage(result.message)

      // Wait a moment to show success, then close
      setTimeout(() => {
        onSuccess()
        onClose()
      }, 1000)
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } } }
      setError(axiosError.response?.data?.detail || 'Failed to update position settings')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-2 sm:p-4">
      <div className="bg-slate-800 rounded-lg w-full max-w-lg max-h-[95vh] sm:max-h-[90vh] overflow-y-auto mx-1 sm:mx-auto">
        {/* Header */}
        <div className="p-6 border-b border-slate-700 flex items-center justify-between sticky top-0 bg-slate-800">
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-blue-400" />
            <h2 className="text-xl font-bold text-white">
              Edit Deal Settings
            </h2>
          </div>
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

          {successMessage && (
            <div className="bg-green-500/10 border border-green-500 rounded p-4 text-green-400 text-sm">
              {successMessage}
            </div>
          )}

          {/* Position Info */}
          <div className="bg-slate-900 rounded-lg p-4">
            <div className="flex justify-between text-sm">
              <span className="text-slate-400">Position:</span>
              <span className="text-white font-mono">#{position.id} - {position.product_id}</span>
            </div>
            <div className="flex justify-between text-sm mt-2">
              <span className="text-slate-400">Current P&L:</span>
              <span className={`font-mono ${(position.profit_percentage ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {(position.profit_percentage ?? 0).toFixed(2)}%
              </span>
            </div>
          </div>

          {/* Take Profit Section */}
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-green-400">
              <Target className="w-4 h-4" />
              <h3 className="font-semibold">Take Profit</h3>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-300">
                Take Profit % (from avg buy price)
              </label>
              <input
                type="number"
                value={takeProfitPercentage}
                onChange={(e) => setTakeProfitPercentage(e.target.value)}
                onBlur={() => { if (takeProfitPercentage === '' || isNaN(parseFloat(takeProfitPercentage))) setTakeProfitPercentage(String(config.take_profit_percentage ?? 1.5)) }}
                step="0.1"
                min="0.1"
                className="w-full px-4 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-green-500"
              />
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="trailingTakeProfit"
                checked={trailingTakeProfit}
                onChange={(e) => setTrailingTakeProfit(e.target.checked)}
                className="w-4 h-4 rounded bg-slate-900 border-slate-700 text-green-500 focus:ring-green-500"
              />
              <label htmlFor="trailingTakeProfit" className="text-sm text-slate-300">
                Enable Trailing Take Profit
              </label>
            </div>

            {trailingTakeProfit && (
              <div className="space-y-2 ml-7">
                <label className="block text-sm font-medium text-slate-300">
                  Trailing Deviation %
                </label>
                <input
                  type="number"
                  value={trailingTpDeviation}
                  onChange={(e) => setTrailingTpDeviation(e.target.value)}
                  onBlur={() => { if (trailingTpDeviation === '' || isNaN(parseFloat(trailingTpDeviation))) setTrailingTpDeviation(String(config.trailing_tp_deviation ?? 0.5)) }}
                  step="0.1"
                  min="0.1"
                  className="w-full px-4 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-green-500"
                />
                <p className="text-xs text-slate-500">
                  Sell when price drops this % from the highest point after hitting TP target
                </p>
              </div>
            )}
          </div>

          {/* Safety Orders Section */}
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-blue-400">
              <TrendingUp className="w-4 h-4" />
              <h3 className="font-semibold">Safety Orders (DCA)</h3>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-300">
                Max Safety Orders
              </label>
              <input
                type="number"
                value={maxSafetyOrders}
                onChange={(e) => setMaxSafetyOrders(e.target.value)}
                onBlur={() => { if (maxSafetyOrders === '' || isNaN(parseInt(maxSafetyOrders))) setMaxSafetyOrders(String(config.max_safety_orders ?? 5)) }}
                step="1"
                min="0"
                max="50"
                className="w-full px-4 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-slate-500">
                Current trades: {position.trade_count ?? 1} (including base order)
              </p>
            </div>
          </div>

          {/* Stop Loss Section */}
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-red-400">
              <Shield className="w-4 h-4" />
              <h3 className="font-semibold">Stop Loss</h3>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="stopLossEnabled"
                checked={stopLossEnabled}
                onChange={(e) => setStopLossEnabled(e.target.checked)}
                className="w-4 h-4 rounded bg-slate-900 border-slate-700 text-red-500 focus:ring-red-500"
              />
              <label htmlFor="stopLossEnabled" className="text-sm text-slate-300">
                Enable Stop Loss
              </label>
            </div>

            {stopLossEnabled && (
              <div className="space-y-2 ml-7">
                <label className="block text-sm font-medium text-slate-300">
                  Stop Loss % (negative value)
                </label>
                <input
                  type="number"
                  value={stopLossPercentage}
                  onChange={(e) => setStopLossPercentage(e.target.value)}
                  onBlur={() => { if (stopLossPercentage === '' || isNaN(parseFloat(stopLossPercentage))) setStopLossPercentage(String(config.stop_loss_percentage ?? -10)) }}
                  step="0.5"
                  max="0"
                  className="w-full px-4 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono focus:outline-none focus:ring-2 focus:ring-red-500"
                />
                <p className="text-xs text-slate-500">
                  Exit position when loss reaches this percentage
                </p>
              </div>
            )}
          </div>

          {/* Info Note */}
          <div className="bg-blue-500/10 border border-blue-500 rounded p-4 text-blue-400 text-sm">
            <strong>Note:</strong> These changes only affect this position (deal). The bot's default settings remain unchanged.
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-700 flex gap-3 sticky bottom-0 bg-slate-800">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold transition-colors disabled:opacity-50"
            disabled={isSubmitting || !hasChanges()}
          >
            {isSubmitting ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}
