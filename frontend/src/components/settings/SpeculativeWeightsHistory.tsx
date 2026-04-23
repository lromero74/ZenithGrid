/**
 * SpeculativeWeightsHistory
 *
 * Read-only table of past calibration proposals for the selected account.
 * Surfaces "what changed when" from the auto-calibration pipeline — pairs
 * with the Speculative Bucket card in Settings.
 *
 * Hidden when no proposals exist, so fresh users don't see a dead panel.
 *
 * See PRPs/speculative-weights-auto-calibration.md §Task F10.
 */

import { useQuery } from '@tanstack/react-query'
import { History } from 'lucide-react'
import { speculativeBucketApi, type SpeculativeWeightsProposal } from '../../services/api'

interface Props {
  accountId: number | null
}

const STATUS_STYLES: Record<string, string> = {
  applied: 'text-green-400 bg-green-900/30 border-green-700/50',
  pending: 'text-amber-300 bg-amber-900/30 border-amber-700/50',
  rejected: 'text-slate-400 bg-slate-800 border-slate-700',
  superseded: 'text-slate-400 bg-slate-800 border-slate-700',
  reverted: 'text-red-300 bg-red-900/30 border-red-700/50',
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function summarizeDeltas(p: SpeculativeWeightsProposal): Array<{ name: string; delta: number }> {
  const deltas: Array<{ name: string; delta: number }> = []
  for (const [name, baseline] of Object.entries(p.baseline_weights)) {
    const proposed = p.proposed_weights[name] ?? baseline
    const delta = proposed - baseline
    if (delta !== 0) deltas.push({ name, delta })
  }
  // Largest-magnitude changes first.
  deltas.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
  return deltas
}

export function SpeculativeWeightsHistory({ accountId }: Props) {
  const { data: proposals = [] } = useQuery({
    queryKey: ['speculative-weights-proposals', accountId],
    queryFn: () => {
      if (accountId == null) return []
      return speculativeBucketApi.listWeightsProposals(accountId)
    },
    enabled: accountId != null,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })

  if (proposals.length === 0) return null

  return (
    <div
      className="mt-4 border-t border-slate-700 pt-4"
      data-testid="speculative-weights-history"
    >
      <div className="flex items-center gap-2 text-sm font-medium text-slate-300 mb-3">
        <History className="w-4 h-4 text-slate-400" />
        <span>Weight calibration history</span>
        <span className="text-xs text-slate-500">({proposals.length})</span>
      </div>
      <div className="space-y-2">
        {proposals.map((p) => {
          const deltas = summarizeDeltas(p)
          const statusClass = STATUS_STYLES[p.status] ?? STATUS_STYLES.rejected
          return (
            <div
              key={p.id}
              data-testid={`proposal-${p.id}`}
              className="flex items-start gap-3 p-2 bg-slate-800/60 rounded text-xs"
            >
              <span
                className={`px-2 py-0.5 rounded border text-[10px] uppercase tracking-wide font-semibold ${statusClass}`}
              >
                {p.status}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-slate-300">
                  <span className="font-mono">{formatDate(p.decided_at || p.created_at)}</span>{' '}
                  <span className="text-slate-500">
                    · {p.sample_size} positions · win rate {p.overall_win_rate_pct.toFixed(1)}%
                  </span>
                </div>
                {deltas.length > 0 ? (
                  <div className="mt-1 flex flex-wrap gap-x-3 text-slate-400">
                    {deltas.slice(0, 4).map((d) => (
                      <span key={d.name}>
                        <span className="text-slate-500">{d.name}</span>{' '}
                        <span className={d.delta > 0 ? 'text-green-400' : 'text-red-400'}>
                          {d.delta > 0 ? '+' : ''}{d.delta}
                        </span>
                      </span>
                    ))}
                    {deltas.length > 4 && (
                      <span className="text-slate-500">+{deltas.length - 4} more</span>
                    )}
                  </div>
                ) : (
                  <div className="mt-1 text-slate-500">no weight changes</div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
