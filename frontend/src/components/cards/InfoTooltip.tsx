import { Info } from 'lucide-react'

export function InfoTooltip({ text }: { text: string }) {
  return (
    <div className="group relative ml-auto">
      <Info className="w-4 h-4 text-slate-500 hover:text-slate-300 cursor-help transition-colors" />
      <div className="absolute top-full right-0 mt-2 w-48 p-2 bg-slate-900 border border-slate-600 rounded-lg shadow-xl text-xs text-slate-300 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50">
        <div className="absolute top-0 right-2 transform -translate-y-1/2 rotate-45 w-2 h-2 bg-slate-900 border-l border-t border-slate-600" />
        {text}
      </div>
    </div>
  )
}
