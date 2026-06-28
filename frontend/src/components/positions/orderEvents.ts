/**
 * Derive human-readable "order executed" timeline entries from a position's
 * trades, so the Decision History modal can show the real fills (base order,
 * each safety order, the close) — retroactively, for any bot type.
 *
 * Reasons are derived from the trade ledger itself: a safety order shows how
 * far the fill was from the running average entry (the price-deviation that
 * classic DCA triggers on), which is exactly the "why" a price-triggered
 * safety order never recorded as an indicator decision.
 */
import type { Trade } from '../../types'

export interface OrderEvent {
  kind: 'order'
  id: string
  timestamp: string
  side: string
  tradeType: string
  price: number
  baseAmount: number
  quoteAmount: number
  label: string
  reason: string
}

/** Build chronological order events from a position's trades. */
export function buildOrderEvents(trades: Trade[]): OrderEvent[] {
  if (!trades || trades.length === 0) return []

  // Oldest first so we can accumulate the running average entry price.
  const ordered = [...trades].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  )

  // The entry side is whatever the first fill was (buy for longs, sell for shorts).
  const entrySide = ordered[0].side
  const isLong = entrySide === 'buy'

  let entryBase = 0
  let entryQuote = 0
  let safetyCount = 0
  const events: OrderEvent[] = []

  for (const t of ordered) {
    const isEntry = t.side === entrySide
    let label: string
    let reason: string

    if (isEntry) {
      const avgBefore = entryBase > 0 ? entryQuote / entryBase : 0
      if (safetyCount === 0 && entryBase === 0) {
        label = 'Base order'
        reason = 'Opened position'
      } else {
        const levels = t.dca_levels && t.dca_levels > 1 ? t.dca_levels : 1
        const first = safetyCount + 1
        const last = safetyCount + levels
        label = levels > 1 ? `Safety orders #${first}–#${last}` : `Safety order #${first}`
        if (avgBefore > 0) {
          // Long: filled below the average; short: above. Show the favorable deviation.
          const devPct = isLong
            ? ((avgBefore - t.price) / avgBefore) * 100
            : ((t.price - avgBefore) / avgBefore) * 100
          const dir = isLong ? 'below' : 'above'
          reason = `${Math.abs(devPct).toFixed(2)}% ${dir} average entry`
        } else {
          reason = 'Averaged down'
        }
        safetyCount = last
      }
      entryBase += t.base_amount
      entryQuote += t.quote_amount
    } else {
      label = 'Position closed'
      reason = isLong ? 'Sold to close' : 'Bought to cover'
    }

    events.push({
      kind: 'order',
      id: `trade-${t.id}`,
      timestamp: t.timestamp,
      side: t.side,
      tradeType: t.trade_type,
      price: t.price,
      baseAmount: t.base_amount,
      quoteAmount: t.quote_amount,
      label,
      reason,
    })
  }

  return events
}
