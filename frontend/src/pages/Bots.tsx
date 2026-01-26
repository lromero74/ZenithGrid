import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { Bot } from '../types'
import { Plus, Activity, Building2, Wallet } from 'lucide-react'
import AIBotLogs from '../components/AIBotLogs'
import IndicatorLogs from '../components/IndicatorLogs'
import ScannerLogs from '../components/ScannerLogs'
import { PnLChart, TimeRange } from '../components/PnLChart'
import { useAccount, getChainName } from '../contexts/AccountContext'
import {
  type BotFormData,
  type ValidationWarning,
  type ValidationError,
  getDefaultFormData,
} from '../components/bots'
import { useValidation } from './bots/hooks/useValidation'
import { useBotsData } from './bots/hooks/useBotsData'
import { useBotMutations } from './bots/hooks/useBotMutations'
import { BotFormModal } from './bots/components/BotFormModal'
import { BotListItem } from './bots/components/BotListItem'

function Bots() {
  const location = useLocation()
  const { selectedAccount, accounts } = useAccount()
  const [showModal, setShowModal] = useState(false)
  const [editingBot, setEditingBot] = useState<Bot | null>(null)
  const [aiLogsBotId, setAiLogsBotId] = useState<number | null>(null)
  const [indicatorLogsBotId, setIndicatorLogsBotId] = useState<number | null>(null)
  const [scannerLogsBotId, setScannerLogsBotId] = useState<number | null>(null)
  const [openMenuId, setOpenMenuId] = useState<number | null>(null)
  const [validationWarnings, setValidationWarnings] = useState<ValidationWarning[]>([])
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([])
  const [formData, setFormData] = useState<BotFormData>(getDefaultFormData())
  const [projectionTimeframe, setProjectionTimeframe] = useState<TimeRange>('all')

  // Fetch all data
  const {
    bots,
    botsLoading,
    botsFetching: _botsFetching,
    strategies,
    portfolio,
    aggregateData,
    templates,
    TRADING_PAIRS
  } = useBotsData({ selectedAccount, projectionTimeframe })

  // Use validation hook
  const { validateBotConfig, validateManualOrderSizing } = useValidation({
    formData,
    setValidationWarnings,
    setValidationErrors,
    portfolio
  })

  // Check for bot to edit from navigation state (from Dashboard Edit button)
  useEffect(() => {
    const state = location.state as { editBot?: Bot } | null
    if (state?.editBot) {
      const bot = state.editBot
      // Open modal and set bot for editing
      setEditingBot(bot)
      // Handle both legacy single pair and new multi-pair bots
      const productIds = (bot as any).product_ids || (bot.product_id ? [bot.product_id] : [])
      setFormData({
        name: bot.name,
        description: bot.description || '',
        reserved_btc_balance: bot.reserved_btc_balance || 0,
        reserved_usd_balance: bot.reserved_usd_balance || 0,
        budget_percentage: bot.budget_percentage || 0,
        check_interval_seconds: (bot as any).check_interval_seconds || 300,
        strategy_type: bot.strategy_type,
        product_id: bot.product_id,  // Keep for backward compatibility
        product_ids: productIds,
        split_budget_across_pairs: (bot as any).split_budget_across_pairs || false,
        strategy_config: bot.strategy_config,
        exchange_type: bot.exchange_type || 'cex',
      })
      setShowModal(true)
      // Clear navigation state to prevent reopening on refresh
      window.history.replaceState({}, '')
    }
  }, [location])

  // Auto-validate when relevant fields change
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      validateBotConfig()
      validateManualOrderSizing()
    }, 500) // Debounce 500ms

    return () => clearTimeout(timeoutId)
  }, [formData.product_ids, formData.strategy_config, portfolio])

  // Reset form helper function
  const resetForm = () => {
    setFormData(getDefaultFormData())
    setEditingBot(null)
  }

  // Use mutations hook
  const {
    createBot,
    updateBot,
    deleteBot,
    startBot,
    stopBot,
    cloneBot,
    copyToAccount,
    forceRunBot,
    cancelAllPositions,
    sellAllPositions
  } = useBotMutations({ selectedAccount, bots, setShowModal, resetForm })

  // Get selected strategy definition
  const selectedStrategy = strategies.find((s) => s.id === formData.strategy_type)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (openMenuId !== null) {
        const target = event.target as Element
        if (!target.closest('.relative')) {
          setOpenMenuId(null)
        }
      }
    }

    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [openMenuId])

  // ESC key handler to close modal
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && showModal) {
        setShowModal(false)
        resetForm()
      }
    }

    if (showModal) {
      document.addEventListener('keydown', handleEscape)
      return () => {
        document.removeEventListener('keydown', handleEscape)
      }
    }
  }, [showModal])

  const handleOpenCreate = () => {
    resetForm()
    setShowModal(true)
  }

  const handleOpenEdit = (bot: Bot) => {
    setEditingBot(bot)
    // Handle both legacy single pair and new multi-pair bots
    const productIds = (bot as any).product_ids || (bot.product_id ? [bot.product_id] : [])
    setFormData({
      name: bot.name,
      description: bot.description || '',
      reserved_btc_balance: bot.reserved_btc_balance || 0,
      reserved_usd_balance: bot.reserved_usd_balance || 0,
      budget_percentage: bot.budget_percentage || 0,
      check_interval_seconds: (bot as any).check_interval_seconds || 300,
      strategy_type: bot.strategy_type,
      product_id: bot.product_id,  // Keep for backward compatibility
      product_ids: productIds,
      split_budget_across_pairs: (bot as any).split_budget_across_pairs || false,
      strategy_config: bot.strategy_config,
      exchange_type: bot.exchange_type || 'cex',
    })
    setShowModal(true)
  }

  const handleDelete = (bot: Bot) => {
    if (bot.is_active) {
      alert('Cannot delete an active bot. Stop it first.')
      return
    }
    if (confirm(`Are you sure you want to delete "${bot.name}"?`)) {
      deleteBot.mutate(bot.id)
    }
  }

  if (botsLoading && bots.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">Loading bots...</div>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          {selectedAccount?.type === 'dex' ? (
            <Wallet className="w-8 h-8 text-orange-400" />
          ) : (
            <Building2 className="w-8 h-8 text-blue-400" />
          )}
          <div>
            <h2 className="text-2xl font-bold">Bot Management</h2>
            <p className="text-slate-400 text-sm mt-1">
              {selectedAccount && (
                <>
                  <span className="text-slate-300">{selectedAccount.name}</span>
                  {selectedAccount.type === 'dex' && selectedAccount.chain_id && (
                    <span className="text-slate-500"> ({getChainName(selectedAccount.chain_id)})</span>
                  )}
                  <span> • </span>
                </>
              )}
              Create and manage multiple trading bots
            </p>
          </div>
        </div>
        <button
          onClick={handleOpenCreate}
          className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>Create Bot</span>
        </button>
      </div>

      {/* P&L Chart - 3Commas-style (filtered by account) */}
      <div className="mb-6">
        <PnLChart
          accountId={selectedAccount?.id}
          onTimeRangeChange={setProjectionTimeframe}
        />
      </div>

      {/* Bot List - 3Commas-style Table */}
      {bots.length === 0 ? (
        <div className="bg-slate-800 rounded-lg p-12 text-center">
          <Activity className="w-16 h-16 text-slate-600 mx-auto mb-4" />
          <h3 className="text-xl font-semibold mb-2">
            No bots on {selectedAccount?.name || 'this account'}
          </h3>
          <p className="text-slate-400 mb-6">
            {selectedAccount?.is_paper_trading ? (
              <>
                This is your paper trading account. Create a bot here to test strategies risk-free with virtual funds.
                <br />
                <span className="text-slate-500 text-sm mt-2 block">
                  Toggle to Live Trading in the header to view your live account bots.
                </span>
              </>
            ) : (
              'Create your first trading bot to get started'
            )}
          </p>
          <button
            onClick={handleOpenCreate}
            className="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded font-medium transition-colors"
          >
            Create Your First Bot
          </button>
        </div>
      ) : (
        <>
        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-slate-900 border-b border-slate-700">
                  <th className="text-left px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Name</th>
                  <th className="text-left px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Strategy</th>
                  <th className="text-left px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Pair</th>
                  <th className="text-left px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Active trades</th>
                  <th className="text-right px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Trade Stats</th>
                  <th className="text-right px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Win Rate</th>
                  <th className="text-right px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">PnL</th>
                  <th className="text-right px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Projected PnL</th>
                  <th className="text-left px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Budget</th>
                  <th className="text-center px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Status</th>
                  <th className="text-center px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Actions</th>
                </tr>
              </thead>
              <tbody>
                {bots.map((bot) => (
                  <BotListItem
                    key={bot.id}
                    bot={bot}
                    strategies={strategies}
                    handleOpenEdit={handleOpenEdit}
                    handleDelete={handleDelete}
                    startBot={startBot}
                    stopBot={stopBot}
                    cloneBot={cloneBot}
                    copyToAccount={copyToAccount}
                    accounts={accounts}
                    currentAccountId={selectedAccount?.id}
                    forceRunBot={forceRunBot}
                    cancelAllPositions={cancelAllPositions}
                    sellAllPositions={sellAllPositions}
                    openMenuId={openMenuId}
                    setOpenMenuId={setOpenMenuId}
                    setAiLogsBotId={setAiLogsBotId}
                    setIndicatorLogsBotId={setIndicatorLogsBotId}
                    setScannerLogsBotId={setScannerLogsBotId}
                    portfolio={portfolio}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Summary Totals Table */}
        <div className="mt-4 bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <table className="w-full">
            <thead className="bg-slate-900">
              <tr>
                <th className="text-left px-1 sm:px-2 py-2 text-sm font-medium text-slate-400">Portfolio Totals</th>
                <th className="text-right px-1 sm:px-2 py-2 text-sm font-medium text-slate-400">Daily</th>
                <th className="text-right px-1 sm:px-2 py-2 text-sm font-medium text-slate-400">Weekly</th>
                <th className="text-right px-1 sm:px-2 py-2 text-sm font-medium text-slate-400">Monthly</th>
                <th className="text-right px-1 sm:px-2 py-2 text-sm font-medium text-slate-400">Yearly</th>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const totalDailyPnl = bots.reduce((sum, bot) => sum + ((bot as any).avg_daily_pnl_usd || 0), 0)
                const portfolioUsd = portfolio?.total_usd_value || 0

                // Calculate daily rate as a decimal (e.g., 0.0009 for 0.09%)
                const dailyRate = portfolioUsd > 0 ? totalDailyPnl / portfolioUsd : 0

                // Use simple linear projection (no compounding)
                // Compounding daily rates leads to unrealistic projections, especially for short timeframes
                // Linear projection: avg_daily_pnl × number_of_days
                const projectPnl = (days: number) => totalDailyPnl * days

                const totalWeeklyPnl = projectPnl(7)
                const totalMonthlyPnl = projectPnl(30)
                const totalYearlyPnl = projectPnl(365)

                const isPositive = totalDailyPnl > 0
                const isNegative = totalDailyPnl < 0
                const colorClass = isPositive ? 'text-green-400' : isNegative ? 'text-red-400' : 'text-slate-400'
                const prefix = isPositive ? '+' : ''

                // Calculate percentage gains based on portfolio value (also compounded)
                const dailyPct = dailyRate * 100
                const weeklyPct = portfolioUsd > 0 ? (totalWeeklyPnl / portfolioUsd) * 100 : 0
                const monthlyPct = portfolioUsd > 0 ? (totalMonthlyPnl / portfolioUsd) * 100 : 0
                const yearlyPct = portfolioUsd > 0 ? (totalYearlyPnl / portfolioUsd) * 100 : 0
                const pctPrefix = isPositive ? '+' : ''

                // Format percentage - only show placeholder if we don't have portfolio value yet
                const formatPct = (pct: number) => {
                  if (portfolioUsd === 0) return '--'
                  return `${pctPrefix}${pct.toFixed(2)}`
                }

                return (
                  <tr>
                    <td className="px-1 sm:px-2 py-2 text-sm font-semibold text-slate-300">Projected PnL</td>
                    <td className={`px-1 sm:px-2 py-2 text-right text-lg font-bold ${colorClass}`}>
                      {prefix}${totalDailyPnl.toFixed(2)}
                      <span className="text-xs ml-1 text-slate-400">
                        ({formatPct(dailyPct)}%)
                      </span>
                    </td>
                    <td className={`px-1 sm:px-2 py-2 text-right text-lg font-bold ${colorClass}`}>
                      {prefix}${totalWeeklyPnl.toFixed(2)}
                      <span className="text-xs ml-1 text-slate-400">
                        ({formatPct(weeklyPct)}%)
                      </span>
                    </td>
                    <td className={`px-1 sm:px-2 py-2 text-right text-lg font-bold ${colorClass}`}>
                      {prefix}${totalMonthlyPnl.toFixed(2)}
                      <span className="text-xs ml-1 text-slate-400">
                        ({formatPct(monthlyPct)}%)
                      </span>
                    </td>
                    <td className={`px-1 sm:px-2 py-2 text-right text-lg font-bold ${colorClass}`}>
                      {prefix}${totalYearlyPnl.toFixed(2)}
                      <span className="text-xs ml-1 text-slate-400">
                        ({formatPct(yearlyPct)}%)
                      </span>
                    </td>
                  </tr>
                )
              })()}
            </tbody>
          </table>
        </div>
        </>
      )}

      {/* Create/Edit Modal */}
      <BotFormModal
        showModal={showModal}
        setShowModal={setShowModal}
        editingBot={editingBot}
        formData={formData}
        setFormData={setFormData}
        templates={templates}
        strategies={strategies}
        TRADING_PAIRS={TRADING_PAIRS}
        selectedStrategy={selectedStrategy}
        validationWarnings={validationWarnings}
        validationErrors={validationErrors}
        selectedAccount={selectedAccount}
        createBot={createBot}
        updateBot={updateBot}
        resetForm={resetForm}
        aggregateData={aggregateData}
      />

      {/* AI Bot Logs Modal */}
      {aiLogsBotId !== null && (
        <AIBotLogs
          botId={aiLogsBotId}
          isOpen={aiLogsBotId !== null}
          onClose={() => setAiLogsBotId(null)}
        />
      )}

      {/* Indicator Logs Modal */}
      {indicatorLogsBotId !== null && (
        <IndicatorLogs
          botId={indicatorLogsBotId}
          isOpen={indicatorLogsBotId !== null}
          onClose={() => setIndicatorLogsBotId(null)}
        />
      )}

      {/* Scanner Logs Modal */}
      {scannerLogsBotId !== null && (
        <ScannerLogs
          botId={scannerLogsBotId}
          isOpen={scannerLogsBotId !== null}
          onClose={() => setScannerLogsBotId(null)}
        />
      )}
    </div>
  )
}

export default Bots
