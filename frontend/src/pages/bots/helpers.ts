import { Bot } from '../../types'

function conditionUsesAI(cond: any): boolean {
  const indicatorType = cond.type || cond.indicator
  return indicatorType === 'ai_buy' || indicatorType === 'ai_sell'
}

// Helper function to check if a bot uses AI indicators in its conditions
function botUsesAIIndicators(bot: Bot): boolean {
  // Check legacy ai_autonomous strategy type
  if (bot.strategy_type === 'ai_autonomous') return true

  // Check for AI indicators in strategy_config conditions
  const config = bot.strategy_config
  if (!config) return false

  // Check all condition arrays/objects for ai_buy or ai_sell
  const conditionSources = [
    config.base_order_conditions,
    config.safety_order_conditions,
    config.take_profit_conditions,
  ]

  for (const conditions of conditionSources) {
    // Handle flat array format: [{indicator: "ai_buy"...}]
    if (Array.isArray(conditions)) {
      for (const cond of conditions) {
        if (conditionUsesAI(cond)) return true
      }
    }
    // Handle grouped format: {groups: [{conditions: [...]}]}
    else if (conditions && typeof conditions === 'object' && conditions.groups) {
      for (const group of conditions.groups) {
        if (Array.isArray(group.conditions)) {
          for (const cond of group.conditions) {
            if (conditionUsesAI(cond)) return true
          }
        }
      }
    }
  }
  return false
}

// Helper function to check if a bot uses Bull Flag indicator in its conditions
function botUsesBullFlagIndicator(bot: Bot): boolean {
  // Check legacy bull_flag strategy type
  if (bot.strategy_type === 'bull_flag') return true

  // Check for bull_flag indicator in strategy_config conditions
  const config = bot.strategy_config
  if (!config) return false

  const conditionArrays = [
    config.base_order_conditions,
    config.safety_order_conditions,
    config.take_profit_conditions,
  ]

  for (const conditions of conditionArrays) {
    if (Array.isArray(conditions)) {
      for (const cond of conditions) {
        if (cond.type === 'bull_flag' || cond.indicator === 'bull_flag') {
          return true
        }
      }
    }
  }
  return false
}

// Helper function to check if a bot uses non-AI indicator conditions
// Shows the chart icon for bots that have conditions but NOT AI indicators
function botUsesNonAIIndicators(bot: Bot): boolean {
  // Skip if it uses AI indicators (they have their own Brain icon)
  if (botUsesAIIndicators(bot)) return false

  // Check if it's indicator_based strategy type
  if (bot.strategy_type !== 'indicator_based') return false

  // Check if it has any conditions configured
  const config = bot.strategy_config
  if (!config) return false

  const conditionSources = [
    config.base_order_conditions,
    config.safety_order_conditions,
    config.take_profit_conditions,
  ]

  for (const conditions of conditionSources) {
    // Handle flat array format
    if (Array.isArray(conditions) && conditions.length > 0) {
      return true
    }
    // Handle grouped format: {groups: [{conditions: [...]}]}
    else if (conditions && typeof conditions === 'object' && conditions.groups) {
      for (const group of conditions.groups) {
        if (Array.isArray(group.conditions) && group.conditions.length > 0) {
          return true
        }
      }
    }
  }
  return false
}

export { conditionUsesAI, botUsesAIIndicators, botUsesBullFlagIndicator, botUsesNonAIIndicators }
