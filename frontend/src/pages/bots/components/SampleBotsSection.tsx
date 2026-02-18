import { useState } from 'react'
import { ChevronDown, ChevronRight, Eye, Copy, Cpu, TrendingUp, BarChart3, Brain } from 'lucide-react'
import { SAMPLE_BOTS, type SampleBot } from '../data/sampleBots'

interface SampleBotsSectionProps {
  onView: (sample: SampleBot) => void
  onCopy: (sample: SampleBot) => void
}

const STRATEGY_ICONS: Record<string, typeof Cpu> = {
  'bb-recovery': BarChart3,
  'rsi-runner': TrendingUp,
  'ai-autonomous': Brain,
  'macd-crossover': Cpu,
}

function getStrategyIcon(sampleId: string) {
  const key = Object.keys(STRATEGY_ICONS).find(k => sampleId.startsWith(k))
  return key ? STRATEGY_ICONS[key] : Cpu
}

export function SampleBotsSection({ onView, onCopy }: SampleBotsSectionProps) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem('zenith-sample-bots-collapsed') === 'true'
    } catch {
      return false
    }
  })

  const toggle = () => {
    const next = !collapsed
    setCollapsed(next)
    try {
      localStorage.setItem('zenith-sample-bots-collapsed', String(next))
    } catch { /* ignored */ }
  }

  const btcBots = SAMPLE_BOTS.filter(b => b.market === 'BTC')
  const usdBots = SAMPLE_BOTS.filter(b => b.market === 'USD')

  return (
    <div className="mb-6">
      {/* Header */}
      <button
        onClick={toggle}
        className="flex items-center gap-2 text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors mb-3"
      >
        {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        <span>Sample Bots</span>
        <span className="text-xs text-slate-500">({SAMPLE_BOTS.length} templates)</span>
      </button>

      {!collapsed && (
        <div className="space-y-4">
          {/* BTC Row */}
          <div>
            <div className="text-xs font-medium text-orange-400 mb-2 flex items-center gap-1.5">
              <span className="inline-block w-2 h-2 rounded-full bg-orange-400" />
              BTC Market
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {btcBots.map(bot => (
                <SampleBotCard key={bot.id} bot={bot} onView={onView} onCopy={onCopy} />
              ))}
            </div>
          </div>

          {/* USD Row */}
          <div>
            <div className="text-xs font-medium text-green-400 mb-2 flex items-center gap-1.5">
              <span className="inline-block w-2 h-2 rounded-full bg-green-400" />
              USD Market
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {usdBots.map(bot => (
                <SampleBotCard key={bot.id} bot={bot} onView={onView} onCopy={onCopy} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SampleBotCard({
  bot,
  onView,
  onCopy,
}: {
  bot: SampleBot
  onView: (bot: SampleBot) => void
  onCopy: (bot: SampleBot) => void
}) {
  const Icon = getStrategyIcon(bot.id)
  const isBtc = bot.market === 'BTC'
  const pairLabel = bot.pairCount === 'all' ? 'All pairs' : `${bot.pairCount} pairs`

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 hover:border-slate-500 transition-colors group">
      {/* Top row: icon + name + market badge */}
      <div className="flex items-start gap-2 mb-2">
        <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${isBtc ? 'text-orange-400' : 'text-green-400'}`} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-white truncate">{bot.name}</div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${isBtc ? 'bg-orange-500/20 text-orange-400' : 'bg-green-500/20 text-green-400'}`}>
              {bot.market}
            </span>
            <span className="text-[10px] text-slate-500">{pairLabel}</span>
          </div>
        </div>
      </div>

      {/* Description */}
      <p className="text-xs text-slate-400 mb-3 line-clamp-2">{bot.description}</p>

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={() => onView(bot)}
          className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium text-slate-300 bg-slate-700 hover:bg-slate-600 rounded transition-colors"
        >
          <Eye className="w-3 h-3" />
          View
        </button>
        <button
          onClick={() => onCopy(bot)}
          className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium text-blue-400 bg-blue-600/20 hover:bg-blue-600/30 border border-blue-600/40 rounded transition-colors"
        >
          <Copy className="w-3 h-3" />
          Copy
        </button>
      </div>
    </div>
  )
}
