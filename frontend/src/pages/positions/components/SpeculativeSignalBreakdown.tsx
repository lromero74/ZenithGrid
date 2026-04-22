/**
 * SpeculativeSignalBreakdown
 *
 * Renders the speculative-preset scoring extras from an AI opinion log row:
 * the LLM's doubling_probability_score (if it answered in catalyst mode)
 * and the deterministic pre-AI scorer's per-component fire breakdown.
 *
 * Quiet when the opinion is not from a speculative call (both fields absent).
 *
 * See PRPs/high-risk-doubling-preset.md §Task D4.
 */

import { Flame } from 'lucide-react'
import type { SpeculativeSignalComponent } from '../../../types'

interface Props {
  doublingProbabilityScore: number | null | undefined
  speculativeScore: number | null | undefined
  components: Record<string, SpeculativeSignalComponent> | null | undefined
}

const humanizeComponent = (name: string) =>
  name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

export function SpeculativeSignalBreakdown({
  doublingProbabilityScore,
  speculativeScore,
  components,
}: Props) {
  const hasDouble = doublingProbabilityScore != null
  const hasScore = speculativeScore != null
  const componentEntries = components ? Object.entries(components) : []
  if (!hasDouble && !hasScore && componentEntries.length === 0) return null

  return (
    <div className="pt-2 border-t border-slate-700/40">
      <div className="flex items-center gap-1 text-slate-400 mb-2">
        <Flame size={12} className="text-amber-400" />
        <span className="font-medium">Speculative catalyst signals</span>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-2">
        {hasDouble && (
          <div className="bg-slate-900/40 rounded p-2">
            <div className="text-[10px] uppercase text-slate-500 tracking-wide">
              Doubling probability
            </div>
            <div className="text-lg font-mono text-amber-300">
              {doublingProbabilityScore}
              <span className="text-xs text-slate-500">/100</span>
            </div>
          </div>
        )}
        {hasScore && (
          <div className="bg-slate-900/40 rounded p-2">
            <div className="text-[10px] uppercase text-slate-500 tracking-wide">
              Pre-AI scorer
            </div>
            <div className="text-lg font-mono text-amber-300">
              {speculativeScore}
              <span className="text-xs text-slate-500">/100</span>
            </div>
          </div>
        )}
      </div>

      {componentEntries.length > 0 && (
        <div className="space-y-1 text-[11px]">
          {componentEntries.map(([name, c]) => (
            <div
              key={name}
              data-component-fired={String(c.fired)}
              className={`flex items-center justify-between gap-2 px-2 py-1 rounded ${
                c.fired
                  ? 'bg-amber-900/20 text-amber-100'
                  : 'bg-slate-800/40 text-slate-500 line-through opacity-70'
              }`}
            >
              <span className="flex items-center gap-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    c.fired ? 'bg-amber-400' : 'bg-slate-600'
                  }`}
                />
                <code className="text-xs no-underline">{name}</code>
                <span className="text-slate-500 no-underline">
                  {humanizeComponent(name) !== name ? `· ${humanizeComponent(name)}` : ''}
                </span>
              </span>
              <span className="font-mono no-underline">
                {c.fired ? '+' : ''}{c.contribution} / {c.weight}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
