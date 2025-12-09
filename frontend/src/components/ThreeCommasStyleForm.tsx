import AdvancedConditionBuilder, {
  ConditionExpression,
  createEmptyExpression,
  Condition,
} from './AdvancedConditionBuilder'
import { ConditionType } from './PhaseConditionSelector'

interface ThreeCommasStyleFormProps {
  config: Record<string, any>
  onChange: (config: Record<string, any>) => void
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

function ThreeCommasStyleForm({ config, onChange }: ThreeCommasStyleFormProps) {
  const updateConfig = (key: string, value: any) => {
    onChange({ ...config, [key]: value })
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
              <option value="percentage">% of BTC Balance</option>
              <option value="fixed_btc">Fixed BTC Amount</option>
            </select>
          </div>

          {config.base_order_type === 'percentage' ? (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Base Order % of BTC Balance
              </label>
              <input
                type="number"
                value={getNumericValue(config.base_order_percentage, 10)}
                onChange={(e) => updateConfig('base_order_percentage', safeParseFloat(e.target.value) ?? 10)}
                min="1"
                max="100"
                step="0.1"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
              />
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Base Order BTC Amount
              </label>
              <input
                type="number"
                value={getNumericValue(config.base_order_btc, 0.001)}
                onChange={(e) => updateConfig('base_order_btc', safeParseFloat(e.target.value) ?? 0.001)}
                min="0.0001"
                max="10"
                step="0.00000001"
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

      {/* Safety Order Settings */}
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
              <option value="fixed_btc">Fixed BTC Amount</option>
            </select>
          </div>

          {config.safety_order_type === 'percentage_of_base' ? (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Safety Order % of Base
              </label>
              <input
                type="number"
                value={getNumericValue(config.safety_order_percentage, 50)}
                onChange={(e) =>
                  updateConfig('safety_order_percentage', safeParseFloat(e.target.value) ?? 50)
                }
                min="10"
                max="500"
                step="1"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
              />
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Safety Order BTC Amount
              </label>
              <input
                type="number"
                value={getNumericValue(config.safety_order_btc, 0.0005)}
                onChange={(e) => updateConfig('safety_order_btc', safeParseFloat(e.target.value) ?? 0.0005)}
                min="0.0001"
                max="10"
                step="0.00000001"
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

      {/* Take Profit Settings */}
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
        </div>
      </div>
    </div>
  )
}

export default ThreeCommasStyleForm
