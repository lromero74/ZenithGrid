/**
 * Pure helpers and presets for AdvancedConditionBuilder. Extracted so the
 * component file only exports a component (keeps Fast Refresh happy).
 */

import type { RiskPreset, Condition, ConditionExpression } from './AdvancedConditionBuilder'

// Risk preset defaults for AI indicators
export const RISK_PRESETS: Record<RiskPreset, {
  label: string
  description: string
  min_confluence_score: number
  ai_confidence_threshold: number
}> = {
  aggressive: {
    label: 'Aggressive',
    description: 'Lower thresholds, more signals',
    min_confluence_score: 50,
    ai_confidence_threshold: 60,
  },
  moderate: {
    label: 'Moderate',
    description: 'Balanced risk/reward',
    min_confluence_score: 65,
    ai_confidence_threshold: 70,
  },
  conservative: {
    label: 'Conservative',
    description: 'Higher thresholds, fewer but stronger signals',
    min_confluence_score: 80,
    ai_confidence_threshold: 80,
  },
  speculative: {
    label: 'Speculative (2x Hunter)',
    description: 'Catalyst-hunt mode — respects the account Speculative Allocation cap; expect low win rate with asymmetric upside',
    min_confluence_score: 35,
    ai_confidence_threshold: 70,
  },
}

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
