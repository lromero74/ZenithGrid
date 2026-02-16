import { useState, useEffect } from 'react'
import { Bot, StrategyParameter } from '../../../types'
import ThreeCommasStyleForm from '../../../components/ThreeCommasStyleForm'
import PhaseConditionSelector from '../../../components/PhaseConditionSelector'
import DexConfigSection from '../../../components/DexConfigSection'
import { isParameterVisible } from '../../../components/bots'
import { blacklistApi, BlacklistEntry } from '../../../services/api'
import type {
  BotFormData,
  ValidationWarning,
  ValidationError,
  TradingPair,
} from '../../../components/bots'

interface BotFormModalProps {
  showModal: boolean
  setShowModal: (show: boolean) => void
  editingBot: Bot | null
  formData: BotFormData
  setFormData: (data: BotFormData) => void
  templates: any[]
  strategies: any[]
  TRADING_PAIRS: TradingPair[]
  selectedStrategy: any
  validationWarnings: ValidationWarning[]
  validationErrors: ValidationError[]
  selectedAccount: { id: number; name: string; type?: string; chain_id?: number } | null
  createBot: any
  updateBot: any
  resetForm: () => void
  aggregateData: any
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
}: BotFormModalProps) {
  // Fetch blacklist/category data for badges and counts
  const [coinCategories, setCoinCategories] = useState<Record<string, string>>({})
  const [categoryCounts, setCategoryCounts] = useState<Record<string, number>>({
    APPROVED: 0,
    BORDERLINE: 0,
    QUESTIONABLE: 0,
    MEME: 0,
    BLACKLISTED: 0,
  })

  useEffect(() => {
    const fetchCategories = async () => {
      try {
        const blacklist = await blacklistApi.getAll()
        const categoryMap: Record<string, string> = {}
        const counts: Record<string, number> = {
          APPROVED: 0,
          BORDERLINE: 0,
          QUESTIONABLE: 0,
          MEME: 0,
          BLACKLISTED: 0,
        }

        blacklist.forEach((entry: BlacklistEntry) => {
          const reason = entry.reason || ''
          let category = 'BLACKLISTED'

          if (reason.startsWith('[APPROVED]')) category = 'APPROVED'
          else if (reason.startsWith('[BORDERLINE]')) category = 'BORDERLINE'
          else if (reason.startsWith('[QUESTIONABLE]')) category = 'QUESTIONABLE'
          else if (reason.startsWith('[MEME]')) category = 'MEME'

          categoryMap[entry.symbol] = category
          counts[category]++
        })

        setCoinCategories(categoryMap)
        setCategoryCounts(counts)
      } catch (err) {
        console.error('Failed to load coin categories:', err)
      }
    }

    if (showModal) {
      fetchCategories()
    }
  }, [showModal])

  // Helper: Get category badge for a coin
  const getCategoryBadge = (pairId: string) => {
    const baseCurrency = pairId.split('-')[0]
    const category = coinCategories[baseCurrency] || 'APPROVED'

    const badgeStyles: Record<string, { bg: string; text: string; label: string }> = {
      APPROVED: { bg: 'bg-green-600/20', text: 'text-green-400', label: 'A' },
      BORDERLINE: { bg: 'bg-yellow-600/20', text: 'text-yellow-400', label: 'B' },
      QUESTIONABLE: { bg: 'bg-orange-600/20', text: 'text-orange-400', label: 'Q' },
      MEME: { bg: 'bg-purple-600/20', text: 'text-purple-400', label: 'M' },
      BLACKLISTED: { bg: 'bg-red-600/20', text: 'text-red-400', label: 'X' },
    }

    const style = badgeStyles[category]
    return (
      <span
        className={`inline-flex items-center justify-center w-4 h-4 text-[10px] font-bold rounded ${style.bg} ${style.text}`}
        title={category}
      >
        {style.label}
      </span>
    )
  }

  const loadTemplate = (templateId: number) => {
    const template = templates.find((t: any) => t.id === templateId)
    if (!template) return

    setFormData({
      name: `${template.name} (Copy)`,  // Prefix to avoid name conflicts
      description: template.description || '',
      market_type: template.market_type || 'spot',
      strategy_type: template.strategy_type,
      product_id: template.product_ids?.[0] || 'ETH-BTC',
      product_ids: template.product_ids || [],
      split_budget_across_pairs: template.split_budget_across_pairs || false,
      reserved_btc_balance: template.reserved_btc_balance || 0,
      reserved_usd_balance: template.reserved_usd_balance || 0,
      budget_percentage: template.budget_percentage || 0,
      check_interval_seconds: template.check_interval_seconds || 300,
      strategy_config: template.strategy_config,
      exchange_type: template.exchange_type || 'cex',
    })
  }

  const handleStrategyChange = (strategyType: string) => {
    const strategy = strategies.find((s) => s.id === strategyType)
    if (!strategy) return

    // Initialize config with default values
    const config: Record<string, any> = {}
    strategy.parameters.forEach((param: StrategyParameter) => {
      config[param.name] = param.default
    })

    setFormData({
      ...formData,
      strategy_type: strategyType,
      strategy_config: config,
    })
  }

  const handleParamChange = (paramName: string, value: any) => {
    const updates: Record<string, any> = { [paramName]: value }

    // When max_concurrent_deals changes, cap max_simultaneous_same_pair
    if (paramName === 'max_concurrent_deals') {
      const maxSim = formData.strategy_config.max_simultaneous_same_pair || 1
      if (maxSim > value) {
        updates.max_simultaneous_same_pair = value
      }
    }
    // When max_simultaneous_same_pair changes, cap at max_concurrent_deals
    if (paramName === 'max_simultaneous_same_pair') {
      const maxDeals = formData.strategy_config.max_concurrent_deals || 1
      if (value > maxDeals) {
        updates.max_simultaneous_same_pair = maxDeals
      }
    }

    setFormData({
      ...formData,
      strategy_config: {
        ...formData.strategy_config,
        ...updates,
      },
    })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    // Block save if there are validation errors
    if (validationErrors.length > 0) {
      alert('Cannot save: Order values are below exchange minimum. Please increase the percentage values or fund your account with more capital.')
      return
    }

    // Validate account is selected
    if (!selectedAccount?.id) {
      alert('Please select an account before creating a bot')
      return
    }

    // Validate at least one pair is selected
    if (formData.product_ids.length === 0) {
      alert('Please select at least one trading pair')
      return
    }

    // Ensure numeric fields have valid defaults if undefined
    const check_interval_seconds = formData.check_interval_seconds ?? 300
    const reserved_btc_balance = formData.reserved_btc_balance ?? 0
    const reserved_usd_balance = formData.reserved_usd_balance ?? 0
    const budget_percentage = formData.budget_percentage ?? 0

    const botData: any = {
      name: formData.name,
      description: formData.description || undefined,
      account_id: selectedAccount?.id,  // Link bot to selected account
      market_type: formData.market_type || 'spot',
      strategy_type: formData.strategy_type,
      product_id: formData.product_ids[0],  // Legacy - use first pair
      product_ids: formData.product_ids,  // Multi-pair support
      split_budget_across_pairs: formData.split_budget_across_pairs,  // Budget splitting option
      reserved_btc_balance,
      reserved_usd_balance,
      budget_percentage,
      check_interval_seconds,  // Monitoring interval
      strategy_config: formData.strategy_config,
      // DEX configuration fields
      exchange_type: formData.exchange_type,
      chain_id: formData.chain_id,
      dex_router: formData.dex_router,
      wallet_private_key: formData.wallet_private_key,
      rpc_url: formData.rpc_url,
    }

    if (editingBot) {
      updateBot.mutate({ id: editingBot.id, data: botData })
    } else {
      createBot.mutate(botData)
    }
  }

  const renderParameterInput = (param: StrategyParameter) => {
    // Don't immediately apply default - let user clear the field while editing
    // Default will be applied on blur or form submission
    const value = formData.strategy_config[param.name]

    // Special handling for position_control_mode - render as toggle switch
    if (param.name === 'position_control_mode' && param.options && param.options.length === 2) {
      const isAiDirected = value === 'ai_directed'
      return (
        <div className="flex items-center justify-between bg-slate-700 rounded-lg p-4 border border-slate-600">
          <div className="flex-1">
            <div className="text-sm font-medium text-white mb-1">
              {isAiDirected ? '🤖 AI-Directed Mode' : '⚙️ Strict Parameters Mode'}
            </div>
            <div className="text-xs text-slate-400">
              {isAiDirected
                ? 'AI dynamically controls position sizes within budget limits'
                : 'Use fixed parameters for all position sizing'
              }
            </div>
          </div>
          <label className="relative inline-flex items-center cursor-pointer ml-4">
            <input
              type="checkbox"
              checked={isAiDirected}
              onChange={(e) => handleParamChange(param.name, e.target.checked ? 'ai_directed' : 'strict')}
              className="sr-only peer"
            />
            <div className="w-14 h-7 bg-slate-600 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-purple-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all peer-checked:bg-purple-600"></div>
          </label>
        </div>
      )
    }

    // Handle conditions type (condition builder for indicators)
    if ((param.type as string) === 'conditions') {
      return (
        <PhaseConditionSelector
          title={param.display_name || ''}
          description={param.description || ''}
          conditions={formData.strategy_config[param.name] || []}
          onChange={(conditions) => handleParamChange(param.name, conditions)}
          allowMultiple={true}
        />
      )
    }

    if (param.type === 'bool') {
      return (
        <label className="flex items-center space-x-2">
          <input
            type="checkbox"
            checked={!!value}
            onChange={(e) => handleParamChange(param.name, e.target.checked)}
            className="rounded border-slate-600 bg-slate-700 text-blue-500"
          />
          <span className="text-sm text-slate-300">{param.description}</span>
        </label>
      )
    }

    if (param.options && param.options.length > 0) {
      return (
        <select
          value={String(value)}
          onChange={(e) => handleParamChange(param.name, e.target.value)}
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

    // Handle text type (multiline textarea)
    if (param.type === 'text') {
      return (
        <div>
          <textarea
            value={value || ''}
            onChange={(e) => handleParamChange(param.name, e.target.value)}
            rows={4}
            placeholder={param.name === 'custom_instructions' ? 'Add any specific instructions for the AI (e.g., "Focus on BTC pairs", "Avoid trading during low volume hours")' : param.description}
            className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white resize-y"
          />
          {param.name === 'custom_instructions' && (
            <div className="mt-2 text-xs text-slate-400 bg-slate-800/50 rounded p-3 border border-slate-700">
              <p className="font-medium text-slate-300 mb-1">📋 Default AI Instructions:</p>
              <p className="text-slate-400">The AI will analyze market data, sentiment, and news to make intelligent trading decisions. It will be {formData.strategy_config?.risk_tolerance || 'moderate'} in its recommendations and will never sell at a loss. Your custom instructions will be added to guide its specific trading behavior.</p>
            </div>
          )}
        </div>
      )
    }

    const inputType = param.type === 'int' || param.type === 'float' ? 'number' : 'text'
    const step = param.type === 'float' ? 'any' : param.type === 'int' ? '1' : undefined

    // Handle NaN and undefined values for display
    const displayValue = (value === undefined || value === null || (typeof value === 'number' && isNaN(value))) ? '' : value

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
            val = rawVal === '' ? undefined : parseFloat(rawVal)
            if (typeof val === 'number' && isNaN(val)) val = undefined
          } else if (param.type === 'int') {
            val = rawVal === '' ? undefined : parseInt(rawVal)
            if (typeof val === 'number' && isNaN(val)) val = undefined
          } else {
            val = rawVal
          }
          handleParamChange(param.name, val)
        }}
        onBlur={() => {
          // Apply default value if field is empty/invalid when focus is lost
          const currentValue = formData.strategy_config[param.name]
          if (currentValue === undefined || currentValue === null || currentValue === '') {
            handleParamChange(param.name, param.default)
          }
        }}
        className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
      />
    )
  }

  if (!showModal) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className={`bg-slate-800 rounded-lg w-full max-h-[90vh] overflow-y-auto ${
        formData.strategy_type === 'conditional_dca' ? 'max-w-6xl' : 'max-w-4xl'
      }`}>
        <div className="p-6 border-b border-slate-700">
          <h3 className="text-xl font-bold">
            {editingBot ? 'Edit Bot' : 'Create New Bot'}
          </h3>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Template Selector - Only show when creating new bot */}
          {!editingBot && templates.length > 0 && (
            <div className="bg-gradient-to-r from-blue-900/20 to-purple-900/20 border border-blue-700/50 rounded-lg p-4">
              <label className="block text-sm font-medium mb-2">
                📝 Start from Template (Optional)
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
                <option value="">Select a template to pre-fill settings...</option>
                {templates.map((template: any) => (
                  <option key={template.id} value={template.id}>
                    {template.is_default ? '⭐ ' : ''}{template.name} - {template.description}
                  </option>
                ))}
              </select>
              <p className="text-xs text-slate-400 mt-2">
                Templates provide quick-start configurations. You can customize all settings after selection.
              </p>
            </div>
          )}

          {/* ============================================ */}
          {/* SECTION: BASIC INFORMATION */}
          {/* ============================================ */}
          <div className="border-b border-slate-700 pb-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span className="text-blue-400">1.</span> Basic Information
            </h3>

            {/* Bot Name */}
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2">Bot Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
                placeholder="My Trading Bot"
                required
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium mb-2">Description</label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
                placeholder="Optional description"
                rows={2}
              />
            </div>
          </div>

          {/* Market Type Toggle */}
          <div className="border-b border-slate-700 pb-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span className="text-blue-400">2.</span> Market Type
            </h3>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setFormData({ ...formData, market_type: 'spot' })}
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
                onClick={() => setFormData({ ...formData, market_type: 'perps' })}
                className={`flex-1 py-2 px-4 rounded border text-sm font-medium transition-colors ${
                  formData.market_type === 'perps'
                    ? 'border-purple-500 bg-purple-500/20 text-purple-400'
                    : 'border-slate-600 bg-slate-700 text-slate-400 hover:border-slate-500'
                }`}
              >
                Perpetual Futures
              </button>
            </div>

            {/* Perps-specific config */}
            {formData.market_type === 'perps' && (
              <div className="mt-4 space-y-3 p-4 bg-purple-500/5 border border-purple-500/20 rounded">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Leverage (1-10x)</label>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={formData.strategy_config.leverage || 1}
                      onChange={(e) => setFormData({
                        ...formData,
                        strategy_config: { ...formData.strategy_config, leverage: parseInt(e.target.value) || 1 }
                      })}
                      className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Margin Type</label>
                    <select
                      value={formData.strategy_config.margin_type || 'CROSS'}
                      onChange={(e) => setFormData({
                        ...formData,
                        strategy_config: { ...formData.strategy_config, margin_type: e.target.value }
                      })}
                      className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white text-sm"
                    >
                      <option value="CROSS">Cross</option>
                      <option value="ISOLATED">Isolated</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Take Profit %</label>
                    <input
                      type="number"
                      step="0.1"
                      min={0}
                      value={formData.strategy_config.default_tp_pct || ''}
                      onChange={(e) => setFormData({
                        ...formData,
                        strategy_config: { ...formData.strategy_config, default_tp_pct: parseFloat(e.target.value) || undefined }
                      })}
                      className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white text-sm"
                      placeholder="e.g. 5.0"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Stop Loss %</label>
                    <input
                      type="number"
                      step="0.1"
                      min={0}
                      value={formData.strategy_config.default_sl_pct || ''}
                      onChange={(e) => setFormData({
                        ...formData,
                        strategy_config: { ...formData.strategy_config, default_sl_pct: parseFloat(e.target.value) || undefined }
                      })}
                      className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white text-sm"
                      placeholder="e.g. 3.0"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Direction</label>
                  <select
                    value={formData.strategy_config.direction || 'long_only'}
                    onChange={(e) => setFormData({
                      ...formData,
                      strategy_config: { ...formData.strategy_config, direction: e.target.value }
                    })}
                    className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white text-sm"
                  >
                    <option value="long_only">Long Only</option>
                    <option value="short_only">Short Only</option>
                    <option value="both">Both (Long + Short)</option>
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* ============================================ */}
          {/* SECTION: EXCHANGE CONFIGURATION */}
          {/* ============================================ */}
          <DexConfigSection
            config={{
              exchange_type: formData.exchange_type,
              chain_id: formData.chain_id,
              dex_router: formData.dex_router,
              wallet_private_key: formData.wallet_private_key,
              rpc_url: formData.rpc_url,
            }}
            onChange={(dexConfig) => setFormData({ ...formData, ...dexConfig })}
          />

          {/* ============================================ */}
          {/* SECTION: STRATEGY */}
          {/* ============================================ */}
          <div className="border-b border-slate-700 pb-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span className="text-blue-400">3.</span> Strategy
            </h3>

            {/* Strategy Selection */}
            <div>
              <label className="block text-sm font-medium mb-2">Trading Strategy *</label>
              <select
                value={formData.strategy_type}
                onChange={(e) => handleStrategyChange(e.target.value)}
                className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
                required
              >
                <option value="">Select a strategy...</option>
                {strategies.map((strategy) => (
                  <option key={strategy.id} value={strategy.id}>
                    {strategy.name}
                  </option>
                ))}
              </select>
              {selectedStrategy && (
                <p className="text-sm text-slate-400 mt-2">{selectedStrategy.description}</p>
              )}
            </div>
          </div>

          {/* ============================================ */}
          {/* SECTION: MARKETS & PAIRS */}
          {/* ============================================ */}
          <div className="border-b border-slate-700 pb-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span className="text-blue-400">4.</span> Markets & Trading Pairs
            </h3>

            {/* Trading Pairs (3Commas Style Multi-Select with Single Market Constraint) */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Pairs
            </label>

            {/* Determine current market (quote currency) based on selected pairs */}
            {(() => {
              // Helper: get market from pair ID (e.g., "ETH-BTC" -> "BTC")
              const getMarket = (pairId: string) => pairId.split('-')[1]

              // Determine which market is currently selected
              const selectedMarket = formData.product_ids.length > 0
                ? getMarket(formData.product_ids[0])
                : null

              // Check if a market is locked (2+ pairs selected from same market)
              const isMarketLocked = formData.product_ids.length >= 2

              // Handler for pair checkbox change with 3Commas logic
              const handlePairToggle = (pairValue: string, isChecked: boolean) => {
                const pairMarket = getMarket(pairValue)

                if (isChecked) {
                  // Adding a pair
                  if (!selectedMarket) {
                    // No pairs selected yet - just add this one
                    setFormData({ ...formData, product_ids: [pairValue], product_id: pairValue })
                  } else if (pairMarket === selectedMarket) {
                    // Adding from same market - just add it
                    setFormData({
                      ...formData,
                      product_ids: [...formData.product_ids, pairValue],
                      product_id: formData.product_ids[0] || pairValue
                    })
                  } else {
                    // Switching markets - clear previous selections and select only this pair
                    setFormData({ ...formData, product_ids: [pairValue], product_id: pairValue })
                  }
                } else {
                  // Removing a pair
                  const newIds = formData.product_ids.filter(id => id !== pairValue)
                  setFormData({
                    ...formData,
                    product_ids: newIds,
                    product_id: newIds[0] || 'ETH-BTC'
                  })
                }
              }

              return (
                <>
                  {/* Header with count and unselect all */}
                  <div className="flex items-center justify-between mb-2 px-3 py-2 bg-slate-700 border border-slate-600 rounded-t">
                    <span className="text-sm text-slate-300">
                      {formData.product_ids.length} pairs
                      {selectedMarket && <span className="text-slate-400 ml-2">({selectedMarket} market)</span>}
                    </span>
                    {formData.product_ids.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setFormData({ ...formData, product_ids: [], product_id: 'ETH-BTC' })}
                        className="text-xs text-blue-400 hover:text-blue-300"
                      >
                        Unselect all ({formData.product_ids.length})
                      </button>
                    )}
                  </div>

                  {/* Quick filter buttons - only show for markets with pairs */}
                  <div className="flex flex-wrap gap-2 mb-3 px-1">
                    {['BTC', 'USD', 'USDC', 'USDT'].map((market) => {
                      const marketPairs = TRADING_PAIRS.filter((p: { value: string; label: string; group: string }) => p.group === market).map((p: { value: string; label: string; group: string }) => p.value)

                      // Don't show button if market has no pairs
                      if (marketPairs.length === 0) return null

                      const isDisabled = isMarketLocked && selectedMarket !== market

                      return (
                        <button
                          key={market}
                          type="button"
                          onClick={() => {
                            setFormData({
                              ...formData,
                              product_ids: marketPairs,
                              product_id: marketPairs[0] || 'ETH-BTC'
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

                  {/* Pair list - grouped by quote currency, sorted by volume */}
                  <div className="border border-slate-600 border-t-0 rounded-b bg-slate-700 p-3 max-h-72 overflow-y-auto">
                    {['BTC', 'USD', 'USDC', 'USDT'].map((group) => {
                      const groupPairs = TRADING_PAIRS.filter((p: { value: string; label: string; group: string }) => p.group === group)
                      if (groupPairs.length === 0) return null

                      // Hide this market group if locked and not the selected market
                      const isGroupHidden = isMarketLocked && selectedMarket !== group
                      if (isGroupHidden) return null

                      return (
                        <div key={group} className="mb-3 last:mb-0">
                          <div className="text-xs font-medium text-slate-400 mb-1.5">
                            {group} Pairs
                          </div>
                          <div className="grid grid-cols-2 gap-1">
                            {groupPairs.map((pair: { value: string; label: string; group: string }) => {
                              const isChecked = formData.product_ids.includes(pair.value)

                              return (
                                <label
                                  key={pair.value}
                                  className="flex items-center space-x-2 px-2 py-1 rounded text-sm cursor-pointer hover:bg-slate-600"
                                >
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    onChange={(e) => handlePairToggle(pair.value, e.target.checked)}
                                    className="rounded border-slate-500"
                                  />
                                  {getCategoryBadge(pair.value)}
                                  <span className="text-xs">{pair.label}</span>
                                </label>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {/* Auto-add new pairs checkbox */}
                  {formData.product_ids.length > 5 && (
                    <div className="mt-4 pt-4 border-t border-slate-600">
                      <label className="flex items-start gap-3 cursor-pointer group">
                        <input
                          type="checkbox"
                          checked={formData.strategy_config?.auto_add_new_pairs || false}
                          onChange={(e) => {
                            setFormData({
                              ...formData,
                              strategy_config: {
                                ...formData.strategy_config,
                                auto_add_new_pairs: e.target.checked,
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
                            Automatically add newly listed {selectedMarket} pairs to this bot daily.
                            Delisted pairs are always removed automatically.
                          </p>
                        </div>
                      </label>
                    </div>
                  )}

                  {/* Allowed Categories - Bot-level filtering */}
                  <div className="mt-4 pt-4 border-t border-slate-600">
                    <label className="block text-sm font-medium text-slate-300 mb-3">
                      Allowed Coin Categories
                      <span className="text-xs text-slate-400 font-normal ml-2">
                        (Select which types of coins this bot can trade)
                      </span>
                    </label>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { value: 'APPROVED', label: 'Approved', description: 'Strong fundamentals, clear utility', color: 'green' },
                        { value: 'BORDERLINE', label: 'Borderline', description: 'Some concerns, declining relevance', color: 'yellow' },
                        { value: 'QUESTIONABLE', label: 'Questionable', description: 'Significant red flags, unclear utility', color: 'orange' },
                        { value: 'MEME', label: 'Meme Coins', description: 'Community-driven, high volatility', color: 'purple' },
                        { value: 'BLACKLISTED', label: 'Blacklisted', description: 'Scams, abandoned projects', color: 'red' },
                      ].map((category) => {
                        const allowedCategories = formData.strategy_config?.allowed_categories || ['APPROVED', 'BORDERLINE']
                        const isChecked = allowedCategories.includes(category.value)

                        const colorClasses = {
                          green: 'border-green-600 bg-green-950/30',
                          yellow: 'border-yellow-600 bg-yellow-950/30',
                          orange: 'border-orange-600 bg-orange-950/30',
                          purple: 'border-purple-600 bg-purple-950/30',
                          red: 'border-red-600 bg-red-950/30',
                        }

                        return (
                          <label
                            key={category.value}
                            className={`flex items-start gap-3 p-3 rounded border-2 cursor-pointer transition-all ${
                              isChecked
                                ? colorClasses[category.color as keyof typeof colorClasses]
                                : 'border-slate-600 bg-slate-700/50 opacity-60'
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={(e) => {
                                const currentCategories = formData.strategy_config?.allowed_categories || ['APPROVED', 'BORDERLINE']
                                const newCategories = e.target.checked
                                  ? [...currentCategories, category.value]
                                  : currentCategories.filter((c: string) => c !== category.value)

                                setFormData({
                                  ...formData,
                                  strategy_config: {
                                    ...formData.strategy_config,
                                    allowed_categories: newCategories,
                                  },
                                })
                              }}
                              className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0"
                            />
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium text-slate-200">
                                {category.label}
                                <span className="text-xs text-slate-400 font-normal ml-1.5">
                                  ({categoryCounts[category.value] || 0})
                                </span>
                              </div>
                              <div className="text-xs text-slate-400 mt-0.5">
                                {category.description}
                              </div>
                            </div>
                          </label>
                        )
                      })}
                    </div>
                    <p className="text-xs text-slate-400 mt-3">
                      💡 Bot will only trade coins in selected categories. Unselected categories are filtered out before trading.
                    </p>
                  </div>
                </>
              )
            })()}
          </div>
          </div>

          {/* ============================================ */}
          {/* SECTION: MONITORING & TIMING */}
          {/* ============================================ */}
          <div className="border-b border-slate-700 pb-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span className="text-blue-400">5.</span> Monitoring & Timing
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
                  value={formData.check_interval_seconds === undefined || formData.check_interval_seconds === null ? '' : formData.check_interval_seconds}
                  onChange={(e) => {
                    const val = e.target.value
                    setFormData({ ...formData, check_interval_seconds: val === '' ? undefined : parseInt(val) })
                  }}
                  onBlur={(e) => {
                    if (e.target.value === '' || isNaN(parseInt(e.target.value))) {
                      setFormData({ ...formData, check_interval_seconds: 300 })
                    }
                  }}
                  className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
                  placeholder="300"
                />
                <p className="text-xs text-slate-400 mt-1.5">
                  How often to run AI analysis (technical checks use candle interval)<br/>
                  <span className="text-slate-500">Default: 300s (5 min) • Gemini: 1800s (30 min)</span>
                </p>
              </div>
            </div>
          </div>

          {/* ============================================ */}
          {/* SECTION: BUDGET & RISK MANAGEMENT */}
          {/* Only show for non-AI strategies (AI strategies have this in Strategy Parameters) */}
          {/* ============================================ */}
          {formData.strategy_type !== 'ai_autonomous' && (
          <div className="border-b border-slate-700 pb-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span className="text-blue-400">6.</span> Budget & Risk Management
            </h3>

            {/* Reserved Balance Configuration */}
            <div className="bg-orange-900/20 border border-orange-700/50 rounded-lg p-4 mb-4">
              <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                💰 Budget Allocation <span className="text-xs font-normal text-slate-400">(Optional)</span>
              </h4>
              <p className="text-xs text-slate-300 mb-3">
                Set bot budget as a percentage of aggregate portfolio value. Leave at 0 to use total portfolio balance.
              </p>

              {/* Budget Percentage (Preferred) */}
              <div className="mb-4">
                <label className="block text-xs font-medium text-emerald-300 mb-1.5">
                  Budget Percentage <span className="text-slate-400">(% of aggregate portfolio)</span>
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="100"
                    value={formData.budget_percentage === undefined || formData.budget_percentage === null ? '' : formData.budget_percentage}
                    onChange={(e) => {
                      const val = e.target.value
                      setFormData({ ...formData, budget_percentage: val === '' ? undefined : parseFloat(val) })
                    }}
                    onBlur={(e) => {
                      // Ensure valid number on blur
                      if (e.target.value === '' || isNaN(parseFloat(e.target.value))) {
                        setFormData({ ...formData, budget_percentage: 0 })
                      }
                    }}
                    className="flex-1 rounded border border-emerald-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
                    placeholder="0.0"
                  />
                  <span className="text-emerald-400 font-medium">%</span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Recommended: 33% for 3 bots, 50% for 2 bots, 100% for 1 bot
                </p>
              </div>

              {/* Legacy Reserved Balances (Deprecated) */}
              <details className="text-xs text-slate-400">
                <summary className="cursor-pointer hover:text-slate-300 mb-2">Legacy: Fixed Reserved Balances (deprecated)</summary>
                <div className="grid grid-cols-2 gap-4 pt-2">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">Reserved BTC</label>
                    <input
                      type="number"
                      step="0.00000001"
                      min="0"
                      value={formData.reserved_btc_balance === undefined || formData.reserved_btc_balance === null ? '' : formData.reserved_btc_balance}
                      onChange={(e) => {
                        const val = e.target.value
                        setFormData({ ...formData, reserved_btc_balance: val === '' ? undefined : parseFloat(val) })
                      }}
                      onBlur={(e) => {
                        if (e.target.value === '' || isNaN(parseFloat(e.target.value))) {
                          setFormData({ ...formData, reserved_btc_balance: 0 })
                        }
                      }}
                      className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
                      placeholder="0.0"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">Reserved USD</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.reserved_usd_balance === undefined || formData.reserved_usd_balance === null ? '' : formData.reserved_usd_balance}
                      onChange={(e) => {
                        const val = e.target.value
                        setFormData({ ...formData, reserved_usd_balance: val === '' ? undefined : parseFloat(val) })
                      }}
                      onBlur={(e) => {
                        if (e.target.value === '' || isNaN(parseFloat(e.target.value))) {
                          setFormData({ ...formData, reserved_usd_balance: 0 })
                        }
                      }}
                      className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
                      placeholder="0.00"
                    />
                  </div>
                </div>
              </details>
            </div>

            {/* Budget Splitting Toggle - Only show for multi-pair */}
            {formData.product_ids.length > 1 && (
            <div className="bg-blue-900/20 border border-blue-700/50 rounded-lg p-4">
              <label className="flex items-start space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.split_budget_across_pairs}
                  onChange={(e) => setFormData({ ...formData, split_budget_across_pairs: e.target.checked })}
                  className="mt-1 rounded border-slate-500"
                />
                <div className="flex-1">
                  <div className="font-medium text-white mb-1">Split Budget Across Pairs</div>
                  <div className="text-sm text-slate-300">
                    {formData.split_budget_across_pairs ? (
                      <>
                        <span className="text-green-400">✓ Enabled:</span> Budget percentages will be divided by {formData.strategy_config?.max_concurrent_deals || 1} max concurrent deals.
                        <br />
                        <span className="text-xs text-slate-400">
                          Example: 30% max usage ÷ {formData.strategy_config?.max_concurrent_deals || 1} = {(30 / (formData.strategy_config?.max_concurrent_deals || 1)).toFixed(1)}% per deal (safer)
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="text-yellow-400">○ Disabled:</span> Each deal gets full budget allocation independently.
                        <br />
                        <span className="text-xs text-slate-400">
                          Example: 30% max usage × {formData.strategy_config?.max_concurrent_deals || 1} deals = up to {30 * (formData.strategy_config?.max_concurrent_deals || 1)}% total (3Commas style)
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </label>
            </div>
          )}
          </div>
          )}

          {/* ============================================ */}
          {/* SECTION: STRATEGY CONFIGURATION */}
          {/* ============================================ */}
          {selectedStrategy && (selectedStrategy.id === 'conditional_dca' || selectedStrategy.id === 'indicator_based' || selectedStrategy.parameters.length > 0) && (
          <div className="border-b border-slate-700 pb-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <span className="text-blue-400">{formData.strategy_type === 'ai_autonomous' ? '6' : '7'}.</span> Strategy Parameters
            </h3>

          {/* Dynamic Strategy Parameters */}
          {(formData.strategy_type === 'conditional_dca' || formData.strategy_type === 'indicator_based') ? (
            <ThreeCommasStyleForm
              config={formData.strategy_config}
              onChange={(newConfig) =>
                setFormData({ ...formData, strategy_config: newConfig })
              }
              quoteCurrency={formData.product_ids.length > 0 ? formData.product_ids[0].split('-')[1] : 'BTC'}
              aggregateBtcValue={aggregateData?.aggregate_btc_value}
              aggregateUsdValue={aggregateData?.aggregate_usd_value}
              budgetPercentage={formData.budget_percentage}
              numPairs={formData.product_ids.length}
              splitBudget={formData.split_budget_across_pairs}
              maxConcurrentDeals={formData.strategy_config.max_concurrent_deals}
            />
          ) : selectedStrategy.parameters.length > 0 ? (
(() => {
              // Check if manual sizing mode is enabled
              const useManualSizing = formData.strategy_config.use_manual_sizing === true

              // Parameters to render separately in the custom budget section
              const customBudgetParams = ['use_manual_sizing', 'max_concurrent_deals', 'max_simultaneous_same_pair']

              // Group parameters by group property
              // Exclude params we render in custom budget section
              const parametersByGroup = selectedStrategy.parameters.reduce((acc: Record<string, StrategyParameter[]>, param: StrategyParameter) => {
                if (!isParameterVisible(param, formData.strategy_config)) return acc
                if (customBudgetParams.includes(param.name)) return acc  // Skip - rendered separately

                const group = param.group || 'Other'
                if (!acc[group]) acc[group] = []
                acc[group].push(param)
                return acc
              }, {} as Record<string, StrategyParameter[]>)

              // Get max_concurrent_deals param for custom rendering
              const maxConcurrentDealsParam = selectedStrategy.parameters.find((p: StrategyParameter) => p.name === 'max_concurrent_deals')
              const maxSimSamePairParam = selectedStrategy.parameters.find((p: StrategyParameter) => p.name === 'max_simultaneous_same_pair')

              // Define group display order - separated into always-show and conditional groups
              const alwaysShowGroups = [
                'Control Mode',
                'AI Configuration',
                'Analysis Timing',
                'Web Search (Optional)',
              ]

              // AI-driven budget groups (shown when manual sizing is OFF)
              const aiBudgetGroups = [
                'Budget & Position Sizing',
                'DCA (Safety Orders)',
              ]

              // Manual sizing group (shown when manual sizing is ON)
              const manualSizingGroups = [
                'Manual Order Sizing',
              ]

              const alwaysShowAfterGroups = [
                'Profit & Exit',
                'Market Filters',
                'Other'
              ]

              // Non-AI strategy groups (bull_flag, etc.)
              const nonAIStrategyGroups = [
                'Pattern Detection',
                'Risk Management',
                'Budget',
              ]

              // Check if this is a non-AI strategy (e.g., bull_flag)
              const isNonAIStrategy = formData.strategy_type === 'bull_flag' ||
                (!selectedStrategy.parameters.some((p: StrategyParameter) => p.group === 'AI Configuration'))

              // Helper to render a group
              const renderGroup = (groupName: string) => {
                const groupParams = parametersByGroup[groupName]
                if (!groupParams || groupParams.length === 0) return null

                return (
                  <div key={groupName} className="bg-slate-750 rounded-lg p-4 border border-slate-700">
                    <h4 className="text-sm font-semibold text-slate-300 mb-4 border-b border-slate-600 pb-2">
                      {groupName}
                    </h4>
                    <div className="space-y-4">
                      {groupParams.map((param: StrategyParameter) => (
                        <div key={param.name}>
                          <label className="block text-sm font-medium mb-2">
                            {param.display_name || param.description}
                            {param.min_value !== undefined && param.max_value !== undefined && (
                              <span className="text-slate-400 text-xs ml-2">
                                ({param.min_value} - {param.max_value})
                              </span>
                            )}
                          </label>
                          {param.description && param.display_name && (
                            <p className="text-xs text-slate-400 mb-2">{param.description}</p>
                          )}
                          {renderParameterInput(param)}

                          {/* Show preset threshold values when risk_tolerance is not manual */}
                          {param.name === 'risk_tolerance' && formData.strategy_config.risk_tolerance && formData.strategy_config.risk_tolerance !== 'manual' && (
                            <div className="mt-2 p-3 bg-blue-900/20 border border-blue-700/50 rounded text-xs">
                              <p className="font-semibold text-blue-400 mb-2">Preset Confidence Thresholds:</p>
                              <div className="grid grid-cols-3 gap-2 text-slate-300">
                                {formData.strategy_config.risk_tolerance === 'aggressive' && (
                                  <>
                                    <div>Open: <span className="text-white font-semibold">70%</span></div>
                                    <div>DCA: <span className="text-white font-semibold">65%</span></div>
                                    <div>Sell: <span className="text-white font-semibold">60%</span></div>
                                  </>
                                )}
                                {formData.strategy_config.risk_tolerance === 'moderate' && (
                                  <>
                                    <div>Open: <span className="text-white font-semibold">75%</span></div>
                                    <div>DCA: <span className="text-white font-semibold">70%</span></div>
                                    <div>Sell: <span className="text-white font-semibold">65%</span></div>
                                  </>
                                )}
                                {formData.strategy_config.risk_tolerance === 'conservative' && (
                                  <>
                                    <div>Open: <span className="text-white font-semibold">80%</span></div>
                                    <div>DCA: <span className="text-white font-semibold">75%</span></div>
                                    <div>Sell: <span className="text-white font-semibold">70%</span></div>
                                  </>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )
              }

              // For non-AI strategies like bull_flag, render all their groups directly
              if (isNonAIStrategy) {
                return (
                  <div className="space-y-6">
                    {/* Render non-AI strategy groups */}
                    {nonAIStrategyGroups.map(renderGroup)}
                    {/* Also render any 'Other' parameters */}
                    {renderGroup('Other')}
                  </div>
                )
              }

              return (
                <div className="space-y-6">
                  {/* Always-show groups first */}
                  {alwaysShowGroups.map(renderGroup)}

                  {/* Manual vs AI Sizing Toggle - Always visible */}
                  <div className="bg-gradient-to-r from-purple-900/30 to-blue-900/30 rounded-lg p-4 border border-purple-700/50">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <h4 className="text-sm font-semibold text-white mb-1">
                          Order Sizing Mode
                        </h4>
                        <p className="text-xs text-slate-400">
                          {useManualSizing
                            ? '📊 Manual: Fixed percentages based on total portfolio value'
                            : '🤖 AI-Directed: AI determines allocation within budget limits'}
                        </p>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer ml-4">
                        <input
                          type="checkbox"
                          checked={useManualSizing}
                          onChange={(e) => handleParamChange('use_manual_sizing', e.target.checked)}
                          className="sr-only peer"
                        />
                        <div className="w-14 h-7 bg-slate-600 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-purple-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all peer-checked:bg-purple-600"></div>
                        <span className="ml-3 text-sm font-medium text-slate-300">
                          {useManualSizing ? 'Manual' : 'AI'}
                        </span>
                      </label>
                    </div>
                  </div>

                  {/* Bot Budget Allocation - Content varies by mode */}
                  <div className="bg-slate-750 rounded-lg p-4 border border-slate-700">
                    <h4 className="text-sm font-semibold text-slate-300 mb-4 border-b border-slate-600 pb-2">
                      {useManualSizing ? 'Position Limits' : 'Bot Budget Allocation'}
                    </h4>
                    <div className="space-y-4">
                      {/* Max Concurrent Positions - Shows in both modes */}
                      {maxConcurrentDealsParam && (
                        <div>
                          <label className="block text-sm font-medium mb-2">
                            {maxConcurrentDealsParam.display_name || 'Max Concurrent Positions'}
                            <span className="text-slate-400 text-xs ml-2">
                              ({maxConcurrentDealsParam.min_value} - {maxConcurrentDealsParam.max_value})
                            </span>
                          </label>
                          <p className="text-xs text-slate-400 mb-2">
                            {maxConcurrentDealsParam.description}
                          </p>
                          {renderParameterInput(maxConcurrentDealsParam)}
                        </div>
                      )}

                      {/* Max Simultaneous Same Pair */}
                      {maxSimSamePairParam && (
                        <div>
                          <label className="block text-sm font-medium mb-2 flex items-center gap-1">
                            {maxSimSamePairParam.display_name || 'Max Simultaneous Deals (Same Pair)'}
                            <span className="text-slate-400 text-xs ml-1">
                              (1 - {formData.strategy_config.max_concurrent_deals || 1})
                            </span>
                            <span
                              className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-slate-600 text-slate-300 text-xs cursor-help"
                              title="Controls how many positions can be open on the SAME trading pair simultaneously. A new deal for the same pair only opens after ALL existing deals on that pair have exhausted their safety orders."
                            >i</span>
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
                            Budget Percentage <span className="text-slate-400 text-xs ml-2">(% of aggregate portfolio)</span>
                          </label>
                          <p className="text-xs text-slate-400 mb-2">
                            AI determines order sizes within this budget allocation.
                          </p>
                          <div className="flex items-center gap-2">
                            <input
                              type="number"
                              step="0.1"
                              min="0"
                              max="100"
                              value={formData.budget_percentage === undefined || formData.budget_percentage === null ? '' : formData.budget_percentage}
                              onChange={(e) => {
                                const val = e.target.value
                                setFormData({ ...formData, budget_percentage: val === '' ? undefined : parseFloat(val) })
                              }}
                              onBlur={(e) => {
                                if (e.target.value === '' || isNaN(parseFloat(e.target.value))) {
                                  setFormData({ ...formData, budget_percentage: 0 })
                                }
                              }}
                              className="flex-1 rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
                              placeholder="0.0"
                            />
                            <span className="text-slate-400 font-medium">%</span>
                          </div>
                          <p className="text-xs text-slate-500 mt-1">
                            Recommended: 33% for 3 bots, 50% for 2 bots, 100% for 1 bot
                          </p>
                        </div>
                      )}

                      {/* Budget Splitting Toggle - AI mode only, multi-pair */}
                      {!useManualSizing && formData.product_ids.length > 1 && (
                        <div className="bg-blue-900/20 border border-blue-700/50 rounded-lg p-3">
                          <label className="flex items-start space-x-3 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={formData.split_budget_across_pairs}
                              onChange={(e) => setFormData({ ...formData, split_budget_across_pairs: e.target.checked })}
                              className="mt-1 rounded border-slate-500"
                            />
                            <div className="flex-1">
                              <div className="font-medium text-white text-sm mb-1">Split Budget Across Pairs</div>
                              <div className="text-xs text-slate-300">
                                {formData.split_budget_across_pairs ? (
                                  <>
                                    <span className="text-green-400">✓ Enabled:</span> Budget divided by {formData.strategy_config?.max_concurrent_deals || 1} max concurrent deals.
                                  </>
                                ) : (
                                  <>
                                    <span className="text-yellow-400">○ Disabled:</span> Each deal gets full budget allocation.
                                  </>
                                )}
                              </div>
                            </div>
                          </label>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Conditional budget groups based on manual sizing toggle */}
                  {useManualSizing ? (
                    // Manual Mode: Show Manual Order Sizing options
                    <>
                      {manualSizingGroups.map(renderGroup)}
                    </>
                  ) : (
                    // AI Mode: Show AI-driven budget groups
                    <>
                      {aiBudgetGroups.map(renderGroup)}
                    </>
                  )}

                  {/* Always-show groups after budget section */}
                  {alwaysShowAfterGroups.map(renderGroup)}
                </div>
              )
            })()
          ) : null}
          </div>
          )}

          {/* Validation Errors (Block Save) */}
          {validationErrors.length > 0 && (
            <div className="bg-red-900/40 border-2 border-red-600 rounded-lg p-4 mb-4">
              <div className="flex items-start gap-3">
                <div className="text-red-500 text-2xl flex-shrink-0">🚫</div>
                <div className="flex-1">
                  <div className="font-bold text-red-300 mb-2 text-lg">
                    Cannot Save - Order Size Below Exchange Minimum
                  </div>
                  <div className="text-sm text-red-200/90 mb-3">
                    Your configured order percentages result in order sizes below the exchange minimum. Increase the percentages or add more funds to your account.
                  </div>
                  <div className="space-y-2">
                    {validationErrors.map((error, idx) => (
                      <div key={idx} className="bg-red-900/30 rounded p-3 border border-red-600/50">
                        <div className="font-medium text-red-300 mb-1">
                          {error.field === 'base_order_value' ? '📊 Base Order Value' : '📈 DCA Order Value'}
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
          )}

          {/* Validation Warnings */}
          {validationWarnings.length > 0 && (
            <div className="bg-yellow-900/30 border border-yellow-700 rounded-lg p-4 mb-4">
              <div className="flex items-start gap-3">
                <div className="text-yellow-500 text-xl flex-shrink-0">⚠️</div>
                <div className="flex-1">
                  <div className="font-semibold text-yellow-300 mb-2">
                    Minimum Order Size Warning
                  </div>
                  <div className="text-sm text-yellow-200/90 mb-3">
                    The following products may fail to execute orders because your configured budget percentage is below the exchange's minimum order size:
                  </div>
                  <div className="space-y-2">
                    {validationWarnings.map((warning, idx) => (
                      <div key={idx} className="bg-yellow-900/20 rounded p-3 border border-yellow-700/50">
                        <div className="font-medium text-yellow-300 mb-1">
                          {warning.product_id}
                        </div>
                        <div className="text-xs text-yellow-200/80 space-y-1">
                          <div>Current budget: <span className="font-mono text-red-400">{warning.current_pct.toFixed(2)}%</span></div>
                          <div>Suggested minimum: <span className="font-mono text-green-400">{warning.suggested_minimum_pct.toFixed(2)}%</span></div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="text-xs text-yellow-200/70 mt-3">
                    You can still create this bot, but orders may fail until you increase the budget percentage or add more funds.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-700">
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
              disabled={createBot.isPending || updateBot.isPending || validationErrors.length > 0}
            >
              {createBot.isPending || updateBot.isPending
                ? 'Saving...'
                : validationErrors.length > 0
                ? 'Fix Errors First'
                : editingBot
                ? 'Update Bot'
                : 'Create Bot'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
