import { useState, useMemo, useCallback, lazy, Suspense } from 'react'
import type { Bot } from '../types'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { BarChart3, Building2, Wallet, Scale, Table2, Rows3, LayoutGrid } from 'lucide-react'
import { useAccount, getChainName } from '../contexts/AccountContext'
import { useConfirm } from '../contexts/ConfirmContext'
import { useNotifications } from '../contexts/NotificationContext'
import type { Position } from '../types'
import PositionLogsModal from '../components/positions/PositionLogsModal'
import TradingViewChartModal from '../components/trading/TradingViewChartModal'
// Lazy: pulls in lightweight-charts only when a chart modal is opened
const LightweightChartModal = lazy(() => import('../components/trading/LightweightChartModal'))
import { LimitCloseModal } from '../components/positions/LimitCloseModal'
import { SlippageWarningModal } from '../components/positions/SlippageWarningModal'
import { EditPositionSettingsModal } from '../components/positions/EditPositionSettingsModal'
import { AddFundsModal } from '../components/positions/AddFundsModal'
import { PanicSellModal } from '../components/positions/PanicSellModal'
import { positionsApi } from '../services/api'
import { usePermission } from '../hooks/usePermission'
import { usePositionsData } from './positions/hooks/usePositionsData'
import { usePositionMutations } from './positions/hooks/usePositionMutations'
import { usePositionFilters } from './positions/hooks/usePositionFilters'
import { usePositionTrades } from './positions/hooks/usePositionTrades'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { buildVisualRows } from './positions/utils/visualRows'
import { calculateOverallStats, checkSlippageBeforeMarketClose } from './positions/helpers'
import {
  OverallStatsPanel,
  FilterPanel,
  PositionCard,
  VirtualizedPositionList,
  CloseConfirmModal,
  NotesModal,
  TradeHistoryModal,
} from './positions/components'

const POSITIONS_SUMMARY_REFETCH_INTERVAL_MS = 120000

export default function Positions() {
  const { selectedAccount, selectedAccountId } = useAccount()
  const isObserver = selectedAccount?.membership_role === 'shadow'
  const canWritePositions = usePermission('positions', 'write') && !isObserver
  const confirm = useConfirm()
  const { addToast } = useNotifications()
  const navigate = useNavigate()

  // Modal and UI state
  const [selectedPosition, setSelectedPosition] = useState<number | null>(null)
  const [showAddFundsModal, setShowAddFundsModal] = useState(false)
  const [addFundsPosition, setAddFundsPosition] = useState<Position | null>(null)
  const [showLogsModal, setShowLogsModal] = useState(false)
  const [logsModalPosition, setLogsModalPosition] = useState<Position | null>(null)
  const [showChartModal, setShowChartModal] = useState(false)
  const [chartModalSymbol, setChartModalSymbol] = useState<string>('')
  const [chartModalPosition, setChartModalPosition] = useState<Position | null>(null)
  const [showLightweightChart, setShowLightweightChart] = useState(false)
  const [lightweightChartSymbol, setLightweightChartSymbol] = useState<string>('')
  const [lightweightChartPosition, setLightweightChartPosition] = useState<Position | null>(null)
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)
  const [closeConfirmPositionId, setCloseConfirmPositionId] = useState<number | null>(null)
  const [showLimitCloseModal, setShowLimitCloseModal] = useState(false)
  const [limitClosePosition, setLimitClosePosition] = useState<Position | null>(null)
  const [showSlippageWarning, setShowSlippageWarning] = useState(false)
  const [slippageData, setSlippageData] = useState<{
    product_id: string
    best_bid: number
    mark_price: number
    expected_profit_at_mark: number
    actual_profit_at_bid: number
    slippage_amount: number
    slippage_percentage: number
  } | null>(null)
  const [pendingMarketClosePositionId, setPendingMarketClosePositionId] = useState<number | null>(null)
  const [showSlippageOverride, setShowSlippageOverride] = useState(false)
  const [slippageOverrideWarning, setSlippageOverrideWarning] = useState<string>('')
  const [slippageOverridePositionId, setSlippageOverridePositionId] = useState<number | null>(null)
  const [showNotesModal, setShowNotesModal] = useState(false)
  const [editingNotesPositionId, setEditingNotesPositionId] = useState<number | null>(null)
  const [notesText, setNotesText] = useState('')
  const [showEditSettingsModal, setShowEditSettingsModal] = useState(false)
  const [editSettingsPosition, setEditSettingsPosition] = useState<Position | null>(null)
  const [showTradeHistoryModal, setShowTradeHistoryModal] = useState(false)
  const [tradeHistoryPosition, setTradeHistoryPosition] = useState<Position | null>(null)
  const [showPanicSell, setShowPanicSell] = useState(false)

  // Use custom hooks for data fetching
  const {
    allPositions,
    positionsWithPnL,
    bots,
    btcUsdPrice,
    currentPrices,
    refetchPositions,
  } = usePositionsData({ selectedAccountId })

  // Use custom hooks for mutations
  const {
    isProcessing,
    handleClosePosition: performClosePosition,
    handleAddFundsSuccess: performAddFundsSuccess,
    handleSaveNotes: performSaveNotes,
  } = usePositionMutations({ refetchPositions })

  // Use custom hooks for filtering
  const {
    filterBot, setFilterBot,
    filterMarket, setFilterMarket,
    filterPair, setFilterPair,
    filterCategory, setFilterCategory,
    groupBy, setGroupBy,
    sortBy, setSortBy,
    sortOrder, setSortOrder,
    viewMode, setViewMode,
    pageSize, setPageSize,
    currentPage, setCurrentPage,
    totalCount, totalPages,
    openPositions,
    filteredPositions,
    uniqueMarkets,
    uniqueBots,
    uniquePairs,
    uniqueCategories,
    getGroupKey,
    clearFilters,
  } = usePositionFilters({ positionsWithPnL, bots })

  // Use custom hooks for trades
  const { trades, tradeHistory, isLoadingTradeHistory } = usePositionTrades({
    selectedPosition,
    tradeHistoryPosition,
    showTradeHistoryModal,
  })

  // Fetch completed trades statistics
  const { data: completedStats } = useQuery({
    queryKey: ['completed-trades-stats', selectedAccountId],
    queryFn: () => positionsApi.getCompletedStats(selectedAccountId ?? undefined),
    enabled: selectedAccountId !== null,
    refetchInterval: POSITIONS_SUMMARY_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    staleTime: 60000,
    refetchOnMount: 'always' as const,
  })

  // Fetch realized PnL (daily and weekly)
  const { data: realizedPnL } = useQuery({
    queryKey: ['realized-pnl', selectedAccountId],
    queryFn: () => positionsApi.getRealizedPnL(selectedAccountId ?? undefined),
    enabled: selectedAccountId !== null,
    refetchInterval: POSITIONS_SUMMARY_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    staleTime: 60000,
    refetchOnMount: 'always' as const,
  })

  // Fetch account balances
  const { data: balances, refetch: refetchBalances } = useQuery({
    queryKey: ['account-balances', selectedAccountId],
    queryFn: async () => {
      const { accountApi } = await import('../services/api')
      return accountApi.getBalances(selectedAccountId ?? undefined)
    },
    enabled: selectedAccountId !== null,
    refetchInterval: POSITIONS_SUMMARY_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    staleTime: 60000,
    refetchOnMount: 'always' as const,
  })

  // Handler functions
  const handleClosePositionClick = async () => {
    const result = await performClosePosition(closeConfirmPositionId)
    if (result?.success) {
      setShowCloseConfirm(false)
      setCloseConfirmPositionId(null)
    } else if (result?.slippageBlocked) {
      // VWAP profit is below TP floor — ask user to confirm selling at a loss
      setShowCloseConfirm(false)
      setSlippageOverridePositionId(closeConfirmPositionId)
      setSlippageOverrideWarning(result.slippageWarning || 'Position profit is below the target floor.')
      setShowSlippageOverride(true)
    }
  }

  const handleSlippageOverrideConfirm = async () => {
    setShowSlippageOverride(false)
    const result = await performClosePosition(slippageOverridePositionId, true)
    if (result?.success || !result?.slippageBlocked) {
      setSlippageOverridePositionId(null)
      setCloseConfirmPositionId(null)
    }
  }

  const handleAddFundsSuccess = () => {
    performAddFundsSuccess()
    setShowAddFundsModal(false)
    setAddFundsPosition(null)
  }

  const handleSaveNotes = async () => {
    const result = await performSaveNotes(editingNotesPositionId, notesText)
    if (result?.success) {
      setShowNotesModal(false)
      setEditingNotesPositionId(null)
      setNotesText('')
    }
  }

  const handleCheckSlippage = async (positionId: number) => {
    await checkSlippageBeforeMarketClose(
      positionId,
      (slippage, posId) => {
        setSlippageData(slippage)
        setPendingMarketClosePositionId(posId)
        setShowSlippageWarning(true)
      },
      (posId) => {
        setCloseConfirmPositionId(posId)
        setShowCloseConfirm(true)
      }
    )
  }

  const openAddFundsModal = (position: Position) => {
    if (isObserver) return
    setAddFundsPosition(position)
    setShowAddFundsModal(true)
  }

  const openNotesModal = (position: Position) => {
    if (isObserver) return
    setEditingNotesPositionId(position.id)
    setNotesText(position.notes || '')
    setShowNotesModal(true)
  }

  const togglePosition = (positionId: number) => {
    if (selectedPosition === positionId) {
      setSelectedPosition(null)
    } else {
      setSelectedPosition(positionId)
    }
  }

  // Memoized handlers for PositionCard (F1)
  const handleOpenChart = useCallback((productId: string, pos: Position) => {
    setChartModalSymbol(productId)
    setChartModalPosition(pos)
    setShowChartModal(true)
  }, [])

  const handleOpenLightweightChart = useCallback((productId: string, pos: Position) => {
    setLightweightChartSymbol(productId)
    setLightweightChartPosition(pos)
    setShowLightweightChart(true)
  }, [])

  const handleOpenLimitClose = useCallback((pos: Position) => {
    setLimitClosePosition(pos)
    setShowLimitCloseModal(true)
  }, [])

  const handleOpenLogs = useCallback((pos: Position) => {
    setShowLogsModal(true)
    setLogsModalPosition(pos)
  }, [])

  const handleOpenEditSettings = useCallback((pos: Position) => {
    if (isObserver) return
    setEditSettingsPosition(pos)
    setShowEditSettingsModal(true)
  }, [isObserver])

  const handleOpenTradeHistory = useCallback((pos: Position) => {
    setTradeHistoryPosition(pos)
    setShowTradeHistoryModal(true)
  }, [])

  const handleEditBot = useCallback((bot: Bot) => {
    navigate('/bots', { state: { editBot: bot } })
  }, [navigate])

  // Rows for the virtualized list — group headers are attached to the first
  // position of each group so a row renders header + card together.
  const positionRows = useMemo(() => {
    let lastGroupKey: string | null = null
    return openPositions.map((position: Position) => {
      const groupKey = groupBy !== 'none' ? getGroupKey(position) : null
      const showHeader = groupKey !== null && groupKey !== lastGroupKey
      if (showHeader) lastGroupKey = groupKey
      return { position, groupKey, showHeader }
    })
  }, [openPositions, groupBy, getGroupKey])

  // Tiling column count for the grid view: 1 on portrait phones, 2 from md
  // (landscape phones / small tablets), 3 from xl. Table and card-list modes
  // are always a single column.
  const isMd = useMediaQuery('(min-width: 768px)')
  const isXl = useMediaQuery('(min-width: 1280px)')
  const columns = viewMode === 'grid' ? (isXl ? 3 : isMd ? 2 : 1) : 1

  // Pack the position rows into virtualized visual rows (group headers occupy
  // their own row; cards tile `columns`-wide). One vertical column of
  // variable-height blocks keeps the window virtualizer in play for all modes.
  const visualRows = useMemo(() => buildVisualRows(positionRows, columns), [positionRows, columns])

  // Pre-compute bot lookup map for O(1) access in PositionCard
  const botsById = useMemo(
    () => new Map((bots || []).map((b: Bot) => [b.id, b])),
    [bots]
  )

  // Calculate overall statistics across ALL filtered positions (not just current page)
  const stats = useMemo(() => calculateOverallStats(filteredPositions), [filteredPositions])

  return (
    <div className="space-y-6">
      {/* Active Deals Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            {selectedAccount?.type === 'dex' ? (
              <Wallet className="w-8 h-8 text-orange-400" />
            ) : (
              <Building2 className="w-8 h-8 text-blue-400" />
            )}
            <div>
              <h2 className="text-3xl font-bold text-white">Active Deals</h2>
              {selectedAccount && (
                <p className="text-sm text-slate-400">
                  <span className="text-slate-300">{selectedAccount.name}</span>
                  {selectedAccount.type === 'dex' && selectedAccount.chain_id && (
                    <span className="text-slate-500"> ({getChainName(selectedAccount.chain_id)})</span>
                  )}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* View mode: compact table / single-column cards / tiled grid */}
            <div className="flex items-center bg-slate-800 border border-slate-700 rounded-lg p-0.5">
              {([
                { mode: 'table', Icon: Table2, label: 'Table' },
                { mode: 'list', Icon: Rows3, label: 'Cards' },
                { mode: 'grid', Icon: LayoutGrid, label: 'Grid' },
              ] as const).map(({ mode, Icon, label }) => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  title={`${label} view`}
                  aria-label={`${label} view`}
                  aria-pressed={viewMode === mode}
                  className={`flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition-colors ${
                    viewMode === mode ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'
                  }`}
                >
                  <Icon size={14} />
                  <span className="hidden md:inline">{label}</span>
                </button>
              ))}
            </div>
            <div className="bg-green-500/20 text-green-400 px-3 py-1 rounded-full text-sm font-medium">
              {totalCount} Active
            </div>
            {canWritePositions && openPositions.length > 0 && selectedAccount && (
              <button
                onClick={() => setShowPanicSell(true)}
                className="flex items-center gap-1.5 bg-red-600/20 hover:bg-red-600/40 text-red-400 hover:text-red-300 border border-red-500/30 px-3 py-1 rounded-full text-sm font-medium transition-colors"
              >
                <span>🚨</span>
                <span>Panic Sell</span>
              </button>
            )}
            {openPositions.length > 0 && !isObserver && (
              <button
                className="flex items-center gap-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white px-3 py-1 rounded-full text-sm font-medium transition-colors"
                title="Recalculates each deal's budget to include base order + all safety orders with volume scaling. May result in overallocation if total exceeds available balance."
                onClick={async () => {
                  if (!await confirm({ title: 'Resize All Budgets', message: 'Resize all deal budgets to their true max potential (base + all safety orders)?\n\nThis may result in overallocation if total exceeds available balance.', variant: 'warning', confirmLabel: 'Resize' })) return
                  try {
                    const result = await positionsApi.resizeAllBudgets(selectedAccount?.id)
                    addToast({ type: 'success', title: 'Budgets Resized', message: `${result.message}` })
                    refetchPositions()
                  } catch (err: unknown) {
                    const e = err as { response?: { data?: { detail?: string } }; message?: string }
                    addToast({ type: 'error', title: 'Resize Failed', message: e.response?.data?.detail || e.message || 'Unknown error' })
                  }
                }}
              >
                <Scale size={14} />
                Resize All Budgets
              </button>
            )}
          </div>
        </div>

        {/* Overall Stats Panel */}
        <OverallStatsPanel
          stats={stats}
          completedStats={completedStats}
          realizedPnL={realizedPnL}
          balances={balances}
          onRefreshBalances={refetchBalances}
        />

        {/* Filters (Market, Bot, Pair, Category, GroupBy) */}
        <FilterPanel
          filterBot={filterBot}
          setFilterBot={setFilterBot}
          filterMarket={filterMarket}
          setFilterMarket={setFilterMarket}
          filterPair={filterPair}
          setFilterPair={setFilterPair}
          filterCategory={filterCategory}
          setFilterCategory={setFilterCategory}
          groupBy={groupBy}
          setGroupBy={setGroupBy}
          bots={bots}
          uniqueMarkets={uniqueMarkets}
          uniqueBots={uniqueBots}
          uniquePairs={uniquePairs}
          uniqueCategories={uniqueCategories}
          onClearFilters={clearFilters}
        />

        {openPositions.length === 0 ? (
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-12 text-center">
            <BarChart3 className="w-16 h-16 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400 text-lg">No active deals</p>
            <p className="text-slate-500 text-sm mt-2">Start a bot to open new positions</p>
          </div>
        ) : (
          <div className="space-y-2">
            {/* Sort Controls — shown on mobile in table mode (no column headers
                there), and at all widths in card/grid modes (no headers at all). */}
            <div className={`${viewMode === 'table' ? 'sm:hidden ' : ''}flex items-center gap-2 px-3 py-2 bg-slate-800/50 rounded-lg border border-slate-700/50`}>
              <span className="text-xs text-slate-400 whitespace-nowrap">Sort:</span>
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value as typeof sortBy)}
                className="flex-1 bg-slate-700 text-white text-sm rounded px-2 py-1 border border-slate-600 focus:outline-none focus:border-blue-500"
              >
                <option value="created">Date</option>
                <option value="pnl">PnL</option>
                <option value="invested">Volume</option>
                <option value="pair">Pair</option>
                <option value="bot">Bot</option>
              </select>
              <button
                onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
                className="px-2 py-1 bg-slate-700 border border-slate-600 rounded text-sm text-slate-300 hover:text-white"
              >
                {sortOrder === 'asc' ? '↑ Asc' : '↓ Desc'}
              </button>
            </div>

            {/* Column Headers — table mode only (hidden on mobile) */}
            {viewMode === 'table' && (
            <div className="hidden sm:block bg-slate-800/50 rounded-lg border border-slate-700/50 px-4 py-2">
              <div className="grid grid-cols-12 gap-4 items-center text-xs text-slate-400">
                <div
                  className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'bot') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('bot')
                      setSortOrder('asc')
                    }
                  }}
                >
                  <span>Bot</span>
                  {sortBy === 'bot' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'bot' && <span className="opacity-30">↕</span>}
                </div>
                <div
                  className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'pair') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('pair')
                      setSortOrder('asc')
                    }
                  }}
                >
                  <span>Pair</span>
                  {sortBy === 'pair' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'pair' && <span className="opacity-30">↕</span>}
                </div>
                <div
                  className="col-span-4 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'pnl') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('pnl')
                      setSortOrder('desc')
                    }
                  }}
                >
                  <span className="flex items-center gap-1">
                    <span className="w-4 h-4 rounded-full bg-slate-600 flex items-center justify-center text-[9px]">?</span>
                    uPnL
                  </span>
                  {sortBy === 'pnl' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'pnl' && <span className="opacity-30">↕</span>}
                </div>
                <div
                  className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'invested') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('invested')
                      setSortOrder('desc')
                    }
                  }}
                >
                  <span>Volume</span>
                  {sortBy === 'invested' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'invested' && <span className="opacity-30">↕</span>}
                </div>
                <div className="col-span-1 flex items-center gap-1 text-slate-500">
                  <span>Status</span>
                </div>
                <div
                  className="col-span-1 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'created') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('created')
                      setSortOrder('desc')
                    }
                  }}
                >
                  <span>Created</span>
                  {sortBy === 'created' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'created' && <span className="opacity-30">↕</span>}
                </div>
              </div>
            </div>
            )}

            {/* Position Cards — virtualized so only visible cards render.
                Each visual row is a group header or up to `columns` tiled cards. */}
            <VirtualizedPositionList
              items={visualRows}
              getItemKey={(index) => visualRows[index].key}
              renderItem={(vrow) =>
                vrow.kind === 'header' ? (
                  <div className="px-3 py-1.5 mb-1 mt-3 bg-slate-700/50 rounded text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    {vrow.label}
                  </div>
                ) : (
                  <div
                    className="grid gap-2 pb-2 items-start"
                    style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
                  >
                    {vrow.items.map(({ position }) => (
                      <PositionCard
                        key={position.id}
                        position={position}
                        currentPrice={currentPrices[position.product_id || 'ETH-BTC']}
                        bots={bots}
                        bot={position.bot_id != null ? botsById.get(position.bot_id) : undefined}
                        btcUsdPrice={btcUsdPrice}
                        trades={trades}
                        selectedPosition={selectedPosition}
                        onTogglePosition={togglePosition}
                        onOpenChart={handleOpenChart}
                        onOpenLightweightChart={handleOpenLightweightChart}
                        onOpenLimitClose={handleOpenLimitClose}
                        onOpenLogs={handleOpenLogs}
                        onOpenAddFunds={openAddFundsModal}
                        onOpenEditSettings={handleOpenEditSettings}
                        onOpenNotes={openNotesModal}
                        onOpenTradeHistory={handleOpenTradeHistory}
                        onCheckSlippage={handleCheckSlippage}
                        onRefetch={refetchPositions}
                        onEditBot={handleEditBot}
                        canWrite={canWritePositions}
                        forceCardLayout={viewMode !== 'table'}
                      />
                    ))}
                  </div>
                )
              }
            />

            {/* Pagination controls */}
            {totalCount > 0 && (
              <div className="flex items-center justify-between pt-2 border-t border-slate-700/50">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400">Per page:</span>
                  {([10, 100] as const).map(n => (
                    <button
                      key={n}
                      onClick={() => setPageSize(n)}
                      className={`px-2 py-1 rounded text-xs font-medium transition-colors ${pageSize === n ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'}`}
                    >
                      {n}
                    </button>
                  ))}
                  <span className="text-xs text-slate-500">
                    {Math.min((currentPage - 1) * pageSize + 1, totalCount)}–{Math.min(currentPage * pageSize, totalCount)} of {totalCount}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage <= 1}
                    className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    ‹ Prev
                  </button>
                  <span className="text-xs text-slate-400 px-2">
                    {currentPage}/{totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage >= totalPages}
                    className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Next ›
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Close Position Confirmation Modal */}
      <CloseConfirmModal
        isOpen={showCloseConfirm}
        isProcessing={isProcessing}
        onClose={() => {
          setShowCloseConfirm(false)
          setCloseConfirmPositionId(null)
        }}
        onConfirm={handleClosePositionClick}
      />

      {/* Slippage Override Confirmation Modal */}
      {showSlippageOverride && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full mx-4 border border-slate-600">
            <h3 className="text-lg font-semibold text-white mb-2">Sell Below Target?</h3>
            <p className="text-slate-300 text-sm mb-4">{slippageOverrideWarning}</p>
            <p className="text-slate-400 text-sm mb-6">
              This position's current profit is below the bot's target floor. Selling now will close it at a loss.
              Continue anyway?
            </p>
            <div className="flex gap-3 justify-end">
              <button
                className="px-4 py-2 rounded bg-slate-700 text-slate-300 hover:bg-slate-600"
                onClick={() => {
                  setShowSlippageOverride(false)
                  setSlippageOverridePositionId(null)
                }}
              >
                Cancel
              </button>
              <button
                className="px-4 py-2 rounded bg-red-600 text-white hover:bg-red-500 font-medium"
                onClick={handleSlippageOverrideConfirm}
                disabled={isProcessing}
              >
                {isProcessing ? 'Selling...' : 'Sell Anyway'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Funds Modal */}
      {addFundsPosition && (
        <AddFundsModal
          position={addFundsPosition}
          isOpen={showAddFundsModal}
          onClose={() => {
            setShowAddFundsModal(false)
            setAddFundsPosition(null)
          }}
          onSuccess={handleAddFundsSuccess}
          readOnly={!canWritePositions}
        />
      )}

      {/* Position AI Logs Modal */}
      {logsModalPosition && (
        <PositionLogsModal
          botId={logsModalPosition.bot_id || 0}
          productId={logsModalPosition.product_id || 'ETH-BTC'}
          positionOpenedAt={logsModalPosition.opened_at}
          isOpen={showLogsModal}
          onClose={() => {
            setShowLogsModal(false)
            setLogsModalPosition(null)
          }}
        />
      )}

      {/* TradingView Chart Modal */}
      <TradingViewChartModal
        isOpen={showChartModal}
        onClose={() => setShowChartModal(false)}
        symbol={chartModalSymbol}
        position={chartModalPosition}
      />

      {/* Lightweight Chart Modal (lazy — loads lightweight-charts on demand) */}
      {showLightweightChart && (
        <Suspense fallback={null}>
          <LightweightChartModal
            isOpen={showLightweightChart}
            onClose={() => setShowLightweightChart(false)}
            symbol={lightweightChartSymbol}
            position={lightweightChartPosition}
          />
        </Suspense>
      )}

      {/* Notes Modal */}
      <NotesModal
        isOpen={showNotesModal}
        isProcessing={isProcessing}
        notesText={notesText}
        onNotesChange={setNotesText}
        onClose={() => setShowNotesModal(false)}
        onSave={handleSaveNotes}
      />

      {/* Limit Close Modal */}
      {showLimitCloseModal && limitClosePosition && (
        <LimitCloseModal
          positionId={limitClosePosition.id}
          dealNumber={limitClosePosition.user_deal_number}
          productId={limitClosePosition.product_id || 'ETH-BTC'}
          totalAmount={limitClosePosition.total_base_acquired}
          quoteCurrency={limitClosePosition.product_id?.split('-')[1] || 'BTC'}
          totalQuoteSpent={limitClosePosition.total_quote_spent}
          isEditing={limitClosePosition.closing_via_limit}
          currentLimitPrice={limitClosePosition.limit_order_details?.limit_price}
          readOnly={!canWritePositions}
          onClose={() => {
            setShowLimitCloseModal(false)
            setLimitClosePosition(null)
          }}
          onSuccess={() => {
            refetchPositions()
          }}
        />
      )}

      {/* Slippage Warning Modal */}
      {showSlippageWarning && slippageData && pendingMarketClosePositionId && (
        <SlippageWarningModal
          positionId={pendingMarketClosePositionId}
          productId={slippageData.product_id}
          slippageData={slippageData}
          quoteCurrency={slippageData.product_id?.split('-')[1] || 'BTC'}
          onClose={() => {
            setShowSlippageWarning(false)
            setSlippageData(null)
            setPendingMarketClosePositionId(null)
          }}
          onProceedWithMarket={async () => {
            const posId = pendingMarketClosePositionId
            setShowSlippageWarning(false)
            setSlippageData(null)
            setPendingMarketClosePositionId(null)
            if (posId) {
              await performClosePosition(posId, true)
            }
          }}
          onSwitchToLimit={() => {
            setShowSlippageWarning(false)
            const position = allPositions?.find(p => p.id === pendingMarketClosePositionId)
            if (position) {
              setLimitClosePosition(position)
              setShowLimitCloseModal(true)
            }
            setPendingMarketClosePositionId(null)
          }}
        />
      )}

      {/* Edit Position Settings Modal */}
      {showEditSettingsModal && editSettingsPosition && (
        <EditPositionSettingsModal
          position={editSettingsPosition}
          onClose={() => {
            setShowEditSettingsModal(false)
            setEditSettingsPosition(null)
          }}
          onSuccess={() => {
            refetchPositions()
          }}
          readOnly={!canWritePositions}
        />
      )}

      {/* Trade History Modal */}
      <TradeHistoryModal
        isOpen={showTradeHistoryModal}
        position={tradeHistoryPosition}
        trades={tradeHistory}
        isLoading={isLoadingTradeHistory}
        onClose={() => {
          setShowTradeHistoryModal(false)
          setTradeHistoryPosition(null)
        }}
      />

      {/* Panic Sell Modal */}
      {showPanicSell && selectedAccount && (
        <PanicSellModal
          isOpen={showPanicSell}
          onClose={() => setShowPanicSell(false)}
          accountId={selectedAccount.id}
        />
      )}
    </div>
  )
}
