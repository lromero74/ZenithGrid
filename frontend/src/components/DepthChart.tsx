import { useState, useEffect } from 'react'
import { api } from '../services/api'

interface DepthChartProps {
  productId: string
  limitPrice?: number
  breakevenPrice?: number
  quoteCurrency: string
  onPriceClick?: (price: number) => void
  onOrderBookUpdate?: (lowestBid: number, highestAsk: number, bestBid: number, bestAsk: number) => void
}

interface OrderBookLevel {
  price: number
  size: number
  cumulative: number
}

export function DepthChart({ productId, limitPrice, breakevenPrice, quoteCurrency, onPriceClick, onOrderBookUpdate }: DepthChartProps) {
  const [bids, setBids] = useState<OrderBookLevel[]>([])
  const [asks, setAsks] = useState<OrderBookLevel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch order book data
  useEffect(() => {
    const fetchOrderBook = async () => {
      try {
        const response = await api.get(`/orderbook/${productId}?limit=15`)
        const data = response.data

        // Process bids (highest price first)
        let bidCumulative = 0
        const processedBids: OrderBookLevel[] = data.bids.map((b: number[]) => {
          bidCumulative += b[1]
          return { price: b[0], size: b[1], cumulative: bidCumulative }
        })

        // Process asks (lowest price first)
        let askCumulative = 0
        const processedAsks: OrderBookLevel[] = data.asks.map((a: number[]) => {
          askCumulative += a[1]
          return { price: a[0], size: a[1], cumulative: askCumulative }
        })

        setBids(processedBids)
        setAsks(processedAsks)
        setLoading(false)

        // Notify parent of order book range for slider extension
        if (onOrderBookUpdate && processedBids.length > 0 && processedAsks.length > 0) {
          const lowestBid = processedBids[processedBids.length - 1].price  // Last bid is lowest
          const highestAsk = processedAsks[processedAsks.length - 1].price  // Last ask is highest
          const bestBid = processedBids[0].price  // First bid is best (highest)
          const bestAsk = processedAsks[0].price  // First ask is best (lowest)
          onOrderBookUpdate(lowestBid, highestAsk, bestBid, bestAsk)
        }
      } catch (err: any) {
        console.error('Failed to fetch orderbook:', err)
        setError('Failed to load')
        setLoading(false)
      }
    }

    fetchOrderBook()
    // Refresh every 3 seconds
    const interval = setInterval(fetchOrderBook, 3000)
    return () => clearInterval(interval)
  }, [productId])

  if (loading) {
    return (
      <div className="w-24 h-full bg-slate-900 rounded-lg flex items-center justify-center">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-slate-400" />
      </div>
    )
  }

  if (error || (bids.length === 0 && asks.length === 0)) {
    return null
  }

  // Calculate max cumulative for scaling
  const maxBidCumulative = bids.length > 0 ? bids[bids.length - 1].cumulative : 0
  const maxAskCumulative = asks.length > 0 ? asks[asks.length - 1].cumulative : 0
  const maxCumulative = Math.max(maxBidCumulative, maxAskCumulative)

  // Format price based on quote currency
  const formatPrice = (price: number) => {
    if (quoteCurrency === 'USD') return price.toFixed(2)
    return price.toFixed(8)
  }

  // Check if a price level is near the limit price
  const isNearLimitPrice = (price: number) => {
    if (!limitPrice) return false
    const tolerance = limitPrice * 0.0001 // 0.01% tolerance
    return Math.abs(price - limitPrice) <= tolerance
  }

  return (
    <div className="w-28 h-full bg-slate-900 rounded-lg p-2 flex flex-col text-[10px]">
      <div className="text-slate-400 text-center mb-1 font-medium">Depth</div>

      {/* Asks (sell orders) - displayed top to bottom, lowest ask at bottom */}
      <div className="flex-1 flex flex-col justify-end overflow-hidden min-h-0">
        {[...asks].reverse().slice(0, 10).map((ask, idx, arr) => {
          const widthPercent = maxCumulative > 0 ? (ask.cumulative / maxCumulative) * 100 : 0
          const isAtLimit = isNearLimitPrice(ask.price)
          // Check if this ask is above breakeven and the next one (below it in price) is at or below breakeven
          const nextAsk = arr[idx + 1]
          const showBreakevenLine = breakevenPrice && breakevenPrice > 0 &&
            ask.price > breakevenPrice &&
            (!nextAsk || nextAsk.price <= breakevenPrice)
          return (
            <div key={`ask-${idx}`} className="flex-1 min-h-[14px] max-h-[24px] flex flex-col justify-center">
              <div
                onClick={() => onPriceClick?.(ask.price)}
                className={`relative flex-1 flex items-center ${isAtLimit ? 'ring-1 ring-slate-400 bg-slate-700/50' : ''} ${onPriceClick ? 'cursor-pointer hover:bg-slate-700/30' : ''}`}
              >
                {/* Background bar */}
                <div
                  className="absolute right-0 h-full bg-red-500/30"
                  style={{ width: `${widthPercent}%` }}
                />
                {/* Price text */}
                <span className="relative z-10 text-red-400 truncate w-full text-right pr-1">
                  {formatPrice(ask.price)}
                </span>
              </div>
              {/* Red line below this ask to mark breakeven boundary */}
              {showBreakevenLine && (
                <div className="h-px bg-red-500 w-full flex-shrink-0" title={`Breakeven: ${formatPrice(breakevenPrice)}`} />
              )}
            </div>
          )
        })}
      </div>

      {/* Spread indicator */}
      <div className="h-4 flex items-center justify-center border-y border-slate-700 my-1">
        {bids.length > 0 && asks.length > 0 && (
          <span className="text-slate-500 text-[9px]">
            {((asks[0].price - bids[0].price) / bids[0].price * 100).toFixed(3)}%
          </span>
        )}
      </div>

      {/* Bids (buy orders) - displayed top to bottom, highest bid at top */}
      <div className="flex-1 flex flex-col overflow-hidden min-h-0">
        {bids.slice(0, 10).map((bid, idx, arr) => {
          const widthPercent = maxCumulative > 0 ? (bid.cumulative / maxCumulative) * 100 : 0
          const isAtLimit = isNearLimitPrice(bid.price)
          // Check if this bid is at or above breakeven and the next one (below it) is below breakeven
          const nextBid = arr[idx + 1]
          const showBreakevenLine = breakevenPrice && breakevenPrice > 0 &&
            bid.price >= breakevenPrice &&
            nextBid && nextBid.price < breakevenPrice
          return (
            <div key={`bid-${idx}`} className="flex-1 min-h-[14px] max-h-[24px] flex flex-col justify-center">
              <div
                onClick={() => onPriceClick?.(bid.price)}
                className={`relative flex-1 flex items-center ${isAtLimit ? 'ring-1 ring-slate-400 bg-slate-700/50' : ''} ${onPriceClick ? 'cursor-pointer hover:bg-slate-700/30' : ''}`}
              >
                {/* Background bar */}
                <div
                  className="absolute right-0 h-full bg-green-500/30"
                  style={{ width: `${widthPercent}%` }}
                />
                {/* Price text */}
                <span className="relative z-10 text-green-400 truncate w-full text-right pr-1">
                  {formatPrice(bid.price)}
                </span>
              </div>
              {/* Red line below this bid to mark breakeven boundary (selling below this is a loss) */}
              {showBreakevenLine && (
                <div className="h-px bg-red-500 w-full flex-shrink-0" title={`Breakeven: ${formatPrice(breakevenPrice)}`} />
              )}
            </div>
          )
        })}
      </div>

      {/* Breakeven indicator if in view */}
      {breakevenPrice && bids.length > 0 && asks.length > 0 && (
        <div className="text-[9px] text-yellow-400 text-center mt-1 border-t border-slate-700 pt-1">
          BE: {formatPrice(breakevenPrice)}
        </div>
      )}
    </div>
  )
}
