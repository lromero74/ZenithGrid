/**
 * Account Switcher Component
 *
 * Dropdown component for switching between CEX and DEX accounts.
 * Displays in the header and shows:
 * - Current selected account
 * - "Your Accounts" section (owned)
 * - "Shared With You" section (membership-based, with role badge)
 * - Pending invitations badge
 * - Option to add new accounts
 */

import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Plus, Building2, Wallet, Check, Settings, Users, FlaskConical } from 'lucide-react'
import { useAccount, getChainName, Account } from '../../contexts/AccountContext'
import { useAuth } from '../../contexts/AuthContext'
import { usePermission } from '../../hooks/usePermission'

interface AccountSwitcherProps {
  onAddAccount?: () => void
  onManageAccounts?: () => void
}

export function AccountSwitcher({ onAddAccount, onManageAccounts }: AccountSwitcherProps) {
  const {
    accounts,
    selectedAccount,
    selectAccount,
    isLoading,
    pendingInvitationCount,
    isOwner,
    getOwnedAccounts,
    getSharedAccounts,
  } = useAccount()
  const { user } = useAuth()
  const isSuperuser = user?.is_superuser ?? false
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
      if (event.key === 'Escape') setIsOpen(false)
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [])

  const handleSelect = (accountId: number) => {
    selectAccount(accountId)
    setIsOpen(false)
  }

  // Owners always see their own accounts (including paper trading).
  // Admins (superusers) also see paper trading accounts they manage via membership.
  // Other shared accounts hide paper trading (non-admin members shouldn't see demo accounts).
  const ownedAccounts = getOwnedAccounts()
  const sharedAccounts = getSharedAccounts().filter(
    (a) => !a.is_paper_trading || isSuperuser
  )

  // Separate real vs paper within owned, then CEX/DEX within real
  const ownedPaper = ownedAccounts.filter((a) => a.is_paper_trading)
  const ownedRealAccounts = ownedAccounts.filter((a) => !a.is_paper_trading)
  const ownedCex = ownedRealAccounts.filter((a) => a.type === 'cex')
  const ownedDex = ownedRealAccounts.filter((a) => a.type === 'dex')

  // Hide account switcher when paper trading is active ONLY for non-owners and non-admins
  if (selectedAccount?.is_paper_trading === true && !isOwner(selectedAccount) && !isSuperuser) return <></>

  if (isLoading) {
    return (
      <div className="flex items-center space-x-2 px-3 py-2 bg-slate-700 rounded-lg animate-pulse">
        <div className="w-4 h-4 bg-slate-600 rounded" />
        <div className="w-20 h-4 bg-slate-600 rounded" />
      </div>
    )
  }

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

  const isSelectedShared = selectedAccount && !isOwner(selectedAccount)

  return (
    <div className="relative flex" ref={dropdownRef}>
      {/* Trigger Button */}
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center space-x-1.5 sm:space-x-2 px-2 sm:px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg border border-slate-600 transition-colors min-w-0 h-[38px]"
        >
          {selectedAccount?.type === 'cex' ? (
            <Building2 className={`w-3.5 h-3.5 sm:w-4 sm:h-4 flex-shrink-0 ${isSelectedShared ? 'text-violet-400' : 'text-blue-400'}`} />
          ) : (
            <Wallet className={`w-3.5 h-3.5 sm:w-4 sm:h-4 flex-shrink-0 ${isSelectedShared ? 'text-violet-400' : 'text-orange-400'}`} />
          )}
          <span className="text-xs sm:text-sm font-medium truncate flex-1 min-w-0 text-left">
            {selectedAccount?.name || 'Select Account'}
          </span>
          {isSelectedShared && (
            <span className="hidden sm:block text-[10px] font-medium px-1.5 py-0.5 bg-violet-500/20 text-violet-300 rounded capitalize">
              {selectedAccount.membership_role}
            </span>
          )}
          <ChevronDown
            className={`w-3.5 h-3.5 sm:w-4 sm:h-4 text-slate-400 transition-transform flex-shrink-0 ${isOpen ? 'rotate-180' : ''}`}
          />
        </button>

        {/* Pending invitations badge */}
        {pendingInvitationCount > 0 && (
          <span className="absolute -top-1.5 -right-1.5 bg-violet-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center leading-none">
            {pendingInvitationCount > 9 ? '9+' : pendingInvitationCount}
          </span>
        )}
      </div>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 mt-10 w-80 bg-slate-800 rounded-lg shadow-xl border border-slate-700 z-50 overflow-hidden">
          <div className="max-h-[480px] overflow-y-auto">

            {/* Your Accounts */}
            {(ownedCex.length > 0 || ownedDex.length > 0) && (
              <div className="p-2">
                <div className="flex items-center space-x-2 px-2 py-1.5 text-xs font-medium text-slate-400 uppercase tracking-wider">
                  <span>Your Accounts</span>
                </div>

                {ownedCex.length > 0 && (
                  <>
                    <div className="flex items-center space-x-2 px-2 py-1 text-[11px] font-medium text-slate-500">
                      <Building2 className="w-3 h-3" />
                      <span>Exchanges</span>
                    </div>
                    {ownedCex.map((account) => (
                      <AccountOption
                        key={account.id}
                        account={account}
                        isSelected={selectedAccount?.id === account.id}
                        onSelect={() => handleSelect(account.id)}
                      />
                    ))}
                  </>
                )}

                {ownedDex.length > 0 && (
                  <>
                    <div className="flex items-center space-x-2 px-2 py-1 text-[11px] font-medium text-slate-500 mt-1">
                      <Wallet className="w-3 h-3" />
                      <span>DEX Wallets</span>
                    </div>
                    {ownedDex.map((account) => (
                      <AccountOption
                        key={account.id}
                        account={account}
                        isSelected={selectedAccount?.id === account.id}
                        onSelect={() => handleSelect(account.id)}
                      />
                    ))}
                  </>
                )}
              </div>
            )}

            {/* Paper Trading (owned) */}
            {ownedPaper.length > 0 && (
              <div className={`p-2 ${(ownedCex.length > 0 || ownedDex.length > 0) ? 'border-t border-slate-700' : ''}`}>
                <div className="flex items-center space-x-2 px-2 py-1.5 text-xs font-medium text-slate-400 uppercase tracking-wider">
                  <FlaskConical className="w-3 h-3" />
                  <span>Paper Trading</span>
                </div>
                {ownedPaper.map((account) => (
                  <AccountOption
                    key={account.id}
                    account={account}
                    isSelected={selectedAccount?.id === account.id}
                    onSelect={() => handleSelect(account.id)}
                    isPaper
                  />
                ))}
              </div>
            )}

            {/* Shared With You */}
            {sharedAccounts.length > 0 && (
              <div className={`p-2 ${(ownedCex.length > 0 || ownedDex.length > 0) ? 'border-t border-slate-700' : ''}`}>
                <div className="flex items-center space-x-2 px-2 py-1.5 text-xs font-medium text-slate-400 uppercase tracking-wider">
                  <Users className="w-3 h-3" />
                  <span>Shared With You</span>
                </div>
                {sharedAccounts.map((account) => (
                  <AccountOption
                    key={account.id}
                    account={account}
                    isSelected={selectedAccount?.id === account.id}
                    onSelect={() => handleSelect(account.id)}
                    isShared
                  />
                ))}
              </div>
            )}

            {/* Pending invitations hint */}
            {pendingInvitationCount > 0 && (
              <div className="px-4 py-2 border-t border-slate-700 bg-violet-900/20">
                <p className="text-xs text-violet-300">
                  {pendingInvitationCount} pending invitation{pendingInvitationCount !== 1 ? 's' : ''} —
                  check <span className="underline cursor-pointer" onClick={() => { setIsOpen(false); onManageAccounts?.() }}>Settings</span> to review
                </p>
              </div>
            )}
          </div>

          {/* Actions Section */}
          <div className="border-t border-slate-700 p-2">
            <button
              onClick={canWriteAccounts ? () => { setIsOpen(false); onAddAccount?.() } : undefined}
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
              onClick={() => { setIsOpen(false); onManageAccounts?.() }}
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
  account: Account
  isSelected: boolean
  onSelect: () => void
  isShared?: boolean
  isPaper?: boolean
}

function AccountOption({ account, isSelected, onSelect, isShared, isPaper }: AccountOptionProps) {
  return (
    <button
      onClick={onSelect}
      className={`flex items-center justify-between w-full px-3 py-2 rounded-lg transition-colors ${
        isSelected
          ? isShared ? 'bg-violet-600/20 text-violet-200'
            : isPaper ? 'bg-emerald-600/20 text-emerald-200'
            : 'bg-blue-600/20 text-blue-300'
          : 'text-slate-300 hover:bg-slate-700'
      }`}
    >
      <div className="flex items-center space-x-3 min-w-0">
        {isPaper ? (
          <FlaskConical className="w-5 h-5 flex-shrink-0 text-emerald-400" />
        ) : account.type === 'cex' ? (
          <Building2 className={`w-5 h-5 flex-shrink-0 ${isShared ? 'text-violet-400' : 'text-blue-400'}`} />
        ) : (
          <Wallet className={`w-5 h-5 flex-shrink-0 ${isShared ? 'text-violet-400' : 'text-orange-400'}`} />
        )}
        <div className="flex flex-col items-start min-w-0">
          <div className="flex items-center space-x-2 flex-wrap gap-y-0.5">
            <span className="text-sm font-medium truncate">{account.name}</span>
            {account.is_default && !isShared && (
              <span className="px-1.5 py-0.5 text-[10px] font-medium bg-blue-500/20 text-blue-300 rounded">
                DEFAULT
              </span>
            )}
            {isShared && account.membership_role && (
              <span className="px-1.5 py-0.5 text-[10px] font-medium bg-violet-500/20 text-violet-300 rounded capitalize">
                {account.membership_role}
              </span>
            )}
          </div>
          <span className="text-xs text-slate-400">
            {isShared && account.shared_by ? (
              <span className="text-violet-400/70">via {account.shared_by}</span>
            ) : account.type === 'cex' ? (
              <span className="capitalize">{account.exchange}</span>
            ) : (
              <>
                {getChainName(account.chain_id || 1)}
                {account.short_address && ` · ${account.short_address}`}
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

      {isSelected && <Check className={`w-4 h-4 flex-shrink-0 ${
        isShared ? 'text-violet-400' : isPaper ? 'text-emerald-400' : 'text-blue-400'
      }`} />}
    </button>
  )
}

export default AccountSwitcher
