/**
 * Shared playing card components — used by all card games.
 *
 * Extracted from Solitaire.tsx to avoid duplicate card renderers.
 */

import { getCardColor, getRankDisplay, getSuitSymbol } from '../utils/cardUtils'
import type { Card } from '../utils/cardUtils'

// ── CardBack ──────────────────────────────────────────────────────────

export function CardBack() {
  return (
    <div className="w-full h-full rounded-md bg-blue-800 border border-blue-700 shadow-md"
         style={{ backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(255,255,255,0.04) 3px, rgba(255,255,255,0.04) 6px)' }}
    />
  )
}

// ── CardFace ──────────────────────────────────────────────────────────

interface CardFaceProps {
  card: Card
  selected?: boolean
  validTarget?: boolean
  hinted?: boolean
  held?: boolean
}

export function CardFace({ card, selected = false, validTarget = false, hinted = false, held = false }: CardFaceProps) {
  const color = getCardColor(card)
  const textColor = color === 'red' ? 'text-red-500' : 'text-slate-900'
  const symbol = getSuitSymbol(card.suit)
  const rank = getRankDisplay(card.rank)

  return (
    <div className={`
      w-full h-full rounded-md bg-slate-50 border shadow-md cursor-pointer
      flex flex-col justify-between p-0.5 sm:p-1 select-none
      transition-all duration-150
      ${selected ? 'ring-2 ring-yellow-400 -translate-y-1 border-yellow-400' : 'border-slate-300'}
      ${validTarget ? 'ring-2 ring-emerald-400/60' : ''}
      ${hinted ? 'ring-2 ring-amber-400 animate-pulse -translate-y-1' : ''}
      ${held ? 'ring-2 ring-cyan-400 border-cyan-400' : ''}
    `}>
      {/* Top-left rank + suit */}
      <div className={`leading-none ${textColor}`}>
        <div className="text-[0.55rem] sm:text-xs font-bold">{rank}</div>
        <div className="text-[0.5rem] sm:text-[0.6rem]">{symbol}</div>
      </div>
      {/* Center suit */}
      <div className={`text-center text-base sm:text-xl ${textColor}`}>
        {symbol}
      </div>
      {/* Bottom-right rank + suit (inverted) */}
      <div className={`leading-none text-right rotate-180 ${textColor}`}>
        <div className="text-[0.55rem] sm:text-xs font-bold">{rank}</div>
        <div className="text-[0.5rem] sm:text-[0.6rem]">{symbol}</div>
      </div>
    </div>
  )
}
