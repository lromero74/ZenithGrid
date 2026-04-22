/**
 * SpeculativePresetPanel
 *
 * Bot-form risk-preset picker. Selecting "speculative" flips on catalyst mode
 * on the backend (via the strategy_config.ai_risk_preset key) and surfaces
 * the mandatory guardrails: warning banner, confirmation checkbox, and
 * bucket-not-configured gate.
 *
 * This component does NOT disable the Save button itself — it reports its
 * blocking state via onBlockingStateChange so the parent form can combine it
 * with other validations.
 *
 * See PRPs/high-risk-doubling-preset.md §Task D2, §7.
 */

import { useEffect, useState } from 'react'
import { AlertTriangle, Flame } from 'lucide-react'
import { speculativeBucketApi, type SpeculativeBucketInfo } from '../../../services/api'

type RiskPreset = 'aggressive' | 'moderate' | 'conservative' | 'speculative'

const PRESET_LABELS: Record<RiskPreset, string> = {
  aggressive: 'Aggressive',
  moderate: 'Moderate',
  conservative: 'Conservative',
  speculative: 'Speculative (High-Risk 2x Hunter)',
}

export interface BlockingState {
  blocked: boolean
  reason: string | null
}

interface Props {
  strategyConfig: Record<string, unknown>
  onChange: (updates: Record<string, unknown>) => void
  onBlockingStateChange: (state: BlockingState) => void
  accountId: number | null
  accountSpeculativeAllocationPct: number
}

export function SpeculativePresetPanel({
  strategyConfig,
  onChange,
  onBlockingStateChange,
  accountId,
  accountSpeculativeAllocationPct,
}: Props) {
  const preset = (strategyConfig.ai_risk_preset as RiskPreset | undefined) ?? ''
  const isSpeculative = preset === 'speculative'
  const [confirmed, setConfirmed] = useState(false)
  const [bucketInfo, setBucketInfo] = useState<SpeculativeBucketInfo | null>(null)

  // Reset the confirmation checkbox if the user switches away from speculative.
  useEffect(() => {
    if (!isSpeculative && confirmed) setConfirmed(false)
  }, [isSpeculative, confirmed])

  // Fetch bucket info on-demand when speculative is picked — only the parent
  // knows whether this is an editable form or a readonly modal, so a quiet
  // failure here should not block rendering.
  useEffect(() => {
    if (!isSpeculative || !accountId) {
      setBucketInfo(null)
      return
    }
    let cancelled = false
    speculativeBucketApi.get(accountId).then(
      (info) => { if (!cancelled) setBucketInfo(info) },
      () => { /* ignore — parent has the allocation pct */ },
    )
    return () => { cancelled = true }
  }, [isSpeculative, accountId])

  // Compute the blocking state any time inputs change.
  const bucketNotConfigured = isSpeculative && accountSpeculativeAllocationPct <= 0
  const needsConfirmation = isSpeculative && !confirmed
  let blockingReason: string | null = null
  if (bucketNotConfigured) {
    blockingReason =
      'Set a non-zero Speculative Allocation on this account under ' +
      'Settings → Speculative Bucket before saving a speculative bot.'
  } else if (needsConfirmation) {
    blockingReason = 'Check the "I understand the risk" box to confirm.'
  }

  useEffect(() => {
    onBlockingStateChange({
      blocked: blockingReason !== null,
      reason: blockingReason,
    })
  }, [blockingReason, onBlockingStateChange])

  const handlePresetChange = (value: string) => {
    onChange({ ai_risk_preset: value })
  }

  return (
    <div className="border-b border-slate-700 pb-6">
      <label className="block text-sm font-medium mb-2">
        Risk Preset
      </label>
      <select
        aria-label="Risk Preset"
        value={typeof preset === 'string' ? preset : ''}
        onChange={(e) => handlePresetChange(e.target.value)}
        className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
      >
        <option value="">(none)</option>
        {Object.entries(PRESET_LABELS).map(([val, label]) => (
          <option key={val} value={val}>{label}</option>
        ))}
      </select>
      <p className="text-xs text-slate-400 mt-1">
        Speculative hunts asymmetric upside with a hard per-account cap.
        All other presets use the regular budget rules.
      </p>

      {isSpeculative && (
        <div className="mt-4 space-y-3">
          <div className="bg-amber-900/30 border border-amber-700 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <Flame size={20} className="text-amber-400 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-amber-100 space-y-2">
                <div className="font-semibold text-amber-200">
                  High-risk speculative preset
                </div>
                <p>
                  Speculative bots hunt for 2x-in-a-day catalyst setups.
                  <strong> Historical win rate is typically under 20%.</strong>{' '}
                  Typical losers close near −12% (tight stop loss). Only
                  allocate capital you can lose entirely.
                </p>
                <p>
                  Every speculative-preset bot on this account shares one
                  account-level <strong>Speculative Allocation</strong> cap.
                  Winners at 2x do NOT unlock new bet headroom (cost-basis
                  accounting) — this is what keeps damage contained.
                </p>
              </div>
            </div>
          </div>

          {bucketNotConfigured ? (
            <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-sm text-red-200 flex items-start gap-2">
              <AlertTriangle size={16} className="text-red-400 mt-0.5 flex-shrink-0" />
              <div>
                Speculative Allocation is <strong>0%</strong> on this account.
                Save is disabled until you configure a non-zero allocation
                under{' '}
                <span className="underline">Settings → Speculative Bucket</span>.
              </div>
            </div>
          ) : (
            bucketInfo && (
              <div className="bg-slate-800/60 border border-slate-600 rounded p-3 text-xs text-slate-300">
                Account bucket:{' '}
                <span className="font-mono text-white">
                  ${bucketInfo.deployed_cost_basis_usd.toFixed(2)}
                </span>{' '}
                deployed of{' '}
                <span className="font-mono text-white">
                  ${bucketInfo.bucket_usd.toFixed(2)}
                </span>{' '}
                (
                <span className="text-amber-300">
                  ${bucketInfo.available_usd.toFixed(2)} available
                </span>
                ) across {bucketInfo.active_bot_count} speculative bot(s).
              </div>
            )
          )}

          <label className="flex items-start gap-2 cursor-pointer text-sm text-slate-200">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-700 text-amber-600 focus:ring-2 focus:ring-amber-500"
            />
            <span>
              I understand the risk — low win rate and typical −12% losses are
              expected, and the account cap is my safety net.
            </span>
          </label>
        </div>
      )}
    </div>
  )
}
