/**
 * Indicator Modals for DealChart
 *
 * Modal components for adding and configuring chart indicators.
 */

import { Search, X } from 'lucide-react'
import { AVAILABLE_INDICATORS } from '../../utils/indicators'
import type { IndicatorConfig } from './positionUtils'

interface AddIndicatorModalProps {
  isOpen: boolean
  onClose: () => void
  onAddIndicator: (indicatorType: string) => void
  indicatorSearch: string
  onSearchChange: (value: string) => void
}

export function AddIndicatorModal({
  isOpen,
  onClose,
  onAddIndicator,
  indicatorSearch,
  onSearchChange,
}: AddIndicatorModalProps) {
  if (!isOpen) return null

  const filteredIndicators = AVAILABLE_INDICATORS.filter(ind =>
    ind.name.toLowerCase().includes(indicatorSearch.toLowerCase()) ||
    ind.category.toLowerCase().includes(indicatorSearch.toLowerCase())
  )

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-slate-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Add Indicator</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white"
          >
            <X size={24} />
          </button>
        </div>

        {/* Search */}
        <div className="mb-4 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" size={20} />
          <input
            type="text"
            placeholder="Search indicators..."
            value={indicatorSearch}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full bg-slate-700 text-white pl-10 pr-4 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Indicator List */}
        <div className="space-y-2">
          {Object.entries(
            filteredIndicators.reduce((acc, ind) => {
              if (!acc[ind.category]) acc[ind.category] = []
              acc[ind.category].push(ind)
              return acc
            }, {} as Record<string, typeof AVAILABLE_INDICATORS>)
          ).map(([category, categoryIndicators]) => (
            <div key={category}>
              <div className="text-xs font-semibold text-slate-400 mb-2 mt-4 first:mt-0">
                {category}
              </div>
              {categoryIndicators.map((indicator) => (
                <button
                  key={indicator.id}
                  onClick={() => onAddIndicator(indicator.id)}
                  className="w-full text-left bg-slate-700 hover:bg-slate-600 text-white px-2 sm:px-4 py-2 sm:py-3 rounded transition-colors"
                >
                  {indicator.name}
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

interface IndicatorSettingsModalProps {
  indicator: IndicatorConfig | null
  onClose: () => void
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onUpdateSettings: (indicatorId: string, newSettings: Record<string, any>) => void
}

export function IndicatorSettingsModal({
  indicator,
  onClose,
  onUpdateSettings,
}: IndicatorSettingsModalProps) {
  if (!indicator) return null

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
                  value={indicator.settings.period as number}
                  onChange={(e) =>
                    onUpdateSettings(indicator.id, {
                      period: parseInt(e.target.value),
                    })
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
                  value={indicator.settings.color as string}
                  onChange={(e) =>
                    onUpdateSettings(indicator.id, {
                      color: e.target.value,
                    })
                  }
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
                  value={indicator.settings.period as number}
                  onChange={(e) =>
                    onUpdateSettings(indicator.id, {
                      period: parseInt(e.target.value),
                    })
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
                  value={indicator.settings.color as string}
                  onChange={(e) =>
                    onUpdateSettings(indicator.id, {
                      color: e.target.value,
                    })
                  }
                  className="w-full h-10 bg-slate-700 rounded border border-slate-600"
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
                  value={indicator.settings.period as number}
                  onChange={(e) =>
                    onUpdateSettings(indicator.id, {
                      period: parseInt(e.target.value),
                    })
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
                  value={indicator.settings.stdDev as number}
                  onChange={(e) =>
                    onUpdateSettings(indicator.id, {
                      stdDev: parseFloat(e.target.value),
                    })
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
