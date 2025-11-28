import { useQuery, useMutation } from '@tanstack/react-query'
import { settingsApi } from '../services/api'
import { useState, useEffect } from 'react'
import { Save, AlertCircle, CheckCircle } from 'lucide-react'
import type { Settings as SettingsType } from '../types'
import { AccountsManagement } from '../components/AccountsManagement'
import { AddAccountModal } from '../components/AddAccountModal'

export default function Settings() {
  const [showAddAccountModal, setShowAddAccountModal] = useState(false)
  const [formData, setFormData] = useState<SettingsType | null>(null)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle')

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
  })

  useEffect(() => {
    if (settings) {
      setFormData(settings)
    }
  }, [settings])

  const saveMutation = useMutation({
    mutationFn: settingsApi.update,
    onSuccess: () => {
      setSaveStatus('success')
      setTimeout(() => setSaveStatus('idle'), 3000)
    },
    onError: () => {
      setSaveStatus('error')
      setTimeout(() => setSaveStatus('idle'), 3000)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (formData) {
      saveMutation.mutate(formData)
    }
  }

  const handleChange = (field: keyof SettingsType, value: number | string) => {
    if (formData) {
      setFormData({ ...formData, [field]: value })
    }
  }

  if (isLoading || !formData) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-slate-400">Loading settings...</p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold">Settings</h2>
        {saveStatus === 'success' && (
          <div className="flex items-center space-x-2 text-green-400">
            <CheckCircle className="w-5 h-5" />
            <span>Settings saved successfully</span>
          </div>
        )}
        {saveStatus === 'error' && (
          <div className="flex items-center space-x-2 text-red-400">
            <AlertCircle className="w-5 h-5" />
            <span>Failed to save settings</span>
          </div>
        )}
      </div>

      {/* Accounts Management Section */}
      <AccountsManagement onAddAccount={() => setShowAddAccountModal(true)} />

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Trading Parameters */}
        <div className="card">
          <h3 className="text-xl font-bold mb-4">Trading Parameters</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="label">
                Initial BTC Percentage
                <span className="text-slate-400 ml-2 text-xs">
                  (% of balance for first buy)
                </span>
              </label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="100"
                className="input"
                value={formData.initial_btc_percentage}
                onChange={(e) =>
                  handleChange('initial_btc_percentage', parseFloat(e.target.value))
                }
              />
            </div>

            <div>
              <label className="label">
                DCA Percentage
                <span className="text-slate-400 ml-2 text-xs">
                  (% of balance for DCA buys)
                </span>
              </label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="100"
                className="input"
                value={formData.dca_percentage}
                onChange={(e) => handleChange('dca_percentage', parseFloat(e.target.value))}
              />
            </div>

            <div>
              <label className="label">
                Max BTC Usage Percentage
                <span className="text-slate-400 ml-2 text-xs">
                  (max % of balance per position)
                </span>
              </label>
              <input
                type="number"
                step="1"
                min="1"
                max="100"
                className="input"
                value={formData.max_btc_usage_percentage}
                onChange={(e) =>
                  handleChange('max_btc_usage_percentage', parseFloat(e.target.value))
                }
              />
            </div>

            <div>
              <label className="label">
                Minimum Profit Percentage
                <span className="text-slate-400 ml-2 text-xs">
                  (min % profit to sell)
                </span>
              </label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="100"
                className="input"
                value={formData.min_profit_percentage}
                onChange={(e) =>
                  handleChange('min_profit_percentage', parseFloat(e.target.value))
                }
              />
            </div>
          </div>
        </div>

        {/* MACD Parameters */}
        <div className="card">
          <h3 className="text-xl font-bold mb-4">MACD Indicator Parameters</h3>

          <div className="mb-6">
            <label className="label">
              Candle Interval
              <span className="text-slate-400 ml-2 text-xs">
                (timeframe for MACD calculation and chart display)
              </span>
            </label>
            <select
              className="input"
              value={formData.candle_interval}
              onChange={(e) => handleChange('candle_interval', e.target.value)}
            >
              <option value="ONE_MINUTE">1 Minute</option>
              <option value="FIVE_MINUTE">5 Minutes</option>
              <option value="FIFTEEN_MINUTE">15 Minutes</option>
              <option value="THIRTY_MINUTE">30 Minutes</option>
              <option value="ONE_HOUR">1 Hour</option>
              <option value="TWO_HOUR">2 Hours</option>
              <option value="SIX_HOUR">6 Hours</option>
              <option value="ONE_DAY">1 Day</option>
            </select>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <label className="label">Fast Period</label>
              <input
                type="number"
                step="1"
                min="1"
                max="100"
                className="input"
                value={formData.macd_fast_period}
                onChange={(e) =>
                  handleChange('macd_fast_period', parseInt(e.target.value))
                }
              />
            </div>

            <div>
              <label className="label">Slow Period</label>
              <input
                type="number"
                step="1"
                min="1"
                max="100"
                className="input"
                value={formData.macd_slow_period}
                onChange={(e) =>
                  handleChange('macd_slow_period', parseInt(e.target.value))
                }
              />
            </div>

            <div>
              <label className="label">Signal Period</label>
              <input
                type="number"
                step="1"
                min="1"
                max="100"
                className="input"
                value={formData.macd_signal_period}
                onChange={(e) =>
                  handleChange('macd_signal_period', parseInt(e.target.value))
                }
              />
            </div>
          </div>
          <p className="text-sm text-slate-400 mt-4">
            <AlertCircle className="w-4 h-4 inline mr-1" />
            Changing MACD parameters will affect future signals. Standard values are 12, 26, 9.
          </p>
        </div>

        {/* Save Button */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saveMutation.isPending}
            className="btn-primary flex items-center space-x-2"
          >
            <Save className="w-4 h-4" />
            <span>{saveMutation.isPending ? 'Saving...' : 'Save Settings'}</span>
          </button>
        </div>
      </form>

      {/* Add Account Modal */}
      <AddAccountModal
        isOpen={showAddAccountModal}
        onClose={() => setShowAddAccountModal(false)}
      />
    </div>
  )
}
