import { useState, useEffect } from 'react'
import { X, Plus, Pencil, Trash2 } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reportsApi } from '../../services/api'
import type { ExpenseItem } from '../../types'

interface ExpenseItemsEditorProps {
  goalId: number
  expensePeriod: string
  currency: string
  onClose: () => void
}

const FREQUENCY_PILLS = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'biweekly', label: 'Every 2 Wks' },
  { value: 'semi_monthly', label: '2x/Month' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'semi_annual', label: '2x/Year' },
  { value: 'yearly', label: 'Annual' },
  { value: 'every_n_days', label: 'Custom' },
]

const FREQ_LABELS: Record<string, string> = {
  daily: '/day', weekly: '/week', biweekly: '/2wk',
  semi_monthly: '/2x mo', every_n_days: '/N days',
  monthly: '/mo', quarterly: '/qtr', semi_annual: '/6mo', yearly: '/yr',
}

export function ExpenseItemsEditor({ goalId, expensePeriod, currency, onClose }: ExpenseItemsEditorProps) {
  const queryClient = useQueryClient()
  const prefix = currency === 'BTC' ? '' : '$'
  const periodLabel = expensePeriod === 'weekly' ? '/wk' :
    expensePeriod === 'quarterly' ? '/qtr' :
    expensePeriod === 'yearly' ? '/yr' : '/mo'

  // Fetch items
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['expense-items', goalId],
    queryFn: () => reportsApi.getExpenseItems(goalId),
  })

  // Fetch categories
  const { data: categories = [] } = useQuery({
    queryKey: ['expense-categories'],
    queryFn: () => reportsApi.getExpenseCategories(),
  })

  // Form state
  const [editing, setEditing] = useState<ExpenseItem | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [category, setCategory] = useState('')
  const [customCategory, setCustomCategory] = useState('')
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [frequency, setFrequency] = useState('monthly')
  const [frequencyN, setFrequencyN] = useState('')
  const [dueDay, setDueDay] = useState('')
  const [dueDayLast, setDueDayLast] = useState(false)

  const resetForm = () => {
    setCategory('')
    setCustomCategory('')
    setName('')
    setAmount('')
    setFrequency('monthly')
    setFrequencyN('')
    setDueDay('')
    setDueDayLast(false)
    setEditing(null)
    setShowForm(false)
  }

  useEffect(() => {
    if (editing) {
      setCategory(categories.includes(editing.category) ? editing.category : '__custom__')
      setCustomCategory(categories.includes(editing.category) ? '' : editing.category)
      setName(editing.name)
      setAmount(String(editing.amount))
      setFrequency(editing.frequency)
      setFrequencyN(editing.frequency_n ? String(editing.frequency_n) : '')
      if (editing.due_day === -1) {
        setDueDayLast(true)
        setDueDay('')
      } else if (editing.due_day) {
        setDueDayLast(false)
        setDueDay(String(editing.due_day))
      } else {
        setDueDayLast(false)
        setDueDay('')
      }
      setShowForm(true)
    }
  }, [editing, categories])

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['expense-items', goalId] })
    queryClient.invalidateQueries({ queryKey: ['report-goals'] })
    queryClient.invalidateQueries({ queryKey: ['expense-categories'] })
  }

  const createItem = useMutation({
    mutationFn: (data: any) => reportsApi.createExpenseItem(goalId, data),
    onSuccess: () => { invalidate(); resetForm() },
  })
  const updateItem = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => reportsApi.updateExpenseItem(goalId, id, data),
    onSuccess: () => { invalidate(); resetForm() },
  })
  const deleteItem = useMutation({
    mutationFn: (id: number) => reportsApi.deleteExpenseItem(goalId, id),
    onSuccess: invalidate,
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const resolvedCategory = category === '__custom__' ? customCategory : category
    const data: any = {
      category: resolvedCategory,
      name,
      amount: parseFloat(amount),
      frequency,
    }
    if (frequency === 'every_n_days') {
      data.frequency_n = parseInt(frequencyN)
    }
    if (dueDayLast) {
      data.due_day = -1
    } else if (dueDay) {
      data.due_day = parseInt(dueDay)
    }
    if (editing) {
      updateItem.mutate({ id: editing.id, data })
    } else {
      createItem.mutate(data)
    }
  }

  const totalNormalized = items.reduce((sum, i) => sum + (i.normalized_amount || 0), 0)

  const pillBase = 'px-3 py-1.5 text-xs font-medium rounded-full border transition-colors'
  const pillActive = 'bg-blue-600 border-blue-500 text-white'
  const pillInactive = 'bg-slate-700 border-slate-600 text-slate-400 hover:border-slate-500'

  const expenseForm = (
    <form onSubmit={handleSubmit} className="bg-slate-700/30 rounded-lg p-4 space-y-3 border border-slate-600">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-slate-300">
          {editing ? 'Edit Expense' : 'New Expense'}
        </span>
        <button type="button" onClick={resetForm} className="text-slate-400 hover:text-white text-xs">
          Cancel
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Category</label>
          <select
            value={category}
            onChange={e => setCategory(e.target.value)}
            required
            className="w-full px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-white focus:outline-none focus:border-blue-500"
          >
            <option value="">Select...</option>
            {categories.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
            <option value="__custom__">Custom...</option>
          </select>
          {category === '__custom__' && (
            <input
              type="text"
              value={customCategory}
              onChange={e => setCustomCategory(e.target.value)}
              placeholder="Category name"
              required
              className="w-full mt-1 px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          )}
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Netflix"
            required
            className="w-full px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {/* Amount on its own row */}
      <div>
        <label className="block text-xs text-slate-400 mb-1">Amount ({currency})</label>
        <input
          type="number"
          step={currency === 'BTC' ? '0.00000001' : '0.01'}
          value={amount}
          onChange={e => setAmount(e.target.value)}
          required
          min="0"
          className="w-full px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-white focus:outline-none focus:border-blue-500"
        />
      </div>

      {/* Frequency pills */}
      <div>
        <label className="block text-xs text-slate-400 mb-1.5">Frequency</label>
        <div className="flex flex-wrap gap-1.5">
          {FREQUENCY_PILLS.map(o => (
            <button
              key={o.value}
              type="button"
              onClick={() => setFrequency(o.value)}
              className={`${pillBase} ${frequency === o.value ? pillActive : pillInactive}`}
            >
              {o.label}
            </button>
          ))}
        </div>
        {frequency === 'every_n_days' && (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-xs text-slate-400">Every</span>
            <input
              type="number"
              value={frequencyN}
              onChange={e => setFrequencyN(e.target.value)}
              required
              min="1"
              className="w-20 px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-white focus:outline-none focus:border-blue-500"
            />
            <span className="text-xs text-slate-400">days</span>
          </div>
        )}
      </div>

      {/* Due day */}
      <div>
        <label className="block text-xs text-slate-400 mb-1.5">Due Day (optional)</label>
        <div className="flex items-center gap-3">
          <input
            type="number"
            value={dueDay}
            onChange={e => setDueDay(e.target.value)}
            min="1"
            max="31"
            disabled={dueDayLast}
            placeholder="1-31"
            className="w-20 px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 disabled:opacity-40"
          />
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={dueDayLast}
              onChange={e => { setDueDayLast(e.target.checked); if (e.target.checked) setDueDay('') }}
              className="rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500 focus:ring-offset-0"
            />
            <span className="text-xs text-slate-400">Last day of month</span>
          </label>
        </div>
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={createItem.isPending || updateItem.isPending || !name || !amount || (!category || (category === '__custom__' && !customCategory))}
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors"
        >
          {(createItem.isPending || updateItem.isPending) ? 'Saving...' : editing ? 'Update' : 'Add'}
        </button>
      </div>
    </form>
  )

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="w-full max-w-2xl bg-slate-800 rounded-lg shadow-2xl border border-slate-700 max-h-[85vh] flex flex-col relative">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-white">Manage Expenses</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Item list */}
          {isLoading ? (
            <div className="text-center py-4 text-slate-400">Loading...</div>
          ) : items.length === 0 ? (
            <div className="text-center py-6 text-slate-500">
              No expense items yet. Add your first expense below.
            </div>
          ) : (
            <div className="space-y-2">
              {items.map(item => (
                <div key={item.id}
                  className="flex items-center justify-between p-3 bg-slate-700/50 rounded-lg border border-slate-600">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-600 text-slate-300">
                        {item.category}
                      </span>
                      <span className="font-medium text-white truncate">{item.name}</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                      <span>{prefix}{item.amount.toLocaleString()}{FREQ_LABELS[item.frequency] || ''}</span>
                      {item.frequency === 'every_n_days' && item.frequency_n && (
                        <span>(every {item.frequency_n} days)</span>
                      )}
                      {item.due_day != null && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-600/50 text-slate-300 text-[10px]">
                          Due {item.due_day === -1 ? 'last' : `${item.due_day}${item.due_day === 1 || item.due_day === 21 || item.due_day === 31 ? 'st' : item.due_day === 2 || item.due_day === 22 ? 'nd' : item.due_day === 3 || item.due_day === 23 ? 'rd' : 'th'}`}
                        </span>
                      )}
                      <span className="text-slate-500">|</span>
                      <span className="text-blue-400">
                        {prefix}{(item.normalized_amount || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}{periodLabel}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-2">
                    <button
                      onClick={() => setEditing(item)}
                      className="p-1.5 text-slate-400 hover:text-white transition-colors"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => { if (confirm('Delete this expense?')) deleteItem.mutate(item.id) }}
                      className="p-1.5 text-slate-400 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Total */}
          {items.length > 0 && (
            <div className="flex justify-between items-center px-3 py-2 bg-slate-700 rounded-lg">
              <span className="text-sm text-slate-300 font-medium">Total ({expensePeriod})</span>
              <span className="text-sm text-white font-semibold">
                {prefix}{totalNormalized.toLocaleString(undefined, { maximumFractionDigits: 2 })} {currency}
              </span>
            </div>
          )}

          {/* Add button (only when form overlay is NOT showing) */}
          {!showForm && (
            <button
              onClick={() => { resetForm(); setShowForm(true) }}
              className="w-full py-2 border border-dashed border-slate-600 rounded-lg text-slate-400 hover:text-white hover:border-slate-500 transition-colors flex items-center justify-center gap-2 text-sm"
            >
              <Plus className="w-4 h-4" /> Add Expense
            </button>
          )}
        </div>

        {/* Form overlay — renders on top of the list */}
        {showForm && (
          <div className="absolute inset-0 bg-black/60 rounded-lg flex items-center justify-center p-6 z-10">
            <div className="w-full max-w-lg">
              {expenseForm}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
