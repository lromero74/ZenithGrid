/**
 * Paper Trading Toggle Component
 *
 * Toggle switch in the header that switches between live CEX trading and paper trading mode.
 * Automatically selects the appropriate account based on toggle state.
 */

import { useState, useEffect } from 'react'
import { FlaskConical, TrendingUp } from 'lucide-react'
import { useAccount } from '../contexts/AccountContext'

export function PaperTradingToggle() {
  const { accounts, selectedAccount, selectAccount } = useAccount()
  const [isPaperMode, setIsPaperMode] = useState(false)

  // Determine if current account is paper trading
  useEffect(() => {
    if (selectedAccount) {
      setIsPaperMode(selectedAccount.is_paper_trading || false)
    }
  }, [selectedAccount])

  const handleToggle = () => {
    const newPaperMode = !isPaperMode

    if (newPaperMode) {
      // Switch to paper trading account
      const paperAccount = accounts.find((acc) => acc.is_paper_trading)
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

  const paperAccount = accounts.find((acc) => acc.is_paper_trading)
  const liveAccount = accounts.find((acc) => acc.type === 'cex' && !acc.is_paper_trading)

  // Don't show toggle if there's no paper account or no live account
  if (!paperAccount || !liveAccount) {
    return null
  }

  return (
    <div className="flex items-center space-x-2 px-3 py-2 bg-slate-700 rounded-lg border border-slate-600">
      {/* Live Trading Icon */}
      <div className={`flex items-center space-x-1 transition-opacity ${!isPaperMode ? 'opacity-100' : 'opacity-40'}`}>
        <TrendingUp className="w-4 h-4 text-green-400" />
        <span className="text-xs font-medium text-green-400 hidden sm:inline">Live</span>
      </div>

      {/* Toggle Switch */}
      <button
        onClick={handleToggle}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-slate-700 ${
          isPaperMode ? 'bg-yellow-600' : 'bg-green-600'
        }`}
        role="switch"
        aria-checked={isPaperMode}
        title={isPaperMode ? 'Switch to Live Trading' : 'Switch to Paper Trading'}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            isPaperMode ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>

      {/* Paper Trading Icon */}
      <div className={`flex items-center space-x-1 transition-opacity ${isPaperMode ? 'opacity-100' : 'opacity-40'}`}>
        <FlaskConical className="w-4 h-4 text-yellow-400" />
        <span className="text-xs font-medium text-yellow-400 hidden sm:inline">Paper</span>
      </div>
    </div>
  )
}

export default PaperTradingToggle
