/**
 * Shared difficulty picker used across games that support difficulty levels.
 *
 * Renders a row of buttons for selecting difficulty.
 */

import type { Difficulty } from '../types'

interface DifficultySelectorProps {
  value: Difficulty
  onChange: (difficulty: Difficulty) => void
  options?: Difficulty[]
}

const DIFFICULTY_STYLES: Record<Difficulty, { active: string; inactive: string }> = {
  easy: {
    active: 'bg-emerald-600 text-white',
    inactive: 'bg-slate-700 text-emerald-400 hover:bg-slate-600',
  },
  medium: {
    active: 'bg-yellow-600 text-white',
    inactive: 'bg-slate-700 text-yellow-400 hover:bg-slate-600',
  },
  hard: {
    active: 'bg-red-600 text-white',
    inactive: 'bg-slate-700 text-red-400 hover:bg-slate-600',
  },
  expert: {
    active: 'bg-purple-600 text-white',
    inactive: 'bg-slate-700 text-purple-400 hover:bg-slate-600',
  },
}

export function DifficultySelector({
  value,
  onChange,
  options = ['easy', 'medium', 'hard'],
}: DifficultySelectorProps) {
  return (
    <div className="flex space-x-2">
      {options.map(diff => {
        const styles = DIFFICULTY_STYLES[diff]
        const isActive = value === diff
        return (
          <button
            key={diff}
            onClick={() => onChange(diff)}
            className={`px-3 py-1 rounded text-sm font-medium capitalize transition-colors ${
              isActive ? styles.active : styles.inactive
            }`}
          >
            {diff}
          </button>
        )
      })}
    </div>
  )
}
