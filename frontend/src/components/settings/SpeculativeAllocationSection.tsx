/**
 * SpeculativeAllocationSection
 *
 * Account-level "Speculative Allocation %" control. Caps the total cost
 * basis that speculative-preset bots can deploy across this account.
 * Cost-basis semantics: winners do NOT expand headroom.
 *
 * See PRPs/high-risk-doubling-preset.md §Task D1.
 */

import { useState } from 'react'
import { AlertTriangle, Flame, Save } from 'lucide-react'
import { useAccount, type Account } from '../../contexts/AccountContext'
import { usePermission } from '../../hooks/usePermission'

interface Props {
  account: Account
}

const clampPct = (n: number): number => {
  if (!Number.isFinite(n)) return 0
  if (n < 0) return 0
  if (n > 100) return 100
  return n
}

export function SpeculativeAllocationSection({ account }: Props) {
  const { updateAccount } = useAccount()
  const canWrite = usePermission('accounts', 'write')

  const initial = account.speculative_allocation_pct ?? 0
  const [value, setValue] = useState<string>(String(initial))
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleSave = async () => {
    const parsed = clampPct(parseFloat(value))
    setSaving(true)
    setMessage(null)
    try {
      await updateAccount(account.id, { speculative_allocation_pct: parsed })
      setValue(String(parsed))
      setMessage({ type: 'success', text: 'Speculative allocation saved' })
      setTimeout(() => setMessage(null), 3000)
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save' })
    } finally {
      setSaving(false)
    }
  }

  const inputId = `speculative-allocation-${account.id}`
  const parsed = clampPct(parseFloat(value))
  const isZero = parsed === 0

  return (
    <div className="bg-slate-800/50 rounded-lg p-4 border border-amber-700/40">
      <div className="flex items-start gap-2 mb-2">
        <Flame size={16} className="text-amber-400 mt-0.5 flex-shrink-0" />
        <div>
          <h4 className="text-sm font-semibold text-white">Speculative Allocation</h4>
          <p className="text-xs text-slate-400 mt-0.5">
            Hard cap on total <strong>cost basis</strong> deployed across
            speculative-preset bots on this account. Winners at 2x do NOT
            unlock new bet headroom — this is what keeps damage contained.
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-end gap-3">
        <div className="flex-1">
          <label
            htmlFor={inputId}
            className="block text-xs font-medium text-slate-300 mb-1"
          >
            Speculative Allocation %
          </label>
          <div className="flex items-center gap-2">
            <input
              id={inputId}
              type="number"
              min="0"
              max="100"
              step="0.5"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              disabled={!canWrite || saving}
              className="w-28 bg-slate-700 text-white px-3 py-1.5 rounded border border-slate-600 text-sm font-mono"
              aria-describedby={`${inputId}-help`}
            />
            <span className="text-slate-400 text-sm">% of account value</span>
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={!canWrite || saving}
          className="bg-amber-600 hover:bg-amber-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white px-4 py-1.5 rounded text-sm flex items-center gap-2"
        >
          <Save size={14} />
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>

      <p id={`${inputId}-help`} className="text-[11px] text-slate-500 mt-2">
        0% disables the bucket — speculative bots cannot open new positions
        until a non-zero allocation is set.
      </p>

      {isZero && (
        <div className="mt-2 text-[11px] text-amber-300 flex items-center gap-1">
          <AlertTriangle size={12} />
          Bucket is currently disabled.
        </div>
      )}

      {message && (
        <div
          className={`mt-3 text-xs px-3 py-2 rounded ${
            message.type === 'success'
              ? 'bg-green-900/30 border border-green-700 text-green-400'
              : 'bg-red-900/30 border border-red-700 text-red-400'
          }`}
        >
          {message.text}
        </div>
      )}
    </div>
  )
}
