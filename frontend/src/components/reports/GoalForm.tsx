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
  time_horizon_months: number
  target_date?: string | null
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

export function GoalForm({ isOpen, onClose, onSubmit, initialData }: GoalFormProps) {
  const [name, setName] = useState('')
  const [targetType, setTargetType] = useState<'balance' | 'profit' | 'both' | 'income'>('balance')
  const [targetCurrency, setTargetCurrency] = useState<'USD' | 'BTC'>('USD')
  const [targetValue, setTargetValue] = useState('')
  const [targetBalanceValue, setTargetBalanceValue] = useState('')
  const [targetProfitValue, setTargetProfitValue] = useState('')
  const [incomePeriod, setIncomePeriod] = useState<'daily' | 'weekly' | 'monthly' | 'yearly'>('monthly')
  const [timeHorizon, setTimeHorizon] = useState(12)
  const [dateMode, setDateMode] = useState<'horizon' | 'date'>('horizon')
  const [customDate, setCustomDate] = useState('')
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
      setTimeHorizon(initialData.time_horizon_months)

      // Detect if stored date matches a preset horizon
      const isPreset = HORIZON_OPTIONS.some(o => o.value === initialData.time_horizon_months)
      if (isPreset && initialData.start_date && initialData.target_date) {
        // Check if the target_date is roughly what the preset would produce
        const start = new Date(initialData.start_date)
        const expected = new Date(start)
        expected.setMonth(expected.getMonth() + initialData.time_horizon_months)
        const actual = new Date(initialData.target_date)
        const diffDays = Math.abs(actual.getTime() - expected.getTime()) / (1000 * 60 * 60 * 24)
        if (diffDays > 3) {
          // Custom date — doesn't match the preset
          setDateMode('date')
          setCustomDate(initialData.target_date.split('T')[0])
        } else {
          setDateMode('horizon')
          setCustomDate('')
        }
      } else if (!isPreset) {
        // Non-standard horizon months — must be custom date
        setDateMode('date')
        setCustomDate(initialData.target_date ? initialData.target_date.split('T')[0] : '')
      } else {
        setDateMode('horizon')
        setCustomDate('')
      }
    } else {
      setName('')
      setTargetType('balance')
      setTargetCurrency('USD')
      setTargetValue('')
      setTargetBalanceValue('')
      setTargetProfitValue('')
      setIncomePeriod('monthly')
      setTimeHorizon(12)
      setDateMode('horizon')
      setCustomDate('')
    }
  }, [initialData, isOpen])

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const formData: GoalFormData = {
        name,
        target_type: targetType,
        target_currency: targetCurrency,
        target_value: parseFloat(targetValue),
        target_balance_value: targetType === 'both' ? parseFloat(targetBalanceValue) || null : null,
        target_profit_value: targetType === 'both' ? parseFloat(targetProfitValue) || null : null,
        income_period: targetType === 'income' ? incomePeriod : null,
        time_horizon_months: timeHorizon,
      }

      if (dateMode === 'date' && customDate) {
        // Send ISO datetime string; back-compute a rough horizon for the required field
        formData.target_date = `${customDate}T23:59:59`
        const now = new Date()
        const target = new Date(customDate)
        const diffMonths = (target.getFullYear() - now.getFullYear()) * 12
          + (target.getMonth() - now.getMonth())
        formData.time_horizon_months = Math.max(diffMonths, 1)
      } else {
        formData.target_date = null
      }

      await onSubmit(formData)
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
                <p className="text-xs text-slate-500 mt-1">Lookback window is controlled by the report schedule</p>
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
            <div className="flex items-center gap-1 mb-2">
              <button
                type="button"
                onClick={() => setDateMode('horizon')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                  dateMode === 'horizon'
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-400 hover:text-white'
                }`}
              >
                Preset
              </button>
              <button
                type="button"
                onClick={() => setDateMode('date')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                  dateMode === 'date'
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-400 hover:text-white'
                }`}
              >
                Custom Date
              </button>
            </div>
            {dateMode === 'horizon' ? (
              <select
                value={timeHorizon}
                onChange={e => setTimeHorizon(Number(e.target.value))}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
              >
                {HORIZON_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            ) : (
              <input
                type="date"
                value={customDate}
                onChange={e => setCustomDate(e.target.value)}
                min={new Date(Date.now() + 86400000).toISOString().split('T')[0]}
                required
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500 [color-scheme:dark]"
              />
            )}
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
              disabled={submitting || !name || !targetValue || (dateMode === 'date' && !customDate)}
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
