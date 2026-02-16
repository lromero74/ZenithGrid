/**
 * Accounts Management Component
 *
 * Displays list of all accounts with management actions.
 * Used in Settings page for full account CRUD.
 */

import { useState, useEffect } from 'react'
import {
  Building2,
  Wallet,
  Trash2,
  Star,
  StarOff,
  MoreVertical,
  AlertCircle,
  RefreshCw,
  ArrowRightLeft,
  ChevronDown,
  ChevronRight,
  Link2,
  CheckCircle,
  Shield,
} from 'lucide-react'
import { useAccount, Account, getChainName } from '../contexts/AccountContext'
import { accountApi, api } from '../services/api'
import { PropGuardStatus } from './PropGuardStatus'

interface AccountsManagementProps {
  onAddAccount: () => void
}

export function AccountsManagement({ onAddAccount }: AccountsManagementProps) {
  const {
    accounts,
    isLoading,
    error,
    deleteAccount,
    setDefaultAccount,
    refreshAccounts,
  } = useAccount()

  const [openMenuId, setOpenMenuId] = useState<number | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [sellingToBTC, setSellingToBTC] = useState(false)
  const [sellingToUSD, setSellingToUSD] = useState(false)

  const toggleExpanded = (id: number) => {
    setExpandedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleDelete = async (account: Account) => {
    if (!confirm(`Are you sure you want to delete "${account.name}"? This action cannot be undone.`)) {
      return
    }

    setDeletingId(account.id)
    setActionError(null)

    try {
      await deleteAccount(account.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to delete account')
    } finally {
      setDeletingId(null)
      setOpenMenuId(null)
    }
  }

  const handleSetDefault = async (account: Account) => {
    setActionError(null)
    try {
      await setDefaultAccount(account.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to set default')
    }
    setOpenMenuId(null)
  }

  const [conversionProgress, setConversionProgress] = useState<{
    taskId: string | null;
    targetCurrency: 'BTC' | 'USD' | null;
    status: string;
    progress: number;
    message: string;
    total: number;
    current: number;
    sold: number;
    failed: number;
  }>({
    taskId: null,
    targetCurrency: null,
    status: 'idle',
    progress: 0,
    message: '',
    total: 0,
    current: 0,
    sold: 0,
    failed: 0,
  })

  // Poll for conversion progress
  useEffect(() => {
    if (!conversionProgress.taskId || conversionProgress.status === 'completed' || conversionProgress.status === 'failed') {
      return
    }

    const pollInterval = setInterval(async () => {
      try {
        const status = await accountApi.getConversionStatus(conversionProgress.taskId!)

        setConversionProgress({
          taskId: conversionProgress.taskId,
          targetCurrency: conversionProgress.targetCurrency,
          status: status.status,
          progress: status.progress_pct,
          message: status.message,
          total: status.total,
          current: status.current,
          sold: status.sold_count,
          failed: status.failed_count,
        })

        // If completed or failed, stop polling
        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(pollInterval)

          // Show completion message
          if (status.status === 'completed') {
            const successRate = status.total > 0 ? Math.round((status.sold_count / status.total) * 100) : 0
            let message = ''
            if (status.failed_count > 0) {
              message =
                `Portfolio Conversion Complete (with some errors):\n\n` +
                `✅ Successfully sold: ${status.sold_count}/${status.total} currencies (${successRate}%)\n` +
                `❌ Failed: ${status.failed_count} currencies\n\n` +
                (status.errors.length > 0 ? `Errors:\n${status.errors.slice(0, 5).join('\n')}` +
                (status.errors.length > 5 ? `\n... and ${status.errors.length - 5} more` : '') : '')
            } else {
              message =
                `✅ Portfolio Conversion Complete!\n\n` +
                `Successfully sold all ${status.sold_count} currencies to ${conversionProgress.targetCurrency}`
            }
            alert(message)
            await refreshAccounts()
          } else {
            alert(`❌ Conversion failed: ${status.message}`)
          }

          // Reset state
          setConversionProgress({
            taskId: null,
            targetCurrency: null,
            status: 'idle',
            progress: 0,
            message: '',
            total: 0,
            current: 0,
            sold: 0,
            failed: 0,
          })

          if (conversionProgress.targetCurrency === 'BTC') {
            setSellingToBTC(false)
          } else {
            setSellingToUSD(false)
          }
        }
      } catch (err) {
        console.error('Failed to fetch conversion status:', err)
      }
    }, 500) // Poll every 500ms for smooth progress updates

    return () => clearInterval(pollInterval)
  }, [conversionProgress.taskId, conversionProgress.status, conversionProgress.targetCurrency, refreshAccounts])

  const handleSellPortfolioToBase = async (account: Account, targetCurrency: 'BTC' | 'USD') => {
    const currencySetter = targetCurrency === 'BTC' ? setSellingToBTC : setSellingToUSD

    if (!confirm(
      `🚨 CONVERT ${account.name.toUpperCase()} PORTFOLIO TO ${targetCurrency} 🚨\n\n` +
      `This will sell ALL holdings on ${account.name} (ETH, ADA, etc.) to ${targetCurrency}.\n\n` +
      `All balances will be converted at MARKET price.\n` +
      `This action CANNOT be undone.\n\n` +
      `Are you absolutely sure you want to proceed?`
    )) {
      return
    }

    currencySetter(true)
    setActionError(null)

    try {
      // Start the conversion (returns task_id immediately)
      const result = await accountApi.sellPortfolioToBase(targetCurrency, true, account.id)

      // Set up progress tracking
      setConversionProgress({
        taskId: result.task_id,
        targetCurrency,
        status: 'running',
        progress: 0,
        message: 'Starting conversion...',
        total: 0,
        current: 0,
        sold: 0,
        failed: 0,
      })

    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error'
      setActionError(`Failed to start portfolio conversion: ${errorMsg}`)
      alert(`❌ Error starting portfolio conversion: ${errorMsg}`)
      currencySetter(false)
    }
  }

  const cexAccounts = accounts.filter((a) => a.type === 'cex')
  const dexAccounts = accounts.filter((a) => a.type === 'dex')

  if (isLoading) {
    return (
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <div className="flex items-center justify-center">
          <RefreshCw className="w-5 h-5 text-slate-400 animate-spin" />
          <span className="ml-2 text-slate-400">Loading accounts...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <Wallet className="w-5 h-5 text-blue-400" />
            Manage Accounts
          </h3>
          <p className="text-sm text-slate-400 mt-1">
            Configure CEX and DEX accounts for trading
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refreshAccounts}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
            title="Refresh accounts"
          >
            <RefreshCw className="w-4 h-4 text-slate-400" />
          </button>
          <button
            onClick={onAddAccount}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium transition-colors"
          >
            Add Account
          </button>
        </div>
      </div>

      {/* Error Message */}
      {(error || actionError) && (
        <div className="flex items-start space-x-2 p-3 bg-red-900/20 border border-red-700 rounded-lg">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-300">{error || actionError}</p>
        </div>
      )}

      {/* No Accounts */}
      {accounts.length === 0 && (
        <div className="bg-slate-800 rounded-lg p-12 border border-slate-700 text-center">
          <Wallet className="w-16 h-16 text-slate-600 mx-auto mb-4" />
          <h4 className="text-xl font-semibold text-white mb-2">No Accounts Configured</h4>
          <p className="text-slate-400 mb-6">
            Add your first trading account to get started
          </p>
          <button
            onClick={onAddAccount}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium transition-colors"
          >
            Add Your First Account
          </button>
        </div>
      )}

      {/* CEX Accounts */}
      {cexAccounts.length > 0 && (
        <div className="bg-slate-800 rounded-lg border border-slate-700">
          <div className="px-4 py-3 bg-slate-900 border-b border-slate-700">
            <h4 className="font-medium text-white flex items-center gap-2">
              <Building2 className="w-4 h-4 text-blue-400" />
              Centralized Exchanges ({cexAccounts.length})
            </h4>
          </div>
          <div className="divide-y divide-slate-700">
            {cexAccounts.map((account) => (
              <AccountRow
                key={account.id}
                account={account}
                isDeleting={deletingId === account.id}
                isMenuOpen={openMenuId === account.id}
                isExpanded={expandedIds.has(account.id)}
                onToggleExpand={() => toggleExpanded(account.id)}
                onMenuToggle={() => setOpenMenuId(openMenuId === account.id ? null : account.id)}
                onDelete={() => handleDelete(account)}
                onSetDefault={() => handleSetDefault(account)}
                onConvertToBTC={() => handleSellPortfolioToBase(account, 'BTC')}
                onConvertToUSD={() => handleSellPortfolioToBase(account, 'USD')}
                isConverting={sellingToBTC || sellingToUSD}
                onRefreshAccounts={refreshAccounts}
              />
            ))}
          </div>
        </div>
      )}

      {/* DEX Accounts */}
      {dexAccounts.length > 0 && (
        <div className="bg-slate-800 rounded-lg border border-slate-700">
          <div className="px-4 py-3 bg-slate-900 border-b border-slate-700">
            <h4 className="font-medium text-white flex items-center gap-2">
              <Wallet className="w-4 h-4 text-orange-400" />
              DEX Wallets ({dexAccounts.length})
            </h4>
          </div>
          <div className="divide-y divide-slate-700">
            {dexAccounts.map((account) => (
              <AccountRow
                key={account.id}
                account={account}
                isDeleting={deletingId === account.id}
                isMenuOpen={openMenuId === account.id}
                onMenuToggle={() => setOpenMenuId(openMenuId === account.id ? null : account.id)}
                onDelete={() => handleDelete(account)}
                onSetDefault={() => handleSetDefault(account)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

interface AccountRowProps {
  account: Account
  isDeleting: boolean
  isMenuOpen: boolean
  isExpanded?: boolean
  onToggleExpand?: () => void
  onMenuToggle: () => void
  onDelete: () => void
  onSetDefault: () => void
  onConvertToBTC?: () => void
  onConvertToUSD?: () => void
  isConverting?: boolean
  onRefreshAccounts?: () => Promise<void>
}

function AccountRow({
  account,
  isDeleting,
  isMenuOpen,
  isExpanded,
  onToggleExpand,
  onMenuToggle,
  onDelete,
  onSetDefault,
  onConvertToBTC,
  onConvertToUSD,
  isConverting,
  onRefreshAccounts,
}: AccountRowProps) {
  const [linking, setLinking] = useState(false)
  const [perpsError, setPerpsError] = useState<string | null>(null)

  const isCex = account.type === 'cex'
  const hasPerps = Boolean(account.perps_portfolio_uuid)

  const handleLinkPerps = async () => {
    setLinking(true)
    setPerpsError(null)
    try {
      await api.post(`/accounts/${account.id}/link-perps-portfolio`)
      if (onRefreshAccounts) await onRefreshAccounts()
    } catch (err: any) {
      setPerpsError(err.response?.data?.detail || 'Failed to link portfolio')
    } finally {
      setLinking(false)
    }
  }

  return (
    <div className={`${isDeleting ? 'opacity-50' : ''}`}>
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center space-x-3 min-w-0">
          {/* Expand/collapse chevron for CEX accounts */}
          {isCex && onToggleExpand ? (
            <button
              onClick={onToggleExpand}
              className="p-0.5 hover:bg-slate-700 rounded transition-colors flex-shrink-0"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-slate-400" />
              ) : (
                <ChevronRight className="w-4 h-4 text-slate-400" />
              )}
            </button>
          ) : null}

          {isCex ? (
            <Building2 className="w-5 h-5 text-blue-400 flex-shrink-0" />
          ) : (
            <Wallet className="w-5 h-5 text-orange-400 flex-shrink-0" />
          )}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-white truncate">{account.name}</span>
              {account.is_default && (
                <span className="px-1.5 py-0.5 text-[10px] font-medium bg-blue-500/20 text-blue-300 rounded">
                  DEFAULT
                </span>
              )}
              {account.prop_firm && (
                <span className="px-1.5 py-0.5 text-[10px] font-medium bg-purple-500/20 text-purple-300 rounded flex items-center gap-1">
                  <Shield className="w-2.5 h-2.5" />
                  {account.prop_firm.toUpperCase()}
                </span>
              )}
            </div>
            <p className="text-sm text-slate-400">
              {isCex ? (
                <span className="capitalize">{account.exchange}</span>
              ) : (
                <>
                  {getChainName(account.chain_id || 1)}
                  {account.short_address && (
                    <span className="font-mono ml-1">{account.short_address}</span>
                  )}
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Bot count badge */}
          {account.bot_count > 0 && (
            <span className="text-xs text-slate-400 bg-slate-700 px-2 py-1 rounded">
              {account.bot_count} bot{account.bot_count !== 1 ? 's' : ''}
            </span>
          )}

          {/* Actions menu */}
          <div className="relative">
            <button
              onClick={onMenuToggle}
              disabled={isDeleting}
              className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
            >
              <MoreVertical className="w-4 h-4 text-slate-400" />
            </button>

            {isMenuOpen && (
              <div className="absolute right-0 bottom-full mb-1 w-56 bg-slate-800 rounded-lg shadow-xl border border-slate-700 z-50 py-1">
                <button
                  onClick={onSetDefault}
                  disabled={account.is_default}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-left hover:bg-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {account.is_default ? (
                    <>
                      <StarOff className="w-4 h-4 text-slate-400" />
                      <span>Already Default</span>
                    </>
                  ) : (
                    <>
                      <Star className="w-4 h-4 text-yellow-400" />
                      <span>Set as Default</span>
                    </>
                  )}
                </button>

                {/* Portfolio Conversion Options (CEX only) */}
                {onConvertToBTC && onConvertToUSD && (
                  <>
                    <div className="border-t border-slate-700 my-1" />
                    <div className="px-3 py-1.5">
                      <p className="text-xs text-slate-500 uppercase font-semibold">Convert Portfolio</p>
                    </div>
                    <button
                      onClick={() => {
                        onMenuToggle()
                        onConvertToBTC()
                      }}
                      disabled={isConverting}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm text-left text-orange-400 hover:bg-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <ArrowRightLeft className="w-4 h-4" />
                      <span>Convert to BTC</span>
                    </button>
                    <button
                      onClick={() => {
                        onMenuToggle()
                        onConvertToUSD()
                      }}
                      disabled={isConverting}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm text-left text-green-400 hover:bg-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <ArrowRightLeft className="w-4 h-4" />
                      <span>Convert to USD</span>
                    </button>
                  </>
                )}

                <div className="border-t border-slate-700 my-1" />
                <button
                  onClick={onDelete}
                  disabled={account.bot_count > 0}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-left text-red-400 hover:bg-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Trash2 className="w-4 h-4" />
                  <span>{account.bot_count > 0 ? 'Has Active Bots' : 'Delete Account'}</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Expanded section: Perpetual Futures (CEX only) */}
      {isCex && isExpanded && (
        <div className="px-4 pb-3">
          <div className="ml-10 space-y-3">
            {/* Perpetual Futures (Coinbase INTX only) */}
            {(!account.exchange || account.exchange === 'coinbase') && (
            <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/50">
              <div className="flex items-center gap-2 mb-2">
                <Link2 className="w-4 h-4 text-purple-400" />
                <span className="text-sm font-medium text-white">Perpetual Futures</span>
              </div>

              {hasPerps ? (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-sm">
                    <CheckCircle className="w-3.5 h-3.5 text-green-400" />
                    <span className="text-green-400">INTX Portfolio Linked</span>
                  </div>
                  <div className="text-xs text-slate-400 font-mono">
                    UUID: {account.perps_portfolio_uuid}
                  </div>
                  <div className="text-xs text-slate-400">
                    Leverage: {account.default_leverage || 1}x | Margin: {account.margin_type || 'CROSS'}
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs text-slate-400">
                    Link your Coinbase INTX perpetuals portfolio to enable futures trading.
                  </p>
                  {perpsError && (
                    <div className="flex items-center gap-2 text-xs text-red-400">
                      <AlertCircle className="w-3.5 h-3.5" />
                      {perpsError}
                    </div>
                  )}
                  <button
                    onClick={handleLinkPerps}
                    disabled={linking}
                    className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-xs font-medium rounded-lg transition-colors"
                  >
                    {linking ? 'Discovering...' : 'Link Perpetuals Portfolio'}
                  </button>
                </div>
              )}
            </div>
            )}

            {/* PropGuard Status (prop firm accounts only) */}
            {account.prop_firm && (
              <PropGuardStatus account={account} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default AccountsManagement
