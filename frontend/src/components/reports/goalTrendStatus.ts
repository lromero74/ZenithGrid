import type { GoalTrendPoint } from '../../types'

export function isPaceOnTrack(point?: Pick<GoalTrendPoint, 'current_value' | 'ideal_value'> | null): boolean {
  if (!point || point.current_value == null || point.ideal_value == null) return false
  const epsilon = Math.max(Math.abs(point.ideal_value) * 1e-9, 1e-8)
  return point.current_value + epsilon >= point.ideal_value
}
