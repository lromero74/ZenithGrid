import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { botsApi, templatesApi } from '../services/api'
import { Bot, BotCreate, StrategyDefinition, StrategyParameter } from '../types'
import { Plus, Play, Square, Edit, Trash2, TrendingUp, Activity, Copy, Brain, MoreVertical } from 'lucide-react'
import ThreeCommasStyleForm from '../components/ThreeCommasStyleForm'
import AIBotLogs from '../components/AIBotLogs'
import axios from 'axios'

interface BotFormData {
  name: string
  description: string
  strategy_type: string
  product_id: string  // Legacy - kept for backward compatibility
  product_ids: string[]  // Multi-pair support
  split_budget_across_pairs: boolean  // Budget splitting toggle
  reserved_btc_balance: number  // BTC allocated to this bot
  reserved_usd_balance: number  // USD allocated to this bot
  check_interval_seconds: number  // How often bot monitors positions
  analysis_interval_minutes: number  // How often AI analyzes (for AI bots)
  strategy_config: Record<string, any>
}

interface ValidationWarning {
  product_id: string
  issue: string
  suggested_minimum_pct: number
  current_pct: number
}

function Bots() {
  const queryClient = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingBot, setEditingBot] = useState<Bot | null>(null)
  const [aiLogsBotId, setAiLogsBotId] = useState<number | null>(null)
  const [openMenuId, setOpenMenuId] = useState<number | null>(null)
  const [validationWarnings, setValidationWarnings] = useState<ValidationWarning[]>([])
  const [formData, setFormData] = useState<BotFormData>({
    name: '',
    description: '',
    strategy_type: '',
    product_id: 'ETH-BTC',  // Legacy fallback
    product_ids: [],  // Start with empty array, user will select
    split_budget_across_pairs: false,  // Default to independent budgets (3Commas style)
    reserved_btc_balance: 0,  // No reserved balance by default
    reserved_usd_balance: 0,  // No reserved balance by default
    check_interval_seconds: 300,  // Default: 5 minutes
    analysis_interval_minutes: 15,  // Default: 15 minutes (for AI bots)
    strategy_config: {},
  })

  // Fetch all bots
  const { data: bots = [], isLoading: botsLoading } = useQuery({
    queryKey: ['bots'],
    queryFn: botsApi.getAll,
    refetchInterval: 5000,
  })

  // Fetch available strategies
  const { data: strategies = [] } = useQuery({
    queryKey: ['strategies'],
    queryFn: botsApi.getStrategies,
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
      const response = await axios.post('http://localhost:8000/api/bots/validate-config', {
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

  // Auto-validate when relevant fields change
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      validateBotConfig()
    }, 500) // Debounce 500ms

    return () => clearTimeout(timeoutId)
  }, [formData.product_ids, formData.strategy_config])

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
  const TRADING_PAIRS = useMemo(() => {
    if (!productsData?.products) {
      // Fallback to default pairs while loading
      return [
        { value: 'BTC-USD', label: 'BTC/USD', group: 'USD', base: 'BTC' },
        { value: 'ETH-USD', label: 'ETH/USD', group: 'USD', base: 'ETH' },
        { value: 'ETH-BTC', label: 'ETH/BTC', group: 'BTC', base: 'ETH' },
      ]
    }

    // Popularity order (by market cap / trading volume)
    const popularityOrder = [
      'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'AVAX', 'LINK', 'DOT',
      'MATIC', 'UNI', 'LTC', 'ATOM', 'XLM', 'ALGO', 'AAVE', 'COMP', 'MKR',
      'SNX', 'CRV', 'SUSHI', 'YFI', '1INCH', 'BAT', 'ZRX', 'ENJ', 'MANA',
      'GRT', 'FIL', 'ICP', 'VET', 'FTM', 'SAND', 'AXS', 'GALA', 'CHZ'
    ]

    // Convert products to trading pairs with grouping
    const pairs = productsData.products.map((product: any) => {
      const base = product.base_currency
      const quote = product.quote_currency
      // Group by quote currency type
      const group = quote === 'USD' ? 'USD' : quote === 'USDT' ? 'USDT' : quote === 'USDC' ? 'USDC' : 'BTC'

      return {
        value: product.product_id,
        label: `${base}/${quote}`,
        group,
        base
      }
    })

    // Sort by: 1) group, 2) popularity order
    return pairs.sort((a: any, b: any) => {
      // Group priority: BTC > USD > USDC > USDT > others
      const groupOrder: Record<string, number> = { 'BTC': 1, 'USD': 2, 'USDC': 3, 'USDT': 4 }
      const aGroupPriority = groupOrder[a.group] || 99
      const bGroupPriority = groupOrder[b.group] || 99

      if (aGroupPriority !== bGroupPriority) {
        return aGroupPriority - bGroupPriority
      }

      // Within same group, sort by popularity
      const aPopularity = popularityOrder.indexOf(a.base)
      const bPopularity = popularityOrder.indexOf(b.base)
      const aRank = aPopularity === -1 ? 999 : aPopularity
      const bRank = bPopularity === -1 ? 999 : bPopularity

      if (aRank !== bRank) {
        return aRank - bRank
      }

      // If both unlisted, sort alphabetically
      return a.label.localeCompare(b.label)
    })
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
  })

  // Delete bot mutation
  const deleteBot = useMutation({
    mutationFn: (id: number) => botsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Start bot mutation
  const startBot = useMutation({
    mutationFn: (id: number) => botsApi.start(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] })
    },
  })

  // Stop bot mutation
  const stopBot = useMutation({
    mutationFn: (id: number) => botsApi.stop(id),
    onSuccess: () => {
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
    setFormData({
      name: '',
      description: '',
      strategy_type: '',
      product_id: 'ETH-BTC',
      product_ids: [],
      split_budget_across_pairs: false,
      reserved_btc_balance: 0,
      reserved_usd_balance: 0,
      check_interval_seconds: 300,
      analysis_interval_minutes: 15,
      strategy_config: {},
    })
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
      check_interval_seconds: template.check_interval_seconds || 300,
      analysis_interval_minutes: template.strategy_config?.analysis_interval_minutes || 15,
      strategy_config: template.strategy_config,
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
      check_interval_seconds: (bot as any).check_interval_seconds || 300,
      analysis_interval_minutes: (bot.strategy_config as any)?.analysis_interval_minutes || 15,
      strategy_type: bot.strategy_type,
      product_id: bot.product_id,  // Keep for backward compatibility
      product_ids: productIds,
      split_budget_across_pairs: (bot as any).split_budget_across_pairs || false,
      strategy_config: bot.strategy_config,
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

    // Validate at least one pair is selected
    if (formData.product_ids.length === 0) {
      alert('Please select at least one trading pair')
      return
    }

    const botData: any = {
      name: formData.name,
      description: formData.description || undefined,
      strategy_type: formData.strategy_type,
      product_id: formData.product_ids[0],  // Legacy - use first pair
      product_ids: formData.product_ids,  // Multi-pair support
      split_budget_across_pairs: formData.split_budget_across_pairs,  // Budget splitting option
      reserved_btc_balance: formData.reserved_btc_balance,
      reserved_usd_balance: formData.reserved_usd_balance,
      check_interval_seconds: formData.check_interval_seconds,  // Monitoring interval
      strategy_config: {
        ...formData.strategy_config,
        analysis_interval_minutes: formData.analysis_interval_minutes  // For AI bots
      },
    }

    if (editingBot) {
      updateBot.mutate({ id: editingBot.id, data: botData })
    } else {
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

    return (
      <input
        type={inputType}
        step={step}
        min={param.min_value}
        max={param.max_value}
        value={value}
        onChange={(e) => {
          const val =
            param.type === 'float'
              ? parseFloat(e.target.value)
              : param.type === 'int'
              ? parseInt(e.target.value)
              : e.target.value
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
        <div>
          <h2 className="text-2xl font-bold">Bot Management</h2>
          <p className="text-slate-400 text-sm mt-1">Create and manage multiple trading bots</p>
        </div>
        <button
          onClick={handleOpenCreate}
          className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>Create Bot</span>
        </button>
      </div>

      {/* Bot List */}
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {bots.map((bot) => (
            <div
              key={bot.id}
              className="bg-slate-800 rounded-lg p-6 border border-slate-700 hover:border-slate-600 transition-colors"
            >
              {/* Bot Header with Toggle */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold">{bot.name}</h3>
                  {bot.description && (
                    <p className="text-sm text-slate-400 mt-1">{bot.description}</p>
                  )}
                </div>
                {/* Toggle Switch */}
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

              {/* Bot Details */}
              <div className="space-y-2 mb-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Strategy:</span>
                  <span className="text-white font-medium">
                    {strategies.find((s) => s.id === bot.strategy_type)?.name || bot.strategy_type}
                  </span>
                </div>
                {bot.strategy_type === 'ai_autonomous' && bot.strategy_config?.ai_provider && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-slate-400">AI Provider:</span>
                    <span className="text-purple-400 font-medium">
                      {bot.strategy_config.ai_provider === 'claude' ? '🤖 Claude'
                        : bot.strategy_config.ai_provider === 'gemini' ? '🤖 Gemini'
                        : bot.strategy_config.ai_provider === 'grok' ? '🤖 Grok'
                        : `🤖 ${bot.strategy_config.ai_provider}`}
                    </span>
                  </div>
                )}
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Pairs:</span>
                  <span className="text-white font-medium text-xs">
                    {((bot as any).product_ids || [bot.product_id]).join(', ')}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Status:</span>
                  <span className={`font-medium ${bot.is_active ? 'text-green-400' : 'text-slate-400'}`}>
                    {bot.is_active ? 'Running' : 'Stopped'}
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center space-x-2">
                {bot.strategy_type === 'ai_autonomous' && (
                  <button
                    onClick={() => setAiLogsBotId(bot.id)}
                    className="flex-1 flex items-center justify-center space-x-2 bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 px-3 py-2 rounded transition-colors"
                    title="View AI Reasoning Logs"
                  >
                    <Brain className="w-4 h-4" />
                    <span>AI Logs</span>
                  </button>
                )}
                {/* ... Menu */}
                <div className="relative">
                  <button
                    onClick={() => setOpenMenuId(openMenuId === bot.id ? null : bot.id)}
                    className="p-2 bg-slate-700 hover:bg-slate-600 rounded transition-colors"
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
            </div>
          ))}
        </div>
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
              {/* SECTION 2: STRATEGY */}
              {/* ============================================ */}
              <div className="border-b border-slate-700 pb-6">
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <span className="text-blue-400">2.</span> Strategy
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
                  <span className="text-blue-400">3.</span> Markets & Trading Pairs
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
                          const marketPairs = TRADING_PAIRS.filter(p => p.group === market).map(p => p.value)

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
                          const groupPairs = TRADING_PAIRS.filter(p => p.group === group)
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
                                {groupPairs.map((pair) => {
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
                  <span className="text-blue-400">4.</span> Monitoring & Timing
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

                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">
                      AI Analysis Interval (minutes)
                    </label>
                    <input
                      type="number"
                      step="5"
                      min="5"
                      max="120"
                      value={formData.analysis_interval_minutes}
                      onChange={(e) => setFormData({ ...formData, analysis_interval_minutes: parseInt(e.target.value) || 15 })}
                      className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white font-mono text-sm"
                      placeholder="15"
                    />
                    <p className="text-xs text-slate-400 mt-1.5">
                      How often AI analyzes markets (AI bots only)<br/>
                      <span className="text-slate-500">Default: 15 min • Gemini: 60 min</span>
                    </p>
                  </div>
                </div>
              </div>

              {/* ============================================ */}
              {/* SECTION 5: BUDGET & RISK MANAGEMENT */}
              {/* ============================================ */}
              <div className="border-b border-slate-700 pb-6">
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <span className="text-blue-400">5.</span> Budget & Risk Management
                </h3>

                {/* Reserved Balance Configuration */}
                <div className="bg-orange-900/20 border border-orange-700/50 rounded-lg p-4 mb-4">
                  <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                    💰 Balance Allocation <span className="text-xs font-normal text-slate-400">(Optional)</span>
                  </h4>
                  <p className="text-xs text-slate-300 mb-3">
                    Reserve specific balance for this bot. Leave at 0 to use total portfolio balance.
                  </p>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1.5">Reserved BTC</label>
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
                      <label className="block text-xs font-medium text-slate-300 mb-1.5">Reserved USD</label>
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
                            <span className="text-green-400">✓ Enabled:</span> Budget percentages will be divided by {formData.product_ids.length} pairs.
                            <br />
                            <span className="text-xs text-slate-400">
                              Example: 30% max usage ÷ {formData.product_ids.length} = {(30 / formData.product_ids.length).toFixed(1)}% per pair (safer)
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="text-yellow-400">○ Disabled:</span> Each pair gets full budget allocation independently.
                            <br />
                            <span className="text-xs text-slate-400">
                              Example: 30% max usage × {formData.product_ids.length} pairs = up to {30 * formData.product_ids.length}% total (3Commas style)
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </label>
                </div>
              )}
              </div>

              {/* ============================================ */}
              {/* SECTION 6: STRATEGY CONFIGURATION */}
              {/* ============================================ */}
              {selectedStrategy && (selectedStrategy.id === 'conditional_dca' || selectedStrategy.parameters.length > 0) && (
              <div className="border-b border-slate-700 pb-6">
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <span className="text-blue-400">6.</span> Strategy Parameters
                </h3>

              {/* Dynamic Strategy Parameters */}
              {formData.strategy_type === 'conditional_dca' ? (
                <ThreeCommasStyleForm
                  config={formData.strategy_config}
                  onChange={(newConfig) =>
                    setFormData({ ...formData, strategy_config: newConfig })
                  }
                />
              ) : selectedStrategy.parameters.length > 0 ? (
                <div className="space-y-4">
                  {selectedStrategy.parameters.map((param) => (
                    <div key={param.name}>
                      <label className="block text-sm font-medium mb-2">
                        {param.description}
                        {param.min_value !== undefined && param.max_value !== undefined && (
                          <span className="text-slate-400 text-xs ml-2">
                            ({param.min_value} - {param.max_value})
                          </span>
                        )}
                      </label>
                      {renderParameterInput(param)}
                    </div>
                  ))}
                </div>
              ) : null}
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
                  className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-700 transition-colors"
                  disabled={createBot.isPending || updateBot.isPending}
                >
                  {createBot.isPending || updateBot.isPending
                    ? 'Saving...'
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
    </div>
  )
}

export default Bots
