import { IChartApi, ISeriesApi, Time, LineStyle } from 'lightweight-charts'
import type { Position } from '../../../types'
import type { CandleData } from '../../../utils/indicators/types'
import { getFeeAdjustedProfitMultiplier, calculateSOLevels } from '../../positions/positionUtils'

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

  // Safety order lines — calculated to match actual backend trigger prices.
  // Uses strategy_config_snapshot (frozen at deal open) with correct reference
  // price (average/base_order/last_buy), geometric step scale, and skips
  // already-filled SOs so only remaining unfilled levels are shown.
  const soLevels = calculateSOLevels(position)
  const visibleSOLevels = soLevels.slice(0, 5) // cap at 5 lines for readability

  for (const level of visibleSOLevels) {
    const soSeries = chartRef.addLineSeries({
      color: '#3b82f6',
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      title: `SO${level.soNumber}`,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    soSeries.setData(chartData.map(d => ({ time: d.time as Time, value: level.triggerPrice })))
    positionLinesRef.current.push(soSeries)
  }
}
