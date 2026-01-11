/**
 * AI Providers Manager Component
 *
 * Manages AI provider API keys for the user's trading bots.
 * Each provider can have a user-specific key stored in the database,
 * with fallback to system-wide keys from .env
 */

import { useState, useEffect } from 'react'
import {
  Brain,
  Key,
  Check,
  X,
  Eye,
  EyeOff,
  AlertCircle,
  CheckCircle,
  Trash2,
  RefreshCw,
  ExternalLink,
} from 'lucide-react'
import { aiCredentialsApi, AIProviderStatus } from '../services/api'

// Provider color configuration
const PROVIDER_COLORS: Record<string, string> = {
  claude: 'text-orange-400',
  gemini: 'text-blue-400',
  grok: 'text-purple-400',
  groq: 'text-green-400',
  openai: 'text-cyan-400',
}

export function AIProvidersManager() {
  const [providerStatus, setProviderStatus] = useState<AIProviderStatus[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Editing state
  const [editingProvider, setEditingProvider] = useState<string | null>(null)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)

  // Fetch provider status
  const fetchStatus = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const status = await aiCredentialsApi.getStatus()
      setProviderStatus(status)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load AI provider status')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
  }, [])

  const getProviderColor = (provider: string): string => {
    return PROVIDER_COLORS[provider] || 'text-slate-400'
  }

  const handleSaveKey = async (provider: string) => {
    if (!apiKeyInput.trim()) return

    setSaving(true)
    setError(null)

    try {
      await aiCredentialsApi.save(provider, apiKeyInput.trim())
      setSaveSuccess(provider)
      setEditingProvider(null)
      setApiKeyInput('')
      setShowApiKey(false)
      await fetchStatus()

      // Clear success message after 3 seconds
      setTimeout(() => setSaveSuccess(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save API key')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteKey = async (provider: string) => {
    const providerInfo = providerStatus.find(p => p.provider === provider)
    if (!confirm(`Are you sure you want to delete your ${providerInfo?.name || provider} API key?`)) {
      return
    }

    setSaving(true)
    setError(null)

    try {
      await aiCredentialsApi.delete(provider)
      await fetchStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete API key')
    } finally {
      setSaving(false)
    }
  }

  const handleCancelEdit = () => {
    setEditingProvider(null)
    setApiKeyInput('')
    setShowApiKey(false)
  }

  if (isLoading) {
    return (
      <div className="card p-6">
        <div className="flex items-center space-x-3 mb-6">
          <Brain className="w-6 h-6 text-purple-400" />
          <h3 className="text-xl font-semibold">AI Providers</h3>
        </div>
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-6 h-6 text-slate-400 animate-spin" />
          <span className="ml-2 text-slate-400">Loading...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <Brain className="w-6 h-6 text-purple-400" />
          <h3 className="text-xl font-semibold">AI Providers</h3>
        </div>
        <button
          onClick={fetchStatus}
          className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
          title="Refresh status"
        >
          <RefreshCw className="w-4 h-4 text-slate-400" />
        </button>
      </div>

      <p className="text-sm text-slate-400 mb-6">
        Configure your AI provider API keys for AI-powered trading bots. Your keys are stored
        securely and used exclusively by your bots. <strong>You must configure your own API key
        to use AI trading strategies.</strong> System-wide keys are only used for coin
        categorization and are not available as fallbacks for user bots.
      </p>

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-4 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {/* Success Message */}
      {saveSuccess && (
        <div className="mb-4 p-4 bg-green-500/10 border border-green-500/50 rounded-lg flex items-center space-x-3">
          <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
          <p className="text-green-400 text-sm">
            API key saved successfully for {providerStatus.find(p => p.provider === saveSuccess)?.name || saveSuccess}!
          </p>
        </div>
      )}

      {/* Provider List */}
      <div className="space-y-4">
        {providerStatus.map((info) => {
          const isEditing = editingProvider === info.provider

          return (
            <div
              key={info.provider}
              className="p-4 bg-slate-700/50 rounded-lg border border-slate-600/50"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <Key className={`w-5 h-5 ${getProviderColor(info.provider)}`} />
                  <div>
                    <div className="flex items-center space-x-2">
                      <h4 className="font-medium text-white">{info.name}</h4>
                      {info.billing_url && (
                        <a
                          href={info.billing_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-slate-400 hover:text-blue-400 transition-colors"
                          title="Get API key"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </div>
                    {info.free_tier && (
                      <p className="text-xs text-green-400">Free tier: {info.free_tier}</p>
                    )}
                  </div>
                </div>

                <div className="flex items-center space-x-3">
                  {/* Status badges */}
                  <div className="flex items-center space-x-2">
                    {info.has_user_key && (
                      <span className="px-2 py-1 text-xs bg-green-600/20 text-green-400 rounded-full">
                        Your Key
                      </span>
                    )}
                    {info.has_system_key && !info.has_user_key && (
                      <span className="px-2 py-1 text-xs bg-blue-600/20 text-blue-400 rounded-full">
                        System Key
                      </span>
                    )}
                    {!info.has_user_key && !info.has_system_key && (
                      <span className="px-2 py-1 text-xs bg-slate-600/50 text-slate-400 rounded-full">
                        Not Configured
                      </span>
                    )}
                  </div>

                  {/* Key preview */}
                  {info.key_preview && (
                    <span className="text-xs text-slate-500 font-mono">...{info.key_preview}</span>
                  )}

                  {/* Action buttons */}
                  {!isEditing && (
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => {
                          setEditingProvider(info.provider)
                          setApiKeyInput('')
                        }}
                        className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
                      >
                        {info.has_user_key ? 'Update' : 'Add Key'}
                      </button>
                      {info.has_user_key && (
                        <button
                          onClick={() => handleDeleteKey(info.provider)}
                          disabled={saving}
                          className="p-1.5 text-red-400 hover:text-red-300 hover:bg-red-500/20 rounded-lg transition-colors"
                          title="Delete your API key"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Edit form */}
              {isEditing && (
                <div className="mt-4 pt-4 border-t border-slate-600/50">
                  <div className="flex items-center space-x-3">
                    <div className="flex-1 relative">
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        value={apiKeyInput}
                        onChange={(e) => setApiKeyInput(e.target.value)}
                        placeholder={`Enter your ${info.name} API key`}
                        className="w-full px-4 py-2 pr-10 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
                        autoComplete="off"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-300"
                      >
                        {showApiKey ? (
                          <EyeOff className="w-4 h-4" />
                        ) : (
                          <Eye className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                    <button
                      onClick={() => handleSaveKey(info.provider)}
                      disabled={saving || !apiKeyInput.trim()}
                      className="p-2 bg-green-600 hover:bg-green-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
                      title="Save"
                    >
                      {saving ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Check className="w-4 h-4" />
                      )}
                    </button>
                    <button
                      onClick={handleCancelEdit}
                      disabled={saving}
                      className="p-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg transition-colors"
                      title="Cancel"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <p className="mt-2 text-xs text-slate-400">
                    Your API key will be stored securely and used for AI analysis in your trading
                    bots.
                  </p>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Info section */}
      <div className="mt-6 p-4 bg-slate-700/30 rounded-lg border border-slate-600/30">
        <h4 className="text-sm font-medium text-slate-300 mb-2">How it works</h4>
        <ul className="text-xs text-slate-400 space-y-1">
          <li>
            <span className="text-green-400">Your Key</span> - Your personal API key, required for
            AI trading bots
          </li>
          <li>
            <span className="text-blue-400">System Key</span> - System-wide key for coin
            categorization only (not available for your bots)
          </li>
          <li>
            <span className="text-slate-400">Not Configured</span> - No key set, you cannot use
            this provider for AI trading
          </li>
        </ul>
      </div>
    </div>
  )
}
