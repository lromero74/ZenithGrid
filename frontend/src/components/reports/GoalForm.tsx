import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import type { ReportGoal } from '../../types'

interface GoalFormProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: GoalFormData) => Promise<void>
  initialData?: ReportGoal | null
}

export interface GoalFormData {
  name: string
  target_type: 'balance' | 'profit' | 'both' | 'income'
  target_currency: 'USD' | 'BTC'
  target_value: number
  target_balance_value?: number | null
  target_profit_value?: number | null
  income_period?: 'daily' | 'weekly' | 'monthly' | 'yearly' | null
  lookback_days?: number | null
  time_horizon_months: number
}

const HORIZON_OPTIONS = [
  { value: 1, label: '1 Month' },
  { value: 3, label: '3 Months' },
  { value: 6, label: '6 Months' },
  { value: 12, label: '1 Year' },
  { value: 24, label: '2 Years' },
  { value: 60, label: '5 Years' },
  { value: 120, label: '10 Years' },
]

const INCOME_PERIOD_OPTIONS = [
  { value: 'daily', label: 'Per Day' },
  { value: 'weekly', label: 'Per Week' },
  { value: 'monthly', label: 'Per Month' },
  { value: 'yearly', label: 'Per Year' },
]

const LOOKBACK_OPTIONS = [
  { value: 0, label: 'All Time' },
  { value: 7, label: '7 Days' },
  { value: 14, label: '14 Days' },
  { value: 30, label: '30 Days' },
  { value: 90, label: '90 Days' },
  { value: 365, label: '365 Days' },
]

export function GoalForm({ isOpen, onClose, onSubmit, initialData }: GoalFormProps) {
  const [name, setName] = useState('')
  const [targetType, setTargetType] = useState<'balance' | 'profit' | 'both' | 'income'>('balance')
  const [targetCurrency, setTargetCurrency] = useState<'USD' | 'BTC'>('USD')
  const [targetValue, setTargetValue] = useState('')
  const [targetBalanceValue, setTargetBalanceValue] = useState('')
  const [targetProfitValue, setTargetProfitValue] = useState('')
  const [incomePeriod, setIncomePeriod] = useState<'daily' | 'weekly' | 'monthly' | 'yearly'>('monthly')
  const [lookbackDays, setLookbackDays] = useState(0)
  const [timeHorizon, setTimeHorizon] = useState(12)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (initialData) {
      setName(initialData.name)
      setTargetType(initialData.target_type)
      setTargetCurrency(initialData.target_currency)
      setTargetValue(String(initialData.target_value))
      setTargetBalanceValue(initialData.target_balance_value ? String(initialData.target_balance_value) : '')
      setTargetProfitValue(initialData.target_profit_value ? String(initialData.target_profit_value) : '')
      setIncomePeriod(initialData.income_period || 'monthly')
      setLookbackDays(initialData.lookback_days || 0)
      setTimeHorizon(initialData.time_horizon_months)
    } else {
      setName('')
      setTargetType('balance')
      setTargetCurrency('USD')
      setTargetValue('')
      setTargetBalanceValue('')
      setTargetProfitValue('')
      setIncomePeriod('monthly')
      setLookbackDays(0)
      setTimeHorizon(12)
    }
  }, [initialData, isOpen])

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await onSubmit({
        name,
        target_type: targetType,
        target_currency: targetCurrency,
        target_value: parseFloat(targetValue),
        target_balance_value: targetType === 'both' ? parseFloat(targetBalanceValue) || null : null,
        target_profit_value: targetType === 'both' ? parseFloat(targetProfitValue) || null : null,
        income_period: targetType === 'income' ? incomePeriod : null,
        lookback_days: targetType === 'income' && lookbackDays > 0 ? lookbackDays : null,
        time_horizon_months: timeHorizon,
      })
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="w-full max-w-md bg-slate-800 rounded-lg shadow-2xl border border-slate-700">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-white">
            {initialData ? 'Edit Goal' : 'Add Goal'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Reach 1 BTC"
              required
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Target Type</label>
              <select
                value={targetType}
                onChange={e => setTargetType(e.target.value as any)}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
              >
                <option value="balance">Balance</option>
                <option value="profit">Profit</option>
                <option value="both">Both</option>
                <option value="income">Income</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Currency</label>
              <select
                value={targetCurrency}
                onChange={e => setTargetCurrency(e.target.value as any)}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
              >
                <option value="USD">USD</option>
                <option value="BTC">BTC</option>
              </select>
            </div>
          </div>

          {targetType === 'income' ? (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Target Income ({targetCurrency}/{INCOME_PERIOD_OPTIONS.find(o => o.value === incomePeriod)?.label?.replace('Per ', '') || 'Month'})
                </label>
                <input
                  type="number"
                  step={targetCurrency === 'BTC' ? '0.00000001' : '0.01'}
                  value={targetValue}
                  onChange={e => setTargetValue(e.target.value)}
                  required
                  min="0"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">Income Period</label>
                  <select
                    value={incomePeriod}
                    onChange={e => setIncomePeriod(e.target.value as any)}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  >
                    {INCOME_PERIOD_OPTIONS.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">Lookback Window</label>
                  <select
                    value={lookbackDays}
                    onChange={e => setLookbackDays(Number(e.target.value))}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  >
                    {LOOKBACK_OPTIONS.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </>
          ) : targetType !== 'both' ? (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Target {targetType === 'balance' ? 'Balance' : 'Profit'} ({targetCurrency})
              </label>
              <input
                type="number"
                step={targetCurrency === 'BTC' ? '0.00000001' : '0.01'}
                value={targetValue}
                onChange={e => setTargetValue(e.target.value)}
                required
                min="0"
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Balance Target ({targetCurrency})
                </label>
                <input
                  type="number"
                  step={targetCurrency === 'BTC' ? '0.00000001' : '0.01'}
                  value={targetBalanceValue}
                  onChange={e => setTargetBalanceValue(e.target.value)}
                  required
                  min="0"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Profit Target ({targetCurrency})
                </label>
                <input
                  type="number"
                  step={targetCurrency === 'BTC' ? '0.00000001' : '0.01'}
                  value={targetProfitValue}
                  onChange={e => setTargetProfitValue(e.target.value)}
                  required
                  min="0"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Time Horizon</label>
            <select
              value={timeHorizon}
              onChange={e => setTimeHorizon(Number(e.target.value))}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
            >
              {HORIZON_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="flex justify-end space-x-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !name || !targetValue}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium rounded-lg transition-colors"
            >
              {submitting ? 'Saving...' : initialData ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
