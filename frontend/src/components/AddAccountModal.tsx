/**
 * Add Account Modal
 *
 * Modal for adding new CEX (Coinbase, ByBit, MT5 Bridge) or DEX accounts.
 * Collects appropriate credentials based on account type and exchange.
 * Supports prop firm configuration for ByBit (HyroTrader) and MT5 (FTMO).
 */

import { useEffect, useState } from 'react'
import { X, Building2, Wallet, Eye, EyeOff, AlertCircle, Shield } from 'lucide-react'
import { useAccount, CreateAccountDto, SUPPORTED_CHAINS } from '../contexts/AccountContext'

interface AddAccountModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess?: () => void
}

type AccountFormType = 'cex' | 'dex'

interface FormData {
  // Common
  name: string
  type: AccountFormType

  // CEX fields
  exchange: string
  api_key_name: string
  api_private_key: string

  // DEX fields
  chain_id: number
  wallet_address: string
  wallet_private_key: string
  rpc_url: string
  wallet_type: string

  // ByBit-specific
  bybit_testnet: boolean

  // MT5 Bridge-specific
  mt5_bridge_url: string
  mt5_magic_number: string

  // Prop firm fields
  prop_firm: string
  prop_daily_drawdown_pct: string
  prop_total_drawdown_pct: string
  prop_initial_deposit: string

  // Flags
  is_default: boolean
}

const initialFormData: FormData = {
  name: '',
  type: 'cex',
  exchange: 'coinbase',
  api_key_name: '',
  api_private_key: '',
  chain_id: 1,
  wallet_address: '',
  wallet_private_key: '',
  rpc_url: '',
  wallet_type: 'metamask',
  bybit_testnet: false,
  mt5_bridge_url: '',
  mt5_magic_number: '12345',
  prop_firm: '',
  prop_daily_drawdown_pct: '4.5',
  prop_total_drawdown_pct: '9.0',
  prop_initial_deposit: '100000',
  is_default: false,
}


export function AddAccountModal({ isOpen, onClose, onSuccess }: AddAccountModalProps) {
  const { addAccount, accounts } = useAccount()
  const [formData, setFormData] = useState<FormData>(initialFormData)
  const [showPrivateKey, setShowPrivateKey] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      const accountData: CreateAccountDto = {
        name: formData.name,
        type: formData.type,
        is_default: formData.is_default || accounts.length === 0,
      }

      if (formData.type === 'cex') {
        accountData.exchange = formData.exchange

        if (formData.exchange === 'bybit') {
          accountData.api_key_name = formData.api_key_name
          accountData.api_private_key = formData.api_private_key
          // Only set prop firm if user selected one (ByBit can be standalone)
          if (formData.prop_firm) {
            accountData.prop_firm = formData.prop_firm
          }
          accountData.prop_firm_config = {
            testnet: formData.bybit_testnet,
          }
        } else if (formData.exchange === 'mt5_bridge') {
          accountData.prop_firm = 'ftmo'
          accountData.prop_firm_config = {
            bridge_url: formData.mt5_bridge_url,
            magic_number: parseInt(formData.mt5_magic_number) || 12345,
          }
        } else {
          accountData.api_key_name = formData.api_key_name
          accountData.api_private_key = formData.api_private_key
        }

        // Prop firm drawdown settings (only when a prop firm is selected)
        if (formData.prop_firm || formData.exchange === 'mt5_bridge') {
          accountData.prop_daily_drawdown_pct = parseFloat(formData.prop_daily_drawdown_pct) || 4.5
          accountData.prop_total_drawdown_pct = parseFloat(formData.prop_total_drawdown_pct) || 9.0
          accountData.prop_initial_deposit = parseFloat(formData.prop_initial_deposit) || 100000
        }
      } else {
        accountData.chain_id = formData.chain_id
        accountData.wallet_address = formData.wallet_address
        accountData.wallet_private_key = formData.wallet_private_key || undefined
        accountData.rpc_url = formData.rpc_url || undefined
        accountData.wallet_type = formData.wallet_type
      }

      await addAccount(accountData)
      setFormData(initialFormData)
      onSuccess?.()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create account')
    } finally {
      setIsSubmitting(false)
    }
  }

  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-800 rounded-lg w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-700">
          <h2 className="text-xl font-bold text-white">Add Account</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Account Type Selection */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-3">
              Account Type
            </label>
            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => setFormData({ ...formData, type: 'cex' })}
                className={`flex flex-col items-center p-4 rounded-lg border-2 transition-all ${
                  formData.type === 'cex'
                    ? 'border-blue-500 bg-blue-500/10'
                    : 'border-slate-600 hover:border-slate-500'
                }`}
              >
                <Building2 className={`w-8 h-8 mb-2 ${
                  formData.type === 'cex' ? 'text-blue-400' : 'text-slate-400'
                }`} />
                <span className="font-medium text-white">CEX</span>
                <span className="text-xs text-slate-400 mt-1">Coinbase / ByBit / MT5</span>
              </button>
              <button
                type="button"
                onClick={() => setFormData({ ...formData, type: 'dex' })}
                className={`flex flex-col items-center p-4 rounded-lg border-2 transition-all ${
                  formData.type === 'dex'
                    ? 'border-orange-500 bg-orange-500/10'
                    : 'border-slate-600 hover:border-slate-500'
                }`}
              >
                <Wallet className={`w-8 h-8 mb-2 ${
                  formData.type === 'dex' ? 'text-orange-400' : 'text-slate-400'
                }`} />
                <span className="font-medium text-white">DEX</span>
                <span className="text-xs text-slate-400 mt-1">MetaMask / Wallet</span>
              </button>
            </div>
          </div>

          {/* Account Name */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Account Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder={
                formData.exchange === 'bybit' ? 'My ByBit Account' :
                formData.exchange === 'mt5_bridge' ? 'My FTMO Account' :
                formData.type === 'cex' ? 'My Coinbase Account' : 'My MetaMask Wallet'
              }
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none"
              required
            />
          </div>

          {/* CEX-specific fields */}
          {formData.type === 'cex' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Exchange
                </label>
                <select
                  value={formData.exchange}
                  onChange={(e) => setFormData({ ...formData, exchange: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                >
                  <option value="coinbase">Coinbase</option>
                  <option value="bybit">ByBit (HyroTrader)</option>
                  <option value="mt5_bridge">MT5 Bridge (FTMO)</option>
                </select>
              </div>

              {/* Coinbase / ByBit: API Key fields */}
              {(formData.exchange === 'coinbase' || formData.exchange === 'bybit') && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">
                      {formData.exchange === 'bybit' ? 'API Key' : 'API Key Name'} *
                    </label>
                    <input
                      type="text"
                      value={formData.api_key_name}
                      onChange={(e) => setFormData({ ...formData, api_key_name: e.target.value })}
                      placeholder={formData.exchange === 'bybit' ? 'ByBit API key' : 'organizations/xxx/apiKeys/xxx'}
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none font-mono text-sm"
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">
                      {formData.exchange === 'bybit' ? 'API Secret' : 'API Private Key'} *
                    </label>
                    <div className="relative">
                      <textarea
                        value={formData.api_private_key}
                        onChange={(e) => setFormData({ ...formData, api_private_key: e.target.value })}
                        placeholder={formData.exchange === 'bybit' ? 'ByBit API secret' : '-----BEGIN EC PRIVATE KEY-----'}
                        rows={formData.exchange === 'bybit' ? 2 : 4}
                        className={`w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none font-mono text-xs ${
                          !showPrivateKey ? 'text-security-disc' : ''
                        }`}
                        style={{ WebkitTextSecurity: showPrivateKey ? 'none' : 'disc' } as React.CSSProperties}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPrivateKey(!showPrivateKey)}
                        className="absolute right-2 top-2 p-1 hover:bg-slate-600 rounded"
                      >
                        {showPrivateKey ? (
                          <EyeOff className="w-4 h-4 text-slate-400" />
                        ) : (
                          <Eye className="w-4 h-4 text-slate-400" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* ByBit testnet toggle */}
                  {formData.exchange === 'bybit' && (
                    <>
                      <label className="flex items-center space-x-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.bybit_testnet}
                          onChange={(e) => setFormData({ ...formData, bybit_testnet: e.target.checked })}
                          className="rounded border-slate-600 bg-slate-700 text-blue-500 focus:ring-blue-500"
                        />
                        <span className="text-sm text-slate-300">Use ByBit Testnet</span>
                      </label>

                      <div>
                        <label className="block text-sm font-medium text-slate-300 mb-2">
                          Prop Firm (optional)
                        </label>
                        <select
                          value={formData.prop_firm}
                          onChange={(e) => setFormData({ ...formData, prop_firm: e.target.value })}
                          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-blue-500 focus:outline-none text-sm"
                        >
                          <option value="">None (standalone ByBit)</option>
                          <option value="hyrotrader">HyroTrader</option>
                        </select>
                      </div>
                    </>
                  )}
                </>
              )}

              {/* MT5 Bridge fields */}
              {formData.exchange === 'mt5_bridge' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">
                      Bridge URL *
                    </label>
                    <input
                      type="text"
                      value={formData.mt5_bridge_url}
                      onChange={(e) => setFormData({ ...formData, mt5_bridge_url: e.target.value })}
                      placeholder="http://your-vps-ip:8080"
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none font-mono text-sm"
                      required
                    />
                    <p className="mt-1 text-xs text-slate-400">
                      URL of your MT5 EA bridge running on a Windows VPS
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">
                      Magic Number
                    </label>
                    <input
                      type="number"
                      value={formData.mt5_magic_number}
                      onChange={(e) => setFormData({ ...formData, mt5_magic_number: e.target.value })}
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                    />
                    <p className="mt-1 text-xs text-slate-400">
                      MT5 magic number to identify orders from this bot
                    </p>
                  </div>
                </>
              )}

              {/* PropGuard Settings (shown when prop firm selected or MT5) */}
              {(formData.prop_firm || formData.exchange === 'mt5_bridge') && (
                <div className="border border-amber-700/50 rounded-lg p-4 bg-amber-900/10">
                  <div className="flex items-center gap-2 mb-3">
                    <Shield className="w-5 h-5 text-amber-400" />
                    <h3 className="text-sm font-semibold text-amber-300">PropGuard Safety Settings</h3>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Initial Deposit (USD)
                      </label>
                      <input
                        type="number"
                        step="1000"
                        min="1"
                        max="100000000"
                        value={formData.prop_initial_deposit}
                        onChange={(e) => setFormData({ ...formData, prop_initial_deposit: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-amber-500 focus:outline-none text-sm"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">
                          Daily Drawdown Limit (%)
                        </label>
                        <input
                          type="number"
                          step="0.5"
                          min="0.1"
                          max="100"
                          value={formData.prop_daily_drawdown_pct}
                          onChange={(e) => setFormData({ ...formData, prop_daily_drawdown_pct: e.target.value })}
                          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-amber-500 focus:outline-none text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">
                          Total Drawdown Limit (%)
                        </label>
                        <input
                          type="number"
                          step="0.5"
                          min="0.1"
                          max="100"
                          value={formData.prop_total_drawdown_pct}
                          onChange={(e) => setFormData({ ...formData, prop_total_drawdown_pct: e.target.value })}
                          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-amber-500 focus:outline-none text-sm"
                        />
                      </div>
                    </div>

                    <p className="text-xs text-amber-400/70">
                      PropGuard will automatically close all positions and block new orders if drawdown limits are breached.
                    </p>
                  </div>
                </div>
              )}
            </>
          )}

          {/* DEX-specific fields */}
          {formData.type === 'dex' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Blockchain Network *
                </label>
                <select
                  value={formData.chain_id}
                  onChange={(e) => {
                    const chain = SUPPORTED_CHAINS.find(c => c.id === parseInt(e.target.value))
                    setFormData({
                      ...formData,
                      chain_id: parseInt(e.target.value),
                      rpc_url: chain?.rpcUrl || '',
                    })
                  }}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                >
                  {SUPPORTED_CHAINS.map((chain) => (
                    <option key={chain.id} value={chain.id}>
                      {chain.name} ({chain.symbol})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Wallet Address *
                </label>
                <input
                  type="text"
                  value={formData.wallet_address}
                  onChange={(e) => setFormData({ ...formData, wallet_address: e.target.value })}
                  placeholder="0x..."
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none font-mono text-sm"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Wallet Type
                </label>
                <select
                  value={formData.wallet_type}
                  onChange={(e) => setFormData({ ...formData, wallet_type: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                >
                  <option value="metamask">MetaMask</option>
                  <option value="walletconnect">WalletConnect</option>
                  <option value="private_key">Private Key</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Private Key <span className="text-slate-400">(Optional - for auto-signing)</span>
                </label>
                <div className="relative">
                  <input
                    type={showPrivateKey ? 'text' : 'password'}
                    value={formData.wallet_private_key}
                    onChange={(e) => setFormData({ ...formData, wallet_private_key: e.target.value })}
                    placeholder="0x..."
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none font-mono text-sm pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPrivateKey(!showPrivateKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-slate-600 rounded"
                  >
                    {showPrivateKey ? (
                      <EyeOff className="w-4 h-4 text-slate-400" />
                    ) : (
                      <Eye className="w-4 h-4 text-slate-400" />
                    )}
                  </button>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  Leave empty to manually approve transactions in your wallet
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Custom RPC URL <span className="text-slate-400">(Optional)</span>
                </label>
                <input
                  type="text"
                  value={formData.rpc_url}
                  onChange={(e) => setFormData({ ...formData, rpc_url: e.target.value })}
                  placeholder="https://mainnet.infura.io/v3/YOUR_KEY"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none font-mono text-sm"
                />
              </div>
            </>
          )}

          {/* Set as Default */}
          <label className="flex items-center space-x-3 cursor-pointer">
            <input
              type="checkbox"
              checked={formData.is_default}
              onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
              className="rounded border-slate-600 bg-slate-700 text-blue-500 focus:ring-blue-500"
            />
            <span className="text-sm text-slate-300">Set as default account</span>
          </label>

          {/* Error Message */}
          {error && (
            <div className="flex items-start space-x-2 p-3 bg-red-900/20 border border-red-700 rounded-lg">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-300">{error}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-700">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-slate-300 hover:bg-slate-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? 'Adding...' : 'Add Account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddAccountModal
