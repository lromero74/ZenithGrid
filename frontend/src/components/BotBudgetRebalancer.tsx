/**
 * BotBudgetRebalancer
 *
 * Allows users to distribute total budget allocation across bots in each
 * quote-currency group (e.g. USDC Bots, BTC Bots) using sliders.
 * Saving writes budget_percentage directly onto each participating bot.
 */

import { useState, useEffect, useCallback } from 'react'
import { ChevronDown, ChevronUp, AlertTriangle, Save, RefreshCw, Lock } from 'lucide-react'
import {
  getRebalancerState,
  saveRebalancerGroup,
  type RebalancerCurrencyGroup,
  type RebalancerBot,
} from '../services/botRebalancerApi'
import { useNotifications } from '../contexts/NotificationContext'

interface BotBudgetRebalancerProps {
  accountId: number
}

interface BotSlotState {
  bot_id: number
  enabled: boolean
  target_pct: number
}

interface GroupState {
  base_currency: string
  max_total_pct: number
  overweight_tolerance_pct: number
  enabled: boolean
  bots: RebalancerBot[]
  slots: BotSlotState[]
  expanded: boolean
  saving: boolean
}

function buildSlots(group: RebalancerCurrencyGroup): BotSlotState[] {
  return group.bots.map((b) => ({
    bot_id: b.id,
    enabled: b.bot_rebalancer_enabled,
    target_pct: b.bot_rebalancer_target_pct,
  }))
}

function totalEnabled(slots: BotSlotState[]): number {
  return slots.filter((s) => s.enabled).reduce((sum, s) => sum + s.target_pct, 0)
}

export function BotBudgetRebalancer({ accountId }: BotBudgetRebalancerProps) {
  const { addToast } = useNotifications()
  const [groups, setGroups] = useState<GroupState[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchState = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getRebalancerState(accountId)
      setGroups(
        res.data.map((g) => ({
          base_currency: g.base_currency,
          max_total_pct: g.max_total_pct,
          overweight_tolerance_pct: g.overweight_tolerance_pct,
          enabled: g.enabled,
          bots: g.bots,
          slots: buildSlots(g),
          expanded: false,
          saving: false,
        }))
      )
    } catch (err) {
      setError('Failed to load rebalancer state.')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [accountId])

  useEffect(() => {
    fetchState()
  }, [fetchState])

  function toggleExpand(idx: number) {
    setGroups((prev) =>
      prev.map((g, i) => (i === idx ? { ...g, expanded: !g.expanded } : g))
    )
  }

  function updateGroupField(
    idx: number,
    field: 'max_total_pct' | 'overweight_tolerance_pct',
    value: number
  ) {
    setGroups((prev) =>
      prev.map((g, i) => (i === idx ? { ...g, [field]: value } : g))
    )
  }

  function toggleBotEnabled(groupIdx: number, botId: number) {
    setGroups((prev) =>
      prev.map((g, i) => {
        if (i !== groupIdx) return g
        return {
          ...g,
          slots: g.slots.map((s) =>
            s.bot_id === botId ? { ...s, enabled: !s.enabled } : s
          ),
        }
      })
    )
  }

  function handleSliderChange(groupIdx: number, botId: number, newValue: number) {
    setGroups((prev) =>
      prev.map((g, i) => {
        if (i !== groupIdx) return g
        const maxPct = g.max_total_pct
        const slots = g.slots

        // Clamp new value
        const clamped = Math.min(Math.max(0, newValue), maxPct)

        // Other enabled slots (not the one being dragged)
        const others = slots.filter((s) => s.enabled && s.bot_id !== botId)
        const totalOthers = others.reduce((sum, s) => sum + s.target_pct, 0)
        const remaining = maxPct - clamped

        let newSlots: BotSlotState[]
        if (others.length === 0) {
          newSlots = slots.map((s) =>
            s.bot_id === botId ? { ...s, target_pct: clamped } : s
          )
        } else if (totalOthers > 0) {
          const scaleFactor = remaining / totalOthers
          newSlots = slots.map((s) => {
            if (s.bot_id === botId) return { ...s, target_pct: clamped }
            if (!s.enabled) return s
            return { ...s, target_pct: Math.max(0, +(s.target_pct * scaleFactor).toFixed(2)) }
          })
        } else {
          // Others are all 0 — distribute remaining equally
          const eachShare = remaining / others.length
          newSlots = slots.map((s) => {
            if (s.bot_id === botId) return { ...s, target_pct: clamped }
            if (!s.enabled) return s
            return { ...s, target_pct: +eachShare.toFixed(2) }
          })
        }

        return { ...g, slots: newSlots }
      })
    )
  }

  async function saveGroup(groupIdx: number) {
    const g = groups[groupIdx]
    const total = totalEnabled(g.slots)
    if (total > g.max_total_pct + 0.01) {
      addToast({
        type: 'error',
        title: 'Over Budget',
        message: `Total ${total.toFixed(1)}% exceeds max ${g.max_total_pct.toFixed(1)}%. Adjust sliders first.`,
      })
      return
    }

    setGroups((prev) =>
      prev.map((grp, i) => (i === groupIdx ? { ...grp, saving: true } : grp))
    )

    try {
      await saveRebalancerGroup({
        account_id: accountId,
        base_currency: g.base_currency,
        max_total_pct: g.max_total_pct,
        overweight_tolerance_pct: g.overweight_tolerance_pct,
        bots: g.slots.map((s) => ({
          bot_id: s.bot_id,
          enabled: s.enabled,
          target_pct: s.target_pct,
        })),
      })
      addToast({
        type: 'success',
        title: 'Rebalancer Saved',
        message: `${g.base_currency} rebalancer saved.`,
      })
      await fetchState()
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Save failed.'
      addToast({ type: 'error', title: 'Save Failed', message: msg })
    } finally {
      setGroups((prev) =>
        prev.map((grp, i) => (i === groupIdx ? { ...grp, saving: false } : grp))
      )
    }
  }

  if (loading) {
    return (
      <div className="mt-6 p-4 bg-slate-800 rounded-lg border border-slate-700">
        <div className="flex items-center gap-2 text-slate-400">
          <RefreshCw className="w-4 h-4 animate-spin" />
          <span className="text-sm">Loading Bot Budget Rebalancer…</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="mt-6 p-4 bg-red-900/20 rounded-lg border border-red-700/50">
        <div className="flex items-center gap-2 text-red-400">
          <AlertTriangle className="w-4 h-4" />
          <span className="text-sm">{error}</span>
        </div>
      </div>
    )
  }

  if (groups.length === 0) {
    return null
  }

  return (
    <div className="mt-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-white flex items-center gap-2">
          <Lock className="w-4 h-4 text-emerald-400" />
          Bot Budget Rebalancer
        </h2>
        <button
          onClick={fetchState}
          className="text-slate-400 hover:text-white transition-colors"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>
      <p className="text-xs text-slate-400 mb-4">
        Distribute budget allocation across bots per currency group. Saving writes{' '}
        <span className="text-emerald-300">Budget %</span> directly to each participating bot.
      </p>

      <div className="space-y-3">
        {groups.map((group, groupIdx) => {
          const total = totalEnabled(group.slots)
          const overBudget = total > group.max_total_pct + 0.01
          const nearLimit = !overBudget && total > group.max_total_pct * 0.9
          const hasOverweight = group.bots.some((b) => b.rebalancer_bot_overweight)
          const hasActiveWithPositions = group.bots.some(
            (b) => b.is_active && b.open_positions_count > 0 &&
              group.slots.find((s) => s.bot_id === b.id)?.enabled
          )

          return (
            <div
              key={group.base_currency}
              className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden"
            >
              {/* Group header */}
              <button
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-700/50 transition-colors"
                onClick={() => toggleExpand(groupIdx)}
              >
                <div className="flex items-center gap-3">
                  <span className="font-medium text-white">
                    {group.base_currency} Bots
                  </span>
                  <span className="text-xs text-slate-400">
                    {group.bots.length} bot{group.bots.length !== 1 ? 's' : ''}
                  </span>
                  {hasOverweight && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-400 border border-amber-700/50">
                      Overweight
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`text-sm font-mono ${
                      overBudget
                        ? 'text-red-400'
                        : nearLimit
                        ? 'text-amber-400'
                        : 'text-emerald-400'
                    }`}
                  >
                    {total.toFixed(1)}% / {group.max_total_pct.toFixed(0)}%
                  </span>
                  {group.expanded ? (
                    <ChevronUp className="w-4 h-4 text-slate-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-slate-400" />
                  )}
                </div>
              </button>

              {group.expanded && (
                <div className="px-4 pb-4 border-t border-slate-700 pt-4 space-y-4">
                  {/* Allocation bar */}
                  <div>
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                      <span>Total allocated</span>
                      <span
                        className={
                          overBudget ? 'text-red-400' : nearLimit ? 'text-amber-400' : ''
                        }
                      >
                        {total.toFixed(1)}% / {group.max_total_pct.toFixed(0)}%
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-700 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          overBudget
                            ? 'bg-red-500'
                            : nearLimit
                            ? 'bg-amber-500'
                            : 'bg-emerald-500'
                        }`}
                        style={{
                          width: `${Math.min(100, (total / group.max_total_pct) * 100)}%`,
                        }}
                      />
                    </div>
                  </div>

                  {/* Warning: live bots with open positions */}
                  {hasActiveWithPositions && (
                    <div className="flex items-start gap-2 p-3 rounded bg-amber-900/20 border border-amber-700/30">
                      <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                      <p className="text-xs text-amber-300">
                        One or more active bots have open positions. Saving will update{' '}
                        <strong>Budget %</strong> live — changes take effect on the next monitor
                        cycle.
                      </p>
                    </div>
                  )}

                  {/* Group settings */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Max Total Allocation (%)
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={150}
                        step={1}
                        value={group.max_total_pct}
                        onChange={(e) =>
                          updateGroupField(
                            groupIdx,
                            'max_total_pct',
                            Math.min(150, Math.max(1, parseFloat(e.target.value) || 100))
                          )
                        }
                        className="w-full rounded border border-slate-600 bg-slate-700 px-2 py-1.5 text-white text-sm font-mono"
                      />
                      <p className="text-xs text-slate-500 mt-0.5">
                        1–150%. Default 100%.
                      </p>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Overweight Tolerance (%)
                      </label>
                      <input
                        type="number"
                        min={0}
                        max={50}
                        step={0.5}
                        value={group.overweight_tolerance_pct}
                        onChange={(e) =>
                          updateGroupField(
                            groupIdx,
                            'overweight_tolerance_pct',
                            Math.min(50, Math.max(0, parseFloat(e.target.value) || 5))
                          )
                        }
                        className="w-full rounded border border-slate-600 bg-slate-700 px-2 py-1.5 text-white text-sm font-mono"
                      />
                      <p className="text-xs text-slate-500 mt-0.5">
                        Gate fires when actual exceeds target + this value.
                      </p>
                    </div>
                  </div>

                  {/* Per-bot rows */}
                  <div className="space-y-3">
                    {group.bots.map((bot) => {
                      const slot = group.slots.find((s) => s.bot_id === bot.id)
                      if (!slot) return null
                      return (
                        <div
                          key={bot.id}
                          className="flex flex-col gap-1.5 p-3 rounded bg-slate-700/50 border border-slate-600/50"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <input
                                type="checkbox"
                                checked={slot.enabled}
                                onChange={() => toggleBotEnabled(groupIdx, bot.id)}
                                className="rounded border-slate-500 shrink-0"
                              />
                              <span className="text-sm font-medium text-white truncate">
                                {bot.name}
                              </span>
                              {bot.is_active ? (
                                <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-900/40 text-emerald-400 border border-emerald-700/40 shrink-0">
                                  Active
                                </span>
                              ) : (
                                <span className="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-400 shrink-0">
                                  Stopped
                                </span>
                              )}
                              {bot.rebalancer_bot_overweight && (
                                <span className="text-xs px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-400 border border-amber-700/40 shrink-0">
                                  ⚠ Overweight
                                </span>
                              )}
                              {bot.open_positions_count > 0 && (
                                <span className="text-xs text-slate-400 shrink-0">
                                  {bot.open_positions_count} open
                                </span>
                              )}
                            </div>
                            <span
                              className={`text-sm font-mono shrink-0 ${
                                slot.enabled ? 'text-emerald-400' : 'text-slate-500'
                              }`}
                            >
                              {slot.target_pct.toFixed(1)}%
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <input
                              type="range"
                              min={0}
                              max={group.max_total_pct}
                              step={0.5}
                              value={slot.target_pct}
                              disabled={!slot.enabled}
                              onChange={(e) =>
                                handleSliderChange(groupIdx, bot.id, parseFloat(e.target.value))
                              }
                              className={`flex-1 h-1.5 rounded-full appearance-none cursor-pointer ${
                                slot.enabled
                                  ? 'accent-emerald-500'
                                  : 'opacity-40 cursor-not-allowed'
                              }`}
                            />
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {/* Save button */}
                  <div className="flex justify-end pt-1">
                    <button
                      onClick={() => saveGroup(groupIdx)}
                      disabled={group.saving || overBudget}
                      className={`flex items-center gap-2 px-4 py-2 rounded font-medium text-sm transition-colors ${
                        group.saving || overBudget
                          ? 'bg-slate-600 text-slate-400 cursor-not-allowed'
                          : 'bg-emerald-600 hover:bg-emerald-700 text-white'
                      }`}
                    >
                      {group.saving ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Save className="w-4 h-4" />
                      )}
                      {group.saving ? 'Saving…' : `Save ${group.base_currency} Group`}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default BotBudgetRebalancer
