import React from 'react'
import type { StrategyParameter } from '../../../types'
import DCABudgetConfigForm from '../../../components/DCABudgetConfigForm'
import PhaseConditionSelector from '../../../components/PhaseConditionSelector'
import { isParameterVisible } from '../../../components/bots'
import type { BotFormData } from '../../../components/bots'

interface StrategyConfigSectionProps {
  formData: BotFormData
  setFormData: (data: BotFormData) => void
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedStrategy: any
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handleParamChange: (paramName: string, value: any) => void
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  aggregateData: any
}

/**
 * Renders a single strategy parameter input based on its
 * type (bool, select, text, number, conditions, toggle).
 */
function ParameterInput({
  param,
  formData,
  handleParamChange,
}: {
  param: StrategyParameter
  formData: BotFormData
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handleParamChange: (name: string, value: any) => void
}) {
  const value = formData.strategy_config[param.name]

  // Special: position_control_mode toggle switch
  if (
    param.name === 'position_control_mode' &&
    param.options &&
    param.options.length === 2
  ) {
    const isAiDirected = value === 'ai_directed'
    return (
      <div className="flex items-center justify-between bg-slate-700 rounded-lg p-4 border border-slate-600">
        <div className="flex-1">
          <div className="text-sm font-medium text-white mb-1">
            {isAiDirected
              ? '🤖 AI-Directed Mode'
              : '⚙️ Strict Parameters Mode'}
          </div>
          <div className="text-xs text-slate-400">
            {isAiDirected
              ? 'AI dynamically controls position sizes within budget limits'
              : 'Use fixed parameters for all position sizing'}
          </div>
        </div>
        <label className="relative inline-flex items-center cursor-pointer ml-4">
          <input
            type="checkbox"
            checked={isAiDirected}
            onChange={(e) =>
              handleParamChange(
                param.name,
                e.target.checked ? 'ai_directed' : 'strict'
              )
            }
            className="sr-only peer"
          />
          <div className="w-14 h-7 bg-slate-600 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-purple-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all peer-checked:bg-purple-600"></div>
        </label>
      </div>
    )
  }

  // Conditions type (condition builder for indicators)
  if ((param.type as string) === 'conditions') {
    return (
      <PhaseConditionSelector
        title={param.display_name || ''}
        description={param.description || ''}
        conditions={
          formData.strategy_config[param.name] || []
        }
        onChange={(conditions) =>
          handleParamChange(param.name, conditions)
        }
        allowMultiple={true}
      />
    )
  }

  // Boolean checkbox
  if (param.type === 'bool') {
    return (
      <label className="flex items-center space-x-2">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) =>
            handleParamChange(
              param.name,
              e.target.checked
            )
          }
          className="rounded border-slate-600 bg-slate-700 text-blue-500"
        />
        <span className="text-sm text-slate-300">
          {param.description}
        </span>
      </label>
    )
  }

  // Select dropdown
  if (param.options && param.options.length > 0) {
    return (
      <select
        value={String(value)}
        onChange={(e) =>
          handleParamChange(param.name, e.target.value)
        }
        className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
      >
        {param.options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    )
  }

  // Multiline text
  if (param.type === 'text') {
    return (
      <div>
        <textarea
          value={value || ''}
          onChange={(e) =>
            handleParamChange(param.name, e.target.value)
          }
          rows={4}
          placeholder={
            param.name === 'custom_instructions'
              ? 'Add any specific instructions for the AI (e.g., "Focus on BTC pairs", "Avoid trading during low volume hours")'
              : param.description
          }
          className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white resize-y"
        />
        {param.name === 'custom_instructions' && (
          <div className="mt-2 text-xs text-slate-400 bg-slate-800/50 rounded p-3 border border-slate-700">
            <p className="font-medium text-slate-300 mb-1">
              Default AI Instructions:
            </p>
            <p className="text-slate-400">
              The AI will analyze market data, sentiment,
              and news to make intelligent trading
              decisions. It will be{' '}
              {formData.strategy_config?.risk_tolerance ||
                'moderate'}{' '}
              in its recommendations and will never sell
              at a loss. Your custom instructions will be
              added to guide its specific trading behavior.
            </p>
          </div>
        )}
      </div>
    )
  }

  // Number / text input
  const inputType =
    param.type === 'int' || param.type === 'float'
      ? 'number'
      : 'text'
  const step =
    param.type === 'float'
      ? 'any'
      : param.type === 'int'
        ? '1'
        : undefined

  const displayValue =
    value === undefined ||
    value === null ||
    (typeof value === 'number' && isNaN(value))
      ? ''
      : value

  return (
    <input
      type={inputType}
      step={step}
      min={param.min_value}
      max={param.max_value}
      value={displayValue}
      onChange={(e) => {
        const rawVal = e.target.value
        let val
        if (param.type === 'float') {
          val =
            rawVal === '' ? undefined : parseFloat(rawVal)
          if (typeof val === 'number' && isNaN(val))
            val = undefined
        } else if (param.type === 'int') {
          val =
            rawVal === '' ? undefined : parseInt(rawVal)
          if (typeof val === 'number' && isNaN(val))
            val = undefined
        } else {
          val = rawVal
        }
        handleParamChange(param.name, val)
      }}
      onBlur={() => {
        const currentValue =
          formData.strategy_config[param.name]
        if (
          currentValue === undefined ||
          currentValue === null ||
          currentValue === ''
        ) {
          handleParamChange(param.name, param.default)
        }
      }}
      className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
    />
  )
}

/**
 * Renders strategy configuration section with
 * dynamic parameters, grouped by category.
 */
export function StrategyConfigSection({
  formData,
  setFormData,
  selectedStrategy,
  handleParamChange,
  aggregateData,
}: StrategyConfigSectionProps) {
  if (
    !selectedStrategy ||
    (selectedStrategy.id !== 'conditional_dca' &&
      selectedStrategy.id !== 'indicator_based' &&
      selectedStrategy.parameters.length === 0)
  ) {
    return null
  }

  // Helper to render a single parameter input
  const renderParameterInput = (
    param: StrategyParameter
  ) => (
    <ParameterInput
      param={param}
      formData={formData}
      handleParamChange={handleParamChange}
    />
  )

  return (
    <div className="border-b border-slate-700 pb-6">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <span className="text-blue-400">
          {formData.strategy_type === 'ai_autonomous'
            ? '6'
            : '7'}
          .
        </span>{' '}
        Strategy Parameters
      </h3>

      {formData.strategy_type === 'conditional_dca' ||
      formData.strategy_type === 'indicator_based' ? (
        <DCABudgetConfigForm
          config={formData.strategy_config}
          onChange={(newConfig) =>
            setFormData({
              ...formData,
              strategy_config: newConfig,
            })
          }
          quoteCurrency={
            formData.product_ids.length > 0
              ? formData.product_ids[0].split('-')[1]
              : 'BTC'
          }
          aggregateBtcValue={
            aggregateData?.aggregate_btc_value
          }
          aggregateUsdValue={
            aggregateData?.aggregate_usd_value
          }
          budgetPercentage={formData.budget_percentage}
          numPairs={formData.product_ids.length}
          splitBudget={formData.split_budget_across_pairs}
          maxConcurrentDeals={
            formData.strategy_config.max_concurrent_deals
          }
        />
      ) : selectedStrategy.parameters.length > 0 ? (
        <StrategyParameterGroups
          formData={formData}
          setFormData={setFormData}
          selectedStrategy={selectedStrategy}
          handleParamChange={handleParamChange}
          renderParameterInput={renderParameterInput}
        />
      ) : null}
    </div>
  )
}

/**
 * Renders grouped strategy parameters with AI/manual
 * sizing toggle and budget allocation sections.
 */
function StrategyParameterGroups({
  formData,
  setFormData,
  selectedStrategy,
  handleParamChange,
  renderParameterInput,
}: {
  formData: BotFormData
  setFormData: (data: BotFormData) => void
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedStrategy: any
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handleParamChange: (name: string, value: any) => void
  renderParameterInput: (
    param: StrategyParameter
  ) => React.ReactNode
}) {
  const useManualSizing =
    formData.strategy_config.use_manual_sizing === true

  // Parameters rendered in custom budget section
  const customBudgetParams = [
    'use_manual_sizing',
    'max_concurrent_deals',
    'max_simultaneous_same_pair',
  ]

  // Group parameters, excluding custom budget params
  const parametersByGroup =
    selectedStrategy.parameters.reduce(
      (
        acc: Record<string, StrategyParameter[]>,
        param: StrategyParameter
      ) => {
        if (
          !isParameterVisible(
            param,
            formData.strategy_config
          )
        )
          return acc
        if (customBudgetParams.includes(param.name))
          return acc
        const group = param.group || 'Other'
        if (!acc[group]) acc[group] = []
        acc[group].push(param)
        return acc
      },
      {} as Record<string, StrategyParameter[]>
    )

  const maxConcurrentDealsParam =
    selectedStrategy.parameters.find(
      (p: StrategyParameter) =>
        p.name === 'max_concurrent_deals'
    )
  const maxSimSamePairParam =
    selectedStrategy.parameters.find(
      (p: StrategyParameter) =>
        p.name === 'max_simultaneous_same_pair'
    )

  // Group display order
  const alwaysShowGroups = [
    'Control Mode',
    'AI Configuration',
    'Analysis Timing',
    'Web Search (Optional)',
  ]
  const aiBudgetGroups = [
    'Budget & Position Sizing',
    'DCA (Safety Orders)',
  ]
  const manualSizingGroups = ['Manual Order Sizing']
  const alwaysShowAfterGroups = [
    'Profit & Exit',
    'Market Filters',
    'Other',
  ]
  const nonAIStrategyGroups = [
    'Pattern Detection',
    'Risk Management',
    'Budget',
  ]

  const isNonAIStrategy =
    formData.strategy_type === 'bull_flag' ||
    !selectedStrategy.parameters.some(
      (p: StrategyParameter) =>
        p.group === 'AI Configuration'
    )

  // Helper to render a parameter group
  const renderGroup = (groupName: string) => {
    const groupParams = parametersByGroup[groupName]
    if (!groupParams || groupParams.length === 0)
      return null

    return (
      <div
        key={groupName}
        className="bg-slate-750 rounded-lg p-4 border border-slate-700"
      >
        <h4 className="text-sm font-semibold text-slate-300 mb-4 border-b border-slate-600 pb-2">
          {groupName}
        </h4>
        <div className="space-y-4">
          {groupParams.map((param: StrategyParameter) => (
            <div key={param.name}>
              <label className="block text-sm font-medium mb-2">
                {param.display_name || param.description}
                {param.min_value !== undefined &&
                  param.max_value !== undefined && (
                    <span className="text-slate-400 text-xs ml-2">
                      ({param.min_value} -{' '}
                      {param.max_value})
                    </span>
                  )}
              </label>
              {param.description && param.display_name && (
                <p className="text-xs text-slate-400 mb-2">
                  {param.description}
                </p>
              )}
              {renderParameterInput(param)}

              {/* Preset threshold values for risk_tolerance */}
              {param.name === 'risk_tolerance' &&
                formData.strategy_config.risk_tolerance &&
                formData.strategy_config.risk_tolerance !==
                  'manual' && (
                  <RiskTolerancePresets
                    riskTolerance={
                      formData.strategy_config
                        .risk_tolerance
                    }
                  />
                )}
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Non-AI strategies (e.g., bull_flag)
  if (isNonAIStrategy) {
    return (
      <div className="space-y-6">
        {nonAIStrategyGroups.map(renderGroup)}
        {renderGroup('Other')}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {alwaysShowGroups.map(renderGroup)}

      {/* Manual vs AI Sizing Toggle */}
      <div className="bg-gradient-to-r from-purple-900/30 to-blue-900/30 rounded-lg p-4 border border-purple-700/50">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-white mb-1">
              Order Sizing Mode
            </h4>
            <p className="text-xs text-slate-400">
              {useManualSizing
                ? 'Manual: Fixed percentages based on total portfolio value'
                : 'AI-Directed: AI determines allocation within budget limits'}
            </p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer ml-4">
            <input
              type="checkbox"
              checked={useManualSizing}
              onChange={(e) =>
                handleParamChange(
                  'use_manual_sizing',
                  e.target.checked
                )
              }
              className="sr-only peer"
            />
            <div className="w-14 h-7 bg-slate-600 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-purple-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all peer-checked:bg-purple-600"></div>
            <span className="ml-3 text-sm font-medium text-slate-300">
              {useManualSizing ? 'Manual' : 'AI'}
            </span>
          </label>
        </div>
      </div>

      {/* Bot Budget Allocation */}
      <div className="bg-slate-750 rounded-lg p-4 border border-slate-700">
        <h4 className="text-sm font-semibold text-slate-300 mb-4 border-b border-slate-600 pb-2">
          {useManualSizing
            ? 'Position Limits'
            : 'Bot Budget Allocation'}
        </h4>
        <div className="space-y-4">
          {/* Max Concurrent Positions */}
          {maxConcurrentDealsParam && (
            <div>
              <label className="block text-sm font-medium mb-2">
                {maxConcurrentDealsParam.display_name ||
                  'Max Concurrent Positions'}
                <span className="text-slate-400 text-xs ml-2">
                  ({maxConcurrentDealsParam.min_value} -{' '}
                  {maxConcurrentDealsParam.max_value})
                </span>
              </label>
              <p className="text-xs text-slate-400 mb-2">
                {maxConcurrentDealsParam.description}
              </p>
              {renderParameterInput(
                maxConcurrentDealsParam
              )}
            </div>
          )}

          {/* Max Simultaneous Same Pair */}
          {maxSimSamePairParam && (
            <div>
              <label className="block text-sm font-medium mb-2 flex items-center gap-1">
                {maxSimSamePairParam.display_name ||
                  'Max Simultaneous Deals (Same Pair)'}
                <span className="text-slate-400 text-xs ml-1">
                  (1 -{' '}
                  {formData.strategy_config
                    .max_concurrent_deals || 1}
                  )
                </span>
                <span
                  className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-slate-600 text-slate-300 text-xs cursor-help"
                  title="Controls how many positions can be open on the SAME trading pair simultaneously. A new deal for the same pair only opens after ALL existing deals on that pair have exhausted their safety orders."
                >
                  i
                </span>
              </label>
              <p className="text-xs text-slate-400 mb-2">
                {maxSimSamePairParam.description}
              </p>
              {renderParameterInput(maxSimSamePairParam)}
            </div>
          )}

          {/* Budget Percentage - AI mode only */}
          {!useManualSizing && (
            <div>
              <label className="block text-sm font-medium mb-2">
                Budget Percentage{' '}
                <span className="text-slate-400 text-xs ml-2">
                  (% of aggregate portfolio)
                </span>
              </label>
              <p className="text-xs text-slate-400 mb-2">
                AI determines order sizes within this
                budget allocation.
              </p>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="100"
                  value={
                    formData.budget_percentage ===
                      undefined ||
                    formData.budget_percentage === null
                      ? ''
                      : formData.budget_percentage
                  }
                  onChange={(e) => {
                    const val = e.target.value
                    setFormData({
                      ...formData,
                      budget_percentage:
                        val === ''
                          ? undefined
                          : parseFloat(val),
                    })
                  }}
                  onBlur={(e) => {
                    if (
                      e.target.value === '' ||
                      isNaN(parseFloat(e.target.value))
                    ) {
                      setFormData({
                        ...formData,
                        budget_percentage: 0,
                      })
                    }
                  }}
                  className="flex-1 rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
                  placeholder="0.0"
                />
                <span className="text-slate-400 font-medium">
                  %
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Recommended: 33% for 3 bots, 50% for 2
                bots, 100% for 1 bot
              </p>
            </div>
          )}

          {/* Budget Splitting - AI mode, multi-pair */}
          {!useManualSizing &&
            formData.product_ids.length > 1 && (
              <div className="bg-blue-900/20 border border-blue-700/50 rounded-lg p-3">
                <label className="flex items-start space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={
                      formData.split_budget_across_pairs
                    }
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        split_budget_across_pairs:
                          e.target.checked,
                      })
                    }
                    className="mt-1 rounded border-slate-500"
                  />
                  <div className="flex-1">
                    <div className="font-medium text-white text-sm mb-1">
                      Split Budget Across Pairs
                    </div>
                    <div className="text-xs text-slate-300">
                      {formData.split_budget_across_pairs ? (
                        <>
                          <span className="text-green-400">
                            Enabled:
                          </span>{' '}
                          Budget divided by{' '}
                          {formData.strategy_config
                            ?.max_concurrent_deals || 1}{' '}
                          max concurrent deals.
                        </>
                      ) : (
                        <>
                          <span className="text-yellow-400">
                            Disabled:
                          </span>{' '}
                          Each deal gets full budget
                          allocation.
                        </>
                      )}
                    </div>
                  </div>
                </label>
              </div>
            )}
        </div>
      </div>

      {/* Conditional budget groups */}
      {useManualSizing
        ? manualSizingGroups.map(renderGroup)
        : aiBudgetGroups.map(renderGroup)}

      {/* Always-show groups after budget */}
      {alwaysShowAfterGroups.map(renderGroup)}
    </div>
  )
}

/**
 * Renders preset confidence threshold values
 * for the selected risk tolerance level.
 */
function RiskTolerancePresets({
  riskTolerance,
}: {
  riskTolerance: string
}) {
  const presets: Record<
    string,
    { open: string; dca: string; sell: string }
  > = {
    aggressive: {
      open: '70%',
      dca: '65%',
      sell: '60%',
    },
    moderate: {
      open: '75%',
      dca: '70%',
      sell: '65%',
    },
    conservative: {
      open: '80%',
      dca: '75%',
      sell: '70%',
    },
  }

  const values = presets[riskTolerance]
  if (!values) return null

  return (
    <div className="mt-2 p-3 bg-blue-900/20 border border-blue-700/50 rounded text-xs">
      <p className="font-semibold text-blue-400 mb-2">
        Preset Confidence Thresholds:
      </p>
      <div className="grid grid-cols-3 gap-2 text-slate-300">
        <div>
          Open:{' '}
          <span className="text-white font-semibold">
            {values.open}
          </span>
        </div>
        <div>
          DCA:{' '}
          <span className="text-white font-semibold">
            {values.dca}
          </span>
        </div>
        <div>
          Sell:{' '}
          <span className="text-white font-semibold">
            {values.sell}
          </span>
        </div>
      </div>
    </div>
  )
}
