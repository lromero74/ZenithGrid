import {
  ConditionExpression,
  createEmptyExpression,
  Condition,
} from './AdvancedConditionBuilder'
import { ConditionType } from './PhaseConditionSelector'

// Safe number parsing that returns undefined for invalid input (instead of NaN)
export const safeParseFloat = (value: string): number | undefined => {
  const parsed = parseFloat(value)
  return isNaN(parsed) ? undefined : parsed
}

export const safeParseInt = (value: string): number | undefined => {
  const parsed = parseInt(value, 10)
  return isNaN(parsed) ? undefined : parsed
}

// Numeric input helper — allows the field to be empty while typing,
// applies the default only when the user leaves the field blank.
export const numericProps = (
  current: any,
  fallback: number,
  commit: (v: number) => void,
  isInt = false,
) => ({
  value: current === '' || current === null || current === undefined ? '' : current,
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.value === '') { commit('' as any); return }
    const v = isInt ? safeParseInt(e.target.value) : safeParseFloat(e.target.value)
    if (v !== undefined) commit(v)
  },
  onBlur: (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = isInt ? safeParseInt(e.target.value) : safeParseFloat(e.target.value)
    commit(v !== undefined ? v : fallback)
  },
})

export interface DCABudgetBreakdown {
  totalBudget: number
  budgetPerDeal: number
  baseOrderSize: number
  safetyOrders: { order: number; size: number; total: number }[]
  totalCapitalPerDeal: number
  maxSimultaneousCapital: number
  budgetUtilization: number  // %
  isOverAllocated: boolean  // True if minimum enforcement causes over-budget
  minimumEnforced: boolean  // True if any order was bumped to minimum
}

// DCA ladder calculation: divides the bot's budget equally among
// max concurrent deals, then within each deal splits budget across a base order
// plus exponentially scaled safety orders (each SO_i = base * scale^i).
export function calculateDCABudget(
  aggregateValue: number,
  budgetPercentage: number,
  maxConcurrentDeals: number,
  maxSafetyOrders: number,
  safetyOrderVolumeScale: number,
  exchangeMinimum: number
): DCABudgetBreakdown {
  const totalBudget = (aggregateValue * budgetPercentage) / 100

  // Budget per deal (divided by max concurrent deals)
  // NOTE: We divide by maxConcurrentDeals, NOT numPairs
  // The bot can analyze many pairs but only open maxConcurrentDeals positions at once
  const budgetPerDeal = totalBudget / Math.max(1, maxConcurrentDeals)

  // Total capital ratio: base order (1.0) + sum of scale^i for each safety order.
  const baseOrderSizeRatio = 1.0
  let totalRatio = baseOrderSizeRatio

  for (let i = 0; i < maxSafetyOrders; i++) {
    const soRatio = Math.pow(safetyOrderVolumeScale, i)
    totalRatio += soRatio
  }

  let baseOrderSize = budgetPerDeal / totalRatio
  let minimumEnforced = false

  if (baseOrderSize < exchangeMinimum) {
    baseOrderSize = exchangeMinimum
    minimumEnforced = true
  }

  const safetyOrders: { order: number; size: number; total: number }[] = []
  let runningTotal = baseOrderSize

  for (let i = 0; i < maxSafetyOrders; i++) {
    let soSize = baseOrderSize * Math.pow(safetyOrderVolumeScale, i)

    if (soSize < exchangeMinimum) {
      soSize = exchangeMinimum
      minimumEnforced = true
    }

    runningTotal += soSize
    safetyOrders.push({
      order: i + 1,
      size: soSize,
      total: runningTotal
    })
  }

  const totalCapitalPerDeal = runningTotal
  const maxSimultaneousCapital = totalCapitalPerDeal * maxConcurrentDeals

  // Utilization measured against per-deal budget, not total bot budget.
  const budgetUtilization = (totalCapitalPerDeal / budgetPerDeal) * 100

  const isOverAllocated = minimumEnforced && budgetUtilization > 100

  return {
    totalBudget,
    budgetPerDeal,
    baseOrderSize,
    safetyOrders,
    totalCapitalPerDeal,
    maxSimultaneousCapital,
    budgetUtilization,
    isOverAllocated,
    minimumEnforced
  }
}

// Normalize conditions from DB format (indicator) to frontend format (type).
// DB stores: { indicator: "ai_buy", ... }
// Frontend expects: { type: "ai_buy", ... }
export function normalizeCondition(c: any): Condition {
  return {
    ...c,
    type: (c.type || c.indicator) as ConditionType,
    negate: c.negate || false,
  }
}

// Convert stored conditions (flat array or expression) to ConditionExpression.
export function toConditionExpression(stored: any, logic: 'and' | 'or' = 'and'): ConditionExpression {
  if (stored && stored.groups && Array.isArray(stored.groups)) {
    return {
      groups: stored.groups.map((g: any) => ({
        ...g,
        conditions: (g.conditions || []).map(normalizeCondition),
      })),
      groupLogic: stored.groupLogic || 'and',
    }
  }

  if (Array.isArray(stored) && stored.length > 0) {
    return {
      groups: [{
        id: `grp_legacy_${Date.now()}`,
        conditions: stored.map(normalizeCondition),
        logic,
      }],
      groupLogic: 'and',
    }
  }

  return createEmptyExpression()
}

export function hasBullFlagEntry(expression: ConditionExpression): boolean {
  if (!expression?.groups) return false
  return expression.groups.some(group =>
    group.conditions?.some(c => c.type === 'bull_flag')
  )
}
