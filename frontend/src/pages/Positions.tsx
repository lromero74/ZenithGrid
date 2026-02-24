import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Building2, Wallet, Scale } from 'lucide-react'
import { useAccount, getChainName } from '../contexts/AccountContext'
import { useConfirm } from '../contexts/ConfirmContext'
import { useNotifications } from '../contexts/NotificationContext'
import type { Position } from '../types'
import PositionLogsModal from '../components/PositionLogsModal'
import TradingViewChartModal from '../components/TradingViewChartModal'
import LightweightChartModal from '../components/LightweightChartModal'
import { LimitCloseModal } from '../components/LimitCloseModal'
import { SlippageWarningModal } from '../components/SlippageWarningModal'
import { EditPositionSettingsModal } from '../components/EditPositionSettingsModal'
import { AddFundsModal } from '../components/AddFundsModal'
import { positionsApi } from '../services/api'
import { usePositionsData } from './positions/hooks/usePositionsData'
import { usePositionMutations } from './positions/hooks/usePositionMutations'
import { usePositionFilters } from './positions/hooks/usePositionFilters'
import { usePositionTrades } from './positions/hooks/usePositionTrades'
import { calculateOverallStats, checkSlippageBeforeMarketClose } from './positions/helpers'
import {
  OverallStatsPanel,
  FilterPanel,
  PositionCard,
  CloseConfirmModal,
  NotesModal,
  TradeHistoryModal,
} from './positions/components'

export default function Positions() {
  const { selectedAccount } = useAccount()
  const confirm = useConfirm()
  const { addToast } = useNotifications()

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
  const [slippageData, setSlippageData] = useState<any>(null)
  const [pendingMarketClosePositionId, setPendingMarketClosePositionId] = useState<number | null>(null)
  const [showNotesModal, setShowNotesModal] = useState(false)
  const [editingNotesPositionId, setEditingNotesPositionId] = useState<number | null>(null)
  const [notesText, setNotesText] = useState('')
  const [showEditSettingsModal, setShowEditSettingsModal] = useState(false)
  const [editSettingsPosition, setEditSettingsPosition] = useState<Position | null>(null)
  const [showTradeHistoryModal, setShowTradeHistoryModal] = useState(false)
  const [tradeHistoryPosition, setTradeHistoryPosition] = useState<Position | null>(null)

  // Use custom hooks for data fetching
  const {
    allPositions,
    positionsWithPnL,
    bots,
    btcUsdPrice,
    currentPrices,
    refetchPositions,
  } = usePositionsData({ selectedAccountId: selectedAccount?.id })

  // Use custom hooks for mutations
  const {
    isProcessing,
    handleClosePosition: performClosePosition,
    handleAddFundsSuccess: performAddFundsSuccess,
    handleSaveNotes: performSaveNotes,
  } = usePositionMutations({ refetchPositions })

  // Use custom hooks for filtering
  const {
    filterBot,
    setFilterBot,
    filterMarket,
    setFilterMarket,
    filterPair,
    setFilterPair,
    sortBy,
    setSortBy,
    sortOrder,
    setSortOrder,
    openPositions,
    uniquePairs,
    clearFilters,
  } = usePositionFilters({ positionsWithPnL })

  // Use custom hooks for trades
  const { trades, tradeHistory, isLoadingTradeHistory } = usePositionTrades({
    selectedPosition,
    tradeHistoryPosition,
    showTradeHistoryModal,
  })

  // Fetch completed trades statistics
  const { data: completedStats } = useQuery({
    queryKey: ['completed-trades-stats', selectedAccount?.id],
    queryFn: () => positionsApi.getCompletedStats(selectedAccount?.id),
    refetchInterval: 60000, // Refresh every minute
  })

  // Fetch realized PnL (daily and weekly)
  const { data: realizedPnL } = useQuery({
    queryKey: ['realized-pnl', selectedAccount?.id],
    queryFn: () => positionsApi.getRealizedPnL(selectedAccount?.id),
    refetchInterval: 60000, // Refresh every minute
  })

  // Fetch account balances
  const { data: balances, refetch: refetchBalances } = useQuery({
    queryKey: ['account-balances', selectedAccount?.id],
    queryFn: async () => {
      const { accountApi } = await import('../services/api')
      return accountApi.getBalances(selectedAccount?.id)
    },
    refetchInterval: 60000, // Refresh every minute
  })

  // Handler functions
  const handleClosePositionClick = async () => {
    const result = await performClosePosition(closeConfirmPositionId)
    if (result?.success) {
      setShowCloseConfirm(false)
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
    setAddFundsPosition(position)
    setShowAddFundsModal(true)
  }

  const openNotesModal = (position: Position) => {
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

  // Calculate overall statistics
  const stats = calculateOverallStats(openPositions)

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
            <div className="bg-green-500/20 text-green-400 px-3 py-1 rounded-full text-sm font-medium">
              {openPositions.length} Active
            </div>
            {openPositions.length > 0 && (
              <button
                className="flex items-center gap-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white px-3 py-1 rounded-full text-sm font-medium transition-colors"
                title="Recalculates each deal's budget to include base order + all safety orders with volume scaling. May result in overallocation if total exceeds available balance."
                onClick={async () => {
                  if (!await confirm({ title: 'Resize All Budgets', message: 'Resize all deal budgets to their true max potential (base + all safety orders)?\n\nThis may result in overallocation if total exceeds available balance.', variant: 'warning', confirmLabel: 'Resize' })) return
                  try {
                    const result = await positionsApi.resizeAllBudgets()
                    addToast({ type: 'success', title: 'Budgets Resized', message: `${result.message}` })
                    refetchPositions()
                  } catch (err: any) {
                    addToast({ type: 'error', title: 'Resize Failed', message: err.response?.data?.detail || err.message })
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

        {/* Filters (Account, Bot, Pair) */}
        <FilterPanel
          filterBot={filterBot}
          setFilterBot={setFilterBot}
          filterMarket={filterMarket}
          setFilterMarket={setFilterMarket}
          filterPair={filterPair}
          setFilterPair={setFilterPair}
          bots={bots}
          uniquePairs={uniquePairs}
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
            {/* Column Headers (hidden on mobile) */}
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

            {/* Position Cards */}
            {openPositions.map((position) => (
              <PositionCard
                key={position.id}
                position={position}
                currentPrice={currentPrices[position.product_id || 'ETH-BTC']}
                bots={bots}
                btcUsdPrice={btcUsdPrice}
                trades={trades}
                selectedPosition={selectedPosition}
                onTogglePosition={togglePosition}
                onOpenChart={(productId, pos) => {
                  setChartModalSymbol(productId)
                  setChartModalPosition(pos)
                  setShowChartModal(true)
                }}
                onOpenLightweightChart={(productId, pos) => {
                  setLightweightChartSymbol(productId)
                  setLightweightChartPosition(pos)
                  setShowLightweightChart(true)
                }}
                onOpenLimitClose={(pos) => {
                  setLimitClosePosition(pos)
                  setShowLimitCloseModal(true)
                }}
                onOpenLogs={(pos) => {
                  setShowLogsModal(true)
                  setLogsModalPosition(pos)
                }}
                onOpenAddFunds={openAddFundsModal}
                onOpenEditSettings={(pos) => {
                  setEditSettingsPosition(pos)
                  setShowEditSettingsModal(true)
                }}
                onOpenNotes={openNotesModal}
                onOpenTradeHistory={(pos) => {
                  setTradeHistoryPosition(pos)
                  setShowTradeHistoryModal(true)
                }}
                onCheckSlippage={handleCheckSlippage}
                onRefetch={refetchPositions}
              />
            ))}
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

      {/* Lightweight Chart Modal */}
      <LightweightChartModal
        isOpen={showLightweightChart}
        onClose={() => setShowLightweightChart(false)}
        symbol={lightweightChartSymbol}
        position={lightweightChartPosition}
      />

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
          onProceedWithMarket={() => {
            setShowSlippageWarning(false)
            setCloseConfirmPositionId(pendingMarketClosePositionId)
            setShowCloseConfirm(true)
            setPendingMarketClosePositionId(null)
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
    </div>
  )
}
