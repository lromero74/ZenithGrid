/**
 * Password Strength Meter
 *
 * Real-time visual strength indicator with 4-segment color bar
 * and checklist of password requirements.
 */

import { Check, X } from 'lucide-react'

interface PasswordStrengthMeterProps {
  password: string
}

interface Requirement {
  label: string
  met: boolean
}

function getStrength(password: string): { score: number; requirements: Requirement[] } {
  const requirements: Requirement[] = [
    { label: 'At least 8 characters', met: password.length >= 8 },
    { label: 'Contains uppercase letter', met: /[A-Z]/.test(password) },
    { label: 'Contains lowercase letter', met: /[a-z]/.test(password) },
    { label: 'Contains a number', met: /[0-9]/.test(password) },
    { label: 'Contains special character', met: /[^A-Za-z0-9]/.test(password) },
  ]

  let score = 0
  // Length scoring
  if (password.length >= 8) score += 1
  if (password.length >= 12) score += 1
  // Character class scoring
  if (/[A-Z]/.test(password)) score += 1
  if (/[a-z]/.test(password)) score += 1
  if (/[0-9]/.test(password)) score += 1
  if (/[^A-Za-z0-9]/.test(password)) score += 1

  return { score, requirements }
}

function getStrengthLevel(score: number): { label: string; color: string; segments: number } {
  if (score <= 2) return { label: 'Weak', color: 'text-red-400', segments: 1 }
  if (score <= 3) return { label: 'Fair', color: 'text-orange-400', segments: 2 }
  if (score <= 4) return { label: 'Good', color: 'text-yellow-400', segments: 3 }
  return { label: 'Strong', color: 'text-green-400', segments: 4 }
}

const segmentColors = [
  'bg-red-500',
  'bg-orange-500',
  'bg-yellow-500',
  'bg-green-500',
]

export function PasswordStrengthMeter({ password }: PasswordStrengthMeterProps) {
  if (!password) return null

  const { score, requirements } = getStrength(password)
  const level = getStrengthLevel(score)

  return (
    <div className="mt-2 space-y-2">
      {/* Strength bar */}
      <div className="flex items-center space-x-2">
        <div className="flex-1 flex space-x-1">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                i < level.segments ? segmentColors[level.segments - 1] : 'bg-slate-600'
              }`}
            />
          ))}
        </div>
        <span className={`text-xs font-medium ${level.color}`}>{level.label}</span>
      </div>

      {/* Requirements checklist */}
      <div className="space-y-1">
        {requirements.map((req) => (
          <div key={req.label} className="flex items-center space-x-2">
            {req.met ? (
              <Check className="w-3.5 h-3.5 text-green-400" />
            ) : (
              <X className="w-3.5 h-3.5 text-slate-500" />
            )}
            <span className={`text-xs ${req.met ? 'text-green-400' : 'text-slate-500'}`}>
              {req.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Check if all required password criteria are met (special char is bonus) */
export function isPasswordValid(password: string): boolean {
  return (
    password.length >= 8 &&
    /[A-Z]/.test(password) &&
    /[a-z]/.test(password) &&
    /[0-9]/.test(password)
  )
}
