import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Layers, X, Settings, TrendingUp, Activity, BarChart3, Info } from 'lucide-react'
import axios from 'axios'
import { API_BASE_URL } from '../config/api'
import { LoadingSpinner } from '../components/LoadingSpinner'

interface StrategyParameter {
  name: string
  display_name: string
  description: string
  type: string
  default: any
  min_value?: number
  max_value?: number
  options?: string[]
}

interface StrategyDefinition {
  id: string
  name: string
  description: string
  parameters: StrategyParameter[]
  supported_products: string[]
}

export default function Strategies() {
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyDefinition | null>(null)
  const [showDetailsModal, setShowDetailsModal] = useState(false)
  const [customConfig, setCustomConfig] = useState<Record<string, any>>({})

  // Fetch available strategies
  const { data: strategies, isLoading } = useQuery<StrategyDefinition[]>({
    queryKey: ['strategies'],
    queryFn: async () => {
      const response = await axios.get(`${API_BASE_URL}/api/bots/strategies`)
      return response.data
    }
  })

  const handleViewStrategy = (strategy: StrategyDefinition) => {
    setSelectedStrategy(strategy)
    // Initialize config with defaults
    const config: Record<string, any> = {}
    strategy.parameters.forEach(param => {
      config[param.name] = param.default
    })
    setCustomConfig(config)
    setShowDetailsModal(true)
  }

  const handleParamChange = (paramName: string, value: any) => {
    setCustomConfig(prev => ({
      ...prev,
      [paramName]: value
    }))
  }

  const renderParameterInput = (param: StrategyParameter) => {
    const value = customConfig[param.name] ?? param.default

    if (param.type === 'bool') {
      return (
        <div className="flex items-center">
          <input
            type="checkbox"
            checked={value}
            onChange={(e) => handleParamChange(param.name, e.target.checked)}
            className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-2 focus:ring-blue-500"
          />
        </div>
      )
    }

    if (param.options && param.options.length > 0) {
      return (
        <select
          value={String(value)}
          onChange={(e) => handleParamChange(param.name, e.target.value)}
          className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
        >
          {param.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt.replace(/_/g, ' ')}
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
        className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-white focus:ring-2 focus:ring-blue-500"
      />
    )
  }

  const getStrategyIcon = (strategyId: string) => {
    switch (strategyId) {
      case 'macd_dca':
        return <Activity className="w-6 h-6 text-blue-400" />
      case 'rsi':
        return <TrendingUp className="w-6 h-6 text-purple-400" />
      case 'bollinger_bands':
        return <BarChart3 className="w-6 h-6 text-green-400" />
      case 'simple_dca':
        return <Layers className="w-6 h-6 text-yellow-400" />
      case 'advanced_dca':
        return <Layers className="w-6 h-6 text-red-400" />
      default:
        return <Layers className="w-6 h-6 text-slate-400" />
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" text="Loading strategies..." />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold mb-2">Strategy Library</h2>
        <p className="text-slate-400">
          Explore and configure trading strategies. Use these as templates when creating new bots.
        </p>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-950/30 border border-blue-500/30 rounded-lg p-4">
        <div className="flex items-start space-x-3">
          <Info className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-slate-300">
            <p className="font-semibold mb-1">About Strategies</p>
            <p>
              Each strategy has configurable parameters that control its behavior. When creating a bot,
              select a strategy and customize its parameters to match your trading goals. You can create
              multiple bots using the same strategy with different configurations.
            </p>
          </div>
        </div>
      </div>

      {/* Strategy Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {strategies?.map((strategy) => (
          <div
            key={strategy.id}
            className="bg-slate-800 rounded-lg border border-slate-700 hover:border-slate-600 transition-colors overflow-hidden"
          >
            {/* Strategy Header */}
            <div className="p-6 border-b border-slate-700">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center space-x-3">
                  {getStrategyIcon(strategy.id)}
                  <div>
                    <h3 className="text-lg font-semibold">{strategy.name}</h3>
                    <p className="text-xs text-slate-400 mt-0.5">ID: {strategy.id}</p>
                  </div>
                </div>
              </div>
              <p className="text-sm text-slate-300">{strategy.description}</p>
            </div>

            {/* Strategy Info */}
            <div className="p-6 space-y-3">
              <div>
                <p className="text-xs font-semibold text-slate-400 mb-1">Parameters</p>
                <p className="text-sm text-white">{strategy.parameters.length} configurable options</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-400 mb-1">Supported Pairs</p>
                <div className="flex flex-wrap gap-1">
                  {strategy.supported_products.slice(0, 3).map((product) => (
                    <span
                      key={product}
                      className="text-xs bg-slate-700 px-2 py-0.5 rounded"
                    >
                      {product}
                    </span>
                  ))}
                  {strategy.supported_products.length > 3 && (
                    <span className="text-xs text-slate-400">
                      +{strategy.supported_products.length - 3} more
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="p-6 pt-0">
              <button
                onClick={() => handleViewStrategy(strategy)}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded font-medium transition-colors flex items-center justify-center space-x-2"
              >
                <Settings className="w-4 h-4" />
                <span>View Configuration</span>
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Strategy Details Modal */}
      {showDetailsModal && selectedStrategy && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            {/* Modal Header */}
            <div className="p-6 border-b border-slate-700 flex items-center justify-between">
              <div className="flex items-center space-x-3">
                {getStrategyIcon(selectedStrategy.id)}
                <div>
                  <h2 className="text-2xl font-bold">{selectedStrategy.name}</h2>
                  <p className="text-sm text-slate-400">{selectedStrategy.description}</p>
                </div>
              </div>
              <button
                onClick={() => setShowDetailsModal(false)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X size={24} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto flex-1">
              <div className="space-y-6">
                {/* Supported Products */}
                <div>
                  <h3 className="text-lg font-semibold mb-3">Supported Trading Pairs</h3>
                  <div className="flex flex-wrap gap-2">
                    {selectedStrategy.supported_products.map((product) => (
                      <span
                        key={product}
                        className="bg-slate-700 px-3 py-1.5 rounded text-sm font-medium"
                      >
                        {product}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Parameters */}
                <div>
                  <h3 className="text-lg font-semibold mb-3">Configuration Parameters</h3>
                  <div className="space-y-4">
                    {selectedStrategy.parameters.map((param) => (
                      <div
                        key={param.name}
                        className="bg-slate-700/50 rounded-lg p-4 border border-slate-600"
                      >
                        <div className="mb-2">
                          <label className="block font-medium text-white mb-1">
                            {param.display_name}
                          </label>
                          <p className="text-sm text-slate-400">{param.description}</p>
                          <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                            <span>Type: {param.type}</span>
                            {param.min_value !== undefined && (
                              <span>Min: {param.min_value}</span>
                            )}
                            {param.max_value !== undefined && (
                              <span>Max: {param.max_value}</span>
                            )}
                            <span>Default: {String(param.default)}</span>
                          </div>
                        </div>
                        {renderParameterInput(param)}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Info Box */}
                <div className="bg-blue-950/30 border border-blue-500/30 rounded-lg p-4">
                  <div className="flex items-start space-x-3">
                    <Info className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
                    <div className="text-sm text-slate-300">
                      <p className="font-semibold mb-1">Using This Strategy</p>
                      <p>
                        To use this strategy configuration, go to the <strong>Bots</strong> page and
                        create a new bot. Select "{selectedStrategy.name}" as the strategy and
                        customize the parameters as shown above.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-6 border-t border-slate-700 flex justify-end">
              <button
                onClick={() => setShowDetailsModal(false)}
                className="bg-slate-700 hover:bg-slate-600 text-white px-6 py-2 rounded font-medium transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
