import type { Position } from '../../types'
import { authFetch } from '../../services/api'

/**
 * Calculate unrealized P&L for an open position
 */
export const calculateUnrealizedPnL = (position: Position, currentPrice?: number, btcUsdPrice?: number) => {
  if (position.status !== 'open') return null

  // Use real-time price if available, otherwise fall back to average buy price
  const price = currentPrice || position.average_buy_price
  const currentValue = position.total_base_acquired * price
  const costBasis = position.total_quote_spent
  const unrealizedPnL = currentValue - costBasis

  // Prevent division by zero for new positions with no trades yet
  const unrealizedPnLPercent = costBasis > 0 ? (unrealizedPnL / costBasis) * 100 : 0

  const quoteCurrency = position.product_id?.split('-')[1] || 'BTC'
  let usd: number
  if (quoteCurrency === 'USD' || quoteCurrency === 'USDC' || quoteCurrency === 'USDT') {
    usd = unrealizedPnL
  } else if (quoteCurrency === 'BTC') {
    usd = unrealizedPnL * (btcUsdPrice || position.btc_usd_price_at_open || 0)
  } else {
    usd = 0 // Other quotes (ETH, etc.) — no conversion yet
  }

  return {
    quote: unrealizedPnL,
    quoteCurrency,
    percent: unrealizedPnLPercent,
    usd,
    currentPrice: price
  }
}

/**
 * Calculate overall statistics for all open positions
 */
export const calculateOverallStats = (openPositions: (Position & { _cachedPnL?: any })[]) => {
  // Calculate reserved (locked) funds and total budget by quote currency
  const reservedByQuote: Record<string, number> = {}
  const totalBudgetByQuote: Record<string, number> = {}

  openPositions.forEach(pos => {
    // Extract quote currency from product_id (e.g., "ETH-BTC" -> "BTC", "BTC-USD" -> "USD")
    const quoteCurrency = pos.product_id?.split('-')[1] || 'BTC'
    if (!reservedByQuote[quoteCurrency]) {
      reservedByQuote[quoteCurrency] = 0
    }
    if (!totalBudgetByQuote[quoteCurrency]) {
      totalBudgetByQuote[quoteCurrency] = 0
    }
    reservedByQuote[quoteCurrency] += pos.total_quote_spent
    totalBudgetByQuote[quoteCurrency] += pos.max_quote_allowed || 0
  })

  const uPnLByQuote: Record<string, number> = {}
  let totalUPnLUSD = 0
  openPositions.forEach(pos => {
    const pnl = pos._cachedPnL
    if (pnl) {
      const qc = pnl.quoteCurrency || 'BTC'
      uPnLByQuote[qc] = (uPnLByQuote[qc] || 0) + (pnl.quote || 0)
      totalUPnLUSD += (pnl.usd || 0)
    }
  })

  return {
    activeTrades: openPositions.length,
    reservedByQuote, // Reserved funds broken down by quote currency
    totalBudgetByQuote, // Total assigned budget (max_quote_allowed) by quote currency
    uPnLByQuote,
    uPnLUSD: totalUPnLUSD
  }
}

/**
 * Check slippage before market close and show warning if needed
 */
export const checkSlippageBeforeMarketClose = async (
  positionId: number,
  onShowWarning: (slippage: any, positionId: number) => void,
  onProceedDirectly: (positionId: number) => void
) => {
  try {
    const response = await authFetch(`/api/positions/${positionId}/slippage-check`)
    const slippage = await response.json()

    if (slippage.show_warning) {
      // Show slippage warning modal
      onShowWarning(slippage, positionId)
    } else {
      // No significant slippage, proceed directly to close confirmation
      onProceedDirectly(positionId)
    }
  } catch (err: any) {
    console.error('Error checking slippage:', err)
    // If slippage check fails, still allow closing (fallback)
    onProceedDirectly(positionId)
  }
}
