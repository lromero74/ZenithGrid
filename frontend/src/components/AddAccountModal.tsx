/**
 * Add Account Modal
 *
 * Modal for adding new CEX (Coinbase) or DEX (MetaMask) accounts.
 * Collects appropriate credentials based on account type.
 */

import { useState } from 'react'
import { X, Building2, Wallet, Eye, EyeOff, AlertCircle } from 'lucide-react'
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

  // Flags
  is_default: boolean
}

const initialFormData: FormData = {
  name: '',
  type: 'cex',
  exchange: 'coinbase',
  api_key_name: '',
  api_private_key: '',
  chain_id: 1, // Ethereum mainnet
  wallet_address: '',
  wallet_private_key: '',
  rpc_url: '',
  wallet_type: 'metamask',
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
        is_default: formData.is_default || accounts.length === 0, // First account is default
      }

      if (formData.type === 'cex') {
        accountData.exchange = formData.exchange
        accountData.api_key_name = formData.api_key_name
        accountData.api_private_key = formData.api_private_key
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
                <span className="text-xs text-slate-400 mt-1">Coinbase</span>
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
              placeholder={formData.type === 'cex' ? 'My Coinbase Account' : 'My MetaMask Wallet'}
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
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  API Key Name *
                </label>
                <input
                  type="text"
                  value={formData.api_key_name}
                  onChange={(e) => setFormData({ ...formData, api_key_name: e.target.value })}
                  placeholder="organizations/xxx/apiKeys/xxx"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:border-blue-500 focus:outline-none font-mono text-sm"
                  required
                />
                <p className="mt-1 text-xs text-slate-400">
                  From Coinbase CDP API Key settings
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  API Private Key *
                </label>
                <div className="relative">
                  <textarea
                    value={formData.api_private_key}
                    onChange={(e) => setFormData({ ...formData, api_private_key: e.target.value })}
                    placeholder="-----BEGIN EC PRIVATE KEY-----"
                    rows={4}
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
                <p className="mt-1 text-xs text-slate-400">
                  Private key from CDP API Key download
                </p>
              </div>
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
