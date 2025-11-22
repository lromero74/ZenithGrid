import { useState } from 'react'

interface CoinIconProps {
  symbol: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

// Mapping of coin symbols to CoinGecko IDs
const COIN_ID_MAP: Record<string, string> = {
  'BTC': 'bitcoin',
  'ETH': 'ethereum',
  'USDT': 'tether',
  'USDC': 'usd-coin',
  'BNB': 'binancecoin',
  'XRP': 'ripple',
  'ADA': 'cardano',
  'DOGE': 'dogecoin',
  'SOL': 'solana',
  'TRX': 'tron',
  'DOT': 'polkadot',
  'MATIC': 'matic-network',
  'LTC': 'litecoin',
  'SHIB': 'shiba-inu',
  'AVAX': 'avalanche-2',
  'DAI': 'dai',
  'WBTC': 'wrapped-bitcoin',
  'UNI': 'uniswap',
  'LINK': 'chainlink',
  'ATOM': 'cosmos',
  'XLM': 'stellar',
  'ETC': 'ethereum-classic',
  'BCH': 'bitcoin-cash',
  'ALGO': 'algorand',
  'APT': 'aptos',
  'FIL': 'filecoin',
  'HBAR': 'hedera-hashgraph',
  'VET': 'vechain',
  'ICP': 'internet-computer',
  'NEAR': 'near',
  'GRT': 'the-graph',
  'AAVE': 'aave',
  'MKR': 'maker',
  'SNX': 'synthetix-network-token',
  'CRV': 'curve-dao-token',
  'COMP': 'compound-governance-token',
  'YFI': 'yearn-finance',
  'SUSHI': 'sushi',
  'BAT': 'basic-attention-token',
  'ZRX': '0x',
  'MANA': 'decentraland',
  'SAND': 'the-sandbox',
  'ENJ': 'enjincoin',
  'AXS': 'axie-infinity',
  'CHZ': 'chiliz',
  'FTM': 'fantom',
  'ONE': 'harmony',
  'ZIL': 'zilliqa',
  'EGLD': 'elrond-erd-2',
  'XTZ': 'tezos',
  'EOS': 'eos',
  'THETA': 'theta-token',
  'FLOW': 'flow',
  'KSM': 'kusama',
  'KLAY': 'klay-token',
  'RUNE': 'thorchain',
  'WAVES': 'waves',
  'BTT': 'bittorrent',
  'CELO': 'celo',
  'DASH': 'dash',
  'XMR': 'monero',
  'ZEC': 'zcash',
  'QTUM': 'qtum',
  'IOTA': 'iota',
  'NEO': 'neo',
  'OMG': 'omisego',
  'ICX': 'icon',
  'XEM': 'nem',
  'LSK': 'lisk',
  'ZEN': 'zencash',
  '1INCH': '1inch',
  'LRC': 'loopring',
  'IMX': 'immutable-x',
  'GALA': 'gala',
  'APE': 'apecoin',
  'GMT': 'stepn',
  'OP': 'optimism',
  'ARB': 'arbitrum',
  'BLUR': 'blur',
  'PEPE': 'pepe',
  'WLD': 'worldcoin-wld',
  'SUI': 'sui',
  'SEI': 'sei-network',
  'STX': 'blockstack',
  'TIA': 'celestia',
  'BONK': 'bonk',
  'WIF': 'dogwifcoin',
  'FLOKI': 'floki',
  'RNDR': 'render-token',
  'INJ': 'injective-protocol',
  'FET': 'fetch-ai',
  'AGIX': 'singularitynet',
  'OCEAN': 'ocean-protocol',
  'QNT': 'quant-network',
  'ROSE': 'oasis-network',
  'LDO': 'lido-dao',
  'RPL': 'rocket-pool',
}

// Size configurations
const SIZE_CLASSES = {
  sm: 'w-6 h-6',
  md: 'w-8 h-8',
  lg: 'w-10 h-10',
}

export default function CoinIcon({ symbol, size = 'sm', className = '' }: CoinIconProps) {
  const [imageError, setImageError] = useState(false)

  // Normalize symbol (remove any whitespace, convert to uppercase)
  const normalizedSymbol = symbol?.trim().toUpperCase() || ''

  // Get CoinGecko ID for this symbol
  const coinId = COIN_ID_MAP[normalizedSymbol] || normalizedSymbol.toLowerCase()

  // CoinGecko API endpoint for coin images (free, no API key needed)
  const imageUrl = `https://assets.coincap.io/assets/icons/${normalizedSymbol.toLowerCase()}@2x.png`

  const sizeClass = SIZE_CLASSES[size]

  // Fallback: show first letter in a colored circle
  if (imageError || !normalizedSymbol) {
    return (
      <div className={`${sizeClass} rounded-full bg-blue-500/20 flex items-center justify-center text-xs font-semibold ${className}`}>
        {normalizedSymbol?.substring(0, 1) || 'Ƀ'}
      </div>
    )
  }

  return (
    <div className={`${sizeClass} rounded-full overflow-hidden bg-white/5 flex items-center justify-center ${className}`}>
      <img
        src={imageUrl}
        alt={`${symbol} icon`}
        className="w-full h-full object-cover"
        onError={() => setImageError(true)}
      />
    </div>
  )
}
