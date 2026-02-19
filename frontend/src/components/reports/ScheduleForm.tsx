import { useState, useEffect } from 'react'
import { X, Plus, Trash2 } from 'lucide-react'
import type { ReportGoal, ReportSchedule, RecipientItem, ExperienceLevel } from '../../types'

interface ScheduleFormProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: ScheduleFormData) => Promise<void>
  goals: ReportGoal[]
  initialData?: ReportSchedule | null
}

export interface ScheduleFormData {
  name: string
  periodicity: string
  account_id?: number | null
  recipients: RecipientItem[]
  ai_provider?: string | null
  goal_ids: number[]
  is_enabled: boolean
}

const PERIODICITY_OPTIONS = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'biweekly', label: 'Biweekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'yearly', label: 'Yearly' },
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
  const [periodicity, setPeriodicity] = useState('weekly')
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
      setPeriodicity(initialData.periodicity)
      setRecipients(normalizeRecipients(initialData.recipients as unknown[]))
      setAiProvider(initialData.ai_provider || '')
      setSelectedGoalIds(initialData.goal_ids || [])
      setIsEnabled(initialData.is_enabled)
    } else {
      setName('')
      setPeriodicity('weekly')
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await onSubmit({
        name,
        periodicity,
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

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Frequency</label>
              <select
                value={periodicity}
                onChange={e => setPeriodicity(e.target.value)}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
              >
                {PERIODICITY_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
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
