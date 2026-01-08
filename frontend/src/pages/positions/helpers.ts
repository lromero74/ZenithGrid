import type { Position } from '../../types'

/**
 * Calculate unrealized P&L for an open position
 */
export const calculateUnrealizedPnL = (position: Position, currentPrice?: number) => {
  if (position.status !== 'open') return null

  // Use real-time price if available, otherwise fall back to average buy price
  const price = currentPrice || position.average_buy_price
  const currentValue = position.total_base_acquired * price
  const costBasis = position.total_quote_spent
  const unrealizedPnL = currentValue - costBasis

  // Prevent division by zero for new positions with no trades yet
  const unrealizedPnLPercent = costBasis > 0 ? (unrealizedPnL / costBasis) * 100 : 0

  return {
    btc: unrealizedPnL,
    percent: unrealizedPnLPercent,
    usd: unrealizedPnL * (position.btc_usd_price_at_open || 0),
    currentPrice: price
  }
}

/**
 * Calculate overall statistics for all open positions
 */
export const calculateOverallStats = (openPositions: (Position & { _cachedPnL?: any })[]) => {
  const totalFundsLocked = openPositions.reduce((sum, pos) => sum + pos.total_quote_spent, 0)
  const totalUPnL = openPositions.reduce((sum, pos) => {
    return sum + (pos._cachedPnL?.btc || 0)
  }, 0)
  const totalUPnLUSD = openPositions.reduce((sum, pos) => {
    return sum + (pos._cachedPnL?.usd || 0)
  }, 0)

  return {
    activeTrades: openPositions.length,
    fundsLocked: totalFundsLocked,
    uPnL: totalUPnL,
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
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/positions/${positionId}/slippage-check`)
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
