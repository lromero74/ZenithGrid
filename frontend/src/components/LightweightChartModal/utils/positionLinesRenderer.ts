import { IChartApi, ISeriesApi, Time, LineStyle } from 'lightweight-charts'
import type { Position } from '../../../types'
import type { CandleData } from '../../../utils/indicators/types'
import { getFeeAdjustedProfitMultiplier } from '../../positions/positionUtils'

/**
 * Renders position reference lines on the chart
 * - Entry price line (orange)
 * - Target price line (green)
 * - Safety order lines (blue)
 * - DCA level lines (purple)
 */
export function addPositionLines(
  chartRef: IChartApi,
  position: Position | null | undefined,
  chartData: CandleData[],
  positionLinesRef: React.MutableRefObject<ISeriesApi<'Line'>[]>
): void {
  if (!position) return

  // Clear existing position lines
  positionLinesRef.current.forEach(series => {
    try {
      chartRef.removeSeries(series)
    } catch {
      // Series may already be removed
    }
  })
  positionLinesRef.current = []

  const avgBuyPrice = position.average_buy_price

  // Get profit target from strategy config (min_profit_percentage or take_profit_percentage)
  const profitTargetPercent = position.strategy_config_snapshot?.min_profit_percentage
    || position.strategy_config_snapshot?.take_profit_percentage
    || position.bot_config?.min_profit_percentage
    || position.bot_config?.take_profit_percentage
    || 2.0  // Default to 2% if not configured

  // Apply fee adjustment to profit target
  const targetPrice = avgBuyPrice * getFeeAdjustedProfitMultiplier(profitTargetPercent)

  // Entry price line (orange)
  const entrySeries = chartRef.addLineSeries({
    color: '#f59e0b',
    lineWidth: 2,
    lineStyle: LineStyle.Dashed,
    title: 'Entry',
    priceLineVisible: false,
    lastValueVisible: false,
  })
  const entryData = chartData.map(d => ({ time: d.time as Time, value: avgBuyPrice }))
  entrySeries.setData(entryData)
  positionLinesRef.current.push(entrySeries)

  // Target price line (green)
  const targetSeries = chartRef.addLineSeries({
    color: '#10b981',
    lineWidth: 2,
    lineStyle: LineStyle.Dashed,
    title: `Target (+${profitTargetPercent}%)`,
    priceLineVisible: false,
    lastValueVisible: false,
  })
  const targetData = chartData.map(d => ({ time: d.time as Time, value: targetPrice }))
  targetSeries.setData(targetData)
  positionLinesRef.current.push(targetSeries)

  // Safety order lines (blue) if configured
  if (position.bot_config?.safety_order_step_percentage && position.bot_config?.max_safety_orders) {
    const stepPercentage = position.bot_config.safety_order_step_percentage
    const maxSOs = Math.min(position.bot_config.max_safety_orders, 5) // Limit to 5 lines

    for (let i = 1; i <= maxSOs; i++) {
      const deviation = stepPercentage * i
      const soPrice = avgBuyPrice * (1 - deviation / 100)

      const soSeries = chartRef.addLineSeries({
        color: '#3b82f6',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        title: `SO${i}`,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      const soData = chartData.map(d => ({ time: d.time as Time, value: soPrice }))
      soSeries.setData(soData)
      positionLinesRef.current.push(soSeries)
    }
  }

  // DCA level lines (magenta) - show minimum price drops for next DCA orders
  const minPriceDropForDCA = position.strategy_config_snapshot?.min_price_drop_for_dca
    || position.bot_config?.min_price_drop_for_dca
  const maxDCAOrders = position.strategy_config_snapshot?.max_safety_orders
    || position.bot_config?.max_safety_orders
    || 3

  if (minPriceDropForDCA && position.status === 'open') {
    const maxDCA = Math.min(maxDCAOrders, 5) // Limit to 5 lines

    for (let i = 1; i <= maxDCA; i++) {
      const dropPercentage = minPriceDropForDCA * i
      const dcaPrice = avgBuyPrice * (1 - dropPercentage / 100)

      const dcaSeries = chartRef.addLineSeries({
        color: '#a855f7', // Purple/magenta to distinguish from safety orders
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        title: `DCA${i} (-${dropPercentage.toFixed(1)}%)`,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      const dcaData = chartData.map(d => ({ time: d.time as Time, value: dcaPrice }))
      dcaSeries.setData(dcaData)
      positionLinesRef.current.push(dcaSeries)
    }
  }
}
