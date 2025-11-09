import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { botsApi } from '../services/api'
import { Bot, BotCreate, StrategyDefinition, StrategyParameter } from '../types'
import { Plus, Play, Square, Edit, Trash2, TrendingUp, Activity } from 'lucide-react'

const TRADING_PAIRS = [
  { value: 'ETH-BTC', label: 'ETH/BTC', group: 'BTC Pairs' },
  { value: 'SOL-BTC', label: 'SOL/BTC', group: 'BTC Pairs' },
  { value: 'LINK-BTC', label: 'LINK/BTC', group: 'BTC Pairs' },
  { value: 'MATIC-BTC', label: 'MATIC/BTC', group: 'BTC Pairs' },
  { value: 'AVAX-BTC', label: 'AVAX/BTC', group: 'BTC Pairs' },
  { value: 'DOT-BTC', label: 'DOT/BTC', group: 'BTC Pairs' },
  { value: 'UNI-BTC', label: 'UNI/BTC', group: 'BTC Pairs' },
  { value: 'ATOM-BTC', label: 'ATOM/BTC', group: 'BTC Pairs' },
  { value: 'LTC-BTC', label: 'LTC/BTC', group: 'BTC Pairs' },
  { value: 'XLM-BTC', label: 'XLM/BTC', group: 'BTC Pairs' },
  { value: 'BTC-USD', label: 'BTC/USD', group: 'USD Pairs' },
  { value: 'ETH-USD', label: 'ETH/USD', group: 'USD Pairs' },
  { value: 'SOL-USD', label: 'SOL/USD', group: 'USD Pairs' },
  { value: 'USDC-USD', label: 'USDC/USD', group: 'USD Pairs' },
]

interface BotFormData {
  name: string
  description: string
  strategy_type: string
  product_id: string
  strategy_config: Record<string, any>
}

function Bots() {
  const queryClient = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingBot, setEditingBot] = useState<Bot | null>(null)
  const [formData, setFormData] = useState<BotFormData>({
    name: '',
    description: '',
    strategy_type: '',
    product_id: 'ETH-BTC',
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

  // Get selected strategy definition
  const selectedStrategy = strategies.find((s) => s.id === formData.strategy_type)

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

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      strategy_type: '',
      product_id: 'ETH-BTC',
      strategy_config: {},
    })
    setEditingBot(null)
  }

  const handleOpenCreate = () => {
    resetForm()
    setShowModal(true)
  }

  const handleOpenEdit = (bot: Bot) => {
    setEditingBot(bot)
    setFormData({
      name: bot.name,
      description: bot.description || '',
      strategy_type: bot.strategy_type,
      product_id: bot.product_id,
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

    const botData: BotCreate = {
      name: formData.name,
      description: formData.description || undefined,
      strategy_type: formData.strategy_type,
      product_id: formData.product_id,
      strategy_config: formData.strategy_config,
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
              {/* Bot Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold">{bot.name}</h3>
                  {bot.description && (
                    <p className="text-sm text-slate-400 mt-1">{bot.description}</p>
                  )}
                </div>
                <div
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    bot.is_active
                      ? 'bg-green-500/20 text-green-400'
                      : 'bg-slate-700 text-slate-400'
                  }`}
                >
                  {bot.is_active ? 'Active' : 'Stopped'}
                </div>
              </div>

              {/* Bot Details */}
              <div className="space-y-2 mb-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Strategy:</span>
                  <span className="text-white font-medium">
                    {strategies.find((s) => s.id === bot.strategy_type)?.name || bot.strategy_type}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Pair:</span>
                  <span className="text-white font-medium">{bot.product_id}</span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center space-x-2">
                {bot.is_active ? (
                  <button
                    onClick={() => stopBot.mutate(bot.id)}
                    className="flex-1 flex items-center justify-center space-x-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 px-3 py-2 rounded transition-colors"
                  >
                    <Square className="w-4 h-4" />
                    <span>Stop</span>
                  </button>
                ) : (
                  <button
                    onClick={() => startBot.mutate(bot.id)}
                    className="flex-1 flex items-center justify-center space-x-2 bg-green-600/20 hover:bg-green-600/30 text-green-400 px-3 py-2 rounded transition-colors"
                  >
                    <Play className="w-4 h-4" />
                    <span>Start</span>
                  </button>
                )}
                <button
                  onClick={() => handleOpenEdit(bot)}
                  className="p-2 bg-slate-700 hover:bg-slate-600 rounded transition-colors"
                  title="Edit"
                >
                  <Edit className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleDelete(bot)}
                  className="p-2 bg-slate-700 hover:bg-red-600/20 text-red-400 rounded transition-colors"
                  title="Delete"
                  disabled={bot.is_active}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-slate-700">
              <h3 className="text-xl font-bold">
                {editingBot ? 'Edit Bot' : 'Create New Bot'}
              </h3>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-6">
              {/* Bot Name */}
              <div>
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

              {/* Trading Pair */}
              <div>
                <label className="block text-sm font-medium mb-2">Trading Pair *</label>
                <select
                  value={formData.product_id}
                  onChange={(e) => setFormData({ ...formData, product_id: e.target.value })}
                  className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white"
                  required
                >
                  <optgroup label="BTC Pairs">
                    {TRADING_PAIRS.filter((p) => p.group === 'BTC Pairs').map((pair) => (
                      <option key={pair.value} value={pair.value}>
                        {pair.label}
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label="USD Pairs">
                    {TRADING_PAIRS.filter((p) => p.group === 'USD Pairs').map((pair) => (
                      <option key={pair.value} value={pair.value}>
                        {pair.label}
                      </option>
                    ))}
                  </optgroup>
                </select>
              </div>

              {/* Strategy Selection */}
              <div>
                <label className="block text-sm font-medium mb-2">Strategy *</label>
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

              {/* Dynamic Strategy Parameters */}
              {selectedStrategy && selectedStrategy.parameters.length > 0 && (
                <div className="border-t border-slate-700 pt-6">
                  <h4 className="text-lg font-semibold mb-4">Strategy Parameters</h4>
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
    </div>
  )
}

export default Bots
