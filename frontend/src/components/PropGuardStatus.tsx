/**
 * PropGuard Status Widget
 *
 * Dashboard card for monitoring prop firm account safety:
 * - Current equity and drawdown percentages (color-coded)
 * - Kill switch status with manual kill/reset controls
 * - Daily/total drawdown progress bars
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  RefreshCw,
  AlertTriangle,
  Power,
  RotateCcw,
  TrendingDown,
  DollarSign,
  Clock,
  Activity,
} from 'lucide-react'
import { authFetch } from '../services/api'
import { Account } from '../contexts/AccountContext'

interface PropGuardState {
  account_id: number
  prop_firm: string
  status?: string
  message?: string
  initial_deposit?: number
  current_equity?: number
  current_equity_timestamp?: string
  daily_start_equity?: number
  daily_start_timestamp?: string
  daily_drawdown_pct?: number
  daily_drawdown_limit?: number
  total_drawdown_pct?: number
  total_drawdown_limit?: number
  daily_pnl?: number
  total_pnl?: number
  is_killed?: boolean
  kill_reason?: string
  kill_timestamp?: string
}

interface PropGuardStatusProps {
  account: Account
}

export function PropGuardStatus({ account }: PropGuardStatusProps) {
  const [state, setState] = useState<PropGuardState | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  const fetchStatus = useCallback(async () => {
    try {
      const response = await authFetch(`/api/propguard/${account.id}/status`)
      if (response.status === 404) {
        // PropGuard not initialized yet — show as not_initialized, not error
        setState(null)
        setError(null)
        return
      }
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Failed to fetch PropGuard status')
      }
      const data = await response.json()
      setState(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch status')
    } finally {
      setLoading(false)
    }
  }, [account.id])

  useEffect(() => {
    fetchStatus()
    // Refresh every 30 seconds
    const interval = setInterval(fetchStatus, 30000)
    return () => clearInterval(interval)
  }, [fetchStatus])

  const handleKill = async () => {
    if (!confirm(
      'EMERGENCY KILL SWITCH\n\n' +
      'This will:\n' +
      '- Block ALL new orders immediately\n' +
      '- Attempt to close all open positions\n' +
      '- Cancel all pending orders\n\n' +
      'Are you sure you want to activate the kill switch?'
    )) {
      return
    }

    setActionLoading(true)
    try {
      const response = await authFetch(`/api/propguard/${account.id}/kill`, {
        method: 'POST',
      })
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Failed to activate kill switch')
      }
      await fetchStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Kill switch failed')
    } finally {
      setActionLoading(false)
    }
  }

  const handleReset = async () => {
    if (!confirm(
      'Reset Kill Switch\n\n' +
      'This will re-enable trading for this account.\n' +
      'Daily P&L tracking will restart from current equity.\n\n' +
      'Make sure you have reviewed the situation before proceeding.'
    )) {
      return
    }

    setActionLoading(true)
    try {
      const response = await authFetch(`/api/propguard/${account.id}/reset`, {
        method: 'POST',
      })
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Failed to reset kill switch')
      }
      await fetchStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
        <div className="flex items-center justify-center">
          <RefreshCw className="w-5 h-5 text-slate-400 animate-spin" />
          <span className="ml-2 text-slate-400">Loading PropGuard status...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
        <div className="flex items-start gap-2">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-red-300">{error}</p>
            <button
              onClick={() => { setLoading(true); fetchStatus() }}
              className="text-xs text-blue-400 hover:text-blue-300 mt-1"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!state || state.status === 'not_initialized') {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
        <div className="flex items-center gap-2 mb-2">
          <Shield className="w-5 h-5 text-slate-400" />
          <h4 className="font-medium text-white">PropGuard</h4>
          <span className="px-1.5 py-0.5 text-[10px] font-medium bg-slate-500/20 text-slate-300 rounded uppercase">
            {account.prop_firm}
          </span>
        </div>
        <p className="text-sm text-slate-400">
          {state?.message || 'PropGuard state not yet initialized. Will start on next monitor cycle.'}
        </p>
      </div>
    )
  }

  const isKilled = state.is_killed
  const dailyPct = state.daily_drawdown_pct || 0
  const dailyLimit = state.daily_drawdown_limit || 4.5
  const totalPct = state.total_drawdown_pct || 0
  const totalLimit = state.total_drawdown_limit || 9.0

  // Color coding: green < 50% of limit, yellow 50-80%, red > 80%
  const getDrawdownColor = (pct: number, limit: number) => {
    const ratio = pct / limit
    if (ratio >= 0.8) return { bar: 'bg-red-500', text: 'text-red-400' }
    if (ratio >= 0.5) return { bar: 'bg-yellow-500', text: 'text-yellow-400' }
    return { bar: 'bg-green-500', text: 'text-green-400' }
  }

  const dailyColor = getDrawdownColor(dailyPct, dailyLimit)
  const totalColor = getDrawdownColor(totalPct, totalLimit)

  const formatCurrency = (value: number | undefined) => {
    if (value == null) return '--'
    return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  const formatPnl = (value: number | undefined) => {
    if (value == null) return '--'
    const prefix = value >= 0 ? '+' : ''
    return `${prefix}$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  const formatTimestamp = (ts: string | undefined) => {
    if (!ts) return '--'
    return new Date(ts).toLocaleString()
  }

  return (
    <div className={`bg-slate-800 rounded-lg border ${isKilled ? 'border-red-700' : 'border-slate-700'}`}>
      {/* Header */}
      <div className={`px-4 py-3 ${isKilled ? 'bg-red-900/30' : 'bg-slate-900'} border-b ${isKilled ? 'border-red-700' : 'border-slate-700'} rounded-t-lg`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {isKilled ? (
              <ShieldAlert className="w-5 h-5 text-red-400" />
            ) : (
              <ShieldCheck className="w-5 h-5 text-green-400" />
            )}
            <h4 className="font-medium text-white">PropGuard</h4>
            <span className="px-1.5 py-0.5 text-[10px] font-medium bg-purple-500/20 text-purple-300 rounded uppercase">
              {state.prop_firm}
            </span>
            {isKilled ? (
              <span className="px-2 py-0.5 text-[10px] font-bold bg-red-500/30 text-red-300 rounded-full animate-pulse">
                KILLED
              </span>
            ) : (
              <span className="px-2 py-0.5 text-[10px] font-medium bg-green-500/20 text-green-300 rounded-full">
                ACTIVE
              </span>
            )}
          </div>
          <button
            onClick={() => { setLoading(true); fetchStatus() }}
            className="p-1.5 hover:bg-slate-700 rounded transition-colors"
            title="Refresh status"
          >
            <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Kill reason banner */}
        {isKilled && state.kill_reason && (
          <div className="flex items-start gap-2 p-3 bg-red-900/20 border border-red-700/50 rounded-lg">
            <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-red-300 font-medium">Kill Reason</p>
              <p className="text-xs text-red-400 mt-0.5">{state.kill_reason}</p>
              {state.kill_timestamp && (
                <p className="text-xs text-slate-500 mt-1">
                  <Clock className="w-3 h-3 inline mr-1" />
                  {formatTimestamp(state.kill_timestamp)}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Equity Overview */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 bg-slate-900/50 rounded-lg">
            <div className="flex items-center gap-1.5 mb-1">
              <DollarSign className="w-3.5 h-3.5 text-blue-400" />
              <span className="text-xs text-slate-400">Current Equity</span>
            </div>
            <p className="text-lg font-bold text-white">
              {formatCurrency(state.current_equity)}
            </p>
            {state.current_equity_timestamp && (
              <p className="text-[10px] text-slate-500 mt-0.5">
                {formatTimestamp(state.current_equity_timestamp)}
              </p>
            )}
          </div>
          <div className="p-3 bg-slate-900/50 rounded-lg">
            <div className="flex items-center gap-1.5 mb-1">
              <DollarSign className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-xs text-slate-400">Initial Deposit</span>
            </div>
            <p className="text-lg font-bold text-white">
              {formatCurrency(state.initial_deposit)}
            </p>
          </div>
        </div>

        {/* Daily Drawdown */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <TrendingDown className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-xs text-slate-400">Daily Drawdown</span>
            </div>
            <span className={`text-sm font-mono font-bold ${dailyColor.text}`}>
              {dailyPct.toFixed(2)}% / {dailyLimit}%
            </span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-2">
            <div
              className={`${dailyColor.bar} h-2 rounded-full transition-all duration-500`}
              style={{ width: `${Math.min((dailyPct / dailyLimit) * 100, 100)}%` }}
            />
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-[10px] text-slate-500">
              Daily P&L: {formatPnl(state.daily_pnl)}
            </span>
            <span className="text-[10px] text-slate-500">
              Start: {formatCurrency(state.daily_start_equity)}
            </span>
          </div>
        </div>

        {/* Total Drawdown */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-xs text-slate-400">Total Drawdown</span>
            </div>
            <span className={`text-sm font-mono font-bold ${totalColor.text}`}>
              {totalPct.toFixed(2)}% / {totalLimit}%
            </span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-2">
            <div
              className={`${totalColor.bar} h-2 rounded-full transition-all duration-500`}
              style={{ width: `${Math.min((totalPct / totalLimit) * 100, 100)}%` }}
            />
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-[10px] text-slate-500">
              Total P&L: {formatPnl(state.total_pnl)}
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2 pt-2 border-t border-slate-700">
          {isKilled ? (
            <button
              onClick={handleReset}
              disabled={actionLoading}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              {actionLoading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <RotateCcw className="w-4 h-4" />
              )}
              Reset Kill Switch
            </button>
          ) : (
            <button
              onClick={handleKill}
              disabled={actionLoading}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              {actionLoading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Power className="w-4 h-4" />
              )}
              Emergency Kill
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default PropGuardStatus
