import { LoadingSpinner } from '../LoadingSpinner'

export function CardLoading() {
  return (
    <div className="flex items-center justify-center h-32">
      <LoadingSpinner size="sm" text="Loading..." />
    </div>
  )
}

export function CardError() {
  return (
    <div className="flex items-center justify-center h-32 text-slate-500">
      <span className="text-xs">Data unavailable</span>
    </div>
  )
}
