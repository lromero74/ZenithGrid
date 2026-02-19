interface GoalProgressBarProps {
  progress: number
  onTrack: boolean
  size?: 'sm' | 'md'
}

export function GoalProgressBar({ progress, onTrack, size = 'md' }: GoalProgressBarProps) {
  const barHeight = size === 'sm' ? 'h-1.5' : 'h-2.5'
  const clampedProgress = Math.min(Math.max(progress, 0), 100)
  const barColor = onTrack ? 'bg-emerald-500' : 'bg-amber-500'

  return (
    <div className={`w-full bg-slate-700 rounded-full ${barHeight} overflow-hidden`}>
      <div
        className={`${barColor} ${barHeight} rounded-full transition-all duration-500`}
        style={{ width: `${clampedProgress}%` }}
      />
    </div>
  )
}
