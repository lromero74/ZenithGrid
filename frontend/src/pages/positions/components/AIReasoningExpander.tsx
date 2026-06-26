import { useEffect, useState } from 'react'
import { Brain, ChevronDown, ChevronUp, Wrench } from 'lucide-react'
import { positionsApi } from '../../../services/api'
import { formatDateTime } from '../../../utils/dateFormat'
import type { AIOpinionLog, AIToolCall } from '../../../types'
import { SpeculativeSignalBreakdown } from './SpeculativeSignalBreakdown'

interface Props {
  positionId: number
  opinion?: AIOpinionLog | null
  fetched?: boolean
}

const signalColor = (sig: string) => {
  switch (sig.toLowerCase()) {
    case 'buy':
      return 'text-emerald-400'
    case 'sell':
      return 'text-rose-400'
    default:
      return 'text-slate-300'
  }
}

export function AIReasoningExpander({ positionId, opinion: preloadedOpinion, fetched: preloadedFetched }: Props) {
  const [open, setOpen] = useState(false)
  const [localOpinion, setLocalOpinion] = useState<AIOpinionLog | null>(null)
  const [localFetched, setLocalFetched] = useState(false)
  const [expandedTools, setExpandedTools] = useState<Set<number>>(new Set())
  const hasPreloadedState = preloadedOpinion !== undefined || preloadedFetched !== undefined

  // Prefetch once so the component can hide itself entirely when there are no
  // tool calls to surface (single-shot fallback — PRP Phase E). The endpoint
  // returns null when no opinion is logged yet, so we don't need special 404
  // handling here.
  useEffect(() => {
    if (hasPreloadedState) return
    let cancelled = false
    ;(async () => {
      try {
        const data = await positionsApi.getAIOpinion(positionId)
        if (!cancelled) setLocalOpinion(data)
      } catch {
        // Non-critical audit widget — stay quiet on any fetch error.
      } finally {
        if (!cancelled) setLocalFetched(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [hasPreloadedState, positionId])

  const opinion = hasPreloadedState ? (preloadedOpinion ?? null) : localOpinion
  const fetched = hasPreloadedState ? Boolean(preloadedFetched) : localFetched

  const toggle = () => setOpen((prev) => !prev)

  const toggleTool = (idx: number) => {
    setExpandedTools((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  if (!fetched) return null
  if (!opinion || !opinion.tool_calls || opinion.tool_calls.length === 0) return null

  return (
    <div className="mt-3 border-t border-slate-700/50 pt-3">
      <button
        onClick={toggle}
        className="flex items-center gap-2 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        aria-expanded={open}
        aria-label="Toggle AI reasoning detail"
      >
        <Brain size={14} />
        <span>AI reasoning</span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {open && (
        <div className="mt-2 rounded-md bg-slate-900/40 p-3 text-xs text-slate-300 space-y-2">
          <div className="flex items-center gap-3">
            <span className={`font-semibold uppercase ${signalColor(opinion.signal)}`}>
              {opinion.signal}
            </span>
            <span className="text-slate-400">
              confidence <span className="text-slate-200 font-medium">{opinion.confidence}%</span>
            </span>
            {opinion.ai_model && (
              <span className="text-slate-500">via {opinion.ai_model}</span>
            )}
            <span className="text-slate-500 ml-auto">{formatDateTime(opinion.created_at)}</span>
          </div>

          {opinion.reasoning && (
            <div className="text-slate-300 whitespace-pre-wrap leading-relaxed">
              {opinion.reasoning}
            </div>
          )}

          <SpeculativeSignalBreakdown
            doublingProbabilityScore={opinion.doubling_probability_score ?? null}
            speculativeScore={opinion.speculative_score ?? null}
            components={opinion.speculative_components ?? null}
          />

          <div className="pt-2 border-t border-slate-700/40">
            <div className="flex items-center gap-1 text-slate-400 mb-1">
              <Wrench size={12} />
              <span>Tools called ({opinion.tool_calls.length})</span>
            </div>
            <div className="space-y-1">
              {opinion.tool_calls.map((call: AIToolCall, idx: number) => {
                const isExpanded = expandedTools.has(idx)
                return (
                  <div key={idx} className="rounded bg-slate-800/60 p-2">
                    <button
                      onClick={() => toggleTool(idx)}
                      className="flex items-center gap-2 w-full text-left text-slate-200 hover:text-white"
                    >
                      {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      <code className="text-sky-300">{call.name}</code>
                      {call.input && Object.keys(call.input).length > 0 && (
                        <span className="text-slate-500 truncate">
                          ({Object.entries(call.input).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})
                        </span>
                      )}
                    </button>
                    {isExpanded && (
                      <div className="mt-1 pl-5 text-slate-400">
                        {call.output_summary ? (
                          <div className="whitespace-pre-wrap">{call.output_summary}</div>
                        ) : (
                          <div className="italic text-slate-600">No summary recorded.</div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
