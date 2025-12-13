import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { botsApi, templatesApi } from '../services/api'
import { Bot, BotCreate, StrategyParameter } from '../types'
import { Plus, Edit, Trash2, Activity, Copy, Brain, MoreVertical, FastForward, Building2, Wallet, ScanLine, BarChart2 } from 'lucide-react'
import ThreeCommasStyleForm from '../components/ThreeCommasStyleForm'
import PhaseConditionSelector from '../components/PhaseConditionSelector'
import AIBotLogs from '../components/AIBotLogs'
import IndicatorLogs from '../components/IndicatorLogs'
import ScannerLogs from '../components/ScannerLogs'
import { PnLChart } from '../components/PnLChart'
import DexConfigSection from '../components/DexConfigSection'
import axios from 'axios'
import { useAccount, getChainName } from '../contexts/AccountContext'
import {
  type BotFormData,
  type ValidationWarning,
  type ValidationError,
  type TradingPair,
  getDefaultFormData,
  convertProductsToTradingPairs,
  DEFAULT_TRADING_PAIRS,
  isParameterVisible,
} from '../components/bots'

// Helper function to check if a condition uses AI indicators
// Prioritize 'type' over legacy 'indicator' field (matches backend logic)
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

function Bots() {
  const queryClient = useQueryClient()
  const location = useLocation()
  const { selectedAccount } = useAccount()
  const [showModal, setShowModal] = useState(false)
  const [editingBot, setEditingBot] = useState<Bot | null>(null)
  const [aiLogsBotId, setAiLogsBotId] = useState<number | null>(null)
  const [indicatorLogsBotId, setIndicatorLogsBotId] = useState<number | null>(null)
  const [scannerLogsBotId, setScannerLogsBotId] = useState<number | null>(null)
  const [openMenuId, setOpenMenuId] = useState<number | null>(null)
  const [validationWarnings, setValidationWarnings] = useState<ValidationWarning[]>([])
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([])
  const [formData, setFormData] = useState<BotFormData>(getDefaultFormData())

  // Fetch all bots (filtered by selected account)
  const { data: bots = [], isLoading: botsLoading } = useQuery({
    queryKey: ['bots', selectedAccount?.id],
    queryFn: botsApi.getAll,
    refetchInterval: 5000,
    select: (data) => {
      if (!selectedAccount) return data
      // Filter by account_id
      return data.filter((bot: Bot) => bot.account_id === selectedAccount.id)
    },
  })

  // Fetch available strategies
  const { data: strategies = [] } = useQuery({
    queryKey: ['strategies'],
    queryFn: botsApi.getStrategies,
  })

  // Fetch portfolio data for percentage calculations (account-specific)
  const { data: portfolio, isLoading: portfolioLoading } = useQuery({
    queryKey: ['account-portfolio-bots', selectedAccount?.id],
    queryFn: async () => {
      if (selectedAccount) {
        const response = await fetch(`/api/accounts/${selectedAccount.id}/portfolio`)
        if (!response.ok) throw new Error('Failed to fetch portfolio')
        return response.json()
      }
      const response = await fetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 60000, // Update every 60 seconds
  })

  // Validate bot configuration against Coinbase minimum order sizes
  const validateBotConfig = async () => {
    // Only validate if we have products and strategy config
    if (formData.product_ids.length === 0 || !formData.strategy_config) {
      setValidationWarnings([])
      return
    }

    // Skip if no budget percentage configured
    const budgetPct = formData.strategy_config.base_order_percentage ||
                      formData.strategy_config.safety_order_percentage ||
                      formData.strategy_config.initial_budget_percentage
    if (!budgetPct || budgetPct === 0) {
      setValidationWarnings([])
      return
    }

    try {
      const response = await axios.post('/api/bots/validate-config', {
        product_ids: formData.product_ids,
        strategy_config: formData.strategy_config
      })

      if (response.data.warnings) {
        setValidationWarnings(response.data.warnings)
      } else {
        setValidationWarnings([])
      }
    } catch (error) {
      console.error('Validation error:', error)
      setValidationWarnings([])
    }
  }

  // Validate manual order sizing values against exchange minimums
  const validateManualOrderSizing = () => {
    const errors: ValidationError[] = []

    // Only validate if manual sizing mode is enabled
    if (!formData.strategy_config.use_manual_sizing) {
      setValidationErrors([])
      return
    }

    // Get aggregate portfolio value from portfolio data
    // For BTC pairs, use aggregate BTC value; for USD pairs, use aggregate USD value
    const hasBtcPairs = formData.product_ids.some(p => p.endsWith('-BTC'))
    const hasUsdPairs = formData.product_ids.some(p => p.endsWith('-USD') || p.endsWith('-USDC') || p.endsWith('-USDT'))

    // Exchange minimums
    const BTC_MINIMUM = 0.0001  // Coinbase minimum for BTC pairs
    const USD_MINIMUM = 1.0     // Coinbase minimum for USD pairs (roughly)

    if (portfolio) {
      // Use balance_breakdown.btc.total which is the true aggregate (free + in positions)
      const aggregateBtc = portfolio.balance_breakdown?.btc?.total || portfolio.total_btc_value || 0
      const aggregateUsd = portfolio.total_usd_value || 0

      // Validate base_order_value
      const baseOrderPct = formData.strategy_config.base_order_value
      if (baseOrderPct && baseOrderPct > 0) {
        if (hasBtcPairs) {
          const calculatedBtc = aggregateBtc * (baseOrderPct / 100)
          if (calculatedBtc < BTC_MINIMUM) {
            errors.push({
              field: 'base_order_value',
              message: `Base Order Value (${baseOrderPct}%) calculates to ${calculatedBtc.toFixed(8)} BTC, which is below Coinbase's minimum of ${BTC_MINIMUM} BTC`,
              calculated_value: calculatedBtc,
              minimum_required: BTC_MINIMUM
            })
          }
        }
        if (hasUsdPairs) {
          const calculatedUsd = aggregateUsd * (baseOrderPct / 100)
          if (calculatedUsd < USD_MINIMUM) {
            errors.push({
              field: 'base_order_value',
              message: `Base Order Value (${baseOrderPct}%) calculates to $${calculatedUsd.toFixed(2)}, which is below Coinbase's minimum of $${USD_MINIMUM}`,
              calculated_value: calculatedUsd,
              minimum_required: USD_MINIMUM
            })
          }
        }
      }

      // Validate dca_order_value
      const dcaOrderPct = formData.strategy_config.dca_order_value
      if (dcaOrderPct && dcaOrderPct > 0) {
        if (hasBtcPairs) {
          const calculatedBtc = aggregateBtc * (dcaOrderPct / 100)
          if (calculatedBtc < BTC_MINIMUM) {
            errors.push({
              field: 'dca_order_value',
              message: `DCA Order Value (${dcaOrderPct}%) calculates to ${calculatedBtc.toFixed(8)} BTC, which is below Coinbase's minimum of ${BTC_MINIMUM} BTC`,
              calculated_value: calculatedBtc,
              minimum_required: BTC_MINIMUM
            })
          }
        }
        if (hasUsdPairs) {
          const calculatedUsd = aggregateUsd * (dcaOrderPct / 100)
          if (calculatedUsd < USD_MINIMUM) {
            errors.push({
              field: 'dca_order_value',
              message: `DCA Order Value (${dcaOrderPct}%) calculates to $${calculatedUsd.toFixed(2)}, which is below Coinbase's minimum of $${USD_MINIMUM}`,
              calculated_value: calculatedUsd,
              minimum_required: USD_MINIMUM
            })
          }
        }
      }
    }

    setValidationErrors(errors)
  }

  // Check for bot to edit from navigation state (from Dashboard Edit button)
  useEffect(() => {
    const state = location.state as { editBot?: Bot } | null
    if (state?.editBot) {
      const bot = state.editBot
      // Open modal and set bot for editing
      setEditingBot(bot)
      // Handle both legacy single pair and new multi-pair bots
      const productIds = (bot as any).product_ids || (bot.product_id ? [bot.product_id] : [])
      setFormData({
        name: bot.name,
        description: bot.description || '',
        reserved_btc_balance: bot.reserved_btc_balance || 0,
        reserved_usd_balance: bot.reserved_usd_balance || 0,
        budget_percentage: bot.budget_percentage || 0,
        check_interval_seconds: (bot as any).check_interval_seconds || 300,
        strategy_type: bot.strategy_type,
        product_id: bot.product_id,  // Keep for backward compatibility
        product_ids: productIds,
        split_budget_across_pairs: (bot as any).split_budget_across_pairs || false,
        strategy_config: bot.strategy_config,
        exchange_type: bot.exchange_type || 'cex',
      })
      setShowModal(true)
      // Clear navigation state to prevent reopening on refresh
      window.history.replaceState({}, '')
    }
  }, [location])

  // Auto-validate when relevant fields change
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      validateBotConfig()
      validateManualOrderSizing()
    }, 500) // Debounce 500ms

    return () => clearTimeout(timeoutId)
  }, [formData.product_ids, formData.strategy_config, portfolio])

  // Fetch available templates
  const { data: templates = [] } = useQuery({
    queryKey: ['templates'],
    queryFn: templatesApi.getAll,
  })

  // Fetch available trading pairs from Coinbase
  const { data: productsData } = useQuery({
    queryKey: ['available-products'],
    queryFn: async () => {
      const response = await axios.get('/api/products')
      return response.data
    },
    staleTime: 3600000, // Cache for 1 hour (product list rarely changes)
  })

  // Generate trading pairs from all available products
  const TRADING_PAIRS = useMemo<TradingPair[]>(() => {
    if (!productsData?.products) {
      return DEFAULT_TRADING_PAIRS
    }
    return convertProductsToTradingPairs(productsData.products)
  }, [productsData])

  // Get selected strategy definition
  const selectedStrategy = strategies.find((s) => s.id === formData.strategy_type)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (openMenuId !== null) {
        const target = event.target as Element
        if (!target.closest('.relative')) {
          setOpenMenuId(null)
        }
      }
    }

    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [openMenuId])

  // Create bot mutation
  const createBot = useMutation({
    mutationFn: (data: BotCreate) => botsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
      setShowModal(false)
      resetForm()
    },
    onError: (error: Error & { response?: { data?: { detail?: string | Array<{ msg: string; loc: string[] }> } } }) => {
      const detail = error.response?.data?.detail
      let message = 'Failed to create bot'
      if (typeof detail === 'string') {
        message = detail
      } else if (Array.isArray(detail)) {
        message = detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(', ')
      } else if (error.message) {
        message = error.message
      }
      alert(`Error: ${message}`)
      console.error('Create bot error:', error)
    },
  })

  // Update bot mutation
  const updateBot = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<BotCreate> }) =>
      botsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
      setShowModal(false)
      resetForm()
    },
    onError: (error: Error & { response?: { data?: { detail?: string | Array<{ msg: string; loc: string[] }> } } }) => {
      const detail = error.response?.data?.detail
      let message = 'Failed to update bot'
      if (typeof detail === 'string') {
        message = detail
      } else if (Array.isArray(detail)) {
        message = detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(', ')
      } else if (error.message) {
        message = error.message
      }
      alert(`Error: ${message}`)
      console.error('Update bot error:', error)
    },
  })

  // Delete bot mutation
  const deleteBot = useMutation({
    mutationFn: (id: number) => botsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Start bot mutation with optimistic update
  const startBot = useMutation({
    mutationFn: (id: number) => botsApi.start(id),
    onMutate: async (id) => {
      const queryKey = ['bots', selectedAccount?.id]
      await queryClient.cancelQueries({ queryKey })
      const previousBots = queryClient.getQueryData(queryKey)
      queryClient.setQueryData(queryKey, (old: Bot[] | undefined) =>
        old?.map(bot => bot.id === id ? { ...bot, is_active: true } : bot)
      )
      return { previousBots, queryKey }
    },
    onError: (_err, _id, context) => {
      if (context?.queryKey) {
        queryClient.setQueryData(context.queryKey, context.previousBots)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Stop bot mutation with optimistic update
  const stopBot = useMutation({
    mutationFn: (id: number) => botsApi.stop(id),
    onMutate: async (id) => {
      const queryKey = ['bots', selectedAccount?.id]
      await queryClient.cancelQueries({ queryKey })
      const previousBots = queryClient.getQueryData(queryKey)
      queryClient.setQueryData(queryKey, (old: Bot[] | undefined) =>
        old?.map(bot => bot.id === id ? { ...bot, is_active: false } : bot)
      )
      return { previousBots, queryKey }
    },
    onError: (_err, _id, context) => {
      if (context?.queryKey) {
        queryClient.setQueryData(context.queryKey, context.previousBots)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Clone bot mutation
  const cloneBot = useMutation({
    mutationFn: (id: number) => botsApi.clone(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Force run mutation
  const forceRunBot = useMutation({
    mutationFn: (id: number) => botsApi.forceRun(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // ESC key handler to close modal
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && showModal) {
        setShowModal(false)
        resetForm()
      }
    }

    if (showModal) {
      document.addEventListener('keydown', handleEscape)
      return () => {
        document.removeEventListener('keydown', handleEscape)
      }
    }
  }, [showModal])

  const resetForm = () => {
    setFormData(getDefaultFormData())
    setEditingBot(null)
  }

  const loadTemplate = (templateId: number) => {
    const template = templates.find((t: any) => t.id === templateId)
    if (!template) return

    setFormData({
      name: `${template.name} (Copy)`,  // Prefix to avoid name conflicts
      description: template.description || '',
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

  const handleOpenCreate = () => {
    resetForm()
    setShowModal(true)
  }

  const handleOpenEdit = (bot: Bot) => {
    setEditingBot(bot)
    // Handle both legacy single pair and new multi-pair bots
    const productIds = (bot as any).product_ids || (bot.product_id ? [bot.product_id] : [])
    setFormData({
      name: bot.name,
      description: bot.description || '',
      reserved_btc_balance: bot.reserved_btc_balance || 0,
      reserved_usd_balance: bot.reserved_usd_balance || 0,
      budget_percentage: bot.budget_percentage || 0,
      check_interval_seconds: (bot as any).check_interval_seconds || 300,
      strategy_type: bot.strategy_type,
      product_id: bot.product_id,  // Keep for backward compatibility
      product_ids: productIds,
      split_budget_across_pairs: (bot as any).split_budget_across_pairs || false,
      strategy_config: bot.strategy_config,
      exchange_type: bot.exchange_type || 'cex',
    })
    setShowModal(true)
  }

  const handleStrategyChange = (strategyType: string) => {
    const strategy = strategies.find((s) => s.id === strategyType)
    if (!strategy) return

    // Initialize config with default values
    const config: Record<string, any> = {}
    strategy.parameters.forEach((param) => {
      config[param.name] = param.default
    })

    setFormData({
      ...formData,
      strategy_type: strategyType,
      strategy_config: config,
    })
  }

  const handleParamChange = (paramName: string, value: any) => {
    setFormData({
      ...formData,
      strategy_config: {
        ...formData.strategy_config,
        [paramName]: value,
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

    // Validate at least one pair is selected
    if (formData.product_ids.length === 0) {
      alert('Please select at least one trading pair')
      return
    }

    const botData: any = {
      name: formData.name,
      description: formData.description || undefined,
      account_id: selectedAccount?.id,  // Link bot to selected account
      strategy_type: formData.strategy_type,
      product_id: formData.product_ids[0],  // Legacy - use first pair
      product_ids: formData.product_ids,  // Multi-pair support
      split_budget_across_pairs: formData.split_budget_across_pairs,  // Budget splitting option
      reserved_btc_balance: formData.reserved_btc_balance,
      reserved_usd_balance: formData.reserved_usd_balance,
      budget_percentage: formData.budget_percentage,
      check_interval_seconds: formData.check_interval_seconds,  // Monitoring interval
      strategy_config: formData.strategy_config,
      // DEX configuration fields
      exchange_type: formData.exchange_type,
      chain_id: formData.chain_id,
      dex_router: formData.dex_router,
      wallet_private_key: formData.wallet_private_key,
      rpc_url: formData.rpc_url,
    }

    console.log('Submitting bot data:', botData)
    if (editingBot) {
      console.log('Updating bot:', editingBot.id)
      updateBot.mutate({ id: editingBot.id, data: botData })
    } else {
      console.log('Creating new bot')
      createBot.mutate(botData)
    }
  }

  const handleDelete = (bot: Bot) => {
    if (bot.is_active) {
      alert('Cannot delete an active bot. Stop it first.')
      return
    }
    if (confirm(`Are you sure you want to delete "${bot.name}"?`)) {
      deleteBot.mutate(bot.id)
    }
  }

  const renderParameterInput = (param: StrategyParameter) => {
    const value = formData.strategy_config[param.name] ?? param.default

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
        className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
      />
    )
  }

  if (botsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">Loading bots...</div>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          {selectedAccount?.type === 'dex' ? (
            <Wallet className="w-8 h-8 text-orange-400" />
          ) : (
            <Building2 className="w-8 h-8 text-blue-400" />
          )}
          <div>
            <h2 className="text-2xl font-bold">Bot Management</h2>
            <p className="text-slate-400 text-sm mt-1">
              {selectedAccount && (
                <>
                  <span className="text-slate-300">{selectedAccount.name}</span>
                  {selectedAccount.type === 'dex' && selectedAccount.chain_id && (
                    <span className="text-slate-500"> ({getChainName(selectedAccount.chain_id)})</span>
                  )}
                  <span> • </span>
                </>
              )}
              Create and manage multiple trading bots
            </p>
          </div>
        </div>
        <button
          onClick={handleOpenCreate}
          className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>Create Bot</span>
        </button>
      </div>

      {/* P&L Chart - 3Commas-style (filtered by account) */}
      <div className="mb-6">
        <PnLChart accountId={selectedAccount?.id} />
      </div>

      {/* Bot List - 3Commas-style Table */}
      {bots.length === 0 ? (
        <div className="bg-slate-800 rounded-lg p-12 text-center">
          <Activity className="w-16 h-16 text-slate-600 mx-auto mb-4" />
          <h3 className="text-xl font-semibold mb-2">No bots yet</h3>
          <p className="text-slate-400 mb-6">Create your first trading bot to get started</p>
          <button
            onClick={handleOpenCreate}
            className="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded font-medium transition-colors"
          >
            Create Your First Bot
          </button>
        </div>
      ) : (
        <>
        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-slate-900 border-b border-slate-700">
                  <th className="text-left px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">Name</th>
                  <th className="text-left px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">Strategy</th>
                  <th className="text-left px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">Pair</th>
                  <th className="text-left px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">Active trades</th>
                  <th className="text-right px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">Trade Stats</th>
                  <th className="text-right px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">Win Rate</th>
                  <th className="text-right px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">PnL</th>
                  <th className="text-right px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">Projected PnL</th>
                  <th className="text-left px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">Budget</th>
                  <th className="text-center px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">Status</th>
                  <th className="text-center px-2 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium text-slate-400">Actions</th>
                </tr>
              </thead>
              <tbody>
                {bots.map((bot) => {
                  const botPairs = ((bot as any).product_ids || [bot.product_id])
                  const strategyName = strategies.find((s) => s.id === bot.strategy_type)?.name || bot.strategy_type
                  const aiProvider = bot.strategy_config?.ai_provider

                  return (
                    <tr
                      key={bot.id}
                      className="border-b border-slate-700 hover:bg-slate-750 transition-colors"
                    >
                      {/* Name & Description */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3">
                        <div className="flex flex-col">
                          <div className="flex items-center gap-1.5">
                            <span className="font-medium text-white">{bot.name}</span>
                            {(bot as any).insufficient_funds && (
                              <span
                                className="text-amber-500 text-sm"
                                title="Insufficient funds to open new positions"
                              >
                                💰
                              </span>
                            )}
                          </div>
                          {bot.description && (
                            <div className="text-xs text-slate-400 mt-0.5 line-clamp-1">
                              {bot.description}
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Strategy */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3">
                        <div className="flex flex-col">
                          <div className="text-sm text-white">{strategyName}</div>
                          {aiProvider && (
                            <a
                              href={
                                aiProvider === 'claude' ? 'https://console.anthropic.com/settings/billing'
                                : aiProvider === 'gemini' ? 'https://aistudio.google.com/app/apikey'
                                : aiProvider === 'grok' ? 'https://console.x.ai/'
                                : '#'
                              }
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-purple-400 hover:text-purple-300 mt-0.5 flex items-center gap-1 transition-colors cursor-pointer"
                              title="View API credits/usage"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {aiProvider === 'claude' ? '🤖 Claude'
                                : aiProvider === 'gemini' ? '🤖 Gemini'
                                : aiProvider === 'grok' ? '🤖 Grok'
                                : `🤖 ${aiProvider}`}
                              <span className="text-[10px]">💳</span>
                            </a>
                          )}
                        </div>
                      </td>

                      {/* Pairs */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3">
                        <div className="flex items-center gap-1">
                          {botPairs.length === 1 ? (
                            <span className="text-sm text-white font-mono">
                              {botPairs[0]}
                            </span>
                          ) : (
                            <span className="text-sm text-white font-mono" title={botPairs.join(', ')}>
                              {botPairs[0]} +{botPairs.length - 1}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Active Trades */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3">
                        {(bot.strategy_config?.max_concurrent_deals || bot.strategy_config?.max_concurrent_positions) ? (
                          <div className="text-sm">
                            <span className="text-blue-400 font-medium">
                              {(bot as any).open_positions_count || 0}
                            </span>
                            <span className="text-slate-500"> / </span>
                            <span className="text-slate-400">
                              {bot.strategy_config.max_concurrent_deals || bot.strategy_config.max_concurrent_positions}
                            </span>
                          </div>
                        ) : (
                          <span className="text-sm text-slate-500">—</span>
                        )}
                      </td>

                      {/* Trade Stats */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right">
                        <div className="flex flex-col items-end">
                          <div className="text-xs text-slate-400">
                            {(bot as any).closed_positions_count || 0} closed
                          </div>
                          <div className="text-xs text-slate-500">
                            {((bot as any).trades_per_day || 0).toFixed(2)}/day
                          </div>
                        </div>
                      </td>

                      {/* Win Rate */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right">
                        {(() => {
                          const winRate = (bot as any).win_rate || 0
                          const closedCount = (bot as any).closed_positions_count || 0
                          const colorClass = closedCount === 0 ? 'text-slate-500' :
                            winRate >= 70 ? 'text-green-400' :
                            winRate >= 50 ? 'text-yellow-400' :
                            'text-red-400'
                          return (
                            <span className={`text-sm font-medium ${colorClass}`}>
                              {closedCount === 0 ? '—' : `${winRate.toFixed(1)}%`}
                            </span>
                          )
                        })()}
                      </td>

                      {/* PnL */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right">
                        {(() => {
                          const pnl = (bot as any).total_pnl_usd || 0
                          const isPositive = pnl > 0
                          const isNegative = pnl < 0
                          return (
                            <span className={`text-sm font-medium ${
                              isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'
                            }`}>
                              {isPositive ? '+' : ''}${pnl.toFixed(2)} {isPositive ? '↑' : isNegative ? '↓' : ''}
                            </span>
                          )
                        })()}
                      </td>

                      {/* Projected PnL */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-right">
                        {(() => {
                          const dailyPnl = (bot as any).avg_daily_pnl_usd || 0
                          const portfolioUsd = portfolio?.total_usd_value || 0

                          // Calculate bot's allocated value based on its budget percentage
                          const botBudgetPct = bot.budget_percentage || 100
                          const botAllocatedValue = portfolioUsd * (botBudgetPct / 100)

                          // Calculate daily rate for this bot
                          const dailyRate = botAllocatedValue > 0 ? dailyPnl / botAllocatedValue : 0

                          // Use compound interest for projections
                          const compoundGain = (days: number) => {
                            if (botAllocatedValue <= 0 || dailyRate === 0) return dailyPnl * days
                            return botAllocatedValue * (Math.pow(1 + dailyRate, days) - 1)
                          }

                          const weeklyPnl = compoundGain(7)
                          const monthlyPnl = compoundGain(30)
                          const yearlyPnl = compoundGain(365)

                          const isPositive = dailyPnl > 0
                          const isNegative = dailyPnl < 0
                          const colorClass = isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'
                          const prefix = isPositive ? '+' : ''

                          return (
                            <div className="text-xs space-y-0.5">
                              <div className={`font-medium ${colorClass}`}>
                                Day: {prefix}${dailyPnl.toFixed(2)}
                              </div>
                              <div className={`${colorClass}`}>
                                Week: {prefix}${weeklyPnl.toFixed(2)}
                              </div>
                              <div className={`${colorClass}`}>
                                Month: {prefix}${monthlyPnl.toFixed(2)}
                              </div>
                              <div className={`${colorClass}`}>
                                Year: {prefix}${yearlyPnl.toFixed(2)}
                              </div>
                            </div>
                          )
                        })()}
                      </td>

                      {/* Budget */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3">
                        <div className="flex flex-col gap-1">
                          {bot.budget_percentage > 0 ? (
                            <span className="text-sm text-emerald-400 font-medium">
                              {bot.budget_percentage}%
                            </span>
                          ) : (
                            <span className="text-sm text-slate-500">All</span>
                          )}
                          {/* Budget Utilization */}
                          {bot.budget_utilization_percentage !== undefined && (
                            <div className="text-[10px] text-slate-400">
                              {bot.budget_utilization_percentage.toFixed(1)}% in use
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Status Toggle */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3">
                        <div className="flex justify-center">
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={bot.is_active}
                              onChange={() => {
                                if (bot.is_active) {
                                  stopBot.mutate(bot.id)
                                } else {
                                  startBot.mutate(bot.id)
                                }
                              }}
                              className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
                          </label>
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="px-2 sm:px-4 py-2 sm:py-3">
                        <div className="flex items-center justify-center gap-2">
                          {botUsesAIIndicators(bot) && (
                            <button
                              onClick={() => setAiLogsBotId(bot.id)}
                              className="p-1.5 bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 rounded transition-colors"
                              title="View AI Reasoning Logs"
                            >
                              <Brain className="w-4 h-4" />
                            </button>
                          )}
                          {botUsesNonAIIndicators(bot) && (
                            <button
                              onClick={() => setIndicatorLogsBotId(bot.id)}
                              className="p-1.5 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-400 rounded transition-colors"
                              title="View Indicator Logs"
                            >
                              <BarChart2 className="w-4 h-4" />
                            </button>
                          )}
                          {botUsesBullFlagIndicator(bot) && (
                            <button
                              onClick={() => setScannerLogsBotId(bot.id)}
                              className="p-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded transition-colors"
                              title="View Scanner Logs"
                            >
                              <ScanLine className="w-4 h-4" />
                            </button>
                          )}

                          {/* Force Run Button - only show for active bots */}
                          {bot.is_active && (
                            <button
                              onClick={() => forceRunBot.mutate(bot.id)}
                              disabled={forceRunBot.isPending}
                              className="p-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                              title="Force Run Now"
                            >
                              <FastForward className="w-4 h-4" />
                            </button>
                          )}

                          {/* More Actions Menu */}
                          <div className="relative">
                            <button
                              onClick={() => setOpenMenuId(openMenuId === bot.id ? null : bot.id)}
                              className="p-1.5 bg-slate-700 hover:bg-slate-600 rounded transition-colors"
                              title="More actions"
                            >
                              <MoreVertical className="w-4 h-4" />
                            </button>

                            {/* Dropdown Menu */}
                            {openMenuId === bot.id && (
                              <div className="absolute right-0 mt-2 w-48 bg-slate-800 rounded-lg shadow-lg border border-slate-700 z-10">
                                <button
                                  onClick={() => {
                                    handleOpenEdit(bot)
                                    setOpenMenuId(null)
                                  }}
                                  className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left rounded-t-lg transition-colors"
                                >
                                  <Edit className="w-4 h-4" />
                                  <span>Edit Bot</span>
                                </button>
                                <button
                                  onClick={() => {
                                    cloneBot.mutate(bot.id)
                                    setOpenMenuId(null)
                                  }}
                                  className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left transition-colors"
                                >
                                  <Copy className="w-4 h-4 text-blue-400" />
                                  <span>Clone Bot</span>
                                </button>
                                <button
                                  onClick={() => {
                                    handleDelete(bot)
                                    setOpenMenuId(null)
                                  }}
                                  disabled={bot.is_active}
                                  className="w-full flex items-center space-x-2 px-4 py-2 hover:bg-slate-700 text-left rounded-b-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  <Trash2 className="w-4 h-4 text-red-400" />
                                  <span>Delete Bot</span>
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Summary Totals Table */}
        <div className="mt-4 bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-slate-900">
              <tr>
                <th className="text-left px-2 sm:px-4 py-2 sm:py-3 text-sm font-medium text-slate-400">Portfolio Totals</th>
                <th className="text-right px-2 sm:px-4 py-2 sm:py-3 text-sm font-medium text-slate-400">Daily</th>
                <th className="text-right px-2 sm:px-4 py-2 sm:py-3 text-sm font-medium text-slate-400">Weekly</th>
                <th className="text-right px-2 sm:px-4 py-2 sm:py-3 text-sm font-medium text-slate-400">Monthly</th>
                <th className="text-right px-2 sm:px-4 py-2 sm:py-3 text-sm font-medium text-slate-400">Yearly</th>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const totalDailyPnl = bots.reduce((sum, bot) => sum + ((bot as any).avg_daily_pnl_usd || 0), 0)
                const portfolioUsd = portfolio?.total_usd_value || 0

                // Calculate daily rate as a decimal (e.g., 0.0009 for 0.09%)
                const dailyRate = portfolioUsd > 0 ? totalDailyPnl / portfolioUsd : 0

                // Use compound interest for projections: P * (1 + r)^n - P
                // This accounts for percentage-based bots where gains compound
                const compoundGain = (days: number) => {
                  if (portfolioUsd <= 0 || dailyRate === 0) return totalDailyPnl * days
                  return portfolioUsd * (Math.pow(1 + dailyRate, days) - 1)
                }

                const totalWeeklyPnl = compoundGain(7)
                const totalMonthlyPnl = compoundGain(30)
                const totalYearlyPnl = compoundGain(365)

                const isPositive = totalDailyPnl > 0
                const isNegative = totalDailyPnl < 0
                const colorClass = isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'
                const prefix = isPositive ? '+' : ''

                // Calculate percentage gains based on portfolio value (also compounded)
                const dailyPct = dailyRate * 100
                const weeklyPct = portfolioUsd > 0 ? (totalWeeklyPnl / portfolioUsd) * 100 : 0
                const monthlyPct = portfolioUsd > 0 ? (totalMonthlyPnl / portfolioUsd) * 100 : 0
                const yearlyPct = portfolioUsd > 0 ? (totalYearlyPnl / portfolioUsd) * 100 : 0
                const pctPrefix = isPositive ? '+' : ''

                // Format percentage - show loading indicator if portfolio not loaded yet
                const formatPct = (pct: number) => {
                  if (portfolioLoading || portfolioUsd === 0) return '--'
                  return `${pctPrefix}${pct.toFixed(2)}`
                }

                return (
                  <tr>
                    <td className="px-2 sm:px-4 py-2 sm:py-3 text-sm font-semibold text-slate-300">Projected PnL</td>
                    <td className={`px-2 sm:px-4 py-2 sm:py-3 text-right text-lg font-bold ${colorClass}`}>
                      {prefix}${totalDailyPnl.toFixed(2)}
                      <span className="text-xs ml-1 text-slate-400">
                        ({formatPct(dailyPct)}%)
                      </span>
                    </td>
                    <td className={`px-2 sm:px-4 py-2 sm:py-3 text-right text-lg font-bold ${colorClass}`}>
                      {prefix}${totalWeeklyPnl.toFixed(2)}
                      <span className="text-xs ml-1 text-slate-400">
                        ({formatPct(weeklyPct)}%)
                      </span>
                    </td>
                    <td className={`px-2 sm:px-4 py-2 sm:py-3 text-right text-lg font-bold ${colorClass}`}>
                      {prefix}${totalMonthlyPnl.toFixed(2)}
                      <span className="text-xs ml-1 text-slate-400">
                        ({formatPct(monthlyPct)}%)
                      </span>
                    </td>
                    <td className={`px-2 sm:px-4 py-2 sm:py-3 text-right text-lg font-bold ${colorClass}`}>
                      {prefix}${totalYearlyPnl.toFixed(2)}
                      <span className="text-xs ml-1 text-slate-400">
                        ({formatPct(yearlyPct)}%)
                      </span>
                    </td>
                  </tr>
                )
              })()}
            </tbody>
          </table>
        </div>
        </>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className={`bg-slate-800 rounded-lg w-full max-h-[90vh] overflow-y-auto ${
            formData.strategy_type === 'conditional_dca' ? 'max-w-6xl' : 'max-w-2xl'
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
              {/* SECTION 1: BASIC INFORMATION */}
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

              {/* ============================================ */}
              {/* SECTION 2: EXCHANGE CONFIGURATION */}
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
              {/* SECTION 3: STRATEGY */}
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
              {/* SECTION 3: MARKETS & PAIRS */}
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
                                      <span className="text-xs">{pair.label}</span>
                                    </label>
                                  )
                                })}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </>
                  )
                })()}
              </div>
              </div>

              {/* ============================================ */}
              {/* SECTION 4: MONITORING & TIMING */}
              {/* ============================================ */}
              <div className="border-b border-slate-700 pb-6">
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <span className="text-blue-400">5.</span> Monitoring & Timing
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">
                      Check Interval (seconds)
                    </label>
                    <input
                      type="number"
                      step="60"
                      min="60"
                      max="3600"
                      value={formData.check_interval_seconds}
                      onChange={(e) => setFormData({ ...formData, check_interval_seconds: parseInt(e.target.value) || 300 })}
                      className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
                      placeholder="300"
                    />
                    <p className="text-xs text-slate-400 mt-1.5">
                      How often to monitor positions<br/>
                      <span className="text-slate-500">Default: 300s (5 min) • Gemini: 1800s (30 min)</span>
                    </p>
                  </div>
                </div>
              </div>

              {/* ============================================ */}
              {/* SECTION 5: BUDGET & RISK MANAGEMENT */}
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
                        value={formData.budget_percentage}
                        onChange={(e) => setFormData({ ...formData, budget_percentage: parseFloat(e.target.value) || 0 })}
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
                          value={formData.reserved_btc_balance}
                          onChange={(e) => setFormData({ ...formData, reserved_btc_balance: parseFloat(e.target.value) || 0 })}
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
                          value={formData.reserved_usd_balance}
                          onChange={(e) => setFormData({ ...formData, reserved_usd_balance: parseFloat(e.target.value) || 0 })}
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
              {/* SECTION 6: STRATEGY CONFIGURATION */}
              {/* Section number is 6 for AI strategies (Budget section hidden), 7 for others */}
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
                />
              ) : selectedStrategy.parameters.length > 0 ? (
(() => {
                  // Check if manual sizing mode is enabled
                  const useManualSizing = formData.strategy_config.use_manual_sizing === true

                  // Parameters to render separately in the custom budget section
                  const customBudgetParams = ['use_manual_sizing', 'max_concurrent_deals']

                  // Group parameters by group property
                  // Exclude params we render in custom budget section
                  const parametersByGroup = selectedStrategy.parameters.reduce((acc, param) => {
                    if (!isParameterVisible(param, formData.strategy_config)) return acc
                    if (customBudgetParams.includes(param.name)) return acc  // Skip - rendered separately

                    const group = param.group || 'Other'
                    if (!acc[group]) acc[group] = []
                    acc[group].push(param)
                    return acc
                  }, {} as Record<string, StrategyParameter[]>)

                  // Get max_concurrent_deals param for custom rendering
                  const maxConcurrentDealsParam = selectedStrategy.parameters.find(p => p.name === 'max_concurrent_deals')

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
                    (!selectedStrategy.parameters.some(p => p.group === 'AI Configuration'))

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
                          {groupParams.map((param) => (
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
                                  value={formData.budget_percentage}
                                  onChange={(e) => setFormData({ ...formData, budget_percentage: parseFloat(e.target.value) || 0 })}
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
                        Your configured order percentages result in order sizes below Coinbase's minimum. Increase the percentages or add more funds to your account.
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
                        The following products may fail to execute orders because your configured budget percentage is below Coinbase's minimum order size:
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
      )}

      {/* AI Bot Logs Modal */}
      {aiLogsBotId !== null && (
        <AIBotLogs
          botId={aiLogsBotId}
          isOpen={aiLogsBotId !== null}
          onClose={() => setAiLogsBotId(null)}
        />
      )}

      {/* Indicator Logs Modal */}
      {indicatorLogsBotId !== null && (
        <IndicatorLogs
          botId={indicatorLogsBotId}
          isOpen={indicatorLogsBotId !== null}
          onClose={() => setIndicatorLogsBotId(null)}
        />
      )}

      {/* Scanner Logs Modal */}
      {scannerLogsBotId !== null && (
        <ScannerLogs
          botId={scannerLogsBotId}
          isOpen={scannerLogsBotId !== null}
          onClose={() => setScannerLogsBotId(null)}
        />
      )}
    </div>
  )
}

export default Bots
