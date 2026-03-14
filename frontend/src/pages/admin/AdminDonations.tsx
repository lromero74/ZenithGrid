/**
 * Admin Donations Tab
 *
 * Manage donation goal, confirm/reject self-reports, add donations manually.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Heart, Check, X, Plus, RefreshCw, Edit2,
} from 'lucide-react'
import {
  donationsApi, type DonationGoal, type DonationRecord,
} from '../../services/api'
import { useConfirm } from '../../contexts/ConfirmContext'

export function AdminDonations() {
  const [goal, setGoal] = useState<DonationGoal | null>(null)
  const [donations, setDonations] = useState<DonationRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [editingGoal, setEditingGoal] = useState(false)
  const [goalInput, setGoalInput] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const confirm = useConfirm()

  // Add form state
  const [addAmount, setAddAmount] = useState('')
  const [addMethod, setAddMethod] = useState('paypal')
  const [addDonor, setAddDonor] = useState('')
  const [addNotes, setAddNotes] = useState('')
  const [addRef, setAddRef] = useState('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [goalData, donationData] = await Promise.all([
        donationsApi.getGoal(),
        donationsApi.list(statusFilter ? { status: statusFilter } : undefined),
      ])
      setGoal(goalData)
      setDonations(donationData)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load donations')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { fetchData() }, [fetchData])

  const handleConfirm = async (id: number) => {
    const ok = await confirm({
      title: 'Confirm Donation',
      message: 'Confirm this donation? It will count toward the monthly goal.',
      confirmLabel: 'Confirm',
    })
    if (!ok) return
    try {
      await donationsApi.confirm(id)
      fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to confirm')
    }
  }

  const handleReject = async (id: number) => {
    const ok = await confirm({
      title: 'Reject Donation',
      message: 'Reject this donation report?',
      confirmLabel: 'Reject',
      variant: 'danger',
    })
    if (!ok) return
    try {
      await donationsApi.reject(id)
      fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reject')
    }
  }

  const handleSaveGoal = async () => {
    const target = parseFloat(goalInput)
    if (!target || target <= 0) return
    try {
      await donationsApi.updateGoal(target)
      setEditingGoal(false)
      fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update goal')
    }
  }

  const handleAddDonation = async () => {
    const amount = parseFloat(addAmount)
    if (!amount || amount <= 0) return
    try {
      await donationsApi.add({
        amount,
        currency: 'USD',
        payment_method: addMethod,
        donor_name: addDonor || undefined,
        notes: addNotes || undefined,
        tx_reference: addRef || undefined,
      })
      setShowAddForm(false)
      setAddAmount('')
      setAddMethod('paypal')
      setAddDonor('')
      setAddNotes('')
      setAddRef('')
      fetchData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add donation')
    }
  }

  const pendingCount = donations.filter(d => d.status === 'pending').length

  const statusColor = (status: string) => {
    if (status === 'confirmed') return 'text-emerald-400 bg-emerald-900/30'
    if (status === 'rejected') return 'text-red-400 bg-red-900/30'
    return 'text-amber-400 bg-amber-900/30'
  }

  if (loading && donations.length === 0) {
    return <div className="text-center text-slate-400 py-8">Loading donations...</div>
  }

  return (
    <div className="space-y-5">
      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-300 rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}

      {/* Goal + Stats */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Heart className="w-4 h-4 text-rose-400" />
            Quarterly Goal
          </h3>
          <div className="flex items-center gap-2">
            {editingGoal ? (
              <div className="flex items-center gap-1.5">
                <span className="text-slate-400 text-sm">$</span>
                <input
                  type="number"
                  value={goalInput}
                  onChange={e => setGoalInput(e.target.value)}
                  className="w-24 px-2 py-1 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                  autoFocus
                />
                <button onClick={handleSaveGoal} className="p-1 text-emerald-400 hover:text-emerald-300">
                  <Check className="w-4 h-4" />
                </button>
                <button onClick={() => setEditingGoal(false)} className="p-1 text-slate-400 hover:text-white">
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => { setEditingGoal(true); setGoalInput(String(goal?.target ?? 100)) }}
                className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
              >
                <Edit2 className="w-3 h-3" /> Edit
              </button>
            )}
          </div>
        </div>

        {goal && (
          <>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-slate-400">{goal.quarter}</span>
              <span className="text-white font-medium">
                ${goal.current.toFixed(2)} / ${goal.target.toFixed(0)}
              </span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-2.5 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all"
                style={{ width: `${Math.min(goal.percentage, 100)}%` }}
              />
            </div>
            <div className="flex justify-between text-xs mt-1.5 text-slate-500">
              <span>{goal.donation_count} confirmed donation{goal.donation_count !== 1 ? 's' : ''} this quarter</span>
              <span className="text-emerald-400">{goal.percentage}%</span>
            </div>
          </>
        )}
      </div>

      {/* Actions bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded text-sm text-slate-300"
          >
            <option value="">All Status</option>
            <option value="pending">Pending ({pendingCount})</option>
            <option value="confirmed">Confirmed</option>
            <option value="rejected">Rejected</option>
          </select>
          <button onClick={fetchData} className="p-1.5 text-slate-400 hover:text-white rounded hover:bg-slate-700">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" /> Add Donation
        </button>
      </div>

      {/* Add form */}
      {showAddForm && (
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 space-y-3">
          <h4 className="text-sm font-medium text-slate-200">Add Confirmed Donation</h4>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Amount (USD)</label>
              <input
                type="number" min="0.01" step="0.01" value={addAmount}
                onChange={e => setAddAmount(e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                placeholder="25.00"
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Method</label>
              <select value={addMethod} onChange={e => setAddMethod(e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-sm text-white">
                <option value="btc">Bitcoin</option>
                <option value="usdc">USDC</option>
                <option value="paypal">PayPal</option>
                <option value="venmo">Venmo</option>
                <option value="cashapp">CashApp</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Donor Name</label>
              <input type="text" value={addDonor} onChange={e => setAddDonor(e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                placeholder="Anonymous" />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Transaction Ref</label>
              <input type="text" value={addRef} onChange={e => setAddRef(e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                placeholder="Optional" />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Notes</label>
              <input type="text" value={addNotes} onChange={e => setAddNotes(e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                placeholder="Optional" />
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={handleAddDonation}
              disabled={!addAmount || parseFloat(addAmount) <= 0}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded text-sm font-medium transition-colors">
              Add
            </button>
            <button onClick={() => setShowAddForm(false)}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-sm transition-colors">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Donations table */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-slate-400">
              <th className="text-left p-3">Donor</th>
              <th className="text-right p-3">Amount</th>
              <th className="text-left p-3 hidden sm:table-cell">Method</th>
              <th className="text-center p-3">Status</th>
              <th className="text-left p-3 hidden sm:table-cell">Date</th>
              <th className="text-right p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {donations.length === 0 && (
              <tr><td colSpan={6} className="text-center text-slate-500 py-6">No donations found</td></tr>
            )}
            {donations.map(d => (
              <tr key={d.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                <td className="p-3">
                  <p className="font-medium text-slate-200">{d.donor_name || d.user_name || 'Anonymous'}</p>
                  {d.tx_reference && <p className="text-xs text-slate-500 truncate max-w-[150px]">{d.tx_reference}</p>}
                </td>
                <td className="p-3 text-right">
                  <span className="text-white font-medium">${d.amount.toFixed(2)}</span>
                  {d.currency !== 'USD' && <span className="text-xs text-slate-500 ml-1">{d.currency}</span>}
                </td>
                <td className="p-3 hidden sm:table-cell">
                  <span className="text-xs text-slate-400 capitalize">{d.payment_method}</span>
                </td>
                <td className="p-3 text-center">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${statusColor(d.status)}`}>
                    {d.status}
                  </span>
                </td>
                <td className="p-3 hidden sm:table-cell text-xs text-slate-500">
                  {d.donation_date ? new Date(d.donation_date).toLocaleDateString() : '—'}
                </td>
                <td className="p-3 text-right">
                  {d.status === 'pending' && (
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => handleConfirm(d.id)}
                        className="p-1 text-emerald-400 hover:text-emerald-300 hover:bg-slate-700 rounded"
                        title="Confirm">
                        <Check className="w-4 h-4" />
                      </button>
                      <button onClick={() => handleReject(d.id)}
                        className="p-1 text-red-400 hover:text-red-300 hover:bg-slate-700 rounded"
                        title="Reject">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
