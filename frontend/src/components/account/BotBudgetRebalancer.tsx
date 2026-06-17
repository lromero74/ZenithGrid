/**
 * BotBudgetRebalancer
 *
 * Allows users to distribute total budget allocation across bots in each
 * quote-currency group (e.g. USDC Bots, BTC Bots) using sliders.
 * Saving writes budget_percentage directly onto each participating bot.
 *
 * Lock feature: locking a bot's slider pins its allocation; only unlocked
 * bots absorb the redistribution when another slider is moved.
 */

import { useState, useEffect, useCallback } from 'react'
import { ChevronDown, ChevronUp, AlertTriangle, Save, RefreshCw, Lock, LockOpen, Link, Link2 } from 'lucide-react'
import {
  getRebalancerState,
  saveRebalancerGroup,
  type RebalancerCurrencyGroup,
  type RebalancerBot,
} from '../../services/botRebalancerApi'
import { useNotifications } from '../../contexts/NotificationContext'
import { redistributeSlots } from './rebalancerMath'

interface BotBudgetRebalancerProps {
  accountId: number
}

interface BotSlotState {
  bot_id: number
  enabled: boolean
  target_pct: number
  locked: boolean
  bound: boolean
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
  // Raw string drafts while user is typing — avoids clamping fighting backspace
  maxTotalDraft: string
  toleranceDraft: string
}

function buildSlots(group: RebalancerCurrencyGroup): BotSlotState[] {
  return group.bots.map((b) => ({
    bot_id: b.id,
    enabled: b.bot_rebalancer_enabled,
    target_pct: b.bot_rebalancer_target_pct,
    locked: false,
    bound: false,
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
        res.map((g) => ({
          base_currency: g.base_currency,
          max_total_pct: g.max_total_pct,
          overweight_tolerance_pct: g.overweight_tolerance_pct,
          enabled: g.enabled,
          bots: g.bots,
          slots: buildSlots(g),
          expanded: false,
          saving: false,
          maxTotalDraft: String(g.max_total_pct),
          toleranceDraft: String(g.overweight_tolerance_pct),
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

  function updateDraft(idx: number, field: 'maxTotalDraft' | 'toleranceDraft', raw: string) {
    setGroups((prev) =>
      prev.map((g, i) => (i === idx ? { ...g, [field]: raw } : g))
    )
  }

  function commitDraft(idx: number, field: 'maxTotalDraft' | 'toleranceDraft') {
    setGroups((prev) =>
      prev.map((g, i) => {
        if (i !== idx) return g
        if (field === 'maxTotalDraft') {
          const v = Math.min(300, Math.max(1, parseFloat(g.maxTotalDraft) || 100))
          return { ...g, max_total_pct: v, maxTotalDraft: String(v) }
        } else {
          const v = Math.min(50, Math.max(0, parseFloat(g.toleranceDraft) || 5))
          return { ...g, overweight_tolerance_pct: v, toleranceDraft: String(v) }
        }
      })
    )
  }

  function toggleBotEnabled(groupIdx: number, botId: number) {
    setGroups((prev) =>
      prev.map((g, i) => {
        if (i !== groupIdx) return g
        return {
          ...g,
          slots: g.slots.map((s) =>
            s.bot_id === botId ? { ...s, enabled: !s.enabled, locked: false, bound: false } : s
          ),
        }
      })
    )
  }

  function toggleBotLocked(groupIdx: number, botId: number) {
    setGroups((prev) =>
      prev.map((g, i) => {
        if (i !== groupIdx) return g
        return {
          ...g,
          slots: g.slots.map((s) =>
            s.bot_id === botId ? { ...s, locked: !s.locked, bound: false } : s
          ),
        }
      })
    )
  }

  function toggleBotBound(groupIdx: number, botId: number) {
    setGroups((prev) =>
      prev.map((g, i) => {
        if (i !== groupIdx) return g
        return {
          ...g,
          slots: g.slots.map((s) =>
            s.bot_id === botId ? { ...s, bound: !s.bound, locked: false } : s
          ),
        }
      })
    )
  }

  function linkAllSliders(groupIdx: number) {
    setGroups((prev) =>
      prev.map((g, i) => {
        if (i !== groupIdx) return g
        
        // Get all enabled bots in this group
        const enabledBots = g.slots.filter(s => s.enabled && !s.locked)
        
        if (enabledBots.length === 0) {
          addToast({
            type: 'error',
            title: 'No Enabled Bots',
            message: 'Please enable at least one bot before linking all sliders.',
          })
          return g
        }
        
        // Bind all enabled bots together
        const nextSlots = g.slots.map(s => {
          if (s.enabled && !s.locked) {
            return { ...s, bound: true }
          }
          return s
        })
        
        addToast({
          type: 'success',
          title: 'All Sliders Linked',
          message: `Linked ${enabledBots.length} slider${enabledBots.length > 1 ? 's' : ''} together.`,
        })
        
        return { ...g, slots: nextSlots }
      })
    )
  }

  function unlinkAllSliders(groupIdx: number) {
    setGroups((prev) =>
      prev.map((g, i) => {
        if (i !== groupIdx) return g
        
        // Unbind all enabled bots in this group
        const nextSlots = g.slots.map(s => ({
          ...s,
          bound: false,
          locked: false
        }))
        
        addToast({
          type: 'success',
          title: 'All Links Removed',
          message: `Unlinked all sliders in ${g.base_currency} group.`,
        })
        
        return { ...g, slots: nextSlots }
      })
    )
  }

  function handleSliderChange(groupIdx: number, botId: number, newValue: number) {
    setGroups((prev) =>
      prev.map((g, i) => {
        if (i !== groupIdx) return g
        const nextSlots = redistributeSlots(g.slots, g.max_total_pct, botId, newValue)
        return { ...g, slots: nextSlots }
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
          // Snap to 0.5 step on save — cleans up any legacy sub-step values from DB
          target_pct: Math.round(s.target_pct * 2) / 2,
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
        (err as { detail?: string })?.detail ??
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
          const anyLocked = group.slots.some((s) => s.enabled && s.locked)
          const anyBound = group.slots.some((s) => s.enabled && s.bound)

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
                  {anyLocked && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-400 border border-blue-700/50">
                      Pinned
                    </span>
                  )}
                  {anyBound && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-900/40 text-indigo-400 border border-indigo-700/50">
                      Bound
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
                    }`}>
                    {total.toFixed(1)}% / {group.max_total_pct.toFixed(0)}%
                  </span>
                  
                  {/* Link all/unlink all buttons */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => linkAllSliders(groupIdx)}
                      title={anyBound ? 'Click to unbind all sliders' : 'Link all enabled sliders together'}
                      className={`p-1 rounded transition-colors ${
                        anyBound
                          ? 'text-indigo-400 hover:text-indigo-300'
                          : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      {anyBound ? (
                        <Link className="w-3.5 h-3.5" />
                      ) : (
                        <Link2 className="w-3.5 h-3.5 opacity-60" />
                      )}
                    </button>
                    
                    <span className="text-slate-500 text-xs">|</span>
                    
                    <button
                      onClick={() => unlinkAllSliders(groupIdx)}
                      title="Unlink all sliders in this group"
                      className="p-1 rounded transition-colors text-slate-500 hover:text-slate-300"
                    >
                      <Link2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  
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
                        max={300}
                        step={1}
                        value={group.maxTotalDraft}
                        onChange={(e) => updateDraft(groupIdx, 'maxTotalDraft', e.target.value)}
                        onBlur={() => commitDraft(groupIdx, 'maxTotalDraft')}
                        className="w-full rounded border border-slate-600 bg-slate-700 px-2 py-1.5 text-white text-sm font-mono"
                      />
                      <p className="text-xs text-slate-500 mt-0.5">
                        1–300%. Default 100%.
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
                        value={group.toleranceDraft}
                        onChange={(e) => updateDraft(groupIdx, 'toleranceDraft', e.target.value)}
                        onBlur={() => commitDraft(groupIdx, 'toleranceDraft')}
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
                          className={`flex flex-col gap-1.5 p-3 rounded border transition-colors ${
                            slot.locked
                              ? 'bg-blue-900/10 border-blue-700/40'
                              : slot.bound
                              ? 'bg-indigo-900/10 border-indigo-700/40'
                              : 'bg-slate-700/50 border-slate-600/50'
                          }`}
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
                              disabled={!slot.enabled || slot.locked}
                              onChange={(e) =>
                                handleSliderChange(groupIdx, bot.id, parseFloat(e.target.value))
                              }
                              className={`flex-1 h-1.5 rounded-full appearance-none ${
                                !slot.enabled
                                  ? 'opacity-40 cursor-not-allowed'
                                  : slot.locked
                                  ? 'opacity-60 cursor-not-allowed accent-blue-500'
                                  : slot.bound
                                  ? 'cursor-pointer accent-indigo-500'
                                  : 'cursor-pointer accent-emerald-500'
                              }`}
                            />
                            {slot.enabled && (
                              <div className="flex items-center gap-1 shrink-0">
                                <button
                                  onClick={() => toggleBotBound(groupIdx, bot.id)}
                                  title={slot.bound ? 'Bound — click to unbind' : 'Click to bind this slider with others'}
                                  className={`p-1 rounded transition-colors ${
                                    slot.bound
                                      ? 'text-indigo-400 hover:text-indigo-300'
                                      : 'text-slate-500 hover:text-slate-300'
                                  }`}
                                >
                                  {slot.bound ? (
                                    <Link className="w-3.5 h-3.5" />
                                  ) : (
                                    <Link2 className="w-3.5 h-3.5 opacity-60" />
                                  )}
                                </button>
                                <button
                                  onClick={() => toggleBotLocked(groupIdx, bot.id)}
                                  title={slot.locked ? 'Pinned — click to unpin' : 'Click to pin this allocation'}
                                  className={`p-1 rounded transition-colors ${
                                    slot.locked
                                      ? 'text-blue-400 hover:text-blue-300'
                                      : 'text-slate-500 hover:text-slate-300'
                                  }`}
                                >
                                  {slot.locked ? (
                                    <Lock className="w-3.5 h-3.5" />
                                  ) : (
                                    <LockOpen className="w-3.5 h-3.5" />
                                  )}
                                </button>
                              </div>
                            )}
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
