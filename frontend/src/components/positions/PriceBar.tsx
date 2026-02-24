/**
 * Price Bar Component (Memoized)
 *
 * Displays price visualization with entry, current, target, and DCA levels.
 * Memoized to avoid recalculating complex price positions on every render.
 */

import { memo, useMemo } from 'react'
import { formatPrice } from './index'
import type { Position } from '../../types'

interface PriceBarProps {
  position: Position
  currentPrice: number
  pnl: {
    btc: number
    percent: number
    usd: number
    currentPrice: number
  } | null
  strategyConfig: any
  fundsUsedPercent: number
}

export const PriceBar = memo(({ position, currentPrice: _currentPrice, pnl, strategyConfig, fundsUsedPercent }: PriceBarProps) => {
  // Memoize all price calculations to avoid recalculating on every render
  const priceData = useMemo(() => {
    if (!pnl) return null

    const entryPrice = position.average_buy_price

    // Don't render price markers for new positions with no fills yet
    if (!entryPrice || entryPrice === 0) {
      return null
    }

    const currentPriceValue = pnl.currentPrice
    // Use bot's min_profit_percentage setting instead of hardcoded 2%
    const minProfitPercent = strategyConfig.min_profit_percentage || 1.5
    const targetPrice = entryPrice * (1 + minProfitPercent / 100)

    // Calculate DCA levels using price_deviation and step_scale
    const priceDeviation = strategyConfig.price_deviation || 2.0
    const stepScale = strategyConfig.safety_order_step_scale || 1.0
    const maxDCAOrders = strategyConfig.max_safety_orders || 3
    const completedDCAs = Math.max(0, (position.trade_count || 0) - 1)

    // Use the correct reference price based on config
    // base_order: first buy price, average_price: average entry, last_buy: last buy price
    const dcaTargetRef = strategyConfig.dca_target_reference || 'average_price'
    let referencePrice = entryPrice // default: average_price
    if (dcaTargetRef === 'base_order' && position.first_buy_price) {
      referencePrice = position.first_buy_price
    } else if (dcaTargetRef === 'last_buy' && position.last_buy_price) {
      referencePrice = position.last_buy_price
    }
    // For average_price or if first/last prices not available, use entryPrice (average)

    // Calculate all remaining DCA prices
    const dcaPrices: { level: number; price: number }[] = []
    for (let dcaNum = completedDCAs + 1; dcaNum <= maxDCAOrders; dcaNum++) {
      // Same formula as backend: calculate_safety_order_price
      let totalDeviation = 0
      for (let i = 0; i < dcaNum; i++) {
        if (i === 0) {
          totalDeviation += priceDeviation
        } else {
          totalDeviation += priceDeviation * Math.pow(stepScale, i)
        }
      }
      const dcaPrice = referencePrice * (1 - totalDeviation / 100)
      dcaPrices.push({ level: dcaNum, price: dcaPrice })
    }

    // Get lowest DCA price for range calculation
    const lowestDCAPrice = dcaPrices.length > 0 ? dcaPrices[dcaPrices.length - 1].price : null

    const defaultMin = entryPrice * 0.95
    const defaultMax = entryPrice * 1.05
    // Include lowest DCA price in range calculation so all DCAs are visible
    const minPrice = lowestDCAPrice
      ? Math.min(defaultMin, currentPriceValue * 0.98, lowestDCAPrice * 0.98)
      : Math.min(defaultMin, currentPriceValue * 0.98)
    const maxPrice = Math.max(defaultMax, targetPrice * 1.01, currentPriceValue * 1.02)
    const priceRange = maxPrice - minPrice

    const entryPosition = ((entryPrice - minPrice) / priceRange) * 100
    const currentPosition = ((currentPriceValue - minPrice) / priceRange) * 100
    const targetPosition = ((targetPrice - minPrice) / priceRange) * 100

    const isProfit = currentPriceValue >= entryPrice
    const fillStart = Math.min(entryPosition, currentPosition)
    const fillWidth = Math.abs(currentPosition - entryPosition)

    // Collision detection - if labels are too close (< 15%), stagger them
    const buyCurrentGap = Math.abs(currentPosition - entryPosition)
    const currentTargetGap = Math.abs(targetPosition - currentPosition)
    const buyTargetGap = Math.abs(targetPosition - entryPosition)

    // Determine positioning: top or bottom
    const buyPos: 'top' | 'bottom' = 'top'
    let currentPos = 'top'
    let targetPos = 'top'

    // If buy and current are close, put current below
    if (buyCurrentGap < 15) {
      currentPos = 'bottom'
    }

    // If current and target are close, alternate
    if (currentTargetGap < 15) {
      if (currentPos === 'top') {
        targetPos = 'bottom'
      } else {
        targetPos = 'top'
      }
    }

    // If buy and target are close but current is far, alternate them
    if (buyTargetGap < 15 && buyCurrentGap >= 15 && currentTargetGap >= 15) {
      targetPos = 'bottom'
    }

    return {
      entryPrice,
      currentPriceValue,
      targetPrice,
      dcaPrices,
      minPrice,
      priceRange,
      entryPosition,
      currentPosition,
      targetPosition,
      isProfit,
      fillStart,
      fillWidth,
      buyPos,
      currentPos,
      targetPos,
    }
  }, [position, pnl, strategyConfig])

  if (!pnl || !priceData) {
    return null
  }

  return (
    <div>
      <div className="mb-1">
        <span className="text-[10px] text-blue-400">Filled {fundsUsedPercent.toFixed(2)}%</span>
      </div>
      {/* Price Bar */}
      <div className="relative w-full pt-6 pb-6">
        <div className="relative w-full h-2 bg-slate-700 rounded-full">
          {/* Fill color between entry and current */}
          <div
            className={`absolute h-full rounded-full ${priceData.isProfit ? 'bg-green-500' : 'bg-red-500'}`}
            style={{
              left: `${Math.max(0, Math.min(100, priceData.fillStart))}%`,
              width: `${Math.max(0, Math.min(100 - priceData.fillStart, priceData.fillWidth))}%`
            }}
          />

          {/* Buy Price */}
          <div
            className="absolute flex flex-col items-center"
            style={{
              left: `${Math.max(0, Math.min(100, priceData.entryPosition))}%`,
              transform: 'translateX(-50%)',
              ...(priceData.buyPos === 'top' ? { bottom: '100%' } : { top: '100%' })
            }}
          >
            <div className={`text-[9px] text-slate-400 whitespace-nowrap ${priceData.buyPos === 'top' ? 'mb-0.5' : 'mt-0.5'}`}>
              Buy {formatPrice(priceData.entryPrice, position.product_id || 'ETH-BTC')}
            </div>
            {priceData.buyPos === 'top' && <div className="w-px h-3 bg-slate-400" />}
          </div>

          {/* Current Price */}
          <div
            className="absolute flex flex-col items-center"
            style={{
              left: `${Math.max(0, Math.min(100, priceData.currentPosition))}%`,
              transform: 'translateX(-50%)',
              ...(priceData.currentPos === 'top' ? { bottom: '100%' } : { top: '100%' })
            }}
          >
            {priceData.currentPos === 'bottom' && <div className={`w-px h-3 ${priceData.isProfit ? 'bg-green-400' : 'bg-red-400'}`} />}
            <div className={`text-[9px] whitespace-nowrap font-semibold ${priceData.isProfit ? 'text-green-400' : 'text-red-400'} ${priceData.currentPos === 'top' ? 'mb-0.5' : 'mt-0.5'}`}>
              {pnl.percent >= 0 ? '+' : ''}{pnl.percent.toFixed(2)}% {formatPrice(priceData.currentPriceValue, position.product_id || 'ETH-BTC')}
            </div>
            {priceData.currentPos === 'top' && <div className={`w-px h-3 ${priceData.isProfit ? 'bg-green-400' : 'bg-red-400'}`} />}
          </div>

          {/* Target Price (MP) */}
          <div
            className="absolute flex flex-col items-center"
            style={{
              left: `${Math.max(0, Math.min(100, priceData.targetPosition))}%`,
              transform: 'translateX(-50%)',
              ...(priceData.targetPos === 'top' ? { bottom: '100%' } : { top: '100%' })
            }}
          >
            {priceData.targetPos === 'bottom' && <div className="w-px h-3 bg-emerald-400" />}
            <div className={`text-[9px] text-emerald-400 whitespace-nowrap ${priceData.targetPos === 'top' ? 'mb-0.5' : 'mt-0.5'}`}>
              MP {formatPrice(priceData.targetPrice, position.product_id || 'ETH-BTC')}
            </div>
            {priceData.targetPos === 'top' && <div className="w-px h-3 bg-emerald-400" />}
          </div>

          {/* DCA Level Tick Marks - show all remaining DCA targets */}
          {priceData.dcaPrices.map((dca, idx) => {
            const dcaBarPosition = ((dca.price - priceData.minPrice) / priceData.priceRange) * 100
            // Alternate label positions to avoid overlap
            const showLabel = idx === 0 || idx === priceData.dcaPrices.length - 1 || priceData.dcaPrices.length <= 3
            return (
              <div
                key={`dca-${dca.level}`}
                className="absolute flex flex-col items-center"
                style={{
                  left: `${Math.max(0, Math.min(100, dcaBarPosition))}%`,
                  transform: 'translateX(-50%)',
                  top: '100%'
                }}
              >
                <div className={`w-px ${idx === 0 ? 'h-3' : 'h-2'} bg-purple-400`} />
                {showLabel && (
                  <div className="text-[8px] text-purple-400 whitespace-nowrap mt-0.5">
                    SO{dca.level}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
})

PriceBar.displayName = 'PriceBar'
