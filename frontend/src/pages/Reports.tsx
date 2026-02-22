import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Target, Calendar, FileText, Plus, Pencil, Trash2, Play, Eye, Download,
  CheckCircle, Clock, AlertCircle, ChevronLeft, ChevronRight, Receipt
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { reportsApi } from '../services/api'
import { GoalForm, type GoalFormData } from '../components/reports/GoalForm'
import { ScheduleForm, type ScheduleFormData } from '../components/reports/ScheduleForm'
import { ReportViewModal } from '../components/reports/ReportViewModal'
import { GoalProgressBar } from '../components/reports/GoalProgressBar'
import { ExpenseItemsEditor } from '../components/reports/ExpenseItemsEditor'
import type { ReportGoal, ReportSchedule, ReportSummary } from '../types'

type TabId = 'goals' | 'schedules' | 'history'

const TABS: { id: TabId; label: string; icon: typeof Target }[] = [
  { id: 'goals', label: 'Goals', icon: Target },
  { id: 'schedules', label: 'Schedules', icon: Calendar },
  { id: 'history', label: 'Report History', icon: FileText },
]

const VALID_TABS = new Set<string>(['goals', 'schedules', 'history'])

export default function Reports() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const activeTab: TabId = (tabParam && VALID_TABS.has(tabParam) ? tabParam : 'goals') as TabId
  const queryClient = useQueryClient()

  const setActiveTab = (tab: TabId) => {
    setSearchParams({ tab }, { replace: true })
  }

  // Goal state
  const [showGoalForm, setShowGoalForm] = useState(false)
  const [editingGoal, setEditingGoal] = useState<ReportGoal | null>(null)
  const [expenseEditorGoal, setExpenseEditorGoal] = useState<ReportGoal | null>(null)

  // Schedule state
  const [showScheduleForm, setShowScheduleForm] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState<ReportSchedule | null>(null)

  // Report view state
  const [viewingReport, setViewingReport] = useState<ReportSummary | null>(null)

  // History pagination
  const [historyPage, setHistoryPage] = useState(0)
  const PAGE_SIZE = 20

  // ---------- Queries ----------

  const { data: goals = [], isLoading: goalsLoading } = useQuery({
    queryKey: ['report-goals'],
    queryFn: reportsApi.getGoals,
  })

  const { data: schedules = [], isLoading: schedulesLoading } = useQuery({
    queryKey: ['report-schedules'],
    queryFn: reportsApi.getSchedules,
  })

  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ['report-history', historyPage],
    queryFn: () => reportsApi.getHistory(PAGE_SIZE, historyPage * PAGE_SIZE),
  })

  // ---------- Mutations ----------

  const createGoal = useMutation({
    mutationFn: (data: GoalFormData) => reportsApi.createGoal(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-goals'] }),
  })

  const updateGoal = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ReportGoal> }) =>
      reportsApi.updateGoal(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-goals'] }),
  })

  const deleteGoal = useMutation({
    mutationFn: (id: number) => reportsApi.deleteGoal(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-goals'] }),
  })

  const createSchedule = useMutation({
    mutationFn: (data: ScheduleFormData) => reportsApi.createSchedule(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-schedules'] }),
  })

  const updateSchedule = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ReportSchedule & { goal_ids?: number[] }> }) =>
      reportsApi.updateSchedule(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-schedules'] }),
  })

  const deleteSchedule = useMutation({
    mutationFn: (id: number) => reportsApi.deleteSchedule(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-schedules'] }),
  })

  const generateReport = useMutation({
    mutationFn: (scheduleId: number) => reportsApi.generateReport(scheduleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['report-history'] })
      queryClient.invalidateQueries({ queryKey: ['report-schedules'] })
    },
  })

  const deleteReport = useMutation({
    mutationFn: (id: number) => reportsApi.deleteReport(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['report-history'] }),
  })

  // ---------- Handlers ----------

  const handleViewReport = useCallback(async (reportId: number) => {
    const report = await reportsApi.getReport(reportId)
    setViewingReport(report)
  }, [])

  const handleDownloadPdf = useCallback(async (reportId: number) => {
    const blob = await reportsApi.downloadPdf(reportId)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report_${reportId}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  }, [])

  const handleDeleteReport = useCallback((reportId: number) => {
    if (confirm('Delete this report? This cannot be undone.')) {
      deleteReport.mutate(reportId)
    }
  }, [deleteReport])

  // ---------- Render Helpers ----------

  const formatDate = (iso: string | null) => {
    if (!iso) return '-'
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric'
    })
  }

  const formatDateTime = (iso: string | null) => {
    if (!iso) return '-'
    const d = new Date(iso)
    return d.toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric'
    }) + ' ' + d.toLocaleTimeString('en-US', {
      hour: 'numeric', minute: '2-digit'
    })
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'sent':
        return <span className="inline-flex items-center gap-1 text-xs text-emerald-400"><CheckCircle className="w-3 h-3" /> Sent</span>
      case 'pending':
        return <span className="inline-flex items-center gap-1 text-xs text-amber-400"><Clock className="w-3 h-3" /> Pending</span>
      case 'failed':
        return <span className="inline-flex items-center gap-1 text-xs text-red-400"><AlertCircle className="w-3 h-3" /> Failed</span>
      case 'manual':
        return <span className="inline-flex items-center gap-1 text-xs text-blue-400"><FileText className="w-3 h-3" /> Manual</span>
      default:
        return <span className="text-xs text-slate-400">{status}</span>
    }
  }

  const getTimeRemaining = (targetDate: string | null) => {
    if (!targetDate) return ''
    const now = new Date()
    const target = new Date(targetDate)
    const diffMs = target.getTime() - now.getTime()
    if (diffMs <= 0) return 'Past due'
    const days = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    if (days > 365) return `${Math.floor(days / 365)}y ${Math.floor((days % 365) / 30)}m`
    if (days > 30) return `${Math.floor(days / 30)}m ${days % 30}d`
    return `${days}d`
  }

  // ---------- Tab Content ----------

  const renderGoalsTab = () => (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-white">Financial Goals</h3>
        <button
          onClick={() => { setEditingGoal(null); setShowGoalForm(true) }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" /> Add Goal
        </button>
      </div>

      {goalsLoading ? (
        <div className="text-center py-8 text-slate-400">Loading goals...</div>
      ) : goals.length === 0 ? (
        <div className="text-center py-12">
          <Target className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">No goals yet. Create one to start tracking progress.</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {goals.map(goal => {
            // Simple client-side progress calculation
            const now = new Date()
            const start = new Date(goal.start_date || now)
            const target = new Date(goal.target_date || now)
            const totalMs = target.getTime() - start.getTime()
            const elapsedMs = now.getTime() - start.getTime()
            const timePct = totalMs > 0 ? Math.min((elapsedMs / totalMs) * 100, 100) : 100

            return (
              <div key={goal.id} className="bg-slate-800 border border-slate-700 rounded-lg p-4">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h4 className="font-medium text-white">{goal.name}</h4>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-slate-400">
                        {goal.target_type === 'balance' ? 'Balance' :
                         goal.target_type === 'profit' ? 'Profit' :
                         goal.target_type === 'income' ? 'Income' :
                         goal.target_type === 'expenses' ? 'Expenses' : 'Balance & Profit'} target
                      </span>
                      {goal.target_date && (
                        <span className="inline-flex items-center gap-1 text-xs bg-blue-900/40 text-blue-300 border border-blue-800/50 px-1.5 py-0.5 rounded">
                          <Calendar className="w-3 h-3" />
                          {formatDate(goal.target_date)}
                        </span>
                      )}
                      <span className="text-xs text-slate-500">
                        {getTimeRemaining(goal.target_date)} remaining
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {!goal.is_active && (
                      <span className="text-xs bg-slate-700 text-slate-400 px-2 py-0.5 rounded">Inactive</span>
                    )}
                    <button
                      onClick={() => { setEditingGoal(goal); setShowGoalForm(true) }}
                      className="p-1 text-slate-400 hover:text-blue-400 transition-colors"
                      title="Edit"
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => { if (confirm('Delete this goal?')) deleteGoal.mutate(goal.id) }}
                      className="p-1 text-slate-400 hover:text-red-400 transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Target display */}
                <div className="flex items-center gap-2 mb-2">
                  {goal.target_type === 'expenses' ? (
                    <div className="flex items-center gap-3 w-full">
                      <span className="text-lg font-semibold text-white">
                        {goal.target_currency === 'BTC'
                          ? `${goal.target_value} BTC`
                          : `$${goal.target_value.toLocaleString()}`}
                        <span className="text-sm text-slate-400 font-normal">
                          /{goal.expense_period || 'month'}
                        </span>
                      </span>
                      <span className="text-xs text-slate-500">
                        {goal.expense_item_count || 0} item{(goal.expense_item_count || 0) !== 1 ? 's' : ''}
                      </span>
                      {(goal.tax_withholding_pct || 0) > 0 && (
                        <span className="text-xs bg-amber-900/30 text-amber-400 px-1.5 py-0.5 rounded">
                          {goal.tax_withholding_pct}% tax
                        </span>
                      )}
                      <button
                        onClick={() => setExpenseEditorGoal(goal)}
                        className="ml-auto flex items-center gap-1 text-xs bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 px-2.5 py-1 rounded transition-colors"
                      >
                        <Receipt className="w-3 h-3" /> Manage Expenses
                      </button>
                    </div>
                  ) : (
                    <span className="text-lg font-semibold text-white">
                      {goal.target_currency === 'BTC'
                        ? `${goal.target_value} BTC`
                        : `$${goal.target_value.toLocaleString()}`}
                      {goal.target_type === 'income' && goal.income_period && (
                        <span className="text-sm text-slate-400 font-normal">
                          /{goal.income_period === 'daily' ? 'day' :
                            goal.income_period === 'weekly' ? 'week' :
                            goal.income_period === 'monthly' ? 'month' : 'year'}
                        </span>
                      )}
                    </span>
                  )}
                </div>

                {/* Time progress bar (since we can't know account value client-side) */}
                <div className="mb-1">
                  <div className="flex justify-between text-xs text-slate-400 mb-1">
                    <span>Time elapsed</span>
                    <span>{timePct.toFixed(0)}%</span>
                  </div>
                  <GoalProgressBar progress={timePct} onTrack={timePct < 80} size="sm" />
                </div>

                <p className="text-xs text-slate-500 mt-2">
                  {formatDate(goal.start_date)} &rarr; {formatDate(goal.target_date)}
                </p>

              </div>
            )
          })}
        </div>
      )}
    </div>
  )

  const renderSchedulesTab = () => (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-white">Report Schedules</h3>
        <button
          onClick={() => { setEditingSchedule(null); setShowScheduleForm(true) }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" /> Add Schedule
        </button>
      </div>

      {schedulesLoading ? (
        <div className="text-center py-8 text-slate-400">Loading schedules...</div>
      ) : schedules.length === 0 ? (
        <div className="text-center py-12">
          <Calendar className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">No schedules yet. Create one to start receiving reports.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {schedules.map(schedule => (
            <div key={schedule.id} className="bg-slate-800 border border-slate-700 rounded-lg p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h4 className="font-medium text-white">{schedule.name}</h4>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      schedule.is_enabled
                        ? 'bg-emerald-900/50 text-emerald-400 border border-emerald-800'
                        : 'bg-slate-700 text-slate-400'
                    }`}>
                      {schedule.is_enabled ? 'Active' : 'Paused'}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-3 mt-1.5 text-xs text-slate-400">
                    <span>{schedule.periodicity}</span>
                    {schedule.recipients.length > 0 && (
                      <span>{schedule.recipients.length} recipient{schedule.recipients.length > 1 ? 's' : ''}</span>
                    )}
                    {schedule.goal_ids.length > 0 && (
                      <span>{schedule.goal_ids.length} goal{schedule.goal_ids.length > 1 ? 's' : ''} linked</span>
                    )}
                    {schedule.next_run_at && (
                      <span>Next: {formatDate(schedule.next_run_at)}</span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1 ml-3">
                  <button
                    onClick={() => {
                      if (confirm('Generate a report now?')) generateReport.mutate(schedule.id)
                    }}
                    disabled={generateReport.isPending}
                    className="p-1.5 text-slate-400 hover:text-emerald-400 transition-colors"
                    title="Generate Now"
                  >
                    <Play className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => { setEditingSchedule(schedule); setShowScheduleForm(true) }}
                    className="p-1.5 text-slate-400 hover:text-blue-400 transition-colors"
                    title="Edit"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => { if (confirm('Delete this schedule?')) deleteSchedule.mutate(schedule.id) }}
                    className="p-1.5 text-slate-400 hover:text-red-400 transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  const renderHistoryTab = () => {
    const reports = historyData?.reports || []
    const total = historyData?.total || 0
    const totalPages = Math.ceil(total / PAGE_SIZE)

    return (
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-white">
            Report History
            {total > 0 && <span className="text-sm text-slate-400 ml-2">({total} total)</span>}
          </h3>
        </div>

        {historyLoading ? (
          <div className="text-center py-8 text-slate-400">Loading reports...</div>
        ) : reports.length === 0 ? (
          <div className="text-center py-12">
            <FileText className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">No reports generated yet.</p>
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Report</th>
                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Period</th>
                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Status</th>
                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Created</th>
                    <th className="text-right py-2 px-3 text-xs font-medium text-slate-400">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map(report => (
                    <tr key={report.id} className="border-b border-slate-700/50 hover:bg-slate-800/50">
                      <td className="py-2.5 px-3">
                        <div className="text-sm text-slate-200">{report.schedule_name || report.periodicity}</div>
                        <div className="text-xs text-slate-500">{report.periodicity}</div>
                      </td>
                      <td className="py-2.5 px-3 text-sm text-slate-300">
                        {formatDate(report.period_start)} — {formatDate(report.period_end)}
                      </td>
                      <td className="py-2.5 px-3">{getStatusBadge(report.delivery_status)}</td>
                      <td className="py-2.5 px-3 text-sm text-slate-400">{formatDateTime(report.created_at)}</td>
                      <td className="py-2.5 px-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleViewReport(report.id)}
                            className="p-1.5 text-slate-400 hover:text-blue-400 transition-colors"
                            title="View Report"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          {report.has_pdf && (
                            <button
                              onClick={() => handleDownloadPdf(report.id)}
                              className="p-1.5 text-slate-400 hover:text-emerald-400 transition-colors"
                              title="Download PDF"
                            >
                              <Download className="w-4 h-4" />
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteReport(report.id)}
                            className="p-1.5 text-slate-400 hover:text-red-400 transition-colors"
                            title="Delete Report"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="sm:hidden space-y-2">
              {reports.map(report => (
                <div key={report.id} className="bg-slate-800 border border-slate-700 rounded-lg p-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm text-white">
                        {formatDate(report.period_start)} — {formatDate(report.period_end)}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs text-slate-400 capitalize">{report.periodicity}</span>
                        {getStatusBadge(report.delivery_status)}
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleViewReport(report.id)}
                        className="p-1.5 text-slate-400 hover:text-blue-400"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      {report.has_pdf && (
                        <button
                          onClick={() => handleDownloadPdf(report.id)}
                          className="p-1.5 text-slate-400 hover:text-emerald-400"
                        >
                          <Download className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteReport(report.id)}
                        className="p-1.5 text-slate-400 hover:text-red-400"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-3 mt-4">
                <button
                  onClick={() => setHistoryPage(p => Math.max(0, p - 1))}
                  disabled={historyPage === 0}
                  className="p-1.5 text-slate-400 hover:text-white disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <span className="text-sm text-slate-400">
                  Page {historyPage + 1} of {totalPages}
                </span>
                <button
                  onClick={() => setHistoryPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={historyPage >= totalPages - 1}
                  className="p-1.5 text-slate-400 hover:text-white disabled:opacity-30 transition-colors"
                >
                  <ChevronRight className="w-5 h-5" />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    )
  }

  return (
    <div>
      {/* Tab navigation */}
      <div className="flex space-x-1 border-b border-slate-700 mb-6">
        {TABS.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      {activeTab === 'goals' && renderGoalsTab()}
      {activeTab === 'schedules' && renderSchedulesTab()}
      {activeTab === 'history' && renderHistoryTab()}

      {/* Modals */}
      <GoalForm
        isOpen={showGoalForm}
        onClose={() => { setShowGoalForm(false); setEditingGoal(null) }}
        onSubmit={async (data) => {
          if (editingGoal) {
            await updateGoal.mutateAsync({ id: editingGoal.id, data })
          } else {
            const created = await createGoal.mutateAsync(data)
            if (created.target_type === 'expenses') {
              setExpenseEditorGoal(created)
            }
          }
        }}
        initialData={editingGoal}
      />

      <ScheduleForm
        isOpen={showScheduleForm}
        onClose={() => { setShowScheduleForm(false); setEditingSchedule(null) }}
        onSubmit={async (data) => {
          if (editingSchedule) {
            await updateSchedule.mutateAsync({ id: editingSchedule.id, data })
          } else {
            await createSchedule.mutateAsync(data)
          }
        }}
        goals={goals}
        initialData={editingSchedule}
      />

      <ReportViewModal
        isOpen={!!viewingReport}
        onClose={() => setViewingReport(null)}
        htmlContent={viewingReport?.html_content || null}
        title={viewingReport
          ? `Report: ${formatDate(viewingReport.period_start)} — ${formatDate(viewingReport.period_end)}`
          : ''}
        hasPdf={viewingReport?.has_pdf}
        onDownloadPdf={viewingReport ? () => handleDownloadPdf(viewingReport.id) : undefined}
      />

      {expenseEditorGoal && (
        <ExpenseItemsEditor
          goalId={expenseEditorGoal.id}
          expensePeriod={expenseEditorGoal.expense_period || 'monthly'}
          currency={expenseEditorGoal.target_currency}
          onClose={() => setExpenseEditorGoal(null)}
        />
      )}
    </div>
  )
}
