/**
 * Paper Trading Toggle Component
 *
 * Toggle switch in the header that switches between live CEX trading and paper trading mode.
 * Automatically selects the appropriate account based on toggle state.
 */

import { useState, useEffect } from 'react'
import { FlaskConical, TrendingUp, Lock } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAccount } from '../contexts/AccountContext'

export function PaperTradingToggle() {
  const { accounts, selectedAccount, selectAccount } = useAccount()
  const [isPaperMode, setIsPaperMode] = useState(false)
  const [showTooltip, setShowTooltip] = useState(false)
  const navigate = useNavigate()

  // Determine if current account is paper trading
  useEffect(() => {
    if (selectedAccount) {
      setIsPaperMode(selectedAccount.is_paper_trading || false)
    }
  }, [selectedAccount])

  const paperAccount = accounts.find((acc) => acc.is_paper_trading)
  const liveAccount = accounts.find((acc) => acc.type === 'cex' && !acc.is_paper_trading)
  const hasLiveAccount = !!liveAccount

  // If no live account exists, always treat as paper mode regardless of state
  const effectivePaperMode = !hasLiveAccount || isPaperMode

  const handleToggle = () => {
    if (!hasLiveAccount && effectivePaperMode) {
      // No live account — show tooltip instead of toggling
      setShowTooltip(true)
      setTimeout(() => setShowTooltip(false), 3000)
      return
    }

    const newPaperMode = !isPaperMode

    if (newPaperMode) {
      // Switch to paper trading account
      if (paperAccount) {
        selectAccount(paperAccount.id)
      } else {
        console.error('No paper trading account found')
      }
    } else {
      // Switch back to default CEX account (or first non-paper CEX account)
      const cexAccount = accounts.find((acc) => acc.type === 'cex' && !acc.is_paper_trading && acc.is_default)
        || accounts.find((acc) => acc.type === 'cex' && !acc.is_paper_trading)

      if (cexAccount) {
        selectAccount(cexAccount.id)
      } else {
        console.error('No live CEX account found')
      }
    }
  }

  // Only hide if there's no paper account at all
  if (!paperAccount) {
    return null
  }

  return (
    <div className="relative flex items-center space-x-1.5 sm:space-x-2 px-2 sm:px-3 py-2 bg-slate-700 rounded-lg border border-slate-600">
      {/* Live Trading Icon */}
      <div className={`flex items-center space-x-1 transition-opacity ${
        !hasLiveAccount ? 'opacity-25' : !effectivePaperMode ? 'opacity-100' : 'opacity-40'
      }`}>
        {!hasLiveAccount ? (
          <Lock className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-slate-400" />
        ) : (
          <TrendingUp className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-green-400" />
        )}
        <span className={`text-xs font-medium hidden sm:inline ${
          !hasLiveAccount ? 'text-slate-400' : 'text-green-400'
        }`}>Live</span>
      </div>

      {/* Toggle Switch */}
      <button
        onClick={handleToggle}
        className={`relative inline-flex h-5 w-9 sm:h-6 sm:w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-slate-700 ${
          !hasLiveAccount ? 'bg-orange-600 cursor-not-allowed' : effectivePaperMode ? 'bg-orange-600' : 'bg-green-600'
        }`}
        role="switch"
        aria-checked={effectivePaperMode}
        aria-disabled={!hasLiveAccount && effectivePaperMode}
        title={
          !hasLiveAccount
            ? 'Add a live account in Settings to enable live trading'
            : effectivePaperMode
              ? 'Switch to Live Trading'
              : 'Switch to Paper Trading'
        }
      >
        <span
          className={`inline-block h-3.5 w-3.5 sm:h-4 sm:w-4 transform rounded-full bg-white transition-transform ${
            effectivePaperMode ? 'translate-x-[18px] sm:translate-x-6' : 'translate-x-0.5 sm:translate-x-1'
          }`}
        />
      </button>

      {/* Paper Trading Icon */}
      <div className={`flex items-center space-x-1 transition-opacity ${effectivePaperMode ? 'opacity-100' : 'opacity-40'}`}>
        <FlaskConical className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-yellow-400" />
        <span className="text-xs font-medium text-yellow-400 hidden sm:inline">Paper</span>
      </div>

      {/* Tooltip for no live account */}
      {showTooltip && (
        <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 z-50 w-56 px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg shadow-lg">
          <p className="text-xs text-slate-300 mb-1.5">Add a live exchange account to enable live trading.</p>
          <button
            onClick={() => { setShowTooltip(false); navigate('/settings') }}
            className="text-xs font-medium text-blue-400 hover:text-blue-300 transition-colors"
          >
            Go to Settings &rarr;
          </button>
          <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-slate-800 border-l border-t border-slate-600 rotate-45" />
        </div>
      )}
    </div>
  )
}

export default PaperTradingToggle
