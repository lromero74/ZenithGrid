import { useState } from 'react'
import { Plus, X, Trash2 } from 'lucide-react'

// Types matching backend enums
export type ComparisonOperator =
  | 'greater_than'
  | 'less_than'
  | 'greater_equal'
  | 'less_equal'
  | 'equal'
  | 'crossing_above'
  | 'crossing_below'

export type IndicatorType =
  | 'rsi'
  | 'macd'
  | 'macd_signal'
  | 'macd_histogram'
  | 'ema'
  | 'sma'
  | 'price'
  | 'bollinger_upper'
  | 'bollinger_middle'
  | 'bollinger_lower'
  | 'stochastic_k'
  | 'stochastic_d'
  | 'volume'

export type LogicOperator = 'and' | 'or'

export interface Condition {
  id: string
  indicator: IndicatorType
  operator: ComparisonOperator
  value_type: 'static' | 'indicator'
  static_value?: number
  compare_indicator?: IndicatorType
  indicator_params: Record<string, number>
  compare_indicator_params?: Record<string, number>
}

export interface ConditionGroup {
  id: string
  logic: LogicOperator
  conditions: Condition[]
  sub_groups?: ConditionGroup[]
}

interface ConditionBuilderProps {
  group: ConditionGroup
  onChange: (group: ConditionGroup) => void
  level?: number
}

// Indicator metadata
const INDICATORS: Record<IndicatorType, { label: string; params: string[] }> = {
  price: { label: 'Price', params: [] },
  volume: { label: 'Volume', params: [] },
  rsi: { label: 'RSI', params: ['period'] },
  macd: { label: 'MACD Line', params: ['fast_period', 'slow_period', 'signal_period'] },
  macd_signal: { label: 'MACD Signal', params: ['fast_period', 'slow_period', 'signal_period'] },
  macd_histogram: { label: 'MACD Histogram', params: ['fast_period', 'slow_period', 'signal_period'] },
  sma: { label: 'SMA', params: ['period'] },
  ema: { label: 'EMA', params: ['period'] },
  bollinger_upper: { label: 'Bollinger Upper', params: ['period', 'std_dev'] },
  bollinger_middle: { label: 'Bollinger Middle', params: ['period', 'std_dev'] },
  bollinger_lower: { label: 'Bollinger Lower', params: ['period', 'std_dev'] },
  stochastic_k: { label: 'Stochastic %K', params: ['k_period', 'd_period'] },
  stochastic_d: { label: 'Stochastic %D', params: ['k_period', 'd_period'] },
}

const OPERATORS: Record<ComparisonOperator, string> = {
  greater_than: '>',
  less_than: '<',
  greater_equal: '≥',
  less_equal: '≤',
  equal: '=',
  crossing_above: 'Crossing Above',
  crossing_below: 'Crossing Below',
}

const DEFAULT_PARAMS: Record<string, number> = {
  period: 14,
  fast_period: 12,
  slow_period: 26,
  signal_period: 9,
  std_dev: 2,
  k_period: 14,
  d_period: 3,
}

function ConditionBuilder({ group, onChange, level = 0 }: ConditionBuilderProps) {
  const addCondition = () => {
    const newCondition: Condition = {
      id: `cond_${Date.now()}_${Math.random()}`,
      indicator: 'rsi',
      operator: 'less_than',
      value_type: 'static',
      static_value: 30,
      indicator_params: { period: 14 },
    }

    onChange({
      ...group,
      conditions: [...group.conditions, newCondition],
    })
  }

  const addSubGroup = () => {
    const newGroup: ConditionGroup = {
      id: `group_${Date.now()}_${Math.random()}`,
      logic: 'and',
      conditions: [],
      sub_groups: [],
    }

    onChange({
      ...group,
      sub_groups: [...(group.sub_groups || []), newGroup],
    })
  }

  const removeCondition = (conditionId: string) => {
    onChange({
      ...group,
      conditions: group.conditions.filter((c) => c.id !== conditionId),
    })
  }

  const removeSubGroup = (groupId: string) => {
    onChange({
      ...group,
      sub_groups: (group.sub_groups || []).filter((g) => g.id !== groupId),
    })
  }

  const updateCondition = (conditionId: string, updates: Partial<Condition>) => {
    onChange({
      ...group,
      conditions: group.conditions.map((c) =>
        c.id === conditionId ? { ...c, ...updates } : c
      ),
    })
  }

  const updateSubGroup = (groupId: string, updatedGroup: ConditionGroup) => {
    onChange({
      ...group,
      sub_groups: (group.sub_groups || []).map((g) =>
        g.id === groupId ? updatedGroup : g
      ),
    })
  }

  const toggleLogic = () => {
    onChange({
      ...group,
      logic: group.logic === 'and' ? 'or' : 'and',
    })
  }

  const getIndicatorParams = (indicator: IndicatorType): string[] => {
    return INDICATORS[indicator]?.params || []
  }

  const updateIndicatorParams = (
    condition: Condition,
    paramName: string,
    value: number
  ) => {
    updateCondition(condition.id, {
      indicator_params: {
        ...condition.indicator_params,
        [paramName]: value,
      },
    })
  }

  const updateCompareIndicatorParams = (
    condition: Condition,
    paramName: string,
    value: number
  ) => {
    updateCondition(condition.id, {
      compare_indicator_params: {
        ...(condition.compare_indicator_params || {}),
        [paramName]: value,
      },
    })
  }

  const handleIndicatorChange = (condition: Condition, newIndicator: IndicatorType) => {
    // Set default params for new indicator
    const params = getIndicatorParams(newIndicator)
    const newParams: Record<string, number> = {}
    params.forEach((param) => {
      newParams[param] = DEFAULT_PARAMS[param] || 14
    })

    updateCondition(condition.id, {
      indicator: newIndicator,
      indicator_params: newParams,
    })
  }

  const handleCompareIndicatorChange = (condition: Condition, newIndicator: IndicatorType) => {
    const params = getIndicatorParams(newIndicator)
    const newParams: Record<string, number> = {}
    params.forEach((param) => {
      newParams[param] = DEFAULT_PARAMS[param] || 14
    })

    updateCondition(condition.id, {
      compare_indicator: newIndicator,
      compare_indicator_params: newParams,
    })
  }

  const bgColor = level === 0 ? 'bg-slate-800' : level === 1 ? 'bg-slate-750' : 'bg-slate-700'
  const borderColor = level === 0 ? 'border-slate-600' : 'border-slate-500'

  return (
    <div className={`${bgColor} border ${borderColor} rounded-lg p-4`}>
      {/* Header with logic toggle */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-400">Logic:</span>
          <button
            onClick={toggleLogic}
            className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
              group.logic === 'and'
                ? 'bg-blue-600 text-white'
                : 'bg-purple-600 text-white'
            }`}
          >
            {group.logic.toUpperCase()}
          </button>
          <span className="text-xs text-slate-500">
            {group.logic === 'and' ? 'All conditions must be true' : 'Any condition can be true'}
          </span>
        </div>

        {level > 0 && (
          <button
            onClick={() => removeSubGroup(group.id)}
            className="text-red-400 hover:text-red-300 transition-colors"
            title="Remove group"
          >
            <Trash2 size={16} />
          </button>
        )}
      </div>

      {/* Conditions */}
      <div className="space-y-3">
        {group.conditions.map((condition, index) => (
          <div
            key={condition.id}
            className="bg-slate-700/50 rounded-lg p-3 border border-slate-600"
          >
            <div className="flex items-start gap-2 flex-wrap">
              {/* Indicator selector */}
              <div className="flex-shrink-0">
                <select
                  value={condition.indicator}
                  onChange={(e) =>
                    handleIndicatorChange(condition, e.target.value as IndicatorType)
                  }
                  className="bg-slate-600 text-white px-3 py-1.5 rounded text-sm border border-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {Object.entries(INDICATORS).map(([value, { label }]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Indicator params */}
              {getIndicatorParams(condition.indicator).map((param) => (
                <div key={param} className="flex items-center gap-1">
                  <span className="text-xs text-slate-400">{param}:</span>
                  <input
                    type="number"
                    value={condition.indicator_params[param] || DEFAULT_PARAMS[param] || 14}
                    onChange={(e) =>
                      updateIndicatorParams(condition, param, parseFloat(e.target.value))
                    }
                    className="w-16 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              ))}

              {/* Operator selector */}
              <div className="flex-shrink-0">
                <select
                  value={condition.operator}
                  onChange={(e) =>
                    updateCondition(condition.id, {
                      operator: e.target.value as ComparisonOperator,
                    })
                  }
                  className="bg-slate-600 text-white px-3 py-1.5 rounded text-sm border border-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {Object.entries(OPERATORS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Value type toggle */}
              <div className="flex-shrink-0">
                <select
                  value={condition.value_type}
                  onChange={(e) => {
                    const newType = e.target.value as 'static' | 'indicator'
                    updateCondition(condition.id, {
                      value_type: newType,
                      ...(newType === 'indicator' && !condition.compare_indicator
                        ? { compare_indicator: 'price', compare_indicator_params: {} }
                        : {}),
                    })
                  }}
                  className="bg-slate-600 text-white px-3 py-1.5 rounded text-sm border border-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="static">Value</option>
                  <option value="indicator">Indicator</option>
                </select>
              </div>

              {/* Value input or indicator selector */}
              {condition.value_type === 'static' ? (
                <input
                  type="number"
                  value={condition.static_value || 0}
                  onChange={(e) =>
                    updateCondition(condition.id, {
                      static_value: parseFloat(e.target.value),
                    })
                  }
                  step="0.01"
                  className="w-24 bg-slate-600 text-white px-3 py-1.5 rounded text-sm border border-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              ) : (
                <>
                  <select
                    value={condition.compare_indicator || 'price'}
                    onChange={(e) =>
                      handleCompareIndicatorChange(condition, e.target.value as IndicatorType)
                    }
                    className="bg-slate-600 text-white px-3 py-1.5 rounded text-sm border border-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {Object.entries(INDICATORS).map(([value, { label }]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>

                  {/* Compare indicator params */}
                  {condition.compare_indicator &&
                    getIndicatorParams(condition.compare_indicator).map((param) => (
                      <div key={param} className="flex items-center gap-1">
                        <span className="text-xs text-slate-400">{param}:</span>
                        <input
                          type="number"
                          value={
                            condition.compare_indicator_params?.[param] ||
                            DEFAULT_PARAMS[param] ||
                            14
                          }
                          onChange={(e) =>
                            updateCompareIndicatorParams(
                              condition,
                              param,
                              parseFloat(e.target.value)
                            )
                          }
                          className="w-16 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </div>
                    ))}
                </>
              )}

              {/* Remove button */}
              <button
                onClick={() => removeCondition(condition.id)}
                className="ml-auto text-red-400 hover:text-red-300 transition-colors"
                title="Remove condition"
              >
                <X size={16} />
              </button>
            </div>

            {/* Human-readable summary */}
            <div className="mt-2 text-xs text-slate-400">
              {INDICATORS[condition.indicator].label}
              {Object.entries(condition.indicator_params).length > 0 && (
                <>
                  (
                  {Object.entries(condition.indicator_params)
                    .map(([k, v]) => v)
                    .join(', ')}
                  )
                </>
              )}{' '}
              {OPERATORS[condition.operator]}{' '}
              {condition.value_type === 'static' ? (
                condition.static_value
              ) : (
                <>
                  {INDICATORS[condition.compare_indicator || 'price'].label}
                  {condition.compare_indicator_params &&
                    Object.entries(condition.compare_indicator_params).length > 0 && (
                      <>
                        (
                        {Object.entries(condition.compare_indicator_params)
                          .map(([k, v]) => v)
                          .join(', ')}
                        )
                      </>
                    )}
                </>
              )}
            </div>
          </div>
        ))}

        {/* Sub-groups */}
        {group.sub_groups?.map((subGroup) => (
          <ConditionBuilder
            key={subGroup.id}
            group={subGroup}
            onChange={(updated) => updateSubGroup(subGroup.id, updated)}
            level={level + 1}
          />
        ))}
      </div>

      {/* Add buttons */}
      <div className="flex gap-2 mt-4">
        <button
          onClick={addCondition}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-sm transition-colors"
        >
          <Plus size={16} />
          Add Condition
        </button>
        <button
          onClick={addSubGroup}
          className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded text-sm transition-colors"
        >
          <Plus size={16} />
          Add Group
        </button>
      </div>
    </div>
  )
}

export default ConditionBuilder
