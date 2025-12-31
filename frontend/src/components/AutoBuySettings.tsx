/**
 * Auto-Buy BTC Settings Component
 *
 * Allows users to configure automatic BTC purchases from stablecoins
 * when balances exceed configurable minimums.
 */

import { useState, useEffect } from 'react'
import { AlertTriangle, DollarSign, Clock, TrendingUp, Save } from 'lucide-react'
import { autoBuyApi, type AutoBuySettings as AutoBuySettingsType, botsApi } from '../services/api'
import type { Bot } from '../types'

interface Account {
  id: number
  name: string
  type: string
  exchange?: string
}

interface AutoBuySettingsProps {
  accounts: Account[]
}

export function AutoBuySettings({ accounts }: AutoBuySettingsProps) {
  const [settings, setSettings] = useState<Record<number, AutoBuySettingsType>>({})
  const [bots, setBots] = useState<Bot[]>([])
  const [saving, setSaving] = useState<number | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Only show CEX accounts
  const cexAccounts = accounts.filter(a => a.type === 'cex')

  useEffect(() => {
    // Load settings for all accounts
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
      botsApi.getAll()
    ]).then(([accountSettings, botsData]) => {
      const settingsMap: Record<number, AutoBuySettingsType> = {}
      accountSettings.forEach(({ accountId, data }) => {
        if (data) {
          settingsMap[accountId] = data
        }
      })
      setSettings(settingsMap)
      setBots(botsData)
    })
  }, [])

  const handleSave = async (accountId: number) => {
    setSaving(accountId)
    setMessage(null)

    try {
      const updated = await autoBuyApi.updateSettings(accountId, settings[accountId])
      setSettings(prev => ({ ...prev, [accountId]: updated }))
      setMessage({ type: 'success', text: `Settings saved for ${cexAccounts.find(a => a.id === accountId)?.name}` })
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save settings' })
    } finally {
      setSaving(null)
    }
  }

  const updateAccountSettings = (accountId: number, updates: Partial<AutoBuySettingsType>) => {
    setSettings(prev => ({
      ...prev,
      [accountId]: { ...prev[accountId], ...updates }
    }))
  }

  const hasStablecoinBots = (accountId: number): boolean => {
    return bots.some(bot => {
      if (bot.account_id !== accountId) return false

      // Extract quote currency from product_id (e.g., "BTC-USD" -> "USD")
      const quoteCurrency = bot.product_id?.split('-')[1]
      return quoteCurrency && ['USD', 'USDC', 'USDT'].includes(quoteCurrency)
    })
  }

  if (cexAccounts.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <h2 className="text-xl font-semibold text-white mb-4">Auto-Buy BTC</h2>
        <p className="text-slate-400">No CEX accounts available. Add a Coinbase account to use auto-buy.</p>
      </div>
    )
  }

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white">Auto-Buy BTC</h2>
          <p className="text-sm text-slate-400 mt-1">
            Automatically convert stablecoins to BTC when balances exceed minimums
          </p>
        </div>
      </div>

      {message && (
        <div className={`mb-4 p-3 rounded ${
          message.type === 'success' ? 'bg-green-900/30 border border-green-700 text-green-400' : 'bg-red-900/30 border border-red-700 text-red-400'
        }`}>
          {message.text}
        </div>
      )}

      <div className="space-y-6">
        {cexAccounts.map(account => {
          const accountSettings = settings[account.id]
          if (!accountSettings) return null

          const hasWarning = hasStablecoinBots(account.id)

          return (
            <div key={account.id} className="bg-slate-700/50 rounded-lg p-4 border border-slate-600">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-medium text-white">{account.name}</h3>
                <label className="flex items-center gap-2 cursor-pointer">
                  <span className="text-sm text-slate-400">
                    {accountSettings.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                  <div className="relative">
                    <input
                      type="checkbox"
                      checked={accountSettings.enabled}
                      onChange={(e) => updateAccountSettings(account.id, { enabled: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
                  </div>
                </label>
              </div>

              {hasWarning && accountSettings.enabled && (
                <div className="bg-yellow-900/30 border border-yellow-700 rounded p-3 mb-4">
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={18} className="text-yellow-400 mt-0.5 flex-shrink-0" />
                    <div className="text-sm text-yellow-300">
                      <strong>Warning:</strong> This account has bots trading USD/USDC/USDT pairs.
                      Auto-buying BTC may interfere with bot operations by converting their quote currency.
                    </div>
                  </div>
                </div>
              )}

              {accountSettings.enabled && (
                <div className="space-y-4">
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
                        value={accountSettings.check_interval_minutes}
                        onChange={(e) => updateAccountSettings(account.id, {
                          check_interval_minutes: parseInt(e.target.value) || 5
                        })}
                        className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        <TrendingUp size={14} className="inline mr-1" />
                        Order Type
                      </label>
                      <select
                        value={accountSettings.order_type}
                        onChange={(e) => updateAccountSettings(account.id, { order_type: e.target.value })}
                        className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                      >
                        <option value="market">Market (Immediate)</option>
                        <option value="limit">Limit (Auto-Repriced)</option>
                      </select>
                    </div>
                  </div>

                  {/* Stablecoin Settings */}
                  <div className="space-y-3">
                    <h4 className="text-sm font-semibold text-slate-300">
                      <DollarSign size={14} className="inline mr-1" />
                      Stablecoins
                    </h4>

                    {/* USD */}
                    <div className="flex items-center gap-4 bg-slate-800/50 p-3 rounded">
                      <label className="flex items-center gap-2 cursor-pointer flex-shrink-0">
                        <input
                          type="checkbox"
                          checked={accountSettings.usd_enabled}
                          onChange={(e) => updateAccountSettings(account.id, { usd_enabled: e.target.checked })}
                          className="w-4 h-4"
                        />
                        <span className="text-white font-medium">USD</span>
                      </label>
                      <div className="flex items-center gap-2 flex-1">
                        <span className="text-slate-400 text-sm">Min:</span>
                        <input
                          type="number"
                          min="1"
                          step="1"
                          disabled={!accountSettings.usd_enabled}
                          value={accountSettings.usd_min}
                          onChange={(e) => updateAccountSettings(account.id, {
                            usd_min: parseFloat(e.target.value) || 10
                          })}
                          className={`w-24 px-2 py-1 rounded border text-sm ${
                            accountSettings.usd_enabled
                              ? 'bg-slate-700 text-white border-slate-600'
                              : 'bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed'
                          }`}
                        />
                        <span className="text-slate-400 text-sm">USD</span>
                      </div>
                    </div>

                    {/* USDC */}
                    <div className="flex items-center gap-4 bg-slate-800/50 p-3 rounded">
                      <label className="flex items-center gap-2 cursor-pointer flex-shrink-0">
                        <input
                          type="checkbox"
                          checked={accountSettings.usdc_enabled}
                          onChange={(e) => updateAccountSettings(account.id, { usdc_enabled: e.target.checked })}
                          className="w-4 h-4"
                        />
                        <span className="text-white font-medium">USDC</span>
                      </label>
                      <div className="flex items-center gap-2 flex-1">
                        <span className="text-slate-400 text-sm">Min:</span>
                        <input
                          type="number"
                          min="1"
                          step="1"
                          disabled={!accountSettings.usdc_enabled}
                          value={accountSettings.usdc_min}
                          onChange={(e) => updateAccountSettings(account.id, {
                            usdc_min: parseFloat(e.target.value) || 10
                          })}
                          className={`w-24 px-2 py-1 rounded border text-sm ${
                            accountSettings.usdc_enabled
                              ? 'bg-slate-700 text-white border-slate-600'
                              : 'bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed'
                          }`}
                        />
                        <span className="text-slate-400 text-sm">USDC</span>
                      </div>
                    </div>

                    {/* USDT */}
                    <div className="flex items-center gap-4 bg-slate-800/50 p-3 rounded">
                      <label className="flex items-center gap-2 cursor-pointer flex-shrink-0">
                        <input
                          type="checkbox"
                          checked={accountSettings.usdt_enabled}
                          onChange={(e) => updateAccountSettings(account.id, { usdt_enabled: e.target.checked })}
                          className="w-4 h-4"
                        />
                        <span className="text-white font-medium">USDT</span>
                      </label>
                      <div className="flex items-center gap-2 flex-1">
                        <span className="text-slate-400 text-sm">Min:</span>
                        <input
                          type="number"
                          min="1"
                          step="1"
                          disabled={!accountSettings.usdt_enabled}
                          value={accountSettings.usdt_min}
                          onChange={(e) => updateAccountSettings(account.id, {
                            usdt_min: parseFloat(e.target.value) || 10
                          })}
                          className={`w-24 px-2 py-1 rounded border text-sm ${
                            accountSettings.usdt_enabled
                              ? 'bg-slate-700 text-white border-slate-600'
                              : 'bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed'
                          }`}
                        />
                        <span className="text-slate-400 text-sm">USDT</span>
                      </div>
                    </div>
                  </div>

                  {/* Save Button */}
                  <button
                    onClick={() => handleSave(account.id)}
                    disabled={saving === account.id}
                    className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white px-4 py-2 rounded flex items-center justify-center gap-2"
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
