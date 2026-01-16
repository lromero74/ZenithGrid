/**
 * Grid Visualizer Component
 *
 * Displays a visual representation of grid trading levels, showing:
 * - Grid levels chart with current price indicator
 * - Buy/sell levels with fill status
 * - Grid performance stats
 * - Detailed levels table
 */

import { useState } from 'react'
import { TrendingUp, TrendingDown, Activity, DollarSign, Calendar, Grid3X3 } from 'lucide-react'

interface GridLevel {
  level_index: number
  price: number
  order_type: 'buy' | 'sell'
  order_id?: string
  status: 'pending' | 'filled' | 'cancelled'
  position_id?: number
  filled_at?: string
}

interface GridState {
  initialized_at: string
  current_range_upper: number
  current_range_lower: number
  grid_levels: GridLevel[]
  last_rebalance?: string
  total_profit_quote?: number
  breakout_count?: number
}

interface GridVisualizerProps {
  gridState: GridState
  currentPrice: number
  productId: string
}

export function GridVisualizer({ gridState, currentPrice, productId }: GridVisualizerProps) {
  const [showLevelsTable, setShowLevelsTable] = useState(true)

  // Calculate stats
  const totalLevels = gridState.grid_levels.length
  const filledLevels = gridState.grid_levels.filter(l => l.status === 'filled').length
  const pendingLevels = gridState.grid_levels.filter(l => l.status === 'pending').length
  const buyLevels = gridState.grid_levels.filter(l => l.order_type === 'buy')
  const sellLevels = gridState.grid_levels.filter(l => l.order_type === 'sell')
  const filledBuys = buyLevels.filter(l => l.status === 'filled').length
  const filledSells = sellLevels.filter(l => l.status === 'filled').length

  // Calculate price range for visualization
  const priceRange = gridState.current_range_upper - gridState.current_range_lower
  const priceToPercent = (price: number) => {
    return ((price - gridState.current_range_lower) / priceRange) * 100
  }

  // Sort levels by price (descending for display)
  const sortedLevels = [...gridState.grid_levels].sort((a, b) => b.price - a.price)

  // Get quote currency
  const quoteCurrency = productId.split('-')[1] || 'BTC'

  return (
    <div className="space-y-4">
      {/* Grid Stats Panel */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-slate-700/50 rounded-lg p-3">
          <div className="flex items-center space-x-2 mb-1">
            <Grid3X3 className="w-4 h-4 text-slate-400" />
            <span className="text-xs text-slate-400">Total Levels</span>
          </div>
          <p className="text-lg font-bold text-white">{totalLevels}</p>
          <p className="text-xs text-slate-500">
            {buyLevels.length} buy / {sellLevels.length} sell
          </p>
        </div>

        <div className="bg-slate-700/50 rounded-lg p-3">
          <div className="flex items-center space-x-2 mb-1">
            <Activity className="w-4 h-4 text-green-400" />
            <span className="text-xs text-slate-400">Filled</span>
          </div>
          <p className="text-lg font-bold text-green-400">{filledLevels}</p>
          <p className="text-xs text-slate-500">
            {filledBuys} buy / {filledSells} sell
          </p>
        </div>

        <div className="bg-slate-700/50 rounded-lg p-3">
          <div className="flex items-center space-x-2 mb-1">
            <Calendar className="w-4 h-4 text-yellow-400" />
            <span className="text-xs text-slate-400">Pending</span>
          </div>
          <p className="text-lg font-bold text-yellow-400">{pendingLevels}</p>
          <p className="text-xs text-slate-500">
            {buyLevels.filter(l => l.status === 'pending').length} buy /
            {sellLevels.filter(l => l.status === 'pending').length} sell
          </p>
        </div>

        <div className="bg-slate-700/50 rounded-lg p-3">
          <div className="flex items-center space-x-2 mb-1">
            <DollarSign className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-slate-400">Grid Profit</span>
          </div>
          <p className="text-lg font-bold text-blue-400">
            {gridState.total_profit_quote?.toFixed(8) || '0.00000000'}
          </p>
          <p className="text-xs text-slate-500">{quoteCurrency}</p>
        </div>
      </div>

      {/* Visual Grid Chart */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
        <div className="flex items-center justify-between mb-4">
          <h4 className="font-medium text-white">Grid Levels</h4>
          <div className="flex items-center space-x-4 text-xs">
            <div className="flex items-center space-x-1">
              <div className="w-3 h-0.5 bg-green-500"></div>
              <span className="text-slate-400">Buy</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-3 h-0.5 bg-red-500"></div>
              <span className="text-slate-400">Sell</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-3 h-0.5 bg-orange-500"></div>
              <span className="text-slate-400">Current Price</span>
            </div>
          </div>
        </div>

        {/* Price range labels */}
        <div className="flex justify-between text-xs text-slate-400 mb-2">
          <span>{gridState.current_range_lower.toFixed(8)}</span>
          <span className="text-orange-400 font-medium">{currentPrice.toFixed(8)}</span>
          <span>{gridState.current_range_upper.toFixed(8)}</span>
        </div>

        {/* Grid visualization */}
        <div className="relative h-64 bg-slate-900/50 rounded border border-slate-700">
          {/* Grid levels */}
          {gridState.grid_levels.map((level, idx) => {
            const position = priceToPercent(level.price)
            const isBuy = level.order_type === 'buy'
            const isFilled = level.status === 'filled'
            const isPending = level.status === 'pending'

            return (
              <div
                key={idx}
                className="absolute left-0 right-0 flex items-center"
                style={{ bottom: `${position}%` }}
              >
                {/* Level line */}
                <div
                  className={`flex-1 ${
                    isFilled
                      ? (isBuy ? 'border-green-500' : 'border-red-500')
                      : 'border-slate-600'
                  } ${
                    isPending ? 'border-dashed' : ''
                  }`}
                  style={{ borderTopWidth: '2px' }}
                />

                {/* Level indicator */}
                <div className={`absolute -left-1 w-2 h-2 rounded-full ${
                  isFilled
                    ? (isBuy ? 'bg-green-500' : 'bg-red-500')
                    : 'bg-slate-600'
                }`} />

                {/* Price label */}
                <div className={`absolute -right-20 text-xs whitespace-nowrap ${
                  isFilled
                    ? (isBuy ? 'text-green-400' : 'text-red-400')
                    : 'text-slate-500'
                }`}>
                  {level.price.toFixed(8)}
                </div>
              </div>
            )
          })}

          {/* Current price indicator */}
          <div
            className="absolute left-0 right-0 flex items-center pointer-events-none"
            style={{ bottom: `${priceToPercent(currentPrice)}%` }}
          >
            <div className="flex-1 border-orange-500" style={{ borderTopWidth: '2px' }} />
            <div className="absolute -left-2 w-4 h-4 bg-orange-500 rounded-full animate-pulse" />
          </div>
        </div>

        {/* Range info */}
        <div className="mt-4 pt-4 border-t border-slate-700 grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-slate-400">Range:</span>
            <span className="ml-2 text-white font-mono">
              {gridState.current_range_lower.toFixed(8)} - {gridState.current_range_upper.toFixed(8)}
            </span>
          </div>
          <div>
            <span className="text-slate-400">Breakouts:</span>
            <span className="ml-2 text-white">{gridState.breakout_count || 0}</span>
          </div>
        </div>
      </div>

      {/* Grid Levels Table Toggle */}
      <button
        onClick={() => setShowLevelsTable(!showLevelsTable)}
        className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium text-white transition-colors"
      >
        {showLevelsTable ? 'Hide' : 'Show'} Grid Levels Table ({totalLevels} levels)
      </button>

      {/* Grid Levels Table */}
      {showLevelsTable && (
        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-700/50 border-b border-slate-700">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Level</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Price</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Filled At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {sortedLevels.map((level) => (
                  <tr key={level.level_index} className="hover:bg-slate-700/30">
                    <td className="px-4 py-3 text-slate-300">#{level.level_index + 1}</td>
                    <td className="px-4 py-3 font-mono text-white">{level.price.toFixed(8)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center space-x-1">
                        {level.order_type === 'buy' ? (
                          <>
                            <TrendingDown className="w-4 h-4 text-green-400" />
                            <span className="text-green-400 font-medium">BUY</span>
                          </>
                        ) : (
                          <>
                            <TrendingUp className="w-4 h-4 text-red-400" />
                            <span className="text-red-400 font-medium">SELL</span>
                          </>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                        level.status === 'filled'
                          ? 'bg-green-600/20 text-green-400'
                          : level.status === 'pending'
                          ? 'bg-yellow-600/20 text-yellow-400'
                          : 'bg-slate-600/20 text-slate-400'
                      }`}>
                        {level.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {level.filled_at ? (
                        new Date(level.filled_at).toLocaleString()
                      ) : (
                        <span className="text-slate-600">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
