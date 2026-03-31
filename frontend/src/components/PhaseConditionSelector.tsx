import { Plus, X } from 'lucide-react'

// Condition types for indicator-based strategies
export type ConditionType =
  | 'rsi'
  | 'macd'
  | 'bb_percent'
  | 'ema_cross'
  | 'sma_cross'
  | 'vwap'
  | 'price_change'
  | 'stochastic'
  | 'volume'
  | 'volume_rsi'
  | 'gap_fill_pct'
  // Aggregate indicators (return 0 or 1)
  | 'ai_buy'
  | 'ai_sell'
  | 'bull_flag'
  | 'vwap_bounce_up'
  | 'vwap_bounce_down'
  | 'qfl_crack'

export type Operator = 'greater_than' | 'less_than' | 'greater_equal' | 'less_equal' | 'crossing_above' | 'crossing_below' | 'increasing' | 'decreasing'

export type Timeframe =
  | 'ONE_MINUTE'
  | 'THREE_MINUTE'
  | 'FIVE_MINUTE'
  | 'FIFTEEN_MINUTE'
  | 'THIRTY_MINUTE'
  | 'ONE_HOUR'
  | 'TWO_HOUR'
  | 'SIX_HOUR'
  | 'ONE_DAY'
  | 'TWO_DAY'
  | 'THREE_DAY'
  | 'ONE_WEEK'
  | 'TWO_WEEK'
  | 'ONE_MONTH'

export interface PhaseCondition {
  id: string
  type: ConditionType
  operator: Operator
  value: number
  timeframe: Timeframe
  period?: number
  fast_period?: number
  slow_period?: number
  signal_period?: number
  std_dev?: number
  // QFL-specific
  lookback_candles?: number
  bounce_pct?: number
  crack_pct?: number
}

interface PhaseConditionSelectorProps {
  title: string
  description: string
  conditions: PhaseCondition[]
  onChange: (conditions: PhaseCondition[]) => void
  allowMultiple?: boolean
  logic?: 'and' | 'or'
  onLogicChange?: (logic: 'and' | 'or') => void
}

// Available condition types for each phase
const CONDITION_TYPES: Record<ConditionType, { label: string; description: string; isAggregate?: boolean }> = {
  rsi: {
    label: 'RSI (Relative Strength Index)',
    description: 'Momentum oscillator (0-100). Oversold < 30, Overbought > 70',
  },
  macd: {
    label: 'MACD',
    description: 'Trend-following momentum. Histogram crossing above/below 0',
  },
  bb_percent: {
    label: 'Bollinger Band %',
    description: 'Position within bands. 0% = lower band, 100% = upper band',
  },
  ema_cross: {
    label: 'EMA Cross',
    description: 'Price crossing exponential moving average',
  },
  sma_cross: {
    label: 'SMA Cross',
    description: 'Price crossing simple moving average',
  },
  vwap: {
    label: 'VWAP',
    description: 'Price vs. Volume-Weighted Average Price. Use crossing/above/below operators.',
  },
  price_change: {
    label: 'Price Change %',
    description: 'Percentage change from previous candle',
  },
  stochastic: {
    label: 'Stochastic',
    description: 'Momentum oscillator (0-100). Oversold < 20, Overbought > 80',
  },
  volume: {
    label: 'Volume',
    description: 'Trading volume threshold',
  },
  volume_rsi: {
    label: 'Volume RSI',
    description: 'RSI applied to volume (0-100). >70 = volume surging, <30 = volume drying up.',
  },
  gap_fill_pct: {
    label: 'Gap Fill %',
    description: 'Percentage of synthetic/filler candles (0-100). High values = unreliable data.',
  },
  // Aggregate indicators (return 0 or 1)
  ai_buy: {
    label: 'AI Buy Signal',
    description: 'Multi-timeframe confluence analysis. Returns 1 when buy conditions align.',
    isAggregate: true,
  },
  ai_sell: {
    label: 'AI Sell Signal',
    description: 'Multi-timeframe confluence analysis. Returns 1 when sell conditions align.',
    isAggregate: true,
  },
  bull_flag: {
    label: 'Bull Flag Pattern',
    description: 'Technical pattern detection. Returns 1 when bull flag is identified.',
    isAggregate: true,
  },
  vwap_bounce_up: {
    label: 'VWAP Bounce Up',
    description: 'Bullish: price retested VWAP from above (wick touch) and last closed candle closed back above.',
    isAggregate: true,
  },
  vwap_bounce_down: {
    label: 'VWAP Bounce Down',
    description: 'Bearish: price retested VWAP from below (wick touch) and last closed candle closed back below.',
    isAggregate: true,
  },
  qfl_crack: {
    label: 'QFL Crack (Quick Fingers Luke)',
    description: 'Fires when price cracks below a historically validated support base. Classic panic-buy entry.',
    isAggregate: true,
  },
}

const OPERATORS: Record<Operator, string> = {
  greater_than: '>',
  less_than: '<',
  greater_equal: '≥',
  less_equal: '≤',
  crossing_above: 'Crossing Above',
  crossing_below: 'Crossing Below',
  increasing: 'Increasing',
  decreasing: 'Decreasing',
}

// Strength presets for increasing/decreasing operators
const STRENGTH_LEVELS: Record<string, { label: string; value: number }> = {
  any: { label: 'Any', value: 0 },
  mild: { label: 'Mild+ (>1%)', value: 1 },
  medium: { label: 'Medium+ (>2%)', value: 2 },
  strong: { label: 'Strong+ (>5%)', value: 5 },
  very_strong: { label: 'Very Strong (>10%)', value: 10 },
}


const TIMEFRAMES: Record<Timeframe, string> = {
  ONE_MINUTE: '1m',
  THREE_MINUTE: '3m*',  // * = synthetic, aggregated from 1-minute candles
  FIVE_MINUTE: '5m',
  FIFTEEN_MINUTE: '15m',
  THIRTY_MINUTE: '30m',
  ONE_HOUR: '1h',
  TWO_HOUR: '2h',
  SIX_HOUR: '6h',
  ONE_DAY: '1d',
  TWO_DAY: '2d*',      // * = synthetic, aggregated from 1-day candles
  THREE_DAY: '3d*',    // * = synthetic, aggregated from 1-day candles
  ONE_WEEK: '1w*',     // * = synthetic, aggregated from 1-day candles
  TWO_WEEK: '2w*',     // * = synthetic, aggregated from 1-day candles
  ONE_MONTH: '1M*',    // * = synthetic, aggregated from 1-day candles (30 days)
}

function PhaseConditionSelector({
  title,
  description,
  conditions,
  onChange,
  allowMultiple = true,
  logic = 'and',
  onLogicChange,
}: PhaseConditionSelectorProps) {
  const addCondition = () => {
    const newCondition: PhaseCondition = {
      id: `cond_${Date.now()}_${Math.random()}`,
      type: 'rsi',
      operator: 'less_than',
      value: 30,
      timeframe: 'FIVE_MINUTE',
      period: 14,
    }
    onChange([...conditions, newCondition])
  }

  const removeCondition = (id: string) => {
    onChange(conditions.filter((c) => c.id !== id))
  }

  const updateCondition = (id: string, updates: Partial<PhaseCondition>) => {
    onChange(
      conditions.map((c) => {
        if (c.id !== id) return c

        // When changing type, reset parameters to defaults
        if (updates.type && updates.type !== c.type) {
          const newCondition: PhaseCondition = {
            ...c,
            type: updates.type,
            timeframe: c.timeframe || 'FIVE_MINUTE',
          }

          // Set default parameters based on type
          switch (updates.type) {
            case 'rsi':
              newCondition.period = 14
              newCondition.operator = 'less_than'
              newCondition.value = 30
              break
            case 'macd':
              newCondition.fast_period = 12
              newCondition.slow_period = 26
              newCondition.signal_period = 9
              newCondition.operator = 'crossing_above'
              newCondition.value = 0
              break
            case 'bb_percent':
              newCondition.period = 20
              newCondition.std_dev = 2
              newCondition.operator = 'less_than'
              newCondition.value = 0
              break
            case 'ema_cross':
            case 'sma_cross':
              newCondition.period = 50
              newCondition.operator = 'crossing_above'
              newCondition.value = 0
              break
            case 'vwap':
              newCondition.operator = 'crossing_above'
              newCondition.value = 0
              break
            case 'stochastic':
              newCondition.period = 14
              newCondition.operator = 'less_than'
              newCondition.value = 20
              break
            case 'price_change':
              newCondition.operator = 'less_than'
              newCondition.value = -2
              break
            case 'volume':
              newCondition.operator = 'greater_than'
              newCondition.value = 1000000
              break
            case 'volume_rsi':
              newCondition.period = 14
              newCondition.operator = 'greater_than'
              newCondition.value = 70
              break
            case 'gap_fill_pct':
              newCondition.operator = 'less_than'
              newCondition.value = 50
              break
            // Aggregate indicators (return 0 or 1, compare to 1 for "is active")
            case 'ai_buy':
            case 'ai_sell':
            case 'bull_flag':
            case 'vwap_bounce_up':
            case 'vwap_bounce_down':
              newCondition.operator = 'greater_than'
              newCondition.value = 0  // > 0 means signal is active (equals 1)
              break
            case 'qfl_crack':
              newCondition.operator = 'greater_than'
              newCondition.value = 0
              newCondition.lookback_candles = 100
              newCondition.bounce_pct = 3.0
              newCondition.crack_pct = 2.0
              break
          }

          return newCondition
        }

        return { ...c, ...updates }
      })
    )
  }

  const renderConditionFields = (condition: PhaseCondition) => {
    switch (condition.type) {
      case 'rsi':
        return (
          <>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400 w-16">Period:</label>
              <input
                type="number"
                value={condition.period || 14}
                onChange={(e) =>
                  updateCondition(condition.id, { period: parseInt(e.target.value) })
                }
                min="2"
                max="100"
                className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <select
                value={condition.operator}
                onChange={(e) => {
                  const newOp = e.target.value as Operator
                  const updates: Partial<PhaseCondition> = { operator: newOp }
                  if ((newOp === 'increasing' || newOp === 'decreasing') &&
                      condition.operator !== 'increasing' && condition.operator !== 'decreasing') {
                    updates.value = 0
                  }
                  updateCondition(condition.id, updates)
                }}
                className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
              >
                <option value="greater_than">&gt;</option>
                <option value="greater_equal">≥</option>
                <option value="less_than">&lt;</option>
                <option value="less_equal">≤</option>
                <option value="crossing_above">Crossing Above</option>
                <option value="crossing_below">Crossing Below</option>
                <option value="increasing">Increasing</option>
                <option value="decreasing">Decreasing</option>
              </select>
              {condition.operator === 'increasing' || condition.operator === 'decreasing' ? (
                <select
                  value={condition.value || 0}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  className="bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                  title="Minimum % change strength"
                >
                  {Object.entries(STRENGTH_LEVELS).map(([key, { label, value }]) => (
                    <option key={key} value={value}>{label}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="number"
                  value={condition.value}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  min="0"
                  max="100"
                  step="1"
                  className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
              )}
            </div>
          </>
        )

      case 'macd':
        return (
          <>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex items-center gap-1">
                <label className="text-xs text-slate-400">Fast:</label>
                <input
                  type="number"
                  value={condition.fast_period || 12}
                  onChange={(e) =>
                    updateCondition(condition.id, { fast_period: parseInt(e.target.value) })
                  }
                  min="5"
                  max="50"
                  className="w-16 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
              </div>
              <div className="flex items-center gap-1">
                <label className="text-xs text-slate-400">Slow:</label>
                <input
                  type="number"
                  value={condition.slow_period || 26}
                  onChange={(e) =>
                    updateCondition(condition.id, { slow_period: parseInt(e.target.value) })
                  }
                  min="10"
                  max="100"
                  className="w-16 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
              </div>
              <div className="flex items-center gap-1">
                <label className="text-xs text-slate-400">Signal:</label>
                <input
                  type="number"
                  value={condition.signal_period || 9}
                  onChange={(e) =>
                    updateCondition(condition.id, { signal_period: parseInt(e.target.value) })
                  }
                  min="5"
                  max="50"
                  className="w-16 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-300">Histogram</span>
              <select
                value={condition.operator}
                onChange={(e) => {
                  const newOp = e.target.value as Operator
                  const updates: Partial<PhaseCondition> = { operator: newOp }
                  if ((newOp === 'increasing' || newOp === 'decreasing') &&
                      condition.operator !== 'increasing' && condition.operator !== 'decreasing') {
                    updates.value = 0
                  }
                  updateCondition(condition.id, updates)
                }}
                className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
              >
                <option value="crossing_above">Crossing Above</option>
                <option value="crossing_below">Crossing Below</option>
                <option value="greater_than">&gt;</option>
                <option value="greater_equal">≥</option>
                <option value="less_than">&lt;</option>
                <option value="less_equal">≤</option>
                <option value="increasing">Increasing</option>
                <option value="decreasing">Decreasing</option>
              </select>
              {condition.operator === 'increasing' || condition.operator === 'decreasing' ? (
                <select
                  value={condition.value || 0}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  className="bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                  title="Minimum % change strength"
                >
                  {Object.entries(STRENGTH_LEVELS).map(([key, { label, value }]) => (
                    <option key={key} value={value}>{label}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="number"
                  value={condition.value}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  step="0.0001"
                  className="w-24 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
              )}
            </div>
          </>
        )

      case 'bb_percent':
        return (
          <>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Period:</label>
              <input
                type="number"
                value={condition.period || 20}
                onChange={(e) =>
                  updateCondition(condition.id, { period: parseInt(e.target.value) })
                }
                min="5"
                max="100"
                className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              />
              <label className="text-xs text-slate-400">Std Dev:</label>
              <input
                type="number"
                value={condition.std_dev || 2}
                onChange={(e) =>
                  updateCondition(condition.id, { std_dev: parseFloat(e.target.value) })
                }
                min="1"
                max="5"
                step="0.1"
                className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <select
                value={condition.operator}
                onChange={(e) => {
                  const newOp = e.target.value as Operator
                  const updates: Partial<PhaseCondition> = { operator: newOp }
                  if ((newOp === 'increasing' || newOp === 'decreasing') &&
                      condition.operator !== 'increasing' && condition.operator !== 'decreasing') {
                    updates.value = 0
                  }
                  updateCondition(condition.id, updates)
                }}
                className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
              >
                <option value="greater_than">&gt;</option>
                <option value="greater_equal">≥</option>
                <option value="less_than">&lt;</option>
                <option value="less_equal">≤</option>
                <option value="crossing_above">Crossing Above</option>
                <option value="crossing_below">Crossing Below</option>
                <option value="increasing">Increasing</option>
                <option value="decreasing">Decreasing</option>
              </select>
              {condition.operator === 'increasing' || condition.operator === 'decreasing' ? (
                <select
                  value={condition.value || 0}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  className="bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                  title="Minimum % change strength"
                >
                  {Object.entries(STRENGTH_LEVELS).map(([key, { label, value }]) => (
                    <option key={key} value={value}>{label}</option>
                  ))}
                </select>
              ) : (
                <>
                  <input
                    type="number"
                    value={condition.value ?? ''}
                    onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                    min="0"
                    max="100"
                    step="1"
                    className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                  />
                  <span className="text-xs text-slate-400">%</span>
                </>
              )}
            </div>
          </>
        )

      case 'ema_cross':
      case 'sma_cross':
        return (
          <>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Period:</label>
              <input
                type="number"
                value={condition.period || 50}
                onChange={(e) =>
                  updateCondition(condition.id, { period: parseInt(e.target.value) })
                }
                min="5"
                max="200"
                className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-300">Price</span>
              <select
                value={condition.operator}
                onChange={(e) => updateCondition(condition.id, { operator: e.target.value as Operator })}
                className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
              >
                <option value="crossing_above">Crossing Above</option>
                <option value="crossing_below">Crossing Below</option>
              </select>
              <span className="text-sm text-slate-300">{condition.type === 'ema_cross' ? 'EMA' : 'SMA'}</span>
            </div>
          </>
        )

      case 'vwap':
        return (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-slate-300">Price</span>
            <select
              value={condition.operator}
              onChange={(e) => updateCondition(condition.id, { operator: e.target.value as Operator })}
              className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
            >
              <option value="greater_than">Above (&gt;)</option>
              <option value="less_than">Below (&lt;)</option>
              <option value="crossing_above">Crossing Above</option>
              <option value="crossing_below">Crossing Below</option>
            </select>
            <span className="text-sm text-slate-300">VWAP</span>
          </div>
        )

      case 'stochastic':
        return (
          <>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Period:</label>
              <input
                type="number"
                value={condition.period || 14}
                onChange={(e) =>
                  updateCondition(condition.id, { period: parseInt(e.target.value) })
                }
                min="5"
                max="50"
                className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <select
                value={condition.operator}
                onChange={(e) => {
                  const newOp = e.target.value as Operator
                  const updates: Partial<PhaseCondition> = { operator: newOp }
                  if ((newOp === 'increasing' || newOp === 'decreasing') &&
                      condition.operator !== 'increasing' && condition.operator !== 'decreasing') {
                    updates.value = 0
                  }
                  updateCondition(condition.id, updates)
                }}
                className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
              >
                <option value="greater_than">&gt;</option>
                <option value="greater_equal">≥</option>
                <option value="less_than">&lt;</option>
                <option value="less_equal">≤</option>
                <option value="crossing_above">Crossing Above</option>
                <option value="crossing_below">Crossing Below</option>
                <option value="increasing">Increasing</option>
                <option value="decreasing">Decreasing</option>
              </select>
              {condition.operator === 'increasing' || condition.operator === 'decreasing' ? (
                <select
                  value={condition.value || 0}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  className="bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                  title="Minimum % change strength"
                >
                  {Object.entries(STRENGTH_LEVELS).map(([key, { label, value }]) => (
                    <option key={key} value={value}>{label}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="number"
                  value={condition.value}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  min="0"
                  max="100"
                  step="1"
                  className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
              )}
            </div>
          </>
        )

      case 'price_change':
        return (
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-300">Price change</span>
            <select
              value={condition.operator}
              onChange={(e) => {
                const newOp = e.target.value as Operator
                const updates: Partial<PhaseCondition> = { operator: newOp }
                if ((newOp === 'increasing' || newOp === 'decreasing') &&
                    condition.operator !== 'increasing' && condition.operator !== 'decreasing') {
                  updates.value = 0
                }
                updateCondition(condition.id, updates)
              }}
              className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
            >
              <option value="greater_than">&gt;</option>
              <option value="greater_equal">≥</option>
              <option value="less_than">&lt;</option>
              <option value="less_equal">≤</option>
              <option value="crossing_above">Crossing Above</option>
              <option value="crossing_below">Crossing Below</option>
              <option value="increasing">Increasing</option>
              <option value="decreasing">Decreasing</option>
            </select>
            {condition.operator === 'increasing' || condition.operator === 'decreasing' ? (
              <select
                value={condition.value || 0}
                onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                className="bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                title="Minimum % change strength"
              >
                {Object.entries(STRENGTH_LEVELS).map(([key, { label, value }]) => (
                  <option key={key} value={value}>{label}</option>
                ))}
              </select>
            ) : (
              <>
                <input
                  type="number"
                  value={condition.value}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  step="0.1"
                  className="w-24 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
                <span className="text-xs text-slate-400">%</span>
              </>
            )}
          </div>
        )

      case 'volume':
        return (
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-300">Volume</span>
            <select
              value={condition.operator}
              onChange={(e) => updateCondition(condition.id, { operator: e.target.value as Operator })}
              className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
            >
              <option value="greater_than">&gt;</option>
              <option value="greater_equal">≥</option>
              <option value="less_than">&lt;</option>
              <option value="less_equal">≤</option>
              <option value="crossing_above">Crossing Above</option>
              <option value="crossing_below">Crossing Below</option>
            </select>
            <input
              type="number"
              value={condition.value}
              onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
              step="1000"
              className="w-32 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
            />
          </div>
        )

      case 'volume_rsi':
        return (
          <>
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Period:</label>
              <input
                type="number"
                value={condition.period || 14}
                onChange={(e) =>
                  updateCondition(condition.id, { period: parseInt(e.target.value) })
                }
                min="5"
                max="100"
                className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <select
                value={condition.operator}
                onChange={(e) => {
                  const newOp = e.target.value as Operator
                  const updates: Partial<PhaseCondition> = { operator: newOp }
                  if ((newOp === 'increasing' || newOp === 'decreasing') &&
                      condition.operator !== 'increasing' && condition.operator !== 'decreasing') {
                    updates.value = 0
                  }
                  updateCondition(condition.id, updates)
                }}
                className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
              >
                <option value="greater_than">&gt;</option>
                <option value="greater_equal">≥</option>
                <option value="less_than">&lt;</option>
                <option value="less_equal">≤</option>
                <option value="crossing_above">Crossing Above</option>
                <option value="crossing_below">Crossing Below</option>
                <option value="increasing">Increasing</option>
                <option value="decreasing">Decreasing</option>
              </select>
              {condition.operator === 'increasing' || condition.operator === 'decreasing' ? (
                <select
                  value={condition.value || 0}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  className="bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                  title="Minimum % change strength"
                >
                  {Object.entries(STRENGTH_LEVELS).map(([key, { label, value }]) => (
                    <option key={key} value={value}>{label}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="number"
                  value={condition.value}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  min="0"
                  max="100"
                  step="1"
                  className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
              )}
            </div>
          </>
        )

      case 'gap_fill_pct':
        return (
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-300">Gap fill</span>
            <select
              value={condition.operator}
              onChange={(e) => {
                const newOp = e.target.value as Operator
                const updates: Partial<PhaseCondition> = { operator: newOp }
                if ((newOp === 'increasing' || newOp === 'decreasing') &&
                    condition.operator !== 'increasing' && condition.operator !== 'decreasing') {
                  updates.value = 0
                }
                updateCondition(condition.id, updates)
              }}
              className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
            >
              <option value="greater_than">&gt;</option>
              <option value="greater_equal">≥</option>
              <option value="less_than">&lt;</option>
              <option value="less_equal">≤</option>
              <option value="crossing_above">Crossing Above</option>
              <option value="crossing_below">Crossing Below</option>
              <option value="increasing">Increasing</option>
              <option value="decreasing">Decreasing</option>
            </select>
            {condition.operator === 'increasing' || condition.operator === 'decreasing' ? (
              <select
                value={condition.value || 0}
                onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                className="bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                title="Minimum % change strength"
              >
                {Object.entries(STRENGTH_LEVELS).map(([key, { label, value }]) => (
                  <option key={key} value={value}>{label}</option>
                ))}
              </select>
            ) : (
              <>
                <input
                  type="number"
                  value={condition.value}
                  onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                  step="0.1"
                  className="w-24 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
                <span className="text-xs text-slate-400">%</span>
              </>
            )}
          </div>
        )

      // Aggregate indicators (return 0 or 1)
      case 'ai_buy':
      case 'ai_sell':
      case 'bull_flag':
        return (
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-300">
              {condition.type === 'ai_buy' ? 'AI Buy Signal' :
               condition.type === 'ai_sell' ? 'AI Sell Signal' :
               'Bull Flag Pattern'}
            </span>
            <span className="text-sm text-green-400 font-medium">= Active (1)</span>
            <span className="text-xs text-slate-500 ml-2">
              (Triggers when multi-timeframe analysis signals {condition.type === 'ai_sell' ? 'sell' : 'buy'})
            </span>
          </div>
        )

      case 'vwap_bounce_up':
        return (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <span className="text-sm text-green-400 font-medium">▲ Bullish VWAP Bounce</span>
              <span className="text-sm text-green-400 font-medium">= Active (1)</span>
            </div>
            <p className="text-xs text-slate-400">
              Fires when: penultimate closed candle's <strong>low ≤ VWAP</strong> (wick retest) and
              last closed candle's <strong>close &gt; VWAP</strong> (bounce confirmation).
            </p>
          </div>
        )

      case 'vwap_bounce_down':
        return (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <span className="text-sm text-red-400 font-medium">▼ Bearish VWAP Bounce</span>
              <span className="text-sm text-red-400 font-medium">= Active (1)</span>
            </div>
            <p className="text-xs text-slate-400">
              Fires when: penultimate closed candle's <strong>high ≥ VWAP</strong> (wick retest) and
              last closed candle's <strong>close &lt; VWAP</strong> (bounce confirmation).
            </p>
          </div>
        )

      case 'qfl_crack':
        return (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="text-sm text-amber-400 font-medium">⚡ QFL Crack</span>
              <span className="text-sm text-amber-400 font-medium">= Active (1)</span>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-1.5">
                <label className="text-xs text-slate-400 whitespace-nowrap">Lookback candles:</label>
                <input
                  type="number"
                  value={condition.lookback_candles ?? 100}
                  onChange={(e) => updateCondition(condition.id, { lookback_candles: parseInt(e.target.value) })}
                  min="20" max="500" step="10"
                  className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
              </div>
              <div className="flex items-center gap-1.5">
                <label className="text-xs text-slate-400 whitespace-nowrap">Min bounce %:</label>
                <input
                  type="number"
                  value={condition.bounce_pct ?? 3.0}
                  onChange={(e) => updateCondition(condition.id, { bounce_pct: parseFloat(e.target.value) })}
                  min="0.5" max="20" step="0.5"
                  className="w-16 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
              </div>
              <div className="flex items-center gap-1.5">
                <label className="text-xs text-slate-400 whitespace-nowrap">Crack %:</label>
                <input
                  type="number"
                  value={condition.crack_pct ?? 2.0}
                  onChange={(e) => updateCondition(condition.id, { crack_pct: parseFloat(e.target.value) })}
                  min="0.1" max="20" step="0.1"
                  className="w-16 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
                />
              </div>
            </div>
            <p className="text-xs text-slate-400">
              Fires when price drops <strong>{condition.crack_pct ?? 2}%</strong> below a base that bounced
              at least <strong>{condition.bounce_pct ?? 3}%</strong> (scans last <strong>{condition.lookback_candles ?? 100}</strong> candles).
            </p>
          </div>
        )
    }
  }

  const getReadableCondition = (condition: PhaseCondition): string => {
    const op = OPERATORS[condition.operator]
    const tf = TIMEFRAMES[condition.timeframe || 'FIVE_MINUTE']
    const isDirectional = condition.operator === 'increasing' || condition.operator === 'decreasing'
    const strengthLabel = isDirectional && condition.value > 0 ? ` (>${condition.value}%)` : ''

    switch (condition.type) {
      case 'rsi':
        return isDirectional
          ? `[${tf}] RSI(${condition.period || 14}) ${op}${strengthLabel}`
          : `[${tf}] RSI(${condition.period || 14}) ${op} ${condition.value}`
      case 'macd':
        return isDirectional
          ? `[${tf}] MACD Histogram(${condition.fast_period},${condition.slow_period},${condition.signal_period}) ${op}${strengthLabel}`
          : `[${tf}] MACD Histogram(${condition.fast_period},${condition.slow_period},${condition.signal_period}) ${op} ${condition.value}`
      case 'bb_percent':
        return isDirectional
          ? `[${tf}] BB%(${condition.period},${condition.std_dev}) ${op}${strengthLabel}`
          : `[${tf}] BB%(${condition.period},${condition.std_dev}) ${op} ${condition.value}%`
      case 'ema_cross':
        return `[${tf}] Price ${op} EMA(${condition.period})`
      case 'sma_cross':
        return `[${tf}] Price ${op} SMA(${condition.period})`
      case 'vwap':
        return `[${tf}] Price ${op} VWAP`
      case 'stochastic':
        return isDirectional
          ? `[${tf}] Stochastic(${condition.period}) ${op}${strengthLabel}`
          : `[${tf}] Stochastic(${condition.period}) ${op} ${condition.value}`
      case 'price_change':
        return isDirectional
          ? `[${tf}] Price Change ${op}${strengthLabel}`
          : `[${tf}] Price Change ${op} ${condition.value}%`
      case 'volume':
        return `[${tf}] Volume ${op} ${condition.value}`
      case 'volume_rsi':
        return isDirectional
          ? `[${tf}] Volume RSI(${condition.period || 14}) ${op}${strengthLabel}`
          : `[${tf}] Volume RSI(${condition.period || 14}) ${op} ${condition.value}`
      case 'gap_fill_pct':
        return isDirectional
          ? `[${tf}] Gap Fill % ${op}${strengthLabel}`
          : `[${tf}] Gap Fill % ${op} ${condition.value}%`
      // Aggregate indicators
      case 'ai_buy':
        return `[${tf}] AI Buy Signal = Active`
      case 'ai_sell':
        return `[${tf}] AI Sell Signal = Active`
      case 'bull_flag':
        return `[${tf}] Bull Flag Pattern = Active`
      case 'vwap_bounce_up':
        return `[${tf}] VWAP Bounce Up = Active`
      case 'vwap_bounce_down':
        return `[${tf}] VWAP Bounce Down = Active`
      case 'qfl_crack':
        return `[${tf}] QFL Crack (bounce≥${condition.bounce_pct ?? 3}%, crack≥${condition.crack_pct ?? 2}%) = Active`
      default:
        return 'Unknown condition'
    }
  }

  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <div className="mb-3">
        <h4 className="text-md font-semibold text-white">{title}</h4>
        <p className="text-xs text-slate-400 mt-1">{description}</p>
      </div>

      {conditions.length > 0 && (
        <div className="space-y-3 mb-3">
          {conditions.map((condition, index) => (
            <div key={condition.id}>
              {index > 0 && allowMultiple && onLogicChange && (
                <div className="flex items-center justify-center my-2">
                  <button
                    type="button"
                    onClick={() => onLogicChange(logic === 'and' ? 'or' : 'and')}
                    className={`px-3 py-1 rounded text-xs font-medium ${
                      logic === 'and' ? 'bg-blue-600 text-white' : 'bg-purple-600 text-white'
                    }`}
                  >
                    {logic.toUpperCase()}
                  </button>
                </div>
              )}

              <div className="bg-slate-700/50 rounded-lg p-3 border border-slate-600">
                <div className="flex items-start gap-2 mb-2">
                  <div className="flex-1">
                    <div className="flex gap-2 mb-2">
                      <select
                        value={condition.type}
                        onChange={(e) =>
                          updateCondition(condition.id, { type: e.target.value as ConditionType })
                        }
                        className="flex-1 bg-slate-600 text-white px-3 py-2 rounded text-sm border border-slate-500 font-medium"
                      >
                        {Object.entries(CONDITION_TYPES).map(([value, { label }]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                      <select
                        value={condition.timeframe || 'FIVE_MINUTE'}
                        onChange={(e) =>
                          updateCondition(condition.id, { timeframe: e.target.value as Timeframe })
                        }
                        className="bg-slate-600 text-white px-3 py-2 rounded text-sm border border-slate-500 font-medium"
                        title="Timeframe"
                      >
                        {Object.entries(TIMEFRAMES).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <p className="text-xs text-slate-400">
                      {CONDITION_TYPES[condition.type].description}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeCondition(condition.id)}
                    className="text-red-400 hover:text-red-300 transition-colors p-1"
                    title="Remove condition"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  {renderConditionFields(condition)}
                </div>

                {/* Human-readable summary */}
                <div className="mt-2 pt-2 border-t border-slate-600">
                  <span className="text-xs font-mono text-blue-300">
                    {getReadableCondition(condition)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {(allowMultiple || conditions.length === 0) && (
        <button
          type="button"
          onClick={addCondition}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded text-sm transition-colors w-full justify-center"
        >
          <Plus size={16} />
          Add Condition
        </button>
      )}

      {conditions.length === 0 && (
        <p className="text-xs text-slate-500 text-center mt-2">No conditions - will use DCA settings only</p>
      )}
    </div>
  )
}

export default PhaseConditionSelector
