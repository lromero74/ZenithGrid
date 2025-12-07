import { X } from 'lucide-react'

export interface IndicatorConfig {
  id: string
  name: string
  type: string
  enabled: boolean
  settings: Record<string, any>
  color?: string
  series?: any[]
}

interface IndicatorSettingsModalProps {
  indicator: IndicatorConfig
  onClose: () => void
  onUpdateSettings: (indicatorId: string, newSettings: Record<string, any>) => void
}

export function IndicatorSettingsModal({
  indicator,
  onClose,
  onUpdateSettings,
}: IndicatorSettingsModalProps) {
  const handleUpdate = (newSettings: Record<string, any>) => {
    onUpdateSettings(indicator.id, newSettings)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full mx-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">
            {indicator.name} Settings
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white"
          >
            <X size={24} />
          </button>
        </div>

        <div className="space-y-4">
          {indicator.type === 'sma' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Period
                </label>
                <input
                  type="number"
                  value={indicator.settings.period}
                  onChange={(e) =>
                    handleUpdate({ period: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Color
                </label>
                <input
                  type="color"
                  value={indicator.settings.color}
                  onChange={(e) => handleUpdate({ color: e.target.value })}
                  className="w-full h-10 bg-slate-700 rounded border border-slate-600"
                />
              </div>
            </>
          )}

          {indicator.type === 'ema' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Period
                </label>
                <input
                  type="number"
                  value={indicator.settings.period}
                  onChange={(e) =>
                    handleUpdate({ period: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Color
                </label>
                <input
                  type="color"
                  value={indicator.settings.color}
                  onChange={(e) => handleUpdate({ color: e.target.value })}
                  className="w-full h-10 bg-slate-700 rounded border border-slate-600"
                />
              </div>
            </>
          )}

          {indicator.type === 'rsi' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Period
                </label>
                <input
                  type="number"
                  value={indicator.settings.period}
                  onChange={(e) =>
                    handleUpdate({ period: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Overbought Level
                </label>
                <input
                  type="number"
                  value={indicator.settings.overbought}
                  onChange={(e) =>
                    handleUpdate({ overbought: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Oversold Level
                </label>
                <input
                  type="number"
                  value={indicator.settings.oversold}
                  onChange={(e) =>
                    handleUpdate({ oversold: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
            </>
          )}

          {indicator.type === 'bollinger' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Period
                </label>
                <input
                  type="number"
                  value={indicator.settings.period}
                  onChange={(e) =>
                    handleUpdate({ period: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Standard Deviation
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={indicator.settings.stdDev}
                  onChange={(e) =>
                    handleUpdate({ stdDev: parseFloat(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
            </>
          )}

          {indicator.type === 'macd' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Fast Period
                </label>
                <input
                  type="number"
                  value={indicator.settings.fastPeriod}
                  onChange={(e) =>
                    handleUpdate({ fastPeriod: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Slow Period
                </label>
                <input
                  type="number"
                  value={indicator.settings.slowPeriod}
                  onChange={(e) =>
                    handleUpdate({ slowPeriod: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Signal Period
                </label>
                <input
                  type="number"
                  value={indicator.settings.signalPeriod}
                  onChange={(e) =>
                    handleUpdate({ signalPeriod: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
            </>
          )}

          {indicator.type === 'stochastic' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  %K Period
                </label>
                <input
                  type="number"
                  value={indicator.settings.kPeriod}
                  onChange={(e) =>
                    handleUpdate({ kPeriod: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  %D Period
                </label>
                <input
                  type="number"
                  value={indicator.settings.dPeriod}
                  onChange={(e) =>
                    handleUpdate({ dPeriod: parseInt(e.target.value) })
                  }
                  className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
