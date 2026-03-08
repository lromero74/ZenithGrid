/**
 * Portfolio Management Component
 *
 * Combined settings for Auto-Buy BTC and Portfolio Rebalancing.
 * These features are mutually exclusive — enabling one disables the other.
 * A 3-way mode selector lets users pick: Off, Auto-Buy BTC, or Rebalancing.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Clock, Save, RefreshCw, AlertTriangle,
  DollarSign, TrendingUp, PieChart as PieChartIcon, BarChart3, Briefcase,
} from 'lucide-react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import {
  autoBuyApi, rebalanceApi, botsApi,
  type AutoBuySettings, type RebalanceSettings, type RebalanceStatus,
} from '../services/api'
import { usePermission } from '../hooks/usePermission'
import type { Bot } from '../types'

interface Account {
  id: number
  name: string
  type: string
  exchange?: string
}

interface PortfolioManagementProps {
  accounts: Account[]
}

type PortfolioMode = 'off' | 'autobuy' | 'rebalance'

// ─── Rebalance constants ─────────────────────────────────────────────────────

interface CurrencySlider {
  key: 'target_usd_pct' | 'target_btc_pct' | 'target_eth_pct' | 'target_usdc_pct'
  label: string
  color: string
  bgColor: string
}

const CURRENCIES: CurrencySlider[] = [
  { key: 'target_usd_pct', label: 'USD', color: 'text-green-400', bgColor: 'bg-green-500' },
  { key: 'target_btc_pct', label: 'BTC', color: 'text-orange-400', bgColor: 'bg-orange-500' },
  { key: 'target_eth_pct', label: 'ETH', color: 'text-blue-400', bgColor: 'bg-blue-500' },
  { key: 'target_usdc_pct', label: 'USDC', color: 'text-cyan-400', bgColor: 'bg-cyan-500' },
]

const CURRENCY_HEX: Record<string, string> = {
  USD: '#22c55e', BTC: '#f97316', ETH: '#3b82f6', USDC: '#06b6d4',
}

const MIN_BALANCE_CONFIG: Record<string, { key: keyof RebalanceSettings; step: string; placeholder: string }> = {
  USD: { key: 'min_balance_usd', step: '1', placeholder: '0.00' },
  BTC: { key: 'min_balance_btc', step: '0.001', placeholder: '0.000' },
  ETH: { key: 'min_balance_eth', step: '0.01', placeholder: '0.00' },
  USDC: { key: 'min_balance_usdc', step: '1', placeholder: '0.00' },
}

const INTERVAL_OPTIONS = [
  { value: 15, label: '15 min' },
  { value: 30, label: '30 min' },
  { value: 60, label: '1 hour' },
  { value: 120, label: '2 hours' },
  { value: 240, label: '4 hours' },
]

// ─── Mode button config ──────────────────────────────────────────────────────

const MODE_OPTIONS: { value: PortfolioMode; label: string; description: string }[] = [
  { value: 'off', label: 'Off', description: 'No automatic portfolio management' },
  { value: 'autobuy', label: 'Auto-Buy BTC', description: 'Convert idle stablecoins to BTC' },
  { value: 'rebalance', label: 'Rebalancing', description: 'Maintain target allocations' },
]

// ─── Component ───────────────────────────────────────────────────────────────

export function PortfolioManagement({ accounts }: PortfolioManagementProps) {
  const canWrite = usePermission('accounts', 'write')
  const [autoBuySettings, setAutoBuySettings] = useState<Record<number, AutoBuySettings>>({})
  const [rebalanceSettings, setRebalanceSettings] = useState<Record<number, RebalanceSettings>>({})
  const [statuses, setStatuses] = useState<Record<number, RebalanceStatus>>({})
  const [bots, setBots] = useState<Bot[]>([])
  const [saving, setSaving] = useState<number | null>(null)
  const [loadingStatus, setLoadingStatus] = useState<number | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [chartView, setChartView] = useState<'pie' | 'bar'>('bar')

  const cexAccounts = accounts.filter(a => a.type === 'cex')

  // Load all settings on mount
  useEffect(() => {
    if (cexAccounts.length === 0) return

    Promise.all([
      Promise.all(cexAccounts.map(async (account) => {
        try {
          const data = await autoBuyApi.getSettings(account.id)
          return { accountId: account.id, data }
        } catch (err) {
          console.error(`Failed to load auto-buy settings for account ${account.id}:`, err)
          return { accountId: account.id, data: null }
        }
      })),
      Promise.all(cexAccounts.map(async (account) => {
        try {
          const data = await rebalanceApi.getSettings(account.id)
          return { accountId: account.id, data }
        } catch (err) {
          console.error(`Failed to load rebalance settings for account ${account.id}:`, err)
          return { accountId: account.id, data: null }
        }
      })),
      botsApi.getAll(),
    ]).then(([abResults, rbResults, botsData]) => {
      const abMap: Record<number, AutoBuySettings> = {}
      abResults.forEach(({ accountId, data }) => { if (data) abMap[accountId] = data })
      setAutoBuySettings(abMap)

      const rbMap: Record<number, RebalanceSettings> = {}
      rbResults.forEach(({ accountId, data }) => { if (data) rbMap[accountId] = data })
      setRebalanceSettings(rbMap)

      setBots(botsData)
    })
  }, [cexAccounts.length])

  // Derive current mode from loaded settings
  const getMode = (accountId: number): PortfolioMode => {
    const ab = autoBuySettings[accountId]
    const rb = rebalanceSettings[accountId]
    if (rb?.enabled) return 'rebalance'
    if (ab?.enabled) return 'autobuy'
    return 'off'
  }

  // Mode change handler
  const handleModeChange = async (accountId: number, newMode: PortfolioMode) => {
    const accountName = cexAccounts.find(a => a.id === accountId)?.name || 'Account'

    // Optimistic local update
    if (newMode === 'off') {
      setAutoBuySettings(prev => ({ ...prev, [accountId]: { ...prev[accountId], enabled: false } }))
      setRebalanceSettings(prev => ({ ...prev, [accountId]: { ...prev[accountId], enabled: false } }))
    } else if (newMode === 'autobuy') {
      setAutoBuySettings(prev => ({ ...prev, [accountId]: { ...prev[accountId], enabled: true } }))
      setRebalanceSettings(prev => ({ ...prev, [accountId]: { ...prev[accountId], enabled: false } }))
    } else {
      setAutoBuySettings(prev => ({ ...prev, [accountId]: { ...prev[accountId], enabled: false } }))
      setRebalanceSettings(prev => ({ ...prev, [accountId]: { ...prev[accountId], enabled: true } }))
    }

    try {
      if (newMode === 'off') {
        // Disable both
        const [updatedAb, updatedRb] = await Promise.all([
          autoBuyApi.updateSettings(accountId, { enabled: false }),
          rebalanceApi.updateSettings(accountId, { enabled: false }),
        ])
        setAutoBuySettings(prev => ({ ...prev, [accountId]: updatedAb }))
        setRebalanceSettings(prev => ({ ...prev, [accountId]: updatedRb }))
      } else if (newMode === 'autobuy') {
        // Enable auto-buy (backend auto-disables rebalancing)
        const updatedAb = await autoBuyApi.updateSettings(accountId, {
          ...autoBuySettings[accountId],
          enabled: true,
        })
        setAutoBuySettings(prev => ({ ...prev, [accountId]: updatedAb }))
        // Refresh rebalance to reflect disabled state
        const updatedRb = await rebalanceApi.getSettings(accountId)
        setRebalanceSettings(prev => ({ ...prev, [accountId]: updatedRb }))
      } else {
        // Enable rebalancing (backend auto-disables auto-buy)
        const updatedRb = await rebalanceApi.updateSettings(accountId, {
          ...rebalanceSettings[accountId],
          enabled: true,
        })
        setRebalanceSettings(prev => ({ ...prev, [accountId]: updatedRb }))
        // Refresh auto-buy to reflect disabled state
        const updatedAb = await autoBuyApi.getSettings(accountId)
        setAutoBuySettings(prev => ({ ...prev, [accountId]: updatedAb }))
      }
      const modeLabel = MODE_OPTIONS.find(m => m.value === newMode)?.label || newMode
      setMessage({ type: 'success', text: `${modeLabel} ${newMode === 'off' ? 'disabled' : 'enabled'} for ${accountName}` })
      setTimeout(() => setMessage(null), 3000)
    } catch (err) {
      // Revert — reload both
      try {
        const [ab, rb] = await Promise.all([
          autoBuyApi.getSettings(accountId),
          rebalanceApi.getSettings(accountId),
        ])
        setAutoBuySettings(prev => ({ ...prev, [accountId]: ab }))
        setRebalanceSettings(prev => ({ ...prev, [accountId]: rb }))
      } catch { /* ignore reload error */ }
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to change mode' })
    }
  }

  // ─── Auto-Buy handlers ──────────────────────────────────────────────────────

  const updateAB = (accountId: number, updates: Partial<AutoBuySettings>) => {
    setAutoBuySettings(prev => ({
      ...prev,
      [accountId]: { ...prev[accountId], ...updates },
    }))
  }

  const handleSaveAutoBuy = async (accountId: number) => {
    setSaving(accountId)
    setMessage(null)
    try {
      const updated = await autoBuyApi.updateSettings(accountId, autoBuySettings[accountId])
      setAutoBuySettings(prev => ({ ...prev, [accountId]: updated }))
      setMessage({ type: 'success', text: `Auto-buy settings saved for ${cexAccounts.find(a => a.id === accountId)?.name}` })
      setTimeout(() => setMessage(null), 3000)
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save' })
    } finally {
      setSaving(null)
    }
  }

  const hasStablecoinBots = (accountId: number): boolean => {
    return bots.some(bot => {
      if (bot.account_id !== accountId) return false
      const quoteCurrency = bot.product_id?.split('-')[1]
      return quoteCurrency && ['USD', 'USDC', 'USDT'].includes(quoteCurrency)
    })
  }

  // ─── Rebalance handlers ─────────────────────────────────────────────────────

  const updateRB = (accountId: number, updates: Partial<RebalanceSettings>) => {
    setRebalanceSettings(prev => ({
      ...prev,
      [accountId]: { ...prev[accountId], ...updates },
    }))
  }

  const handleSliderChange = (accountId: number, changedKey: CurrencySlider['key'], newValue: number) => {
    const current = rebalanceSettings[accountId]
    if (!current) return

    const others = CURRENCIES.filter(c => c.key !== changedKey)
    const otherTotal = others.reduce((sum, c) => sum + current[c.key], 0)
    const remaining = 100 - newValue

    const updated: Record<string, number> = { [changedKey]: newValue }

    if (otherTotal > 0) {
      let allocated = 0
      others.forEach((c, i) => {
        if (i === others.length - 1) {
          updated[c.key] = Math.max(0, remaining - allocated)
        } else {
          const share = Math.max(0, Math.round((current[c.key] / otherTotal) * remaining))
          updated[c.key] = share
          allocated += share
        }
      })
    } else {
      let allocated = 0
      others.forEach((c, i) => {
        if (i === others.length - 1) {
          updated[c.key] = Math.max(0, remaining - allocated)
        } else {
          const share = Math.max(0, Math.round(remaining / others.length))
          updated[c.key] = share
          allocated += share
        }
      })
    }

    setRebalanceSettings(prev => ({
      ...prev,
      [accountId]: { ...current, ...updated },
    }))
  }

  const handleSaveRebalance = async (accountId: number) => {
    setSaving(accountId)
    setMessage(null)
    try {
      const updated = await rebalanceApi.updateSettings(accountId, rebalanceSettings[accountId])
      setRebalanceSettings(prev => ({ ...prev, [accountId]: updated }))
      setMessage({ type: 'success', text: `Rebalance settings saved for ${cexAccounts.find(a => a.id === accountId)?.name}` })
      setTimeout(() => setMessage(null), 3000)
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save' })
    } finally {
      setSaving(null)
    }
  }

  const fetchStatus = useCallback(async (accountId: number) => {
    setLoadingStatus(accountId)
    try {
      const status = await rebalanceApi.getStatus(accountId)
      setStatuses(prev => ({ ...prev, [accountId]: status }))
    } catch (err) {
      console.error(`Failed to load rebalance status:`, err)
    } finally {
      setLoadingStatus(null)
    }
  }, [])

  // ─── Render ─────────────────────────────────────────────────────────────────

  if (cexAccounts.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <h2 className="text-xl font-semibold text-white flex items-center gap-2">
          <Briefcase size={20} />
          Portfolio Management
        </h2>
        <p className="text-slate-400 mt-2">No CEX accounts available. Add an exchange account to use portfolio management.</p>
      </div>
    )
  }

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-white flex items-center gap-2">
          <Briefcase size={20} />
          Portfolio Management
        </h2>
        <p className="text-sm text-slate-400 mt-1">
          Auto-buy BTC from stablecoins or maintain target allocations across currencies.
          Only one mode can be active at a time.
        </p>
      </div>

      {message && (
        <div className={`mb-4 p-3 rounded text-sm ${
          message.type === 'success'
            ? 'bg-green-900/30 border border-green-700 text-green-400'
            : 'bg-red-900/30 border border-red-700 text-red-400'
        }`}>
          {message.text}
        </div>
      )}

      <div className="space-y-6">
        {cexAccounts.map(account => {
          const ab = autoBuySettings[account.id]
          const rb = rebalanceSettings[account.id]
          if (!ab && !rb) return null

          const mode = getMode(account.id)
          const status = statuses[account.id]
          const hasWarning = hasStablecoinBots(account.id)

          return (
            <div key={account.id} className="bg-slate-700/50 rounded-lg p-4 border border-slate-600">
              {/* Account header */}
              <h3 className="text-lg font-medium text-white mb-3">{account.name}</h3>

              {/* Mode selector */}
              <div className="flex rounded-lg overflow-hidden border border-slate-600 mb-4">
                {MODE_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => canWrite && handleModeChange(account.id, opt.value)}
                    disabled={!canWrite}
                    className={`flex-1 px-3 py-2.5 text-sm font-medium transition-colors ${
                      mode === opt.value
                        ? opt.value === 'off'
                          ? 'bg-slate-600 text-white'
                          : 'bg-emerald-600 text-white'
                        : 'bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700'
                    } ${!canWrite ? 'cursor-not-allowed opacity-50' : ''}`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              {/* ───── Auto-Buy Panel ───── */}
              {mode === 'autobuy' && ab && (
                <div className="space-y-4">
                  {hasWarning && (
                    <div className="bg-yellow-900/30 border border-yellow-700 rounded p-3">
                      <div className="flex items-start gap-2">
                        <AlertTriangle size={18} className="text-yellow-400 mt-0.5 flex-shrink-0" />
                        <div className="text-sm text-yellow-300">
                          <strong>Warning:</strong> This account has bots trading USD/USDC/USDT pairs.
                          Auto-buying BTC may interfere with bot operations by converting their quote currency.
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Check Interval & Order Type */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        <Clock size={14} className="inline mr-1" />
                        Check Every (minutes)
                      </label>
                      <input
                        type="number"
                        min="1"
                        max="1440"
                        value={ab.check_interval_minutes}
                        onChange={(e) => updateAB(account.id, {
                          check_interval_minutes: parseInt(e.target.value) || 5,
                        })}
                        disabled={!canWrite}
                        className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        <TrendingUp size={14} className="inline mr-1" />
                        Order Type
                      </label>
                      <select
                        value={ab.order_type}
                        onChange={(e) => updateAB(account.id, { order_type: e.target.value })}
                        disabled={!canWrite}
                        className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                      >
                        <option value="market">Market (Immediate)</option>
                        <option value="limit">Limit (Auto-Repriced)</option>
                      </select>
                    </div>
                  </div>

                  {/* Per-stablecoin settings */}
                  <div className="space-y-3">
                    <h4 className="text-sm font-semibold text-slate-300">
                      <DollarSign size={14} className="inline mr-1" />
                      Stablecoins
                    </h4>

                    {([
                      { label: 'USD', enabledKey: 'usd_enabled' as const, minKey: 'usd_min' as const },
                      { label: 'USDC', enabledKey: 'usdc_enabled' as const, minKey: 'usdc_min' as const },
                      { label: 'USDT', enabledKey: 'usdt_enabled' as const, minKey: 'usdt_min' as const },
                    ]).map(coin => (
                      <div key={coin.label} className="flex items-center gap-4 bg-slate-800/50 p-3 rounded">
                        <label className={`flex items-center gap-2 flex-shrink-0 ${!canWrite ? 'cursor-not-allowed' : 'cursor-pointer'}`}>
                          <input
                            type="checkbox"
                            checked={ab[coin.enabledKey]}
                            onChange={(e) => updateAB(account.id, { [coin.enabledKey]: e.target.checked })}
                            disabled={!canWrite}
                            className="w-4 h-4"
                          />
                          <span className="text-white font-medium">{coin.label}</span>
                        </label>
                        <div className="flex items-center gap-2 flex-1">
                          <span className="text-slate-400 text-sm">Min:</span>
                          <input
                            type="number"
                            min="1"
                            step="1"
                            disabled={!canWrite || !ab[coin.enabledKey]}
                            value={ab[coin.minKey]}
                            onChange={(e) => updateAB(account.id, {
                              [coin.minKey]: parseFloat(e.target.value) || 10,
                            })}
                            className={`w-24 px-2 py-1 rounded border text-sm ${
                              canWrite && ab[coin.enabledKey]
                                ? 'bg-slate-700 text-white border-slate-600'
                                : 'bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed'
                            }`}
                          />
                          <span className="text-slate-400 text-sm">{coin.label}</span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Save */}
                  <button
                    onClick={() => handleSaveAutoBuy(account.id)}
                    disabled={saving === account.id || !canWrite}
                    className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white px-4 py-2 rounded flex items-center justify-center gap-2"
                  >
                    <Save size={16} />
                    {saving === account.id ? 'Saving...' : 'Save Settings'}
                  </button>
                </div>
              )}

              {/* ───── Rebalance Panel ───── */}
              {mode === 'rebalance' && rb && (
                <div className="space-y-5">
                  {/* Allocation bar */}
                  <div className="h-3 rounded-full overflow-hidden flex">
                    {CURRENCIES.map(({ key, bgColor }) => (
                      <div key={key} className={`${bgColor} transition-all`} style={{ width: `${rb[key]}%` }} />
                    ))}
                  </div>

                  {/* Sliders */}
                  <div className="space-y-3">
                    {CURRENCIES.map(({ key, label, color }) => (
                      <div key={key} className="flex items-center gap-3">
                        <span className={`w-10 text-sm font-medium ${color}`}>{label}</span>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          value={rb[key]}
                          onChange={(e) => handleSliderChange(account.id, key, parseInt(e.target.value))}
                          disabled={!canWrite}
                          className="flex-1 h-2 bg-slate-600 rounded-lg appearance-none cursor-pointer accent-slate-400"
                        />
                        <span className="w-12 text-right text-sm text-white font-mono">{rb[key]}%</span>
                      </div>
                    ))}
                  </div>

                  {/* Settings row */}
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        <Clock size={14} className="inline mr-1" />
                        Check Interval
                      </label>
                      <select
                        value={rb.check_interval_minutes}
                        onChange={(e) => updateRB(account.id, { check_interval_minutes: parseInt(e.target.value) })}
                        disabled={!canWrite}
                        className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 text-sm"
                      >
                        {INTERVAL_OPTIONS.map(opt => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Drift Threshold
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="range" min="1" max="10"
                          value={rb.drift_threshold_pct}
                          onChange={(e) => updateRB(account.id, { drift_threshold_pct: parseInt(e.target.value) })}
                          disabled={!canWrite}
                          className="flex-1 h-2 bg-slate-600 rounded-lg appearance-none cursor-pointer accent-slate-400"
                        />
                        <span className="text-sm text-white font-mono w-8 text-right">{rb.drift_threshold_pct}%</span>
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Min Trade Size
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="range" min="1" max="25"
                          value={rb.min_trade_pct}
                          onChange={(e) => updateRB(account.id, { min_trade_pct: parseInt(e.target.value) })}
                          disabled={!canWrite}
                          className="flex-1 h-2 bg-slate-600 rounded-lg appearance-none cursor-pointer accent-slate-400"
                        />
                        <span className="text-sm text-white font-mono w-8 text-right">{rb.min_trade_pct}%</span>
                      </div>
                    </div>
                  </div>

                  {/* Minimum Balance Reserves */}
                  <details className="group border-t border-slate-600 pt-3">
                    <summary className="cursor-pointer text-sm font-medium text-slate-300 hover:text-white select-none flex items-center gap-1">
                      <span className="text-xs text-slate-500 group-open:rotate-90 transition-transform">&#9654;</span>
                      Minimum Balance Reserves
                      <span className="text-xs text-slate-500 font-normal ml-1">(optional)</span>
                    </summary>
                    <p className="text-xs text-slate-500 mt-2 mb-3">
                      Maintain a minimum free balance per currency. The rebalancer will top up from other currencies if needed.
                    </p>
                    <div className="grid grid-cols-4 gap-3">
                      {CURRENCIES.map(c => {
                        const cfg = MIN_BALANCE_CONFIG[c.label]
                        if (!cfg) return null
                        return (
                          <div key={cfg.key}>
                            <label className={`block text-xs ${c.color} mb-1 font-medium`}>
                              Min {c.label}
                            </label>
                            <input
                              type="number"
                              value={(rb[cfg.key] as number) || ''}
                              onChange={(e) => {
                                const val = e.target.value === '' ? 0 : parseFloat(e.target.value)
                                updateRB(account.id, { [cfg.key]: val })
                              }}
                              step={cfg.step}
                              min="0"
                              placeholder={cfg.placeholder}
                              disabled={!canWrite}
                              className="w-full bg-slate-700 text-white px-2 py-1.5 rounded border border-slate-600 text-sm font-mono"
                            />
                          </div>
                        )
                      })}
                    </div>
                  </details>

                  {/* Current allocation status */}
                  <div className="bg-slate-800/50 rounded p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-slate-400 uppercase tracking-wide">Current Allocation</span>
                      <div className="flex items-center gap-2">
                        {status && (
                          <div className="flex bg-slate-700 rounded overflow-hidden">
                            <button
                              onClick={() => setChartView('bar')}
                              className={`p-1 ${chartView === 'bar' ? 'bg-slate-500 text-white' : 'text-slate-400 hover:text-white'}`}
                              title="Stacked bar"
                            >
                              <BarChart3 size={14} />
                            </button>
                            <button
                              onClick={() => setChartView('pie')}
                              className={`p-1 ${chartView === 'pie' ? 'bg-slate-500 text-white' : 'text-slate-400 hover:text-white'}`}
                              title="Pie chart"
                            >
                              <PieChartIcon size={14} />
                            </button>
                          </div>
                        )}
                        <button
                          onClick={() => fetchStatus(account.id)}
                          disabled={loadingStatus === account.id}
                          className="text-xs text-slate-400 hover:text-white flex items-center gap-1"
                        >
                          <RefreshCw size={12} className={loadingStatus === account.id ? 'animate-spin' : ''} />
                          Refresh
                        </button>
                      </div>
                    </div>
                    {status ? (
                      <div>
                        {chartView === 'pie' ? (
                          <div className="flex items-center justify-center gap-4">
                            <div className="w-[140px] h-[140px]">
                              <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                  <Pie
                                    data={CURRENCIES.map(c => ({
                                      name: c.label,
                                      value: status[`current_${c.label.toLowerCase()}_pct` as keyof RebalanceStatus] as number,
                                      color: CURRENCY_HEX[c.label],
                                    })).filter(d => d.value > 0)}
                                    cx="50%" cy="50%"
                                    innerRadius={35} outerRadius={60}
                                    paddingAngle={2} dataKey="value" strokeWidth={0}
                                  >
                                    {CURRENCIES.map(c => ({
                                      name: c.label,
                                      value: status[`current_${c.label.toLowerCase()}_pct` as keyof RebalanceStatus] as number,
                                      color: CURRENCY_HEX[c.label],
                                    })).filter(d => d.value > 0).map((entry, i) => (
                                      <Cell key={i} fill={entry.color} />
                                    ))}
                                  </Pie>
                                  <Tooltip
                                    contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: '6px' }}
                                    itemStyle={{ color: '#e2e8f0' }}
                                    formatter={(value: number) => [`${value.toFixed(1)}%`, '']}
                                    labelFormatter={(name: string) => name}
                                  />
                                </PieChart>
                              </ResponsiveContainer>
                            </div>
                            <div className="space-y-2">
                              {CURRENCIES.map(c => {
                                const currentPct = status[`current_${c.label.toLowerCase()}_pct` as keyof RebalanceStatus] as number
                                return (
                                  <div key={c.key} className="flex items-center gap-2">
                                    <div className={`w-3 h-3 rounded-full ${c.bgColor}`} />
                                    <span className={`${c.color} font-mono text-sm`}>{currentPct}%</span>
                                    <span className="text-xs text-slate-500">{c.label}</span>
                                    <span className="text-xs text-slate-600">target {rb[c.key]}%</span>
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        ) : (
                          <div className="space-y-2">
                            <div>
                              <div className="text-[10px] text-slate-500 mb-1">CURRENT</div>
                              <div className="h-7 rounded overflow-hidden flex relative">
                                {CURRENCIES.map(c => {
                                  const pct = status[`current_${c.label.toLowerCase()}_pct` as keyof RebalanceStatus] as number
                                  return pct > 0 ? (
                                    <div
                                      key={c.key}
                                      className={`${c.bgColor}/80 flex items-center justify-center text-[10px] font-mono text-white transition-all`}
                                      style={{ width: `${pct}%` }}
                                    >
                                      {pct >= 8 && `${pct}%`}
                                    </div>
                                  ) : null
                                })}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] text-slate-500 mb-1">TARGET</div>
                              <div className="h-7 rounded overflow-hidden flex">
                                {CURRENCIES.map(c => {
                                  const pct = rb[c.key]
                                  return pct > 0 ? (
                                    <div
                                      key={c.key}
                                      className="flex items-center justify-center text-[10px] font-mono transition-all"
                                      style={{
                                        width: `${pct}%`,
                                        backgroundColor: `${CURRENCY_HEX[c.label]}30`,
                                        borderColor: `${CURRENCY_HEX[c.label]}80`,
                                        color: `${CURRENCY_HEX[c.label]}cc`,
                                        border: `1px solid ${CURRENCY_HEX[c.label]}80`,
                                      }}
                                    >
                                      {pct >= 8 && `${pct}%`}
                                    </div>
                                  ) : null
                                })}
                              </div>
                            </div>
                            <div className="flex justify-center gap-4 mt-1">
                              {CURRENCIES.map(c => (
                                <span key={c.key} className="flex items-center gap-1 text-[10px]">
                                  <span className={`w-2.5 h-2.5 rounded-sm ${c.bgColor} inline-block`} />
                                  <span className="text-slate-400">{c.label}</span>
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        <div className="text-xs text-slate-500 text-center mt-2">
                          Total value: ${status.total_value_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-500 text-center py-2">
                        Click Refresh to see current allocation
                      </p>
                    )}
                  </div>

                  {/* Save */}
                  <button
                    onClick={() => handleSaveRebalance(account.id)}
                    disabled={saving === account.id || !canWrite}
                    className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white px-4 py-2 rounded flex items-center justify-center gap-2 text-sm"
                  >
                    <Save size={16} />
                    {saving === account.id ? 'Saving...' : 'Save Settings'}
                  </button>
                </div>
              )}

              {/* Off mode message */}
              {mode === 'off' && (
                <p className="text-sm text-slate-500 text-center py-4">
                  Select a mode above to configure automatic portfolio management.
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
