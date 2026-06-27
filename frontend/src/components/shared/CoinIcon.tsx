import { useState } from 'react'

interface CoinIconProps {
  symbol: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
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

  // Use our backend proxy to avoid CORS issues with external coin icon APIs
  // Icons are cached on the backend for fast subsequent requests
  const imageUrl = `/api/coin-icons/${normalizedSymbol.toLowerCase()}`

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
