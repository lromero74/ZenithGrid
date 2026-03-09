/**
 * Shared playing card components — used by all card games.
 *
 * Extracted from Solitaire.tsx to avoid duplicate card renderers.
 */

import { getCardColor, getRankDisplay, getSuitSymbol } from '../utils/cardUtils'
import type { Card } from '../utils/cardUtils'

// ── Standard card sizes ─────────────────────────────────────────────
// Use these constants for all card-game layouts so sizing is consistent.

/** Standard playable card — most games use this for player hands, piles, etc. */
export const CARD_SIZE = 'w-14 h-[5rem] sm:w-16 sm:h-[5.625rem]'

/** Compact card — same desktop size, narrower on mobile (Hearts, Spades, Blackjack). */
export const CARD_SIZE_COMPACT = 'w-12 h-[4.25rem] sm:w-16 sm:h-[5.625rem]'

/** Narrow card — for dense layouts like FreeCell columns. */
export const CARD_SIZE_NARROW = 'w-11 h-[4.25rem] sm:w-14 sm:h-[5.625rem]'

/** Mini card — for opponent hands, small displays. */
export const CARD_SIZE_MINI = 'w-11 h-[3.85rem] sm:w-14 sm:h-[4.9rem]'

/** Large card — for featured player hands (Texas Hold'em). */
export const CARD_SIZE_LARGE = 'w-[4.5rem] h-[6.25rem] sm:w-20 sm:h-[7rem]'

/** Extra-small card — for pegging/scoring displays (Cribbage, Hold'em). */
export const CARD_SIZE_XS = 'w-10 h-14 sm:w-11 sm:h-[3.75rem]'

/** Tiny vertical indicator slot — opponent hand backs in trick-taking games. */
export const CARD_SLOT_V = 'w-5 h-8'

/** Tiny horizontal indicator slot — opponent hand backs (east/west seats). */
export const CARD_SLOT_H = 'w-8 h-3'

// ── CardBack ──────────────────────────────────────────────────────────

export function CardBack() {
  return (
    <div className="w-full h-full rounded-md bg-blue-800 border border-blue-700 shadow-md relative overflow-hidden"
         style={{ backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(255,255,255,0.04) 3px, rgba(255,255,255,0.04) 6px)' }}
    >
      {/* Truck logo overlay */}
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="rgba(0, 212, 255, 0.25)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="absolute inset-0 w-full h-full p-2 sm:p-2.5"
      >
        <path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2" />
        <path d="M15 18H9" />
        <path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14" />
        <circle cx="17" cy="18" r="2" />
        <circle cx="7" cy="18" r="2" />
      </svg>
    </div>
  )
}

// ── CardFace ──────────────────────────────────────────────────────────

interface CardFaceProps {
  card: Card
  selected?: boolean
  validTarget?: boolean
  hinted?: boolean
  held?: boolean
  /** Minimal layout — just rank + suit centered. Use for very small cards. */
  mini?: boolean
  /** Larger text — for featured player hands. */
  large?: boolean
  /** Rotate the text content (degrees). For side-facing cards on opponents. */
  textRotation?: number
}

export function CardFace({ card, selected = false, validTarget = false, hinted = false, held = false, mini = false, large = false, textRotation }: CardFaceProps) {
  const color = getCardColor(card)
  const textColor = color === 'red' ? 'text-red-500' : 'text-slate-900'
  const symbol = getSuitSymbol(card.suit)
  const rank = getRankDisplay(card.rank)

  return (
    <div className={`
      w-full h-full rounded-md bg-slate-50 border shadow-md cursor-pointer
      ${mini ? 'flex items-center justify-center' : 'flex flex-col justify-between p-0.5 sm:p-1'} select-none text-left overflow-hidden
      transition-all duration-150
      ${selected ? 'ring-2 ring-yellow-400 -translate-y-1 border-yellow-400' : 'border-slate-300'}
      ${validTarget ? 'ring-2 ring-emerald-400/60' : ''}
      ${hinted ? 'ring-2 ring-amber-400 animate-pulse -translate-y-1' : ''}
      ${held ? 'ring-2 ring-cyan-400 border-cyan-400' : ''}
    `}>
      {mini ? (
        <div className={`text-center leading-tight ${textColor}`} style={textRotation ? { transform: `rotate(${textRotation}deg)` } : undefined}>
          <div className="text-xs sm:text-sm font-bold">{rank}</div>
          <div className="text-[0.6rem] sm:text-xs -mt-0.5">{symbol}</div>
        </div>
      ) : (
        <>
          {/* Top-left rank + suit */}
          <div className={`leading-none ${textColor}`}>
            <div className={`${large ? 'text-xs sm:text-sm' : 'text-[0.55rem] sm:text-xs'} font-bold`}>{rank}</div>
            <div className={large ? 'text-[0.6rem] sm:text-xs' : 'text-[0.5rem] sm:text-[0.6rem]'}>{symbol}</div>
          </div>
          {/* Center suit */}
          <div className={`text-center ${large ? 'text-lg sm:text-2xl' : 'text-base sm:text-xl'} ${textColor}`}>
            {symbol}
          </div>
          {/* Bottom-right rank + suit (inverted) */}
          <div className={`leading-none text-right rotate-180 self-end ${textColor}`}>
            <div className={`${large ? 'text-xs sm:text-sm' : 'text-[0.55rem] sm:text-xs'} font-bold`}>{rank}</div>
            <div className={large ? 'text-[0.6rem] sm:text-xs' : 'text-[0.5rem] sm:text-[0.6rem]'}>{symbol}</div>
          </div>
        </>
      )}
    </div>
  )
}
