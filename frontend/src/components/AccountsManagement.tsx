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
  AlertTriangle,
} from 'lucide-react'
import { useAccount, Account, getChainName } from '../contexts/AccountContext'
import { accountApi } from '../services/api'

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
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [sellingToBTC, setSellingToBTC] = useState(false)
  const [sellingToUSD, setSellingToUSD] = useState(false)

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

  const handleSellPortfolioToBase = async (targetCurrency: 'BTC' | 'USD') => {
    const currencySetter = targetCurrency === 'BTC' ? setSellingToBTC : setSellingToUSD

    if (!confirm(
      `🚨 CONVERT ENTIRE PORTFOLIO TO ${targetCurrency} 🚨\n\n` +
      `This will sell ALL your portfolio holdings (ETH, ADA, etc.) to ${targetCurrency}.\n\n` +
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
      const result = await accountApi.sellPortfolioToBase(targetCurrency, true)

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

      {/* Portfolio Conversion Section */}
      {accounts.length > 0 && (
        <div className="bg-orange-900/20 border border-orange-700 rounded-lg p-4">
          <div className="flex items-start gap-3 mb-3">
            <AlertTriangle className="w-5 h-5 text-orange-400 mt-0.5" />
            <div className="flex-1">
              <h4 className="text-orange-400 font-semibold mb-1">
                Portfolio Conversion
              </h4>
              <p className="text-sm text-orange-300">
                Convert your entire portfolio to BTC or USD. This sells all your holdings (ETH, ADA, etc.)
                at market price. Use after cancelling deals to consolidate into a single currency.
              </p>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => handleSellPortfolioToBase('BTC')}
              disabled={sellingToBTC}
              className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {sellingToBTC ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Converting...
                </>
              ) : (
                'Convert Portfolio to BTC'
              )}
            </button>
            <button
              onClick={() => handleSellPortfolioToBase('USD')}
              disabled={sellingToUSD}
              className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {sellingToUSD ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Converting...
                </>
              ) : (
                'Convert Portfolio to USD'
              )}
            </button>
          </div>
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
                onMenuToggle={() => setOpenMenuId(openMenuId === account.id ? null : account.id)}
                onDelete={() => handleDelete(account)}
                onSetDefault={() => handleSetDefault(account)}
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
  onMenuToggle: () => void
  onDelete: () => void
  onSetDefault: () => void
}

function AccountRow({
  account,
  isDeleting,
  isMenuOpen,
  onMenuToggle,
  onDelete,
  onSetDefault,
}: AccountRowProps) {
  return (
    <div className={`flex items-center justify-between px-4 py-3 ${isDeleting ? 'opacity-50' : ''}`}>
      <div className="flex items-center space-x-3 min-w-0">
        {account.type === 'cex' ? (
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
          </div>
          <p className="text-sm text-slate-400">
            {account.type === 'cex' ? (
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
            <div className="absolute right-0 bottom-full mb-1 w-48 bg-slate-800 rounded-lg shadow-xl border border-slate-700 z-50 py-1">
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
  )
}

export default AccountsManagement
