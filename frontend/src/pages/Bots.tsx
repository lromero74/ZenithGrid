import { useState, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { Bot } from '../types'
import { Plus, Activity, Building2, Wallet, Upload, ClipboardPaste, X, CheckCircle, AlertCircle } from 'lucide-react'
import AIBotLogs from '../components/AIBotLogs'
import IndicatorLogs from '../components/IndicatorLogs'
import ScannerLogs from '../components/ScannerLogs'
import { PnLChart, TimeRange } from '../components/PnLChart'
import { SeasonalityToggle } from '../components/SeasonalityToggle'
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
  const [projectionBasis, setProjectionBasis] = useState<TimeRange>(() => {
    try { const saved = localStorage.getItem('zenith-bots-projection-basis'); return (saved as TimeRange) || '7d' } catch { return '7d' }
  })
  const [showImportModal, setShowImportModal] = useState(false)
  const [importMode, setImportMode] = useState<'file' | 'paste'>('file')
  const [pasteInput, setPasteInput] = useState('')
  const [importValidation, setImportValidation] = useState<{
    isValid: boolean | null
    errors: string[]
    warnings: string[]
    parsedData: any | null
  }>({ isValid: null, errors: [], warnings: [], parsedData: null })
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [showStoppedBots, setShowStoppedBots] = useState(() => {
    try { return localStorage.getItem('zenith-show-stopped-bots') !== 'false' } catch { return true }
  })
  useEffect(() => { try { localStorage.setItem('zenith-show-stopped-bots', String(showStoppedBots)) } catch { /* ignored */ } }, [showStoppedBots])
  useEffect(() => { try { localStorage.setItem('zenith-bots-projection-basis', projectionBasis) } catch { /* ignored */ } }, [projectionBasis])

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
  } = useBotsData({ selectedAccount, projectionTimeframe: projectionBasis })

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

  // Handle opening cloned bot in edit modal
  const handleCloneSuccess = (clonedBot: Bot) => {
    // Open the cloned bot in edit modal so user can review/modify
    const productIds = (clonedBot as any).product_ids || (clonedBot.product_id ? [clonedBot.product_id] : [])
    setEditingBot(clonedBot)
    setFormData({
      name: clonedBot.name,
      description: clonedBot.description || '',
      reserved_btc_balance: clonedBot.reserved_btc_balance || 0,
      reserved_usd_balance: clonedBot.reserved_usd_balance || 0,
      budget_percentage: clonedBot.budget_percentage || 0,
      check_interval_seconds: (clonedBot as any).check_interval_seconds || 300,
      strategy_type: clonedBot.strategy_type,
      product_id: clonedBot.product_id,
      product_ids: productIds,
      split_budget_across_pairs: (clonedBot as any).split_budget_across_pairs || false,
      strategy_config: clonedBot.strategy_config,
      exchange_type: clonedBot.exchange_type || 'cex',
    })
    setShowModal(true)
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
  } = useBotMutations({ selectedAccount, bots, setShowModal, resetForm, onCloneSuccess: handleCloneSuccess, projectionTimeframe: projectionBasis })

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

  // Validate imported bot JSON and check for duplicates
  const validateImportedBot = (jsonString: string): {
    isValid: boolean
    errors: string[]
    warnings: string[]
    parsedData: any | null
  } => {
    const errors: string[] = []
    const warnings: string[] = []
    let parsedData: any = null

    // Step 1: Parse JSON
    try {
      parsedData = JSON.parse(jsonString)
    } catch (err) {
      return { isValid: false, errors: ['Invalid JSON format'], warnings: [], parsedData: null }
    }

    // Step 2: Check required fields
    if (!parsedData.strategy_type) {
      errors.push('Missing required field: strategy_type')
    }
    if (!parsedData.product_id && (!parsedData.product_ids || parsedData.product_ids.length === 0)) {
      errors.push('Missing required field: product_id or product_ids')
    }

    // Step 3: Validate strategy_type exists in our strategies
    if (parsedData.strategy_type && strategies.length > 0) {
      const strategyExists = strategies.some(s => s.id === parsedData.strategy_type)
      if (!strategyExists) {
        errors.push(`Unknown strategy type: "${parsedData.strategy_type}"`)
      }
    }

    // Step 4: Validate trading pairs exist
    const pairs = parsedData.product_ids || (parsedData.product_id ? [parsedData.product_id] : [])
    if (TRADING_PAIRS.length > 0) {
      const invalidPairs = pairs.filter((p: string) => !TRADING_PAIRS.some(tp => tp.value === p))
      if (invalidPairs.length > 0) {
        warnings.push(`Unknown trading pair(s): ${invalidPairs.join(', ')} - they may not be available`)
      }
    }

    // Step 5: Check for duplicate bot (same strategy_type, same pairs, same strategy_config)
    if (errors.length === 0) {
      const isDuplicate = bots.some(existingBot => {
        const existingPairs = (existingBot as any).product_ids || [existingBot.product_id]
        const newPairs = parsedData.product_ids || [parsedData.product_id]

        const sameStrategy = existingBot.strategy_type === parsedData.strategy_type
        const samePairs = existingPairs.length === newPairs.length &&
          existingPairs.every((p: string) => newPairs.includes(p))
        const sameConfig = JSON.stringify(existingBot.strategy_config) === JSON.stringify(parsedData.strategy_config)

        return sameStrategy && samePairs && sameConfig
      })

      if (isDuplicate) {
        warnings.push('A bot with identical configuration already exists')
      }
    }

    // Step 6: Validate budget_percentage if provided
    if (parsedData.budget_percentage !== undefined) {
      if (typeof parsedData.budget_percentage !== 'number' || parsedData.budget_percentage < 0 || parsedData.budget_percentage > 100) {
        errors.push('budget_percentage must be a number between 0 and 100')
      }
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings,
      parsedData
    }
  }

  // Validate input when it changes (for paste mode)
  const handlePasteInputChange = (value: string) => {
    setPasteInput(value)
    if (!value.trim()) {
      setImportValidation({ isValid: null, errors: [], warnings: [], parsedData: null })
      return
    }
    const validation = validateImportedBot(value)
    setImportValidation(validation)
  }

  // Handle file selection in modal
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result as string
      setPasteInput(content)
      const validation = validateImportedBot(content)
      setImportValidation(validation)
    }
    reader.readAsText(file)
    event.target.value = ''
  }

  const handleImportSubmit = () => {
    if (!importValidation.isValid || !importValidation.parsedData) return

    // Show warnings confirmation if any
    if (importValidation.warnings.length > 0) {
      const proceed = confirm(
        `Warnings:\n${importValidation.warnings.join('\n')}\n\nDo you want to import anyway?`
      )
      if (!proceed) return
    }

    const importedData = importValidation.parsedData
    const productIds = importedData.product_ids || [importedData.product_id || 'BTC-USD']

    // Populate the Create Bot form with imported data (don't create yet)
    // Note: exchange_type uses current account's type, not imported value
    setFormData({
      name: importedData.name ? `${importedData.name} (Imported)` : 'Imported Bot',
      description: importedData.description || '',
      strategy_type: importedData.strategy_type,
      strategy_config: importedData.strategy_config || {},
      product_id: productIds[0],
      product_ids: productIds,
      split_budget_across_pairs: importedData.split_budget_across_pairs || false,
      budget_percentage: importedData.budget_percentage || 10,
      exchange_type: selectedAccount?.type || 'cex',
      reserved_btc_balance: 0,
      reserved_usd_balance: 0,
      check_interval_seconds: importedData.strategy_config?.check_interval_seconds || 300,
    })

    // Close import modal and open create modal
    closeImportModal()
    setEditingBot(null) // Ensure it's a new bot, not editing
    setShowModal(true)
  }

  const closeImportModal = () => {
    setShowImportModal(false)
    setPasteInput('')
    setImportValidation({ isValid: null, errors: [], warnings: [], parsedData: null })
    setImportMode('file')
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
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowImportModal(true)}
            className="flex items-center space-x-2 bg-slate-700 hover:bg-slate-600 px-4 py-2 rounded font-medium transition-colors"
            title="Import bot from file or clipboard"
          >
            <Upload className="w-4 h-4" />
            <span>Import Bot</span>
          </button>
          <button
            onClick={handleOpenCreate}
            className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-medium transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Create Bot</span>
          </button>
        </div>
      </div>

      {/* Seasonality Toggle */}
      <SeasonalityToggle />

      {/* P&L Chart - 3Commas-style (filtered by account) */}
      <div className="mb-6">
        <PnLChart
          accountId={selectedAccount?.id}
          onTimeRangeChange={setProjectionBasis}
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
        {/* Toggle for stopped bots */}
        {bots.some(b => !b.is_active) && (
          <div className="flex justify-end mb-2">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <span className="text-sm text-slate-400">Show stopped</span>
              <div className="relative">
                <input
                  type="checkbox"
                  checked={showStoppedBots}
                  onChange={() => setShowStoppedBots(!showStoppedBots)}
                  className="peer sr-only"
                />
                <div className="w-9 h-5 bg-slate-600 rounded-full peer-checked:bg-blue-600 transition-colors" />
                <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-4" />
              </div>
            </label>
          </div>
        )}
        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-slate-900 border-b border-slate-700">
                  <th className="text-left px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Name</th>
                  <th className="text-left px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Strategy</th>
                  <th className="text-left px-1 sm:px-2 py-2 text-xs sm:text-sm font-medium text-slate-400">Pair</th>
                  <th className="text-left px-0.5 sm:px-1 py-2 text-xs sm:text-sm font-medium text-slate-400">Active trades</th>
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
                {bots.filter(b => showStoppedBots || b.is_active).map((bot) => (
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

      {/* Import Bot Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg shadow-xl border border-slate-700 w-full max-w-2xl mx-4">
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <h2 className="text-xl font-semibold">Import Bot</h2>
              <button
                onClick={closeImportModal}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Tab Selector */}
            <div className="flex border-b border-slate-700">
              <button
                onClick={() => {
                  setImportMode('file')
                  setPasteInput('')
                  setImportValidation({ isValid: null, errors: [], warnings: [], parsedData: null })
                }}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                  importMode === 'file'
                    ? 'text-blue-400 border-b-2 border-blue-400 bg-slate-700/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Upload className="w-4 h-4 inline mr-2" />
                From File
              </button>
              <button
                onClick={() => {
                  setImportMode('paste')
                  setPasteInput('')
                  setImportValidation({ isValid: null, errors: [], warnings: [], parsedData: null })
                }}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                  importMode === 'paste'
                    ? 'text-blue-400 border-b-2 border-blue-400 bg-slate-700/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <ClipboardPaste className="w-4 h-4 inline mr-2" />
                From Clipboard
              </button>
            </div>

            <div className="p-4 space-y-4">
              {importMode === 'file' ? (
                <>
                  <p className="text-slate-400 text-sm">
                    Select a JSON file containing a bot configuration.
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".json"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full py-8 border-2 border-dashed border-slate-600 rounded-lg hover:border-slate-500 hover:bg-slate-700/30 transition-colors"
                  >
                    <Upload className="w-8 h-8 mx-auto text-slate-400 mb-2" />
                    <div className="text-slate-300 font-medium">Click to select file</div>
                    <div className="text-slate-500 text-sm">or drag and drop a .json file</div>
                  </button>
                  {pasteInput && (
                    <div className="bg-slate-900 border border-slate-600 rounded-lg p-3 max-h-32 overflow-auto">
                      <pre className="text-xs font-mono text-slate-400 whitespace-pre-wrap">{pasteInput.substring(0, 500)}{pasteInput.length > 500 ? '...' : ''}</pre>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <p className="text-slate-400 text-sm">
                    Paste a bot configuration JSON below. The configuration will be validated before import.
                  </p>
                  <textarea
                    value={pasteInput}
                    onChange={(e) => handlePasteInputChange(e.target.value)}
                    placeholder='{"name": "My Bot", "strategy_type": "grid", ...}'
                    className="w-full h-48 bg-slate-900 border border-slate-600 rounded-lg p-3 text-sm font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  />
                </>
              )}

              {/* Validation Status */}
              {importValidation.isValid !== null && (
                <div className="space-y-2">
                  {importValidation.isValid ? (
                    <div className="flex items-center gap-2 text-green-400">
                      <CheckCircle className="w-5 h-5" />
                      <span className="font-medium">Valid configuration</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-red-400">
                      <AlertCircle className="w-5 h-5" />
                      <span className="font-medium">Invalid configuration</span>
                    </div>
                  )}

                  {/* Errors */}
                  {importValidation.errors.length > 0 && (
                    <div className="bg-red-500/10 border border-red-500/30 rounded p-3">
                      <div className="text-red-400 text-sm font-medium mb-1">Errors:</div>
                      <ul className="text-red-300 text-sm list-disc list-inside space-y-1">
                        {importValidation.errors.map((error, i) => (
                          <li key={i}>{error}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Warnings */}
                  {importValidation.warnings.length > 0 && (
                    <div className="bg-yellow-500/10 border border-yellow-500/30 rounded p-3">
                      <div className="text-yellow-400 text-sm font-medium mb-1">Warnings:</div>
                      <ul className="text-yellow-300 text-sm list-disc list-inside space-y-1">
                        {importValidation.warnings.map((warning, i) => (
                          <li key={i}>{warning}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Show parsed bot info when valid */}
                  {importValidation.isValid && importValidation.parsedData && (
                    <div className="bg-slate-700/50 rounded p-3 text-sm">
                      <div className="text-slate-300 font-medium mb-2">Bot Preview:</div>
                      <div className="grid grid-cols-2 gap-2 text-slate-400">
                        <div>Name: <span className="text-slate-200">{importValidation.parsedData.name || 'Imported Bot'}</span></div>
                        <div>Strategy: <span className="text-slate-200">{importValidation.parsedData.strategy_type}</span></div>
                        <div>Pairs: <span className="text-slate-200">
                          {(importValidation.parsedData.product_ids || [importValidation.parsedData.product_id]).join(', ')}
                        </span></div>
                        <div>Budget: <span className="text-slate-200">{importValidation.parsedData.budget_percentage || 10}%</span></div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 p-4 border-t border-slate-700">
              <button
                onClick={closeImportModal}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleImportSubmit}
                disabled={!importValidation.isValid}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed rounded font-medium transition-colors"
              >
                Import Bot
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Bots
