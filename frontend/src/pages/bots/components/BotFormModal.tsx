import type { Bot } from '../../../types'
import DexConfigSection from '../../../components/DexConfigSection'
import type {
  BotFormData,
  ValidationWarning,
  ValidationError,
  TradingPair,
} from '../../../components/bots'
import { useBotForm } from '../hooks/useBotForm'
import { StrategyConfigSection } from './StrategyConfigSection'
import {
  CoinCategorySelector,
  CategoryBadge,
} from './CoinCategorySelector'
import { BudgetSection } from './BudgetSection'

interface BotFormModalProps {
  showModal: boolean
  setShowModal: (show: boolean) => void
  editingBot: Bot | null
  formData: BotFormData
  setFormData: (data: BotFormData) => void
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  templates: any[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  strategies: any[]
  TRADING_PAIRS: TradingPair[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedStrategy: any
  validationWarnings: ValidationWarning[]
  validationErrors: ValidationError[]
  selectedAccount: {
    id: number
    name: string
    type?: string
    chain_id?: number
  } | null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  createBot: any
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  updateBot: any
  resetForm: () => void
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  aggregateData: any
  readOnly?: boolean
  readOnlyTitle?: string
}

export function BotFormModal({
  showModal,
  setShowModal,
  editingBot,
  formData,
  setFormData,
  templates,
  strategies,
  TRADING_PAIRS,
  selectedStrategy,
  validationWarnings,
  validationErrors,
  selectedAccount,
  createBot,
  updateBot,
  resetForm,
  aggregateData,
  readOnly = false,
  readOnlyTitle,
}: BotFormModalProps) {
  const {
    coinCategoryData,
    loadTemplate,
    handleStrategyChange,
    handleParamChange,
    handleSubmit,
  } = useBotForm({
    showModal,
    formData,
    setFormData,
    editingBot,
    templates,
    strategies,
    validationErrors,
    selectedAccount,
    createBot,
    updateBot,
  })

  if (!showModal) return null

  // Helper: get market from pair ID (e.g., "ETH-BTC" -> "BTC")
  const getMarket = (pairId: string) =>
    pairId.split('-')[1]
  const selectedMarket =
    formData.product_ids.length > 0
      ? getMarket(formData.product_ids[0])
      : null
  const isMarketLocked = formData.product_ids.length >= 2

  const handlePairToggle = (
    pairValue: string,
    isChecked: boolean
  ) => {
    const pairMarket = getMarket(pairValue)

    if (isChecked) {
      if (!selectedMarket) {
        setFormData({
          ...formData,
          product_ids: [pairValue],
          product_id: pairValue,
        })
      } else if (pairMarket === selectedMarket) {
        setFormData({
          ...formData,
          product_ids: [
            ...formData.product_ids,
            pairValue,
          ],
          product_id:
            formData.product_ids[0] || pairValue,
        })
      } else {
        setFormData({
          ...formData,
          product_ids: [pairValue],
          product_id: pairValue,
        })
      }
    } else {
      const newIds = formData.product_ids.filter(
        (id) => id !== pairValue
      )
      setFormData({
        ...formData,
        product_ids: newIds,
        product_id: newIds[0] || 'ETH-BTC',
      })
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-1 sm:p-4 z-[60]">
      <div
        className={`bg-slate-800 rounded-lg w-full max-h-[95vh] sm:max-h-[90vh] overflow-y-auto mx-1 sm:mx-auto ${
          formData.strategy_type === 'conditional_dca'
            ? 'max-w-[98vw] sm:max-w-6xl'
            : 'max-w-[98vw] sm:max-w-4xl'
        }`}
      >
        <div className="p-4 sm:p-6 border-b border-slate-700">
          <h3 className="text-xl font-bold">
            {readOnly
              ? readOnlyTitle || 'View Bot'
              : editingBot
                ? 'Edit Bot'
                : 'Create New Bot'}
          </h3>
        </div>

        <form
          onSubmit={
            readOnly
              ? (e) => {
                  e.preventDefault()
                  setShowModal(false)
                  resetForm()
                }
              : handleSubmit
          }
          className="p-3 sm:p-6 space-y-6"
        >
          <fieldset
            disabled={readOnly}
            className={readOnly ? 'opacity-80' : ''}
          >
            {/* Template Selector */}
            {!editingBot &&
              !readOnly &&
              templates.length > 0 && (
                <TemplateSelector
                  templates={templates}
                  loadTemplate={loadTemplate}
                />
              )}

            {/* SECTION 1: BASIC INFORMATION */}
            <BasicInfoSection
              formData={formData}
              setFormData={setFormData}
            />

            {/* SECTION 2: MARKET TYPE */}
            <MarketTypeSection
              formData={formData}
              setFormData={setFormData}
            />

            {/* SECTION: EXCHANGE CONFIGURATION */}
            <DexConfigSection
              config={{
                exchange_type: formData.exchange_type,
                chain_id: formData.chain_id,
                dex_router: formData.dex_router,
                wallet_private_key:
                  formData.wallet_private_key,
                rpc_url: formData.rpc_url,
              }}
              onChange={(dexConfig) =>
                setFormData({
                  ...formData,
                  ...dexConfig,
                })
              }
            />

            {/* SECTION 3: STRATEGY */}
            <StrategySelectionSection
              formData={formData}
              strategies={strategies}
              selectedStrategy={selectedStrategy}
              handleStrategyChange={handleStrategyChange}
            />

            {/* SECTION 4: MARKETS & TRADING PAIRS */}
            <div className="border-b border-slate-700 pb-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <span className="text-blue-400">4.</span>{' '}
                Markets & Trading Pairs
              </h3>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Pairs
                </label>

                {/* Header with count and unselect all */}
                <div className="flex items-center justify-between mb-2 px-3 py-2 bg-slate-700 border border-slate-600 rounded-t">
                  <span className="text-sm text-slate-300">
                    {formData.product_ids.length} pairs
                    {selectedMarket && (
                      <span className="text-slate-400 ml-2">
                        ({selectedMarket} market)
                      </span>
                    )}
                  </span>
                  {formData.product_ids.length > 0 && (
                    <button
                      type="button"
                      onClick={() =>
                        setFormData({
                          ...formData,
                          product_ids: [],
                          product_id: 'ETH-BTC',
                        })
                      }
                      className="text-xs text-blue-400 hover:text-blue-300"
                    >
                      Unselect all (
                      {formData.product_ids.length})
                    </button>
                  )}
                </div>

                {/* Quick filter buttons */}
                <MarketFilterButtons
                  TRADING_PAIRS={TRADING_PAIRS}
                  formData={formData}
                  setFormData={setFormData}
                  isMarketLocked={isMarketLocked}
                  selectedMarket={selectedMarket}
                />

                {/* Pair list */}
                <PairList
                  TRADING_PAIRS={TRADING_PAIRS}
                  formData={formData}
                  isMarketLocked={isMarketLocked}
                  selectedMarket={selectedMarket}
                  handlePairToggle={handlePairToggle}
                  coinCategoryData={coinCategoryData}
                />

                {/* Auto-add new pairs checkbox */}
                {formData.product_ids.length > 5 && (
                  <div className="mt-4 pt-4 border-t border-slate-600">
                    <label className="flex items-start gap-3 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={
                          formData.strategy_config
                            ?.auto_add_new_pairs || false
                        }
                        onChange={(e) => {
                          setFormData({
                            ...formData,
                            strategy_config: {
                              ...formData.strategy_config,
                              auto_add_new_pairs:
                                e.target.checked,
                            },
                          })
                        }}
                        className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0"
                      />
                      <div className="flex-1">
                        <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">
                          Auto-add new pairs
                        </span>
                        <p className="text-xs text-slate-400 mt-0.5">
                          Automatically add newly listed{' '}
                          {selectedMarket} pairs to this
                          bot daily. Delisted pairs are
                          always removed automatically.
                        </p>
                      </div>
                    </label>
                  </div>
                )}

                {/* Skip stable/pegged pairs checkbox */}
                <div className="mt-4 pt-4 border-t border-slate-600">
                  <label className="flex items-start gap-3 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={
                        formData.strategy_config
                          ?.skip_stable_pairs ?? true
                      }
                      onChange={(e) => {
                        setFormData({
                          ...formData,
                          strategy_config: {
                            ...formData.strategy_config,
                            skip_stable_pairs:
                              e.target.checked,
                          },
                        })
                      }}
                      className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0"
                    />
                    <div className="flex-1">
                      <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">
                        Skip stable/pegged pairs
                      </span>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Exclude stablecoin pairs (USDC-USD,
                        DAI-USD) and wrapped token pairs
                        (WBTC-BTC, CBETH-ETH) that rarely
                        move in price.
                      </p>
                    </div>
                  </label>
                </div>

                {/* Coin Category Selector */}
                <CoinCategorySelector
                  formData={formData}
                  setFormData={setFormData}
                  coinCategoryData={coinCategoryData}
                />
              </div>
            </div>

            {/* SECTION 5: MONITORING & TIMING */}
            <MonitoringSection
              formData={formData}
              setFormData={setFormData}
            />

            {/* SECTION 6: BUDGET & RISK (non-AI only) */}
            {formData.strategy_type !==
              'ai_autonomous' && (
              <BudgetSection
                formData={formData}
                setFormData={setFormData}
              />
            )}

            {/* SECTION 7: STRATEGY CONFIGURATION */}
            <StrategyConfigSection
              formData={formData}
              setFormData={setFormData}
              selectedStrategy={selectedStrategy}
              handleParamChange={handleParamChange}
              aggregateData={aggregateData}
            />
          </fieldset>

          {/* Validation Errors */}
          {!readOnly && validationErrors.length > 0 && (
            <ValidationErrorsPanel
              errors={validationErrors}
            />
          )}

          {/* Validation Warnings */}
          {!readOnly &&
            validationWarnings.length > 0 && (
              <ValidationWarningsPanel
                warnings={validationWarnings}
              />
            )}

          {/* Actions */}
          <FormActions
            readOnly={readOnly}
            editingBot={editingBot}
            createBot={createBot}
            updateBot={updateBot}
            validationErrors={validationErrors}
            setShowModal={setShowModal}
            resetForm={resetForm}
          />
        </form>
      </div>
    </div>
  )
}

// ========================================
// Small, focused sub-sections below
// ========================================

function TemplateSelector({
  templates,
  loadTemplate,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  templates: any[]
  loadTemplate: (id: number) => void
}) {
  return (
    <div className="bg-gradient-to-r from-blue-900/20 to-purple-900/20 border border-blue-700/50 rounded-lg p-4">
      <label className="block text-sm font-medium mb-2">
        Start from Template (Optional)
      </label>
      <select
        value=""
        onChange={(e) => {
          if (e.target.value) {
            loadTemplate(parseInt(e.target.value))
          }
        }}
        className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
      >
        <option value="">
          Select a template to pre-fill settings...
        </option>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        {templates.map((template: any) => (
          <option key={template.id} value={template.id}>
            {template.is_default ? '* ' : ''}
            {template.name} - {template.description}
          </option>
        ))}
      </select>
      <p className="text-xs text-slate-400 mt-2">
        Templates provide quick-start configurations. You
        can customize all settings after selection.
      </p>
    </div>
  )
}

function BasicInfoSection({
  formData,
  setFormData,
}: {
  formData: BotFormData
  setFormData: (data: BotFormData) => void
}) {
  return (
    <div className="border-b border-slate-700 pb-6">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <span className="text-blue-400">1.</span> Basic
        Information
      </h3>

      <div className="mb-4">
        <label className="block text-sm font-medium mb-2">
          Bot Name *
        </label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) =>
            setFormData({
              ...formData,
              name: e.target.value,
            })
          }
          className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
          placeholder="My Trading Bot"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">
          Description
        </label>
        <textarea
          value={formData.description}
          onChange={(e) =>
            setFormData({
              ...formData,
              description: e.target.value,
            })
          }
          className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
          placeholder="Optional description"
          rows={2}
        />
      </div>
    </div>
  )
}

function MarketTypeSection({
  formData,
  setFormData,
}: {
  formData: BotFormData
  setFormData: (data: BotFormData) => void
}) {
  return (
    <div className="border-b border-slate-700 pb-6">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <span className="text-blue-400">2.</span> Market
        Type
      </h3>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={() =>
            setFormData({
              ...formData,
              market_type: 'spot',
            })
          }
          className={`flex-1 py-2 px-4 rounded border text-sm font-medium transition-colors ${
            formData.market_type === 'spot'
              ? 'border-blue-500 bg-blue-500/20 text-blue-400'
              : 'border-slate-600 bg-slate-700 text-slate-400 hover:border-slate-500'
          }`}
        >
          Spot Trading
        </button>
        <button
          type="button"
          onClick={() =>
            setFormData({
              ...formData,
              market_type: 'perps',
            })
          }
          className={`flex-1 py-2 px-4 rounded border text-sm font-medium transition-colors ${
            formData.market_type === 'perps'
              ? 'border-purple-500 bg-purple-500/20 text-purple-400'
              : 'border-slate-600 bg-slate-700 text-slate-400 hover:border-slate-500'
          }`}
        >
          Perpetual Futures
        </button>
      </div>

      {formData.market_type === 'perps' && (
        <PerpsConfig
          formData={formData}
          setFormData={setFormData}
        />
      )}
    </div>
  )
}

function PerpsConfig({
  formData,
  setFormData,
}: {
  formData: BotFormData
  setFormData: (data: BotFormData) => void
}) {
  return (
    <div className="mt-4 space-y-3 p-4 bg-purple-500/5 border border-purple-500/20 rounded">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">
            Leverage (1-10x)
          </label>
          <input
            type="number"
            min={1}
            max={10}
            value={
              formData.strategy_config.leverage || 1
            }
            onChange={(e) =>
              setFormData({
                ...formData,
                strategy_config: {
                  ...formData.strategy_config,
                  leverage:
                    parseInt(e.target.value) || 1,
                },
              })
            }
            className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">
            Margin Type
          </label>
          <select
            value={
              formData.strategy_config.margin_type ||
              'CROSS'
            }
            onChange={(e) =>
              setFormData({
                ...formData,
                strategy_config: {
                  ...formData.strategy_config,
                  margin_type: e.target.value,
                },
              })
            }
            className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white text-sm"
          >
            <option value="CROSS">Cross</option>
            <option value="ISOLATED">Isolated</option>
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">
            Take Profit %
          </label>
          <input
            type="number"
            step="0.1"
            min={0}
            value={
              formData.strategy_config.default_tp_pct ||
              ''
            }
            onChange={(e) =>
              setFormData({
                ...formData,
                strategy_config: {
                  ...formData.strategy_config,
                  default_tp_pct:
                    parseFloat(e.target.value) ||
                    undefined,
                },
              })
            }
            className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white text-sm"
            placeholder="e.g. 5.0"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">
            Stop Loss %
          </label>
          <input
            type="number"
            step="0.1"
            min={0}
            value={
              formData.strategy_config.default_sl_pct ||
              ''
            }
            onChange={(e) =>
              setFormData({
                ...formData,
                strategy_config: {
                  ...formData.strategy_config,
                  default_sl_pct:
                    parseFloat(e.target.value) ||
                    undefined,
                },
              })
            }
            className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white text-sm"
            placeholder="e.g. 3.0"
          />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-400 mb-1">
          Direction
        </label>
        <select
          value={
            formData.strategy_config.direction ||
            'long_only'
          }
          onChange={(e) =>
            setFormData({
              ...formData,
              strategy_config: {
                ...formData.strategy_config,
                direction: e.target.value,
              },
            })
          }
          className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white text-sm"
        >
          <option value="long_only">Long Only</option>
          <option value="short_only">
            Short Only
          </option>
          <option value="both">
            Both (Long + Short)
          </option>
        </select>
      </div>
    </div>
  )
}

function StrategySelectionSection({
  formData,
  strategies,
  selectedStrategy,
  handleStrategyChange,
}: {
  formData: BotFormData
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  strategies: any[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedStrategy: any
  handleStrategyChange: (strategyType: string) => void
}) {
  return (
    <div className="border-b border-slate-700 pb-6">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <span className="text-blue-400">3.</span>{' '}
        Strategy
      </h3>
      <div>
        <label className="block text-sm font-medium mb-2">
          Trading Strategy *
        </label>
        <select
          value={formData.strategy_type}
          onChange={(e) =>
            handleStrategyChange(e.target.value)
          }
          className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
          required
        >
          <option value="">Select a strategy...</option>
          {strategies.map(
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (strategy: any) => (
              <option
                key={strategy.id}
                value={strategy.id}
              >
                {strategy.name}
              </option>
            )
          )}
        </select>
        {selectedStrategy && (
          <p className="text-sm text-slate-400 mt-2">
            {selectedStrategy.description}
          </p>
        )}
      </div>
    </div>
  )
}

function MarketFilterButtons({
  TRADING_PAIRS,
  formData,
  setFormData,
  isMarketLocked,
  selectedMarket,
}: {
  TRADING_PAIRS: TradingPair[]
  formData: BotFormData
  setFormData: (data: BotFormData) => void
  isMarketLocked: boolean
  selectedMarket: string | null
}) {
  return (
    <div className="flex flex-wrap gap-2 mb-3 px-1">
      {['BTC', 'USD', 'USDC', 'USDT'].map((market) => {
        const marketPairs = TRADING_PAIRS.filter(
          (p) => p.group === market
        ).map((p) => p.value)
        if (marketPairs.length === 0) return null
        const isDisabled =
          isMarketLocked && selectedMarket !== market

        return (
          <button
            key={market}
            type="button"
            onClick={() => {
              setFormData({
                ...formData,
                product_ids: marketPairs,
                product_id:
                  marketPairs[0] || 'ETH-BTC',
              })
            }}
            disabled={isDisabled}
            className={`px-3 py-1.5 text-xs font-medium rounded border ${
              isDisabled
                ? 'bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed opacity-50'
                : 'bg-slate-700 hover:bg-slate-600 text-slate-300 border-slate-600'
            }`}
          >
            {market} All
          </button>
        )
      })}
    </div>
  )
}

function PairList({
  TRADING_PAIRS,
  formData,
  isMarketLocked,
  selectedMarket,
  handlePairToggle,
  coinCategoryData,
}: {
  TRADING_PAIRS: TradingPair[]
  formData: BotFormData
  isMarketLocked: boolean
  selectedMarket: string | null
  handlePairToggle: (
    pairValue: string,
    isChecked: boolean
  ) => void
  coinCategoryData: import('../hooks/useBotForm').CoinCategoryData
}) {
  return (
    <div className="border border-slate-600 border-t-0 rounded-b bg-slate-700 p-3 max-h-72 overflow-y-auto">
      {['BTC', 'USD', 'USDC', 'USDT'].map((group) => {
        const groupPairs = TRADING_PAIRS.filter(
          (p) => p.group === group
        )
        if (groupPairs.length === 0) return null
        const isGroupHidden =
          isMarketLocked && selectedMarket !== group
        if (isGroupHidden) return null

        return (
          <div key={group} className="mb-3 last:mb-0">
            <div className="text-xs font-medium text-slate-400 mb-1.5">
              {group} Pairs
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
              {groupPairs.map((pair) => {
                const isChecked =
                  formData.product_ids.includes(
                    pair.value
                  )
                return (
                  <label
                    key={pair.value}
                    className="flex items-center space-x-2 px-2 py-1 rounded text-sm cursor-pointer hover:bg-slate-600"
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={(e) =>
                        handlePairToggle(
                          pair.value,
                          e.target.checked
                        )
                      }
                      className="rounded border-slate-500"
                    />
                    <CategoryBadge
                      pairId={pair.value}
                      coinCategoryData={
                        coinCategoryData
                      }
                    />
                    <span className="text-xs">
                      {pair.label}
                    </span>
                  </label>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function MonitoringSection({
  formData,
  setFormData,
}: {
  formData: BotFormData
  setFormData: (data: BotFormData) => void
}) {
  return (
    <div className="border-b border-slate-700 pb-6">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <span className="text-blue-400">5.</span>{' '}
        Monitoring & Timing
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            AI Analysis Interval (seconds)
          </label>
          <input
            type="number"
            step="60"
            min="60"
            max="3600"
            value={
              formData.check_interval_seconds ===
                undefined ||
              formData.check_interval_seconds === null
                ? ''
                : formData.check_interval_seconds
            }
            onChange={(e) => {
              const val = e.target.value
              setFormData({
                ...formData,
                check_interval_seconds:
                  val === ''
                    ? undefined
                    : parseInt(val),
              })
            }}
            onBlur={(e) => {
              if (
                e.target.value === '' ||
                isNaN(parseInt(e.target.value))
              ) {
                setFormData({
                  ...formData,
                  check_interval_seconds: 300,
                })
              }
            }}
            className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
            placeholder="300"
          />
          <p className="text-xs text-slate-400 mt-1.5">
            How often to run AI analysis (technical
            checks use candle interval)
            <br />
            <span className="text-slate-500">
              Default: 300s (5 min) | Gemini: 1800s (30
              min)
            </span>
          </p>
        </div>
      </div>
    </div>
  )
}

function ValidationErrorsPanel({
  errors,
}: {
  errors: ValidationError[]
}) {
  return (
    <div className="bg-red-900/40 border-2 border-red-600 rounded-lg p-4 mb-4">
      <div className="flex items-start gap-3">
        <div className="text-red-500 text-2xl flex-shrink-0">
          {/* Block icon */}
          &#128683;
        </div>
        <div className="flex-1">
          <div className="font-bold text-red-300 mb-2 text-lg">
            Cannot Save - Order Size Below Exchange
            Minimum
          </div>
          <div className="text-sm text-red-200/90 mb-3">
            Your configured order percentages result in
            order sizes below the exchange minimum.
            Increase the percentages or add more funds to
            your account.
          </div>
          <div className="space-y-2">
            {errors.map((error, idx) => (
              <div
                key={idx}
                className="bg-red-900/30 rounded p-3 border border-red-600/50"
              >
                <div className="font-medium text-red-300 mb-1">
                  {error.field === 'base_order_value'
                    ? 'Base Order Value'
                    : 'DCA Order Value'}
                </div>
                <div className="text-xs text-red-200/80">
                  {error.message}
                </div>
              </div>
            ))}
          </div>
          <div className="text-sm text-red-200 mt-3 font-medium">
            Save is disabled until this is resolved.
          </div>
        </div>
      </div>
    </div>
  )
}

function ValidationWarningsPanel({
  warnings,
}: {
  warnings: ValidationWarning[]
}) {
  return (
    <div className="bg-yellow-900/30 border border-yellow-700 rounded-lg p-4 mb-4">
      <div className="flex items-start gap-3">
        <div className="text-yellow-500 text-xl flex-shrink-0">
          {/* Warning icon */}
          &#9888;&#65039;
        </div>
        <div className="flex-1">
          <div className="font-semibold text-yellow-300 mb-2">
            Minimum Order Size Warning
          </div>
          <div className="text-sm text-yellow-200/90 mb-3">
            The following products may fail to execute
            orders because your configured budget
            percentage is below the exchange minimum
            order size:
          </div>
          <div className="space-y-2">
            {warnings.map((warning, idx) => (
              <div
                key={idx}
                className="bg-yellow-900/20 rounded p-3 border border-yellow-700/50"
              >
                <div className="font-medium text-yellow-300 mb-1">
                  {warning.product_id}
                </div>
                <div className="text-xs text-yellow-200/80 space-y-1">
                  <div>
                    Current budget:{' '}
                    <span className="font-mono text-red-400">
                      {warning.current_pct.toFixed(2)}%
                    </span>
                  </div>
                  <div>
                    Suggested minimum:{' '}
                    <span className="font-mono text-green-400">
                      {warning.suggested_minimum_pct.toFixed(
                        2
                      )}
                      %
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="text-xs text-yellow-200/70 mt-3">
            You can still create this bot, but orders may
            fail until you increase the budget percentage
            or add more funds.
          </div>
        </div>
      </div>
    </div>
  )
}

function FormActions({
  readOnly,
  editingBot,
  createBot,
  updateBot,
  validationErrors,
  setShowModal,
  resetForm,
}: {
  readOnly: boolean
  editingBot: Bot | null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  createBot: any
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  updateBot: any
  validationErrors: ValidationError[]
  setShowModal: (show: boolean) => void
  resetForm: () => void
}) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-3 pt-4 border-t border-slate-700">
      {readOnly ? (
        <button
          type="submit"
          className="px-4 py-2 rounded bg-slate-600 hover:bg-slate-500 transition-colors"
        >
          Close
        </button>
      ) : (
        <>
          <button
            type="button"
            onClick={() => {
              setShowModal(false)
              resetForm()
            }}
            className="px-4 py-2 rounded border border-slate-600 hover:bg-slate-700 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            className={`px-4 py-2 rounded transition-colors ${
              validationErrors.length > 0
                ? 'bg-slate-600 cursor-not-allowed opacity-50'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
            disabled={
              createBot.isPending ||
              updateBot.isPending ||
              validationErrors.length > 0
            }
          >
            {createBot.isPending || updateBot.isPending
              ? 'Saving...'
              : validationErrors.length > 0
                ? 'Fix Errors First'
                : editingBot
                  ? 'Update Bot'
                  : 'Create Bot'}
          </button>
        </>
      )}
    </div>
  )
}
