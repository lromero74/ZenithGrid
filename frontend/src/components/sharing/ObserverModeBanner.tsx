import { Eye } from 'lucide-react'

interface ObserverModeBannerProps {
  accountName: string
}

export function ObserverModeBanner({ accountName }: ObserverModeBannerProps) {
  return (
    <div className="bg-violet-900/50 border-b border-violet-600/50">
      <div className="container mx-auto px-4 sm:px-6 py-2">
        <div className="flex items-center justify-center space-x-2 text-violet-200">
          <Eye className="w-4 h-4" />
          <span className="text-sm font-medium">
            Observer Mode — Viewing {accountName} (Read-Only)
          </span>
        </div>
      </div>
    </div>
  )
}
