import { useState, useEffect, useMemo } from 'react'
import { X, Plus, ArrowUpNarrowWide, ArrowDownNarrowWide, PiggyBank } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reportsApi } from '../../services/api'
import { useConfirm } from '../../contexts/ConfirmContext'
import type { ExpenseItem } from '../../types'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { SortableExpenseRow } from './SortableExpenseRow'
import { FREQUENCY_PILLS, FREQ_LABELS, DAY_OF_WEEK, MONTH_NAMES, formatDueBadge } from './ExpenseItemsEditor.helpers'

interface ExpenseItemsEditorProps {
  goalId: number
  expensePeriod: string
  currency: string
  onClose: () => void
  readOnly?: boolean
}

export function ExpenseItemsEditor({ goalId, expensePeriod, currency, onClose, readOnly }: ExpenseItemsEditorProps) {
  const queryClient = useQueryClient()
  const confirm = useConfirm()
  const prefix = currency === 'BTC' ? '' : '$'
  const periodLabel = expensePeriod === 'weekly' ? '/wk' :
    expensePeriod === 'quarterly' ? '/qtr' :
    expensePeriod === 'yearly' ? '/yr' : '/mo'

  // Fetch items + coverage summary
  const { data: expenseData, isLoading } = useQuery({
    queryKey: ['expense-items', goalId],
    queryFn: () => reportsApi.getExpenseItems(goalId),
  })
  const items: ExpenseItem[] = useMemo(() => expenseData?.items ?? [], [expenseData])
  const coverageSummary: Record<string, unknown> = expenseData?.coverage_summary ?? {}

  // Local ordered list for optimistic drag reorder
  const [localItems, setLocalItems] = useState<ExpenseItem[]>([])
  useEffect(() => { setLocalItems(items) }, [items])

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
  const [dueMonth, setDueMonth] = useState('')
  const [dueDow, setDueDow] = useState('')  // day of week (0-6) for weekly/biweekly
  const [anchor, setAnchor] = useState('')  // start date for biweekly
  const [loginUrl, setLoginUrl] = useState('')
  const [amountMode, setAmountMode] = useState<'fixed' | 'percent_of_income'>('fixed')
  const [percentOfIncome, setPercentOfIncome] = useState('')
  const [percentBasis, setPercentBasis] = useState<'pre_tax' | 'post_tax'>('pre_tax')
  // Savings target state
  const [itemType, setItemType] = useState<'expense' | 'savings_target'>('expense')
  const [savingsTargetAmount, setSavingsTargetAmount] = useState('')
  const [savingsTargetDate, setSavingsTargetDate] = useState('')
  const [savingsCurrentBalance, setSavingsCurrentBalance] = useState('')
  const [savingsGrowthRate, setSavingsGrowthRate] = useState('')
  const [savingsIsRecurring, setSavingsIsRecurring] = useState(false)
  const [savingsRecurrenceMonths, setSavingsRecurrenceMonths] = useState('')

  const resolvedCategory = category === '__custom__' ? customCategory : category
  const isDonations = resolvedCategory.toLowerCase() === 'donations'
  const isPercentMode = isDonations && amountMode === 'percent_of_income'
  const isSavings = itemType === 'savings_target'

  const needsMonth = frequency === 'quarterly' || frequency === 'semi_annual' || frequency === 'yearly'
  const needsDow = frequency === 'weekly' || frequency === 'biweekly'
  const needsDom = frequency === 'monthly' || frequency === 'semi_monthly' || needsMonth
  const needsAnchor = frequency === 'biweekly' || frequency === 'every_n_days'
  const showDueSection = needsDow || needsDom

  const resetForm = () => {
    setCategory('')
    setCustomCategory('')
    setName('')
    setAmount('')
    setFrequency('monthly')
    setFrequencyN('')
    setDueDay('')
    setDueDayLast(false)
    setDueMonth('')
    setDueDow('')
    setAnchor('')
    setLoginUrl('')
    setAmountMode('fixed')
    setPercentOfIncome('')
    setPercentBasis('pre_tax')
    setItemType('expense')
    setSavingsTargetAmount('')
    setSavingsTargetDate('')
    setSavingsCurrentBalance('')
    setSavingsGrowthRate('8')
    setSavingsIsRecurring(false)
    setSavingsRecurrenceMonths('')
    setEditing(null)
    setShowForm(false)
  }

  useEffect(() => {
    if (editing) {
      setCategory(categories.includes(editing.category) ? editing.category : '__custom__')
      setCustomCategory(categories.includes(editing.category) ? '' : editing.category)
      setName(editing.name)
      setItemType(editing.item_type || 'expense')

      if (editing.item_type === 'savings_target') {
        // Savings target fields
        setSavingsTargetAmount(editing.savings_target_amount != null ? String(editing.savings_target_amount) : '')
        setSavingsTargetDate(editing.savings_target_date || '')
        setSavingsCurrentBalance(editing.savings_current_balance != null ? String(editing.savings_current_balance) : '0')
        setSavingsGrowthRate(editing.assumed_growth_rate_pct != null ? String(editing.assumed_growth_rate_pct) : '')
        setSavingsIsRecurring(editing.savings_is_recurring || false)
        setSavingsRecurrenceMonths(editing.savings_recurrence_months != null ? String(editing.savings_recurrence_months) : '')
        // Reset expense-only fields
        setAmount('0')
        setFrequency('monthly')
        setFrequencyN('')
        setDueDay('')
        setDueDayLast(false)
        setDueMonth('')
        setDueDow('')
        setAnchor('')
        setLoginUrl('')
        setAmountMode('fixed')
        setPercentOfIncome('')
        setPercentBasis('pre_tax')
      } else {
        // Expense fields
        setAmount(String(editing.amount))
        setFrequency(editing.frequency)
        setFrequencyN(editing.frequency_n ? String(editing.frequency_n) : '')
        setAnchor(editing.frequency_anchor || '')

        const isWeeklyType = editing.frequency === 'weekly' || editing.frequency === 'biweekly'
        if (isWeeklyType) {
          setDueDow(editing.due_day != null ? String(editing.due_day) : '')
          setDueDay('')
          setDueDayLast(false)
        } else if (editing.due_day === -1) {
          setDueDayLast(true)
          setDueDay('')
          setDueDow('')
        } else if (editing.due_day != null) {
          setDueDayLast(false)
          setDueDay(String(editing.due_day))
          setDueDow('')
        } else {
          setDueDayLast(false)
          setDueDay('')
          setDueDow('')
        }

        setDueMonth(editing.due_month ? String(editing.due_month) : '')
        setLoginUrl(editing.login_url || '')
        setAmountMode(editing.amount_mode || 'fixed')
        setPercentOfIncome(editing.percent_of_income ? String(editing.percent_of_income) : '')
        setPercentBasis(editing.percent_basis || 'pre_tax')
        // Reset savings fields
        setSavingsTargetAmount('')
        setSavingsTargetDate('')
        setSavingsCurrentBalance('')
        setSavingsGrowthRate('8')
        setSavingsIsRecurring(false)
        setSavingsRecurrenceMonths('')
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
    mutationFn: (data: Partial<ExpenseItem>) =>
      reportsApi.createExpenseItem(goalId, data as Parameters<typeof reportsApi.createExpenseItem>[1]),
    onSuccess: () => { invalidate(); resetForm() },
  })
  const updateItem = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ExpenseItem> }) => reportsApi.updateExpenseItem(goalId, id, data),
    onSuccess: () => { invalidate(); resetForm() },
  })
  const deleteItem = useMutation({
    mutationFn: (id: number) => reportsApi.deleteExpenseItem(goalId, id),
    onSuccess: invalidate,
  })
  const reorderItems = useMutation({
    mutationFn: (itemIds: number[]) => reportsApi.reorderExpenseItems(goalId, itemIds),
    onSuccess: invalidate,
  })

  // Persist a new order (optimistic local update + API call)
  const persistOrder = (newItems: ExpenseItem[]) => {
    setLocalItems(newItems)
    reorderItems.mutate(newItems.map(i => i.id))
  }

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = localItems.findIndex(i => i.id === active.id)
    const newIndex = localItems.findIndex(i => i.id === over.id)
    if (oldIndex === -1 || newIndex === -1) return
    persistOrder(arrayMove(localItems, oldIndex, newIndex))
  }

  const handleMoveToTop = (id: number) => {
    const idx = localItems.findIndex(i => i.id === id)
    if (idx <= 0) return
    persistOrder(arrayMove(localItems, idx, 0))
  }

  const handleMoveToBottom = (id: number) => {
    const idx = localItems.findIndex(i => i.id === id)
    if (idx === -1 || idx >= localItems.length - 1) return
    persistOrder(arrayMove(localItems, idx, localItems.length - 1))
  }

  const handleMoveTo = (id: number, position: number) => {
    const idx = localItems.findIndex(i => i.id === id)
    if (idx === -1) return
    const target = Math.max(0, Math.min(position - 1, localItems.length - 1))
    if (target === idx) return
    persistOrder(arrayMove(localItems, idx, target))
  }

  const handleSortAsc = () => {
    const sorted = [...localItems].sort((a, b) => (a.normalized_amount || 0) - (b.normalized_amount || 0))
    persistOrder(sorted)
  }

  const handleSortDesc = () => {
    const sorted = [...localItems].sort((a, b) => (b.normalized_amount || 0) - (a.normalized_amount || 0))
    persistOrder(sorted)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const finalCategory = category === '__custom__' ? customCategory : category

    if (isSavings) {
      const data: Partial<ExpenseItem> = {
        item_type: 'savings_target',
        category: finalCategory,
        name,
        savings_target_amount: parseFloat(savingsTargetAmount),
        savings_target_date: savingsTargetDate,
        savings_current_balance: savingsCurrentBalance ? parseFloat(savingsCurrentBalance) : 0,
        assumed_growth_rate_pct: savingsGrowthRate !== '' ? parseFloat(savingsGrowthRate) : null,
        savings_is_recurring: savingsIsRecurring,
      }
      if (savingsIsRecurring && savingsRecurrenceMonths) {
        data.savings_recurrence_months = parseInt(savingsRecurrenceMonths)
      }
      if (editing) {
        updateItem.mutate({ id: editing.id, data })
      } else {
        createItem.mutate(data)
      }
      return
    }

    const data: Partial<ExpenseItem> = {
      item_type: 'expense',
      category: finalCategory,
      name,
      amount: isPercentMode ? 0 : parseFloat(amount),
      frequency: isPercentMode ? 'monthly' : frequency,
      amount_mode: isPercentMode ? 'percent_of_income' : 'fixed',
    }
    if (isPercentMode) {
      data.percent_of_income = parseFloat(percentOfIncome)
      data.percent_basis = percentBasis
    }
    if (!isPercentMode && frequency === 'every_n_days') {
      data.frequency_n = parseInt(frequencyN)
    }
    // Due date — frequency-aware (only for fixed mode)
    if (!isPercentMode) {
      if (needsDow && dueDow !== '') {
        data.due_day = parseInt(dueDow)
      } else if (needsDom) {
        if (dueDayLast) {
          data.due_day = -1
        } else if (dueDay) {
          data.due_day = parseInt(dueDay)
        }
      }
      if (needsMonth && dueMonth) {
        data.due_month = parseInt(dueMonth)
      }
      if (needsAnchor && anchor) {
        data.frequency_anchor = anchor
      }
    }
    if (loginUrl.trim()) {
      data.login_url = loginUrl.trim()
    }
    if (editing) {
      updateItem.mutate({ id: editing.id, data })
    } else {
      createItem.mutate(data)
    }
  }

  const displayItems = localItems
  const totalNormalized = displayItems.reduce((sum, i) => sum + (i.normalized_amount || 0), 0)

  const pillBase = 'px-3 py-1.5 text-xs font-medium rounded-full border transition-colors'
  const pillActive = 'bg-blue-600 border-blue-500 text-white'
  const pillInactive = 'bg-slate-700 border-slate-600 text-slate-400 hover:border-slate-500'

  const inputCls = 'px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-white'
    + ' focus:outline-none focus:border-blue-500'

  const expenseForm = (
    <form onSubmit={handleSubmit} className="bg-slate-700/30 rounded-lg p-4 space-y-3 border border-slate-600">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-slate-300">
          {editing
            ? (isSavings ? 'Edit Savings Target' : 'Edit Expense')
            : (isSavings ? 'New Savings Target' : 'New Expense')}
        </span>
        <button type="button" onClick={resetForm} className="text-slate-400 hover:text-white text-xs">
          Cancel
        </button>
      </div>

      {/* Item type toggle */}
      {!editing && (
        <div>
          <label className="block text-xs text-slate-400 mb-1.5">Type</label>
          <div className="flex gap-1.5">
            <button
              type="button"
              onClick={() => setItemType('expense')}
              className={`${pillBase} ${itemType === 'expense' ? pillActive : pillInactive}`}
            >
              Expense
            </button>
            <button
              type="button"
              onClick={() => setItemType('savings_target')}
              className={`${pillBase} ${itemType === 'savings_target' ? 'bg-emerald-700 border-emerald-600 text-white' : pillInactive}`}
            >
              <PiggyBank className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
              Savings Target
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Category</label>
          <select
            value={category}
            onChange={e => setCategory(e.target.value)}
            required
            className={`w-full ${inputCls}`}
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
              className={`w-full mt-1 ${inputCls} placeholder-slate-500`}
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
            className={`w-full ${inputCls} placeholder-slate-500`}
          />
        </div>
      </div>

      {/* Savings target fields */}
      {isSavings && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Target Amount ({currency})</label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={savingsTargetAmount}
                onChange={e => setSavingsTargetAmount(e.target.value)}
                required
                placeholder="5000"
                className={`w-full ${inputCls} placeholder-slate-500`}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Target Date</label>
              <input
                type="date"
                value={savingsTargetDate}
                onChange={e => setSavingsTargetDate(e.target.value)}
                required
                className={`w-full ${inputCls}`}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Recurring rollover reserve ({currency})
                <span className="ml-1 text-[10px] text-slate-500">for recurring goals</span>
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={savingsCurrentBalance}
                onChange={e => setSavingsCurrentBalance(e.target.value)}
                placeholder="0"
                className={`w-full ${inputCls} placeholder-slate-500`}
              />
              <p className="text-[10px] text-slate-500 mt-1">
                Recurring: principal to preserve for the next cycle after withdrawal.
                Position in list determines what is dynamically reserved from your account balance.
              </p>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Annual Growth Rate (%)
                <span className="ml-1 text-[10px] text-emerald-400">optional override</span>
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={savingsGrowthRate}
                onChange={e => setSavingsGrowthRate(e.target.value)}
                placeholder="Auto (from account)"
                className={`w-full ${inputCls} placeholder-slate-500`}
              />
              <p className="text-[10px] text-slate-500 mt-1">
                Leave blank to use your account's live projected return
              </p>
            </div>
          </div>
          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={savingsIsRecurring}
                onChange={e => setSavingsIsRecurring(e.target.checked)}
                className="rounded border-slate-600 bg-slate-700 text-emerald-600 focus:ring-emerald-500 focus:ring-offset-0"
              />
              <span className="text-xs text-slate-300">Recurring goal (restarts after each cycle)</span>
            </label>
            {savingsIsRecurring && (
              <div className="flex items-center gap-2 mt-2 ml-6">
                <span className="text-xs text-slate-400">Repeat every</span>
                <input
                  type="number"
                  min="1"
                  max="360"
                  value={savingsRecurrenceMonths}
                  onChange={e => setSavingsRecurrenceMonths(e.target.value)}
                  placeholder="24"
                  required
                  className={`w-20 ${inputCls} placeholder-slate-500`}
                />
                <span className="text-xs text-slate-400">months</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Amount mode toggle — Donations only (expense mode) */}
      {!isSavings && isDonations && (
        <div>
          <label className="block text-xs text-slate-400 mb-1.5">Amount Mode</label>
          <div className="flex gap-1.5">
            <button
              type="button"
              onClick={() => setAmountMode('fixed')}
              className={`${pillBase} ${amountMode === 'fixed' ? pillActive : pillInactive}`}
            >
              Fixed Amount
            </button>
            <button
              type="button"
              onClick={() => setAmountMode('percent_of_income')}
              className={`${pillBase} ${amountMode === 'percent_of_income' ? pillActive : pillInactive}`}
            >
              % of Income
            </button>
          </div>
        </div>
      )}

      {/* Amount — fixed mode (expense only) */}
      {!isSavings && !isPercentMode && (
        <div>
          <label className="block text-xs text-slate-400 mb-1">Amount ({currency})</label>
          <input
            type="number"
            step={currency === 'BTC' ? '0.00000001' : '0.01'}
            value={amount}
            onChange={e => setAmount(e.target.value)}
            required
            min="0"
            className={`w-full ${inputCls}`}
          />
        </div>
      )}

      {/* Percent of income — percent mode (expense only) */}
      {!isSavings && isPercentMode && (
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Percentage of Income</label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="100"
                value={percentOfIncome}
                onChange={e => setPercentOfIncome(e.target.value)}
                required
                placeholder="10"
                className={`w-24 ${inputCls} placeholder-slate-500`}
              />
              <span className="text-sm text-slate-400">%</span>
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1.5">Income Basis</label>
            <div className="flex gap-1.5">
              <button
                type="button"
                onClick={() => setPercentBasis('pre_tax')}
                className={`${pillBase} ${percentBasis === 'pre_tax' ? pillActive : pillInactive}`}
              >
                Pre-Tax
              </button>
              <button
                type="button"
                onClick={() => setPercentBasis('post_tax')}
                className={`${pillBase} ${percentBasis === 'post_tax' ? pillActive : pillInactive}`}
              >
                Post-Tax
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Frequency pills — hidden in percent mode and savings mode */}
      {!isSavings && !isPercentMode && <div>
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
          <div className="mt-2 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Every</span>
              <input
                type="number"
                value={frequencyN}
                onChange={e => setFrequencyN(e.target.value)}
                required
                min="1"
                className={`w-20 ${inputCls}`}
              />
              <span className="text-xs text-slate-400">days</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Starting from</span>
              <input
                type="date"
                value={anchor}
                onChange={e => setAnchor(e.target.value)}
                className={`${inputCls} text-xs`}
              />
            </div>
          </div>
        )}
      </div>}

      {/* Due date — frequency-aware (expense only) */}
      {!isSavings && !isPercentMode && showDueSection && (
        <div>
          <label className="block text-xs text-slate-400 mb-1.5">
            Due Date (optional)
          </label>

          {/* Weekly / Biweekly: day of week pills */}
          {needsDow && (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-1.5">
                {DAY_OF_WEEK.map((d, i) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDueDow(dueDow === String(i) ? '' : String(i))}
                    className={`${pillBase} ${dueDow === String(i) ? pillActive : pillInactive}`}
                  >
                    {d}
                  </button>
                ))}
              </div>
              {needsAnchor && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400">Starting from</span>
                  <input
                    type="date"
                    value={anchor}
                    onChange={e => setAnchor(e.target.value)}
                    className={`${inputCls} text-xs`}
                  />
                </div>
              )}
            </div>
          )}

          {/* Monthly+ frequencies: day of month + optional month */}
          {needsDom && (
            <div className="flex items-center gap-3 flex-wrap">
              {needsMonth && (
                <select
                  value={dueMonth}
                  onChange={e => setDueMonth(e.target.value)}
                  className={`w-24 ${inputCls}`}
                >
                  <option value="">Month</option>
                  {MONTH_NAMES.map((m, i) => (
                    <option key={m} value={i + 1}>{m}</option>
                  ))}
                </select>
              )}
              <input
                type="number"
                value={dueDay}
                onChange={e => setDueDay(e.target.value)}
                min="1"
                max="31"
                disabled={dueDayLast}
                placeholder="Day"
                className={`w-20 ${inputCls} placeholder-slate-500 disabled:opacity-40`}
              />
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={dueDayLast}
                  onChange={e => { setDueDayLast(e.target.checked); if (e.target.checked) setDueDay('') }}
                  className="rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500 focus:ring-offset-0"
                />
                <span className="text-xs text-slate-400">Last day</span>
              </label>
            </div>
          )}
        </div>
      )}

      {/* Login URL — expense only */}
      {!isSavings && (
        <div>
          <label className="block text-xs text-slate-400 mb-1">Login / Payment URL (optional)</label>
          <input
            type="url"
            value={loginUrl}
            onChange={e => setLoginUrl(e.target.value)}
            placeholder="https://..."
            className={`w-full ${inputCls} placeholder-slate-500`}
          />
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={
            createItem.isPending || updateItem.isPending || !name
            || (!category || (category === '__custom__' && !customCategory))
            || (isSavings ? (!savingsTargetAmount || !savingsTargetDate) : (isPercentMode ? !percentOfIncome : !amount))
          }
          className={`px-4 py-1.5 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors ${
            isSavings ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-blue-600 hover:bg-blue-700'
          }`}
        >
          {(createItem.isPending || updateItem.isPending) ? 'Saving...' : editing ? 'Update' : 'Add'}
        </button>
      </div>
    </form>
  )

  const readOnlyRow = (item: ExpenseItem, index: number) => {
    const badge = formatDueBadge(item)
    const isSavingsItem = item.item_type === 'savings_target'
    return (
      <div key={item.id} className="flex items-center gap-2 p-3 bg-slate-700/50 rounded-lg border border-slate-600">
        <span className="text-[10px] font-mono text-slate-500 shrink-0 w-10 text-center">
          #{index + 1}/{displayItems.length}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {isSavingsItem ? (
              <span className="text-xs px-2 py-0.5 rounded bg-emerald-900/60 border border-emerald-700/50 text-emerald-300 flex items-center gap-1">
                <PiggyBank className="w-3 h-3" /> Savings
              </span>
            ) : (
              <span className="text-xs px-2 py-0.5 rounded bg-slate-600 text-slate-300">
                {item.category}
              </span>
            )}
            <span className="font-medium text-white truncate">{item.name}</span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-slate-400 flex-wrap">
            {isSavingsItem ? (
              <>
                <span>
                  Spend: {prefix}{(item.savings_target_amount || 0).toLocaleString()}
                  {item.gross_target != null && item.gross_target > (item.savings_target_amount || 0) + 0.01 && (
                    <span className="text-slate-500"> → accumulate: {prefix}{item.gross_target.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                  )}
                  {' '}by {item.savings_target_date || '?'}
                </span>
                {item.capital_required != null ? (
                  item.capital_gap === 0 ? (
                    <span className="text-emerald-400 font-medium">
                      {item.dynamic_reserved != null
                        ? `Reserved: ${prefix}${(item.dynamic_reserved).toLocaleString(undefined, { maximumFractionDigits: 0 })} ✓`
                        : 'Funded by growth'}
                    </span>
                  ) : (
                    <>
                      <span className="text-slate-500">|</span>
                      <span>Need: {prefix}{(item.capital_required).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                      {item.dynamic_reserved != null && item.dynamic_reserved > 0 && (
                        <span className="text-slate-400">
                          reserved: {prefix}{(item.dynamic_reserved).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </span>
                      )}
                      <span className="text-amber-400">gap: {prefix}{(item.capital_gap ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                    </>
                  )
                ) : (
                  item.savings_current_balance != null && item.savings_target_amount != null && item.savings_target_amount > 0 && (
                    <span className="text-emerald-400">
                      {Math.round((item.savings_current_balance / item.savings_target_amount) * 100)}% saved
                    </span>
                  )
                )}
                {item.effective_growth_rate_pct != null && item.effective_growth_rate_pct > 0 && (
                  <span className="text-[10px] text-slate-500">
                    @ {item.effective_growth_rate_pct.toFixed(1)}%/yr
                    {item.growth_rate_source === 'account' && <span className="text-emerald-500/70"> (auto)</span>}
                  </span>
                )}
              </>
            ) : (
              <>
                {item.amount_mode === 'percent_of_income' ? (
                  <span>
                    {item.percent_of_income}% {item.percent_basis === 'post_tax' ? 'post-tax' : 'pre-tax'}
                  </span>
                ) : (
                  <>
                    <span>
                      {prefix}{item.amount.toLocaleString()}{FREQ_LABELS[item.frequency] || ''}
                    </span>
                    {item.frequency === 'every_n_days' && item.frequency_n && (
                      <span>(every {item.frequency_n} days)</span>
                    )}
                  </>
                )}
                {badge && (
                  <span className="px-1.5 py-0.5 rounded bg-slate-600/50 text-slate-300 text-[10px]">
                    {badge}
                  </span>
                )}
                <span className="text-slate-500">|</span>
                <span className="text-blue-400">
                  {prefix}{(item.normalized_amount || 0).toLocaleString(
                    undefined, { maximumFractionDigits: 2 }
                  )}{periodLabel}
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    )
  }

  const itemsList = (
    <div className="space-y-2">
      {readOnly ? (
        displayItems.map((item, index) => readOnlyRow(item, index))
      ) : (
        displayItems.map((item, index) => (
          <SortableExpenseRow
            key={item.id}
            item={item}
            index={index}
            total={displayItems.length}
            prefix={prefix}
            periodLabel={periodLabel}
            onEdit={setEditing}
            onDelete={async (id) => {
              if (await confirm({ title: 'Delete Item', message: 'Delete this item?', variant: 'danger', confirmLabel: 'Delete' }))
                deleteItem.mutate(id)
            }}
            onMoveToTop={handleMoveToTop}
            onMoveToBottom={handleMoveToBottom}
            onMoveTo={handleMoveTo}
          />
        ))
      )}
    </div>
  )

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="w-full max-w-2xl bg-slate-800 rounded-lg shadow-2xl border border-slate-700 max-h-[85vh]
        flex flex-col relative">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div>
            <h3 className="text-lg font-semibold text-white">{readOnly ? 'Expense Items' : 'Manage Expenses & Savings'}</h3>
            {!readOnly && displayItems.length > 1 && (
              <div className="flex items-center gap-2 mt-1">
                <p className="text-xs text-slate-500">Sort:</p>
                <button
                  onClick={handleSortAsc}
                  className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded bg-slate-700 text-slate-400 hover:text-white hover:bg-slate-600 transition-colors"
                  title="Sort smallest first"
                >
                  <ArrowUpNarrowWide className="w-3 h-3" /> Low→High
                </button>
                <button
                  onClick={handleSortDesc}
                  className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded bg-slate-700 text-slate-400 hover:text-white hover:bg-slate-600 transition-colors"
                  title="Sort largest first"
                >
                  <ArrowDownNarrowWide className="w-3 h-3" /> High→Low
                </button>
                <span className="text-[10px] text-slate-600">|</span>
                <p className="text-[10px] text-slate-500">Drag to customize</p>
              </div>
            )}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Item list */}
          {isLoading ? (
            <div className="text-center py-4 text-slate-400">Loading...</div>
          ) : displayItems.length === 0 ? (
            <div className="text-center py-6 text-slate-500">
              No expense items yet. Add your first expense below.
            </div>
          ) : readOnly ? (
            itemsList
          ) : (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={displayItems.map(i => i.id)}
                strategy={verticalListSortingStrategy}
              >
                {itemsList}
              </SortableContext>
            </DndContext>
          )}

          {/* Total */}
          {displayItems.length > 0 && (
            <div className="flex justify-between items-center px-3 py-2 bg-slate-700 rounded-lg">
              <span className="text-sm text-slate-300 font-medium">Total ({expensePeriod})</span>
              <span className="text-sm text-white font-semibold">
                {prefix}{totalNormalized.toLocaleString(undefined, { maximumFractionDigits: 2 })} {currency}
              </span>
            </div>
          )}

          {/* Deposit coaching bar */}
          {displayItems.length > 0 && (() => {
            const cs = coverageSummary
            const balance = (cs.account_balance as number) ?? 0
            const annualPct = (cs.annual_return_pct as number) ?? 0
            const taxPct = (cs.tax_pct as number) ?? 0
            const period = (cs.period as string) ?? 'monthly'
            const periodDays = period === 'weekly' ? 7 : period === 'quarterly' ? 91 : period === 'yearly' ? 365 : 30
            const dailyRate = balance > 0 && annualPct > 0
              ? (Math.pow(1 + annualPct / 100, 1 / 365) - 1)
              : 0
            const afterTax = taxPct < 100 ? (1 - taxPct / 100) : 0
            const denom = dailyRate * periodDays * afterTax

            // Savings-gap path
            const savingsGapName = cs.first_gap_savings_name as string | undefined
            const savingsGap = (cs.first_gap_savings_cap_gap as number) ?? 0
            const blockedExpenseName = cs.first_blocked_after_savings_name as string | undefined
            const blockedExpenseAmt = (cs.first_blocked_after_savings_amount as number) ?? 0

            // Expense path
            const partialName = cs.partial_item_name as string | undefined
            const partialShortfall = (cs.partial_item_shortfall as number) ?? 0
            const nextName = cs.next_uncovered_name as string | undefined
            const nextAmt = (cs.next_uncovered_amount as number) ?? 0

            const lines: { text: string; icon: string }[] = []

            if (savingsGapName && savingsGap > 0 && !partialName) {
              // Savings target gap is blocking items below
              lines.push({
                icon: '🏦',
                text: `Deposit ${prefix}${savingsGap.toLocaleString(undefined, { maximumFractionDigits: 2 })} to fund ${savingsGapName}`
              })
              if (blockedExpenseName && blockedExpenseAmt > 0 && denom > 0) {
                const totalDeposit = savingsGap + blockedExpenseAmt / denom
                lines.push({
                  icon: '➕',
                  text: `Deposit ${prefix}${totalDeposit.toLocaleString(undefined, { maximumFractionDigits: 2 })} total to also cover ${blockedExpenseName}`
                })
              }
            } else if (partialName && partialShortfall > 0 && denom > 0) {
              const dep1 = partialShortfall / denom
              lines.push({
                icon: '💡',
                text: `Deposit ${prefix}${dep1.toLocaleString(undefined, { maximumFractionDigits: 2 })} to finish covering ${partialName}`
              })
              if (nextName && nextAmt > 0) {
                const dep2 = (partialShortfall + nextAmt) / denom
                lines.push({
                  icon: '➕',
                  text: `Deposit ${prefix}${dep2.toLocaleString(undefined, { maximumFractionDigits: 2 })} total to also cover ${nextName}`
                })
              }
            }

            if (lines.length === 0) return null
            return (
              <div className="bg-blue-950/40 border border-blue-800/40 rounded-lg px-3 py-2.5 space-y-1">
                <p className="text-[10px] font-semibold text-blue-400 uppercase tracking-wide mb-1">Deposit Coaching</p>
                {lines.map((l, i) => (
                  <p key={i} className="text-xs text-blue-200">
                    <span className="mr-1">{l.icon}</span>{l.text}
                  </p>
                ))}
              </div>
            )
          })()}

          {/* Add button (only when form overlay is NOT showing, hidden in read-only) */}
          {!readOnly && !showForm && (
            <button
              onClick={() => { resetForm(); setShowForm(true) }}
              className="w-full py-2 border border-dashed border-slate-600 rounded-lg text-slate-400
                hover:text-white hover:border-slate-500 transition-colors flex items-center justify-center
                gap-2 text-sm"
            >
              <Plus className="w-4 h-4" /> Add Expense or Savings Target
            </button>
          )}
        </div>

        {/* Form overlay — renders on top of the list (hidden in read-only) */}
        {!readOnly && showForm && (
          <div className="absolute inset-0 bg-black/85 rounded-lg flex items-center justify-center p-6 z-10">
            <div className="w-full max-w-lg">
              {expenseForm}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
