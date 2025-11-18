import { useQuery, useMutation } from '@tanstack/react-query'
import { settingsApi } from '../services/api'
import { useState, useEffect } from 'react'
import { Save, AlertCircle, CheckCircle, Key, TestTube, Trash2, Info, Eye, EyeOff } from 'lucide-react'
import type { Settings as SettingsType } from '../types'

export default function Settings() {
  const [formData, setFormData] = useState<SettingsType | null>(null)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle')
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle')
  const [testMessage, setTestMessage] = useState<string>('')
  const [showApiSecret, setShowApiSecret] = useState(false)

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

  const handleTestConnection = async () => {
    setTestStatus('testing')
    setTestMessage('')
    try {
      const response = await fetch('/api/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          coinbase_api_key: formData?.coinbase_api_key,
          coinbase_api_secret: formData?.coinbase_api_secret,
        }),
      })
      const data = await response.json()
      if (response.ok) {
        setTestStatus('success')
        setTestMessage(data.message || 'Connection successful!')
      } else {
        setTestStatus('error')
        setTestMessage(data.detail || 'Connection failed')
      }
    } catch (error) {
      setTestStatus('error')
      setTestMessage('Failed to connect to backend')
    }
    setTimeout(() => {
      setTestStatus('idle')
      setTestMessage('')
    }, 5000)
  }

  const handleClearKeys = () => {
    if (confirm('Are you sure you want to clear your API keys? This will stop the bot from trading.')) {
      setFormData({
        ...formData!,
        coinbase_api_key: '',
        coinbase_api_secret: ''
      })
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
    <div className="space-y-6">
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

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Coinbase API Credentials */}
        <div className="card border-2 border-blue-500/30">
          <div className="flex items-center space-x-2 mb-4">
            <Key className="w-5 h-5 text-blue-400" />
            <h3 className="text-xl font-bold">Coinbase API Credentials</h3>
          </div>

          <div className="bg-blue-950/30 border border-blue-500/30 rounded-lg p-4 mb-4">
            <div className="flex items-start space-x-2">
              <Info className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-slate-300">
                <p className="font-semibold mb-2">Required Coinbase API Key Permissions:</p>
                <ul className="list-disc list-inside space-y-1 text-slate-400">
                  <li><strong>View</strong> - Read account balances and transaction history</li>
                  <li><strong>Trade</strong> - Place buy and sell orders for ETH/BTC</li>
                </ul>
                <p className="mt-2 text-xs">
                  Create your API key at: <a href="https://www.coinbase.com/settings/api" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">coinbase.com/settings/api</a>
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="label">
                API Key
              </label>
              <input
                type="text"
                className="input font-mono text-sm"
                placeholder="Enter your Coinbase API Key"
                value={formData.coinbase_api_key || ''}
                onChange={(e) => handleChange('coinbase_api_key', e.target.value)}
              />
            </div>

            <div>
              <label className="label">
                API Secret
              </label>
              <div className="relative">
                {!showApiSecret && formData.coinbase_api_secret ? (
                  <div
                    onClick={() => setShowApiSecret(true)}
                    className="input font-mono text-sm pr-10 cursor-pointer select-none"
                    style={{ letterSpacing: '2px' }}
                  >
                    {'•'.repeat(formData.coinbase_api_secret.length)}
                  </div>
                ) : (
                  <input
                    type="text"
                    className="input font-mono text-sm pr-10"
                    placeholder="Enter your Coinbase API Secret"
                    value={formData.coinbase_api_secret || ''}
                    onChange={(e) => handleChange('coinbase_api_secret', e.target.value)}
                    onBlur={() => setShowApiSecret(false)}
                  />
                )}
                {formData.coinbase_api_secret && (
                  <button
                    type="button"
                    onClick={() => setShowApiSecret(!showApiSecret)}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-white transition-colors"
                  >
                    {showApiSecret ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                )}
              </div>
            </div>

            <div className="flex items-center space-x-3">
              <button
                type="button"
                onClick={handleTestConnection}
                disabled={!formData.coinbase_api_key || !formData.coinbase_api_secret || testStatus === 'testing'}
                className="btn-secondary flex items-center space-x-2"
              >
                <TestTube className="w-4 h-4" />
                <span>{testStatus === 'testing' ? 'Testing...' : 'Test Connection'}</span>
              </button>

              <button
                type="button"
                onClick={handleClearKeys}
                disabled={!formData.coinbase_api_key && !formData.coinbase_api_secret}
                className="btn-danger flex items-center space-x-2"
              >
                <Trash2 className="w-4 h-4" />
                <span>Clear Keys</span>
              </button>

              {testStatus === 'success' && (
                <div className="flex items-center space-x-2 text-green-400">
                  <CheckCircle className="w-4 h-4" />
                  <span className="text-sm">{testMessage}</span>
                </div>
              )}
              {testStatus === 'error' && (
                <div className="flex items-center space-x-2 text-red-400">
                  <AlertCircle className="w-4 h-4" />
                  <span className="text-sm">{testMessage}</span>
                </div>
              )}
            </div>
          </div>
        </div>

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
    </div>
  )
}
