import { useState, useEffect } from 'react'
import { X, Plus, Trash2 } from 'lucide-react'
import type {
  ReportGoal, ReportSchedule, RecipientItem, ExperienceLevel,
  ScheduleType, PeriodWindow, LookbackUnit,
} from '../../types'

interface ScheduleFormProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: ScheduleFormData) => Promise<void>
  goals: ReportGoal[]
  initialData?: ReportSchedule | null
}

export interface ScheduleFormData {
  name: string
  schedule_type: ScheduleType
  schedule_days: number[] | null
  quarter_start_month: number | null
  period_window: PeriodWindow
  lookback_value: number | null
  lookback_unit: LookbackUnit | null
  account_id?: number | null
  recipients: RecipientItem[]
  ai_provider?: string | null
  goal_ids: number[]
  is_enabled: boolean
}

const SCHEDULE_TYPE_OPTIONS: { value: ScheduleType; label: string }[] = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'yearly', label: 'Yearly' },
]

const PERIOD_WINDOW_OPTIONS: { value: PeriodWindow; label: string; description: string }[] = [
  { value: 'full_prior', label: 'Full prior period', description: 'Complete previous week/month/quarter/year' },
  { value: 'wtd', label: 'WTD', description: 'Week to date' },
  { value: 'mtd', label: 'MTD', description: 'Month to date' },
  { value: 'qtd', label: 'QTD', description: 'Quarter to date' },
  { value: 'ytd', label: 'YTD', description: 'Year to date' },
  { value: 'trailing', label: 'Trailing', description: 'Rolling lookback window' },
]

const LOOKBACK_UNIT_OPTIONS: { value: LookbackUnit; label: string }[] = [
  { value: 'days', label: 'days' },
  { value: 'weeks', label: 'weeks' },
  { value: 'months', label: 'months' },
  { value: 'years', label: 'years' },
]

const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const MONTH_LABELS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

const AI_PROVIDERS = [
  { value: '', label: 'Default (first available)' },
  { value: 'claude', label: 'Claude (Anthropic)' },
  { value: 'openai', label: 'OpenAI (GPT)' },
  { value: 'gemini', label: 'Google Gemini' },
]

const LEVEL_OPTIONS: { value: ExperienceLevel; label: string; color: string }[] = [
  { value: 'beginner', label: 'Beginner', color: 'text-emerald-400 bg-emerald-900/40 border-emerald-700' },
  { value: 'comfortable', label: 'Comfortable', color: 'text-blue-400 bg-blue-900/40 border-blue-700' },
  { value: 'experienced', label: 'Experienced', color: 'text-purple-400 bg-purple-900/40 border-purple-700' },
]

function normalizeRecipients(raw: unknown[]): RecipientItem[] {
  if (!raw || !Array.isArray(raw)) return []
  return raw.map(item => {
    if (typeof item === 'string') {
      return { email: item, level: 'comfortable' as ExperienceLevel }
    }
    if (typeof item === 'object' && item !== null && 'email' in item) {
      const obj = item as Record<string, unknown>
      return {
        email: String(obj.email),
        level: (['beginner', 'comfortable', 'experienced'].includes(String(obj.level))
          ? String(obj.level) as ExperienceLevel
          : 'comfortable'),
      }
    }
    return { email: String(item), level: 'comfortable' as ExperienceLevel }
  })
}

export function ScheduleForm({ isOpen, onClose, onSubmit, goals, initialData }: ScheduleFormProps) {
  const [name, setName] = useState('')
  const [scheduleType, setScheduleType] = useState<ScheduleType>('weekly')
  const [scheduleDays, setScheduleDays] = useState<number[]>([0]) // Default Monday
  const [quarterStartMonth, setQuarterStartMonth] = useState(1)
  const [yearlyMonth, setYearlyMonth] = useState(1)
  const [yearlyDay, setYearlyDay] = useState(1)
  const [quarterDay, setQuarterDay] = useState(1)
  const [periodWindow, setPeriodWindow] = useState<PeriodWindow>('full_prior')
  const [lookbackValue, setLookbackValue] = useState<number>(7)
  const [lookbackUnit, setLookbackUnit] = useState<LookbackUnit>('days')
  const [recipients, setRecipients] = useState<RecipientItem[]>([])
  const [newRecipient, setNewRecipient] = useState('')
  const [newRecipientLevel, setNewRecipientLevel] = useState<ExperienceLevel>('comfortable')
  const [aiProvider, setAiProvider] = useState('')
  const [selectedGoalIds, setSelectedGoalIds] = useState<number[]>([])
  const [isEnabled, setIsEnabled] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (initialData) {
      setName(initialData.name)
      setScheduleType(initialData.schedule_type || 'weekly')
      setPeriodWindow(initialData.period_window || 'full_prior')
      setLookbackValue(initialData.lookback_value || 7)
      setLookbackUnit(initialData.lookback_unit || 'days')
      setQuarterStartMonth(initialData.quarter_start_month || 1)
      setRecipients(normalizeRecipients(initialData.recipients as unknown[]))
      setAiProvider(initialData.ai_provider || '')
      setSelectedGoalIds(initialData.goal_ids || [])
      setIsEnabled(initialData.is_enabled)

      // Parse schedule_days based on type
      const days = initialData.schedule_days || []
      const stype = initialData.schedule_type || 'weekly'
      if (stype === 'weekly') {
        setScheduleDays(days.length > 0 ? days : [0])
      } else if (stype === 'monthly') {
        setScheduleDays(days.length > 0 ? days : [1])
      } else if (stype === 'quarterly') {
        setQuarterDay(days.length > 0 ? days[0] : 1)
      } else if (stype === 'yearly') {
        setYearlyMonth(days.length >= 1 ? days[0] : 1)
        setYearlyDay(days.length >= 2 ? days[1] : 1)
      } else {
        setScheduleDays(days)
      }
    } else {
      setName('')
      setScheduleType('weekly')
      setScheduleDays([0])
      setQuarterStartMonth(1)
      setQuarterDay(1)
      setYearlyMonth(1)
      setYearlyDay(1)
      setPeriodWindow('full_prior')
      setLookbackValue(7)
      setLookbackUnit('days')
      setRecipients([])
      setNewRecipient('')
      setNewRecipientLevel('comfortable')
      setAiProvider('')
      setSelectedGoalIds([])
      setIsEnabled(true)
    }
  }, [initialData, isOpen])

  if (!isOpen) return null

  const addRecipient = () => {
    const email = newRecipient.trim()
    if (email && !recipients.some(r => r.email === email) && email.includes('@')) {
      setRecipients([...recipients, { email, level: newRecipientLevel }])
      setNewRecipient('')
    }
  }

  const removeRecipient = (email: string) => {
    setRecipients(recipients.filter(r => r.email !== email))
  }

  const toggleGoal = (goalId: number) => {
    setSelectedGoalIds(prev =>
      prev.includes(goalId) ? prev.filter(id => id !== goalId) : [...prev, goalId]
    )
  }

  const toggleWeekday = (day: number) => {
    setScheduleDays(prev => {
      if (prev.includes(day)) {
        // Don't allow deselecting the last day
        if (prev.length === 1) return prev
        return prev.filter(d => d !== day)
      }
      return [...prev, day].sort()
    })
  }

  const toggleMonthDay = (day: number) => {
    setScheduleDays(prev => {
      if (prev.includes(day)) {
        if (prev.length === 1) return prev
        return prev.filter(d => d !== day)
      }
      return [...prev, day].sort((a, b) => {
        // Sort -1 (last) after all positive numbers
        if (a === -1) return 1
        if (b === -1) return -1
        return a - b
      })
    })
  }

  // Build the schedule_days array for the API based on schedule type
  const getScheduleDaysForApi = (): number[] | null => {
    switch (scheduleType) {
      case 'daily': return null
      case 'weekly': return scheduleDays
      case 'monthly': return scheduleDays
      case 'quarterly': return [quarterDay]
      case 'yearly': return [yearlyMonth, yearlyDay]
      default: return null
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await onSubmit({
        name,
        schedule_type: scheduleType,
        schedule_days: getScheduleDaysForApi(),
        quarter_start_month: scheduleType === 'quarterly' ? quarterStartMonth : null,
        period_window: periodWindow,
        lookback_value: periodWindow === 'trailing' ? lookbackValue : null,
        lookback_unit: periodWindow === 'trailing' ? lookbackUnit : null,
        recipients,
        ai_provider: aiProvider || null,
        goal_ids: selectedGoalIds,
        is_enabled: isEnabled,
      })
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  const getLevelBadge = (level: ExperienceLevel) => {
    const opt = LEVEL_OPTIONS.find(o => o.value === level) || LEVEL_OPTIONS[1]
    return (
      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${opt.color}`}>
        {opt.label}
      </span>
    )
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="w-full max-w-lg bg-slate-800 rounded-lg shadow-2xl border border-slate-700 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-slate-700 sticky top-0 bg-slate-800 z-10">
          <h3 className="text-lg font-semibold text-white">
            {initialData ? 'Edit Schedule' : 'Add Schedule'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Schedule Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Weekly Performance Report"
              required
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Section 1: When does the report run? */}
          <div className="border border-slate-600/50 rounded-lg p-3 space-y-3">
            <h4 className="text-sm font-medium text-slate-300">When does the report run?</h4>

            <div>
              <label className="block text-xs text-slate-400 mb-1">Schedule type</label>
              <select
                value={scheduleType}
                onChange={e => {
                  const val = e.target.value as ScheduleType
                  setScheduleType(val)
                  // Reset days to sensible defaults
                  if (val === 'weekly') setScheduleDays([0])
                  else if (val === 'monthly') setScheduleDays([1])
                  else if (val === 'quarterly') setQuarterDay(1)
                  else if (val === 'yearly') { setYearlyMonth(1); setYearlyDay(1) }
                }}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
              >
                {SCHEDULE_TYPE_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {/* Contextual day selector */}
            {scheduleType === 'daily' && (
              <p className="text-xs text-slate-500">Runs every day at 06:00 UTC</p>
            )}

            {scheduleType === 'weekly' && (
              <div>
                <label className="block text-xs text-slate-400 mb-1.5">Run on</label>
                <div className="flex flex-wrap gap-1.5">
                  {WEEKDAY_LABELS.map((label, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => toggleWeekday(i)}
                      className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                        scheduleDays.includes(i)
                          ? 'bg-blue-600 border-blue-500 text-white'
                          : 'bg-slate-700 border-slate-600 text-slate-400 hover:border-slate-500'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {scheduleType === 'monthly' && (
              <div>
                <label className="block text-xs text-slate-400 mb-1.5">Run on day(s) of month</label>
                <div className="flex flex-wrap gap-1">
                  {Array.from({ length: 28 }, (_, i) => i + 1).map(d => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => toggleMonthDay(d)}
                      className={`w-8 h-8 text-xs font-medium rounded border transition-colors ${
                        scheduleDays.includes(d)
                          ? 'bg-blue-600 border-blue-500 text-white'
                          : 'bg-slate-700 border-slate-600 text-slate-400 hover:border-slate-500'
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => toggleMonthDay(-1)}
                    className={`px-2 h-8 text-xs font-medium rounded border transition-colors ${
                      scheduleDays.includes(-1)
                        ? 'bg-blue-600 border-blue-500 text-white'
                        : 'bg-slate-700 border-slate-600 text-slate-400 hover:border-slate-500'
                    }`}
                  >
                    Last
                  </button>
                </div>
              </div>
            )}

            {scheduleType === 'quarterly' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Quarter starts in</label>
                  <select
                    value={quarterStartMonth}
                    onChange={e => setQuarterStartMonth(parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                  >
                    {MONTH_LABELS.map((label, i) => (
                      <option key={i + 1} value={i + 1}>{label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Run on day</label>
                  <input
                    type="number"
                    min={1}
                    max={28}
                    value={quarterDay}
                    onChange={e => setQuarterDay(Math.max(1, Math.min(28, parseInt(e.target.value) || 1)))}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>
                <p className="col-span-2 text-xs text-slate-500">
                  Runs on day {quarterDay} of {MONTH_LABELS[quarterStartMonth - 1]}, {MONTH_LABELS[((quarterStartMonth - 1 + 3) % 12)]}, {MONTH_LABELS[((quarterStartMonth - 1 + 6) % 12)]}, {MONTH_LABELS[((quarterStartMonth - 1 + 9) % 12)]}
                </p>
              </div>
            )}

            {scheduleType === 'yearly' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Month</label>
                  <select
                    value={yearlyMonth}
                    onChange={e => setYearlyMonth(parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                  >
                    {MONTH_LABELS.map((label, i) => (
                      <option key={i + 1} value={i + 1}>{label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Day</label>
                  <input
                    type="number"
                    min={1}
                    max={31}
                    value={yearlyDay}
                    onChange={e => setYearlyDay(Math.max(1, Math.min(31, parseInt(e.target.value) || 1)))}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Section 2: Report covers */}
          <div className="border border-slate-600/50 rounded-lg p-3 space-y-3">
            <h4 className="text-sm font-medium text-slate-300">Report covers</h4>

            <div className="flex flex-wrap gap-1.5">
              {PERIOD_WINDOW_OPTIONS.map(o => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => setPeriodWindow(o.value)}
                  title={o.description}
                  className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                    periodWindow === o.value
                      ? 'bg-blue-600 border-blue-500 text-white'
                      : 'bg-slate-700 border-slate-600 text-slate-400 hover:border-slate-500'
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>

            {/* Description of selected window */}
            <p className="text-xs text-slate-500">
              {PERIOD_WINDOW_OPTIONS.find(o => o.value === periodWindow)?.description}
            </p>

            {/* Trailing lookback inputs */}
            {periodWindow === 'trailing' && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Last</span>
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={lookbackValue}
                  onChange={e => setLookbackValue(Math.max(1, parseInt(e.target.value) || 1))}
                  className="w-20 px-2 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                />
                <select
                  value={lookbackUnit}
                  onChange={e => setLookbackUnit(e.target.value as LookbackUnit)}
                  className="px-2 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                >
                  {LOOKBACK_UNIT_OPTIONS.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* AI Provider */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">AI Provider</label>
            <select
              value={aiProvider}
              onChange={e => setAiProvider(e.target.value)}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
            >
              {AI_PROVIDERS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Email Recipients */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Email Recipients</label>
            <div className="flex gap-2">
              <input
                type="email"
                value={newRecipient}
                onChange={e => setNewRecipient(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addRecipient())}
                placeholder="Add email address"
                className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:border-blue-500"
              />
              <select
                value={newRecipientLevel}
                onChange={e => setNewRecipientLevel(e.target.value as ExperienceLevel)}
                className="w-[130px] px-2 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
              >
                {LEVEL_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={addRecipient}
                className="px-3 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg transition-colors"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
            {recipients.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {recipients.map(r => (
                  <span key={r.email} className="inline-flex items-center gap-1.5 px-2 py-1 bg-slate-700 border border-slate-600 rounded-full text-sm text-slate-300">
                    {getLevelBadge(r.level)}
                    {r.email}
                    <button
                      type="button"
                      onClick={() => removeRecipient(r.email)}
                      className="text-slate-500 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <p className="text-xs text-slate-500 mt-1">
              Each recipient receives an individual email with their experience level's summary highlighted
            </p>
          </div>

          {/* Link Goals */}
          {goals.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Include Goals</label>
              <div className="space-y-1.5">
                {goals.filter(g => g.is_active).map(goal => (
                  <label
                    key={goal.id}
                    className="flex items-center gap-2 p-2 bg-slate-700/50 rounded-lg cursor-pointer hover:bg-slate-700 transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={selectedGoalIds.includes(goal.id)}
                      onChange={() => toggleGoal(goal.id)}
                      className="rounded border-slate-600 bg-slate-700 text-blue-500 focus:ring-blue-500"
                    />
                    <span className="text-sm text-slate-300">{goal.name}</span>
                    <span className="text-xs text-slate-500 ml-auto">
                      {goal.target_currency === 'BTC' ? `${goal.target_value} BTC` : `$${goal.target_value.toLocaleString()}`}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Enabled Toggle */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={isEnabled}
              onChange={e => setIsEnabled(e.target.checked)}
              className="rounded border-slate-600 bg-slate-700 text-blue-500 focus:ring-blue-500"
            />
            <span className="text-sm text-slate-300">Enabled (auto-generate on schedule)</span>
          </label>

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
              disabled={submitting || !name}
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
