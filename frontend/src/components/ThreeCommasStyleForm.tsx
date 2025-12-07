import PhaseConditionSelector, { PhaseCondition, ConditionType } from './PhaseConditionSelector'

interface ThreeCommasStyleFormProps {
  config: Record<string, any>
  onChange: (config: Record<string, any>) => void
}

// Normalize conditions from DB format (indicator) to frontend format (type)
// DB stores: { indicator: "ai_buy", ... }
// Frontend expects: { type: "ai_buy", ... }
function normalizeConditions(conditions: any[]): PhaseCondition[] {
  if (!conditions || !Array.isArray(conditions)) return []
  return conditions.map((c) => ({
    ...c,
    // Use 'type' if present, otherwise fallback to 'indicator'
    type: (c.type || c.indicator) as ConditionType,
  }))
}

function ThreeCommasStyleForm({ config, onChange }: ThreeCommasStyleFormProps) {
  const updateConfig = (key: string, value: any) => {
    onChange({ ...config, [key]: value })
  }

  // Normalize conditions to handle both 'type' and 'indicator' keys from DB
  const baseOrderConditions: PhaseCondition[] = normalizeConditions(config.base_order_conditions)
  const safetyOrderConditions: PhaseCondition[] = normalizeConditions(config.safety_order_conditions)
  const takeProfitConditions: PhaseCondition[] = normalizeConditions(config.take_profit_conditions)

  const baseOrderLogic = config.base_order_logic || 'and'
  const safetyOrderLogic = config.safety_order_logic || 'and'
  const takeProfitLogic = config.take_profit_logic || 'and'

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
              value={config.max_concurrent_deals || 1}
              onChange={(e) => updateConfig('max_concurrent_deals', parseInt(e.target.value))}
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
                value={config.base_order_percentage || 10}
                onChange={(e) => updateConfig('base_order_percentage', parseFloat(e.target.value))}
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
                value={config.base_order_btc || 0.001}
                onChange={(e) => updateConfig('base_order_btc', parseFloat(e.target.value))}
                min="0.0001"
                max="10"
                step="0.0001"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
              />
            </div>
          )}
        </div>

        {/* Base Order Entry Conditions */}
        <PhaseConditionSelector
          title="Base Order Entry Conditions"
          description="When to open a new position (base order)"
          conditions={baseOrderConditions}
          onChange={(conditions) => updateConfig('base_order_conditions', conditions)}
          allowMultiple={true}
          logic={baseOrderLogic}
          onLogicChange={(logic) => updateConfig('base_order_logic', logic)}
        />
      </div>

      {/* Safety Order Settings */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-lg font-semibold text-white mb-4">Safety Orders</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Max Safety Orders
            </label>
            <input
              type="number"
              value={config.max_safety_orders || 5}
              onChange={(e) => updateConfig('max_safety_orders', parseInt(e.target.value))}
              min="0"
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
                value={config.safety_order_percentage || 50}
                onChange={(e) =>
                  updateConfig('safety_order_percentage', parseFloat(e.target.value))
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
                value={config.safety_order_btc || 0.0005}
                onChange={(e) => updateConfig('safety_order_btc', parseFloat(e.target.value))}
                min="0.0001"
                max="10"
                step="0.0001"
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Price Deviation % (Fallback)
            </label>
            <input
              type="number"
              value={config.price_deviation || 2.0}
              onChange={(e) => updateConfig('price_deviation', parseFloat(e.target.value))}
              min="0.1"
              max="20"
              step="0.1"
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
            />
            <p className="text-xs text-slate-400 mt-1">
              Used if no indicator conditions are set
            </p>
          </div>
        </div>

        {/* Safety Order Entry Conditions */}
        <PhaseConditionSelector
          title="Safety Order Entry Conditions (Optional)"
          description="When to add safety orders (if empty, uses price deviation only)"
          conditions={safetyOrderConditions}
          onChange={(conditions) => updateConfig('safety_order_conditions', conditions)}
          allowMultiple={true}
          logic={safetyOrderLogic}
          onLogicChange={(logic) => updateConfig('safety_order_logic', logic)}
        />

        {/* Volume/Step Scaling - always visible like 3Commas */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 pt-4 border-t border-slate-600">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Safety Order Volume Scale
              </label>
              <input
                type="number"
                value={config.safety_order_volume_scale || 1.0}
                onChange={(e) =>
                  updateConfig('safety_order_volume_scale', parseFloat(e.target.value))
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
                value={config.safety_order_step_scale || 1.0}
                onChange={(e) =>
                  updateConfig('safety_order_step_scale', parseFloat(e.target.value))
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
              value={config.take_profit_percentage || 3.0}
              onChange={(e) => updateConfig('take_profit_percentage', parseFloat(e.target.value))}
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
              Min Profit % for Condition Exit
            </label>
            <input
              type="number"
              value={config.min_profit_for_conditions ?? 0.0}
              onChange={(e) => updateConfig('min_profit_for_conditions', parseFloat(e.target.value))}
              min="-50"
              max="50"
              step="0.1"
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
            />
            <p className="text-xs text-slate-400 mt-1">
              Min profit to exit on conditions below (0 = breakeven)
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
                value={config.stop_loss_percentage || -10}
                onChange={(e) =>
                  updateConfig('stop_loss_percentage', parseFloat(e.target.value))
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
                  value={config.trailing_deviation || 1.0}
                  onChange={(e) =>
                    updateConfig('trailing_deviation', parseFloat(e.target.value))
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
        <PhaseConditionSelector
          title="Additional Exit Conditions (Optional)"
          description="Extra conditions to trigger sell (TP% always applies)"
          conditions={takeProfitConditions}
          onChange={(conditions) => updateConfig('take_profit_conditions', conditions)}
          allowMultiple={true}
          logic={takeProfitLogic}
          onLogicChange={(logic) => updateConfig('take_profit_logic', logic)}
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
            {baseOrderConditions.length > 0
              ? `${baseOrderConditions.length} condition(s) with ${baseOrderLogic.toUpperCase()} logic`
              : 'Manual start only'}
          </p>
          <p>
            🔁 <strong>Safety Orders:</strong>{' '}
            {safetyOrderConditions.length > 0
              ? `${safetyOrderConditions.length} condition(s) with ${safetyOrderLogic.toUpperCase()} logic`
              : `Price deviation (${config.price_deviation || 2}%)`}
          </p>
          <p>
            📤 <strong>Exit:</strong> Take Profit {config.take_profit_percentage || 3}%
            {takeProfitConditions.length > 0 &&
              ` + ${takeProfitConditions.length} condition(s) with ${takeProfitLogic.toUpperCase()} logic`}
          </p>
        </div>
      </div>
    </div>
  )
}

export default ThreeCommasStyleForm
