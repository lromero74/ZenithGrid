/**
 * Wordle on-screen QWERTY keyboard with color-coded keys.
 */

import { Delete } from 'lucide-react'
import type { KeyboardState } from './wordleEngine'

const ROWS = [
  ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
  ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
  ['ENTER', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', 'BACK'],
]

const KEY_COLORS = {
  correct: 'bg-emerald-600 text-white',
  present: 'bg-yellow-600 text-white',
  absent: 'bg-slate-800 text-slate-500',
  unused: 'bg-slate-600 text-white hover:bg-slate-500',
}

interface WordleKeyboardProps {
  keyboardState: KeyboardState
  onKey: (key: string) => void
  disabled: boolean
}

export function WordleKeyboard({ keyboardState, onKey, disabled }: WordleKeyboardProps) {
  return (
    <div className="flex flex-col items-center space-y-1">
      {ROWS.map((row, i) => (
        <div key={i} className="flex space-x-1">
          {row.map(key => {
            const isSpecial = key === 'ENTER' || key === 'BACK'
            const state = keyboardState[key]
            const colorClass = state ? KEY_COLORS[state] : KEY_COLORS.unused

            return (
              <button
                key={key}
                onClick={() => onKey(key)}
                disabled={disabled}
                className={`${isSpecial ? 'px-2 sm:px-3' : 'w-8 sm:w-9'} h-10 sm:h-12 rounded text-xs sm:text-sm font-bold transition-colors ${colorClass} disabled:opacity-50`}
              >
                {key === 'BACK' ? <Delete className="w-4 h-4 mx-auto" /> : key}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
