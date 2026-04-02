/**
 * DEX Configuration Section Component
 *
 * Provides UI for configuring DEX-specific bot settings:
 * - Exchange type selector (CEX/DEX)
 * - Blockchain selection (Ethereum, BSC, Polygon, Arbitrum)
 * - DEX router selection (Uniswap V3, PancakeSwap, SushiSwap)
 * - Wallet private key input
 * - RPC URL configuration
 *
 * Separation of concerns: Keeps DEX configuration logic isolated from main bot form.
 */

import { useState } from 'react'
import { Eye, EyeOff, AlertCircle } from 'lucide-react'

export interface DexConfig {
  exchange_type: 'cex' | 'dex'
  chain_id?: number
  dex_router?: string
  wallet_private_key?: string
  rpc_url?: string
}

interface DexConfigSectionProps {
  config: DexConfig
  onChange: (config: DexConfig) => void
}

// Blockchain configurations
const BLOCKCHAINS = [
  { id: 1, name: 'Ethereum Mainnet', shortName: 'Ethereum', defaultRpc: 'https://mainnet.infura.io/v3/YOUR_INFURA_KEY' },
  { id: 56, name: 'Binance Smart Chain', shortName: 'BSC', defaultRpc: 'https://bsc-dataseed.binance.org/' },
  { id: 137, name: 'Polygon Mainnet', shortName: 'Polygon', defaultRpc: 'https://polygon-rpc.com' },
  { id: 42161, name: 'Arbitrum One', shortName: 'Arbitrum', defaultRpc: 'https://arb1.arbitrum.io/rpc' },
]

// DEX router configurations (contract addresses)
const DEX_ROUTERS = {
  1: [ // Ethereum
    { name: 'Uniswap V3', address: '0xE592427A0AEce92De3Edee1F18E0157C05861564', fee: '0.3%' },
  ],
  56: [ // BSC
    { name: 'PancakeSwap V3', address: '0x1b81D678ffb9C0263b24A97847620C99d213eB14', fee: '0.25%' },
    { name: 'PancakeSwap V2', address: '0x10ED43C718714eb63d5aA57B78B54704E256024E', fee: '0.25%' },
  ],
  137: [ // Polygon
    { name: 'Uniswap V3', address: '0xE592427A0AEce92De3Edee1F18E0157C05861564', fee: '0.3%' },
    { name: 'SushiSwap', address: '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506', fee: '0.3%' },
  ],
  42161: [ // Arbitrum
    { name: 'Uniswap V3', address: '0xE592427A0AEce92De3Edee1F18E0157C05861564', fee: '0.3%' },
    { name: 'SushiSwap', address: '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506', fee: '0.3%' },
  ],
}

export default function DexConfigSection({ config, onChange }: DexConfigSectionProps) {
  const [showPrivateKey, setShowPrivateKey] = useState(false)

  const isDex = config.exchange_type === 'dex'
  const selectedBlockchain = BLOCKCHAINS.find(b => b.id === config.chain_id)
  const availableRouters = config.chain_id ? DEX_ROUTERS[config.chain_id as keyof typeof DEX_ROUTERS] || [] : []

  // Handler for exchange type change
  const handleExchangeTypeChange = (type: 'cex' | 'dex') => {
    if (type === 'cex') {
      // Clear DEX-specific fields when switching to CEX
      onChange({
        exchange_type: 'cex',
        chain_id: undefined,
        dex_router: undefined,
        wallet_private_key: undefined,
        rpc_url: undefined,
      })
    } else {
      // Set default DEX values
      onChange({
        exchange_type: 'dex',
        chain_id: 1, // Default to Ethereum
        dex_router: DEX_ROUTERS[1][0].address, // Default to Uniswap V3
        wallet_private_key: '',
        rpc_url: BLOCKCHAINS[0].defaultRpc,
      })
    }
  }

  // Handler for blockchain change
  const handleBlockchainChange = (chainId: number) => {
    const blockchain = BLOCKCHAINS.find(b => b.id === chainId)
    const routers = DEX_ROUTERS[chainId as keyof typeof DEX_ROUTERS] || []

    onChange({
      ...config,
      chain_id: chainId,
      dex_router: routers[0]?.address || '',
      rpc_url: blockchain?.defaultRpc || '',
    })
  }

  return (
    <div className="border-b border-slate-700 pb-6">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <span className="text-blue-400">2.</span> Exchange Configuration
      </h3>

      {/* Exchange Type Selector */}
      <div className="mb-6">
        <label className="block text-sm font-medium mb-3">
          Exchange Type *
        </label>
        <div className="grid grid-cols-2 gap-3">
          {/* CEX Option */}
          <button
            type="button"
            onClick={() => handleExchangeTypeChange('cex')}
            className={`p-4 rounded-lg border-2 transition-all ${
              !isDex
                ? 'border-blue-500 bg-blue-500/10 text-white'
                : 'border-slate-600 bg-slate-700/50 text-slate-300 hover:border-slate-500'
            }`}
          >
            <div className="font-semibold mb-1">Centralized Exchange (CEX)</div>
            <div className="text-xs text-slate-400">Coinbase Pro</div>
          </button>

          {/* DEX Option */}
          <button
            type="button"
            onClick={() => handleExchangeTypeChange('dex')}
            className={`p-4 rounded-lg border-2 transition-all ${
              isDex
                ? 'border-blue-500 bg-blue-500/10 text-white'
                : 'border-slate-600 bg-slate-700/50 text-slate-300 hover:border-slate-500'
            }`}
          >
            <div className="font-semibold mb-1">Decentralized Exchange (DEX)</div>
            <div className="text-xs text-slate-400">Uniswap, PancakeSwap, etc.</div>
          </button>
        </div>
      </div>

      {/* DEX-Specific Configuration */}
      {isDex && (
        <div className="space-y-4 bg-slate-800/50 p-4 rounded-lg border border-slate-700">
          {/* Blockchain Selector */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Blockchain Network *
            </label>
            <select
              value={config.chain_id || ''}
              onChange={(e) => handleBlockchainChange(Number(e.target.value))}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white"
            >
              <option value="">Select blockchain...</option>
              {BLOCKCHAINS.map((blockchain) => (
                <option key={blockchain.id} value={blockchain.id}>
                  {blockchain.name} (Chain ID: {blockchain.id})
                </option>
              ))}
            </select>
            {selectedBlockchain && (
              <p className="mt-1 text-xs text-slate-400">
                Selected: {selectedBlockchain.shortName}
              </p>
            )}
          </div>

          {/* DEX Router Selector */}
          {config.chain_id && availableRouters.length > 0 && (
            <div>
              <label className="block text-sm font-medium mb-2">
                DEX Router *
              </label>
              <select
                value={config.dex_router || ''}
                onChange={(e) => onChange({ ...config, dex_router: e.target.value })}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white"
              >
                <option value="">Select DEX...</option>
                {availableRouters.map((router) => (
                  <option key={router.address} value={router.address}>
                    {router.name} (Fee: {router.fee})
                  </option>
                ))}
              </select>
              {config.dex_router && (
                <p className="mt-1 text-xs text-slate-400 font-mono break-all">
                  Router: {config.dex_router}
                </p>
              )}
            </div>
          )}

          {/* RPC URL Input */}
          <div>
            <label className="block text-sm font-medium mb-2">
              RPC Endpoint URL *
            </label>
            <input
              type="text"
              value={config.rpc_url || ''}
              onChange={(e) => onChange({ ...config, rpc_url: e.target.value })}
              placeholder="https://mainnet.infura.io/v3/YOUR_KEY"
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white font-mono text-sm"
            />
            <p className="mt-1 text-xs text-slate-400">
              RPC endpoint for blockchain connection (Infura, Alchemy, etc.)
            </p>
          </div>

          {/* Wallet Private Key Input */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Wallet Private Key *
            </label>
            <div className="relative">
              <input
                type={showPrivateKey ? 'text' : 'password'}
                value={config.wallet_private_key || ''}
                onChange={(e) => onChange({ ...config, wallet_private_key: e.target.value })}
                placeholder="0x..."
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 pr-10 text-white font-mono text-sm"
              />
              <button
                type="button"
                onClick={() => setShowPrivateKey(!showPrivateKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
              >
                {showPrivateKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <div className="mt-2 flex items-start gap-2 p-2 bg-yellow-500/10 border border-yellow-500/30 rounded text-xs text-yellow-300">
              <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
              <div>
                <strong>Security Warning:</strong> Your private key grants full control of your wallet.
                Never share it and ensure you trust this application. Private keys are encrypted before storage.
              </div>
            </div>
          </div>

          {/* Summary */}
          {config.chain_id && config.dex_router && (
            <div className="mt-4 p-3 bg-slate-700/50 rounded border border-slate-600">
              <div className="text-xs font-medium text-slate-300 mb-2">Configuration Summary:</div>
              <div className="space-y-1 text-xs text-slate-400">
                <div>Network: <span className="text-white">{selectedBlockchain?.name}</span></div>
                <div>DEX: <span className="text-white">
                  {availableRouters.find(r => r.address === config.dex_router)?.name}
                </span></div>
                <div>Status: <span className="text-green-400">Ready to trade</span></div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* CEX Info */}
      {!isDex && (
        <div className="p-3 bg-slate-700/50 rounded border border-slate-600 text-xs text-slate-400">
          Using exchange API credentials configured in your account settings.
        </div>
      )}
    </div>
  )
}
