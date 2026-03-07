/**
 * Portfolio Rebalance Settings Component
 *
 * Per-account target allocation settings for USD, BTC, and ETH.
 * Three linked sliders that always sum to 100%.
 */

import { useState, useEffect, useCallback } from 'react'
import { Scale, Clock, Save, RefreshCw } from 'lucide-react'
import { rebalanceApi, type RebalanceSettings as RebalanceSettingsType, type RebalanceStatus } from '../services/api'
import { usePermission } from '../hooks/usePermission'

interface Account {
  id: number
  name: string
  type: string
}

interface RebalanceSettingsProps {
  accounts: Account[]
}

interface CurrencySlider {
  key: 'target_usd_pct' | 'target_btc_pct' | 'target_eth_pct'
  label: string
  color: string
  bgColor: string
}

const CURRENCIES: CurrencySlider[] = [
  { key: 'target_usd_pct', label: 'USD', color: 'text-green-400', bgColor: 'bg-green-500' },
  { key: 'target_btc_pct', label: 'BTC', color: 'text-orange-400', bgColor: 'bg-orange-500' },
  { key: 'target_eth_pct', label: 'ETH', color: 'text-blue-400', bgColor: 'bg-blue-500' },
]

const INTERVAL_OPTIONS = [
  { value: 15, label: '15 min' },
  { value: 30, label: '30 min' },
  { value: 60, label: '1 hour' },
  { value: 120, label: '2 hours' },
  { value: 240, label: '4 hours' },
]

export function RebalanceSettings({ accounts }: RebalanceSettingsProps) {
  const canWrite = usePermission('accounts', 'write')
  const [settings, setSettings] = useState<Record<number, RebalanceSettingsType>>({})
  const [statuses, setStatuses] = useState<Record<number, RebalanceStatus>>({})
  const [saving, setSaving] = useState<number | null>(null)
  const [loadingStatus, setLoadingStatus] = useState<number | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const cexAccounts = accounts.filter(a => a.type === 'cex')

  useEffect(() => {
    if (cexAccounts.length === 0) return

    Promise.all(cexAccounts.map(async (account) => {
      try {
        const data = await rebalanceApi.getSettings(account.id)
        return { accountId: account.id, data }
      } catch (err) {
        console.error(`Failed to load rebalance settings for account ${account.id}:`, err)
        return { accountId: account.id, data: null }
      }
    })).then((results) => {
      const map: Record<number, RebalanceSettingsType> = {}
      results.forEach(({ accountId, data }) => {
        if (data) map[accountId] = data
      })
      setSettings(map)
    })
  }, [cexAccounts.length])

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

  const handleSliderChange = (accountId: number, changedKey: CurrencySlider['key'], newValue: number) => {
    const current = settings[accountId]
    if (!current) return

    const others = CURRENCIES.filter(c => c.key !== changedKey)
    const oldOther0 = current[others[0].key]
    const oldOther1 = current[others[1].key]
    const otherTotal = oldOther0 + oldOther1
    const remaining = 100 - newValue

    let newOther0: number
    let newOther1: number

    if (otherTotal > 0) {
      // Distribute remaining proportionally
      newOther0 = Math.round((oldOther0 / otherTotal) * remaining)
      newOther1 = remaining - newOther0
    } else {
      // Equal split
      newOther0 = Math.round(remaining / 2)
      newOther1 = remaining - newOther0
    }

    // Clamp to 0
    newOther0 = Math.max(0, newOther0)
    newOther1 = Math.max(0, newOther1)

    setSettings(prev => ({
      ...prev,
      [accountId]: {
        ...current,
        [changedKey]: newValue,
        [others[0].key]: newOther0,
        [others[1].key]: newOther1,
      }
    }))
  }

  const handleToggle = async (accountId: number, enabled: boolean) => {
    setSettings(prev => ({
      ...prev,
      [accountId]: { ...prev[accountId], enabled }
    }))

    try {
      const updated = await rebalanceApi.updateSettings(accountId, { enabled })
      setSettings(prev => ({ ...prev, [accountId]: updated }))
      const name = cexAccounts.find(a => a.id === accountId)?.name || 'Account'
      setMessage({ type: 'success', text: `Rebalancing ${enabled ? 'enabled' : 'disabled'} for ${name}` })
      setTimeout(() => setMessage(null), 3000)
    } catch (err) {
      setSettings(prev => ({
        ...prev,
        [accountId]: { ...prev[accountId], enabled: !enabled }
      }))
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to toggle' })
    }
  }

  const handleSave = async (accountId: number) => {
    setSaving(accountId)
    setMessage(null)

    try {
      const updated = await rebalanceApi.updateSettings(accountId, settings[accountId])
      setSettings(prev => ({ ...prev, [accountId]: updated }))
      setMessage({ type: 'success', text: `Rebalance settings saved for ${cexAccounts.find(a => a.id === accountId)?.name}` })
      setTimeout(() => setMessage(null), 3000)
    } catch (err) {
      const detail = err instanceof Error ? err.message : 'Failed to save'
      setMessage({ type: 'error', text: detail })
    } finally {
      setSaving(null)
    }
  }

  if (cexAccounts.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <h2 className="text-xl font-semibold text-white mb-4">Portfolio Rebalancing</h2>
        <p className="text-slate-400">No CEX accounts available.</p>
      </div>
    )
  }

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Scale size={20} />
            Portfolio Rebalancing
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Maintain target allocations across USD, BTC, and ETH per exchange account
          </p>
        </div>
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
          const s = settings[account.id]
          if (!s) return null

          const status = statuses[account.id]

          return (
            <div key={account.id} className="bg-slate-700/50 rounded-lg p-4 border border-slate-600">
              {/* Header with toggle */}
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-medium text-white">{account.name}</h3>
                <label className={`flex items-center gap-2 ${!canWrite ? 'cursor-not-allowed' : 'cursor-pointer'}`}>
                  <span className="text-sm text-slate-400">
                    {s.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                  <div className={`relative ${!canWrite ? 'opacity-50' : ''}`}>
                    <input
                      type="checkbox"
                      checked={s.enabled}
                      onChange={(e) => handleToggle(account.id, e.target.checked)}
                      disabled={!canWrite}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500" />
                  </div>
                </label>
              </div>

              {s.enabled && (
                <div className="space-y-5">
                  {/* Allocation bar */}
                  <div className="h-3 rounded-full overflow-hidden flex">
                    <div className="bg-green-500 transition-all" style={{ width: `${s.target_usd_pct}%` }} />
                    <div className="bg-orange-500 transition-all" style={{ width: `${s.target_btc_pct}%` }} />
                    <div className="bg-blue-500 transition-all" style={{ width: `${s.target_eth_pct}%` }} />
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
                          value={s[key]}
                          onChange={(e) => handleSliderChange(account.id, key, parseInt(e.target.value))}
                          disabled={!canWrite}
                          className="flex-1 h-2 bg-slate-600 rounded-lg appearance-none cursor-pointer accent-slate-400"
                        />
                        <span className="w-12 text-right text-sm text-white font-mono">
                          {s[key]}%
                        </span>
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
                        value={s.check_interval_minutes}
                        onChange={(e) => setSettings(prev => ({
                          ...prev,
                          [account.id]: { ...prev[account.id], check_interval_minutes: parseInt(e.target.value) }
                        }))}
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
                          type="range"
                          min="1"
                          max="10"
                          value={s.drift_threshold_pct}
                          onChange={(e) => setSettings(prev => ({
                            ...prev,
                            [account.id]: { ...prev[account.id], drift_threshold_pct: parseInt(e.target.value) }
                          }))}
                          disabled={!canWrite}
                          className="flex-1 h-2 bg-slate-600 rounded-lg appearance-none cursor-pointer accent-slate-400"
                        />
                        <span className="text-sm text-white font-mono w-8 text-right">
                          {s.drift_threshold_pct}%
                        </span>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Min Trade Size
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="range"
                          min="1"
                          max="25"
                          value={s.min_trade_pct}
                          onChange={(e) => setSettings(prev => ({
                            ...prev,
                            [account.id]: { ...prev[account.id], min_trade_pct: parseInt(e.target.value) }
                          }))}
                          disabled={!canWrite}
                          className="flex-1 h-2 bg-slate-600 rounded-lg appearance-none cursor-pointer accent-slate-400"
                        />
                        <span className="text-sm text-white font-mono w-8 text-right">
                          {s.min_trade_pct}%
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Current allocation status */}
                  <div className="bg-slate-800/50 rounded p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-slate-400 uppercase tracking-wide">Current Allocation</span>
                      <button
                        onClick={() => fetchStatus(account.id)}
                        disabled={loadingStatus === account.id}
                        className="text-xs text-slate-400 hover:text-white flex items-center gap-1"
                      >
                        <RefreshCw size={12} className={loadingStatus === account.id ? 'animate-spin' : ''} />
                        Refresh
                      </button>
                    </div>
                    {status ? (
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div>
                          <div className="text-green-400 text-lg font-mono">{status.current_usd_pct}%</div>
                          <div className="text-xs text-slate-500">USD</div>
                        </div>
                        <div>
                          <div className="text-orange-400 text-lg font-mono">{status.current_btc_pct}%</div>
                          <div className="text-xs text-slate-500">BTC</div>
                        </div>
                        <div>
                          <div className="text-blue-400 text-lg font-mono">{status.current_eth_pct}%</div>
                          <div className="text-xs text-slate-500">ETH</div>
                        </div>
                        <div className="col-span-3 text-xs text-slate-500 mt-1">
                          Total value: ${status.total_value_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-500 text-center py-2">
                        Click Refresh to see current allocation
                      </p>
                    )}
                  </div>

                  {/* Save button */}
                  <button
                    onClick={() => handleSave(account.id)}
                    disabled={saving === account.id || !canWrite}
                    className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white px-4 py-2 rounded flex items-center justify-center gap-2 text-sm"
                  >
                    <Save size={16} />
                    {saving === account.id ? 'Saving...' : 'Save Settings'}
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
