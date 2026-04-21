/**
 * AI Cost Dashboard
 *
 * Shows the current user's AI usage and spend over a selectable window
 * (7 / 30 / 90 days). Aggregates the per-call audit rows from
 * `ai_opinion_log` into totals and breakdowns by provider and model.
 */

import { useState, useEffect, useCallback } from 'react'
import { Brain, RefreshCw, AlertCircle, DollarSign, Activity, Hash } from 'lucide-react'
import { aiCostApi, AICostSummary } from '../../services/api'

const WINDOW_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 7, label: '7 days' },
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
]

const PROVIDER_COLORS: Record<string, string> = {
  claude: 'text-orange-400',
  gemini: 'text-blue-400',
  grok: 'text-purple-400',
  groq: 'text-green-400',
  gpt: 'text-cyan-400',
  openai: 'text-cyan-400',
}

function formatCost(usd: number): string {
  if (usd === 0) return '$0.00'
  if (usd < 0.01) return `$${usd.toFixed(6)}`
  if (usd < 1) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(2)}`
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return `${n}`
}

export function AICostDashboard() {
  const [days, setDays] = useState(7)
  const [summary, setSummary] = useState<AICostSummary | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchSummary = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await aiCostApi.getSummary(days)
      setSummary(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cost summary')
    } finally {
      setIsLoading(false)
    }
  }, [days])

  useEffect(() => {
    fetchSummary()
  }, [fetchSummary])

  const providerColor = (provider: string) =>
    PROVIDER_COLORS[provider] || 'text-slate-300'

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          <Brain className="w-6 h-6 text-purple-400" />
          <h3 className="text-xl font-semibold">AI Usage & Cost</h3>
        </div>
        <div className="flex items-center space-x-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {WINDOW_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button
            onClick={fetchSummary}
            disabled={isLoading}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 text-slate-400 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <p className="text-sm text-slate-400 mb-6">
        Token usage and cost for AI calls made by your bots over the selected window.
        Legacy rows from before per-call tracking appear under model <em>(legacy)</em>.
      </p>

      {error && (
        <div className="mb-4 p-4 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {isLoading && !summary && (
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-6 h-6 text-slate-400 animate-spin" />
          <span className="ml-2 text-slate-400">Loading...</span>
        </div>
      )}

      {summary && (
        <>
          {/* Totals */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            <div className="p-4 bg-slate-700/50 rounded-lg border border-slate-600/50">
              <div className="flex items-center space-x-2 mb-1">
                <Activity className="w-4 h-4 text-slate-400" />
                <span className="text-xs text-slate-400 uppercase tracking-wider">Calls</span>
              </div>
              <div className="text-2xl font-semibold text-white">
                {summary.total_calls.toLocaleString()}
              </div>
            </div>
            <div className="p-4 bg-slate-700/50 rounded-lg border border-slate-600/50">
              <div className="flex items-center space-x-2 mb-1">
                <Hash className="w-4 h-4 text-slate-400" />
                <span className="text-xs text-slate-400 uppercase tracking-wider">Tokens (in / out)</span>
              </div>
              <div className="text-2xl font-semibold text-white">
                {formatTokens(summary.total_input_tokens)}
                <span className="text-slate-500 text-lg"> / </span>
                {formatTokens(summary.total_output_tokens)}
              </div>
            </div>
            <div className="p-4 bg-slate-700/50 rounded-lg border border-slate-600/50">
              <div className="flex items-center space-x-2 mb-1">
                <DollarSign className="w-4 h-4 text-green-400" />
                <span className="text-xs text-slate-400 uppercase tracking-wider">Total cost</span>
              </div>
              <div className="text-2xl font-semibold text-green-400">
                {formatCost(summary.total_cost_usd)}
              </div>
            </div>
          </div>

          {/* By provider */}
          <div className="mb-6">
            <h4 className="text-sm font-medium text-slate-300 mb-2">By provider</h4>
            {summary.by_provider.length === 0 ? (
              <p className="text-sm text-slate-500 italic">No AI activity in this window.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-400 border-b border-slate-700">
                      <th className="py-2 pr-4 font-medium">Provider</th>
                      <th className="py-2 pr-4 font-medium text-right">Calls</th>
                      <th className="py-2 pr-4 font-medium text-right">Input</th>
                      <th className="py-2 pr-4 font-medium text-right">Output</th>
                      <th className="py-2 font-medium text-right">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.by_provider.map((row) => (
                      <tr key={row.provider} className="border-b border-slate-800 last:border-0">
                        <td className={`py-2 pr-4 font-medium ${providerColor(row.provider)}`}>
                          {row.provider}
                        </td>
                        <td className="py-2 pr-4 text-right text-white">{row.calls}</td>
                        <td className="py-2 pr-4 text-right text-slate-300">{formatTokens(row.input_tokens)}</td>
                        <td className="py-2 pr-4 text-right text-slate-300">{formatTokens(row.output_tokens)}</td>
                        <td className="py-2 text-right text-green-400">{formatCost(row.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* By model */}
          <div>
            <h4 className="text-sm font-medium text-slate-300 mb-2">By model</h4>
            {summary.by_model.length === 0 ? (
              <p className="text-sm text-slate-500 italic">No model-level detail available.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-400 border-b border-slate-700">
                      <th className="py-2 pr-4 font-medium">Provider</th>
                      <th className="py-2 pr-4 font-medium">Model</th>
                      <th className="py-2 pr-4 font-medium text-right">Calls</th>
                      <th className="py-2 pr-4 font-medium text-right">Input</th>
                      <th className="py-2 pr-4 font-medium text-right">Output</th>
                      <th className="py-2 font-medium text-right">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.by_model.map((row) => (
                      <tr
                        key={`${row.provider}:${row.model_used}`}
                        className="border-b border-slate-800 last:border-0"
                      >
                        <td className={`py-2 pr-4 font-medium ${providerColor(row.provider)}`}>
                          {row.provider}
                        </td>
                        <td className="py-2 pr-4 text-slate-200 font-mono text-xs">{row.model_used}</td>
                        <td className="py-2 pr-4 text-right text-white">{row.calls}</td>
                        <td className="py-2 pr-4 text-right text-slate-300">{formatTokens(row.input_tokens)}</td>
                        <td className="py-2 pr-4 text-right text-slate-300">{formatTokens(row.output_tokens)}</td>
                        <td className="py-2 text-right text-green-400">{formatCost(row.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
