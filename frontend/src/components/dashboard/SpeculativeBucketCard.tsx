/**
 * SpeculativeBucketCard
 *
 * Dashboard card showing the account-level speculative bucket:
 * deployed cost basis vs configured allocation, with a separate
 * speculative-only PnL so losers don't hide inside the main portfolio PnL.
 *
 * Hidden when bucket_pct is 0 (unconfigured — no need to take up space).
 *
 * See PRPs/high-risk-doubling-preset.md §Task D3.
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Flame } from 'lucide-react'
import { speculativeBucketApi, positionsApi } from '../../services/api'

interface Props {
  accountId: number | null
}

const SPECULATIVE_BUCKET_STALE_MS = 30_000

const isSpeculativePosition = (p: { strategy_config_snapshot?: Record<string, unknown> | null }) => {
  // Speculative preset stringifies the flag for PG/JSON-path compatibility —
  // tolerate boolean too in case any paper-trade path stored it differently.
  const flag = p.strategy_config_snapshot?.is_speculative
  return flag === true || flag === 'true'
}

export function SpeculativeBucketCard({ accountId }: Props) {
  const { data: bucket } = useQuery({
    queryKey: ['speculative-bucket', accountId],
    queryFn: () => {
      if (accountId == null) return null
      return speculativeBucketApi.get(accountId)
    },
    enabled: accountId != null,
    staleTime: SPECULATIVE_BUCKET_STALE_MS,
    refetchOnWindowFocus: false,
  })

  const { data: closedPositions = [] } = useQuery({
    queryKey: ['closed-positions-speculative', accountId],
    queryFn: () => positionsApi.getAll('closed', 1000, accountId ?? undefined),
    enabled: accountId != null && !!bucket && bucket.bucket_pct > 0,
    staleTime: SPECULATIVE_BUCKET_STALE_MS,
    refetchOnWindowFocus: false,
  })

  const speculativePnl = useMemo(() => {
    let total = 0
    for (const p of closedPositions) {
      if (isSpeculativePosition(p)) {
        total += p.profit_usd || 0
      }
    }
    return total
  }, [closedPositions])

  // Bucket either not fetched yet or not configured — do not render the card.
  if (!bucket || bucket.bucket_pct <= 0) return null

  const deployedPct = bucket.bucket_usd > 0
    ? Math.min(100, Math.round((bucket.deployed_cost_basis_usd / bucket.bucket_usd) * 100))
    : 0

  const pnlClass = speculativePnl >= 0 ? 'text-green-400' : 'text-red-400'
  const pnlPrefix = speculativePnl >= 0 ? '+' : ''

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-amber-700/40">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Flame className="w-5 h-5 text-amber-400" />
          <h3 className="text-lg font-semibold text-white">Speculative Bucket</h3>
        </div>
        <span className={`text-sm font-mono ${pnlClass}`} data-testid="speculative-pnl">
          {pnlPrefix}${speculativePnl.toFixed(2)}
        </span>
      </div>

      <div className="space-y-2">
        <div className="text-sm text-slate-300">
          <span className="font-mono text-white">
            ${bucket.deployed_cost_basis_usd.toFixed(2)}
          </span>{' '}
          / <span className="font-mono">${bucket.bucket_usd.toFixed(2)}</span>{' '}
          <span className="text-slate-500 text-xs ml-1">
            ({bucket.bucket_pct.toFixed(1)}% of account)
          </span>
        </div>

        <div
          role="progressbar"
          aria-valuenow={deployedPct}
          aria-valuemin={0}
          aria-valuemax={100}
          className="h-2 bg-slate-700 rounded overflow-hidden"
        >
          <div
            className="h-full bg-amber-500 transition-all"
            style={{ width: `${deployedPct}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>
            <span className="text-amber-300 font-mono">
              ${bucket.available_usd.toFixed(2)}
            </span>{' '}
            available
          </span>
          <span>
            {bucket.active_bot_count} bot{bucket.active_bot_count !== 1 ? 's' : ''} •{' '}
            {bucket.open_position_count} open
          </span>
        </div>

        {bucket.warnings && bucket.warnings.length > 0 && (
          <div className="mt-3 space-y-2">
            {bucket.warnings.map((w) => (
              <div
                key={w.code}
                data-testid={`speculative-bucket-warning-${w.code}`}
                className="flex gap-2 p-2 rounded border border-amber-600/40 bg-amber-900/20 text-xs text-amber-200"
              >
                <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
                <span className="leading-relaxed">{w.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
