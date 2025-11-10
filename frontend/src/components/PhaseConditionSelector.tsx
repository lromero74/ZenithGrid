import { useState } from 'react'
import { Plus, X } from 'lucide-react'

// Condition types matching 3Commas
export type ConditionType =
  | 'rsi'
  | 'macd'
  | 'bb_percent'
  | 'ema_cross'
  | 'sma_cross'
  | 'price_change'
  | 'stochastic'
  | 'volume'

export type Operator = 'greater_than' | 'less_than' | 'crossing_above' | 'crossing_below'

export interface PhaseCondition {
  id: string
  type: ConditionType
  operator: Operator
  value: number
  period?: number
  fast_period?: number
  slow_period?: number
  signal_period?: number
  std_dev?: number
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
const CONDITION_TYPES: Record<ConditionType, { label: string; description: string }> = {
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
}

const OPERATORS: Record<Operator, string> = {
  greater_than: '>',
  less_than: '<',
  crossing_above: 'Crossing Above',
  crossing_below: 'Crossing Below',
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
                onChange={(e) => updateCondition(condition.id, { operator: e.target.value as Operator })}
                className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
              >
                <option value="greater_than">&gt;</option>
                <option value="less_than">&lt;</option>
              </select>
              <input
                type="number"
                value={condition.value}
                onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                min="0"
                max="100"
                step="1"
                className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              />
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
                onChange={(e) => updateCondition(condition.id, { operator: e.target.value as Operator })}
                className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
              >
                <option value="crossing_above">Crossing Above</option>
                <option value="crossing_below">Crossing Below</option>
                <option value="greater_than">&gt;</option>
                <option value="less_than">&lt;</option>
              </select>
              <input
                type="number"
                value={condition.value}
                onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                step="0.0001"
                className="w-24 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              />
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
                onChange={(e) => updateCondition(condition.id, { operator: e.target.value as Operator })}
                className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
              >
                <option value="greater_than">&gt;</option>
                <option value="less_than">&lt;</option>
              </select>
              <input
                type="number"
                value={condition.value}
                onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                min="0"
                max="100"
                step="1"
                className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              />
              <span className="text-xs text-slate-400">%</span>
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
                onChange={(e) => updateCondition(condition.id, { operator: e.target.value as Operator })}
                className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
              >
                <option value="greater_than">&gt;</option>
                <option value="less_than">&lt;</option>
              </select>
              <input
                type="number"
                value={condition.value}
                onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
                min="0"
                max="100"
                step="1"
                className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              />
            </div>
          </>
        )

      case 'price_change':
        return (
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-300">Price change</span>
            <select
              value={condition.operator}
              onChange={(e) => updateCondition(condition.id, { operator: e.target.value as Operator })}
              className="bg-slate-600 text-white px-3 py-1 rounded text-sm border border-slate-500"
            >
              <option value="greater_than">&gt;</option>
              <option value="less_than">&lt;</option>
            </select>
            <input
              type="number"
              value={condition.value}
              onChange={(e) => updateCondition(condition.id, { value: parseFloat(e.target.value) })}
              step="0.1"
              className="w-24 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
            />
            <span className="text-xs text-slate-400">%</span>
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
              <option value="less_than">&lt;</option>
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
    }
  }

  const getReadableCondition = (condition: PhaseCondition): string => {
    const op = OPERATORS[condition.operator]

    switch (condition.type) {
      case 'rsi':
        return `RSI(${condition.period || 14}) ${op} ${condition.value}`
      case 'macd':
        return `MACD Histogram(${condition.fast_period},${condition.slow_period},${condition.signal_period}) ${op} ${condition.value}`
      case 'bb_percent':
        return `BB%(${condition.period},${condition.std_dev}) ${op} ${condition.value}%`
      case 'ema_cross':
        return `Price ${op} EMA(${condition.period})`
      case 'sma_cross':
        return `Price ${op} SMA(${condition.period})`
      case 'stochastic':
        return `Stochastic(${condition.period}) ${op} ${condition.value}`
      case 'price_change':
        return `Price Change ${op} ${condition.value}%`
      case 'volume':
        return `Volume ${op} ${condition.value}`
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
                    <select
                      value={condition.type}
                      onChange={(e) =>
                        updateCondition(condition.id, { type: e.target.value as ConditionType })
                      }
                      className="w-full bg-slate-600 text-white px-3 py-2 rounded text-sm border border-slate-500 font-medium"
                    >
                      {Object.entries(CONDITION_TYPES).map(([value, { label }]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-slate-400 mt-1">
                      {CONDITION_TYPES[condition.type].description}
                    </p>
                  </div>
                  <button
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
