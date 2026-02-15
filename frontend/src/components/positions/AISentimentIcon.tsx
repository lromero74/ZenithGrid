import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { authFetch } from '../../services/api'

interface AISentimentIconProps {
  botId: number
  productId: string
}

export function AISentimentIcon({ botId, productId }: AISentimentIconProps) {
  const { data: aiLog } = useQuery({
    queryKey: ['ai-sentiment', botId, productId],
    queryFn: async () => {
      const response = await authFetch(`/api/bots/${botId}/logs?product_id=${encodeURIComponent(productId)}&limit=1`)
      if (!response.ok) return null
      const data = await response.json()
      return data[0] || null
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    enabled: !!botId && !!productId,
  })

  if (!aiLog || !aiLog.decision) return null

  const decision = aiLog.decision.toLowerCase()
  const confidence = aiLog.confidence || 0

  // Map decision to icon and color
  const getIcon = () => {
    switch (decision) {
      case 'buy':
        return <TrendingUp size={14} className="text-green-400" />
      case 'sell':
        return <TrendingDown size={14} className="text-red-400" />
      case 'hold':
        return <Minus size={14} className="text-yellow-400" />
      default:
        return null
    }
  }

  const getTooltip = () => {
    return `AI: ${decision.toUpperCase()} (${confidence.toFixed(0)}%)\n${aiLog.thinking || ''}`
  }

  return (
    <div
      className="flex items-center gap-1 cursor-help"
      title={getTooltip()}
    >
      {getIcon()}
      <span className="text-[10px] text-slate-400">{confidence.toFixed(0)}%</span>
    </div>
  )
}
