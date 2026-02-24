import { useState, useEffect } from 'react'
import { X, Plus, Pencil, Trash2, GripVertical, ChevronsUp, ChevronsDown } from 'lucide-react'
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
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

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

const DAY_OF_WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const MONTH_NAMES = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

function ordinalDay(d: number): string {
  if (d === -1) return 'last'
  if (d >= 11 && d <= 13) return `${d}th`
  const s = { 1: 'st', 2: 'nd', 3: 'rd' }[d % 10] || 'th'
  return `${d}${s}`
}

function formatDueBadge(item: ExpenseItem): string | null {
  if (item.due_day == null) return null
  const freq = item.frequency
  if (freq === 'weekly' || freq === 'biweekly') {
    return `Due ${DAY_OF_WEEK[item.due_day] ?? '?'}`
  }
  const dayPart = ordinalDay(item.due_day)
  if ((freq === 'quarterly' || freq === 'semi_annual' || freq === 'yearly') && item.due_month) {
    return `Due ${MONTH_NAMES[item.due_month - 1]} ${dayPart}`
  }
  return `Due ${dayPart}`
}

// Sortable expense row for drag-to-reorder
function SortableExpenseRow({
  item, index, total, prefix, periodLabel,
  onEdit, onDelete, onMoveToTop, onMoveToBottom, onMoveTo,
}: {
  item: ExpenseItem
  index: number
  total: number
  prefix: string
  periodLabel: string
  onEdit: (item: ExpenseItem) => void
  onDelete: (id: number) => void
  onMoveToTop: (id: number) => void
  onMoveToBottom: (id: number) => void
  onMoveTo: (id: number, pos: number) => void
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.id })

  const [moveToInput, setMoveToInput] = useState('')
  const [showMoveTo, setShowMoveTo] = useState(false)

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  const badge = formatDueBadge(item)
  const position = index + 1

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-2 p-3 bg-slate-700/50 rounded-lg border border-slate-600 ${
        isDragging ? 'ring-2 ring-blue-500' : ''
      }`}
    >
      {/* Drag handle */}
      <div className="flex items-center gap-1 shrink-0">
        <button
          {...attributes}
          {...listeners}
          className="cursor-grab active:cursor-grabbing text-slate-500 hover:text-slate-300 touch-none"
          title="Drag to reorder"
        >
          <GripVertical className="w-4 h-4" />
        </button>
      </div>

      {/* Position badge */}
      <span className="text-[10px] font-mono text-slate-500 shrink-0 w-10 text-center"
        title={`Position ${position} of ${total}`}
      >
        #{position}/{total}
      </span>

      {/* Item details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs px-2 py-0.5 rounded bg-slate-600 text-slate-300">
            {item.category}
          </span>
          <span className="font-medium text-white truncate">{item.name}</span>
        </div>
        <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
          <span>
            {prefix}{item.amount.toLocaleString()}{FREQ_LABELS[item.frequency] || ''}
          </span>
          {item.frequency === 'every_n_days' && item.frequency_n && (
            <span>(every {item.frequency_n} days)</span>
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
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-0.5 ml-2 shrink-0">
        <button
          onClick={() => onMoveToTop(item.id)}
          disabled={index === 0}
          className="p-1 text-slate-500 hover:text-white disabled:opacity-30 transition-colors"
          title="Move to top"
        >
          <ChevronsUp className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => onMoveToBottom(item.id)}
          disabled={index === total - 1}
          className="p-1 text-slate-500 hover:text-white disabled:opacity-30 transition-colors"
          title="Move to bottom"
        >
          <ChevronsDown className="w-3.5 h-3.5" />
        </button>
        <div className="relative">
          <button
            onClick={() => setShowMoveTo(!showMoveTo)}
            className="p-1 text-slate-500 hover:text-white transition-colors text-[10px] font-mono"
            title="Move to position..."
          >
            #
          </button>
          {showMoveTo && (
            <div className="absolute right-0 top-full mt-1 z-20 bg-slate-700 border border-slate-600
              rounded p-1.5 flex items-center gap-1 shadow-lg">
              <input
                type="number"
                min="1"
                max={total}
                step="1"
                value={moveToInput}
                onChange={e => {
                  const v = e.target.value.replace(/[^0-9]/g, '')
                  setMoveToInput(v)
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter' && moveToInput) {
                    onMoveTo(item.id, parseInt(moveToInput))
                    setShowMoveTo(false)
                    setMoveToInput('')
                  } else if (e.key === 'Escape') {
                    setShowMoveTo(false)
                    setMoveToInput('')
                  }
                }}
                placeholder={`1-${total}`}
                autoFocus
                className="w-14 px-1.5 py-0.5 bg-slate-800 border border-slate-500 rounded text-xs
                  text-white focus:outline-none focus:border-blue-500 placeholder-slate-500"
              />
              <button
                onClick={() => {
                  if (moveToInput) {
                    onMoveTo(item.id, parseInt(moveToInput))
                    setShowMoveTo(false)
                    setMoveToInput('')
                  }
                }}
                className="px-1.5 py-0.5 bg-blue-600 text-white text-[10px] rounded hover:bg-blue-700"
              >
                Go
              </button>
            </div>
          )}
        </div>
        <button
          onClick={() => onEdit(item)}
          className="p-1.5 text-slate-400 hover:text-white transition-colors"
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => onDelete(item.id)}
          className="p-1.5 text-slate-400 hover:text-red-400 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}

export function ExpenseItemsEditor({ goalId, expensePeriod, currency, onClose }: ExpenseItemsEditorProps) {
  const queryClient = useQueryClient()
  const confirm = useConfirm()
  const prefix = currency === 'BTC' ? '' : '$'
  const periodLabel = expensePeriod === 'weekly' ? '/wk' :
    expensePeriod === 'quarterly' ? '/qtr' :
    expensePeriod === 'yearly' ? '/yr' : '/mo'

  // Fetch items
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['expense-items', goalId],
    queryFn: () => reportsApi.getExpenseItems(goalId),
  })

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
    // Due date — frequency-aware
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
          className={`w-full ${inputCls}`}
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
      </div>

      {/* Due date — frequency-aware */}
      {showDueSection && (
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

      {/* Login URL */}
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

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={createItem.isPending || updateItem.isPending || !name || !amount
            || (!category || (category === '__custom__' && !customCategory))}
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium
            rounded transition-colors"
        >
          {(createItem.isPending || updateItem.isPending) ? 'Saving...' : editing ? 'Update' : 'Add'}
        </button>
      </div>
    </form>
  )

  const itemsList = (
    <div className="space-y-2">
      {displayItems.map((item, index) => (
        <SortableExpenseRow
          key={item.id}
          item={item}
          index={index}
          total={displayItems.length}
          prefix={prefix}
          periodLabel={periodLabel}
          onEdit={setEditing}
          onDelete={async (id) => {
            if (await confirm({ title: 'Delete Expense', message: 'Delete this expense?', variant: 'danger', confirmLabel: 'Delete' }))
              deleteItem.mutate(id)
          }}
          onMoveToTop={handleMoveToTop}
          onMoveToBottom={handleMoveToBottom}
          onMoveTo={handleMoveTo}
        />
      ))}
    </div>
  )

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="w-full max-w-2xl bg-slate-800 rounded-lg shadow-2xl border border-slate-700 max-h-[85vh]
        flex flex-col relative">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div>
            <h3 className="text-lg font-semibold text-white">Manage Expenses</h3>
            {displayItems.length > 1 && (
              <p className="text-xs text-slate-500 mt-0.5">Drag to reorder or use controls to set priority</p>
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

          {/* Add button (only when form overlay is NOT showing) */}
          {!showForm && (
            <button
              onClick={() => { resetForm(); setShowForm(true) }}
              className="w-full py-2 border border-dashed border-slate-600 rounded-lg text-slate-400
                hover:text-white hover:border-slate-500 transition-colors flex items-center justify-center
                gap-2 text-sm"
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
