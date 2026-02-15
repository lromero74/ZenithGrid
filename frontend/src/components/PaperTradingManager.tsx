/**
 * Paper Trading Manager Component
 *
 * Displays paper trading account balance and provides controls for:
 * - Viewing current virtual balances
 * - Depositing virtual funds
 * - Withdrawing virtual funds
 * - Resetting account to defaults
 */

import { useState, useEffect } from 'react'
import { FlaskConical, Plus, Minus, RotateCcw, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { authFetch } from '../services/api'

interface PaperBalances {
  BTC: number
  ETH: number
  USD: number
  USDC: number
  USDT: number
}

interface PaperAccount {
  account_id: number
  account_name: string
  balances: PaperBalances
  is_paper_trading: boolean
}

export function PaperTradingManager() {
  const { getAccessToken } = useAuth()
  const [paperAccount, setPaperAccount] = useState<PaperAccount | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Deposit/Withdraw state
  const [showDepositModal, setShowDepositModal] = useState(false)
  const [showWithdrawModal, setShowWithdrawModal] = useState(false)
  const [selectedCurrency, setSelectedCurrency] = useState<keyof PaperBalances>('USD')
  const [amount, setAmount] = useState('')
  const [processing, setProcessing] = useState(false)

  // Reset state
  const [showResetConfirm, setShowResetConfirm] = useState(false)

  useEffect(() => {
    loadPaperAccount()
  }, [])

  const loadPaperAccount = async () => {
    try {
      setLoading(true)
      const token = getAccessToken()
      const response = await authFetch('/api/paper-trading/balance', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      if (response.ok) {
        const data = await response.json()
        setPaperAccount(data)
      } else if (response.status === 404) {
        setError('Paper trading account not found')
      } else {
        throw new Error('Failed to load paper trading account')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load balance')
    } finally {
      setLoading(false)
    }
  }

  const handleDeposit = async () => {
    const depositAmount = parseFloat(amount)
    if (isNaN(depositAmount) || depositAmount <= 0) {
      setError('Please enter a valid positive amount')
      return
    }

    setProcessing(true)
    setError(null)
    setSuccess(null)

    try {
      const token = getAccessToken()
      const response = await authFetch('/api/paper-trading/deposit', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          currency: selectedCurrency,
          amount: depositAmount
        })
      })

      if (!response.ok) throw new Error('Deposit failed')

      const data = await response.json()
      setPaperAccount(prev => prev ? { ...prev, balances: data.balances } : null)
      setSuccess(`Deposited ${depositAmount} ${selectedCurrency} successfully`)
      setShowDepositModal(false)
      setAmount('')
      setTimeout(() => setSuccess(null), 5000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Deposit failed')
    } finally {
      setProcessing(false)
    }
  }

  const handleWithdraw = async () => {
    const withdrawAmount = parseFloat(amount)
    if (isNaN(withdrawAmount) || withdrawAmount <= 0) {
      setError('Please enter a valid positive amount')
      return
    }

    setProcessing(true)
    setError(null)
    setSuccess(null)

    try {
      const token = getAccessToken()
      const response = await authFetch('/api/paper-trading/withdraw', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          currency: selectedCurrency,
          amount: withdrawAmount
        })
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Withdrawal failed')
      }

      const data = await response.json()
      setPaperAccount(prev => prev ? { ...prev, balances: data.balances } : null)
      setSuccess(`Withdrew ${withdrawAmount} ${selectedCurrency} successfully`)
      setShowWithdrawModal(false)
      setAmount('')
      setTimeout(() => setSuccess(null), 5000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Withdrawal failed')
    } finally {
      setProcessing(false)
    }
  }

  const handleReset = async () => {
    setProcessing(true)
    setError(null)
    setSuccess(null)

    try {
      const token = getAccessToken()
      const response = await authFetch('/api/paper-trading/reset', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      if (!response.ok) throw new Error('Reset failed')

      const data = await response.json()
      setPaperAccount(prev => prev ? { ...prev, balances: data.balances } : null)
      setSuccess('Paper trading account reset to defaults. All history wiped.')
      setShowResetConfirm(false)
      setTimeout(() => setSuccess(null), 5000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
    } finally {
      setProcessing(false)
    }
  }

  if (loading) {
    return (
      <div className="card p-6">
        <div className="flex items-center space-x-3 mb-6">
          <FlaskConical className="w-6 h-6 text-yellow-400 animate-pulse" />
          <h3 className="text-xl font-semibold">Paper Trading</h3>
        </div>
        <p className="text-slate-400">Loading paper trading account...</p>
      </div>
    )
  }

  if (!paperAccount) {
    return (
      <div className="card p-6">
        <div className="flex items-center space-x-3 mb-6">
          <FlaskConical className="w-6 h-6 text-yellow-400" />
          <h3 className="text-xl font-semibold">Paper Trading</h3>
        </div>
        <p className="text-red-400">{error || 'Paper trading account not found'}</p>
      </div>
    )
  }

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <FlaskConical className="w-6 h-6 text-yellow-400" />
          <h3 className="text-xl font-semibold">Paper Trading</h3>
        </div>
        <span className="px-3 py-1 bg-yellow-500/20 text-yellow-300 text-sm font-medium rounded-full">
          Simulated Account
        </span>
      </div>

      {/* Success Message */}
      {success && (
        <div className="mb-4 p-4 bg-green-500/10 border border-green-500/50 rounded-lg flex items-center space-x-3">
          <CheckCircle2 className="w-5 h-5 text-green-400 flex-shrink-0" />
          <p className="text-green-400 text-sm">{success}</p>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-4 bg-red-500/10 border border-red-500/50 rounded-lg flex items-center space-x-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {/* Virtual Balances */}
      <div className="mb-6">
        <h4 className="text-sm font-medium text-slate-400 mb-3">Virtual Balances</h4>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {Object.entries(paperAccount.balances).map(([currency, balance]) => (
            <div key={currency} className="p-4 bg-slate-700/50 rounded-lg">
              <p className="text-xs text-slate-400 mb-1">{currency}</p>
              <p className="text-lg font-mono font-semibold text-white">
                {balance.toLocaleString(undefined, { minimumFractionDigits: currency === 'USD' ? 2 : 8, maximumFractionDigits: currency === 'USD' ? 2 : 8 })}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={() => setShowDepositModal(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>Deposit</span>
        </button>

        <button
          onClick={() => setShowWithdrawModal(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
        >
          <Minus className="w-4 h-4" />
          <span>Withdraw</span>
        </button>

        <button
          onClick={() => setShowResetConfirm(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white font-medium rounded-lg transition-colors"
        >
          <RotateCcw className="w-4 h-4" />
          <span>Reset to Defaults</span>
        </button>
      </div>

      {/* Deposit Modal */}
      {showDepositModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full">
            <h3 className="text-xl font-semibold mb-4">Deposit Virtual Funds</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Currency</label>
                <select
                  value={selectedCurrency}
                  onChange={(e) => setSelectedCurrency(e.target.value as keyof PaperBalances)}
                  className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-green-500"
                >
                  {Object.keys(paperAccount.balances).map((currency) => (
                    <option key={currency} value={currency}>{currency}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Amount</label>
                <input
                  type="number"
                  step="any"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0.00"
                  className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              </div>

              <div className="flex gap-3">
                <button
                  onClick={handleDeposit}
                  disabled={processing || !amount}
                  className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
                >
                  {processing ? 'Processing...' : 'Deposit'}
                </button>
                <button
                  onClick={() => { setShowDepositModal(false); setAmount(''); setError(null); }}
                  disabled={processing}
                  className="flex-1 px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white font-medium rounded-lg transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Withdraw Modal */}
      {showWithdrawModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full">
            <h3 className="text-xl font-semibold mb-4">Withdraw Virtual Funds</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Currency</label>
                <select
                  value={selectedCurrency}
                  onChange={(e) => setSelectedCurrency(e.target.value as keyof PaperBalances)}
                  className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {Object.keys(paperAccount.balances).map((currency) => (
                    <option key={currency} value={currency}>{currency}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Amount (Available: {paperAccount.balances[selectedCurrency].toLocaleString()})
                </label>
                <input
                  type="number"
                  step="any"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0.00"
                  className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex gap-3">
                <button
                  onClick={handleWithdraw}
                  disabled={processing || !amount}
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
                >
                  {processing ? 'Processing...' : 'Withdraw'}
                </button>
                <button
                  onClick={() => { setShowWithdrawModal(false); setAmount(''); setError(null); }}
                  disabled={processing}
                  className="flex-1 px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white font-medium rounded-lg transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Reset Confirmation Modal */}
      {showResetConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full">
            <div className="flex items-center space-x-3 mb-4">
              <AlertCircle className="w-6 h-6 text-orange-400" />
              <h3 className="text-xl font-semibold">Reset Paper Trading Account?</h3>
            </div>

            <div className="space-y-4">
              <p className="text-slate-300">
                This will:
              </p>
              <ul className="list-disc list-inside space-y-1 text-slate-400 text-sm">
                <li>Reset all balances to defaults (1 BTC, 10 ETH, 100k USD)</li>
                <li>Delete all paper trading positions</li>
                <li>Delete all paper trading trades</li>
                <li>Reset deal numbers to start from 1</li>
              </ul>
              <p className="text-orange-400 text-sm font-medium">
                This action cannot be undone.
              </p>

              <div className="flex gap-3">
                <button
                  onClick={handleReset}
                  disabled={processing}
                  className="flex-1 px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
                >
                  {processing ? 'Resetting...' : 'Yes, Reset Account'}
                </button>
                <button
                  onClick={() => { setShowResetConfirm(false); setError(null); }}
                  disabled={processing}
                  className="flex-1 px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white font-medium rounded-lg transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Info */}
      <div className="mt-6 p-4 bg-yellow-900/20 border border-yellow-600/30 rounded-lg">
        <p className="text-yellow-200/80 text-sm">
          <strong>Paper Trading Mode:</strong> All trades are simulated using real market prices.
          No real orders are placed on the exchange. Use this to test strategies risk-free.
        </p>
      </div>
    </div>
  )
}
