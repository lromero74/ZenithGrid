/**
 * Seasonality Toggle Component
 *
 * Displays the current market season and allows toggling seasonality-based
 * bot management on/off.
 *
 * When enabled:
 * - Risk-On (Winter 80% → Summer 80%): BTC bots allowed, USD bots blocked
 * - Risk-Off (Summer 80% → Winter 80%): USD bots allowed, BTC bots blocked
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sun, Snowflake, Leaf, Sprout, ToggleLeft, ToggleRight, AlertTriangle, TrendingUp, DollarSign } from 'lucide-react'
import { LoadingSpinner } from './LoadingSpinner'

interface SeasonalityStatus {
  enabled: boolean
  season: 'accumulation' | 'bull' | 'distribution' | 'bear'
  season_name: string
  subtitle: string
  description: string
  progress: number
  confidence: number
  signals: string[]
  mode: 'risk_on' | 'risk_off'
  btc_bots_allowed: boolean
  usd_bots_allowed: boolean
  threshold_crossed: boolean
  last_transition: string | null
}

const seasonIcons = {
  accumulation: Sprout,
  bull: Sun,
  distribution: Leaf,
  bear: Snowflake,
}

const seasonColors = {
  accumulation: { text: 'text-pink-400', bg: 'bg-pink-500', border: 'border-pink-500/50', bgMuted: 'bg-pink-900/30' },
  bull: { text: 'text-green-400', bg: 'bg-green-500', border: 'border-green-500/50', bgMuted: 'bg-green-900/30' },
  distribution: { text: 'text-orange-400', bg: 'bg-orange-500', border: 'border-orange-500/50', bgMuted: 'bg-orange-900/30' },
  bear: { text: 'text-blue-400', bg: 'bg-blue-500', border: 'border-blue-500/50', bgMuted: 'bg-blue-900/30' },
}

export function SeasonalityToggle() {
  const queryClient = useQueryClient()
  const [showConfirmDisable, setShowConfirmDisable] = useState(false)

  // Fetch seasonality status
  const { data: status, isLoading, error } = useQuery<SeasonalityStatus>({
    queryKey: ['seasonality'],
    queryFn: async () => {
      const response = await fetch('/api/seasonality')
      if (!response.ok) throw new Error('Failed to fetch seasonality status')
      return response.json()
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchInterval: 1000 * 60 * 5,
  })

  // Toggle mutation
  const toggleMutation = useMutation({
    mutationFn: async (enabled: boolean) => {
      const response = await fetch('/api/seasonality', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      if (!response.ok) throw new Error('Failed to toggle seasonality')
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seasonality'] })
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  const handleToggle = () => {
    if (status?.enabled) {
      // Disabling - show confirmation
      setShowConfirmDisable(true)
    } else {
      // Enabling
      toggleMutation.mutate(true)
    }
  }

  const confirmDisable = () => {
    toggleMutation.mutate(false)
    setShowConfirmDisable(false)
  }

  if (isLoading) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-6">
        <div className="flex items-center justify-center h-24">
          <LoadingSpinner size="sm" text="Loading seasonality..." />
        </div>
      </div>
    )
  }

  if (error || !status) {
    return null // Silently fail - seasonality is optional
  }

  const SeasonIcon = seasonIcons[status.season]
  const colors = seasonColors[status.season]

  return (
    <>
      <div className={`bg-slate-800 border ${status.enabled ? colors.border : 'border-slate-700'} rounded-lg p-4 mb-6`}>
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          {/* Left: Season Info */}
          <div className="flex items-center gap-4">
            {/* Season Icon */}
            <div className={`w-12 h-12 rounded-full ${colors.bgMuted} flex items-center justify-center`}>
              <SeasonIcon className={`w-6 h-6 ${colors.text}`} />
            </div>

            {/* Season Details */}
            <div>
              <div className="flex items-center gap-2">
                <span className={`text-lg font-semibold ${colors.text}`}>{status.season_name}</span>
                <span className="text-slate-500 text-sm">({status.subtitle})</span>
              </div>
              <p className="text-slate-400 text-sm">{status.description}</p>
            </div>
          </div>

          {/* Center: Progress and Mode */}
          <div className="flex-1 max-w-md px-4">
            {/* Progress bar with 80% threshold marker */}
            <div className="mb-2">
              <div className="flex justify-between text-xs text-slate-500 mb-1">
                <span>Progress</span>
                <span>{status.progress.toFixed(0)}%</span>
              </div>
              <div className="relative h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className={`h-full ${colors.bg} transition-all duration-500`}
                  style={{ width: `${status.progress}%` }}
                />
                {/* 80% threshold marker */}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-yellow-400"
                  style={{ left: '80%' }}
                  title="80% threshold - mode transition point"
                />
              </div>
            </div>

            {/* Mode indicator */}
            <div className="flex items-center justify-center gap-4 mt-2">
              <div className={`flex items-center gap-1 px-2 py-0.5 rounded ${
                status.mode === 'risk_on' ? 'bg-green-900/50 text-green-400' : 'bg-slate-700 text-slate-500'
              }`}>
                <TrendingUp className="w-3 h-3" />
                <span className="text-xs font-medium">Risk-On</span>
              </div>
              <div className={`flex items-center gap-1 px-2 py-0.5 rounded ${
                status.mode === 'risk_off' ? 'bg-red-900/50 text-red-400' : 'bg-slate-700 text-slate-500'
              }`}>
                <DollarSign className="w-3 h-3" />
                <span className="text-xs font-medium">Risk-Off</span>
              </div>
            </div>
          </div>

          {/* Right: Toggle and Status */}
          <div className="flex flex-col items-end gap-2">
            {/* Toggle */}
            <button
              onClick={handleToggle}
              disabled={toggleMutation.isPending}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                status.enabled
                  ? 'bg-green-600 hover:bg-green-700 text-white'
                  : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
              }`}
            >
              {status.enabled ? (
                <ToggleRight className="w-5 h-5" />
              ) : (
                <ToggleLeft className="w-5 h-5" />
              )}
              <span className="font-medium text-sm">
                {toggleMutation.isPending ? 'Updating...' : status.enabled ? 'Enabled' : 'Disabled'}
              </span>
            </button>

            {/* Bot restrictions */}
            {status.enabled && (
              <div className="flex items-center gap-3 text-xs">
                <span className={status.btc_bots_allowed ? 'text-green-400' : 'text-red-400'}>
                  BTC: {status.btc_bots_allowed ? 'Allowed' : 'Blocked'}
                </span>
                <span className={status.usd_bots_allowed ? 'text-green-400' : 'text-red-400'}>
                  USD: {status.usd_bots_allowed ? 'Allowed' : 'Blocked'}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Signals */}
        {status.signals.length > 0 && (
          <div className="mt-3 pt-3 border-t border-slate-700">
            <div className="flex flex-wrap gap-2">
              {status.signals.map((signal, i) => (
                <span key={i} className="text-xs text-slate-400 px-2 py-0.5 bg-slate-700/50 rounded">
                  {signal}
                </span>
              ))}
              <span className="text-xs text-slate-500 px-2 py-0.5">
                {status.confidence}% confidence
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Disable Confirmation Modal */}
      {showConfirmDisable && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="w-full max-w-md bg-slate-800 rounded-lg shadow-2xl border border-slate-700">
            <div className="flex items-center gap-2 p-4 border-b border-slate-700">
              <AlertTriangle className="w-5 h-5 text-yellow-400" />
              <h3 className="text-lg font-semibold text-white">Disable Seasonality?</h3>
            </div>
            <div className="p-4">
              <p className="text-slate-300 text-sm">
                Disabling seasonality will remove all automatic bot restrictions.
                You will need to manually manage your bots based on market conditions.
              </p>
            </div>
            <div className="flex justify-end gap-3 p-4 border-t border-slate-700">
              <button
                onClick={() => setShowConfirmDisable(false)}
                className="px-4 py-2 text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDisable}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg transition-colors"
              >
                Disable
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
