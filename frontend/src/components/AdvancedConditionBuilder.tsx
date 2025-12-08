/**
 * AdvancedConditionBuilder - Condition builder with grouping and NOT support
 * Allows complex expressions like: (A AND B) OR (C OR D) AND NOT E
 */

import { useState } from 'react'
import { Plus, X, Parentheses, CircleSlash } from 'lucide-react'

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
  | 'ai_buy'
  | 'ai_sell'
  | 'bull_flag'

export type Operator = 'greater_than' | 'less_than' | 'crossing_above' | 'crossing_below' | 'equal'

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

export interface Condition {
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
  negate?: boolean  // NOT this condition
}

export interface ConditionGroup {
  id: string
  conditions: Condition[]
  logic: 'and' | 'or'  // Logic within the group
}

export interface ConditionExpression {
  groups: ConditionGroup[]
  groupLogic: 'and' | 'or'  // Logic between groups
}

interface AdvancedConditionBuilderProps {
  title: string
  description: string
  expression: ConditionExpression
  onChange: (expression: ConditionExpression) => void
}

// Available condition types
const CONDITION_TYPES: Record<ConditionType, { label: string; description: string; isAggregate?: boolean }> = {
  rsi: { label: 'RSI', description: 'Momentum oscillator (0-100)' },
  macd: { label: 'MACD', description: 'MACD Histogram value' },
  bb_percent: { label: 'BB%', description: 'Bollinger Band % (0-100)' },
  ema_cross: { label: 'EMA Cross', description: 'Price vs EMA' },
  sma_cross: { label: 'SMA Cross', description: 'Price vs SMA' },
  price_change: { label: 'Price Change %', description: '% change from previous candle' },
  stochastic: { label: 'Stochastic', description: 'Stochastic oscillator (0-100)' },
  volume: { label: 'Volume', description: 'Trading volume' },
  ai_buy: { label: 'AI Buy', description: 'AI buy signal = 1', isAggregate: true },
  ai_sell: { label: 'AI Sell', description: 'AI sell signal = 1', isAggregate: true },
  bull_flag: { label: 'Bull Flag', description: 'Pattern detected = 1', isAggregate: true },
}

const OPERATORS: Record<Operator, string> = {
  greater_than: '>',
  less_than: '<',
  crossing_above: 'X Above',
  crossing_below: 'X Below',
  equal: '=',
}

const TIMEFRAMES: Record<Timeframe, string> = {
  ONE_MINUTE: '1m',
  THREE_MINUTE: '3m',
  FIVE_MINUTE: '5m',
  FIFTEEN_MINUTE: '15m',
  THIRTY_MINUTE: '30m',
  ONE_HOUR: '1h',
  TWO_HOUR: '2h',
  SIX_HOUR: '6h',
  ONE_DAY: '1d',
}

// Create default condition
const createDefaultCondition = (): Condition => ({
  id: `cond_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
  type: 'rsi',
  operator: 'less_than',
  value: 30,
  timeframe: 'FIFTEEN_MINUTE',
  period: 14,
  negate: false,
})

// Create default group with one condition
const createDefaultGroup = (): ConditionGroup => ({
  id: `grp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
  conditions: [createDefaultCondition()],
  logic: 'and',
})

// Create empty expression
export const createEmptyExpression = (): ConditionExpression => ({
  groups: [],
  groupLogic: 'and',
})

// Convert old flat format to new grouped format
export const convertLegacyConditions = (
  conditions: Condition[],
  logic: 'and' | 'or'
): ConditionExpression => {
  if (conditions.length === 0) {
    return createEmptyExpression()
  }
  return {
    groups: [{
      id: `grp_legacy_${Date.now()}`,
      conditions: conditions.map(c => ({ ...c, negate: c.negate || false })),
      logic,
    }],
    groupLogic: 'and',
  }
}

// Flatten expression back to simple conditions (for backward compatibility)
export const flattenExpression = (expression: ConditionExpression): { conditions: Condition[], logic: 'and' | 'or' } => {
  const allConditions = expression.groups.flatMap(g => g.conditions)
  return {
    conditions: allConditions,
    logic: expression.groups[0]?.logic || 'and',
  }
}

function AdvancedConditionBuilder({
  title,
  description,
  expression,
  onChange,
}: AdvancedConditionBuilderProps) {
  const [showRawExpression, setShowRawExpression] = useState(false)

  // Add a new group
  const addGroup = () => {
    onChange({
      ...expression,
      groups: [...expression.groups, createDefaultGroup()],
    })
  }

  // Remove a group
  const removeGroup = (groupId: string) => {
    onChange({
      ...expression,
      groups: expression.groups.filter(g => g.id !== groupId),
    })
  }

  // Update group logic (AND/OR within group)
  const updateGroupLogic = (groupId: string, logic: 'and' | 'or') => {
    onChange({
      ...expression,
      groups: expression.groups.map(g =>
        g.id === groupId ? { ...g, logic } : g
      ),
    })
  }

  // Toggle logic between groups
  const toggleGroupLogic = () => {
    onChange({
      ...expression,
      groupLogic: expression.groupLogic === 'and' ? 'or' : 'and',
    })
  }

  // Add condition to a group
  const addConditionToGroup = (groupId: string) => {
    onChange({
      ...expression,
      groups: expression.groups.map(g =>
        g.id === groupId
          ? { ...g, conditions: [...g.conditions, createDefaultCondition()] }
          : g
      ),
    })
  }

  // Remove condition from a group
  const removeCondition = (groupId: string, conditionId: string) => {
    onChange({
      ...expression,
      groups: expression.groups.map(g =>
        g.id === groupId
          ? { ...g, conditions: g.conditions.filter(c => c.id !== conditionId) }
          : g
      ).filter(g => g.conditions.length > 0), // Remove empty groups
    })
  }

  // Update a condition
  const updateCondition = (groupId: string, conditionId: string, updates: Partial<Condition>) => {
    onChange({
      ...expression,
      groups: expression.groups.map(g =>
        g.id === groupId
          ? {
              ...g,
              conditions: g.conditions.map(c => {
                if (c.id !== conditionId) return c

                // Handle type changes - reset to defaults
                if (updates.type && updates.type !== c.type) {
                  const newCond: Condition = {
                    ...c,
                    type: updates.type,
                    negate: c.negate,
                  }
                  switch (updates.type) {
                    case 'rsi':
                      newCond.period = 14
                      newCond.operator = 'less_than'
                      newCond.value = 30
                      break
                    case 'macd':
                      newCond.fast_period = 12
                      newCond.slow_period = 26
                      newCond.signal_period = 9
                      newCond.operator = 'crossing_above'
                      newCond.value = 0
                      break
                    case 'bb_percent':
                      newCond.period = 20
                      newCond.std_dev = 2
                      newCond.operator = 'less_than'
                      newCond.value = 20
                      break
                    case 'stochastic':
                      newCond.period = 14
                      newCond.operator = 'less_than'
                      newCond.value = 20
                      break
                    case 'ai_buy':
                    case 'ai_sell':
                    case 'bull_flag':
                      newCond.operator = 'equal'
                      newCond.value = 1
                      break
                    default:
                      newCond.operator = 'greater_than'
                      newCond.value = 0
                  }
                  return newCond
                }

                return { ...c, ...updates }
              }),
            }
          : g
      ),
    })
  }

  // Toggle NOT on a condition
  const toggleNegate = (groupId: string, conditionId: string) => {
    updateCondition(groupId, conditionId, {
      negate: !expression.groups
        .find(g => g.id === groupId)
        ?.conditions.find(c => c.id === conditionId)?.negate
    })
  }

  // Render a single condition
  const renderCondition = (group: ConditionGroup, condition: Condition, index: number) => {
    const isAggregate = CONDITION_TYPES[condition.type]?.isAggregate

    return (
      <div key={condition.id} className="relative">
        {/* Logic connector between conditions */}
        {index > 0 && (
          <div className="flex items-center justify-center my-1">
            <button
              type="button"
              onClick={() => updateGroupLogic(group.id, group.logic === 'and' ? 'or' : 'and')}
              className={`px-2 py-0.5 rounded text-xs font-bold ${
                group.logic === 'and'
                  ? 'bg-blue-600/80 text-blue-100'
                  : 'bg-purple-600/80 text-purple-100'
              }`}
            >
              {group.logic.toUpperCase()}
            </button>
          </div>
        )}

        <div className={`flex items-center gap-2 p-2 rounded border ${
          condition.negate
            ? 'bg-red-900/20 border-red-600/50'
            : 'bg-slate-700/50 border-slate-600'
        }`}>
          {/* NOT toggle */}
          <button
            type="button"
            onClick={() => toggleNegate(group.id, condition.id)}
            className={`p-1 rounded transition-colors ${
              condition.negate
                ? 'bg-red-600 text-white'
                : 'bg-slate-600 text-slate-400 hover:text-white'
            }`}
            title={condition.negate ? 'Remove NOT' : 'Add NOT'}
          >
            <CircleSlash size={14} />
          </button>

          {condition.negate && (
            <span className="text-red-400 text-xs font-bold">NOT</span>
          )}

          {/* Condition type */}
          <select
            value={condition.type}
            onChange={(e) => updateCondition(group.id, condition.id, { type: e.target.value as ConditionType })}
            className="bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
          >
            {Object.entries(CONDITION_TYPES).map(([value, { label }]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>

          {/* Timeframe */}
          <select
            value={condition.timeframe}
            onChange={(e) => updateCondition(group.id, condition.id, { timeframe: e.target.value as Timeframe })}
            className="bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500 w-16"
          >
            {Object.entries(TIMEFRAMES).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>

          {/* Operator (not for aggregates) */}
          {!isAggregate && (
            <select
              value={condition.operator}
              onChange={(e) => updateCondition(group.id, condition.id, { operator: e.target.value as Operator })}
              className="bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
            >
              {Object.entries(OPERATORS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          )}

          {/* Value (not for aggregates) */}
          {!isAggregate && (
            <input
              type="number"
              value={condition.value}
              onChange={(e) => updateCondition(group.id, condition.id, { value: parseFloat(e.target.value) })}
              className="w-20 bg-slate-600 text-white px-2 py-1 rounded text-sm border border-slate-500"
              step={condition.type === 'macd' ? '0.0001' : '1'}
            />
          )}

          {/* Aggregate indicator shows = Active */}
          {isAggregate && (
            <span className="text-green-400 text-sm font-medium">= Active</span>
          )}

          {/* Period (for indicators that use it) */}
          {['rsi', 'bb_percent', 'stochastic', 'ema_cross', 'sma_cross'].includes(condition.type) && (
            <div className="flex items-center gap-1">
              <span className="text-xs text-slate-400">P:</span>
              <input
                type="number"
                value={condition.period || 14}
                onChange={(e) => updateCondition(group.id, condition.id, { period: parseInt(e.target.value) })}
                className="w-12 bg-slate-600 text-white px-1 py-1 rounded text-sm border border-slate-500"
                min={2}
                max={200}
              />
            </div>
          )}

          {/* Remove condition */}
          <button
            type="button"
            onClick={() => removeCondition(group.id, condition.id)}
            className="text-red-400 hover:text-red-300 p-1"
            title="Remove condition"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    )
  }

  // Render a group
  const renderGroup = (group: ConditionGroup, groupIndex: number) => {
    return (
      <div key={group.id} className="relative">
        {/* Logic connector between groups */}
        {groupIndex > 0 && (
          <div className="flex items-center justify-center my-2">
            <button
              type="button"
              onClick={toggleGroupLogic}
              className={`px-3 py-1 rounded text-sm font-bold ${
                expression.groupLogic === 'and'
                  ? 'bg-blue-600 text-white'
                  : 'bg-purple-600 text-white'
              }`}
            >
              {expression.groupLogic.toUpperCase()}
            </button>
          </div>
        )}

        {/* Group container */}
        <div className="border-2 border-dashed border-slate-500 rounded-lg p-3 bg-slate-800/50">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Parentheses size={16} className="text-slate-400" />
              <span className="text-xs text-slate-400 font-medium">
                Group {groupIndex + 1}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded ${
                group.logic === 'and' ? 'bg-blue-600/30 text-blue-300' : 'bg-purple-600/30 text-purple-300'
              }`}>
                {group.logic.toUpperCase()} within
              </span>
            </div>
            <button
              type="button"
              onClick={() => removeGroup(group.id)}
              className="text-red-400 hover:text-red-300 text-xs"
              title="Remove group"
            >
              Remove Group
            </button>
          </div>

          {/* Conditions in this group */}
          <div className="space-y-1">
            {group.conditions.map((condition, index) =>
              renderCondition(group, condition, index)
            )}
          </div>

          {/* Add condition to group */}
          <button
            type="button"
            onClick={() => addConditionToGroup(group.id)}
            className="mt-2 flex items-center gap-1 text-blue-400 hover:text-blue-300 text-sm"
          >
            <Plus size={14} />
            Add Condition
          </button>
        </div>
      </div>
    )
  }

  // Generate human-readable expression string
  const getExpressionString = (): string => {
    if (expression.groups.length === 0) return 'No conditions'

    return expression.groups.map((group, gi) => {
      const groupStr = group.conditions.map((c, ci) => {
        const negateStr = c.negate ? 'NOT ' : ''
        const tf = TIMEFRAMES[c.timeframe]
        const condStr = CONDITION_TYPES[c.type]?.isAggregate
          ? `${c.type.toUpperCase()}=1`
          : `${c.type}${c.operator === 'greater_than' ? '>' : c.operator === 'less_than' ? '<' : c.operator === 'equal' ? '=' : c.operator}${c.value}`
        const connector = ci > 0 ? ` ${group.logic.toUpperCase()} ` : ''
        return `${connector}${negateStr}[${tf}]${condStr}`
      }).join('')

      const groupWrapper = group.conditions.length > 1 ? `(${groupStr})` : groupStr
      const groupConnector = gi > 0 ? ` ${expression.groupLogic.toUpperCase()} ` : ''
      return `${groupConnector}${groupWrapper}`
    }).join('')
  }

  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h4 className="text-md font-semibold text-white">{title}</h4>
          <p className="text-xs text-slate-400 mt-1">{description}</p>
        </div>
        <button
          type="button"
          onClick={() => setShowRawExpression(!showRawExpression)}
          className="text-xs text-slate-400 hover:text-slate-300"
        >
          {showRawExpression ? 'Hide' : 'Show'} Expression
        </button>
      </div>

      {/* Expression preview */}
      {showRawExpression && (
        <div className="mb-3 p-2 bg-slate-900 rounded border border-slate-600">
          <code className="text-xs text-green-400 font-mono break-all">
            {getExpressionString()}
          </code>
        </div>
      )}

      {/* Groups */}
      <div className="space-y-2">
        {expression.groups.map((group, index) => renderGroup(group, index))}
      </div>

      {/* Add group button */}
      <button
        type="button"
        onClick={addGroup}
        className="mt-3 flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded text-sm transition-colors w-full justify-center"
      >
        <Parentheses size={16} />
        Add Condition Group
      </button>

      {expression.groups.length === 0 && (
        <p className="text-xs text-slate-500 text-center mt-2">
          No conditions - will use default DCA settings
        </p>
      )}

      {/* Help text */}
      <div className="mt-3 p-2 bg-slate-900/50 rounded text-xs text-slate-400">
        <p className="font-medium text-slate-300 mb-1">Tips:</p>
        <ul className="list-disc list-inside space-y-0.5">
          <li>Click <span className="text-blue-400">AND/OR</span> to toggle logic between conditions or groups</li>
          <li>Click <CircleSlash size={10} className="inline mx-1" /> to negate (NOT) a condition</li>
          <li>Use groups to create complex logic like: (A AND B) OR (C OR D)</li>
        </ul>
      </div>
    </div>
  )
}

export default AdvancedConditionBuilder
