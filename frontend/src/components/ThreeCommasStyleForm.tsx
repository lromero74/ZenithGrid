import { useState, useCallback, useRef, useEffect } from 'react'
import AdvancedConditionBuilder, {
  ConditionExpression,
  createEmptyExpression,
  Condition,
} from './AdvancedConditionBuilder'
import { ConditionType } from './PhaseConditionSelector'

interface ThreeCommasStyleFormProps {
  config: Record<string, any>
  onChange: (config: Record<string, any>) => void
  quoteCurrency?: string  // 'BTC', 'USD', 'USDC', etc. - defaults to 'BTC'
  aggregateBtcValue?: number  // Total BTC value for min percentage calculation
  aggregateUsdValue?: number  // Total USD value for min percentage calculation
}

// Exchange minimum order sizes
const EXCHANGE_MINIMUMS = {
  BTC: 0.0001,  // 0.0001 BTC minimum for BTC pairs
  USD: 1.0,     // $1 minimum for USD pairs
  USDC: 1.0,    // $1 minimum for USDC pairs
  USDT: 1.0,    // $1 minimum for USDT pairs
  EUR: 1.0,     // 1 EUR minimum for EUR pairs
}

// Safe number parsing that returns undefined for invalid input (instead of NaN)
const safeParseFloat = (value: string): number | undefined => {
  const parsed = parseFloat(value)
  return isNaN(parsed) ? undefined : parsed
}

const safeParseInt = (value: string): number | undefined => {
  const parsed = parseInt(value, 10)
  return isNaN(parsed) ? undefined : parsed
}

// Get a number value with fallback, handling NaN properly
const getNumericValue = (value: any, fallback: number): number => {
  if (value === undefined || value === null || (typeof value === 'number' && isNaN(value))) {
    return fallback
  }
  return Number(value)
}

// Normalize conditions from DB format (indicator) to frontend format (type)
// DB stores: { indicator: "ai_buy", ... }
// Frontend expects: { type: "ai_buy", ... }
function normalizeCondition(c: any): Condition {
  return {
    ...c,
    // Use 'type' if present, otherwise fallback to 'indicator'
    type: (c.type || c.indicator) as ConditionType,
    negate: c.negate || false,
  }
}

// Convert stored conditions (which might be flat array or expression) to ConditionExpression
function toConditionExpression(stored: any, logic: 'and' | 'or' = 'and'): ConditionExpression {
  // Already in new format (has 'groups' array)
  if (stored && stored.groups && Array.isArray(stored.groups)) {
    return {
      groups: stored.groups.map((g: any) => ({
        ...g,
        conditions: (g.conditions || []).map(normalizeCondition),
      })),
      groupLogic: stored.groupLogic || 'and',
    }
  }

  // Old flat array format - convert to single group
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

  // Empty or invalid - return empty expression
  return createEmptyExpression()
}

// Check if entry conditions use bull_flag indicator (pattern-based entry)
function hasBullFlagEntry(expression: ConditionExpression): boolean {
  if (!expression?.groups) return false
  return expression.groups.some(group =>
    group.conditions?.some(c => c.type === 'bull_flag')
  )
}

function ThreeCommasStyleForm({ config, onChange, quoteCurrency = 'BTC', aggregateBtcValue, aggregateUsdValue }: ThreeCommasStyleFormProps) {
  // Track which fields have validation error (red flash)
  const [errorFields, setErrorFields] = useState<Set<string>>(new Set())
  const errorTimeoutRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  // Clean up timeouts on unmount
  useEffect(() => {
    return () => {
      Object.values(errorTimeoutRef.current).forEach(clearTimeout)
    }
  }, [])

  const updateConfig = (key: string, value: any) => {
    onChange({ ...config, [key]: value })
  }

  // Determine if this is a fiat (USD-based) or crypto (BTC-based) bot
  const isFiatQuote = ['USD', 'USDC', 'USDT', 'EUR'].includes(quoteCurrency)

  // Get the aggregate value for the quote currency
  const aggregateValue = isFiatQuote ? aggregateUsdValue : aggregateBtcValue

  // Get exchange minimum for this quote currency
  const exchangeMinimum = EXCHANGE_MINIMUMS[quoteCurrency as keyof typeof EXCHANGE_MINIMUMS] || 0.0001

  // Calculate minimum percentage needed to meet exchange minimum
  const calculateMinPercentage = useCallback(() => {
    if (!aggregateValue || aggregateValue <= 0) return 1 // Default 1% if no balance info
    const minPct = (exchangeMinimum / aggregateValue) * 100
    // Round up to nearest 0.1%
    return Math.ceil(minPct * 10) / 10
  }, [aggregateValue, exchangeMinimum])

  // Flash error and auto-correct percentage field
  const validateAndCorrectPercentage = useCallback((fieldKey: string, currentValue: number, minValue: number) => {
    if (currentValue < minValue) {
      // Add error state (red flash)
      setErrorFields(prev => new Set(prev).add(fieldKey))

      // Clear any existing timeout for this field
      if (errorTimeoutRef.current[fieldKey]) {
        clearTimeout(errorTimeoutRef.current[fieldKey])
      }

      // After 1 second, remove error state and auto-correct to minimum
      errorTimeoutRef.current[fieldKey] = setTimeout(() => {
        setErrorFields(prev => {
          const next = new Set(prev)
          next.delete(fieldKey)
          return next
        })
        updateConfig(fieldKey, minValue)
      }, 1000)
    }
  }, [updateConfig])

  // Calculate minimum safety order percentage (as % of base order)
  // Safety order = (base_order_percentage / 100) * aggregate * (safety_order_percentage / 100)
  // For SO to meet minimum: (base_pct / 100) * agg * (so_pct / 100) >= min
  // so_pct >= (min * 100 * 100) / (base_pct * agg)
  const calculateMinSafetyOrderPercentage = useCallback(() => {
    if (!aggregateValue || aggregateValue <= 0) return 10 // Default 10%
    const basePct = config.base_order_percentage || 10
    const minSoPct = (exchangeMinimum * 10000) / (basePct * aggregateValue)
    // Round up to nearest 1%
    return Math.max(10, Math.ceil(minSoPct))
  }, [aggregateValue, exchangeMinimum, config.base_order_percentage])

  // Use generic key names that work for both BTC and USD
  // Backend will store as base_order_size/safety_order_size with quote_currency
  const baseOrderKey = 'base_order_size'
  const safetyOrderKey = 'safety_order_size'

  // For backward compatibility, read from legacy keys if new ones not set
  const getBaseOrderSize = () => {
    if (config.base_order_size !== undefined) return config.base_order_size
    if (config.base_order_btc !== undefined) return config.base_order_btc
    return isFiatQuote ? 10 : 0.001  // Default: $10 for USD, 0.001 for BTC
  }

  const getSafetyOrderSize = () => {
    if (config.safety_order_size !== undefined) return config.safety_order_size
    if (config.safety_order_btc !== undefined) return config.safety_order_btc
    return isFiatQuote ? 5 : 0.0005  // Default: $5 for USD, 0.0005 for BTC
  }

  // Convert conditions to ConditionExpression format (handles legacy flat arrays)
  const baseOrderExpression = toConditionExpression(
    config.base_order_conditions,
    config.base_order_logic || 'and'
  )
  const safetyOrderExpression = toConditionExpression(
    config.safety_order_conditions,
    config.safety_order_logic || 'and'
  )
  const takeProfitExpression = toConditionExpression(
    config.take_profit_conditions,
    config.take_profit_logic || 'and'
  )

  // Bull flag entry uses pattern-calculated TSL/TTP, not percentage-based config
  const isPatternBasedEntry = hasBullFlagEntry(baseOrderExpression)

  return (
    <div className="space-y-6">
      {/* Deal Management Settings */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-lg font-semibold text-white mb-4">Deal Management</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Max Concurrent Deals
            </label>
            <input
              type="number"
              value={getNumericValue(config.max_concurrent_deals, 1)}
              onChange={(e) => updateConfig('max_concurrent_deals', safeParseInt(e.target.value) ?? 1)}
              min="1"
              max="20"
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
            />
            <p className="text-xs text-slate-400 mt-1">
              Maximum positions that can be open at the same time
            </p>
          </div>
        </div>
      </div>

      {/* Base Order Settings */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-lg font-semibold text-white mb-4">Base Order</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Base Order Type
            </label>
            <select
              value={config.base_order_type || 'percentage'}
              onChange={(e) => updateConfig('base_order_type', e.target.value)}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
            >
              <option value="percentage">% of {quoteCurrency} Balance</option>
              <option value="fixed">Fixed {quoteCurrency} Amount</option>
            </select>
          </div>

          {config.base_order_type === 'percentage' ? (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Base Order % of {quoteCurrency} Balance
                {aggregateValue && (
                  <span className="text-xs text-slate-400 ml-2">
                    (min: {calculateMinPercentage().toFixed(1)}%)
                  </span>
                )}
              </label>
              <input
                type="number"
                value={getNumericValue(config.base_order_percentage, 10)}
                onChange={(e) => updateConfig('base_order_percentage', safeParseFloat(e.target.value) ?? 10)}
                onBlur={() => validateAndCorrectPercentage('base_order_percentage', config.base_order_percentage ?? 10, calculateMinPercentage())}
                min={calculateMinPercentage()}
                max="100"
                step="0.1"
                className={`w-full bg-slate-700 text-white px-3 py-2 rounded border transition-colors duration-200 ${
                  errorFields.has('base_order_percentage')
                    ? 'border-red-500 bg-red-900/30'
                    : 'border-slate-600'
                }`}
              />
              {errorFields.has('base_order_percentage') && (
                <p className="text-xs text-red-400 mt-1">
                  Below exchange minimum. Adjusting to {calculateMinPercentage().toFixed(1)}%...
                </p>
              )}
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Base Order {quoteCurrency} Amount
              </label>
              <input
                type="number"
                value={getNumericValue(getBaseOrderSize(), isFiatQuote ? 10 : 0.001)}
                onChange={(e) => {
                  const value = safeParseFloat(e.target.value) ?? (isFiatQuote ? 10 : 0.001)
                  // Store both for backward compatibility and update quote_currency
                  updateConfig(baseOrderKey, value)
                  updateConfig('quote_currency', quoteCurrency)
                }}
                min={isFiatQuote ? 1 : 0.0001}
                max={isFiatQuote ? 100000 : 10}
                step={isFiatQuote ? 1 : 0.00000001}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
              />
            </div>
          )}
        </div>

        {/* Base Order Entry Conditions */}
        <AdvancedConditionBuilder
          title="Base Order Entry Conditions"
          description="When to open a new position (base order). Use groups for complex logic like (A AND B) OR (C AND D)."
          expression={baseOrderExpression}
          onChange={(expression) => updateConfig('base_order_conditions', expression)}
        />
      </div>

      {/* Pattern-Based Entry Info (Bull Flag) */}
      {isPatternBasedEntry && (
        <div className="bg-emerald-900/30 rounded-lg p-4 border border-emerald-700">
          <h3 className="text-lg font-semibold text-emerald-400 mb-2">Pattern-Based Exit Strategy</h3>
          <p className="text-sm text-emerald-300/80">
            Bull Flag entry uses <strong>pattern-calculated targets</strong> instead of percentage-based settings:
          </p>
          <ul className="text-sm text-emerald-300/80 mt-2 ml-4 list-disc space-y-1">
            <li><strong>Stop Loss</strong>: Trailing stop at pullback low (moves up as price rises)</li>
            <li><strong>Take Profit</strong>: Trailing TP at 2x risk (activates when target reached, then trails 1%)</li>
            <li><strong>No DCA</strong>: Bull flag is a momentum trade - uses TSL/TTP exit strategy</li>
          </ul>
        </div>
      )}

      {/* Safety Order Settings - hidden for pattern-based entries */}
      {!isPatternBasedEntry && (
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">Safety Orders (DCA)</h3>
          <label className="flex items-center gap-2 cursor-pointer">
            <span className="text-sm text-slate-400">
              {(config.max_safety_orders ?? 5) > 0 ? 'Enabled' : 'Disabled'}
            </span>
            <div className="relative">
              <input
                type="checkbox"
                checked={(config.max_safety_orders ?? 5) > 0}
                onChange={(e) => {
                  if (e.target.checked) {
                    updateConfig('max_safety_orders', 5)
                  } else {
                    updateConfig('max_safety_orders', 0)
                  }
                }}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
            </div>
          </label>
        </div>

        {(config.max_safety_orders ?? 5) > 0 && (
          <>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Max Safety Orders
            </label>
            <input
              type="number"
              value={getNumericValue(config.max_safety_orders, 5)}
              onChange={(e) => updateConfig('max_safety_orders', safeParseInt(e.target.value) ?? 5)}
              min="1"
              max="20"
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Safety Order Type
            </label>
            <select
              value={config.safety_order_type || 'percentage_of_base'}
              onChange={(e) => updateConfig('safety_order_type', e.target.value)}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
            >
              <option value="percentage_of_base">% of Base Order</option>
              <option value="fixed">Fixed {quoteCurrency} Amount</option>
            </select>
          </div>

          {config.safety_order_type === 'percentage_of_base' ? (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Safety Order % of Base
                {aggregateValue && (
                  <span className="text-xs text-slate-400 ml-2">
                    (min: {calculateMinSafetyOrderPercentage()}%)
                  </span>
                )}
              </label>
              <input
                type="number"
                value={getNumericValue(config.safety_order_percentage, 50)}
                onChange={(e) =>
                  updateConfig('safety_order_percentage', safeParseFloat(e.target.value) ?? 50)
                }
                onBlur={() => validateAndCorrectPercentage('safety_order_percentage', config.safety_order_percentage ?? 50, calculateMinSafetyOrderPercentage())}
                min={calculateMinSafetyOrderPercentage()}
                max="500"
                step="1"
                className={`w-full bg-slate-700 text-white px-3 py-2 rounded border transition-colors duration-200 ${
                  errorFields.has('safety_order_percentage')
                    ? 'border-red-500 bg-red-900/30'
                    : 'border-slate-600'
                }`}
              />
              {errorFields.has('safety_order_percentage') && (
                <p className="text-xs text-red-400 mt-1">
                  Below exchange minimum. Adjusting to {calculateMinSafetyOrderPercentage()}%...
                </p>
              )}
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Safety Order {quoteCurrency} Amount
              </label>
              <input
                type="number"
                value={getNumericValue(getSafetyOrderSize(), isFiatQuote ? 5 : 0.0005)}
                onChange={(e) => {
                  const value = safeParseFloat(e.target.value) ?? (isFiatQuote ? 5 : 0.0005)
                  updateConfig(safetyOrderKey, value)
                }}
                min={isFiatQuote ? 1 : 0.0001}
                max={isFiatQuote ? 100000 : 10}
                step={isFiatQuote ? 1 : 0.00000001}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Price Deviation %
            </label>
            <input
              type="number"
              value={getNumericValue(config.price_deviation, 2.0)}
              onChange={(e) => updateConfig('price_deviation', safeParseFloat(e.target.value) ?? 2.0)}
              min="0.1"
              max="20"
              step="0.1"
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
            />
            <p className="text-xs text-slate-400 mt-1">
              Minimum price drop for first DCA
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              DCA Target Reference
            </label>
            <select
              value={config.dca_target_reference || 'average_price'}
              onChange={(e) => updateConfig('dca_target_reference', e.target.value)}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
            >
              <option value="base_order">Base Order Price (first buy)</option>
              <option value="average_price">Average Entry Price</option>
              <option value="last_buy">Last Buy Price</option>
            </select>
            <p className="text-xs text-slate-400 mt-1">
              Calculate DCA deviation from this reference
            </p>
          </div>
        </div>

        {/* Safety Order Entry Conditions */}
        <AdvancedConditionBuilder
          title="Safety Order Entry Conditions (Optional)"
          description="Additional conditions for DCA. Price target must ALWAYS be met first, then these conditions are checked."
          expression={safetyOrderExpression}
          onChange={(expression) => updateConfig('safety_order_conditions', expression)}
        />

        {/* Volume/Step Scaling - always visible like 3Commas */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 pt-4 border-t border-slate-600">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Safety Order Volume Scale
              </label>
              <input
                type="number"
                value={getNumericValue(config.safety_order_volume_scale, 1.0)}
                onChange={(e) =>
                  updateConfig('safety_order_volume_scale', safeParseFloat(e.target.value) ?? 1.0)
                }
                min="1.0"
                max="5.0"
                step="0.1"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
              />
              <p className="text-xs text-slate-400 mt-1">1.0 = same size, 2.0 = double each time</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Safety Order Step Scale
              </label>
              <input
                type="number"
                value={getNumericValue(config.safety_order_step_scale, 1.0)}
                onChange={(e) =>
                  updateConfig('safety_order_step_scale', safeParseFloat(e.target.value) ?? 1.0)
                }
                min="1.0"
                max="5.0"
                step="0.1"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
              />
              <p className="text-xs text-slate-400 mt-1">
                1.0 = even spacing, higher = exponential spacing
              </p>
            </div>
          </div>
          </>
        )}
      </div>
      )}

      {/* Take Profit Settings - hidden for pattern-based entries */}
      {!isPatternBasedEntry && (
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-lg font-semibold text-white mb-4">Take Profit / Exit</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Take Profit %
            </label>
            <input
              type="number"
              value={getNumericValue(config.take_profit_percentage, 3.0)}
              onChange={(e) => updateConfig('take_profit_percentage', safeParseFloat(e.target.value) ?? 3.0)}
              min="0.1"
              max="50"
              step="0.1"
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
            />
            <p className="text-xs text-slate-400 mt-1">
              Always active (minimum profit target)
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Condition Exit Override %
              <span className="text-slate-500 font-normal ml-1">(optional)</span>
            </label>
            <input
              type="number"
              value={config.min_profit_for_conditions !== undefined && config.min_profit_for_conditions !== null
                ? config.min_profit_for_conditions
                : ''}
              onChange={(e) => {
                const val = e.target.value === '' ? undefined : safeParseFloat(e.target.value)
                updateConfig('min_profit_for_conditions', val)
              }}
              min="-50"
              max="50"
              step="0.1"
              placeholder={`${config.take_profit_percentage || 3}%`}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
            />
            <p className="text-xs text-slate-400 mt-1">
              Uses Take Profit % by default. Set only to allow condition exits at different profit.
            </p>
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-slate-300 mb-1">
              <input
                type="checkbox"
                checked={config.stop_loss_enabled || false}
                onChange={(e) => updateConfig('stop_loss_enabled', e.target.checked)}
                className="rounded"
              />
              Enable Stop Loss
            </label>
            {config.stop_loss_enabled && (
              <input
                type="number"
                value={getNumericValue(config.stop_loss_percentage, -10)}
                onChange={(e) =>
                  updateConfig('stop_loss_percentage', safeParseFloat(e.target.value) ?? -10)
                }
                min="-50"
                max="-0.1"
                step="0.1"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
              />
            )}
          </div>

          <div className="md:col-span-2">
            <label className="flex items-center gap-2 text-sm font-medium text-slate-300 mb-1">
              <input
                type="checkbox"
                checked={config.trailing_take_profit || false}
                onChange={(e) => updateConfig('trailing_take_profit', e.target.checked)}
                className="rounded"
              />
              Enable Trailing Take Profit
            </label>
            {config.trailing_take_profit && (
              <div className="mt-2">
                <label className="block text-sm text-slate-400 mb-1">Trailing Deviation %</label>
                <input
                  type="number"
                  value={getNumericValue(config.trailing_deviation, 1.0)}
                  onChange={(e) =>
                    updateConfig('trailing_deviation', safeParseFloat(e.target.value) ?? 1.0)
                  }
                  min="0.1"
                  max="10"
                  step="0.1"
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
            )}
          </div>
        </div>

        {/* Take Profit Conditions */}
        <AdvancedConditionBuilder
          title="Additional Exit Conditions (Optional)"
          description="Extra conditions to trigger sell (TP% always applies). Use groups for complex exit logic."
          expression={takeProfitExpression}
          onChange={(expression) => updateConfig('take_profit_conditions', expression)}
        />
      </div>
      )}

      {/* Summary */}
      <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
        <h4 className="text-sm font-semibold text-slate-300 mb-2">Strategy Summary</h4>
        <div className="text-xs text-slate-400 space-y-1">
          <p>
            🎯 <strong>Max Positions:</strong> {config.max_concurrent_deals || 1}
          </p>
          <p>
            📥 <strong>Base Order:</strong>{' '}
            {baseOrderExpression.groups.length > 0
              ? `${baseOrderExpression.groups.length} group(s), ${baseOrderExpression.groups.reduce((sum, g) => sum + g.conditions.length, 0)} condition(s)`
              : 'Manual start only'}
          </p>
          {isPatternBasedEntry ? (
            <>
              <p>
                🛡️ <strong>Stop Loss:</strong> Trailing (at pullback low)
              </p>
              <p>
                📤 <strong>Exit:</strong> Trailing TP (2x risk target, trails 1%)
              </p>
            </>
          ) : (
            <>
              <p>
                🔁 <strong>Safety Orders:</strong>{' '}
                {(config.max_safety_orders ?? 5) === 0
                  ? 'Disabled'
                  : safetyOrderExpression.groups.length > 0
                    ? `${safetyOrderExpression.groups.length} group(s), ${safetyOrderExpression.groups.reduce((sum, g) => sum + g.conditions.length, 0)} condition(s)`
                    : `Price deviation (${config.price_deviation || 2}%)`}
              </p>
              <p>
                📤 <strong>Exit:</strong> Take Profit {config.take_profit_percentage || 3}%
                {takeProfitExpression.groups.length > 0 &&
                  ` + ${takeProfitExpression.groups.length} group(s), ${takeProfitExpression.groups.reduce((sum, g) => sum + g.conditions.length, 0)} condition(s)`}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default ThreeCommasStyleForm
