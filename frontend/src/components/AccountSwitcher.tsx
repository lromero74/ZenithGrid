/**
 * Account Switcher Component
 *
 * Dropdown component for switching between CEX and DEX accounts.
 * Displays in the header and shows:
 * - Current selected account
 * - List of CEX accounts (Coinbase)
 * - List of DEX wallets (MetaMask, etc.)
 * - Option to add new accounts
 */

import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Plus, Building2, Wallet, Check, Settings } from 'lucide-react'
import { useAccount, getChainName } from '../contexts/AccountContext'
import { usePermission } from '../hooks/usePermission'

interface AccountSwitcherProps {
  onAddAccount?: () => void
  onManageAccounts?: () => void
}

export function AccountSwitcher({ onAddAccount, onManageAccounts }: AccountSwitcherProps) {
  const { accounts, selectedAccount, selectAccount, isLoading } = useAccount()
  const canWriteAccounts = usePermission('accounts', 'write')
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Close on escape key
  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false)
      }
    }

    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [])

  // Exclude paper trading accounts from dropdown (controlled by toggle switch instead)
  const cexAccounts = accounts.filter((a) => a.type === 'cex' && !a.is_paper_trading)
  const dexAccounts = accounts.filter((a) => a.type === 'dex')

  const handleSelect = (accountId: number) => {
    selectAccount(accountId)
    setIsOpen(false)
  }

  // Hide account switcher when paper trading is active
  if (selectedAccount?.is_paper_trading === true) {
    return <></>
  }

  if (isLoading) {
    return (
      <div className="flex items-center space-x-2 px-3 py-2 bg-slate-700 rounded-lg animate-pulse">
        <div className="w-4 h-4 bg-slate-600 rounded" />
        <div className="w-20 h-4 bg-slate-600 rounded" />
      </div>
    )
  }

  // If no accounts, show add account button
  if (accounts.length === 0) {
    return (
      <button
        onClick={canWriteAccounts ? onAddAccount : undefined}
        disabled={!canWriteAccounts}
        className={`flex items-center space-x-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
          canWriteAccounts
            ? 'bg-blue-600 hover:bg-blue-500'
            : 'bg-slate-700 text-slate-500 cursor-not-allowed'
        }`}
        title={!canWriteAccounts ? 'Read-only account' : undefined}
      >
        <Plus className="w-4 h-4" />
        <span>Add Account</span>
      </button>
    )
  }

  return (
    <div className="relative flex" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center space-x-1.5 sm:space-x-2 px-2 sm:px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg border border-slate-600 transition-colors min-w-0 h-[38px]"
      >
        {selectedAccount?.type === 'cex' ? (
          <Building2 className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-blue-400 flex-shrink-0" />
        ) : (
          <Wallet className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-orange-400 flex-shrink-0" />
        )}
        <span className="text-xs sm:text-sm font-medium truncate flex-1 min-w-0 text-left">
          {selectedAccount?.name || 'Select Account'}
        </span>
        <ChevronDown
          className={`w-3.5 h-3.5 sm:w-4 sm:h-4 text-slate-400 transition-transform flex-shrink-0 ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-72 bg-slate-800 rounded-lg shadow-xl border border-slate-700 z-50 overflow-hidden">
          <div className="max-h-96 overflow-y-auto">
            {/* CEX Accounts Section */}
            {cexAccounts.length > 0 && (
              <div className="p-2">
                <div className="flex items-center space-x-2 px-2 py-1.5 text-xs font-medium text-slate-400 uppercase tracking-wider">
                  <Building2 className="w-3 h-3" />
                  <span>Centralized Exchanges</span>
                </div>
                {cexAccounts.map((account) => (
                  <AccountOption
                    key={account.id}
                    account={account}
                    isSelected={selectedAccount?.id === account.id}
                    onSelect={() => handleSelect(account.id)}
                  />
                ))}
              </div>
            )}

            {/* DEX Accounts Section */}
            {dexAccounts.length > 0 && (
              <div className="p-2 border-t border-slate-700">
                <div className="flex items-center space-x-2 px-2 py-1.5 text-xs font-medium text-slate-400 uppercase tracking-wider">
                  <Wallet className="w-3 h-3" />
                  <span>DEX Wallets</span>
                </div>
                {dexAccounts.map((account) => (
                  <AccountOption
                    key={account.id}
                    account={account}
                    isSelected={selectedAccount?.id === account.id}
                    onSelect={() => handleSelect(account.id)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Actions Section */}
          <div className="border-t border-slate-700 p-2 bg-slate-850">
            <button
              onClick={canWriteAccounts ? () => {
                setIsOpen(false)
                onAddAccount?.()
              } : undefined}
              disabled={!canWriteAccounts}
              className={`flex items-center space-x-2 w-full px-3 py-2 text-sm rounded-lg transition-colors ${
                canWriteAccounts
                  ? 'text-slate-300 hover:bg-slate-700'
                  : 'text-slate-500 cursor-not-allowed'
              }`}
              title={!canWriteAccounts ? 'Read-only account' : undefined}
            >
              <Plus className={`w-4 h-4 ${canWriteAccounts ? 'text-blue-400' : 'text-slate-600'}`} />
              <span>Add Account</span>
            </button>
            <button
              onClick={() => {
                setIsOpen(false)
                onManageAccounts?.()
              }}
              className="flex items-center space-x-2 w-full px-3 py-2 text-sm text-slate-300 hover:bg-slate-700 rounded-lg transition-colors"
            >
              <Settings className="w-4 h-4 text-slate-400" />
              <span>Manage Accounts</span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// Account Option Component
// =============================================================================

interface AccountOptionProps {
  account: {
    id: number
    name: string
    type: 'cex' | 'dex'
    is_default: boolean
    exchange?: string
    chain_id?: number
    short_address?: string
    bot_count: number
  }
  isSelected: boolean
  onSelect: () => void
}

function AccountOption({ account, isSelected, onSelect }: AccountOptionProps) {
  return (
    <button
      onClick={onSelect}
      className={`flex items-center justify-between w-full px-3 py-2 rounded-lg transition-colors ${
        isSelected
          ? 'bg-blue-600/20 text-blue-300'
          : 'text-slate-300 hover:bg-slate-700'
      }`}
    >
      <div className="flex items-center space-x-3 min-w-0">
        {account.type === 'cex' ? (
          <Building2 className="w-5 h-5 text-blue-400 flex-shrink-0" />
        ) : (
          <Wallet className="w-5 h-5 text-orange-400 flex-shrink-0" />
        )}
        <div className="flex flex-col items-start min-w-0">
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium truncate">{account.name}</span>
            {account.is_default && (
              <span className="px-1.5 py-0.5 text-[10px] font-medium bg-blue-500/20 text-blue-300 rounded">
                DEFAULT
              </span>
            )}
          </div>
          <span className="text-xs text-slate-400">
            {account.type === 'cex' ? (
              <span className="capitalize">{account.exchange}</span>
            ) : (
              <>
                {getChainName(account.chain_id || 1)}
                {account.short_address && ` - ${account.short_address}`}
              </>
            )}
          </span>
          {account.bot_count > 0 && (
            <span className="text-xs text-slate-500">
              {account.bot_count} bot{account.bot_count !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {isSelected && <Check className="w-4 h-4 text-blue-400 flex-shrink-0" />}
    </button>
  )
}

export default AccountSwitcher
