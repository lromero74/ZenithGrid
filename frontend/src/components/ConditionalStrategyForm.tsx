import { useState } from 'react'
import ConditionBuilder, { ConditionGroup } from './ConditionBuilder'

interface ConditionalStrategyFormProps {
  config: Record<string, any>
  onChange: (config: Record<string, any>) => void
}

const DEFAULT_BUY_CONDITIONS: ConditionGroup = {
  id: 'buy_root',
  logic: 'and',
  conditions: [
    {
      id: 'buy_cond_1',
      indicator: 'rsi',
      operator: 'less_than',
      value_type: 'static',
      static_value: 30,
      indicator_params: { period: 14 },
    },
  ],
  sub_groups: [],
}

const DEFAULT_SELL_CONDITIONS: ConditionGroup = {
  id: 'sell_root',
  logic: 'and',
  conditions: [
    {
      id: 'sell_cond_1',
      indicator: 'rsi',
      operator: 'greater_than',
      value_type: 'static',
      static_value: 70,
      indicator_params: { period: 14 },
    },
  ],
  sub_groups: [],
}

function ConditionalStrategyForm({ config, onChange }: ConditionalStrategyFormProps) {
  const [showAdvanced, setShowAdvanced] = useState(false)

  const updateConfig = (key: string, value: any) => {
    onChange({ ...config, [key]: value })
  }

  const buyConditions = config.buy_conditions || DEFAULT_BUY_CONDITIONS
  const sellConditions = config.sell_conditions || DEFAULT_SELL_CONDITIONS

  return (
    <div className="space-y-6">
      {/* Basic DCA Settings */}
      <div className="bg-slate-800 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-4">DCA Settings</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Base Order */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Base Order Type
            </label>
            <select
              value={config.base_order_type || 'percentage'}
              onChange={(e) => updateConfig('base_order_type', e.target.value)}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          )}

          {/* Safety Orders */}
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
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Price Deviation %
            </label>
            <input
              type="number"
              value={config.price_deviation || 2.0}
              onChange={(e) => updateConfig('price_deviation', parseFloat(e.target.value))}
              min="0.1"
              max="20"
              step="0.1"
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-slate-400 mt-1">
              Price drop % to trigger first safety order
            </p>
          </div>

          {/* Take Profit */}
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
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Stop Loss */}
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
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            )}
          </div>
        </div>

        {/* Advanced Settings Toggle */}
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="mt-4 text-blue-400 hover:text-blue-300 text-sm transition-colors"
        >
          {showAdvanced ? '− Hide' : '+ Show'} Advanced Settings
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 pt-4 border-t border-slate-600">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Safety Order Type
              </label>
              <select
                value={config.safety_order_type || 'percentage_of_base'}
                onChange={(e) => updateConfig('safety_order_type', e.target.value)}
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}

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
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-slate-400 mt-1">
                1.0 = even spacing, higher = exponential spacing
              </p>
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
                    className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Buy Conditions */}
      <div className="bg-slate-800 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-2">Buy Conditions</h3>
        <p className="text-sm text-slate-400 mb-4">
          When to open a new position (base order)
        </p>
        <ConditionBuilder
          group={buyConditions}
          onChange={(newGroup) => updateConfig('buy_conditions', newGroup)}
        />
      </div>

      {/* Sell Conditions */}
      <div className="bg-slate-800 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-2">Sell Conditions (Optional)</h3>
        <p className="text-sm text-slate-400 mb-4">
          Additional conditions to trigger sell. Take profit and stop loss always apply.
        </p>
        <ConditionBuilder
          group={sellConditions}
          onChange={(newGroup) => updateConfig('sell_conditions', newGroup)}
        />
      </div>

      {/* Preview */}
      <div className="bg-slate-800 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-white mb-2">Configuration Preview</h3>
        <pre className="bg-slate-900 p-3 rounded text-xs text-slate-300 overflow-auto max-h-96">
          {JSON.stringify({ ...config, buy_conditions: buyConditions, sell_conditions: sellConditions }, null, 2)}
        </pre>
      </div>
    </div>
  )
}

export default ConditionalStrategyForm
