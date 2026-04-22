import { useState } from 'react'
import { Pencil, Trash2, GripVertical, ChevronsUp, ChevronsDown, PiggyBank } from 'lucide-react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { ExpenseItem } from '../../types'
import { FREQ_LABELS, formatDueBadge } from './ExpenseItemsEditor.helpers'

export function SortableExpenseRow({
  item, index, total, prefix, periodLabel,
  onEdit, onDelete, onMoveToTop, onMoveToBottom, onMoveTo,
}: {
  item: ExpenseItem
  index: number
  total: number
  prefix: string
  periodLabel: string
  onEdit: (item: ExpenseItem) => void
  onDelete: (id: number) => void
  onMoveToTop: (id: number) => void
  onMoveToBottom: (id: number) => void
  onMoveTo: (id: number, pos: number) => void
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.id })

  const [moveToInput, setMoveToInput] = useState('')
  const [showMoveTo, setShowMoveTo] = useState(false)

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  const badge = formatDueBadge(item)
  const position = index + 1

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-2 p-3 bg-slate-700/50 rounded-lg border border-slate-600 ${
        isDragging ? 'ring-2 ring-blue-500' : ''
      }`}
    >
      {/* Drag handle */}
      <div className="flex items-center gap-1 shrink-0">
        <button
          {...attributes}
          {...listeners}
          className="cursor-grab active:cursor-grabbing text-slate-500 hover:text-slate-300 touch-none"
          title="Drag to reorder"
        >
          <GripVertical className="w-4 h-4" />
        </button>
      </div>

      {/* Position badge */}
      <span className="text-[10px] font-mono text-slate-500 shrink-0 w-10 text-center"
        title={`Position ${position} of ${total}`}
      >
        #{position}/{total}
      </span>

      {/* Item details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {item.item_type === 'savings_target' ? (
            <span className="text-xs px-2 py-0.5 rounded bg-emerald-900/60 border border-emerald-700/50 text-emerald-300 flex items-center gap-1">
              <PiggyBank className="w-3 h-3" /> Savings
            </span>
          ) : (
            <span className="text-xs px-2 py-0.5 rounded bg-slate-600 text-slate-300">
              {item.category}
            </span>
          )}
          <span className="font-medium text-white truncate">{item.name}</span>
        </div>
        <div className="flex items-center gap-3 mt-1 text-xs text-slate-400 flex-wrap">
          {item.item_type === 'savings_target' ? (
            <>
              <span>
                Spend: {prefix}{(item.savings_target_amount || 0).toLocaleString()}
                {item.gross_target != null && item.gross_target > (item.savings_target_amount || 0) + 0.01 && (
                  <span className="text-slate-500"> → accumulate: {prefix}{item.gross_target.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                )}
                {' '}by {item.savings_target_date || '?'}
              </span>
              {/* Capital reservation framing — dynamic based on sort position */}
              {item.waterfall_status === 'blocked' ? (
                <span className="text-indigo-300 font-medium">
                  Blocked — need {prefix}{(item.capital_required ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              ) : item.capital_required != null ? (
                item.capital_gap === 0 ? (
                  <span className="text-emerald-400 font-medium">
                    {item.dynamic_reserved != null
                      ? `Reserved: ${prefix}${(item.dynamic_reserved).toLocaleString(undefined, { maximumFractionDigits: 0 })} ✓`
                      : 'Funded by growth'}
                  </span>
                ) : (
                  <>
                    <span className="text-slate-500">|</span>
                    <span>Need: {prefix}{(item.capital_required).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                    {item.dynamic_reserved != null && item.dynamic_reserved > 0 && (
                      <span className="text-slate-400">
                        reserved: {prefix}{(item.dynamic_reserved).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </span>
                    )}
                    <span className="text-amber-400">
                      gap: {prefix}{(item.capital_gap ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                    {(item.monthly_contribution ?? 0) > 0 && (
                      <span className="text-slate-400">
                        or {prefix}{(item.monthly_contribution ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo from income
                      </span>
                    )}
                  </>
                )
              ) : (
                item.savings_current_balance != null && item.savings_target_amount != null && item.savings_target_amount > 0 && (
                  <span className="text-emerald-400">
                    {Math.round((item.savings_current_balance / item.savings_target_amount) * 100)}% saved
                  </span>
                )
              )}
              {item.effective_growth_rate_pct != null && item.effective_growth_rate_pct > 0 && (
                <span className="text-[10px] text-slate-500">
                  @ {item.effective_growth_rate_pct.toFixed(1)}%/yr
                  {item.growth_rate_source === 'account' && <span className="text-emerald-500/70"> (auto)</span>}
                </span>
              )}
            </>
          ) : (
            <>
              {item.amount_mode === 'percent_of_income' ? (
                <span>
                  {item.percent_of_income}% {item.percent_basis === 'post_tax' ? 'post-tax' : 'pre-tax'}
                </span>
              ) : (
                <>
                  <span>
                    {prefix}{item.amount.toLocaleString()}{FREQ_LABELS[item.frequency] || ''}
                  </span>
                  {item.frequency === 'every_n_days' && item.frequency_n && (
                    <span>(every {item.frequency_n} days)</span>
                  )}
                </>
              )}
              {badge && (
                <span className="px-1.5 py-0.5 rounded bg-slate-600/50 text-slate-300 text-[10px]">
                  {badge}
                </span>
              )}
              <span className="text-slate-500">|</span>
              <span className="text-blue-400">
                {prefix}{(item.normalized_amount || 0).toLocaleString(
                  undefined, { maximumFractionDigits: 2 }
                )}{periodLabel}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-0.5 ml-2 shrink-0">
        <button
          onClick={() => onMoveToTop(item.id)}
          disabled={index === 0}
          className="p-1 text-slate-500 hover:text-white disabled:opacity-30 transition-colors"
          title="Move to top"
        >
          <ChevronsUp className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => onMoveToBottom(item.id)}
          disabled={index === total - 1}
          className="p-1 text-slate-500 hover:text-white disabled:opacity-30 transition-colors"
          title="Move to bottom"
        >
          <ChevronsDown className="w-3.5 h-3.5" />
        </button>
        <div className="relative">
          <button
            onClick={() => setShowMoveTo(!showMoveTo)}
            className="p-1 text-slate-500 hover:text-white transition-colors text-[10px] font-mono"
            title="Move to position..."
          >
            #
          </button>
          {showMoveTo && (
            <div className="absolute right-0 top-full mt-1 z-20 bg-slate-700 border border-slate-600
              rounded p-1.5 flex items-center gap-1 shadow-lg">
              <input
                type="number"
                min="1"
                max={total}
                step="1"
                value={moveToInput}
                onChange={e => {
                  const v = e.target.value.replace(/[^0-9]/g, '')
                  setMoveToInput(v)
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter' && moveToInput) {
                    onMoveTo(item.id, parseInt(moveToInput))
                    setShowMoveTo(false)
                    setMoveToInput('')
                  } else if (e.key === 'Escape') {
                    setShowMoveTo(false)
                    setMoveToInput('')
                  }
                }}
                placeholder={`1-${total}`}
                autoFocus
                className="w-14 px-1.5 py-0.5 bg-slate-800 border border-slate-500 rounded text-xs
                  text-white focus:outline-none focus:border-blue-500 placeholder-slate-500"
              />
              <button
                onClick={() => {
                  if (moveToInput) {
                    onMoveTo(item.id, parseInt(moveToInput))
                    setShowMoveTo(false)
                    setMoveToInput('')
                  }
                }}
                className="px-1.5 py-0.5 bg-blue-600 text-white text-[10px] rounded hover:bg-blue-700"
              >
                Go
              </button>
            </div>
          )}
        </div>
        <button
          onClick={() => onEdit(item)}
          className="p-1.5 text-slate-400 hover:text-white transition-colors"
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => onDelete(item.id)}
          className="p-1.5 text-slate-400 hover:text-red-400 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}
