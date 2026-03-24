import { Eye } from 'lucide-react'

interface ObserverModeBannerProps {
  accountName: string
  ownerName?: string | null
}

export function ObserverModeBanner({ accountName, ownerName }: ObserverModeBannerProps) {
  const label = ownerName
    ? `Observer Mode — Viewing ${ownerName}'s account "${accountName}" (Read-Only)`
    : `Observer Mode — Viewing ${accountName} (Read-Only)`

  return (
    <div className="bg-violet-900/50 border-b border-violet-600/50">
      <div className="container mx-auto px-4 sm:px-6 py-2">
        <div className="flex items-center justify-center space-x-2 text-violet-200">
          <Eye className="w-4 h-4" />
          <span className="text-sm font-medium">{label}</span>
        </div>
      </div>
    </div>
  )
}
